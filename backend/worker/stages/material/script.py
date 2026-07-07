from __future__ import annotations

import re
import time

from app.config import get_settings
from app.quality.quality_mgr import (
    apply_quality_checks,
    check_narration,
    merge_quality_report,
    skip_narration_check,
)
from app.repositories import repo_job_log, repo_job, repo_segment
from app.repositories.connection import connection
from app.services.llm.llm_mgr import llm_mgr
from app.services.script.script_mgr import script_mgr
from app.services.script.board_timeline import parse_video_timeline
from app.utils.job_cancel import job_cancel
from app.utils.media import (
    assign_segment_timings,
    base_video_duration_sec,
    estimate_narration_target_words,
    NARRATION_ABS_MIN_CHARS,
    narration_soft_min_chars,
)
from worker.context import JobContext
from worker.stages.base import StageExecutor
from worker.stages.standard.script import (
    ScriptValidationError,
    _apply_script_title,
    _apply_video_description,
    _min_narration_chars,
    _normalize_segments,
    _narration_chars,
    _title_chars,
)

MIN_ACCEPT_NARRATION_CHARS = NARRATION_ABS_MIN_CHARS


def _split_manual_narration(narration: str) -> list[dict]:
    parts = re.split(r"(?<=[。！？；\n])", narration.strip())
    segments: list[dict] = []
    index = 1
    for part in parts:
        text = part.strip()
        if not text:
            continue
        segments.append(
            {
                "segment_index": index,
                "text": text,
                "visual_mode": "material",
            }
        )
        index += 1
    if not segments:
        raise ScriptValidationError("narration is empty", retryable=False)
    return segments


def _timeline_length_mode(attempt: int) -> str:
    """重试越多校验越松，避免 LLM 略超字数死循环。"""
    if attempt >= 5:
        return "warn_only"
    if attempt >= 3:
        return "relaxed"
    return "strict"


def _validate_material_script(
    script: dict,
    *,
    max_title_length: int | None = None,
    min_narration_chars: int | None = None,
    video_timeline_raw: str | None = None,
    timeline_length_mode: str = "strict",
) -> list[str]:
    settings = get_settings()
    max_len = settings.max_title_length if max_title_length is None else max_title_length
    required_narration_chars = min_narration_chars or MIN_ACCEPT_NARRATION_CHARS
    narration = script.get("narration", "")
    segments = script.get("segments") or []
    warnings: list[str] = []
    chars = _narration_chars(narration)
    if chars < required_narration_chars:
        soft_min = narration_soft_min_chars(required_narration_chars)
        retry_min = max(MIN_ACCEPT_NARRATION_CHARS, int(required_narration_chars * 0.8))
        if chars >= soft_min:
            warnings.append(
                f"narration slightly short ({chars} < {required_narration_chars}), continuing"
            )
        elif chars >= retry_min:
            raise ScriptValidationError(
                f"narration too short: {chars} chars (need >= {required_narration_chars})",
                retryable=True,
            )
        elif chars < MIN_ACCEPT_NARRATION_CHARS:
            raise ScriptValidationError(
                f"narration too short: {chars} chars (need >= {MIN_ACCEPT_NARRATION_CHARS})",
                retryable=True,
            )
        else:
            warnings.append(
                f"narration shorter than target ({chars} < {required_narration_chars}), continuing"
            )
    if not segments:
        raise ScriptValidationError("no segments", retryable=False)
    title = _title_chars(script.get("title") or "")
    if not title:
        raise ScriptValidationError("title is empty", retryable=False)
    if len(title) > max_len:
        raise ScriptValidationError(f"title too long: {len(title)} chars (need <= {max_len})")
    script["title"] = title
    script["segments"] = _normalize_segments(segments)

    timeline = script_mgr.parse_timeline(video_timeline_raw)
    if timeline:
        timeline_error, timeline_warnings = script_mgr.validate_timeline(
            script,
            timeline,
            length_mode=timeline_length_mode,
        )
        warnings.extend(timeline_warnings)
        if timeline_error:
            raise ScriptValidationError(timeline_error, retryable=True)
    return warnings


class MaterialScriptStage(StageExecutor):
    """素材任务口播稿：无分镜出图字段。"""

    name = "script"

    def run(self, ctx: JobContext) -> None:
        started = time.perf_counter()
        title = ctx.job["title"]
        max_title_length = ctx.script_max_title_length
        narration_target_words = ctx.script_narration_target_words
        supplementary_info = (
            ctx.script_supplementary_info.strip()
            if ctx.script_supplementary_info and ctx.script_supplementary_info.strip()
            else None
        )
        video_timeline = (
            ctx.script_video_timeline.strip()
            if ctx.script_video_timeline and ctx.script_video_timeline.strip()
            else None
        )
        if narration_target_words is None:
            duration = base_video_duration_sec(job=ctx.job, media_dir=ctx.media_dir)
            if duration:
                narration_target_words = estimate_narration_target_words(duration)
                with connection() as conn:
                    repo_job_log.append_log(
                        conn,
                        ctx.job["id"],
                        self.name,
                        (
                            f"narration target from base duration {duration:.1f}s "
                            f"-> {narration_target_words} chars"
                        ),
                    )
        min_narration_chars = _min_narration_chars(narration_target_words)

        pending = ctx.job.get("script_json") or {}
        manual_narration = ctx.material_narration
        if manual_narration is None and isinstance(pending, dict):
            manual_narration = pending.get("pending_narration")

        script = None
        if manual_narration and str(manual_narration).strip():
            narration = str(manual_narration).strip()
            # 有时间表时，用AI按时间表分段生成，手动口播作为补充参考
            if video_timeline:
                extra = supplementary_info or ""
                extra += f"\n用户已提供口播素材（需融入或参考）：{narration}"
                supplementary_info = extra.strip()
            else:
                script = {
                    "title": _title_chars(title),
                    "narration": narration,
                    "segments": _split_manual_narration(narration),
                    "script_mode": "manual",
                }
                accept_warnings = _validate_material_script(
                    script,
                    max_title_length=max_title_length,
                    min_narration_chars=min_narration_chars,
                    video_timeline_raw=video_timeline,
                )

        if script is None:
            last_exc: Exception | None = None
            last_script: dict | None = None
            feedback: str | None = None
            accept_warnings: list[str] = []
            max_attempts = get_settings().script_qa_max_attempts
            for attempt in range(max_attempts):
                job_cancel.raise_if_cancelled(ctx.job["id"])
                length_mode = _timeline_length_mode(attempt)
                script = llm_mgr.generate_material_script(
                    title,
                    feedback=feedback,
                    max_title_length=max_title_length,
                    narration_target_words=narration_target_words,
                    supplementary_info=supplementary_info,
                    video_timeline=video_timeline,
                    job=ctx.job,
                )
                job_cancel.raise_if_cancelled(ctx.job["id"])
                last_script = script
                try:
                    accept_warnings = _validate_material_script(
                        script,
                        max_title_length=max_title_length,
                        min_narration_chars=min_narration_chars,
                        video_timeline_raw=video_timeline,
                        timeline_length_mode=length_mode,
                    )
                    break
                except ScriptValidationError as exc:
                    last_exc = exc
                    feedback = str(exc)
                    with connection() as conn:
                        repo_job_log.append_log(
                            conn,
                            ctx.job["id"],
                            self.name,
                            (
                                f"script rejected (attempt {attempt + 1}, "
                                f"timeline_check={length_mode}): {exc}"
                            ),
                            level="warning",
                        )
                    script = None
            if script is None and last_script is not None:
                try:
                    accept_warnings = _validate_material_script(
                        last_script,
                        max_title_length=max_title_length,
                        min_narration_chars=min_narration_chars,
                        video_timeline_raw=video_timeline,
                        timeline_length_mode="warn_only",
                    )
                    script = last_script
                    with connection() as conn:
                        repo_job_log.append_log(
                            conn,
                            ctx.job["id"],
                            self.name,
                            "timeline length checks exhausted; accepted last draft (warn_only)",
                            level="warning",
                        )
                except ScriptValidationError:
                    script = None
            if script is None:
                raise last_exc or RuntimeError("material script generation failed")
            script["script_mode"] = "ai"

        max_len = (
            max_title_length
            if max_title_length is not None
            else get_settings().max_title_length
        )
        _apply_script_title(
            script,
            source_title=title,
            max_len=max_len,
            skip_optimize=bool(ctx.script_skip_title_optimize),
            job_id=ctx.job["id"],
            stage_name=self.name,
        )
        _apply_video_description(
            script,
            job_id=ctx.job["id"],
            stage_name=self.name,
        )

        script_mgr.attach_prompts(
            script,
            ctx.job,
            title,
            narration_target_words=narration_target_words,
            max_title_length=max_title_length,
            supplementary_info=supplementary_info,
            video_timeline=video_timeline,
            skip_title_optimize=bool(ctx.script_skip_title_optimize),
        )

        if supplementary_info:
            script["supplementary_info"] = supplementary_info
        else:
            script.pop("supplementary_info", None)
        if video_timeline:
            script["video_timeline"] = video_timeline
        else:
            script.pop("video_timeline", None)

        script.pop("pending_narration", None)
        script["word_count"] = _narration_chars(script.get("narration", ""))
        if narration_target_words is not None:
            script["narration_target_words"] = narration_target_words
        assign_segment_timings(
            script,
            video_timeline=script_mgr.parse_timeline(video_timeline) if video_timeline else None,
        )
        script["cost_time"] = round(time.perf_counter() - started, 1)

        job_cancel.raise_if_cancelled(ctx.job["id"])
        with connection() as conn:
            for warning in accept_warnings:
                repo_job_log.append_log(
                    conn,
                    ctx.job["id"],
                    self.name,
                    warning,
                    level="warning",
                )
            repo_job.update_job(
                conn,
                ctx.job["id"],
                title=script["title"],
                script_json=script,
            )
            repo_segment.insert_segments(conn, ctx.job["id"], script["segments"])
            repo_job_log.append_log(
                conn,
                ctx.job["id"],
                self.name,
                (
                    f"material script ready, mode={script.get('script_mode')}, "
                    f"segments={len(script['segments'])}, "
                    f"words={script['word_count']}, "
                    f"cost_time={script['cost_time']}s"
                ),
            )
            if get_settings().skip_script_quality_check:
                merged = merge_quality_report(
                    ctx.job.get("quality_report"),
                    "copy",
                    skip_narration_check(),
                )
                repo_job_log.append_log(
                    conn,
                    ctx.job["id"],
                    self.name,
                    "script quality checks skipped (SKIP_SCRIPT_QUALITY_CHECK)",
                    level="warning",
                )
                repo_job.update_job(conn, ctx.job["id"], quality_report=merged)
            else:
                apply_quality_checks(
                    conn,
                    ctx.job["id"],
                    self.name,
                    {"copy": check_narration(script)},
                    existing_report=ctx.job.get("quality_report"),
                )
