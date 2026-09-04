"""O 类目标错位：线路/校验/观感 smoke。"""

from app.services.daily_story.gold_story.types import (
    allowed_structure_types,
    structure_type_for_mechanism,
    validate_mechanism_structure_pair,
)
from app.services.daily_story.quality import attach_daily_story_quality
from app.services.daily_story.story_types import STORY_TYPE_LINES, patch_type_body
from app.services.daily_story.story_types.o.validate import append_o_body_errors


def test_o_registered_and_m13_maps_to_o():
    assert "O" in STORY_TYPE_LINES
    assert STORY_TYPE_LINES["O"].label == "目标错位"
    assert STORY_TYPE_LINES["O"].quality_ready is False
    assert structure_type_for_mechanism("M13") == "O"
    assert allowed_structure_types("M13") == frozenset({"O"})
    validate_mechanism_structure_pair("M13", "O")


def test_o_body_validate_and_structure_score():
    story = {
        "story_type": "O",
        "scene_title": "光顾着赢",
        "setting": "餐桌前",
        "conflict_core": "目标错位：昭昭光顾着赢猜拳，菜被吃光",
        "key": "抢吃猜拳",
        "punchline_explain": "O类目标错位，赢了过程输了目标",
        "discovery_opening": [
            {"speaker": "昭昭", "line": "剪刀石头布，赢的才能吃菜！"},
            {"speaker": "灿灿", "line": "好，来！"},
        ],
        "dialogue": [
            {"speaker": "昭昭", "line": "剪刀石头布，赢的才能吃菜！"},
            {"speaker": "灿灿", "line": "好，来！"},
            {"speaker": "昭昭", "line": "剪刀石头布！我赢了！"},
            {"speaker": "灿灿", "line": "那你夹吧。"},
            {"speaker": "昭昭", "line": "咦，菜怎么少了？"},
            {"speaker": "灿灿", "line": "你赢你的，我吃我的。"},
            {"speaker": "昭昭", "line": "再来！又赢！"},
            {"speaker": "灿灿", "line": "快夹，不然又没了。"},
            {"speaker": "昭昭", "line": "啊？只剩一小块了？"},
            {"speaker": "灿灿", "line": "嘿嘿，我吃饱了。"},
            {"speaker": "昭昭", "line": "我光顾着赢，菜都没了……"},
            {"speaker": "妈妈", "line": "哈哈，你俩真逗。"},
        ],
    }
    errors: list[str] = []
    append_o_body_errors(story, errors)
    assert errors == []

    notes = patch_type_body(story)
    assert isinstance(notes, list)

    attach_daily_story_quality(story, theme="抢吃猜拳")
    q = story["quality"]
    assert q["structure_score"] >= 60
    assert any(
        "点题" in r or "溜走" in r or "死磕" in r or "立规" in r
        for r in q.get("reasons") or []
    )
