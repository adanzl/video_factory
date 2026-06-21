from __future__ import annotations

import re
import time

from app.config import get_settings
from app.quality.checkers import check_copy, check_storyboard
from app.quality.gate import apply_quality_checks
from app.repositories import job_log_repo, job_repo, segment_repo
from app.repositories.connection import connection
from app.services.llm.llm_mgr import llm_mgr
from app.services.llm.llm_script_prompts import MIN_IMAGE_PROMPT_CHARS
from worker.context import JobContext
from worker.stages.base import StageExecutor

MIN_NARRATION_CHARS = 700
# 低于此比例视为「主题撑不满」，不再重试，直接沿用当前文案继续。
NARRATION_RETRY_MIN_CHARS = int(MIN_NARRATION_CHARS * 0.8)
MIN_ACCEPT_NARRATION_CHARS = 200


def _min_narration_chars(narration_target_words: int | None) -> int:
    if narration_target_words is None:
        return MIN_NARRATION_CHARS
    target = max(MIN_ACCEPT_NARRATION_CHARS, narration_target_words)
    return max(MIN_ACCEPT_NARRATION_CHARS, int(target * 0.67))


class ScriptValidationError(ValueError):
    def __init__(self, message: str, *, retryable: bool = True) -> None:
        super().__init__(message)
        self.retryable = retryable


def _narration_chars(narration: str) -> int:
    return len(re.sub(r"\s+", "", narration))


def _title_chars(title: str) -> str:
    return re.sub(r"\s+", "", title.strip())


def _resolve_script_title(*, source_title: str, llm_title: str, max_len: int) -> str:
    """原标题未超长则沿用；否则采用 LLM 精简结果。"""
    source = _title_chars(source_title)
    if len(source) <= max_len:
        return source
    candidate = _title_chars(llm_title)
    if not candidate:
        raise ScriptValidationError(
            f"title too long: {len(source)} chars (need <= {max_len})",
            retryable=True,
        )
    if len(candidate) > max_len:
        raise ScriptValidationError(
            f"title too long: {len(candidate)} chars (need <= {max_len})",
            retryable=True,
        )
    return candidate


def _apply_script_title(
    script: dict,
    *,
    source_title: str,
    max_len: int,
    skip_optimize: bool,
    job_id: int,
    stage_name: str,
) -> None:
    script["title"] = _resolve_script_title(
        source_title=source_title,
        llm_title=str(script.get("title") or ""),
        max_len=max_len,
    )
    if skip_optimize:
        return
    try:
        optimized_title = llm_mgr.optimize_script_title(
            script["title"],
            script.get("narration", ""),
            max_title_length=max_len,
        )
        script["draft_title"] = script["title"]
        script["title"] = _title_chars(optimized_title)
        if len(script["title"]) > max_len:
            raise ScriptValidationError(
                f"optimized title too long: {len(script['title'])} chars (need <= {max_len})"
            )
    except Exception as exc:
        with connection() as conn:
            job_log_repo.append_log(
                conn,
                job_id,
                stage_name,
                f"title optimize failed, keep draft: {exc}",
                level="warning",
            )


def _narration_short_retryable(chars: int) -> bool:
    return chars >= NARRATION_RETRY_MIN_CHARS


def _normalize_segments(segments: list[dict]) -> list[dict]:
    out: list[dict] = []
    for i, seg in enumerate(segments, start=1):
        row = dict(seg)
        if "segment_index" not in row:
            row["segment_index"] = row.get("index", i)
        out.append(row)
    return out


def _validate_script(
    script: dict,
    *,
    segment_target_sec: float | None = None,
    max_title_length: int | None = None,
    min_narration_chars: int | None = None,
) -> list[str]:
    settings = get_settings()
    seg_target = (
        settings.segment_target_sec if segment_target_sec is None else segment_target_sec
    )
    max_len = settings.max_title_length if max_title_length is None else max_title_length
    required_narration_chars = (
        MIN_NARRATION_CHARS if min_narration_chars is None else min_narration_chars
    )
    narration = script.get("narration", "")
    segments = script.get("segments") or []
    warnings: list[str] = []
    chars = _narration_chars(narration)
    if chars < required_narration_chars:
        retry_min = max(MIN_ACCEPT_NARRATION_CHARS, int(required_narration_chars * 0.8))
        if chars >= retry_min:
            raise ScriptValidationError(
                f"narration too short: {chars} chars (need >= {required_narration_chars})",
                retryable=True,
            )
        if chars < MIN_ACCEPT_NARRATION_CHARS:
            raise ScriptValidationError(
                f"narration too short: {chars} chars (need >= {MIN_ACCEPT_NARRATION_CHARS})",
                retryable=False,
            )
        warnings.append(
            f"cannot reach {required_narration_chars} chars ({chars} got), continuing with shorter copy"
        )
    if not segments:
        raise ScriptValidationError("no segments", retryable=False)
    if not (script.get("visual_style") or "").strip():
        raise ScriptValidationError("visual_style is empty", retryable=True)
    for seg in segments:
        if not (seg.get("visual_brief") or "").strip():
            raise ScriptValidationError(
                f"segment {seg.get('segment_index')} missing visual_brief",
                retryable=True,
            )
        prompt = seg.get("image_prompt") or ""
        if len(prompt) < MIN_IMAGE_PROMPT_CHARS:
            raise ScriptValidationError(
                f"segment {seg.get('segment_index')} image_prompt too short: "
                f"{len(prompt)} chars (need >= {MIN_IMAGE_PROMPT_CHARS})",
                retryable=True,
            )
    if seg_target > 0:
        cap = max(20, int(seg_target * 7.5))
        hard_cap = int(cap * 1.15)
        overflow: list[tuple[int, int]] = []
        for seg in segments:
            seg_chars = _narration_chars(seg.get("text") or "")
            if seg_chars > hard_cap:
                overflow.append((seg.get("segment_index", -1), seg_chars))
        if overflow:
            raise ScriptValidationError(
                f"segment text exceeds {seg_target}s cap (~{cap} chars): "
                f"{overflow}",
                retryable=True,
            )
        needed = max(1, (chars + cap - 1) // cap)
        if len(segments) < needed:
            raise ScriptValidationError(
                f"too few segments: {len(segments)} (need >= {needed} for "
                f"{seg_target}s/segment cap, {chars} chars narration)",
                retryable=True,
            )
    title = _title_chars(script.get("title") or "")
    if not title:
        raise ScriptValidationError("title is empty")
    if len(title) > max_len:
        raise ScriptValidationError(
            f"title too long: {len(title)} chars (need <= {max_len})"
        )
    script["title"] = title
    script["segments"] = _normalize_segments(segments)
    return warnings


class ScriptStage(StageExecutor):
    name = "script"

    def run(self, ctx: JobContext) -> None:
        started = time.perf_counter()
        title = ctx.job["title"]
        segment_target_sec = ctx.script_segment_target_sec
        max_title_length = ctx.script_max_title_length
        narration_target_words = ctx.script_narration_target_words
        min_narration_chars = _min_narration_chars(narration_target_words)
        last_exc: Exception | None = None
        script: dict | None = None
        feedback: str | None = None
        accept_warnings: list[str] = []
        for attempt in range(6):
            script = llm_mgr.generate_script(
                title,
                feedback=feedback,
                segment_target_sec=segment_target_sec,
                max_title_length=max_title_length,
                narration_target_words=narration_target_words,
            )
            try:
                accept_warnings = _validate_script(
                    script,
                    segment_target_sec=segment_target_sec,
                    max_title_length=max_title_length,
                    min_narration_chars=min_narration_chars,
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
                        f"script rejected (attempt {attempt + 1}): {exc}",
                        level="warning",
                    )
                script = None
        if script is None:
            raise last_exc or RuntimeError("script generation failed")

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

        from app.services.llm.llm_script_prompts import attach_llm_prompts_to_script

        attach_llm_prompts_to_script(
            script,
            ctx.job,
            title,
            segment_target_sec=segment_target_sec,
            max_title_length=max_title_length,
            narration_target_words=narration_target_words,
            skip_title_optimize=bool(ctx.script_skip_title_optimize),
        )

        script["word_count"] = _narration_chars(script.get("narration", ""))
        script["cost_time"] = round(time.perf_counter() - started, 1)
        display_title = script["title"]
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
                title=display_title,
                script_json=script,
            )
            segment_repo.insert_segments(conn, ctx.job["id"], script["segments"])
            job_log_repo.append_log(
                conn,
                ctx.job["id"],
                self.name,
                f"script ready, segments={len(script['segments'])}, "
                f"words={script['word_count']}, "
                f"title={script['title']}, "
                f"cost_time={script['cost_time']}s",
            )
            apply_quality_checks(
                conn,
                ctx.job["id"],
                self.name,
                {
                    "copy": check_copy(script),
                    "storyboard": check_storyboard(script),
                },
                existing_report=ctx.job.get("quality_report"),
            )
