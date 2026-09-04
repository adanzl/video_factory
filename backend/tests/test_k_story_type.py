"""K 类家长看戏 validate 与质检注册。"""

from __future__ import annotations

from app.services.daily_story.story_types import (
    append_type_body_validation_errors,
    parse_story_type_code,
    type_body_validation_enabled,
)
from app.services.daily_story.story_types.k.validate import append_k_body_errors


def _k_stalemate_story() -> dict:
    return {
        "story_type": "K",
        "theme": "越劝越哭",
        "setting": "客厅，姐弟扭在一起，妈妈站在门口",
        "conflict_core": "姐弟互骂升级，妈妈越劝越凶",
        "punchline_explain": (
            "K类家长看戏，姐弟互骂升级，妈妈叹气劝失败，"
            "最后僵持不和好。"
        ),
        "discovery_opening": [
            {"speaker": "灿灿", "line": "你干嘛抢我遥控器！"},
            {"speaker": "昭昭", "line": "你才抢！你滚！"},
        ],
        "dialogue": [
            {"speaker": "灿灿", "line": "你干嘛抢我遥控器！"},
            {"speaker": "昭昭", "line": "你才抢！你滚！"},
            {"speaker": "灿灿", "line": "你骂谁呢！我打你了！"},
            {"speaker": "昭昭", "line": "来啊！谁怕谁！"},
            {"speaker": "灿灿", "line": "讨厌！你推我！"},
            {"speaker": "昭昭", "line": "你还推！呜呜呜！"},
            {"speaker": "妈妈", "line": "别打了！你们别吵了！"},
            {"speaker": "灿灿", "line": "你管不着！"},
            {"speaker": "昭昭", "line": "越劝越凶！哼！"},
            {"speaker": "妈妈", "line": "唉，我管不了你们了。"},
            {"speaker": "灿灿", "line": "就不理你！"},
            {"speaker": "昭昭", "line": "我也不和好！"},
            {"speaker": "灿灿", "line": "僵持就僵持，谁怕谁！"},
            {"speaker": "昭昭", "line": "哼，别理你！"},
        ],
    }


def test_k_validate_passes_stalemate_shape():
    story = _k_stalemate_story()
    errors: list[str] = []
    append_k_body_errors(story, errors)
    assert errors == []


def test_k_validate_rejects_h_reconcile():
    story = _k_stalemate_story()
    story["dialogue"][-2] = {"speaker": "灿灿", "line": "好吧，我们和好吧。"}
    story["dialogue"][-1] = {"speaker": "昭昭", "line": "拉手，不打了。"}
    errors: list[str] = []
    append_k_body_errors(story, errors)
    assert any("H 式" in e for e in errors)


def test_k_patch_strips_h_reconcile_and_fills_stalemate():
    from app.services.daily_story.story_types.k.patch import patch_k_body

    story = _k_stalemate_story()
    story["dialogue"][-2] = {"speaker": "妈妈", "line": "你们什么时候能和好？"}
    story["dialogue"][-1] = {"speaker": "昭昭", "line": "拉手，不打了。"}
    notes = patch_k_body(story)
    assert notes
    errors: list[str] = []
    append_k_body_errors(story, errors)
    assert errors == []


def test_k_repair_closing_and_seed_sanitize():
    from app.services.daily_story.story_types.k.patch import sanitize_k_dialogue_seed
    from app.services.daily_story.story_types.k.validate import (
        repair_closing_intent_for_k,
    )

    closing = repair_closing_intent_for_k("妈妈哭笑不得，总结胜不骄败不馁")
    assert "僵持" in closing or "不和好" in closing
    assert "和好" not in closing or "不和好" in closing

    seed = sanitize_k_dialogue_seed(
        [
            {"speaker": "妈妈", "intent": "叹气，你们俩什么时候能和好？"},
            {"speaker": "昭昭", "intent": "不服气"},
        ]
    )
    assert "和好" not in str(seed[0].get("intent") or "") or "不和好" in str(
        seed[0].get("intent") or ""
    )
    assert "劝不" in str(seed[0].get("intent") or "") or "管不了" in str(
        seed[0].get("intent") or ""
    )


def test_k_body_validate_gated_when_not_quality_ready():
    story = _k_stalemate_story()
    story["dialogue"] = story["dialogue"][:8]
    assert not type_body_validation_enabled("K")
    errors: list[str] = []
    append_type_body_validation_errors(story, errors)
    assert not any("K类" in e for e in errors)


def test_parse_k_from_story_type():
    assert parse_story_type_code(story_type="K", punchline="H类：旧稿") == "K"


def test_k_quality_scores_stalemate_story():
    from app.services.daily_story.quality import score_daily_story

    story = _k_stalemate_story()
    q = score_daily_story(story, theme="越劝越哭")
    assert q["structure_score"] >= 70, q
    assert "C开场说话人" not in "".join(q["reasons"])
    assert "C规则轮次升级" not in "".join(q["reasons"])
    assert "收束形态未落位" not in "".join(q["reasons"])
    assert "笑点解析缺类型" not in q["reasons"]
