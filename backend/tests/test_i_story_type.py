"""I 类问倒收束 validate 与质检注册。"""

from __future__ import annotations

from app.services.daily_story.story_types import (
    STORY_TYPE_LINES,
    append_type_body_validation_errors,
    parse_story_type_code,
    story_type_punchline_conflict,
    story_type_tag,
    type_body_validation_enabled,
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
            {"speaker": "灿灿", "line": "哼，看你还嘴硬！"},
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


def test_i_body_validate_gated_when_not_quality_ready():
    story = {
        "story_type": "I",
        "punchline_explain": "I类问倒收束",
        "dialogue": [{"speaker": "灿灿", "line": f"我爱学习你爱吗{i}"} for i in range(10)],
    }
    assert not type_body_validation_enabled("I")
    errors: list[str] = []
    append_type_body_validation_errors(story, errors)
    assert not any("I类" in e for e in errors)


def test_parse_i_from_story_type():
    assert parse_story_type_code(story_type="I", punchline="C类：旧稿") == "I"


def test_story_type_punchline_conflict():
    story = {
        "story_type": "I",
        "punchline_explain": "C类：姐姐用双标灵魂拷问把弟弟问到哑口无言",
    }
    msg = story_type_punchline_conflict(story)
    assert msg is not None
    assert "story_type=I" in msg
    assert "punchline=C" in msg


def test_i_quality_profile_not_c_fallback():
    from app.services.daily_story.story_types.quality import quality_profile_for_code

    assert quality_profile_for_code("I").code == "I"


def test_i_quality_scores_story_69_shape():
    from app.services.daily_story.quality import score_daily_story

    story = {
        "theme": "灵魂拷问",
        "story_type": "I",
        "setting": "卧室里，灿灿和昭昭因为作业吵起来",
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
            {"speaker": "灿灿", "line": "少来这套！转移话题也没用。"},
            {"speaker": "昭昭", "line": "我哪有啊！我就是……就是怕你不理我。"},
            {
                "speaker": "灿灿",
                "line": "咱俩一个爸妈生的，凭啥我爱学习你不爱？你倒是说说看！",
            },
            {"speaker": "昭昭", "line": "我……我就是说不过你。"},
            {"speaker": "灿灿", "line": "让你学习你哭哭啼啼的，让你玩你咋不哭呢？"},
            {"speaker": "昭昭", "line": "你听不懂我说话，我也听不懂你！"},
            {"speaker": "灿灿", "line": "还嘴硬？我不说了还不行？你呀！"},
            {"speaker": "昭昭", "line": "我……我不说了，哼！哼！"},
            {"speaker": "灿灿", "line": "哼，看你还嘴硬！"},
            {"speaker": "昭昭", "line": "服了……我以后也爱学习，行了吧！哼"},
            {"speaker": "灿灿", "line": "这还差不多，说到做到，别光嘴上说啊。"},
        ],
    }
    q = score_daily_story(story, theme="灵魂拷问")
    assert q["structure_score"] >= 75, q
    from app.services.daily_story.prompts import dialogue_total_chars

    assert dialogue_total_chars(story) >= 240
    assert len(story["dialogue"]) >= 12
    assert "C规则轮次升级" not in "".join(q["reasons"])
    assert "回旋镖" not in "".join(q["reasons"])
    assert "收束形态未落位" not in "".join(q["reasons"])
    assert "拖尾" not in "".join(q["reasons"])
    assert "I末段缺赢家一招制敌" not in q["reasons"]


def test_collect_narration_meta_flags_yizhaozhidi():
    from app.services.daily_story.gold_story.gold_chat_convert import (
        collect_gold_chat_polish_issues,
    )
    from app.services.daily_story.review import collect_wording_issues

    story = {
        "story_type": "I",
        "dialogue": [
            {"speaker": "灿灿", "line": "我爱学习，你爱吗？"},
            {"speaker": "昭昭", "line": "我……我也爱吧。"},
            {"speaker": "灿灿", "line": "哼，一招制敌！你服不服？"},
        ],
    }
    wording = collect_wording_issues(story, type_code="I")
    polish = collect_gold_chat_polish_issues(story)
    assert any(it["kind"] == "旁白腔" for it in wording)
    assert any(it["kind"] == "旁白腔" for it in polish)
    assert wording[0]["lines"] == [3]
    assert "一招制敌" in wording[0]["desc"]


def test_i_humor_no_false_missing_win_on_trimmed_story():
    from app.services.daily_story.story_types.i.humor import collect_i_humor_issues

    lines = [
        "昭昭，别跟我讲道理。我就问你，我爱学习，你爱吗？",
        "我……我也爱吧。",
        "那你怎么老不写作业？",
        "可我更爱你呀！",
        "少来这套！凭啥我爱学习你不爱？",
        "我……我说不过你。",
        "让你学习你哭哭啼啼的，让你玩你咋不哭呢？",
        "我……我不说了，别说了还不行？",
        "哼，看你还嘴硬！",
        "服了……我以后也爱学习，行了吧！",
        "这还差不多，说到做到，别光嘴上说啊。",
    ]
    assert "I末段缺赢家一招制敌" not in collect_i_humor_issues(lines)


def test_attach_normalizes_punchline_on_conflict():
    from app.services.daily_story.quality import attach_daily_story_quality

    story = {
        "story_type": "I",
        "conflict_core": "灵魂拷问",
        "punchline_explain": "C类：旧稿解释",
        "discovery_opening": [
            {"speaker": "灿灿", "line": "我爱学习，你爱吗？"},
            {"speaker": "昭昭", "line": "我……我也爱吧。"},
        ],
        "dialogue": [
            {"speaker": "灿灿", "line": "我爱学习，你爱吗？"},
            {"speaker": "昭昭", "line": "我……我也爱吧。"},
            {"speaker": "灿灿", "line": "那你怎么老不写作业？"},
            {"speaker": "昭昭", "line": "可我更爱你呀！"},
            {"speaker": "灿灿", "line": "少来！凭啥我爱学习你不爱？"},
            {"speaker": "昭昭", "line": "我……我说不过你。"},
            {"speaker": "灿灿", "line": "让你学习你哭哭啼啼，让你玩你咋不哭？"},
            {"speaker": "昭昭", "line": "我不说了，我看窗外还不行？"},
            {"speaker": "灿灿", "line": "哼，看你还嘴硬！"},
            {"speaker": "昭昭", "line": "服了……我以后也爱学习。"},
        ],
    }
    attach_daily_story_quality(story, theme="灵魂拷问", finalize=False)
    assert story["punchline_explain"].startswith("I类问倒收束")
