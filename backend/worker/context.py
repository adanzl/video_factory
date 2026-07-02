from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.config import Settings, get_settings


@dataclass
class JobContext:
    job: dict
    settings: Settings
    media_dir: Path
    rerun_segment_indices: tuple[int, ...] | None = None
    segment_scope: str | None = None
    intro_hold_tail_sec: float | None = None
    intro_orientation: str | None = None
    tts_speech_rate: float | None = None
    tts_voice_id: str | None = None
    script_segment_target_sec: float | None = None
    script_max_title_length: int | None = None
    script_narration_target_words: int | None = None
    script_speech_chars_per_sec: float | None = None
    script_skip_title_optimize: bool = False
    script_generate_image_prompts: bool = False
    script_supplementary_info: str | None = None
    script_video_timeline: str | None = None
    material_narration: str | None = None

    @classmethod
    def from_job(
        cls,
        job: dict,
        *,
        rerun_segment_indices: tuple[int, ...] | None = None,
        segment_scope: str | None = None,
        intro_hold_tail_sec: float | None = None,
        intro_orientation: str | None = None,
        tts_speech_rate: float | None = None,
        tts_voice_id: str | None = None,
        script_segment_target_sec: float | None = None,
        script_max_title_length: int | None = None,
        script_narration_target_words: int | None = None,
        script_speech_chars_per_sec: float | None = None,
        script_skip_title_optimize: bool = False,
        script_generate_image_prompts: bool = False,
        script_supplementary_info: str | None = None,
        script_video_timeline: str | None = None,
        material_narration: str | None = None,
    ) -> "JobContext":
        from app.utils.job_info import (
            content_style_from_job,
            resolve_narration_target_words,
            resolve_speech_chars_per_sec,
            script_params_from_info,
        )

        settings = get_settings()
        media_dir = settings.video_data_dir / str(job["id"])
        media_dir.mkdir(parents=True, exist_ok=True)
        saved_script = script_params_from_info(job.get("info"))
        if not script_supplementary_info or not str(script_supplementary_info).strip():
            saved_extra = saved_script.get("supplementary_info")
            if saved_extra and str(saved_extra).strip():
                script_supplementary_info = str(saved_extra).strip()

        def _saved_float(key: str) -> float | None:
            raw = saved_script.get(key)
            if isinstance(raw, bool) or raw is None:
                return None
            if isinstance(raw, (int, float)):
                value = float(raw)
                return value if value > 0 else None
            return None

        def _saved_int(key: str) -> int | None:
            raw = saved_script.get(key)
            if isinstance(raw, bool) or raw is None:
                return None
            if isinstance(raw, int):
                return raw if raw > 0 else None
            if isinstance(raw, float) and raw.is_integer():
                parsed = int(raw)
                return parsed if parsed > 0 else None
            return None

        resolved_segment_target_sec = (
            script_segment_target_sec
            if script_segment_target_sec is not None
            else _saved_float("segment_target_sec")
        )
        resolved_max_title_length = (
            script_max_title_length
            if script_max_title_length is not None
            else _saved_int("max_title_length")
        )
        resolved_narration_target_words = (
            script_narration_target_words
            if script_narration_target_words is not None
            else resolve_narration_target_words(
                saved_script,
                content_style=content_style_from_job(job),
            )
        )
        resolved_speech_chars_per_sec = (
            script_speech_chars_per_sec
            if script_speech_chars_per_sec is not None
            else resolve_speech_chars_per_sec(saved_script)
        )
        if script_skip_title_optimize is False:
            saved_skip = saved_script.get("skip_title_optimize")
            if isinstance(saved_skip, bool):
                script_skip_title_optimize = saved_skip
        if script_generate_image_prompts is False:
            saved_generate = saved_script.get("generate_image_prompts")
            if isinstance(saved_generate, bool):
                script_generate_image_prompts = saved_generate
        if not script_video_timeline or not str(script_video_timeline).strip():
            saved_timeline = saved_script.get("video_timeline")
            if saved_timeline and str(saved_timeline).strip():
                script_video_timeline = str(saved_timeline).strip()

        return cls(
            job=job,
            settings=settings,
            media_dir=media_dir,
            rerun_segment_indices=rerun_segment_indices,
            segment_scope=segment_scope,
            intro_hold_tail_sec=intro_hold_tail_sec,
            intro_orientation=intro_orientation,
            tts_speech_rate=tts_speech_rate,
            tts_voice_id=tts_voice_id,
            script_segment_target_sec=resolved_segment_target_sec,
            script_max_title_length=resolved_max_title_length,
            script_narration_target_words=resolved_narration_target_words,
            script_speech_chars_per_sec=resolved_speech_chars_per_sec,
            script_skip_title_optimize=script_skip_title_optimize,
            script_generate_image_prompts=script_generate_image_prompts,
            script_supplementary_info=script_supplementary_info,
            script_video_timeline=script_video_timeline,
            material_narration=material_narration,
        )

    def rel(self, name: str) -> Path:
        return self.media_dir / name

    def segment_indices_set(self) -> set[int] | None:
        if not self.rerun_segment_indices:
            return None
        return set(self.rerun_segment_indices)
