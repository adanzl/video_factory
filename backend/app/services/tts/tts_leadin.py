"""CosyVoice 复刻音色句首弱启动：合成前加短引导词，再按字级时间戳裁掉。"""

from __future__ import annotations

import logging
from pathlib import Path

from app.services.tts.phrase_timing import TimedWord
from app.services.tts.segment_trim import TrimPlan, _trim_audio, shift_word_timestamps

logger = logging.getLogger(__name__)

# cSpell: disable
CLONED_VOICE = "cosyvoice-v3.5-flash-leo-60621bdce780434ab0734555e5196d7d"
# cSpell: enable

DEFAULT_LEAD_IN = "那，"
_WEAK_START_CHARS = frozenset("可但而然因")


def prepare_lead_in(text: str, *, voice: str, lead_in: str = DEFAULT_LEAD_IN) -> tuple[str, str | None]:
    """句首易吞字时返回 (带引导词的 TTS 文本, 引导词)；字幕仍用原文。"""
    if voice != CLONED_VOICE or not text.strip() or not lead_in:
        return text, None
    if text[0] not in _WEAK_START_CHARS:
        return text, None
    return f"{lead_in}{text}", lead_in


def strip_tts_lead_in(path: Path, words: list[TimedWord], lead_in: str) -> list[TimedWord]:
    """裁掉引导词对应音频，并平移剩余字级时间戳。"""
    if not lead_in or not words:
        return words

    expected = list(lead_in)
    matched = 0
    cut_ms = 0
    for word in words:
        if matched < len(expected) and word.text == expected[matched]:
            cut_ms = word.end_time_ms
            matched += 1
        else:
            break

    if matched < len(expected):
        logger.warning(
            "tts lead-in partial match %r (%s/%s chars), skip strip",
            lead_in,
            matched,
            len(expected),
        )
        return words

    remaining = words[matched:]
    if cut_ms <= 0 or not remaining:
        return remaining

    _trim_audio(path, TrimPlan(leading_ms=cut_ms, trailing_ms=0))
    shifted = shift_word_timestamps(remaining, cut_ms)
    logger.info(
        "tts lead-in stripped %r cut=%sms words %s -> %s",
        lead_in,
        cut_ms,
        len(words),
        len(shifted),
    )
    return shifted
