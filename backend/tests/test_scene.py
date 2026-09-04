"""H3a scene_contract 与成品对白 hard 校验测试。"""

from __future__ import annotations

import pytest

from app.services.gold_story.gold_chat.validate import (
    validate_chat_hard,
)
from app.services.gold_story.scene import (
    format_scene_block,
    seed_from_beat_chain,
    validate_scene,
)


def _sample_contract() -> dict:
    return {
        "source_type": "field",
        "location": "客厅",
        "object": "遥控器",
        "characters": ["昭昭", "灿灿"],
        "conflict": "抢遥控器",
        "mechanism": "M2",
        "mom_lines_max": 0,
        "remap_note": "姐弟→昭昭灿灿",
        "beat_chain": [
            {"speaker": "灿灿", "intent": "占物"},
            {"speaker": "昭昭", "intent": "质疑"},
            {"speaker": "灿灿", "intent": "歪理"},
            {"speaker": "昭昭", "intent": "威胁"},
        ],
        "closing_intent": "嘴硬收束",
        "contract_confidence": 0.8,
    }


def test_validate_scene_ok():
    assert validate_scene(_sample_contract()) == []


def test_validate_scene_rejects_short_chain():
    bad = {**_sample_contract(), "beat_chain": [{"speaker": "昭昭", "intent": "a"}]}
    errs = validate_scene(bad)
    assert any("beat_chain" in e for e in errs)


def test_format_scene_block():
    block = format_scene_block(_sample_contract())
    assert "scene_contract" in block
    assert "昭昭" in block
    assert "beat_chain" in block


def test_seed_from_beat_chain():
    seed = seed_from_beat_chain(_sample_contract()["beat_chain"])
    assert len(seed) == 4
    assert seed[0]["speaker"] == "灿灿"


def _long_dialogue(n: int = 14) -> list[dict[str, str]]:
    lines: list[dict[str, str]] = []
    for i in range(n):
        sp = "昭昭" if i % 2 else "灿灿"
        lines.append({"speaker": sp, "line": f"这是第{i + 1}句可拍对白，我们当场说清楚。"})
    return lines


def test_validate_chat_hard_ok():
    story = {"dialogue": _long_dialogue(14)}
    assert validate_chat_hard(story, mom_lines_max=0) == []


def test_validate_chat_hard_rejects_short_lines():
    story = {"dialogue": _long_dialogue(8)}
    errs = validate_chat_hard(story)
    assert any("对白句数" in e for e in errs)


def test_validate_chat_hard_allows_mom_last():
    lines = _long_dialogue(14)
    lines[-1] = {"speaker": "妈妈", "line": "好了别吵了。"}
    errs = validate_chat_hard(lines_to_story(lines), mom_lines_max=1)
    assert not any("末句" in e for e in errs)


def lines_to_story(lines: list[dict[str, str]]) -> dict:
    return {"dialogue": lines}
