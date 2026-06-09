"""将 CosyVoice 字级时间戳对齐到 split_phrase_chunks 的断句。"""

from __future__ import annotations

import re
from dataclasses import dataclass

__all__ = [
    "TimedWord",
    "build_segment_tts_text",
    "normalize_word_timestamps",
    "phrase_durations_from_words",
]


@dataclass(frozen=True)
class TimedWord:
    text: str
    begin_time_ms: int
    end_time_ms: int


_PUNCT_ONLY = re.compile(
    r'^[。！？；：，,.!?;:…—·—－~～\'"）】》〉）\]]+$'
)


def build_segment_tts_text(phrases: list[tuple[str, str]]) -> str:
    return "".join(tts for tts, _ in phrases)


def normalize_word_timestamps(raw_words: list[dict]) -> list[TimedWord]:
    """合并多句时间戳；若 API 按句重置时间轴则累加偏移。"""
    if not raw_words:
        return []

    normalized: list[TimedWord] = []
    offset_ms = 0
    prev_end = -1

    for item in raw_words:
        text = str(item.get("text") or "")
        if not text:
            continue
        begin = int(item["begin_time"])
        end = int(item["end_time"])
        if normalized and begin < prev_end - 80:
            offset_ms = normalized[-1].end_time_ms
        begin += offset_ms
        end += offset_ms
        normalized.append(TimedWord(text=text, begin_time_ms=begin, end_time_ms=end))
        prev_end = end

    return normalized


def _proportional_durations(phrases: list[tuple[str, str]], total_sec: float) -> list[float]:
    weights = [max(len(tts.strip()), 1) for tts, _ in phrases]
    total_weight = sum(weights) or 1
    return [max(total_sec * weight / total_weight, 0.05) for weight in weights]


def phrase_durations_from_words(
    phrases: list[tuple[str, str]],
    words: list[TimedWord],
    *,
    segment_duration_sec: float,
) -> list[float]:
    """按 phrase 的 TTS 文本对齐字级时间戳，保留现有断句列表。"""
    if not phrases:
        return []
    if not words:
        return _proportional_durations(phrases, segment_duration_sec)

    durations: list[float | None] = []
    word_idx = 0

    for tts_text, _ in phrases:
        if not tts_text.strip():
            durations.append(0.05)
            continue

        matched: list[TimedWord] = []
        for ch in tts_text:
            if word_idx >= len(words):
                break
            if _PUNCT_ONLY.fullmatch(ch):
                if words[word_idx].text == ch:
                    matched.append(words[word_idx])
                    word_idx += 1
                continue
            if words[word_idx].text == ch:
                matched.append(words[word_idx])
                word_idx += 1
                continue
            if len(words[word_idx].text) == 1 and ch in words[word_idx].text:
                matched.append(words[word_idx])
                word_idx += 1
                continue
            if ch in "，。！？；：,.!?;:…":
                continue
            matched.append(words[word_idx])
            word_idx += 1

        if matched:
            begin = matched[0].begin_time_ms
            end = matched[-1].end_time_ms
            durations.append(max((end - begin) / 1000.0, 0.05))
        else:
            durations.append(None)

    resolved = [
        duration if duration is not None else 0.05
        for duration in durations
    ]
    total = sum(resolved)
    if total <= 0.01:
        return _proportional_durations(phrases, segment_duration_sec)

    scale = segment_duration_sec / total
    return [max(duration * scale, 0.05) for duration in resolved]
