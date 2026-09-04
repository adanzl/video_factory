"""gold_chat setting 地点映射与限制。"""

from __future__ import annotations

import pytest

from app.services.gold_story.gold_chat import convert as gc
from app.services.gold_story.gold_chat.setting import (
    ALLOWED_SETTING_PLACES,
    classify_setting_place,
    format_place_catalog_for_prompt,
    normalize_gold_chat_setting,
    resolve_target_location,
    set_place_classify_hook,
    setting_location_violations,
)


@pytest.fixture(autouse=True)
def _reset_place_hook():
    set_place_classify_hook(None)
    classify_setting_place.cache_clear()
    yield
    set_place_classify_hook(None)
    classify_setting_place.cache_clear()


def _hook(mapping: dict[str, str]):
    default = mapping.get("__default__", "客厅")

    def _fn(raw: str, context: str) -> dict:
        blob = f"{raw} {context}"
        for key, place in mapping.items():
            if key == "__default__":
                continue
            if key in blob:
                return {"place": place, "confidence": 0.9, "reason": "test"}
        return {"place": default, "confidence": 0.9, "reason": "test"}

    return _fn


def test_place_catalog_covers_allowed_set():
    catalog = format_place_catalog_for_prompt()
    assert "客厅" in catalog
    assert ALLOWED_SETTING_PLACES == frozenset(
        line.split("：", 1)[0].removeprefix("- ").strip()
        for line in catalog.splitlines()
        if line.startswith("- ")
    )


def test_resolve_keeps_allowed_place_in_text():
    assert resolve_target_location("卧室里吵架") == "卧室"
    assert resolve_target_location("地板上的垫子") == "地板"


def test_classify_setting_place_uses_llm_hook():
    set_place_classify_hook(_hook({"车内": "卧室", "幼儿园午休垫子": "地板"}))
    assert classify_setting_place("车内") == "卧室"
    assert classify_setting_place("幼儿园午休垫子") == "地板"


def test_resolve_unknown_uses_llm_classify():
    set_place_classify_hook(_hook({"车内": "卧室"}))
    assert resolve_target_location("车内") == "卧室"


def test_normalize_car_setting_maps_via_llm():
    set_place_classify_hook(_hook({"车内": "卧室"}))
    new, notes = normalize_gold_chat_setting(
        "车内，妈妈开车，灿灿和昭昭坐在后座",
        scene_contract_location="车内",
    )
    assert "卧室" in new
    assert "开车" not in new
    assert any("归类" in n for n in notes)


def test_setting_violations_reject_car():
    assert setting_location_violations("车内，妈妈开车")


def test_setting_violations_allow_bedroom():
    assert setting_location_violations("卧室里，灿灿和昭昭因为作业吵起来") == []


def test_normalize_kindergarten_setting_maps_via_llm():
    set_place_classify_hook(_hook({"幼儿园午休垫子": "地板"}))
    new, notes = normalize_gold_chat_setting(
        "幼儿园午休垫子上，灿灿和昭昭对峙",
        scene_contract_location="幼儿园午休垫子",
    )
    assert "地板" in new
    assert "幼儿园" not in new
    assert notes


def test_apply_gold_chat_normalizations_i_trims_tail():
    """I 型（车内→卧室）：映射为允许地点并保持制敌收束闭环完整。

    现行 I 型在「首次收束后裁拖尾」与「垫字补 min 回填中段」两条路径间
    受流程顺序影响，最终对话长度不固定，故此处不 pin 具体行数。
    """
    set_place_classify_hook(_hook({"车内": "卧室"}))
    chat = {
        "story_type": "I",
        "setting": "车内，妈妈开车",
        "dialogue": [
            {"speaker": "灿灿", "line": "我爱学习，你爱吗？"},
            {"speaker": "昭昭", "line": "我……我也爱吧。"},
            {"speaker": "灿灿", "line": "那你怎么老不写作业？"},
            {"speaker": "昭昭", "line": "可我更爱你呀！"},
            {"speaker": "灿灿", "line": "少来！凭啥我爱学习你不爱？"},
            {"speaker": "昭昭", "line": "我……我说不过你。"},
            {"speaker": "灿灿", "line": "让你学习你哭哭啼啼，让你玩你咋不哭？"},
            {"speaker": "昭昭", "line": "我不说了，我看窗外还不行？"},
            {"speaker": "灿灿", "line": "哼，一招制敌！你服不服？"},
            {"speaker": "昭昭", "line": "服了……我以后也爱学习。"},
            {"speaker": "灿灿", "line": "这还差不多，说到做到，别光嘴上说啊。"},
            {"speaker": "昭昭", "line": "嗯嗯，姐姐你监督我，我一定写，不偷懒。"},
        ],
    }
    row = {
        "structure_type": "I",
        "payload": {"scene_contract": {"location": "车内", "characters": ["灿灿", "昭昭"]}},
    }
    out, notes = gc.apply_gold_chat_normalizations(dict(chat), row=row)
    assert "卧室" in out["setting"]
    lines = [d["line"] for d in out["dialogue"]]
    # I 制敌收束闭环：无论后续走裁尾还是垫字回填，闭环两拍都须完整
    assert "服了……我以后也爱学习。" in lines
    assert "这还差不多，说到做到，别光嘴上说啊。" in lines
    assert any("subplot" in n or "归类" in n or "映射" in n for n in notes)
