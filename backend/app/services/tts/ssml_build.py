"""CosyVoice SSML 构建（气口 break 等）。"""

from __future__ import annotations

from app.services.tts.breath_cue import (
    MIN_LEN_FOR_TTS_PART,
    PAUSE_MARK,
    BreathCueParsed,
    should_skip_break_before_question,
    strip_trailing_punct_before_break,
)


def escape_ssml_text(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_ssml_from_breath_cue(parsed: BreathCueParsed) -> str | None:
    """将气口稿转为 <speak>…<break/>…</speak>。"""
    parts = parsed.segmented.split(PAUSE_MARK)
    if len(parts) != len(parsed.pause_ms) + 1:
        return None
    for part in parts:
        if len(part.strip()) < MIN_LEN_FOR_TTS_PART:
            return None

    chunks: list[str] = []
    for index, part in enumerate(parts):
        spoken = part
        if index < len(parsed.pause_ms):
            if should_skip_break_before_question(part):
                chunks.append(escape_ssml_text(part))
                continue
            spoken = strip_trailing_punct_before_break(part)
            if len(spoken.strip()) < MIN_LEN_FOR_TTS_PART:
                return None
            ms = max(50, min(int(parsed.pause_ms[index]), 10000))
            if ms > 0:
                chunks.append(escape_ssml_text(spoken))
                chunks.append(f'<break time="{ms}ms"/>')
                continue
        chunks.append(escape_ssml_text(spoken))
    return f"<speak>{''.join(chunks)}</speak>"
