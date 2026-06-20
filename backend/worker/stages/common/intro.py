from __future__ import annotations

from app.repositories import job_log_repo, job_repo
from app.repositories.connection import connection
from app.services.intro import generate_intro
from app.utils.media import base_video_size
from worker.context import JobContext
from worker.stages.base import StageExecutor

_PIPELINE_MATERIAL = "material"


def _is_material_job(job: dict) -> bool:
    return (job.get("pipeline") or "standard").strip() == _PIPELINE_MATERIAL
from app.repositories.connection import connection
from app.services.intro import generate_intro
from app.utils.media import base_video_size
from worker.context import JobContext
from worker.stages.base import StageExecutor


class IntroStage(StageExecutor):
    name = "intro"

    def run(self, ctx: JobContext) -> None:
        intro_path = ctx.rel("intro.mp4")
        width: int | None = None
        height: int | None = None
        if _is_material_job(ctx.job):
            size = base_video_size(job=ctx.job, media_dir=ctx.media_dir)
            if size:
                width, height = size

        generate_intro(
            ctx.job["title"],
            intro_path,
            hold_tail_sec=ctx.intro_hold_tail_sec,
            width=width,
            height=height,
        )
        with connection() as conn:
            job_repo.update_job(conn, ctx.job["id"], intro_path=str(intro_path))
            tail = ctx.intro_hold_tail_sec
            detail = f"intro at {intro_path}"
            if width and height:
                detail += f", size={width}x{height}"
            if tail is not None:
                detail += f", hold_tail_sec={tail:.2f}"
            job_log_repo.append_log(conn, ctx.job["id"], self.name, detail)
