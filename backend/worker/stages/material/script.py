from __future__ import annotations

import re
import time

from app.config import get_settings
from app.quality.checkers import check_copy
from app.quality.gate import apply_quality_checks
from app.repositories import job_log_repo, job_repo, segment_repo
from app.repositories.connection import connection
from app.services.llm.llm_mgr import llm_mgr
from worker.context import JobContext
from worker.stages.base import StageExecutor
from worker.stages.standard.script import (
    ScriptValidationError,
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


def _validate_material_script(
    script: dict,
    *,
    max_title_length: int | None = None,
    min_narration_chars: int | None = None,
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
    return warnings


class MaterialScriptStage(StageExecutor):
    """素材任务口播稿：无分镜出图字段。"""

    name = "script"

    def run(self, ctx: JobContext) -> None:
        started = time.perf_counter()
        title = ctx.job["title"]
        max_title_length = ctx.script_max_title_length
        narration_target_words = ctx.script_narration_target_words
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
            )
        else:
            last_exc: Exception | None = None
            script = None
            feedback: str | None = None
            accept_warnings: list[str] = []
            for attempt in range(6):
                script = llm_mgr.generate_material_script(
                    title,
                    feedback=feedback,
                    max_title_length=max_title_length,
                    narration_target_words=narration_target_words,
                )
                try:
                    accept_warnings = _validate_material_script(
                        script,
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
                raise last_exc or RuntimeError("material script generation failed")
            script["script_mode"] = "ai"

        max_len = (
            max_title_length
            if max_title_length is not None
            else get_settings().max_title_length
        )
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
                    ctx.job["id"],
                    self.name,
                    f"title optimize failed, keep draft: {exc}",
                    level="warning",
                )

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
