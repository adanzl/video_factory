"""N 类正经胡说：线路/校验/观感 smoke。"""

from app.services.daily_story.gold_story.types import (
    allowed_structure_types,
    structure_type_for_mechanism,
    validate_mechanism_structure_pair,
)
from app.services.daily_story.quality import attach_daily_story_quality
from app.services.daily_story.story_types import STORY_TYPE_LINES, patch_type_body
from app.services.daily_story.story_types.n.validate import append_n_body_errors


def test_n_registered_and_m6_maps_to_n():
    assert "N" in STORY_TYPE_LINES
    assert STORY_TYPE_LINES["N"].label == "正经胡说"
    assert STORY_TYPE_LINES["N"].quality_ready is False
    assert structure_type_for_mechanism("M6") == "N"
    assert allowed_structure_types("M6") == frozenset({"N", "A", "E"})
    validate_mechanism_structure_pair("M6", "N")
    validate_mechanism_structure_pair("M6", "A")
    validate_mechanism_structure_pair("M6", "E")


def test_n_body_validate_and_structure_score():
    story = {
        "story_type": "N",
        "scene_title": "香蕉救父",
        "setting": "家中客厅",
        "conflict_core": "正经胡说：假设性二选一，荒诞自洽噎住追问方",
        "key": "正经胡说",
        "punchline_explain": "N类正经胡说，荒诞自洽噎住追问方",
        "discovery_opening": [
            {"speaker": "灿灿", "line": "如果爸爸掉水里，你先吃啥？"},
            {"speaker": "昭昭", "line": "先吃香蕉。"},
        ],
        "dialogue": [
            {"speaker": "灿灿", "line": "爸爸掉水里，你先吃苹果还是香蕉？"},
            {"speaker": "昭昭", "line": "吃香蕉。"},
            {"speaker": "灿灿", "line": "为什么？"},
            {"speaker": "昭昭", "line": "因为有籽，吃了能长成树。"},
            {"speaker": "灿灿", "line": "长成树又怎样？"},
            {"speaker": "昭昭", "line": "这样就能把爸爸捞上来。"},
            {"speaker": "灿灿", "line": "那……行吧。"},
            {"speaker": "昭昭", "line": "你服了吧。"},
            {"speaker": "灿灿", "line": "接不住了，算了。"},
            {"speaker": "昭昭", "line": "我说得通吧。"},
        ],
    }
    errors: list[str] = []
    append_n_body_errors(story, errors)
    assert errors == []

    notes = patch_type_body(story)
    assert isinstance(notes, list)

    attach_daily_story_quality(story, theme="正经胡说")
    q = story["quality"]
    assert q["structure_score"] >= 60
    assert any(
        "自洽" in r or "愣住" in r or "设问" in r for r in q.get("reasons") or []
    )
