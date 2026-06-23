from __future__ import annotations

import re

from PIL import Image

from app.repositories import job_log_repo, job_repo
from app.repositories.connection import connection
from app.services.intro import generate_intro
from app.services.intro.size import is_material_job, resolve_intro_size
from app.utils.job_info import (
    ORIENTATION_AUTO,
    ORIENTATION_PORTRAIT,
    orientation_for_resolve,
)
from worker.context import JobContext
from worker.stages.base import StageExecutor


def _normalize_title(title: str) -> str:
    return re.sub(r"\s+", "", (title or "").strip())


def _resolve_intro_title(job: dict) -> str:
    """优先 script_json 定稿标题，否则 job.title。"""
    script = job.get("script_json")
    if isinstance(script, dict):
        script_title = _normalize_title(str(script.get("title") or ""))
        if script_title:
            return script_title
    job_title = _normalize_title(str(job.get("title") or ""))
    return job_title or "未命名"


class IntroStage(StageExecutor):
    name = "intro"

    def run(self, ctx: JobContext) -> None:
        with connection() as conn:
            job = job_repo.get_job(conn, ctx.job["id"])

        intro_path = ctx.rel("intro.mp4")
        title = _resolve_intro_title(job)
        effective_orientation = ctx.intro_orientation
        if effective_orientation is None:
            effective_orientation = orientation_for_resolve(job)
        width, height = resolve_intro_size(
            settings=ctx.settings,
            orientation=effective_orientation,
            job=job,
            media_dir=ctx.media_dir,
        )
        if ctx.intro_orientation:
            orient_label = ctx.intro_orientation
        elif effective_orientation:
            orient_label = effective_orientation
        elif is_material_job(job):
            orient_label = ORIENTATION_AUTO
        else:
            orient_label = f"{ORIENTATION_PORTRAIT}(default)"

        generate_intro(
            title,
            intro_path,
            hold_tail_sec=ctx.intro_hold_tail_sec,
            width=width,
            height=height,
        )

        cover_path = ctx.rel("cover.jpg")
        intro_png = ctx.rel("intro.png")
        if not intro_png.exists():
            raise ValueError(f"intro.png 未生成: {intro_png}")
        Image.open(intro_png).convert("RGB").save(cover_path, quality=92)

        with connection() as conn:
            updates: dict = {
                "intro_path": str(intro_path.resolve()),
                "cover_path": str(cover_path.resolve()),
            }
            if _normalize_title(str(job.get("title") or "")) != title:
                updates["title"] = title
            job_repo.update_job(conn, ctx.job["id"], **updates)
            detail = (
                f"intro at {intro_path}, cover at {cover_path}, title={title}, "
                f"size={width}x{height}, orientation={orient_label}"
            )
            if ctx.intro_hold_tail_sec is not None:
                detail += f", hold_tail_sec={ctx.intro_hold_tail_sec:.2f}"
            job_log_repo.append_log(conn, ctx.job["id"], self.name, detail)
