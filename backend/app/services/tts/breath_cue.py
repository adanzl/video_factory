"""配音气口：DeepSeek 断句 + pause_ms 解析，转 CosyVoice SSML break。"""

from __future__ import annotations

import logging
import random
import re
import time
from dataclasses import dataclass

import requests

from app.config import get_settings
from app.services.llm.deepseek_request import build_deepseek_chat_payload
from app.services.llm.llm_deepseek import _loads_llm_json

logger = logging.getLogger(__name__)

PAUSE_MARK = "·"
MIN_LEN_FOR_LLM = 2
MIN_LEN_FOR_TTS_PART = 2
_PAUSE_ADJ_PUNCT = frozenset("，。！？；：,.!?;:…")
_MARK_ADJ_PUNCT_DROP = _PAUSE_ADJ_PUNCT - {"？"}
_QUESTION_MARK = "？"


def strip_trailing_punct_before_break(text: str) -> str:
    """SSML break 前去掉句读标点（？保留），避免与 break 双重停顿。"""
    result = text.rstrip()
    while result and result[-1] in _MARK_ADJ_PUNCT_DROP:
        result = result[:-1]
    return result


def should_skip_break_before_question(text: str) -> bool:
    return text.rstrip().endswith(_QUESTION_MARK)


_LLM_JSON_FENCE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL | re.IGNORECASE)
_LLM_MAX_RETRIES = 4
_LLM_MAX_TOKENS = 1024


@dataclass(frozen=True)
class BreathCueParsed:
    segmented: str
    pause_ms: list[int]


def is_usable(parsed: BreathCueParsed | None) -> bool:
    return (
        parsed is not None
        and bool(parsed.segmented.strip())
        and bool(parsed.pause_ms)
        and PAUSE_MARK in parsed.segmented
    )


def _is_han_char(ch: str) -> bool:
    return len(ch) == 1 and "\u4e00" <= ch <= "\u9fff"


def _system_prompt() -> str:
    m = PAUSE_MARK
    return (
        f"你是中文科普短视频配音稿编辑。请在需要换气处插入气口「{m}」，"
        f"并给出每个气口后的停顿时长（毫秒）。\n\n"
        "遵守以下规则：\n"
        f"* 只允许“插入”气口，不得改写原文：不能增删文字，不能改动任何原有标点"
        f"（尤其不能把原始标点改成「{m}」，不能把「，」删掉或换成「{m}」）。\n"
        f"* 气口只能插在字词之间，不能贴着标点；禁止出现「{m}、」「、{m}」"
        f"「{m}，」「，{m}」；\n"
        f"* 整句不能以「{m}」结尾。\n"
        "* 按语义短语断句，不拆紧密搭配；\n"
        f"* 禁止「…{m}的…」，气口不得紧贴放在「的」前面。\n"
        "* pause_ms 用顿号级短停：每处 50-120ms；多处时做轻微随机，避免全相同。\n\n"
        "输出必须是 JSON 且仅一个对象：\n"
        f"- text: 插入气口后的完整文本\n"
        f"- pause_ms: 与 text 中「{m}」数量一一对应的整数数组\n\n"
        "示例：\n"
        f'{{"text":"你知道吗{m}欧洲好多房子都没空调，","pause_ms":[82]}}'
    )


def _sanitize_mark_adjacent_punct(segmented: str, pause_ms: list[int]) -> tuple[str, list[int]]:
    """
    LLM 把气口贴在标点旁时的修正：
    - 一般标点：删标点、留气口（如 「·，」→「·」）
    - ？旁：删气口、留？（如 「？·」「·？」→「？」）
    """
    mark = PAUSE_MARK
    out_chars: list[str] = []
    out_pauses: list[int] = []
    pause_idx = 0
    i = 0
    while i < len(segmented):
        ch = segmented[i]
        if ch == mark:
            ms = pause_ms[pause_idx] if pause_idx < len(pause_ms) else 75
            pause_idx += 1
            prev = out_chars[-1] if out_chars else ""
            nxt = segmented[i + 1] if i + 1 < len(segmented) else ""

            if prev == _QUESTION_MARK or nxt == _QUESTION_MARK:
                if nxt == _QUESTION_MARK:
                    out_chars.append(_QUESTION_MARK)
                    i += 2
                else:
                    i += 1
                continue

            out_chars.append(mark)
            out_pauses.append(ms)
            if nxt in _MARK_ADJ_PUNCT_DROP:
                i += 2
            else:
                i += 1
            continue

        nxt = segmented[i + 1] if i + 1 < len(segmented) else ""
        if ch in _MARK_ADJ_PUNCT_DROP and nxt == mark:
            i += 1
            continue
        if ch == _QUESTION_MARK and nxt == mark:
            out_chars.append(_QUESTION_MARK)
            if pause_idx < len(pause_ms):
                pause_idx += 1
            i += 2
            continue

        out_chars.append(ch)
        i += 1

    return "".join(out_chars), out_pauses


def post_process(original: str, raw: str) -> BreathCueParsed | None:
    """解析 LLM JSON，按原文对齐气口位置并去掉句末/「的」前气口。"""
    if not raw or not raw.strip():
        return None
    s = raw.strip()
    fence = _LLM_JSON_FENCE.match(s)
    if fence:
        s = fence.group(1).strip()
    try:
        root = _loads_llm_json(s)
        if "text" not in root or "pause_ms" not in root:
            return None
        segmented = str(root["text"]).strip()
        pause_raw = root["pause_ms"]
        if not isinstance(pause_raw, list):
            return None
        pause_ms = [int(round(float(x))) for x in pause_raw]
        segmented, pause_ms = _sanitize_mark_adjacent_punct(segmented, pause_ms)
        mark = PAUSE_MARK
        n_mark = segmented.count(mark)
        if len(pause_ms) != n_mark:
            logger.debug("pause_ms 与「·」数量不一致: %s vs %s", len(pause_ms), n_mark)
            return None

        if not original or not segmented:
            return BreathCueParsed(original, [])

        keep_boundaries: list[int] = []
        keep_pauses: list[int] = []
        i = 0
        j = 0
        p = 0
        while i < len(segmented):
            ch = segmented[i]
            if ch == mark:
                ms = pause_ms[p] if p < len(pause_ms) else 75
                p += 1
                if j > 0 and j < len(original):
                    prev_ch = original[j - 1]
                    curr_ch = original[j]
                    if _is_han_char(prev_ch) and (
                        _is_han_char(curr_ch) or curr_ch in _PAUSE_ADJ_PUNCT
                    ):
                        keep_boundaries.append(j)
                        keep_pauses.append(ms)
                i += 1
                continue
            if j < len(original) and ch == original[j]:
                i += 1
                j += 1
                continue
            if j < len(original) and original[j] in _PAUSE_ADJ_PUNCT:
                j += 1
                continue
            i += 1

        by_boundary: dict[int, list[int]] = {}
        for boundary, ms in zip(keep_boundaries, keep_pauses, strict=False):
            by_boundary.setdefault(boundary, []).append(ms)

        out_chars: list[str] = []
        out_pauses: list[int] = []
        for idx in range(len(original)):
            for ms in by_boundary.get(idx, []):
                out_chars.append(mark)
                out_pauses.append(ms)
            out_chars.append(original[idx])

        _strip_pause_before_de(out_chars, out_pauses)
        while out_chars and out_chars[-1] == mark:
            out_chars.pop()
            if out_pauses:
                out_pauses.pop()

        if not out_pauses:
            return None

        return BreathCueParsed("".join(out_chars), out_pauses)
    except (ValueError, TypeError, KeyError) as exc:
        logger.debug("气口 JSON 解析失败: %s", exc)
        return None


def _strip_pause_before_de(chars: list[str], pause_ms: list[int]) -> None:
    i = 0
    p = 0
    while i < len(chars):
        if chars[i] == PAUSE_MARK:
            if i + 1 < len(chars) and chars[i + 1] == "的":
                chars.pop(i)
                if p < len(pause_ms):
                    pause_ms.pop(p)
                continue
            i += 1
            p += 1
        else:
            i += 1


def scale_pause_ms_to_fit_slot(
    max_slot_sec: float,
    speech_sum_sec: float,
    pause_ms: list[int],
) -> list[int]:
    """语音+气口超过槽位时等比缩小 pause_ms。"""
    if not pause_ms or max_slot_sec == float("inf") or max_slot_sec != max_slot_sec:
        return pause_ms
    sum_ms = sum(pause_ms)
    if speech_sum_sec + sum_ms / 1000.0 <= max_slot_sec + 1e-6:
        return pause_ms
    if speech_sum_sec >= max_slot_sec - 1e-6:
        logger.warning(
            "气口槽位: 纯语音已超过上限，停顿置 0, speech=%.2fs max=%.2fs",
            speech_sum_sec,
            max_slot_sec,
        )
        return [0] * len(pause_ms)
    factor = (max_slot_sec - speech_sum_sec) / (sum_ms / 1000.0)
    return [int(round(p * factor)) for p in pause_ms]


def _parts_valid(parsed: BreathCueParsed) -> bool:
    parts = parsed.segmented.split(PAUSE_MARK)
    if len(parts) != len(parsed.pause_ms) + 1:
        return False
    for part in parts:
        trimmed = part.strip()
        if not trimmed or len(trimmed) < MIN_LEN_FOR_TTS_PART:
            return False
    return True


def request_parsed(voice_text: str) -> BreathCueParsed | None:
    """DeepSeek 请求 + 解析；失败返回 None（调用方整段 TTS）。"""
    settings = get_settings()
    if not settings.deepseek_api_key:
        logger.warning("气口 DeepSeek 未配置 API Key，跳过")
        return None

    prompt_user = "台词：\n" + voice_text.strip()
    remaining = _LLM_MAX_RETRIES
    while remaining > 0:
        remaining -= 1
        try:
            resp = requests.post(
                f"{settings.deepseek_base_url.rstrip('/')}/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.deepseek_api_key}",
                    "Content-Type": "application/json",
                },
                json=build_deepseek_chat_payload(
                    model=settings.deepseek_model,
                    system=_system_prompt(),
                    user=prompt_user,
                    max_tokens=_LLM_MAX_TOKENS,
                    thinking_enabled=False,
                    json_mode=True,
                ),
                timeout=120,
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0].get("message", {}).get("content") or ""
            parsed = post_process(voice_text, content)
            if parsed is not None:
                return parsed
        except Exception as exc:
            logger.warning("气口 DeepSeek 调用失败, remaining=%s: %s", remaining, exc)
        if remaining > 0:
            time.sleep(1 + random.randint(0, 2))
    return None


def rule_based_breath_cue(original: str) -> BreathCueParsed | None:
    """LLM 失败时按字幕短语边界插气口（规则兜底）。"""
    from app.services.visual.text_render import split_phrase_chunks

    phrases = split_phrase_chunks(original)
    if len(phrases) < 2:
        return None

    segmented_parts: list[str] = []
    pause_ms: list[int] = []
    for index, (tts, _) in enumerate(phrases):
        segmented_parts.append(tts)
        if index >= len(phrases) - 1:
            continue
        tts_stripped = tts.rstrip()
        if len(tts_stripped) <= 4 and tts_stripped.endswith("，"):
            continue
        if tts_stripped.endswith(_QUESTION_MARK):
            continue
        if tts_stripped and tts_stripped[-1] in "。！":
            ms = random.randint(70, 110)
        elif tts_stripped.endswith("，"):
            ms = random.randint(55, 85)
        else:
            ms = random.randint(60, 95)
        segmented_parts.append(PAUSE_MARK)
        pause_ms.append(ms)

    segmented = "".join(segmented_parts)
    if PAUSE_MARK not in segmented or not _parts_valid(BreathCueParsed(segmented, pause_ms)):
        return None
    return BreathCueParsed(segmented, pause_ms)


def prepare_ssml_text(original: str) -> tuple[str, bool]:
    """
    为 CosyVoice 准备 SSML 文本。
    返回 (text, enable_ssml)；不可用时退回原文 PlainText。
    """
    from app.services.tts.ssml_build import build_ssml_from_breath_cue

    text = original.strip()
    if len(text) < MIN_LEN_FOR_LLM:
        return text, False

    parsed = request_parsed(text)
    if not is_usable(parsed) or parsed is None or not _parts_valid(parsed):
        parsed = rule_based_breath_cue(text)
        if parsed:
            logger.info("气口 LLM 不可用，使用规则短语边界兜底, marks=%s", parsed.pause_ms)
    if not is_usable(parsed) or parsed is None or not _parts_valid(parsed):
        logger.info("气口不可用，整段 PlainText TTS, chars=%s", len(text))
        return text, False

    ssml = build_ssml_from_breath_cue(parsed)
    if not ssml:
        return text, False

    logger.info(
        "气口 SSML: marks=%s pause_ms=%s",
        parsed.segmented.count(PAUSE_MARK),
        parsed.pause_ms,
    )
    return ssml, True
