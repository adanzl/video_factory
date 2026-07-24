from __future__ import annotations
import json
from pathlib import Path
from app.repositories import repo_job_log, repo_job, repo_material_video
from app.services.intro.size import design_size_for_source
from app.services.media.ffmpeg_utils import fit_video_to_canvas, probe_duration, probe_video_size
from app.utils.media import _coerce_positive_int
from worker.context import JobContext
from worker.stages.base import StageExecutor
from app.repositories.sql_exec import atomic

class MaterialPrepareStage(StageExecutor):
    """从素材库复制基底视频到任务目录，并归一化到设计分辨率（留黑边）。"""
    name = 'prepare'

    def run(self, ctx: JobContext) -> None:
        material_id = ctx.job.get('material_id')
        if not material_id:
            raise ValueError('material_id is required for material pipeline')
        with atomic():
            material = repo_material_video.get_material_video(int(material_id))
        source = Path(material['file_path'])
        if not source.is_file():
            raise FileNotFoundError(f'material source not found: {source}')
        source_w = _coerce_positive_int(material.get('width'))
        source_h = _coerce_positive_int(material.get('height'))
        if not (source_w and source_h):
            source_w, source_h = probe_video_size(source)
        target_w, target_h = design_size_for_source(source_w, source_h, ctx.settings)
        dest = ctx.rel('base.mp4')
        fit_video_to_canvas(source, dest, width=target_w, height=target_h)
        duration = probe_duration(dest)
        width, height = probe_video_size(dest)
        size_bytes = dest.stat().st_size
        meta_path = ctx.rel('base_meta.json')
        meta_path.write_text(json.dumps({'duration_sec': duration, 'width': width, 'height': height, 'source_width': source_w, 'source_height': source_h, 'size_bytes': size_bytes}, ensure_ascii=False), encoding='utf-8')
        with atomic():
            repo_job.update_job(ctx.job['id'], base_path=str(dest.resolve()))
            repo_job_log.append_log(ctx.job['id'], self.name, f'base fitted from material #{material_id}, source={source_w}x{source_h} -> {width}x{height}, duration={duration:.2f}s')
