from __future__ import annotations

import re

from app.config import get_settings
from app.quality.checkers import check_copy, check_storyboard
from app.quality.gate import apply_quality_checks
from app.repositories import job_log_repo, job_repo, segment_repo
from app.repositories.connection import connection
from app.services.llm.llm_mgr import generate_script
from worker.context import JobContext
from worker.stages.base import StageExecutor

MIN_NARRATION_CHARS = 700
# 低于此比例视为「主题撑不满」，不再重试，直接沿用当前文案继续。
NARRATION_RETRY_MIN_CHARS = int(MIN_NARRATION_CHARS * 0.8)
MIN_ACCEPT_NARRATION_CHARS = 200
MIN_IMAGE_PROMPT_CHARS = 200


class ScriptValidationError(ValueError):
    def __init__(self, message: str, *, retryable: bool = True) -> None:
        super().__init__(message)
        self.retryable = retryable


def _narration_chars(narration: str) -> int:
    return len(re.sub(r"\s+", "", narration))


def _title_chars(title: str) -> str:
    return re.sub(r"\s+", "", title.strip())


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


def _validate_script(script: dict) -> list[str]:
    settings = get_settings()
    narration = script.get("narration", "")
    segments = script.get("segments") or []
    warnings: list[str] = []
    chars = _narration_chars(narration)
    if chars < MIN_NARRATION_CHARS:
        if _narration_short_retryable(chars):
            raise ScriptValidationError(
                f"narration too short: {chars} chars (need >= {MIN_NARRATION_CHARS})",
                retryable=True,
            )
        if chars < MIN_ACCEPT_NARRATION_CHARS:
            raise ScriptValidationError(
                f"narration too short: {chars} chars (need >= {MIN_ACCEPT_NARRATION_CHARS})",
                retryable=False,
            )
        warnings.append(
            f"cannot reach {MIN_NARRATION_CHARS} chars ({chars} got), continuing with shorter copy"
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
    if settings.segment_target_sec > 0:
        cap = max(20, int(settings.segment_target_sec * 7.5))
        hard_cap = int(cap * 1.15)
        overflow: list[tuple[int, int]] = []
        for seg in segments:
            seg_chars = _narration_chars(seg.get("text") or "")
            if seg_chars > hard_cap:
                overflow.append((seg.get("segment_index", -1), seg_chars))
        if overflow:
            raise ScriptValidationError(
                f"segment text exceeds {settings.segment_target_sec}s cap (~{cap} chars): "
                f"{overflow}",
                retryable=True,
            )
        needed = max(1, (chars + cap - 1) // cap)
        if len(segments) < needed:
            raise ScriptValidationError(
                f"too few segments: {len(segments)} (need >= {needed} for "
                f"{settings.segment_target_sec}s/segment cap, {chars} chars narration)",
                retryable=True,
            )
    title = _title_chars(script.get("title") or "")
    if not title:
        raise ScriptValidationError("title is empty")
    max_len = settings.max_title_length
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
        title = ctx.job["title"]
        last_exc: Exception | None = None
        script: dict | None = None
        feedback: str | None = None
        accept_warnings: list[str] = []
        for attempt in range(6):
            script = generate_script(title, feedback=feedback)
            try:
                accept_warnings = _validate_script(script)
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

        script["word_count"] = _narration_chars(script.get("narration", ""))
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
                f"words={script['word_count']}",
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
