"""O 类目标错位：校验/观感 smoke（注册映射见 test_gold_story_types）。"""

from app.services.daily_story.quality import attach_daily_story_quality
from app.services.daily_story.story_types import patch_type_body
from app.services.daily_story.story_types.o.validate import append_o_body_errors


def test_o_body_validate_and_structure_score():
    story = {
        "story_type": "O",
        "scene_title": "光顾着赢",
        "setting": "餐桌前",
        "conflict_core": "目标错位：昭昭光顾着赢猜拳，菜被吃光",
        "key": "抢吃猜拳",
        "punchline_explain": "O类目标错位，赢了过程输了目标",
        "discovery_opening": [
            {"speaker": "昭昭", "line": "剪刀石头布，赢的才能吃菜！"},
            {"speaker": "灿灿", "line": "好，来！"},
        ],
        "dialogue": [
            {"speaker": "昭昭", "line": "剪刀石头布，赢的才能吃菜！"},
            {"speaker": "灿灿", "line": "好，来！"},
            {"speaker": "昭昭", "line": "剪刀石头布！我赢了！"},
            {"speaker": "灿灿", "line": "那你夹吧。"},
            {"speaker": "昭昭", "line": "咦，菜怎么少了？"},
            {"speaker": "灿灿", "line": "你赢你的，我吃我的。"},
            {"speaker": "昭昭", "line": "再来！又赢！"},
            {"speaker": "灿灿", "line": "快夹，不然又没了。"},
            {"speaker": "昭昭", "line": "啊？只剩一小块了？"},
            {"speaker": "灿灿", "line": "嘿嘿，我吃饱了。"},
            {"speaker": "昭昭", "line": "我光顾着赢，菜都没了……"},
            {"speaker": "妈妈", "line": "哈哈，你俩真逗。"},
        ],
    }
    errors: list[str] = []
    append_o_body_errors(story, errors)
    assert errors == []

    notes = patch_type_body(story)
    assert isinstance(notes, list)

    # 点题后抬杠应被截断，只留笑场
    bloated = {
        **story,
        "dialogue": list(story["dialogue"])
        + [
            {"speaker": "昭昭", "line": "不行，我偏就不信！"},
            {"speaker": "灿灿", "line": "真的不行好不好呀！"},
            {"speaker": "昭昭", "line": "不行呢！"},
            {"speaker": "灿灿", "line": "真的！"},
            {"speaker": "妈妈", "line": "哈哈，你俩真逗。"},
        ],
    }
    bad: list[str] = []
    append_o_body_errors(bloated, bad)
    assert any("第二轮" in e for e in bad), bad
    trim_notes = patch_type_body(bloated)
    assert any("截断" in n for n in trim_notes), trim_notes
    bad2: list[str] = []
    append_o_body_errors(bloated, bad2)
    assert bad2 == [], bad2
    # 带续赛暗示的笑场也应截断
    with_continue = {
        **story,
        "dialogue": list(story["dialogue"][:-1])
        + [
            {"speaker": "灿灿", "line": "嘿嘿，我吃饱了，你慢慢赢吧。"},
            {"speaker": "妈妈", "line": "哈哈，你俩真逗。"},
        ],
    }
    # 确保点题句仍在
    assert any("光顾着赢" in str(d["line"]) for d in with_continue["dialogue"])
    bad3: list[str] = []
    append_o_body_errors(with_continue, bad3)
    assert any("第二轮" in e for e in bad3), bad3
    patch_type_body(with_continue)
    bad4: list[str] = []
    append_o_body_errors(with_continue, bad4)
    assert bad4 == [], bad4
    assert not any("慢慢赢" in str(d["line"]) for d in with_continue["dialogue"])

    # 点题句带申诉尾巴、点题前得意夹续赛暗示 → 校验拦、修稿净
    soft_tail = {
        **story,
        "dialogue": [
            *story["dialogue"][:-2],
            {"speaker": "灿灿", "line": "嘿嘿，我吃饱啦，你慢慢赢，不许再耍赖了。"},
            {"speaker": "昭昭", "line": "我光顾着赢，菜都没了……呜呜，不公平呢！"},
            {"speaker": "妈妈", "line": "哈哈，你俩真逗。"},
        ],
    }
    soft_err: list[str] = []
    append_o_body_errors(soft_tail, soft_err)
    assert any("申诉" in e or "续赛" in e for e in soft_err), soft_err
    soft_notes = patch_type_body(soft_tail)
    assert soft_notes, soft_notes
    soft_err2: list[str] = []
    append_o_body_errors(soft_tail, soft_err2)
    assert soft_err2 == [], soft_err2
    punch_line = next(
        d["line"] for d in soft_tail["dialogue"] if "光顾着赢" in d["line"]
    )
    assert "不公平" not in punch_line
    assert not any("慢慢赢" in str(d["line"]) for d in soft_tail["dialogue"])

    # 对手嘲讽「只顾着赢」不得当成点题句，否则截断失效
    taunt_tail = {
        **story,
        "dialogue": list(story["dialogue"][:-1])
        + [
            {"speaker": "灿灿", "line": "那你慢慢赢吧，我收碗了。"},
            {"speaker": "昭昭", "line": "别收！你赔我！"},
            {"speaker": "灿灿", "line": "活该，谁让你只顾着赢！"},
        ],
    }
    taunt_err: list[str] = []
    append_o_body_errors(taunt_tail, taunt_err)
    assert any("第二轮" in e for e in taunt_err), taunt_err
    patch_type_body(taunt_tail)
    taunt_err2: list[str] = []
    append_o_body_errors(taunt_tail, taunt_err2)
    assert taunt_err2 == [], taunt_err2
    assert not any("赔我" in str(d["line"]) for d in taunt_tail["dialogue"])
    assert not any("只顾着赢" in str(d["line"]) for d in taunt_tail["dialogue"])

    attach_daily_story_quality(story, theme="抢吃猜拳")
    q = story["quality"]
    assert q["structure_score"] >= 60
    assert "笑点解析缺类型" not in (q.get("reasons") or [])
    assert any(
        "点题" in r or "溜走" in r or "死磕" in r or "立规" in r
        for r in q.get("reasons") or []
    )
