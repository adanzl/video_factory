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


def test_h_quality_profile_not_c_fallback():
    from app.services.daily_story.story_types.quality import quality_profile_for_code

    assert quality_profile_for_code("H").code == "H"


def test_h_quality_scores_mediation_story():
    from app.services.daily_story.quality import score_daily_story

    story = {
        "theme": "画作争夺战",
        "story_type": "H",
        "setting": "客厅，地上散落画纸和彩笔",
        "conflict_core": "抢看秘密画互毁",
        "punchline_explain": (
            "H类：妈妈作为第三方调解，先问谁先动手，再定责劝和，"
            "最终姐弟拉手和好，齐声承诺不打了，妈妈拿碘伏收场。"
        ),
        "discovery_opening": [
            {"speaker": "灿灿", "line": "昭昭，你趴地上画啥呢？让我瞅瞅！"},
            {"speaker": "昭昭", "line": "不行！这是我的秘密，你不能看！"},
        ],
        "dialogue": [
            {"speaker": "灿灿", "line": "昭昭，你趴地上画啥呢？让我瞅瞅！"},
            {"speaker": "昭昭", "line": "不行！这是我的秘密，你不能看！"},
            {"speaker": "灿灿", "line": "哼，小气鬼！我偏要看！"},
            {"speaker": "昭昭", "line": "你走开！你把我画抢坏了！再抢我打你了！"},
            {"speaker": "灿灿", "line": "你敢！哎呀！你推我！"},
            {"speaker": "昭昭", "line": "谁让你抢的！我也弄坏你的画！"},
            {"speaker": "灿灿", "line": "你赔！我额头都蹭破了！"},
            {"speaker": "昭昭", "line": "呜……对不起嘛，我不是故意的。"},
            {"speaker": "灿灿", "line": "家规就是谁先动手谁道歉！你推我，你先道歉！哼，我不原谅！"},
            {"speaker": "昭昭", "line": "姐姐，我真的错了，你别不理我。"},
            {"speaker": "灿灿", "line": "道歉也没用！我画了好久呢！"},
            {"speaker": "妈妈", "line": "别打了！谁先动手的？"},
            {"speaker": "昭昭", "line": "我……我先推的，姐姐对不起！"},
            {"speaker": "妈妈", "line": "昭昭先推不对，灿灿你也别抢画。画能重画，额头先处理。"},
            {"speaker": "灿灿", "line": "哼……那拉手吧。"},
            {"speaker": "妈妈", "line": "以后还打不打架？"},
            {"speaker": "昭昭", "line": "不打了！"},
            {"speaker": "灿灿", "line": "不打了！这还差不多。"},
            {"speaker": "妈妈", "line": "我去拿碘伏，你额头上还没涂呢。"},
            {"speaker": "灿灿", "line": "嗯，谢谢妈妈。"},
        ],
    }
    q = score_daily_story(story, theme="画作争夺战")
    assert q["structure_score"] >= 70
    assert 6 <= q["humor_regex_points"] <= 12
    assert "很好笑" not in q["reasons"]
    assert "C规则轮次升级" not in "".join(q["reasons"])
    assert "回旋镖" not in "".join(q["reasons"])
    assert "笑点解析缺类型" not in q["reasons"]
