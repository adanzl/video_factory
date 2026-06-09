"""TTS 模块总入口：外部只调用本文件，内部分发至具体客户端。"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from app.config import get_settings
from app.services.visual.text_render import split_phrase_chunks

__all__ = [
    "SubtitleCue",
    "TTSClient",
    "TTSResult",
    "load_subtitle_cues",
    "save_subtitle_cues",
    "synthesize",
    "synthesize_utterance",
]


@dataclass
class SubtitleCue:
    segment_index: int
    text: str
    duration_sec: float


@dataclass
class TTSUsageTask:
    """单次 WebSocket 合成的计费 usage（取该 task 最后一次 payload.usage）。"""

    usage: dict
    segment_index: int | None = None
    kind: str = "segment"


@dataclass
class TTSResult:
    audio_path: Path
    subtitle_path: Path
    subtitle_cues_path: Path
    duration_sec: float
    segment_durations: list[float]
    subtitle_cues: list[SubtitleCue]
    usage_tasks: list[TTSUsageTask] | None = None

    @property
    def total_characters(self) -> int:
        if not self.usage_tasks:
            return 0
        return sum(int(task.usage.get("characters") or 0) for task in self.usage_tasks)

    def usage_summary(self) -> dict:
        tasks = self.usage_tasks or []
        return {
            "total_characters": self.total_characters,
            "tasks": [
                {
                    "kind": task.kind,
                    "segment_index": task.segment_index,
                    "usage": task.usage,
                }
                for task in tasks
            ],
        }


class TTSClient:
    def synthesize(self, narration: str, segments: list[dict], output_dir: Path) -> TTSResult:
        raise NotImplementedError


def phrase_chunks_for_segment(segment: dict) -> list[tuple[str, str]]:
    """返回分镜内 (TTS文本, 字幕文本) 列表。"""
    text = (segment.get("text") or "").strip()
    if not text:
        raise ValueError(f"segment {segment.get('segment_index')} has empty text")
    chunks = split_phrase_chunks(text)
    if chunks:
        return chunks
    return [(text, text)]


def sentences_for_segment(segment: dict) -> list[str]:
    """兼容旧调用：返回 TTS 文本（含标点）。"""
    return [tts for tts, _ in phrase_chunks_for_segment(segment)]


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


def synthesize_utterance(
    text: str,
    output_path: Path,
    *,
    rate: float | None = None,
    pitch: float | None = None,
) -> Path:
    """合成单句 MP3（片头品牌喊声等）。有 TTS Key 时始终走真实合成，不受 MOCK_MODE 影响。"""
    settings = get_settings()
    has_tts = bool(settings.tts_api_key or settings.dashscope_api_key)
    if not has_tts:
        from app.services.tts.tts_mock import synthesize_utterance as _mock_utterance

        return _mock_utterance(text, output_path, rate=rate)
    from app.services.tts.tts_ali import synthesize_utterance as _ali_utterance

    return _ali_utterance(text, output_path, rate=rate, pitch=pitch)
