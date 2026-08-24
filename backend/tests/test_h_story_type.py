"""H 类第三方化解 validate 与注册。"""

from __future__ import annotations

from app.services.daily_story.story_types import (
    STORY_TYPE_LINES,
    parse_story_type_code,
    story_type_tag,
)
from app.services.daily_story.story_types.h.validate import append_h_body_errors


def test_h_registered():
    assert "H" in STORY_TYPE_LINES
    assert STORY_TYPE_LINES["H"].label == "第三方化解"
    assert story_type_tag("H") == "H类第三方化解"
    assert STORY_TYPE_LINES["H"].quality_ready is False


def test_h_validate_passes_mediation_shape():
    story = {
        "punchline_explain": "H类第三方化解，妈妈定责劝和",
        "dialogue": [
            {"speaker": "灿灿", "line": "你干嘛弄坏我的画！"},
            {"speaker": "昭昭", "line": "不给你看！你抢！"},
            {"speaker": "灿灿", "line": "我偏要看！"},
            {"speaker": "昭昭", "line": "你推我！我打你了！"},
            {"speaker": "灿灿", "line": "你敢！哎呀！"},
            {"speaker": "昭昭", "line": "对不起……"},
            {"speaker": "灿灿", "line": "哼，不原谅你！"},
            {"speaker": "妈妈", "line": "别打了！都错了！"},
            {"speaker": "妈妈", "line": "弟弟都道歉了，要互相原谅。"},
            {"speaker": "灿灿", "line": "好吧……"},
            {"speaker": "昭昭", "line": "我们和好吧。"},
            {"speaker": "灿灿", "line": "拉手，以后不打了！"},
            {"speaker": "昭昭", "line": "嗯，不打了。"},
        ],
    }
    errors: list[str] = []
    append_h_body_errors(story, errors)
    assert errors == []


def test_h_validate_rejects_no_mom():
    story = {
        "punchline_explain": "H类第三方化解",
        "dialogue": [{"speaker": "灿灿", "line": f"互毁句{i}"} for i in range(12)],
    }
    errors: list[str] = []
    append_h_body_errors(story, errors)
    assert any("妈妈" in e for e in errors)


def test_parse_h_from_punchline():
    assert parse_story_type_code(punchline="H类第三方化解，仪式性和好") == "H"
