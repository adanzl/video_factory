"""CosyVoice 复刻音色句首弱启动：合成前加短引导词，再按字级时间戳裁掉。"""

from __future__ import annotations

import logging
from pathlib import Path

from app.services.tts.phrase_timing import TimedWord
from app.services.tts.segment_trim import TrimPlan, _trim_audio, shift_word_timestamps

logger = logging.getLogger(__name__)

# cSpell: disable
CLONED_VOICE_CAN = "cosyvoice-v3.5-flash-leo-60621bdce780434ab0734555e5196d7d"
CLONED_VOICE_ZHAO = "cosyvoice-v3.5-flash-leo-f9d115bfdf2346edbeb9d21ecd4f9ce9"
# cSpell: enable

DEFAULT_LEAD_IN = "那，"
_LEAD_IN_PAD_MS = 15


def prepare_lead_in(text: str, *, voice: str, lead_in: str = DEFAULT_LEAD_IN) -> tuple[str, str | None]:
    """复刻音色每段合成前加短引导词，再裁掉；字幕仍用原文。"""
    if voice not in (CLONED_VOICE_CAN, CLONED_VOICE_ZHAO) or not text.strip() or not lead_in:
        return text, None
    return f"{lead_in}{text}", lead_in


def strip_tts_lead_in(path: Path, words: list[TimedWord], lead_in: str) -> list[TimedWord]:
    """裁掉引导词对应音频，并平移剩余字级时间戳。"""
    if not lead_in or not words:
        return words

    # 打印TTS返回的所有字级时间戳，便于排查
    logger.debug(
        "tts lead-in check: lead_in=%r words_count=%s first_10_words=%s",
        lead_in,
        len(words),
        [(w.text, w.begin_time_ms) for w in words[:10]],
    )

    expected = list(lead_in)
    matched = 0
    for word in words:
        if matched < len(expected) and word.text == expected[matched]:
            matched += 1
        else:
            break

    if matched < len(expected):
        logger.warning(
            "tts lead-in partial match %r (%s/%s chars), skip strip. words=%s",
            lead_in,
            matched,
            len(expected),
            [(w.text, w.begin_time_ms) for w in words[:10]],
        )
        return words

    remaining = words[matched:]
    if not remaining:
        return remaining

    cut_ms = max(0, remaining[0].begin_time_ms - _LEAD_IN_PAD_MS)
    _trim_audio(path, TrimPlan(leading_ms=cut_ms, trailing_ms=0))
    shifted = shift_word_timestamps(remaining, cut_ms)
    logger.debug(
        "tts lead-in stripped %r cut=%sms words %s -> %s remaining_first_5=%s",
        lead_in,
        cut_ms,
        len(words),
        len(shifted),
        [(w.text, w.begin_time_ms) for w in remaining[:5]],
    )
    return shifted
