from __future__ import annotations

from pathlib import Path

from PIL import Image

from app.repositories import job_log_repo, job_repo
from app.repositories.connection import connection
from app.services.media.ffmpeg_utils import extract_first_frame
from worker.context import JobContext
from worker.stages.base import StageExecutor


class CoverStage(StageExecutor):
    name = "cover"

    def run(self, ctx: JobContext) -> None:
        cover_path = ctx.rel("cover.jpg")
        intro_png = ctx.rel("intro.png")
        if intro_png.exists():
            Image.open(intro_png).convert("RGB").save(cover_path, quality=92)
            source = f"intro.png: {intro_png}"
        else:
            with connection() as conn:
                job = job_repo.get_job(conn, ctx.job["id"])
            final_path = job.get("final_path")
            if not final_path:
                raise ValueError(
                    "intro.png 不存在且 final_path 缺失，请先跑 intro 或 merge 阶段"
                )
            extract_first_frame(Path(final_path), cover_path)
            source = f"final first frame: {final_path}"

        with connection() as conn:
            job_repo.update_job(conn, ctx.job["id"], cover_path=str(cover_path))
            job_log_repo.append_log(
                conn,
                ctx.job["id"],
                self.name,
                f"cover from {source}",
            )
