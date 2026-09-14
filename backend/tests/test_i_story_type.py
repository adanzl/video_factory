"""I 类问倒收束 validate 与质检注册。"""

from __future__ import annotations

from app.services.daily_story.story_types import (
    append_type_body_validation_errors,
    parse_story_type_code,
    story_type_punchline_conflict,
    type_body_validation_enabled,
)
from app.services.daily_story.story_types.i.validate import append_i_body_errors


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


def test_review_prompt_i_stubborn_progression_not_dup():
    from app.services.daily_story.review import build_review_prompts

    story = {
        "story_type": "I",
        "setting": "卧室里，灿灿和昭昭因为作业吵起来",
        "conflict_core": "姐姐灵魂拷问「我爱学习你爱吗」，弟弟哑口无言",
        "dialogue": [
            {"speaker": "灿灿", "line": "还嘴硬？我不说了还不行？你真是的！"},
            {"speaker": "昭昭", "line": "哼！不说了呢！"},
            {"speaker": "灿灿", "line": "哼，看你还嘴硬呢！"},
        ],
    }
    system, _ = build_review_prompts("灵魂拷问", story)
    assert "I 类「问倒收束」" in system
    assert "还嘴硬" in system
    assert "递进" in system
    assert "别当重复报" in system


def test_collect_narration_meta_flags_yizhaozhidi():
    from app.services.gold_story.gold_chat.convert import (
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


def test_i_speechless_accepts_stammer_ellipsis():
    """省略号结巴算语塞（类型级，非单篇词表）。"""
    story = {
        "story_type": "I",
        "punchline_explain": "I类问倒收束",
        "dialogue": [
            {"speaker": "昭昭", "line": "我爱学习，你爱吗？"},
            {"speaker": "灿灿", "line": "我……我也爱学习。"},
            {"speaker": "昭昭", "line": "那你怎么不写作业？"},
            {"speaker": "灿灿", "line": "我……我待会写。"},
            {"speaker": "昭昭", "line": "哼，就知道看电视。"},
            {"speaker": "灿灿", "line": "我去写作业。"},
            {"speaker": "昭昭", "line": "看你还嘴硬！"},
            {"speaker": "灿灿", "line": "行了行了。"},
            {"speaker": "昭昭", "line": "一招制敌。"},
            {"speaker": "灿灿", "line": "哼。"},
        ],
    }
    errors: list[str] = []
    append_i_body_errors(story, errors)
    assert not any("语塞" in e for e in errors)


def test_i_rejects_speechless_before_parent_soul():
    """家长拷问后才算语塞；拷问前伪语塞硬拦。"""
    story = {
        "story_type": "I",
        "punchline_explain": "I类问倒收束",
        "dialogue": [
            {"speaker": "昭昭", "line": "我见人就说你低分！"},
            {"speaker": "灿灿", "line": "你嘴怎么这么快！"},
            {"speaker": "昭昭", "line": "我……我一时接不上，反正没错！"},
            {"speaker": "灿灿", "line": "你再宣传我跟妈妈告状！"},
            {"speaker": "妈妈", "line": "换你被到处说低分，你乐意吗？"},
            {"speaker": "昭昭", "line": "事实摆那儿，我宣传怎么了！"},
            {"speaker": "妈妈", "line": "不乐意就别乱说别人！"},
            {"speaker": "昭昭", "line": "我偏就不认！"},
            {"speaker": "妈妈", "line": "看你还嘴硬！"},
            {"speaker": "昭昭", "line": "哼！"},
        ],
    }
    errors: list[str] = []
    append_i_body_errors(story, errors)
    assert any("语塞须在灵魂拷问之后" in e for e in errors)


def test_i_patch_preserves_speechless_after_soul_vs_dedupe():
    """去重不得把拷问后语塞短句改回嘴硬争锋。"""
    from app.services.daily_story.story_types.i.patch import patch_i_body

    story = {
        "story_type": "I",
        "conflict_core": "昭昭到处宣扬灿灿数学58分，妈妈责备昭昭戳灿灿痛处",
        "punchline_explain": "I类问倒收束",
        "dialogue": [
            {"speaker": "昭昭", "line": "灿灿数学考了58分，我见人就说！"},
            {"speaker": "灿灿", "line": "你到处说我58分，同学都笑我！"},
            {"speaker": "昭昭", "line": "我……我一时接不上，反正我没错！"},
            {"speaker": "灿灿", "line": "你拿我分数当笑话讲，也太过分！"},
            {"speaker": "昭昭", "line": "跟我有啥关系，又不是我考的！"},
            {"speaker": "灿灿", "line": "你到处说还有理了？别再嚷！"},
            {"speaker": "昭昭", "line": "高分就该谢我，低分就怪分数！"},
            {"speaker": "灿灿", "line": "你再宣传一次，我跟妈妈告状！"},
            {"speaker": "妈妈", "line": "换你被到处说低分，你乐意吗？"},
            {"speaker": "昭昭", "line": "事实摆那儿，我宣传怎么了！"},
            {"speaker": "妈妈", "line": "不乐意就别乱说别人！"},
        ],
    }
    notes = patch_i_body(story)
    assert notes
    dlg = story["dialogue"]
    lines = [(d["speaker"], d["line"]) for d in dlg]
    soul = next(i for i, (s, l) in enumerate(lines) if s == "妈妈" and "乐意吗" in l)
    assert soul >= 0
    assert soul + 1 < len(lines)
    assert lines[soul + 1][0] == "昭昭"
    assert "我……" in lines[soul + 1][1]
    assert "事实摆" not in lines[soul + 1][1]
    assert lines[-1][0] == "妈妈"
    assert "不乐意" in lines[-1][1]
    # 拷问前不应再留伪语塞
    for sp, ln in lines[:soul]:
        if sp == "昭昭":
            assert "接不上" not in ln
            assert not (ln.startswith("我……") and "反正" in ln)


def test_repair_closing_intent_follows_seed_win_speaker():
    from app.services.daily_story.story_types.i.validate import (
        repair_closing_intent_from_seed_win,
        repair_conflict_core_from_seed_win,
    )

    seed = [
        {"speaker": "昭昭", "intent": "我爱学习，你爱吗？"},
        {"speaker": "灿灿", "intent": "我……我也爱。"},
        {"speaker": "昭昭", "intent": "（得意）一招制敌。"},
    ]
    fixed = repair_closing_intent_from_seed_win("灿灿得意总结一招制敌", seed)
    assert fixed.startswith("昭昭")
    conflict = repair_conflict_core_from_seed_win(
        "姐弟抢遥控器，姐姐用爱学习灵魂拷问瞬间制胜",
        seed,
    )
    assert "昭昭" in conflict
    assert "姐姐用" not in conflict


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
