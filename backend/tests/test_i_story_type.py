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


def test_i_validate_accepts_mirror_why_accusation_as_soul_question():
    """「为什么说/骂」和「算什么道理」是价值反问，不依赖「凭啥」等单篇词。"""
    story = {
        "story_type": "I",
        "punchline_explain": "I类问倒收束",
        "dialogue": [
            {"speaker": "妈妈", "line": "你看你，吃个早餐都能把衣服弄成这样，傻不傻啊！"},
            {"speaker": "昭昭", "line": "你为什么要大声骂我？就吃早餐的时候。"},
            {"speaker": "昭昭", "line": "你骂我傻，我不高兴，我那么大声干嘛？"},
            {"speaker": "妈妈", "line": "好，对不起，妈妈不该大声。那咱讲道理行吗？"},
            {"speaker": "妈妈", "line": "你说，你是不是把衣服弄脏了？弄脏的是谁的衣服？"},
            {"speaker": "昭昭", "line": "是我弄脏的，弄脏的是我自己的衣服呀。"},
            {"speaker": "昭昭", "line": "我没帮你弄干净，因为我疼你啊。"},
            {"speaker": "妈妈", "line": "你疼我，我还骂你、说你傻，这算怎么回事？"},
            {"speaker": "昭昭", "line": "弄了衣服就是傻吗？那你为什么说我傻呢？"},
            {"speaker": "昭昭", "line": "你说我是不小心的，那不小心就是傻吗？"},
            {"speaker": "妈妈", "line": "对不起，是妈妈错了，不该说你傻。"},
            {"speaker": "昭昭", "line": "哼，我还没消气呢。"},
        ],
    }
    errors: list[str] = []
    append_i_body_errors(story, errors)
    assert errors == []


def test_i_ground_quote_frames_removes_unsupported_parent_quote():
    from app.services.daily_story.story_types.i.patch import (
        patch_i_ground_quote_frames,
    )

    story = {
        "dialogue": [
            {"speaker": "妈妈", "line": "吃个早餐都把衣服弄脏，傻不傻啊！"},
            {
                "speaker": "昭昭",
                "line": "你说我是不小心的，那不小心就是傻吗？",
            },
            {"speaker": "昭昭", "line": "你上次也这么说我，光骂我傻。"},
        ]
    }
    notes = patch_i_ground_quote_frames(story)
    assert notes
    assert story["dialogue"][1]["line"].startswith("我是不小心的")
    assert story["dialogue"][2]["line"].startswith("你刚才也这么说我")


def test_i_duplicate_question_group_gets_new_demand():
    from app.services.daily_story.story_types.i.patch import (
        patch_i_rewrite_duplicate_question_groups,
    )

    story = {
        "dialogue": [
            {"speaker": "妈妈", "line": "衣服又弄脏了，傻不傻啊！"},
            {"speaker": "昭昭", "line": "你为什么要大声骂我？就吃早餐的时候。"},
            {
                "speaker": "昭昭",
                "line": "你骂我傻，我不高兴，我那么大声干嘛？",
            },
        ]
    }
    notes = patch_i_rewrite_duplicate_question_groups(story)
    assert notes
    assert story["dialogue"][2]["line"] == "你骂我傻，这总得有个说法吧？"


def test_i_softens_parent_win_after_apology():
    from app.services.daily_story.story_types.i.patch import (
        patch_i_soften_win_after_concession,
    )

    story = {
        "dialogue": [
            {"speaker": "妈妈", "line": "衣服又弄脏了，傻不傻啊！"},
            {"speaker": "昭昭", "line": "你疼我为什么还骂我傻？"},
            {
                "speaker": "妈妈",
                "line": "你疼我，我还骂你、说你傻，这算怎么回事？",
            },
            {"speaker": "妈妈", "line": "对不起，是妈妈错了，不该说你傻。"},
            {"speaker": "昭昭", "line": "哼，我还没消气呢。"},
            {"speaker": "妈妈", "line": "看你还嘴硬！"},
        ]
    }
    notes = patch_i_soften_win_after_concession(story)
    assert notes
    assert story["dialogue"][-1]["line"] == "还没消气？那妈妈再好好跟你说。"


def test_i_repairs_mirror_parent_question_pronouns():
    from app.services.daily_story.story_types.i.patch import (
        patch_i_repair_mirror_parent_question,
    )

    story = {
        "dialogue": [
            {"speaker": "妈妈", "line": "衣服又弄脏了，傻不傻啊！"},
            {"speaker": "昭昭", "line": "你疼我为什么还骂我傻？"},
            {
                "speaker": "妈妈",
                "line": "你疼我，我还骂你、说你傻，那你说说为什么？",
            },
            {"speaker": "昭昭", "line": "要是我真是不小心的，这算怎么回事？"},
        ]
    }
    notes = patch_i_repair_mirror_parent_question(story)
    assert notes
    assert story["dialogue"][2]["line"] == (
        "你疼妈妈，妈妈为什么还大声骂你、说你傻？"
    )


def test_i_strips_self_action_narration_and_acknowledges_apology():
    from app.services.daily_story.story_types.i.patch import (
        patch_i_acknowledge_apology,
        patch_i_strip_self_action_narration,
    )

    story = {
        "dialogue": [
            {"speaker": "昭昭", "line": "我正低头喝粥，你就骂我傻，我错哪儿了？"},
            {"speaker": "妈妈", "line": "对不起，是妈妈错了，不该说你傻。"},
            {"speaker": "昭昭", "line": "哼，你道歉我也还没消气呢。"},
        ]
    }
    assert patch_i_strip_self_action_narration(story)
    assert story["dialogue"][0]["line"] == "你就骂我傻，我错哪儿了？"
    assert patch_i_acknowledge_apology(story)
    assert story["dialogue"][2]["line"] == (
        "妈妈道歉我听见了，可我没那么快消气。"
    )


def test_i_parent_mirror_question_uses_contract_without_duplicate_insert():
    from app.services.daily_story.story_types.i.patch import (
        patch_i_ensure_parent_soul_from_beat,
    )

    line = "你疼我，我还骂你、说你傻，这算怎么回事？"
    story = {
        "story_type": "I",
        "dialogue": [
            {"speaker": "妈妈", "line": "衣服又弄脏了。"},
            {"speaker": "昭昭", "line": "你为什么大声骂我？"},
            {"speaker": "妈妈", "line": "你先听我说。"},
            {"speaker": "昭昭", "line": "我在听。"},
            {"speaker": "妈妈", "line": line},
            {"speaker": "昭昭", "line": "我还没消气。"},
        ],
        "gold_beat_chain": [
            {
                "speaker": "妈妈",
                "intent": "愣住后追问：疼我为什么大声骂我、说我傻",
            }
        ],
    }
    before = [dict(x) for x in story["dialogue"]]
    notes = patch_i_ensure_parent_soul_from_beat(story)
    assert notes == []
    assert story["dialogue"] == before


def test_i_validate_accepts_opponent_apology_as_defeat():
    """对手被问住后当场认错，属于败北；末段不必再喊「一招制敌」口号。"""
    story = {
        "story_type": "I",
        "punchline_explain": "I类问倒收束",
        "dialogue": [
            {"speaker": "妈妈", "line": "衣服又弄这么脏，吃个早餐都不省心，真是傻！"},
            {"speaker": "昭昭", "line": "吃早餐的时候你干嘛那么大声骂我，还说我傻？"},
            {"speaker": "妈妈", "line": "我说你两句你还撅嘴，衣服脏成这样还有理了？"},
            {"speaker": "灿灿", "line": "这话我可有点不信，你可得说清楚才行。"},
            {"speaker": "昭昭", "line": "衣服是我自己弄脏的，可那是因为我疼你啊。"},
            {"speaker": "妈妈", "line": "疼我你还大声骂我，还说我傻，这道理讲不通吧。"},
            {"speaker": "灿灿", "line": "我怎么听着这么玄乎，越琢磨越觉得悬。"},
            {"speaker": "昭昭", "line": "弄了衣服就是傻？那你刚才干嘛还骂我傻？"},
            {"speaker": "昭昭", "line": "你自己说是不小心，那不小心跟傻有什么关系？"},
            {"speaker": "灿灿", "line": "行，那我就在旁边看着你把这事说圆。"},
            {"speaker": "妈妈", "line": "对不起，是妈妈不该说你傻，妈妈向你道歉。"},
            {"speaker": "昭昭", "line": "哼，我还没消气呢！"},
        ],
    }
    errors: list[str] = []
    append_i_body_errors(story, errors)
    assert errors == []


def test_i_line_max_keeps_trailing_meaning_when_one_char_over():
    """只超 1 字时删前文虚词，不能把句末「傻」一起截掉。"""
    from app.services.daily_story.dialogue_text import truncate_overlong_line

    line = "你怎么又把衣服弄这么脏，吃个早餐都不省心，真是傻！"
    out = truncate_overlong_line(line, max_chars=24)
    assert len(out) <= 24
    assert out.endswith("真是傻！")


def test_i_line_max_prefers_meaningful_last_clause():
    from app.services.daily_story.dialogue_text import truncate_overlong_line

    line = "你从早上到现在一直把衣服弄得这么脏，吃个早餐都不省心，真是傻！"
    out = truncate_overlong_line(line, max_chars=24)
    assert len(out) <= 24
    assert out.endswith("真是傻！")


def test_i_close_ignores_apology_before_soul_question():
    """开头的哄人道歉不是败北；灵魂拷问后的认错才是收束。"""
    from app.services.daily_story.story_types.i.validate import (
        find_i_close_index,
    )

    lines = [
        "你怎么又把衣服弄这么脏，真是傻！",
        "你干嘛那么大声骂我，还说我傻？",
        "对不起，妈妈不该大声，那咱讲道理行吗？",
        "你说的是你自己吧，弄脏衣服就是傻吗？",
        "你自己说是不小心，那为什么还说我傻？",
        "对不起，是妈妈错了，不该说你傻。",
        "哼，我还没消气呢。",
    ]
    assert find_i_close_index(lines) == 5

    no_soul = lines[:3]
    assert find_i_close_index(no_soul) == -1


def test_i_trim_keeps_apology_close_without_forced_win():
    """认错就是收束，不能再用低分梗「制敌」句覆盖孩子台词。"""
    from app.services.daily_story.story_types.i.patch import (
        patch_i_trim_trailing_subplot,
    )

    story = {
        "story_type": "I",
        "punchline_explain": "I类问倒收束",
        "dialogue": [
            {"speaker": "妈妈", "line": "衣服又弄这么脏，真是傻！"},
            {"speaker": "昭昭", "line": "吃早餐的时候你干嘛那么大声骂我？"},
            {"speaker": "妈妈", "line": "我说你两句你还撅嘴，还有理了？"},
            {"speaker": "灿灿", "line": "这话我可有点不信，你可得说清楚。"},
            {"speaker": "昭昭", "line": "衣服是我自己弄脏的，可那是因为我疼你啊。"},
            {"speaker": "妈妈", "line": "疼我你还大声骂我，这道理讲不通吧。"},
            {"speaker": "灿灿", "line": "我怎么听着这么玄乎，越琢磨越觉得悬。"},
            {"speaker": "昭昭", "line": "弄了衣服就是傻？那你干嘛还骂我傻？"},
            {"speaker": "昭昭", "line": "你自己说是不小心，那不小心跟傻有什么关系？"},
            {"speaker": "妈妈", "line": "对不起，是妈妈不该说你傻，妈妈向你道歉。"},
            {"speaker": "昭昭", "line": "小嘴一撇，嘟囔一句听不清的话，神情还没消气。"},
        ],
    }
    patch_i_trim_trailing_subplot(story)
    lines = [str(item.get("line") or "") for item in story["dialogue"]]
    assert "低分" not in "".join(lines)
    assert "对不起" in lines[-2]
    assert lines[-1].startswith("小嘴一撇")


def test_i_conceding_soul_winner_gets_no_win_line():
    """拷问方已认错时不再补「制敌」：多补一句会让家长台词超预算。"""
    from app.services.daily_story.story_types.i.patch import _ensure_oral_win_at_end

    story = {
        "story_type": "I",
        "dialogue": [
            {"speaker": "昭昭", "line": "那你为什么说我傻呢？"},
            {"speaker": "妈妈", "line": "对不起，是妈妈不对，不该说你傻。"},
        ],
    }
    before = len(story["dialogue"])
    notes = _ensure_oral_win_at_end(story, "妈妈")
    assert len(story["dialogue"]) == before
    assert not notes


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
    assert "嘴硬" in lines[-1][1]
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


def test_ground_opening_quote_assertion_turns_rhetorical_repeat_into_claim():
    from app.services.daily_story.story_types.i.patch import (
        patch_i_ground_opening_quote_assertion,
    )

    story = {
        "gold_beat_chain": [
            {
                "beat": 1,
                "speaker": "妈妈",
                "intent": "大声骂昭昭弄脏衣服，并说“傻”",
            },
            {"beat": 2, "speaker": "昭昭", "intent": "反问为什么骂自己"},
        ],
        "dialogue": [
            {"speaker": "妈妈", "line": "你看你，衣服弄成这样，傻不傻啊！"},
            {"speaker": "昭昭", "line": "你为什么要骂我？"},
        ],
    }
    notes = patch_i_ground_opening_quote_assertion(story)
    assert notes
    assert "你可真傻" in story["dialogue"][0]["line"]
    assert "傻不傻" not in story["dialogue"][0]["line"]
    assert patch_i_ground_opening_quote_assertion(story) == []


def test_acknowledge_apology_names_parent_and_does_not_repeat_words():
    from app.services.daily_story.story_types.i.patch import (
        patch_i_acknowledge_apology,
    )

    story = {
        "dialogue": [
            {"speaker": "妈妈", "line": "对不起，是妈妈错了，不该说你傻。"},
            {"speaker": "昭昭", "line": "你说了对不起，可我心里还没消气呢。"},
        ],
    }
    notes = patch_i_acknowledge_apology(story)
    assert notes
    assert story["dialogue"][1]["line"] == "妈妈道歉我听见了，可我没那么快消气。"


def test_parent_acknowledges_child_feeling_before_fact_question():
    from app.services.daily_story.story_types.i.patch import (
        patch_i_parent_acknowledge_child_feeling,
    )

    story = {
        "dialogue": [
            {"speaker": "昭昭", "line": "你骂我傻，我不高兴。"},
            {"speaker": "妈妈", "line": "衣服是不是你弄脏的？"},
        ],
    }
    notes = patch_i_parent_acknowledge_child_feeling(story)
    assert notes
    assert story["dialogue"][1]["line"].startswith("妈妈知道你不高兴，")


def test_oral_win_skipped_after_parent_apology():
    """家长已经认错：不再补「看你还嘴硬」，否则是冲着道歉继续训人。

    #144 实测：昭昭的「还没消气」收束被替换成固定制敌句，终检判接不上，
    修稿又把收束改成完全满意，未消气的反差余味全丢。
    """
    from app.services.daily_story.story_types.i.patch import _ensure_oral_win_at_end

    story = {
        "dialogue": [
            {"speaker": "妈妈", "line": "昭昭你看你衣服脏成这样，你可真傻！"},
            {"speaker": "昭昭", "line": "弄了衣服是傻？那你为什么要说傻呢？"},
            {"speaker": "妈妈", "line": "对不起昭昭，是妈妈不对，妈妈不该说你傻。"},
            {
                "speaker": "昭昭",
                "line": "妈妈现在说对不起，可我心里那根刺还没拔出来。",
            },
        ]
    }
    notes = _ensure_oral_win_at_end(story, "昭昭")
    assert notes == []
    assert story["dialogue"][-1]["line"] == "妈妈现在说对不起，可我心里那根刺还没拔出来。"


def test_oral_win_keeps_existing_stubborn_closing():
    """末句已经是嘴硬/赌气收场时，不再用固定句覆盖。"""
    from app.services.daily_story.story_types.i.patch import _ensure_oral_win_at_end

    story = {
        "dialogue": [
            {"speaker": "妈妈", "line": "你到底写不写作业？"},
            {"speaker": "昭昭", "line": "我就是不服，你能拿我怎么办？"},
        ]
    }
    notes = _ensure_oral_win_at_end(story, "昭昭")
    assert notes == []
    assert story["dialogue"][-1]["line"] == "我就是不服，你能拿我怎么办？"


def test_patch_i_body_keeps_unresolved_sulk_closing():
    """整条 I 类本地修稿链不得把「没消气」的收束改掉。"""
    from app.services.daily_story.story_types.i.patch import patch_i_body

    story = {
        "story_type": "I",
        "setting": "餐桌",
        "conflict_core": "妈妈骂昭昭弄脏衣服还说傻，昭昭用疼你和傻反问把妈妈问住",
        "dialogue": [
            {"speaker": "妈妈", "line": "昭昭你看你衣服脏成这样，你可真傻！"},
            {"speaker": "昭昭", "line": "妈你干嘛这么大声骂我，我哪里傻了？"},
            {"speaker": "灿灿", "line": "你慢慢说，别急，先听昭昭把话讲完。"},
            {"speaker": "昭昭", "line": "姐姐让我慢慢说，妈你先别急，我听着。"},
            {"speaker": "妈妈", "line": "你是不是弄脏了衣服，弄脏谁的衣服，帮妈妈弄干净。"},
            {"speaker": "昭昭", "line": "衣服是我弄脏的，我自己弄干净，因为疼妈妈。"},
            {"speaker": "灿灿", "line": "我在这儿看着都替你俩累，先歇会儿再吵。"},
            {"speaker": "妈妈", "line": "你疼妈妈，妈妈还怪你不小心、说你傻，这算什么？"},
            {"speaker": "昭昭", "line": "弄了衣服是傻？你说不小心，那你为什么要说傻呢？"},
            {"speaker": "灿灿", "line": "昭昭，你先说，我在旁边听着，不插嘴。"},
            {"speaker": "妈妈", "line": "对不起昭昭，是妈妈不对，妈妈不该说你傻。"},
            {
                "speaker": "昭昭",
                "line": "妈妈现在说对不起，可我心里那根刺还没拔出来。",
            },
        ],
    }
    patch_i_body(story)
    assert story["dialogue"][-1]["line"] == "妈妈现在说对不起，可我心里那根刺还没拔出来。"
