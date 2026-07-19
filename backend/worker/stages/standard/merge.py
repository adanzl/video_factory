from __future__ import annotations

import time
from pathlib import Path

from app.quality.quality_mgr import apply_quality_checks, check_merged_video
from app.repositories import repo_job_log, repo_job, repo_segment
from app.repositories.connection import connection
from app.services.tts.audio_analysis import analyze_loudness
from app.services.media.ffmpeg_utils import ffmpeg_hwaccel_config_summary, probe_duration
from app.services.media.media_mgr import media_mgr
from app.utils.final_asset import build_final_asset
from worker.context import JobContext
from worker.stages.base import StageExecutor


class MergeStage(StageExecutor):
    name = "merge"

    def run(self, ctx: JobContext) -> None:
        started = time.perf_counter()
        with connection() as conn:
            job = repo_job.get_job(conn, ctx.job["id"])
            segments = repo_segment.list_segments(conn, ctx.job["id"])
            repo_job_log.append_log(
                conn,
                ctx.job["id"],
                self.name,
                f"ffmpeg encode: {ffmpeg_hwaccel_config_summary()}",
            )

        intro_path: Path | None = None
        if job.get("intro_path"):
            intro_path = Path(job["intro_path"])
        else:
            fallback = ctx.rel("intro.mp4")
            if fallback.exists():
                intro_path = fallback

        end_path: Path | None = None
        if job.get("end_path"):
            end_path = Path(job["end_path"])

        result = media_mgr.merge_final(
            media_dir=ctx.media_dir,
            segments=segments,
            audio_path=Path(job["audio_path"]),
            subtitle_path=Path(job["subtitle_path"]) if job.get("subtitle_path") else None,
            intro_path=intro_path,
            end_path=end_path,
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
                updates["intro_path"] = str(intro_path.resolve())
            repo_job.update_job(conn, ctx.job["id"], **updates)
            repo_job_log.append_log(
                conn,
                ctx.job["id"],
                self.name,
                (
                    f"final at {result.final_path}, "
                    f"lufs={loudness.integrated_lufs}, "
                    f"cost_time={updates['final_path']['cost_time']}s"
                ),
            )
            apply_quality_checks(
                conn,
                ctx.job["id"],
                self.name,
                {
                    "final": check_merged_video(result.final_path, loudness=loudness),
                },
                existing_report=job.get("quality_report"),
            )
