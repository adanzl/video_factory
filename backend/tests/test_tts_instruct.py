"""TTS instruction 解析优先级测试。"""

from __future__ import annotations

from app.services.tts.instruct import resolve_instruction

_CLONED_VOICE = "cosyvoice-v3.5-flash-leo-60621bdce780434ab0734555e5196d7d"  # cSpell: disable-line


def test_resolve_instruction_explicit_overrides_voice_map():
    result = resolve_instruction(
        _CLONED_VOICE,
        explicit="全局覆盖指令。",
        preset="science_child",
    )
    assert result == "全局覆盖指令。"


def test_resolve_instruction_uses_voice_map_for_cloned_voice():
    result = resolve_instruction(_CLONED_VOICE, preset="science_child")
    assert result == "语速适中，吐字清晰，语气亲切，适合儿童科普短视频。"


def test_resolve_instruction_falls_back_to_preset_for_system_voice():
    result = resolve_instruction("longhuhu_v3", preset="science_child")
    assert result == "你说话的角色是可爱孩童，你说话的情感是neutral。"  # cSpell: disable-line


def test_resolve_instruction_returns_none_when_unmapped():
    assert resolve_instruction("longwan_v3", preset="science_child") is None
