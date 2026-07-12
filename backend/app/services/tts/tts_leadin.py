"""CosyVoice 复刻音色句首弱启动：合成前加短引导词，再按字级时间戳裁掉。"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from app.services.tts.phrase_timing import TimedWord
from app.services.tts.segment_trim import TrimPlan, _trim_audio, shift_word_timestamps

logger = logging.getLogger(__name__)

# cSpell: disable
CLONED_VOICE_CAN = "cosyvoice-v3.5-flash-leo-60621bdce780434ab0734555e5196d7d"
CLONED_VOICE_ZHAO = "cosyvoice-v3.5-flash-leo-f9d115bfdf2346edbeb9d21ecd4f9ce9"
# cSpell: enable

DEFAULT_LEAD_IN = "那，"
_LEAD_IN_PAD_MS = 0  # 切到内容词开头，越小切得越多
_LEAD_IN_MS_PER_CHAR = 300  # 每个实字约 300ms（rate=1.0 基准）
_PUNCT_RE = re.compile(r"^[。！？；：，,.!?;:…—·~～'\"）】》〉）\]]+$")


def prepare_lead_in(text: str, *, voice: str, lead_in: str = DEFAULT_LEAD_IN) -> tuple[str, str | None]:
    """复刻音色每段合成前加短引导词，再裁掉；字幕仍用原文。"""
    if voice not in (CLONED_VOICE_CAN, CLONED_VOICE_ZHAO) or not text.strip() or not lead_in:
        return text, None
    return f"{lead_in}{text}", lead_in


def _strip_lead_in_fallback(path: Path, lead_in: str, rate: float) -> list[TimedWord]:
    """words 为空时，按 lead-in 实字数+语速估算时长，强制裁剪音频开头。"""
    content_chars = [c for c in lead_in if not _PUNCT_RE.fullmatch(c)]
    if not content_chars:
        return []
    est_ms = int(len(content_chars) * _LEAD_IN_MS_PER_CHAR / max(rate, 0.5))
    cut_ms = est_ms + 200  # 估算 lead-in 时长 + 尾巴余量
    if cut_ms <= 0:
        return []
    logger.info(
        "tts lead-in fallback (no words) %r est=%sms cut=%sms rate=%.2f",
        lead_in, est_ms, cut_ms, rate,
    )
    _trim_audio(path, TrimPlan(leading_ms=cut_ms, trailing_ms=0))
    return []


def strip_tts_lead_in(
    path: Path, words: list[TimedWord], lead_in: str, *, rate: float = 1.0,
) -> list[TimedWord]:
    """裁掉引导词对应音频，并平移剩余字级时间戳。"""
    if not lead_in:
        return words

    logger.debug(
        "tts lead-in entry: words=%s lead_in=%r rate=%.2f path=%s",
        len(words), lead_in, rate, path.name,
    )

    # words 为空时（TTS 未返回时间戳），按实字数+语速估算裁剪
    if not words:
        return _strip_lead_in_fallback(path, lead_in, rate)

    # 提取 lead_in 中的实字（非标点）
    lead_content_chars = [c for c in lead_in if not _PUNCT_RE.fullmatch(c)]

    # 在 TTS 返回的 words 中找到 lead-in 实字，跳过中间可能缺失的标点
    matched_content = 0
    last_lead_word_idx = -1  # lead-in 最后一个 word 的索引
    for i, word in enumerate(words):
        if matched_content >= len(lead_content_chars):
            break
        if word.text == lead_content_chars[matched_content]:
            matched_content += 1
            last_lead_word_idx = i
        elif _PUNCT_RE.fullmatch(word.text):
            # 标点：如果是 lead_in 期望的标点则消费，否则跳过
            expected_idx = matched_content
            if expected_idx < len(lead_in) and lead_in[expected_idx] == word.text:
                last_lead_word_idx = i
            # 非期望标点，跳过但不中断匹配
        else:
            # 实字不匹配 → 停止
            break

    if matched_content >= len(lead_content_chars):
        # 匹配完实字后，继续跳过 lead-in 尾部的标点
        content_end_idx = last_lead_word_idx
        for j in range(last_lead_word_idx + 1, len(words)):
            if _PUNCT_RE.fullmatch(words[j].text):
                content_end_idx = j
            else:
                break
        remaining = words[content_end_idx + 1:]
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

    # Fallback: 匹配失败，用第一个实字的时间戳强制裁剪
    first_content_idx = None
    for i, word in enumerate(words):
        if not _PUNCT_RE.fullmatch(word.text):
            if first_content_idx is None:
                first_content_idx = i
            # 跳过 lead_in 中的实字数量的实字
            content_count = sum(
                1 for w in words[: i + 1] if not _PUNCT_RE.fullmatch(w.text)
            )
            if content_count >= len(lead_content_chars):
                remaining = words[i + 1:]
                cut_ms = max(0, word.end_time_ms + 200)  # lead-in 结束后 +200ms 覆盖尾巴
                logger.warning(
                    "tts lead-in fallback strip %r cut=%sms (exact match failed) words=%s",
                    lead_in,
                    cut_ms,
                    [(w.text, w.begin_time_ms) for w in words[:10]],
                )
                _trim_audio(path, TrimPlan(leading_ms=cut_ms, trailing_ms=0))
                shifted = shift_word_timestamps(remaining, cut_ms)
                return shifted

    logger.warning(
        "tts lead-in could not strip %r, no content words found. words=%s",
        lead_in,
        [(w.text, w.begin_time_ms) for w in words[:10]],
    )
    return words
