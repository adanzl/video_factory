from __future__ import annotations

import time
from pathlib import Path

from app.quality.checkers import check_final
from app.quality.gate import apply_quality_checks
from app.repositories import job_log_repo, job_repo
from app.repositories.connection import connection
from app.services.media.audio_analysis import analyze_loudness
from app.services.media.ffmpeg_utils import probe_duration
from app.services.media.media_mgr import media_mgr
from app.utils.final_asset import build_final_asset
from worker.context import JobContext
from worker.stages.base import StageExecutor


class MaterialMergeStage(StageExecutor):
    name = "merge"

    def run(self, ctx: JobContext) -> None:
        started = time.perf_counter()
        with connection() as conn:
            job = job_repo.get_job(conn, ctx.job["id"])

        base_path = ctx.rel("base.mp4")
        if not base_path.exists():
            raise FileNotFoundError(f"base video missing: {base_path}")

        if not job.get("audio_path"):
            raise FileNotFoundError("audio_path missing, run tts first")

        intro_path: Path | None = None
        if job.get("intro_path"):
            intro_path = Path(job["intro_path"])
        else:
            fallback = ctx.rel("intro.mp4")
            if fallback.exists():
                intro_path = fallback

        result = media_mgr.merge_material_final(
            media_dir=ctx.media_dir,
            base_video_path=base_path,
            audio_path=Path(job["audio_path"]),
            intro_path=intro_path,
        )
        loudness = analyze_loudness(result.final_path)
        duration = probe_duration(result.final_path)
        cost_time = time.perf_counter() - started

        with connection() as conn:
            updates: dict = {
                "final_path": build_final_asset(
                    result.final_path,
                    duration=duration,
                    cost_time=cost_time,
                ),
            }
            if intro_path and not job.get("intro_path"):
                updates["intro_path"] = str(intro_path)
            job_repo.update_job(conn, ctx.job["id"], **updates)
            job_log_repo.append_log(
                conn,
                ctx.job["id"],
                self.name,
                (
                    f"material final at {result.final_path}, "
                    f"lufs={loudness.integrated_lufs}, "
                    f"cost_time={updates['final_path']['cost_time']}s"
                ),
            )
            apply_quality_checks(
                conn,
                ctx.job["id"],
                self.name,
                {"final": check_final(result.final_path, loudness=loudness)},
                existing_report=job.get("quality_report"),
            )
