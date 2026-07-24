from __future__ import annotations
import time
from pathlib import Path
from app.quality.quality_mgr import apply_quality_checks, check_merged_video
from app.repositories import repo_job_log, repo_job, repo_segment
from app.services.tts.audio_analysis import analyze_loudness
from app.services.media.ffmpeg_utils import ffmpeg_hwaccel_config_summary, probe_duration
from app.services.media.media_mgr import media_mgr
from app.utils.final_asset import build_final_asset
from app.utils.job_info import bgm_params_from_info, resolve_bgm_file, subtitle_params_from_info, xfade_params_from_info
from worker.context import JobContext
from worker.stages.base import StageExecutor
from app.repositories.sql_exec import atomic

class MergeStage(StageExecutor):
    name = 'merge'

    def run(self, ctx: JobContext) -> None:
        started = time.perf_counter()
        with atomic():
            job = repo_job.get_job(ctx.job['id'])
            segments = repo_segment.list_segments(ctx.job['id'])
            repo_job_log.append_log(ctx.job['id'], self.name, f'ffmpeg encode: {ffmpeg_hwaccel_config_summary()}')
        intro_path: Path | None = None
        if job.get('intro_path'):
            intro_path = Path(job['intro_path'])
        else:
            fallback = ctx.rel('intro.mp4')
            if fallback.exists():
                intro_path = fallback
        end_path: Path | None = None
        if job.get('end_path'):
            end_path = Path(job['end_path'])
        bgm = bgm_params_from_info(job.get('info'))
        bgm_path = resolve_bgm_file(bgm['material_id']) if bgm['enabled'] else None
        if bgm['enabled'] and bgm_path is None:
            raise RuntimeError(f"bgm enabled but material {bgm['material_id']} file missing")
        if bgm_path is not None:
            with atomic():
                repo_job_log.append_log(ctx.job['id'], self.name, f"bgm material_id={bgm['material_id']} volume_db={bgm['volume_db']}")
        subtitle = subtitle_params_from_info(job.get('info'))
        xfade = xfade_params_from_info(job.get('info'))
        with atomic():
            repo_job_log.append_log(ctx.job['id'], self.name, f"subtitle burn={('on' if subtitle['enabled'] else 'off')}")
            repo_job_log.append_log(ctx.job['id'], self.name, f"xfade transition={xfade['transition']} duration_sec={xfade['duration_sec']}")
        result = media_mgr.merge_final(media_dir=ctx.media_dir, segments=segments, audio_path=Path(job['audio_path']), subtitle_path=Path(job['subtitle_path']) if job.get('subtitle_path') else None, intro_path=intro_path, end_path=end_path, bgm_path=bgm_path, bgm_volume_db=float(bgm['volume_db']), burn_subtitles=bool(subtitle['enabled']), xfade_duration_sec=float(xfade['duration_sec']), xfade_transition=str(xfade['transition']))
        loudness = analyze_loudness(result.final_path)
        duration = probe_duration(result.final_path)
        cost_time = time.perf_counter() - started
        with atomic():
            updates: dict = {'final_path': build_final_asset(result.final_path, duration=duration, cost_time=cost_time)}
            if intro_path and (not job.get('intro_path')):
                updates['intro_path'] = str(intro_path.resolve())
            repo_job.update_job(ctx.job['id'], **updates)
            repo_job_log.append_log(ctx.job['id'], self.name, f"final at {result.final_path}, lufs={loudness.integrated_lufs}, cost_time={updates['final_path']['cost_time']}s")
            apply_quality_checks(ctx.job['id'], self.name, {'final': check_merged_video(result.final_path, loudness=loudness)}, existing_report=job.get('quality_report'))
