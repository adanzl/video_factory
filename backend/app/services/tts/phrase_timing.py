"""将 CosyVoice 字级时间戳对齐到 split_phrase_chunks 的断句。"""

from __future__ import annotations

import re
from dataclasses import dataclass

__all__ = [
    "TimedWord",
    "build_segment_tts_text",
    "match_phrase_words",
    "normalize_word_timestamps",
    "phrase_durations_from_words",
    "speech_end_ms",
]


@dataclass(frozen=True)
class TimedWord:
    text: str
    begin_time_ms: int
    end_time_ms: int
    begin_index: int | None = None
    end_index: int | None = None


_PUNCT_ONLY = re.compile(
    r'^[。！？；：，,.!?;:…—·—－~～\'"）】》〉）\]]+$'
)


def build_segment_tts_text(phrases: list[tuple[str, str]]) -> str:
    return "".join(tts for tts, _ in phrases)


def normalize_word_timestamps(raw_words: list[dict]) -> list[TimedWord]:
    """合并多句时间戳；按 begin_index 排序，仅在索引回绕时累加偏移。"""
    if not raw_words:
        return []

    items = [item for item in raw_words if str(item.get("text") or "")]
    if items and items[0].get("begin_index") is not None:
        items.sort(key=lambda item: int(item["begin_index"]))

    normalized: list[TimedWord] = []
    offset_ms = 0
    prev_begin_index: int | None = None

    for item in items:
        text = str(item.get("text") or "")
        begin = int(item["begin_time"])
        end = int(item["end_time"])
        begin_index = item.get("begin_index")
        end_index = item.get("end_index")
        if begin_index is not None:
            begin_index = int(begin_index)
            if prev_begin_index is not None and begin_index < prev_begin_index:
                offset_ms = normalized[-1].end_time_ms if normalized else 0
            prev_begin_index = begin_index
        if end_index is not None:
            end_index = int(end_index)

        begin += offset_ms
        end += offset_ms
        normalized.append(
            TimedWord(
                text=text,
                begin_time_ms=begin,
                end_time_ms=end,
                begin_index=begin_index,
                end_index=end_index,
            )
        )

    normalized = _stabilize_monotonic_times(normalized)
    return normalized


def _stabilize_monotonic_times(
    words: list[TimedWord],
    *,
    rollback_tolerance_ms: int = 300,
) -> list[TimedWord]:
    """修正 API 偶发的时间戳回跳，保持与 begin_index 顺序一致。"""
    if not words:
        return []

    stabilized: list[TimedWord] = [words[0]]
    for word in words[1:]:
        prev = stabilized[-1]
        begin = word.begin_time_ms
        end = word.end_time_ms
        duration = max(end - begin, 50)
        if begin < prev.end_time_ms - rollback_tolerance_ms:
            begin = prev.end_time_ms
            end = begin + duration
        elif end < begin:
            end = begin + duration
        stabilized.append(
            TimedWord(
                text=word.text,
                begin_time_ms=begin,
                end_time_ms=end,
                begin_index=word.begin_index,
                end_index=word.end_index,
            )
        )
    return stabilized


def _proportional_durations(phrases: list[tuple[str, str]], total_sec: float) -> list[float]:
    weights = [max(len(tts.strip()), 1) for tts, _ in phrases]
    total_weight = sum(weights) or 1
    return [max(total_sec * weight / total_weight, 0.05) for weight in weights]


def speech_end_ms(matched_words: list[TimedWord]) -> int | None:
    """句末实词结束时刻（去掉句尾标点）。"""
    if not matched_words:
        return None
    trimmed = list(matched_words)
    while trimmed and _PUNCT_ONLY.fullmatch(trimmed[-1].text):
        trimmed.pop()
    if trimmed:
        return trimmed[-1].end_time_ms
    return matched_words[-1].end_time_ms


def match_phrase_words(
    phrases: list[tuple[str, str]],
    words: list[TimedWord],
) -> list[list[TimedWord]]:
    """把字级时间戳按 phrase 的 TTS 文本逐字顺序对齐（API 漏标点时不串句）。"""
    matched_per_phrase: list[list[TimedWord]] = []
    word_idx = 0

    for tts_text, _ in phrases:
        if not tts_text.strip():
            matched_per_phrase.append([])
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

        matched_per_phrase.append(matched)

    return matched_per_phrase


def phrase_durations_from_words(
    phrases: list[tuple[str, str]],
    words: list[TimedWord],
    *,
    segment_duration_sec: float,
    duration_drift_tolerance_sec: float = 0.15,
) -> list[float]:
    """按字级时间戳切分断句；句间自然停顿算进前一句时长。"""
    if not phrases:
        return []
    if not words:
        return _proportional_durations(phrases, segment_duration_sec)

    matched_per_phrase = match_phrase_words(phrases, words)
    begins: list[int | None] = []
    speech_ends: list[int | None] = []
    for matched in matched_per_phrase:
        if matched:
            begins.append(matched[0].begin_time_ms)
            speech_ends.append(matched[-1].end_time_ms)
        else:
            begins.append(None)
            speech_ends.append(None)

    durations: list[float] = []
    for index in range(len(phrases)):
        begin = begins[index]
        if begin is None:
            durations.append(0.05)
            continue

        next_begin = None
        for later in begins[index + 1 :]:
            if later is not None:
                next_begin = later
                break

        if next_begin is not None:
            end_ms = next_begin
        else:
            end_ms = speech_ends[index] if speech_ends[index] is not None else begin

        durations.append(max((end_ms - begin) / 1000.0, 0.05))

    segment_ms = int(round(segment_duration_sec * 1000))
    if begins and begins[-1] is not None and speech_ends[-1] is not None:
        tail_ms = segment_ms - speech_ends[-1]
        if tail_ms > 50:
            durations[-1] = max(durations[-1] + tail_ms / 1000.0, 0.05)

    total = sum(durations)
    if total <= 0.01:
        return _proportional_durations(phrases, segment_duration_sec)

    if abs(total - segment_duration_sec) > duration_drift_tolerance_sec:
        scale = segment_duration_sec / total
        return [max(duration * scale, 0.05) for duration in durations]

    return durations
