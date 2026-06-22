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
        script_skip_title_optimize: bool = False,
        script_generate_image_prompts: bool = False,
        script_supplementary_info: str | None = None,
        script_video_timeline: str | None = None,
        material_narration: str | None = None,
    ) -> "JobContext":
        settings = get_settings()
        media_dir = settings.video_data_dir / str(job["id"])
        media_dir.mkdir(parents=True, exist_ok=True)
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
            script_segment_target_sec=script_segment_target_sec,
            script_max_title_length=script_max_title_length,
            script_narration_target_words=script_narration_target_words,
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
