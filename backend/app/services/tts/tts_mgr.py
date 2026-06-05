"""TTS 模块总入口：外部只调用本文件，内部分发至具体客户端。"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from app.config import get_settings
from app.services.visual.text_render import split_sentences

__all__ = [
    "SubtitleCue",
    "TTSClient",
    "TTSResult",
    "load_subtitle_cues",
    "save_subtitle_cues",
    "synthesize",
]


@dataclass
class SubtitleCue:
    segment_index: int
    text: str
    duration_sec: float


@dataclass
class TTSResult:
    audio_path: Path
    subtitle_path: Path
    subtitle_cues_path: Path
    duration_sec: float
    segment_durations: list[float]
    subtitle_cues: list[SubtitleCue]


class TTSClient:
    def synthesize(self, narration: str, segments: list[dict], output_dir: Path) -> TTSResult:
        raise NotImplementedError


def sentences_for_segment(segment: dict) -> list[str]:
    text = (segment.get("text") or "").strip()
    if not text:
        raise ValueError(f"segment {segment.get('segment_index')} has empty text")
    sentences = split_sentences(text)
    return sentences if sentences else [text]


def subtitle_cues_path_for(audio_dir: Path) -> Path:
    return audio_dir / "subtitle_cues.json"


def save_subtitle_cues(path: Path, cues: list[SubtitleCue]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps([asdict(c) for c in cues], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_subtitle_cues(path: Path) -> list[SubtitleCue]:
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [
        SubtitleCue(
            segment_index=int(item["segment_index"]),
            text=str(item["text"]),
            duration_sec=float(item["duration_sec"]),
        )
        for item in raw
    ]


def cues_for_segment(cues: list[SubtitleCue], segment_index: int) -> list[tuple[str, float]]:
    return [(c.text, c.duration_sec) for c in cues if c.segment_index == segment_index]


def _get_client() -> TTSClient:
    from app.services.tts.tts_ali import AliTTSClient
    from app.services.tts.tts_mock import MockTTSClient

    if get_settings().mock_mode:
        return MockTTSClient()
    return AliTTSClient()


def synthesize(narration: str, segments: list[dict], output_dir: Path) -> TTSResult:
    return _get_client().synthesize(narration, segments, output_dir)
