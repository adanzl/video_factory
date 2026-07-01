"""配音气口：整段 TTS 后按字级时间戳量化句间换气停顿。"""

from __future__ import annotations

from dataclasses import dataclass

from app.services.tts.phrase_timing import (
    TimedWord,
    match_phrase_words,
    phrase_durations_from_words,
    speech_end_ms,
)

__all__ = [
    "PhraseBreathCue",
    "build_phrase_breath_cues",
    "pause_after_ms",
    "phrase_pauses_from_matched",
]


@dataclass(frozen=True)
class PhraseBreathCue:
    """单句字幕时长 + 句后气口（下一句开口前的自然停顿）。"""

    display_text: str
    tts_text: str
    duration_sec: float
    word_begin_ms: int | None
    word_end_ms: int | None
    pause_after_ms: int | None


def pause_after_ms(
    current_words: list[TimedWord],
    next_words: list[TimedWord],
) -> int | None:
    """两句之间气口：下一句开口 − 本句末个实词收声（不含句尾标点）。"""
    if not current_words or not next_words:
        return None
    end_ms = speech_end_ms(current_words)
    if end_ms is None:
        return None
    return max(0, next_words[0].begin_time_ms - end_ms)


def phrase_pauses_from_matched(
    matched_per_phrase: list[list[TimedWord]],
) -> list[int | None]:
    pauses: list[int | None] = []
    for index, matched in enumerate(matched_per_phrase):
        if index + 1 < len(matched_per_phrase):
            pauses.append(pause_after_ms(matched, matched_per_phrase[index + 1]))
        else:
            pauses.append(None)
    return pauses


def build_phrase_breath_cues(
    phrases: list[tuple[str, str]],
    words: list[TimedWord],
    *,
    segment_duration_sec: float,
) -> list[PhraseBreathCue]:
    """断句时长（含句间气口）与每句后的 pause_after_ms。"""
    matched = match_phrase_words(phrases, words)
    durations = phrase_durations_from_words(
        phrases,
        words,
        segment_duration_sec=segment_duration_sec,
    )
    pauses = phrase_pauses_from_matched(matched)
    return [
        PhraseBreathCue(
            display_text=display,
            tts_text=tts,
            duration_sec=duration,
            word_begin_ms=matched_words[0].begin_time_ms if matched_words else None,
            word_end_ms=matched_words[-1].end_time_ms if matched_words else None,
            pause_after_ms=pause,
        )
        for (tts, display), duration, matched_words, pause in zip(
            phrases,
            durations,
            matched,
            pauses,
            strict=False,
        )
    ]
