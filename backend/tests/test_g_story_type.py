"""G 类嘴硬心软 validate 与注册。"""

from __future__ import annotations

from app.services.daily_story.story_types import parse_story_type_code
from app.services.daily_story.story_types.g.validate import (
    RE_F_STALE,
    RE_PIVOT,
    append_g_body_errors,
)


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


def test_g_pivot_not_dismissive_buyongniguan():
    """「不用你管」不得单独充当 pivot。"""
    assert not RE_PIVOT.search("不用你管！你管得着吗？")
    assert RE_PIVOT.search("你去哪？我怕你一个人走")


def test_g_validate_passes_coincidence_soft_close():
    """同路巧合：先问去向 + 笑出声 + 一起去/没走成。"""
    story = {
        "punchline_explain": "G类嘴硬心软，同路巧合笑散",
        "dialogue": [
            {"speaker": "灿灿", "line": "我走了，谁也别拦我！"},
            {"speaker": "昭昭", "line": "我也走，不用你管！"},
            {"speaker": "灿灿", "line": "你收拾包干嘛？还嘴硬！"},
            {"speaker": "昭昭", "line": "你管得着吗？少来烦我！"},
            {"speaker": "灿灿", "line": "门口撞见了？还充大侠呢！"},
            {"speaker": "昭昭", "line": "你走开！别装关心！"},
            {"speaker": "灿灿", "line": "你去哪？"},
            {"speaker": "昭昭", "line": "不用你管！"},
            {"speaker": "灿灿", "line": "我也走，同一方向！"},
            {"speaker": "昭昭", "line": "那你还不是跟我一路？"},
            {"speaker": "昭昭", "line": "噗——你还跟我一路啊！"},
            {"speaker": "灿灿", "line": "……你笑什么？"},
            {"speaker": "昭昭", "line": "算了，一起去楼下吧。"},
            {"speaker": "灿灿", "line": "行，谁也没走成。"},
        ],
    }
    errors: list[str] = []
    append_g_body_errors(story, errors)
    assert errors == []


def test_g_f_stale_who_ye_bu_not_bare():
    """裸「谁也不」不判 F；双方僵持结构才判。"""
    assert not RE_F_STALE.search("谁也没真走成")
    assert RE_F_STALE.search("谁也不理谁")


def test_g_validate_f_stale_softened_by_warm_tail():
    """末段有暖收时，残余僵持词不硬拦。"""
    story = {
        "punchline_explain": "G类嘴硬心软",
        "dialogue": [
            {"speaker": "灿灿", "line": f"数落升级第{i}句丢人怂"} for i in range(10)
        ]
        + [
            {"speaker": "昭昭", "line": "谁敢动你我拼命！"},
            {"speaker": "灿灿", "line": "你说啥？"},
            {"speaker": "昭昭", "line": "谁也不让谁也行，一起走吧。"},
        ],
    }
    errors: list[str] = []
    append_g_body_errors(story, errors)
    assert not any("威胁僵持" in e for e in errors)


def test_g_validate_accepts_behavioral_follow_warm_branch_like_111():
    """M4+G 行动递台词：拒绝→看见示范→惊讶→主动跟随，不硬造护短真情。"""
    from app.services.daily_story.story_types.g.humor import collect_g_humor_issues

    story = {
        "punchline_explain": "G类嘴硬心软，行动示范后主动跟随暖收",
        "dialogue": [
            {"speaker": "妈妈", "line": "昭昭，玩具收好再玩。"},
            {"speaker": "昭昭", "line": "我还没玩完，等会儿再收。"},
            {"speaker": "灿灿", "line": "你不收，我先把这几块放回去。"},
            {"speaker": "昭昭", "line": "姐姐，你码积木干嘛？又不玩了。"},
            {"speaker": "灿灿", "line": "红色放这格，蓝色放那格。"},
            {"speaker": "昭昭", "line": "我才不学你呢。"},
            {"speaker": "灿灿", "line": "那我去看书了，你自己慢慢玩。"},
            {"speaker": "昭昭", "line": "等等，剩下这些我来收。"},
            {"speaker": "灿灿", "line": "那边还有两块，别漏了。"},
            {"speaker": "昭昭", "line": "知道啦，这就收。"},
            {"speaker": "灿灿", "line": "我去沙发看书。"},
            {"speaker": "昭昭", "line": "那我也读，给我留个位。"},
            {"speaker": "灿灿", "line": "行，一起看。"},
        ],
    }
    errors: list[str] = []
    append_g_body_errors(story, errors)
    assert errors == [], errors
    lines = [row["line"] for row in story["dialogue"]]
    assert collect_g_humor_issues(lines) == []


    from app.services.daily_story.quality import _score_escalation
    from app.services.daily_story.story_types.g.quality import QUALITY_PROFILE

    esc_points, _ = _score_escalation(
        lines,
        layer_patterns=QUALITY_PROFILE.layer_patterns(),
    )
    assert esc_points == 14


def test_g_behavioral_follow_real_111_shape_scores_80_not_72():
    from app.services.daily_story.quality import score_daily_story

    story = {
        "story_type": "G",
        "conflict_core": "昭昭拒绝收玩具，灿灿用行动示范，昭昭最后主动跟着收并一起读书",
        "punchline_explain": "G类嘴硬心软，行动示范后主动跟随暖收",
        "dialogue": [
            {"speaker": "妈妈", "line": "昭昭，把玩具收好，地上都下不去脚了。"},
            {"speaker": "昭昭", "line": "我还没玩完呢，别动我的积木！"},
            {"speaker": "灿灿", "line": "用过的东西放回原位，这是习惯。"},
            {"speaker": "昭昭", "line": "我还没玩完，你别管我，踢散了我自己捡。"},
            {"speaker": "灿灿", "line": "这是习惯，不是罚你，我帮你一起码。"},
            {"speaker": "昭昭", "line": "那也不行，这块红的我还没搭完呢。"},
            {"speaker": "灿灿", "line": "行，我码我的积木，码好我就看书了。"},
            {"speaker": "昭昭", "line": "你干嘛拿书？积木还没收完呢。"},
            {"speaker": "灿灿", "line": "每天读书学习，这是第十条，妈妈定的。"},
            {"speaker": "昭昭", "line": "第十条？妈妈说的？那我也要听。"},
            {"speaker": "灿灿", "line": "对，你收完玩具也能来，挤我旁边一起读。"},
            {"speaker": "昭昭", "line": "那我也读，挤你旁边，这块红的先放箱子里。"},
            {"speaker": "灿灿", "line": "放吧，按颜色码好，明天找起来才快。"},
            {"speaker": "昭昭", "line": "姐姐，书翻慢点，我还没坐稳呢。"},
        ],
    }

    quality = score_daily_story(story, skip_relevancy=True)

    assert quality["structure_score"] == 80
    assert quality["structure_cons"] == []
    assert "行动软化暖收" in quality["reasons"]


def test_g_validate_authority_punchline_mode_skips_pivot_soft():
    """closing_mode=authority_punchline 走权威点题槽，不卡 pivot/暖收。"""
    from app.services.gold_story.structure_resolve import (
        CLOSING_MODE_AUTHORITY_PUNCHLINE,
    )

    story = {
        "punchline_explain": "G类嘴硬心软，权威点题",
        "closing_mode": CLOSING_MODE_AUTHORITY_PUNCHLINE,
        "dialogue": [
            {"speaker": "妈妈", "line": "谁先写完作业谁玩。"},
            {"speaker": "昭昭", "line": "本子呢？我没看见。"},
            {"speaker": "灿灿", "line": "我本子呢？急死了！"},
            {"speaker": "妈妈", "line": "你藏得快，那今晚你负责哄她睡。"},
            {"speaker": "昭昭", "line": "哄人这事我真不会呀。"},
            {"speaker": "灿灿", "line": "你哄我，我就告你偷吃。"},
            {"speaker": "昭昭", "line": "你玩你玩，我哄你。"},
            {"speaker": "灿灿", "line": "真让我玩？"},
            {"speaker": "昭昭", "line": "真让，我哄你睡。"},
            {"speaker": "灿灿", "line": "那作业本呢？"},
            {"speaker": "妈妈", "line": "记住，这个家我第一，你俩并列第三。"},
        ],
    }
    errors: list[str] = []
    append_g_body_errors(story, errors)
    assert errors == []
    assert not any("pivot" in e for e in errors)
    assert not any("暖收" in e for e in errors)


def test_g_validate_without_mode_still_requires_pivot():
    """无 closing_mode 时仍走标准 G 硬卡。"""
    story = {
        "punchline_explain": "G类嘴硬心软",
        "dialogue": [
            {"speaker": "妈妈", "line": "谁先写完作业谁玩。"},
            {"speaker": "昭昭", "line": "本子呢？我没看见。"},
            {"speaker": "灿灿", "line": "我本子呢？急死了！"},
            {"speaker": "妈妈", "line": "你藏得快，那今晚你负责哄她睡。"},
            {"speaker": "昭昭", "line": "这算奖还是罚？"},
            {"speaker": "灿灿", "line": "你哄我，我就告你偷吃。"},
            {"speaker": "昭昭", "line": "你玩你玩，我哄你。"},
            {"speaker": "灿灿", "line": "真让我玩？"},
            {"speaker": "昭昭", "line": "真让，我哄你睡。"},
            {"speaker": "妈妈", "line": "早这样不就好了。"},
            {"speaker": "妈妈", "line": "记住，这个家我第一，你俩并列第三。"},
        ],
    }
    errors: list[str] = []
    append_g_body_errors(story, errors)
    assert any("pivot" in e for e in errors)
    assert any("暖收" in e for e in errors)
