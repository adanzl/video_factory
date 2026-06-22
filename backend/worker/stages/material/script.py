from __future__ import annotations

import re
import time

from app.config import get_settings
from app.quality.checkers import check_copy
from app.quality.gate import apply_quality_checks
from app.repositories import job_log_repo, job_repo, segment_repo
from app.repositories.connection import connection
from app.services.llm.llm_mgr import llm_mgr
from app.services.llm.llm_script_timeline import parse_video_timeline, validate_timeline_script
from app.utils.media import base_video_duration_sec, estimate_narration_target_words
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

MIN_ACCEPT_NARRATION_CHARS = 200


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
    if chars < MIN_ACCEPT_NARRATION_CHARS:
        raise ScriptValidationError(
            f"narration too short: {chars} chars (need >= {MIN_ACCEPT_NARRATION_CHARS})",
            retryable=False,
        )
    if chars < required_narration_chars:
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

    timeline = parse_video_timeline(video_timeline_raw)
    if timeline:
        timeline_error, timeline_warnings = validate_timeline_script(
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
                    job_log_repo.append_log(
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

        if manual_narration and str(manual_narration).strip():
            narration = str(manual_narration).strip()
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
        else:
            last_exc: Exception | None = None
            script = None
            last_script: dict | None = None
            feedback: str | None = None
            accept_warnings: list[str] = []
            for attempt in range(6):
                length_mode = _timeline_length_mode(attempt)
                script = llm_mgr.generate_material_script(
                    title,
                    feedback=feedback,
                    max_title_length=max_title_length,
                    narration_target_words=narration_target_words,
                    supplementary_info=supplementary_info,
                    video_timeline=video_timeline,
                )
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
                        job_log_repo.append_log(
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
                        job_log_repo.append_log(
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

        from app.services.llm.llm_script_prompts import attach_llm_prompts_to_script

        attach_llm_prompts_to_script(
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
        script["cost_time"] = round(time.perf_counter() - started, 1)

        with connection() as conn:
            for warning in accept_warnings:
                job_log_repo.append_log(
                    conn,
                    ctx.job["id"],
                    self.name,
                    warning,
                    level="warning",
                )
            job_repo.update_job(
                conn,
                ctx.job["id"],
                title=script["title"],
                script_json=script,
            )
            segment_repo.insert_segments(conn, ctx.job["id"], script["segments"])
            job_log_repo.append_log(
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
            apply_quality_checks(
                conn,
                ctx.job["id"],
                self.name,
                {"copy": check_copy(script)},
                existing_report=ctx.job.get("quality_report"),
            )
