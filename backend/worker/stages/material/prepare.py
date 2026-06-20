from __future__ import annotations

import json
from pathlib import Path

from app.repositories import job_log_repo, job_repo, material_repo
from app.repositories.connection import connection
from app.services.intro.size import design_size_for_source
from app.services.media.ffmpeg_utils import (
    fit_video_to_canvas,
    probe_duration,
    probe_video_size,
)
from app.utils.media import _coerce_positive_int
from worker.context import JobContext
from worker.stages.base import StageExecutor


class MaterialPrepareStage(StageExecutor):
    """从素材库复制基底视频到任务目录，并归一化到设计分辨率（留黑边）。"""

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

        source_w = _coerce_positive_int(material.get("width"))
        source_h = _coerce_positive_int(material.get("height"))
        if not (source_w and source_h):
            source_w, source_h = probe_video_size(source)

        target_w, target_h = design_size_for_source(source_w, source_h, ctx.settings)
        dest = ctx.rel("base.mp4")
        fit_video_to_canvas(source, dest, width=target_w, height=target_h)

        duration = probe_duration(dest)
        width, height = probe_video_size(dest)
        size_bytes = dest.stat().st_size

        meta_path = ctx.rel("base_meta.json")
        meta_path.write_text(
            json.dumps(
                {
                    "duration_sec": duration,
                    "width": width,
                    "height": height,
                    "source_width": source_w,
                    "source_height": source_h,
                    "size_bytes": size_bytes,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        with connection() as conn:
            job_repo.update_job(conn, ctx.job["id"], base_path=f"{ctx.job['id']}/base.mp4")
            job_log_repo.append_log(
                conn,
                ctx.job["id"],
                self.name,
                (
                    f"base fitted from material #{material_id}, "
                    f"source={source_w}x{source_h} -> {width}x{height}, "
                    f"duration={duration:.2f}s"
                ),
            )
