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


def test_k_patch_fixes_limp_hum_last_line():
    """末句以哼起笔且无破功锚时，patch 须改掉以免无破功软收 -20。"""
    from app.services.daily_story.quality import score_daily_story
    from app.services.daily_story.story_types.k.patch import patch_k_body

    story = _k_stalemate_story()
    story["key"] = "抢遥控"
    # 去掉末段破功锚，只留哼软收
    story["dialogue"][-3] = {"speaker": "灿灿", "line": "你再闹试试！"}
    story["dialogue"][-2] = {"speaker": "昭昭", "line": "我咬定你了！"}
    story["dialogue"][-1] = {"speaker": "灿灿", "line": "哼，随你吧！"}
    before = score_daily_story(story, theme="越劝越哭")
    assert "无破功软收" in "".join(before["reasons"]), before
    notes = patch_k_body(story)
    assert any("软收" in n or "去哼" in n or "僵持" in n or "回扣" in n for n in notes), notes
    last = str(story["dialogue"][-1]["line"])
    assert not last.startswith("哼"), last
    # 末句应挂上前文/主题锚，避免逻辑脱节
    assert "不理" in last
    after = score_daily_story(story, theme="越劝越哭")
    assert "无破功软收" not in "".join(after["reasons"]), after
    assert after["structure_score"] > before["structure_score"], (before, after)


def test_k_patch_tail_anchor_when_mid_filler_dominates():
    """尾段若全是空喊互打、丢掉主题锚，须回扣 key/conflict。"""
    from app.services.daily_story.story_types.k.patch import patch_k_body

    story = _k_stalemate_story()
    story["key"] = "抢粥洒地"
    story["conflict_core"] = "抢粥洒地后趴舔，妈妈劝不动"
    story["dialogue"][-4:] = [
        {"speaker": "昭昭", "line": "你还敢推我！"},
        {"speaker": "灿灿", "line": "推你怎么了！"},
        {"speaker": "昭昭", "line": "你再吼我试试！"},
        {"speaker": "灿灿", "line": "我偏要吼！"},
    ]
    notes = patch_k_body(story)
    assert any("回扣" in n or "僵持" in n for n in notes), notes
    tail = "".join(d["line"] for d in story["dialogue"][-4:])
    assert "粥" in tail or "抢" in tail or "不理" in tail, tail


def test_k_mid_pairs_forbid_ear_twist_filler():
    """K 中段垫句禁拧耳朵/咬手注水，避免冲掉场故事主梗。"""
    from app.services.gold_story.gold_chat import convert as gc_convert

    blob = "\n".join(
        f"{a[1]}\n{b[1]}" for a, b in gc_convert._K_NATURAL_MID_PAIRS
    )
    assert "拧" not in blob
    assert "耳朵" not in blob
    assert "咬定" not in blob
    # 须能点到互骂/升级层关键词
    assert any(k in blob for k in ("推", "吵", "骂", "打", "吼"))
    assert any(k in blob for k in ("更凶", "还骂", "还打", "哭", "吼"))


def test_k_force_min_chars_reaches_body_floor():
    """K 短稿 force_min 须能垫到正文 hard min，不再卡在 227。"""
    from app.services.daily_story.prompts import (
        DAILY_STORY_BODY_CHARS_MIN,
        dialogue_total_chars,
    )
    from app.services.gold_story.gold_chat.convert import _gold_chat_force_min_chars

    story = {
        "story_type": "K",
        "scene_title": "抢粥洒地",
        "setting": "客厅餐桌旁",
        "key": "抢粥洒地",
        "conflict_core": "抢粥洒地后趴舔，妈妈劝不动",
        "punchline_explain": "K类：趴舔僵持，妈妈劝失败。",
        "dialogue": [
            {"speaker": "灿灿", "line": "哼，这碗粥是我的！"},
            {"speaker": "昭昭", "line": "你推我，明明我先碰到！"},
            {"speaker": "灿灿", "line": "别推别吵，粥洒了！"},
            {"speaker": "昭昭", "line": "都怪你推，全洒了！"},
            {"speaker": "灿灿", "line": "不能浪费，我用手拢着吃。"},
            {"speaker": "昭昭", "line": "我也趴着舔，不能浪费。"},
            {"speaker": "灿灿", "line": "咂咂真甜，你少抢！"},
            {"speaker": "昭昭", "line": "我偏要舔！"},
            {"speaker": "妈妈", "line": "唉，我管不了你们了。"},
            {"speaker": "昭昭", "line": "妈妈不管了，我继续舔。"},
            {"speaker": "灿灿", "line": "谁怕谁，剩下归我！"},
            {"speaker": "昭昭", "line": "不理你，我舔我的。"},
        ],
    }
    assert dialogue_total_chars(story) < DAILY_STORY_BODY_CHARS_MIN
    out, changed = _gold_chat_force_min_chars(story)
    assert changed
    assert dialogue_total_chars(out) >= DAILY_STORY_BODY_CHARS_MIN, (
        dialogue_total_chars(out),
        [d.get("line") for d in out["dialogue"]],
    )
    blob = "".join(str(d.get("line") or "") for d in out["dialogue"])
    assert "拧耳朵" not in blob
    assert "耳朵" not in blob
