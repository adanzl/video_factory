"""gold_chat setting 地点映射与限制。"""

from __future__ import annotations

from app.services.daily_story.gold_story.gold_chat import convert as gc
from app.services.daily_story.gold_story.gold_chat.setting import (
    normalize_gold_chat_setting,
    resolve_target_location,
    setting_location_violations,
)


def test_resolve_car_to_bedroom():
    assert resolve_target_location("车内") == "卧室"
    assert resolve_target_location("妈妈开车，后座") == "卧室"


def test_normalize_car_setting():
    new, notes = normalize_gold_chat_setting(
        "车内，妈妈开车，灿灿和昭昭坐在后座",
        scene_contract_location="车内",
    )
    assert "卧室" in new
    assert "开车" not in new
    assert notes


def test_setting_violations_reject_car():
    assert setting_location_violations("车内，妈妈开车")


def test_setting_violations_allow_bedroom():
    assert setting_location_violations("卧室里，灿灿和昭昭因为作业吵起来") == []


def test_apply_gold_chat_normalizations_i_trims_tail():
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
    assert len(out["dialogue"]) == 11
    assert any("subplot" in n or "映射" in n for n in notes)
