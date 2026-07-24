from __future__ import annotations
import json
from pathlib import Path
from app.config import get_settings
from app.utils.job_info import resolve_image_provider, resolve_video_provider
from app.quality.quality_mgr import apply_quality_checks, check_segment_clips, check_segment_images
from app.repositories import repo_job_log, repo_job, repo_segment
from app.services.segment.segment_mgr import segment_mgr
from worker.context import JobContext
from worker.stages.base import StageExecutor
from app.repositories.sql_exec import atomic

class SegmentStage(StageExecutor):
    name = 'segment'

    def run(self, ctx: JobContext) -> None:
        settings = get_settings()
        with atomic():
            job = repo_job.get_job(ctx.job['id'])
            segments = repo_segment.list_segments(ctx.job['id'])
        image_provider = resolve_image_provider(job)
        video_provider = resolve_video_provider(job)
        audio_path = Path(job['audio_path']) if job.get('audio_path') else None
        produce_scope = ctx.segment_scope or 'all'

        def _merge_info(info_raw: str | None, key: str, value: float) -> str | None:
            info: dict = {}
            if info_raw:
                try:
                    info = json.loads(info_raw)
                except (json.JSONDecodeError, TypeError):
                    info = {}
            info[key] = value
            return json.dumps(info, ensure_ascii=False)

        def persist_segment_image(seg_id: int, path: Path, gen_sec: float=0) -> None:
            with atomic():
                info_raw = repo_segment.get_segment_info(seg_id)
                info = _merge_info(info_raw, 'image_gen_sec', gen_sec)
                repo_segment.update_segment(seg_id, image_path=str(path), status='done', info=info)
                repo_segment.increase_version(seg_id)

        def persist_segment_clip(seg_id: int, path: Path, gen_sec: float=0) -> None:
            with atomic():
                info_raw = repo_segment.get_segment_info(seg_id)
                info = _merge_info(info_raw, 'clip_gen_sec', gen_sec)
                repo_segment.update_segment(seg_id, clip_path=str(path), info=info)
                repo_segment.increase_version(seg_id)
        on_image_done = persist_segment_image if produce_scope in {'all', 'images'} else None
        on_clip_done = persist_segment_clip if produce_scope in {'all', 'clips'} else None
        result = segment_mgr.produce_segments(segments=segments, media_dir=ctx.media_dir, audio_path=audio_path, only_segment_indices=ctx.segment_indices_set(), scope=produce_scope, job=job, on_image_done=on_image_done, on_clip_done=on_clip_done)
        image_by_id = dict(result.image_paths)
        clip_by_id = dict(result.clips.segment_clip_paths)
        segments_for_qc = []
        for seg in segments:
            image_path = image_by_id.get(seg['id']) or seg.get('image_path')
            clip_path = clip_by_id.get(seg['id']) or seg.get('clip_path')
            segments_for_qc.append({**seg, 'image_path': str(image_path) if image_path else None, 'clip_path': str(clip_path) if clip_path else None})
        with atomic():
            log_scope = f'segments={list(ctx.rerun_segment_indices)}' if ctx.rerun_segment_indices else 'all'
            clip_note = f'clips={len(result.clips.segment_clip_paths)} (provider={video_provider})' if result.clips.segment_clip_paths else 'clips=0'
            model = settings.z_image_model if image_provider == 'z_image_t2i' else settings.wan_model if image_provider == 'wan_t2i' else settings.agnes_image_model if image_provider == 'agnes_t2i' else f"sd15/{settings.sd_business or 'auto'}" if image_provider == 'sd15_t2i' else image_provider
            repo_job_log.append_log(ctx.job['id'], self.name, f'scope={log_scope}, images={len(result.image_paths)} (provider={image_provider}, model={model}), {clip_note}')
            qc_checks: dict = {}
            rerun_indices = ctx.segment_indices_set()
            if produce_scope in {'all', 'images'}:
                visual_qc = segments_for_qc
                if rerun_indices is not None and produce_scope == 'images':
                    visual_qc = [seg for seg in segments_for_qc if seg['segment_index'] in rerun_indices]
                qc_checks['visual'] = check_segment_images(visual_qc)
            if produce_scope in {'all', 'clips'} and (produce_scope == 'clips' or audio_path is not None):
                clip_qc = segments_for_qc
                if rerun_indices is not None:
                    clip_qc = [seg for seg in segments_for_qc if seg['segment_index'] in rerun_indices]
                qc_checks['clip'] = check_segment_clips(clip_qc)
            apply_quality_checks(ctx.job['id'], self.name, qc_checks, existing_report=job.get('quality_report'))
