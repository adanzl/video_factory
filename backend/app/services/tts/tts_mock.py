"""本地 Mock TTS 客户端（静音轨 + 估时字幕）。"""

from __future__ import annotations

from pathlib import Path

from app.services.media.ffmpeg_utils import build_srt_from_cues, concat_clips, generate_silent_mp3
from app.services.tts.tts_mgr import (
    SubtitleCue,
    TTSClient,
    TTSResult,
    save_subtitle_cues,
    sentences_for_segment,
    subtitle_cues_path_for,
)


def _estimate_duration(text: str) -> float:
    chars = max(len(text.replace(" ", "")), 1)
    return max(chars / 4.5, 1.0)


class MockTTSClient(TTSClient):
    def synthesize(self, narration: str, segments: list[dict], output_dir: Path) -> TTSResult:
        output_dir.mkdir(parents=True, exist_ok=True)
        clips_dir = output_dir / "clips"
        clips_dir.mkdir(parents=True, exist_ok=True)

        clip_paths: list[Path] = []
        subtitle_cues: list[SubtitleCue] = []
        segment_durations: list[float] = []

        for seg in segments:
            seg_index = seg["segment_index"]
            seg_duration = 0.0
            for sent_index, sentence in enumerate(sentences_for_segment(seg)):
                duration = _estimate_duration(sentence)
                clip_path = clips_dir / f"{seg_index}_{sent_index}.mp3"
                generate_silent_mp3(clip_path, duration)
                clip_paths.append(clip_path)
                subtitle_cues.append(
                    SubtitleCue(
                        segment_index=seg_index,
                        text=sentence,
                        duration_sec=duration,
                    )
                )
                seg_duration += duration
            segment_durations.append(seg_duration)

        audio_path = output_dir / "narration.mp3"
        concat_clips(clip_paths, audio_path)

        cues_path = subtitle_cues_path_for(output_dir)
        save_subtitle_cues(cues_path, subtitle_cues)

        subtitle_path = output_dir / "subtitles.srt"
        subtitle_path.write_text(build_srt_from_cues(subtitle_cues), encoding="utf-8")

        return TTSResult(
            audio_path=audio_path,
            subtitle_path=subtitle_path,
            subtitle_cues_path=cues_path,
            duration_sec=sum(segment_durations),
            segment_durations=segment_durations,
            subtitle_cues=subtitle_cues,
        )
