from __future__ import annotations

import shutil
from pathlib import Path

from app.repositories import job_log_repo, job_repo, material_repo
from app.repositories.connection import connection
from app.services.media.ffmpeg_utils import probe_duration, probe_video_size
from worker.context import JobContext
from worker.stages.base import StageExecutor


class MaterialPrepareStage(StageExecutor):
    """从素材库复制基底视频到任务目录。"""

    name = "prepare"

    def run(self, ctx: JobContext) -> None:
        material_id = ctx.job.get("material_id")
        if not material_id:
            raise ValueError("material_id is required for material pipeline")

        with connection() as conn:
            material = material_repo.get_material(conn, int(material_id))

        source = Path(material["file_path"])
        if not source.is_file():
            raise FileNotFoundError(f"material source not found: {source}")

        dest = ctx.rel("base.mp4")
        shutil.copy2(source, dest)

        duration = probe_duration(dest)
        width, height = probe_video_size(dest)
        size_bytes = dest.stat().st_size

        meta_path = ctx.rel("base_meta.json")
        meta_path.write_text(
            (
                f'{{"duration_sec": {duration}, "width": {width}, '
                f'"height": {height}, "size_bytes": {size_bytes}}}'
            ),
            encoding="utf-8",
        )

        with connection() as conn:
            job_repo.update_job(conn, ctx.job["id"], base_path=str(dest.resolve()))
            job_log_repo.append_log(
                conn,
                ctx.job["id"],
                self.name,
                (
                    f"base copied from material #{material_id}, "
                    f"duration={duration:.2f}s, size={width}x{height}"
                ),
            )
