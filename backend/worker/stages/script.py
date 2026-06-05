from __future__ import annotations

import re

from app.config import get_settings
from app.repositories import job_log_repo, job_repo, segment_repo
from app.repositories.connection import connection
from app.services.llm.llm_mgr import generate_script
from worker.context import JobContext
from worker.stages.base import StageExecutor


def _narration_chars(narration: str) -> int:
    return len(re.sub(r"\s+", "", narration))


def _title_chars(title: str) -> str:
    return re.sub(r"\s+", "", title.strip())


def _validate_script(script: dict) -> None:
    settings = get_settings()
    narration = script.get("narration", "")
    segments = script.get("segments") or []
    chars = _narration_chars(narration)
    if chars < 700:
        raise ValueError(f"narration too short: {chars} chars (need >= 700)")
    if settings.segment_target_sec > 0 and len(segments) < 10:
        raise ValueError(
            f"too few segments: {len(segments)} (need >= 10 for "
            f"{settings.segment_target_sec}s/segment mode)"
        )
    title = _title_chars(script.get("title") or "")
    if not title:
        raise ValueError("title is empty")
    max_len = settings.max_title_length
    if len(title) > max_len:
        raise ValueError(f"title too long: {len(title)} chars (need <= {max_len})")
    script["title"] = title


class ScriptStage(StageExecutor):
    name = "script"

    def run(self, ctx: JobContext) -> None:
        title = ctx.job["title"]
        last_exc: Exception | None = None
        script: dict | None = None
        feedback: str | None = None
        for attempt in range(6):
            script = generate_script(title, feedback=feedback)
            try:
                _validate_script(script)
                break
            except ValueError as exc:
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
