from __future__ import annotations

from app.repositories import job_log_repo, job_repo
from app.repositories.connection import connection
from app.services.intro import generate_intro
from app.services.intro.size import is_material_job, resolve_intro_size
from worker.context import JobContext
from worker.stages.base import StageExecutor


class IntroStage(StageExecutor):
    name = "intro"

    def run(self, ctx: JobContext) -> None:
        intro_path = ctx.rel("intro.mp4")
        width, height = resolve_intro_size(
            settings=ctx.settings,
            orientation=ctx.intro_orientation,
            job=ctx.job,
            media_dir=ctx.media_dir,
        )
        orient_label = ctx.intro_orientation or ("auto" if is_material_job(ctx.job) else "portrait(default)")

        generate_intro(
            ctx.job["title"],
            intro_path,
            hold_tail_sec=ctx.intro_hold_tail_sec,
            width=width,
            height=height,
        )
        with connection() as conn:
            job_repo.update_job(conn, ctx.job["id"], intro_path=str(intro_path.resolve()))
            detail = f"intro at {intro_path}, size={width}x{height}, orientation={orient_label}"
            if ctx.intro_hold_tail_sec is not None:
                detail += f", hold_tail_sec={ctx.intro_hold_tail_sec:.2f}"
            job_log_repo.append_log(conn, ctx.job["id"], self.name, detail)
