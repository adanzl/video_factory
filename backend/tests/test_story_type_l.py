"""L 类退让点破：校验/观感 smoke（注册见 fl_extended）。"""

from app.services.gold_story.types import (
    allowed_structure_types,
    validate_mechanism_structure_pair,
)
from app.services.daily_story.quality import attach_daily_story_quality
from app.services.daily_story.story_types import patch_type_body
from app.services.daily_story.story_types.l.validate import append_l_body_errors


def test_m2_allows_l():
    assert "L" in allowed_structure_types("M2")
    validate_mechanism_structure_pair("M2", "L")


def test_l_body_validate_and_structure_score():
    story = {
        "story_type": "L",
        "scene_title": "公平的陷阱",
        "setting": "客厅餐桌",
        "conflict_core": "公平的陷阱：成人催让渡，孩子拒领点破偏心",
        "key": "退让点破",
        "punchline_explain": "L类：拒领点破表演公平，成人语塞",
        "discovery_opening": [
            {"speaker": "灿灿", "line": "桌上这瓶，该我喝。"},
            {"speaker": "昭昭", "line": "我也要，不能总让。"},
        ],
        "dialogue": [
            {"speaker": "灿灿", "line": "这瓶该给我，我都喝过一瓶了。"},
            {"speaker": "昭昭", "line": "我也要喝，不能每次都让。"},
            {"speaker": "妈妈", "line": "给她。"},
            {"speaker": "昭昭", "line": "好吧，给你。"},
            {"speaker": "灿灿", "line": "我不想喝了。"},
            {"speaker": "昭昭", "line": "你不是刚要吗？"},
            {"speaker": "灿灿", "line": "你们喝吧。"},
            {"speaker": "昭昭", "line": "这哪门子公平？"},
            {"speaker": "灿灿", "line": "我不喝，你们别拿公平压我。"},
            {"speaker": "昭昭", "line": "原来一直向着她。"},
            {"speaker": "灿灿", "line": "偏心被揭穿了吧。"},
            {"speaker": "昭昭", "line": "行，这回算你赢。"},
        ],
    }
    # mom 2 lines → hard error
    story_two_mom = {
        **story,
        "dialogue": story["dialogue"]
        + [{"speaker": "妈妈", "line": "那……先放着吧。"}],
    }
    errors: list[str] = []
    append_l_body_errors(story_two_mom, errors)
    assert any("妈妈台词" in e for e in errors)

    errors2: list[str] = []
    append_l_body_errors(story, errors2)
    assert errors2 == []

    notes = patch_type_body(story)
    assert isinstance(notes, list)

    attach_daily_story_quality(story, theme="公平的陷阱")
    q = story["quality"]
    assert q["structure_score"] >= 60
    assert any(
        "点破" in r or "催让" in r or "拒收" in r for r in q.get("reasons") or []
    )
