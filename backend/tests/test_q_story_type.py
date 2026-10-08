"""Q 类观感：立约定层与结构分。"""

from __future__ import annotations

from app.services.daily_story.quality import score_daily_story
from app.services.daily_story.story_types.q.line import LINE_Q


def _q_story(*, with_rule_setup: bool) -> dict:
    opening = (
        [
            {"speaker": "灿灿", "line": "抽签吃饭，抽到几口吃几口！"},
            {"speaker": "妈妈", "line": "行，按签算，不许耍赖。"},
        ]
        if with_rule_setup
        else [
            {"speaker": "灿灿", "line": "三口太少啦，不算，我要重抽呢！"},
            {"speaker": "昭昭", "line": "你又来这套吧！"},
        ]
    )
    body = [
        {"speaker": "灿灿", "line": "这次八口，满意！看我一口吞泡芙！"},
        {"speaker": "昭昭", "line": "签都认了还改口啊！"},
        {"speaker": "灿灿", "line": "辣面真香，我还能吃！"},
        {"speaker": "昭昭", "line": "刚才不是挺能的！"},
        {"speaker": "灿灿", "line": "才没有，我这是吃面辣的！"},
        {"speaker": "昭昭", "line": "你昨天偷吃辣条我都看见啦！"},
        {"speaker": "灿灿", "line": "那是辣条吗？不算偷吃！"},
        {"speaker": "昭昭", "line": "你就是嘴硬！"},
        {"speaker": "灿灿", "line": "我还能塞，这碗面我包了！"},
        {"speaker": "昭昭", "line": "你脸都红了，还逞强！"},
        {"speaker": "灿灿", "line": "我胃小吃不下，这碗面你帮我吃吧！"},
        {"speaker": "昭昭", "line": "不行，你自己说包了的！"},
        {"speaker": "灿灿", "line": "可我真的撑！"},
        {"speaker": "昭昭", "line": "你就是耍赖，刚才还逞强呢！"},
        {"speaker": "灿灿", "line": "我哪有逞强，就是胃小嘛！"},
        {"speaker": "妈妈", "line": "刚才还说包了，现在胃小？去洗碗吧！"},
    ]
    dialogue = list(opening) + body
    return {
        "story_type": "Q",
        "theme": "抽签吃饭的机灵鬼",
        "setting": "家中餐桌，泡芙和辣面摆着，妈妈坐对面",
        "conflict_core": "灿灿抽签耍赖猛吃逞强，借口胃小推食，妈妈看穿让洗碗",
        "punchline_explain": "Q类耍赖翻车，借口被拆穿后反噬",
        "discovery_opening": opening,
        "dialogue": dialogue,
    }


def test_q1_layer_hits_quantity_unit_not_only_jikou():
    lines = ["三口太少啦，不算！", "你又来这套！"]
    label, pat = LINE_Q.layer_patterns[0]
    assert label == "Q1_立约定"
    assert pat.search(lines[0])


def test_q_quality_uses_q_profile_not_c_markers():
    story = _q_story(with_rule_setup=True)
    q = score_daily_story(story, theme=story["theme"])
    reasons = " ".join(q.get("reasons") or [])
    assert "C规则" not in reasons
    assert "C开场" not in reasons
    assert "回旋镖收束" not in reasons
    assert int(q.get("structure_score") or 0) >= 75


def test_q_quality_four_layers_when_rule_setup_present():
    story = _q_story(with_rule_setup=True)
    q = score_daily_story(story, theme=story["theme"])
    reasons = q.get("reasons") or []
    assert any("冲突推进4层" in r or "冲突推进5层" in r for r in reasons) or (
        int(q.get("structure_score") or 0) >= 78
    )


def test_q_117_patch_reassigns_cheat_and_expose_speakers():
    from app.services.daily_story.quality import score_daily_story
    from app.services.daily_story.story_types.q.patch import patch_q_body
    from app.services.daily_story.story_types.q.validate import append_q_body_errors
    from app.services.gold_story.gold_chat.convert import (
        patch_gold_chat_consecutive_siblings,
    )

    story = {
        "story_type": "Q",
        "conflict_core": "昭昭猜错食物后耍赖不认，灿灿拆穿后摔筷子不玩了",
        "punchline_explain": "Q类耍赖翻车，昭昭猜错食物后耍赖不认，灿灿拆穿后摔筷子不玩了",
        "dialogue": [
            {"speaker": "昭昭", "line": "咱俩玩猜食物，猜中得分，猜错加码！"},
            {"speaker": "灿灿", "line": "行，我猜披萨，这盒归我，先得一分！"},
            {"speaker": "昭昭", "line": "冷面我都没动，不敢吃不敢喝，披萨呢！"},
            {"speaker": "灿灿", "line": "你骗过没有啊？你刚那两回车都跑里面是吧！"},
            {"speaker": "昭昭", "line": "你管我呢！我说没动就是没动！"},
            {"speaker": "灿灿", "line": "那炸鸡呢？你手指头油光锃亮，别装傻！"},
            {"speaker": "昭昭", "line": "炸鸡？不对，爱咋样啊，反正我不认！"},
            {"speaker": "灿灿", "line": "可乐！我猜对了，这罐归我，又得一分！"},
            {"speaker": "昭昭", "line": "我去你咋开的了啊？来呀，再来一轮！"},
            {"speaker": "灿灿", "line": "胃小吃不下就推给我？看穿了，去洗碗。"},
            {"speaker": "妈妈", "line": "妈，我猜错想加码，灿灿不让，我就摔了筷子！"},
            {"speaker": "昭昭", "line": "你加码就是耍赖，摔筷子更没理，我不玩了！"},
            {"speaker": "灿灿", "line": "那我把炸鸡分你一半，咱重新猜，行不行？"},
            {"speaker": "昭昭", "line": "不行，你先把摔筷子的毛病改了再说！"},
            {"speaker": "灿灿", "line": "不玩了！你耍赖还摔筷子，谁跟你玩！"},
        ],
    }
    patch_q_body(story)
    story, _ = patch_gold_chat_consecutive_siblings(story)
    errors: list[str] = []
    append_q_body_errors(story, errors)
    assert errors == []
    assert score_daily_story(
        story, skip_relevancy=True
    )["structure_score"] >= 75
