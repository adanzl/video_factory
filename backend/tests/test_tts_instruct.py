"""TTS instruction 解析测试。"""

from __future__ import annotations

from app.services.tts.instruct import resolve_instruction
from app.services.tts.tts_ali import _disambiguate_dao_for_tts

_CLONED_VOICE = "cosyvoice-v3.5-flash-leo-40c4359c732f4b459a40f3408e1186ed"  # cSpell: disable-line


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


def test_disambiguate_dao_forces_pour_reading():
    assert _disambiguate_dao_for_tts("我要先倒。") == "我要先到。"
    assert _disambiguate_dao_for_tts("你少倒点") == "你少到点"
    assert _disambiguate_dao_for_tts("我是倒数，不是先倒。") == "我是到数，不是先到。"
    assert _disambiguate_dao_for_tts("一人倒一次") == "一人到一次"


def test_disambiguate_dao_keeps_fall_compounds():
    assert _disambiguate_dao_for_tts("我差点摔倒了") == "我差点摔倒了"
    assert _disambiguate_dao_for_tts("摔倒后再倒水") == "摔倒后再到水"
    assert _disambiguate_dao_for_tts("真倒霉") == "真倒霉"