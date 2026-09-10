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
