from __future__ import annotations
import logging
from app.config import get_settings
from app.quality.quality_mgr import apply_quality_checks, check_tts_audio
from app.repositories import repo_job_log, repo_job, repo_segment
from app.services.tts.audio_analysis import analyze_loudness, analyze_silence, normalize_loudness
from app.services.tts.tts_mgr import tts_mgr
from app.services.tts.audio_timeline import (
    probe_segment_clip_durations,
    resolve_segment_timeline_durations,
    save_audio_timeline_manifest,
)
from app.utils.media import base_video_duration_sec, material_min_audio_duration_sec
from worker.context import JobContext
from worker.stages.base import StageExecutor
from app.repositories.sql_exec import atomic

logger = logging.getLogger(__name__)

class TTSStage(StageExecutor):
    name = 'tts'

    def run(self, ctx: JobContext) -> None:
        settings = get_settings()
        with atomic():
            job = repo_job.get_job(ctx.job['id'])
            segments = repo_segment.list_segments(ctx.job['id'])
        script = job.get('script_json') or {}
        result = tts_mgr.synthesize(script.get('narration', ''), segments, ctx.media_dir / 'audio', voice=ctx.tts_voice_id, speech_rate=ctx.tts_speech_rate)
        normalize_loudness(result.audio_path, target_lufs=settings.audio_target_lufs, true_peak=settings.audio_true_peak)
        loudness = analyze_loudness(result.audio_path)
        silence = analyze_silence(result.audio_path, noise_db=settings.audio_silence_noise_db)
        audio_dir = ctx.media_dir / 'audio'
        probed_clips = probe_segment_clip_durations(audio_dir, segments)
        timeline_durations = resolve_segment_timeline_durations(
            audio_dir=audio_dir,
            narration_path=result.audio_path,
            segments=segments,
        )
        save_audio_timeline_manifest(
            audio_dir,
            segments,
            timeline_durations,
            result.audio_path,
            clip_probe_durations=probed_clips,
        )
        reported = list(result.segment_durations)
        if len(reported) == len(timeline_durations):
            drift = sum(reported) - sum(timeline_durations)
            if abs(drift) > 0.05:
                logger.info(
                    'tts timeline: synth reported %.3fs, clips+narration aligned %.3fs (drift %.3fs)',
                    sum(reported),
                    sum(timeline_durations),
                    drift,
                )
        min_audio_dur: float | None = None
        if (job.get('pipeline') or 'standard').strip() == 'material':
            base_dur = base_video_duration_sec(job=job, media_dir=ctx.media_dir)
            min_audio_dur = material_min_audio_duration_sec(base_dur)
        with atomic():
            for seg, duration in zip(segments, timeline_durations, strict=True):
                repo_segment.update_segment(seg['id'], duration_sec=duration)
                seg['duration_sec'] = duration
            audio_version = (job.get('audio_version') or 0) + 1
            repo_job.update_job(ctx.job['id'], audio_path=str(result.audio_path.resolve()), subtitle_path=str(result.subtitle_path.resolve()), tts_usage_json=result.usage_summary(), audio_version=audio_version)
            clip_sum = sum(probed_clips)
            narr_dur = sum(timeline_durations)
            repo_job_log.append_log(
                ctx.job['id'],
                self.name,
                f'audio {narr_dur:.1f}s, clips_sum={clip_sum:.1f}s, segments={len(timeline_durations)}, '
                f'cues={len(result.subtitle_cues)}, billing_chars={result.total_characters}, '
                f'lufs={loudness.integrated_lufs}, max_silence={silence.max_gap_sec:.2f}s',
            )
            apply_quality_checks(ctx.job['id'], self.name, {'tts': check_tts_audio(result.audio_path, narr_dur, subtitle_cues=result.subtitle_cues, segments=segments, loudness=loudness, silence=silence, min_duration_sec=min_audio_dur)}, existing_report=job.get('quality_report'))
