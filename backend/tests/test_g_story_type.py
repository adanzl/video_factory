"""G 类嘴硬心软 validate 与注册。"""

from __future__ import annotations

from app.services.daily_story.story_types import parse_story_type_code
from app.services.daily_story.story_types.g.validate import append_g_body_errors


def test_g_validate_passes_canonical_shape():
    story = {
        "punchline_explain": "G类嘴硬心软，护短破防后暖收",
        "dialogue": [
            {"speaker": "灿灿", "line": "昭昭，手咋了？又跟人闹了？"},
            {"speaker": "昭昭", "line": "没……没有。"},
            {"speaker": "灿灿", "line": "还嘴硬！手都肿了，还充大侠呢！"},
            {"speaker": "昭昭", "line": "我……我不是。"},
            {"speaker": "灿灿", "line": "十个人围你一个，丢不丢人？"},
            {"speaker": "昭昭", "line": "我……我跑了。"},
            {"speaker": "灿灿", "line": "跑？你跑啥？怂包！"},
            {"speaker": "昭昭", "line": "我错了。"},
            {"speaker": "灿灿", "line": "记住个屁！谁还敢跟你玩？"},
            {"speaker": "昭昭", "line": "我不怕。"},
            {"speaker": "灿灿", "line": "你不怕？我怕！"},
            {"speaker": "昭昭", "line": "谁敢动你，我跟他拼命！"},
            {"speaker": "灿灿", "line": "你……你说啥？"},
            {"speaker": "昭昭", "line": "谁欺负你，我就跟谁拼命。"},
            {"speaker": "灿灿", "line": "就你这样？还拼命？"},
            {"speaker": "昭昭", "line": "认真的。"},
            {"speaker": "灿灿", "line": "行了，过来，我给你擦擦药。"},
            {"speaker": "昭昭", "line": "嗯。"},
            {"speaker": "灿灿", "line": "以后谁欺负你，我还得给你撑腰呢！"},
            {"speaker": "昭昭", "line": "那说好了！"},
        ],
    }
    errors: list[str] = []
    append_g_body_errors(story, errors)
    assert errors == []


def test_g_validate_rejects_c_boomerang_tail():
    story = {
        "punchline_explain": "G类嘴硬心软",
        "dialogue": [{"speaker": "昭昭", "line": f"句{i}"} for i in range(11)]
        + [
            {"speaker": "灿灿", "line": "你刚才说不能抢"},
            {"speaker": "昭昭", "line": "护姐！"},
            {"speaker": "灿灿", "line": "你说啥？"},
            {"speaker": "昭昭", "line": "认真的"},
            {"speaker": "灿灿", "line": "你自己说的你先选"},
        ],
    }
    # pad middle with pivot keywords
    for i, item in enumerate(story["dialogue"][5:8], start=5):
        item["line"] = "谁敢动你我拼命"
    errors: list[str] = []
    append_g_body_errors(story, errors)
    assert any("回旋镖" in e for e in errors)


def test_parse_g_from_punchline():
    assert parse_story_type_code(punchline="G类嘴硬心软，暖收") == "G"
