from __future__ import annotations
import time
from pathlib import Path
from app.quality.quality_mgr import apply_quality_checks, check_merged_video
from app.repositories import repo_job_log, repo_job
from app.services.tts.audio_analysis import analyze_loudness
from app.services.media.ffmpeg_utils import ffmpeg_hwaccel_config_summary, probe_duration
from app.services.media.media_mgr import media_mgr
from app.utils.final_asset import build_final_asset
from app.utils.job_info import subtitle_params_from_info
from app.utils.media import material_final_min_duration_sec
from worker.context import JobContext
from worker.stages.base import StageExecutor
from app.repositories.sql_exec import atomic

def _resolve_base_video(job: dict, ctx: JobContext) -> Path:
    raw = job.get('base_path')
    if raw:
        path = Path(str(raw))
        if path.is_file():
            return path
    return ctx.rel('base.mp4')

class MaterialMergeStage(StageExecutor):
    name = 'merge'

    def run(self, ctx: JobContext) -> None:
        started = time.perf_counter()
        with atomic():
            job = repo_job.get_job(ctx.job['id'])
            repo_job_log.append_log(ctx.job['id'], self.name, f'ffmpeg encode: {ffmpeg_hwaccel_config_summary()}')
        base_path = _resolve_base_video(job, ctx)
        if not base_path.is_file():
            raise FileNotFoundError(f'base video missing: {base_path}')
        if not job.get('audio_path'):
            raise FileNotFoundError('audio_path missing, run tts first')
        intro_path: Path | None = None
        if job.get('intro_path'):
            intro_path = Path(job['intro_path'])
        else:
            fallback = ctx.rel('intro.mp4')
            if fallback.exists():
                intro_path = fallback
        subtitle = subtitle_params_from_info(job.get('info'))
        with atomic():
            repo_job_log.append_log(ctx.job['id'], self.name, f"subtitle burn={('on' if subtitle['enabled'] else 'off')}")
        result = media_mgr.merge_material_final(media_dir=ctx.media_dir, base_video_path=base_path, audio_path=Path(job['audio_path']), intro_path=intro_path, burn_subtitles=bool(subtitle['enabled']))
        loudness = analyze_loudness(result.final_path)
        duration = probe_duration(result.final_path)
        cost_time = time.perf_counter() - started
        base_dur = probe_duration(base_path)
        intro_dur = probe_duration(intro_path) if intro_path and intro_path.is_file() else 0.0
        final_min_dur = material_final_min_duration_sec(base_dur, intro_duration_sec=intro_dur)
        with atomic():
            updates: dict = {'final_path': build_final_asset(result.final_path, duration=duration, cost_time=cost_time)}
            if intro_path and (not job.get('intro_path')):
                updates['intro_path'] = str(intro_path.resolve())
            repo_job.update_job(ctx.job['id'], **updates)
            repo_job_log.append_log(ctx.job['id'], self.name, f"material final at {result.final_path}, lufs={loudness.integrated_lufs}, cost_time={updates['final_path']['cost_time']}s, subtitles={('burned' if subtitle['enabled'] else 'off')}")
            apply_quality_checks(ctx.job['id'], self.name, {'final': check_merged_video(result.final_path, loudness=loudness, min_duration_sec=final_min_dur)}, existing_report=job.get('quality_report'))
