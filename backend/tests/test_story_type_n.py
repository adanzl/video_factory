"""N 类正经胡说：校验/观感 smoke（注册映射见 test_gold_story_types）。"""

from app.services.daily_story.quality import (
    attach_daily_story_quality,
    score_daily_story,
    structure_score_of,
)
from app.services.daily_story.story_types import patch_type_body
from app.services.daily_story.story_types.n.validate import append_n_body_errors


def test_n_body_validate_and_structure_score():
    story = {
        "story_type": "N",
        "scene_title": "香蕉救父",
        "setting": "家中客厅",
        "conflict_core": "正经胡说：假设性二选一，荒诞自洽噎住追问方",
        "key": "正经胡说",
        "punchline_explain": "N类正经胡说，荒诞自洽噎住追问方",
        "discovery_opening": [
            {"speaker": "灿灿", "line": "如果爸爸掉水里，你先吃啥？"},
            {"speaker": "昭昭", "line": "先吃香蕉。"},
        ],
        "dialogue": [
            {"speaker": "灿灿", "line": "爸爸掉水里，你先吃苹果还是香蕉？"},
            {"speaker": "昭昭", "line": "吃香蕉。"},
            {"speaker": "灿灿", "line": "为什么？"},
            {"speaker": "昭昭", "line": "因为有籽，吃了能长成树。"},
            {"speaker": "灿灿", "line": "长成树又怎样？"},
            {"speaker": "昭昭", "line": "这样就能把爸爸捞上来。"},
            {"speaker": "灿灿", "line": "那……行吧。"},
            {"speaker": "昭昭", "line": "你服了吧。"},
            {"speaker": "灿灿", "line": "接不住了，算了。"},
            {"speaker": "昭昭", "line": "我说得通吧。"},
        ],
    }
    errors: list[str] = []
    append_n_body_errors(story, errors)
    assert errors == []

    notes = patch_type_body(story)
    assert isinstance(notes, list)

    attach_daily_story_quality(story, theme="正经胡说")
    q = story["quality"]
    assert q["structure_score"] >= 60
    assert any(
        "自洽" in r or "愣住" in r or "设问" in r for r in q.get("reasons") or []
    )


def test_n_stun_close_not_double_penalized_as_limp_soft():
    """N 类末段愣住已落位时，末句软尾勿再扣「无破功软收」。"""
    dialogue = [
        {"speaker": "灿灿", "line": "爸爸一百岁还是一千岁？"},
        {"speaker": "昭昭", "line": "一千四！"},
        {"speaker": "灿灿", "line": "为什么？"},
        {"speaker": "昭昭", "line": "因为吃血就能补回来呀。"},
        {"speaker": "灿灿", "line": "那爸爸掉河里呢？"},
        {"speaker": "昭昭", "line": "先吃香蕉有籽长成树。"},
        {"speaker": "灿灿", "line": "长成树又怎样？"},
        {"speaker": "昭昭", "line": "这样就能把爸爸捞上来。"},
        {"speaker": "灿灿", "line": "你这歪理也太绝了。"},
        {"speaker": "昭昭", "line": "我说得通吧。"},
        {"speaker": "灿灿", "line": "那……我说不过你。"},
        {"speaker": "昭昭", "line": "给你吧。"},
    ]
    story = {
        "story_type": "N",
        "punchline_explain": "N类正经胡说",
        "dialogue": dialogue,
    }
    quality = score_daily_story(story)
    reasons = quality.get("reasons") or []
    assert not any("无破功软收" in str(r) for r in reasons)
    assert any("愣住收束" in str(r) for r in reasons)
    assert structure_score_of(quality) >= 70


def test_n_mid_stun_then_soft_tail_still_penalizes_limp_close():
    """中段愣住、后又续写软收：末段仍按无破功软收扣分。"""
    dialogue = [
        {"speaker": "灿灿", "line": "爸爸一百岁还是一千岁？"},
        {"speaker": "昭昭", "line": "一千四！"},
        {"speaker": "灿灿", "line": "为什么？"},
        {"speaker": "昭昭", "line": "因为吃血就能补回来呀。"},
        {"speaker": "灿灿", "line": "那……行吧。"},
        {"speaker": "昭昭", "line": "还没完，掉河里呢？"},
        {"speaker": "灿灿", "line": "你继续编。"},
        {"speaker": "昭昭", "line": "先吃香蕉有籽长成树。"},
        {"speaker": "灿灿", "line": "然后呢？"},
        {"speaker": "昭昭", "line": "树长好就捞人。"},
        {"speaker": "灿灿", "line": "我听不懂了。"},
        {"speaker": "昭昭", "line": "给你。"},
    ]
    story = {
        "story_type": "N",
        "punchline_explain": "N类正经胡说",
        "dialogue": dialogue,
    }
    quality = score_daily_story(story)
    reasons = quality.get("reasons") or []
    assert any("无破功软收" in str(r) for r in reasons)
    assert not any("类型收束软尾（已达标）" in str(r) for r in reasons)
