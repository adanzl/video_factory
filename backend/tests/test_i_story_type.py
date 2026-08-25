"""I 类问倒收束 validate 与质检注册。"""

from __future__ import annotations

from app.services.daily_story.story_types import (
    STORY_TYPE_LINES,
    parse_story_type_code,
    story_type_tag,
)
from app.services.daily_story.story_types.i.validate import append_i_body_errors


def test_i_registered():
    assert "I" in STORY_TYPE_LINES
    assert STORY_TYPE_LINES["I"].label == "问倒收束"
    assert story_type_tag("I") == "I类问倒收束"
    assert STORY_TYPE_LINES["I"].quality_ready is False


def test_i_validate_passes_soul_question_shape():
    story = {
        "story_type": "I",
        "punchline_explain": "I类问倒收束，灵魂拷问问倒弟弟",
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
        ],
    }
    errors: list[str] = []
    append_i_body_errors(story, errors)
    assert errors == []


def test_i_validate_rejects_missing_speechless():
    story = {
        "story_type": "I",
        "punchline_explain": "I类问倒收束",
        "dialogue": [{"speaker": "灿灿", "line": f"我爱学习你爱吗{i}"} for i in range(10)],
    }
    errors: list[str] = []
    append_i_body_errors(story, errors)
    assert any("语塞" in e for e in errors)


def test_parse_i_from_story_type():
    assert parse_story_type_code(story_type="I", punchline="C类：旧稿") == "I"


def test_i_quality_profile_not_c_fallback():
    from app.services.daily_story.story_types.quality import quality_profile_for_code

    assert quality_profile_for_code("I").code == "I"


def test_i_quality_scores_story_69_shape():
    from app.services.daily_story.quality import score_daily_story

    story = {
        "theme": "灵魂拷问",
        "story_type": "I",
        "setting": "车内，妈妈开车，灿灿和昭昭坐在后座",
        "conflict_core": "姐姐灵魂拷问「我爱学习你爱吗」，弟弟哑口无言",
        "punchline_explain": (
            "I类问倒收束：姐姐用双标灵魂拷问把弟弟问到哑口无言，一招制敌收场。"
        ),
        "discovery_opening": [
            {
                "speaker": "灿灿",
                "line": "昭昭，别跟我讲道理。我就问你，我爱学习，你爱吗？",
            },
            {"speaker": "昭昭", "line": "我……我也爱吧。"},
        ],
        "dialogue": [
            {
                "speaker": "灿灿",
                "line": "昭昭，别跟我讲道理。我就问你，我爱学习，你爱吗？",
            },
            {"speaker": "昭昭", "line": "我……我也爱吧。"},
            {"speaker": "灿灿", "line": "那你怎么老不写作业？每次都要妈妈催！"},
            {"speaker": "昭昭", "line": "可我更爱你呀！姐姐，我最喜欢你了！"},
            {"speaker": "灿灿", "line": "少来这套！咱俩一个爸妈生的，凭啥我爱学习你不爱？"},
            {"speaker": "昭昭", "line": "我……我说不过你。"},
            {"speaker": "灿灿", "line": "让你学习你哭哭啼啼的，让你玩你咋不哭呢？"},
            {"speaker": "昭昭", "line": "我……我不说了，我看窗外还不行？"},
            {"speaker": "灿灿", "line": "哼，一招制敌！你服不服？"},
            {"speaker": "昭昭", "line": "服了……我以后也爱学习，行了吧！"},
            {"speaker": "灿灿", "line": "这还差不多，说到做到，别光嘴上说啊。"},
            {"speaker": "昭昭", "line": "嗯嗯，姐姐你监督我，我一定写，不偷懒。"},
            {"speaker": "灿灿", "line": "行，以后我写作业，你也得写，这样才公平吧？"},
            {"speaker": "昭昭", "line": "公平……姐姐你说啥就是啥，我听你的。"},
        ],
    }
    q = score_daily_story(story, theme="灵魂拷问")
    assert q["structure_score"] >= 70, q
    assert "C规则轮次升级" not in "".join(q["reasons"])
    assert "回旋镖" not in "".join(q["reasons"])
    assert "收束形态未落位" not in "".join(q["reasons"])
