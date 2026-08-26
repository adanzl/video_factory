"""F 类互呛加码 validate 与注册。"""

from __future__ import annotations

from app.services.daily_story.story_types import (
    STORY_TYPE_LINES,
    parse_story_type_code,
    story_type_tag,
)
from app.services.daily_story.story_types.f.validate import append_f_body_errors


def test_f_registered():
    assert "F" in STORY_TYPE_LINES
    assert STORY_TYPE_LINES["F"].label == "互呛加码"
    assert story_type_tag("F") == "F类互呛加码"


def test_f_validate_passes_m3_external_interrupt():
    story = {
        "story_type": "F",
        "punchline_explain": "F类：互怼升级发现偷拍后尴尬收束",
        "dialogue": [
            {"speaker": "灿灿", "line": "你这样说我还觉得你很讨厌了呢！"},
            {"speaker": "昭昭", "line": "那你还很讨厌了呢！"},
            {"speaker": "灿灿", "line": "你再说一遍试试啊！"},
            {"speaker": "昭昭", "line": "试试就试试嘛！"},
            {"speaker": "灿灿", "line": "吼什么吼吧！"},
            {"speaker": "昭昭", "line": "那你还吼了呢！"},
            {"speaker": "灿灿", "line": "啊啊啊了啊！"},
            {"speaker": "昭昭", "line": "啊什么了啊！"},
            {"speaker": "灿灿", "line": "姐，有人拍我们呢！"},
            {"speaker": "昭昭", "line": "啊？快闭嘴！"},
            {"speaker": "灿灿", "line": "别吵了，咱们先看看谁在拍！"},
            {"speaker": "昭昭", "line": "好，先别丢人，笑一个！"},
            {"speaker": "灿灿", "line": "嗯，假装刚才在闹着玩！"},
            {"speaker": "昭昭", "line": "茄子！"},
            {"speaker": "灿灿", "line": "茄子！"},
            {"speaker": "昭昭", "line": "这样他们就不尴尬了。"},
            {"speaker": "灿灿", "line": "对，别让人看笑话。"},
            {"speaker": "昭昭", "line": "回头再跟你算账！"},
        ],
    }
    errors: list[str] = []
    append_f_body_errors(story, errors)
    assert errors == []


def test_f_validate_rejects_b_alliance_tail():
    story = {
        "story_type": "F",
        "punchline_explain": "F类互呛加码",
        "dialogue": [
            {"speaker": "灿灿", "line": "你再说一遍试试！"},
            {"speaker": "昭昭", "line": "试试就试试！"},
            {"speaker": "灿灿", "line": "你还讨厌呢！"},
            {"speaker": "昭昭", "line": "那你还讨厌呢！"},
            {"speaker": "灿灿", "line": "吼什么吼！"},
            {"speaker": "昭昭", "line": "那你还吼呢！"},
            {"speaker": "灿灿", "line": "啊啊啊！"},
            {"speaker": "昭昭", "line": "啊什么啊！"},
            {"speaker": "灿灿", "line": "不跟你玩了！"},
            {"speaker": "昭昭", "line": "咱们永远是一伙的！"},
            {"speaker": "灿灿", "line": "谁欺负你就跟谁急！"},
            {"speaker": "昭昭", "line": "一致对外！"},
        ],
    }
    errors: list[str] = []
    append_f_body_errors(story, errors)
    assert any("B" in e for e in errors)


def test_parse_f_from_punchline():
    assert parse_story_type_code(punchline="F类：互呛加码") == "F"
