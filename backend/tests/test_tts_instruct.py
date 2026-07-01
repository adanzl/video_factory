"""TTS instruction 解析测试。"""

from __future__ import annotations

from app.services.tts.instruct import resolve_instruction

_CLONED_VOICE = "cosyvoice-v3.5-flash-leo-60621bdce780434ab0734555e5196d7d"  # cSpell: disable-line


def test_resolve_instruction_explicit_only():
    result = resolve_instruction(
        _CLONED_VOICE,
        explicit="全局覆盖指令。",
        preset="science_child",
    )
    assert result == "全局覆盖指令。"


def test_resolve_instruction_returns_none_without_explicit():
    assert resolve_instruction(_CLONED_VOICE, preset="science_child") is None
    assert resolve_instruction("longhuhu_v3", preset="science_child") is None
    assert resolve_instruction("longwan_v3", preset="science_child") is None
