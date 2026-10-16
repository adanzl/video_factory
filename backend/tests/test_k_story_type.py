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
        "k_close_mode": "K_A_PARENT_FAIL_STALEMATE",
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
            {"speaker": "昭昭", "line": "疼！快松手啊！"},
            {"speaker": "灿灿", "line": "你管不着！"},
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


def test_k_explicit_unknown_is_rejected_but_legacy_empty_passes():
    """显式 K_UNKNOWN（解析器跑过没定轨）须硬拒；历史字段缺失仍走旧兜底。"""
    from app.services.daily_story.story_types.k.close_mode import (
        k_close_mode_is_explicit_unknown,
    )
    from app.services.daily_story.story_types.k.validate import append_k_body_errors

    # 1) 历史稿：字段从未落盘（legacy_empty / absent）→ 不因"缺失"阻断
    legacy = _k_stalemate_story()
    legacy["k_close_mode"] = ""
    errors: list[str] = []
    append_k_body_errors(legacy, errors)
    assert not [e for e in errors if "K_UNKNOWN" in e]
    assert k_close_mode_is_explicit_unknown(legacy) is False

    absent = _k_stalemate_story()
    absent.pop("k_close_mode")
    assert k_close_mode_is_explicit_unknown(absent) is False
    errors_absent: list[str] = []
    append_k_body_errors(absent, errors_absent)
    assert not [e for e in errors_absent if "K_UNKNOWN" in e]

    # 2) 新稿：显式 K_UNKNOWN = 未定轨非法状态 → 必须拒
    explicit = _k_stalemate_story()
    explicit["k_close_mode"] = "K_UNKNOWN"
    assert k_close_mode_is_explicit_unknown(explicit) is True
    errors2: list[str] = []
    append_k_body_errors(explicit, errors2)
    assert any("K_UNKNOWN" in e for e in errors2)

    # 3) 嵌套在 scene_contract 里的显式 K_UNKNOWN 同样拒
    nested = _k_stalemate_story()
    nested["k_close_mode"] = ""
    nested["scene_contract"] = {"k_close_mode": "K_UNKNOWN"}
    assert k_close_mode_is_explicit_unknown(nested) is True
    errors3: list[str] = []
    append_k_body_errors(nested, errors3)
    assert any("K_UNKNOWN" in e for e in errors3)
    # 但嵌套只是缺失（空串）时仍算历史稿
    nested_empty = _k_stalemate_story()
    nested_empty["k_close_mode"] = ""
    nested_empty["scene_contract"] = {"k_close_mode": ""}
    assert k_close_mode_is_explicit_unknown(nested_empty) is False


def test_k_contract_phase_fails_fast_on_unresolvable_close_mode():
    """契约期判不出 K-A/K-B 就该 fail-fast，不许烧完 16 句才在终检失败。"""
    import pytest

    from app.services.gold_story.gold_chat.expand import _repair_k_row_contract

    row = {
        "id": 999,
        "structure_type": "K",
        "payload": {
            "scene_contract": {"beat_chain": [], "mechanism": ""},
            "closing_intent": "",
        },
    }
    with pytest.raises(ValueError, match="K_CLOSE_MODE_UNRESOLVED"):
        _repair_k_row_contract(row)

    # 非 K 类不受影响，原样返回
    passthrough = {"id": 1, "structure_type": "C", "payload": {}}
    assert _repair_k_row_contract(passthrough) is passthrough


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

    closing = repair_closing_intent_for_k(
        "妈妈哭笑不得，总结胜不骄败不馁",
        k_close_mode="K_A_PARENT_FAIL_STALEMATE",
    )
    assert "僵持" in closing or "不和好" in closing
    unknown = repair_closing_intent_for_k(
        "妈妈放下碗对爸爸说：不掺和就对了。",
        k_close_mode="K_UNKNOWN",
    )
    assert unknown == "妈妈放下碗对爸爸说：不掺和就对了。"
    assert "和好" not in closing or "不和好" in closing

    seed = sanitize_k_dialogue_seed(
        [
            {"speaker": "妈妈", "intent": "叹气，你们俩什么时候能和好？"},
            {"speaker": "昭昭", "intent": "不服气"},
        ],
        k_close_mode="K_A_PARENT_FAIL_STALEMATE",
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


def test_k_padding_pairs_do_not_invent_props_or_actions():
    from app.services.gold_story.gold_chat.convert import _K_NATURAL_MID_PAIRS

    text = "".join(
        line
        for pair in _K_NATURAL_MID_PAIRS
        for _speaker, line in pair
    )
    for forbidden in ("笔", "挠", "追", "跑", "逮", "抓", "松手"):
        assert forbidden not in text


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
    """K 中段垫句禁拧耳朵/咬手注水，亦禁点题后推吵骂空打。"""
    from app.services.gold_story.gold_chat import convert as gc_convert

    blob = "\n".join(
        f"{a[1]}\n{b[1]}" for a, b in gc_convert._K_NATURAL_MID_PAIRS
    )
    assert "拧" not in blob
    assert "耳朵" not in blob
    assert "咬定" not in blob
    assert "推你" not in blob
    assert "来吵" not in blob
    assert "偏要吼" not in blob
    # 须能落到不服/僵持/哭口吻
    assert any(k in blob for k in ("哭", "不服", "不理", "谁怕谁", "记仇"))
    assert any(k in blob for k in ("笔", "松手", "瞪", "不怕"))

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


def _k_b_beat_chain() -> list[dict[str, str]]:
    return [
        {"beat": 1, "speaker": "妈妈", "intent": "立规：挡回告状不评理"},
        {"beat": 2, "speaker": "灿灿", "intent": "互打：和昭昭扭打升级"},
        {"beat": 3, "speaker": "昭昭", "intent": "告状：喊妈妈评理被规矩挡回"},
        {"beat": 4, "speaker": "灿灿", "intent": "旁观：妈妈继续吃饭不介入"},
        {"beat": 5, "speaker": "昭昭", "intent": "自行收场：隔一会儿邀约一起玩"},
        {"beat": 6, "speaker": "妈妈", "intent": "旁观总结：对第三方说不掺和就对了"},
    ]


def _k_b_dialogue_ok() -> list[dict[str, str]]:
    lines = [
        ("灿灿", "你干嘛抢我枕头！"),
        ("昭昭", "你才抢！推你！"),
        ("灿灿", "讨厌！来啊！"),
        ("昭昭", "妈！他先动手，你评评理！"),
        ("妈妈", "不评理，规矩写墙上呢。"),
        ("灿灿", "哼，那我自己打！"),
        ("昭昭", "来就来，谁怕谁！"),
        ("灿灿", "你还推！枕头飞一地！"),
        ("昭昭", "你还抓我！"),
        ("灿灿", "妈妈也不管！"),
        ("昭昭", "……灿灿，还玩不玩？"),
        ("灿灿", "玩！等我换鞋！"),
        ("昭昭", "行，一起走。"),
        ("妈妈", "不掺和就对了……嗯，让他们自己弄去吧。"),
    ]
    return [{"speaker": sp, "line": ln} for sp, ln in lines]


def test_repair_k_row_contract_stamps_close_mode_in_memory():
    from app.services.gold_story.gold_chat.expand import _repair_k_row_contract

    row = {
        "id": 0,
        "structure_type": "K",
        "mechanism": "M12",
        "payload": {
            "closing_intent": "妈妈对爸爸说：不掺和就对了。",
            "scene_contract": {
                "beat_chain": _k_b_beat_chain(),
                "closing_intent": "妈妈对爸爸说：不掺和就对了。",
            },
        },
    }
    fixed = _repair_k_row_contract(row)
    assert fixed["payload"]["k_close_mode"] == "K_B_CHILD_SELF_RESOLVE"
    assert (
        fixed["payload"]["scene_contract"]["k_close_mode"]
        == "K_B_CHILD_SELF_RESOLVE"
    )


def test_resolve_k_close_mode_b_from_beats():
    from app.services.daily_story.story_types.k.close_mode import (
        K_B_CHILD_SELF_RESOLVE,
        resolve_k_close_mode,
    )

    mode = resolve_k_close_mode(
        beat_chain=_k_b_beat_chain(),
        closing_intent="妈妈对爸爸说：不掺和就对了。",
    )
    assert mode == K_B_CHILD_SELF_RESOLVE


def _k_b_beat_chain_with_parent_as_target() -> list[dict[str, str]]:
    """家长被孩子迁怒：孩子拍的目标是家长。"""
    chain = _k_b_beat_chain()
    chain[3] = {"beat": 4, "speaker": "灿灿", "intent": "迁怒：冲爸爸发火", "addressee": "爸爸"}
    return chain


def test_resolve_k_close_mode_disqualifies_b_when_child_targets_parent():
    from app.services.daily_story.story_types.k.close_mode import (
        K_B_DISQUALIFIED,
        resolve_k_close_mode,
    )

    mode = resolve_k_close_mode(
        beat_chain=_k_b_beat_chain_with_parent_as_target(),
        closing_intent="两个孩子停手，看着爸爸狼狈的样子笑了。",
    )
    assert mode == K_B_DISQUALIFIED


def test_resolve_k_close_mode_disqualifies_b_when_closing_presets_parent_harm():
    from app.services.daily_story.story_types.k.close_mode import (
        K_B_DISQUALIFIED,
        resolve_k_close_mode,
    )

    mode = resolve_k_close_mode(
        beat_chain=_k_b_beat_chain(),
        closing_intent="孩子推了妈妈一把，妈妈狼狈地坐在地上。",
    )
    assert mode == K_B_DISQUALIFIED


def test_k_b_guard_ignores_parent_to_child_direction():
    """反向（家长拍的目标是孩子）不由 K-B 负向守卫负责，仍按收场判 K-B。"""
    from app.services.daily_story.story_types.k.close_mode import (
        K_B_CHILD_SELF_RESOLVE,
        resolve_k_close_mode,
    )

    chain = _k_b_beat_chain()
    chain[1] = {"beat": 2, "speaker": "妈妈", "intent": "挡回：把枕头推回给灿灿"}
    mode = resolve_k_close_mode(
        beat_chain=chain,
        closing_intent="妈妈对爸爸说：不掺和就对了。",
    )
    assert mode == K_B_CHILD_SELF_RESOLVE


def test_k_b_guard_ignores_appeal_to_parent():
    """告状/评理把家长当诉求对象，不是攻击目标（家长是第三方）。"""
    from app.services.daily_story.story_types.k.close_mode import (
        K_B_CHILD_SELF_RESOLVE,
        resolve_k_close_mode,
    )

    chain = _k_b_beat_chain()
    chain[2] = {
        "beat": 3,
        "speaker": "昭昭",
        "intent": "告状：喊妈妈他先动手",
        "addressee": "妈妈",
    }
    mode = resolve_k_close_mode(
        beat_chain=chain,
        closing_intent="妈妈对爸爸说：不掺和就对了。",
    )
    assert mode == K_B_CHILD_SELF_RESOLVE


def test_repair_k_row_contract_rejects_k_b_parent_targeted_chain():
    import pytest

    from app.services.gold_story.gold_chat.expand import _repair_k_row_contract

    row = {
        "id": 0,
        "structure_type": "K",
        "mechanism": "M12",
        "payload": {
            "closing_intent": "两个孩子停手，看着爸爸狼狈的样子笑了。",
            "scene_contract": {
                "beat_chain": _k_b_beat_chain_with_parent_as_target(),
                "closing_intent": "两个孩子停手，看着爸爸狼狈的样子笑了。",
            },
        },
    }
    with pytest.raises(ValueError, match="K_B_DISQUALIFIED"):
        _repair_k_row_contract(row)


def test_k_unknown_patch_does_not_inject_advise_fail():
    from app.services.daily_story.story_types.k.patch import patch_k_body

    story = {
        "story_type": "K",
        "k_close_mode": "K_UNKNOWN",
        "dialogue": _k_b_dialogue_ok(),
    }
    patch_k_body(story)
    blob = "".join(d["line"] for d in story["dialogue"])
    assert "别闹了" not in blob
    assert "快分开" not in blob


def test_k_b_validate_rejects_cold_war_despite_punchline():
    story = {
        "story_type": "K",
        "k_close_mode": "K_B_CHILD_SELF_RESOLVE",
        "punchline_explain": "K类：孩子自行恢复互动，勾肩搭背出门",
        "dialogue": [
            {"speaker": "灿灿", "line": "你推我！抢枕头！"},
            {"speaker": "昭昭", "line": "你才推！来啊！"},
            {"speaker": "灿灿", "line": "讨厌！打你！"},
            {"speaker": "昭昭", "line": "妈，评评理！"},
            {"speaker": "妈妈", "line": "不评理，你们自己解决。"},
            {"speaker": "灿灿", "line": "哼，我不理你了！"},
            {"speaker": "昭昭", "line": "谁稀罕！"},
            {"speaker": "灿灿", "line": "不认输！"},
            {"speaker": "昭昭", "line": "我也不让！"},
            {"speaker": "灿灿", "line": "没完就没完！"},
            {"speaker": "昭昭", "line": "谁怕谁！"},
            {"speaker": "灿灿", "line": "别理你！"},
            {"speaker": "昭昭", "line": "我才不理！"},
            {"speaker": "灿灿", "line": "僵持到底！"},
        ],
    }
    errors: list[str] = []
    append_k_body_errors(story, errors)
    assert any("K_B_MISSING" in e or "自行恢复" in e for e in errors)


def test_k_b_validate_passes_self_resolve_dialogue():
    story = {
        "story_type": "K",
        "k_close_mode": "K_B_CHILD_SELF_RESOLVE",
        "punchline_explain": "K类：自行收场",
        "dialogue": _k_b_dialogue_ok(),
    }
    errors: list[str] = []
    append_k_body_errors(story, errors)
    assert not any("K_B_MISSING" in e for e in errors)


def test_k_close_mode_persists_through_export(tmp_path, monkeypatch):
    from app.config import Config
    from app.services.gold_story.gold_chat.export import export_gold_chat_files

    monkeypatch.setattr(
        "app.services.gold_story.gold_chat.export.gold_chat_export_dir",
        lambda _cfg=None: tmp_path,
    )
    row = {
        "id": 0,
        "source_id": "BV_TEST_K_MODE",
        "title": "测试",
        "mechanism": "M12",
        "structure_type": "K",
        "payload": {
            "k_close_mode": "K_B_CHILD_SELF_RESOLVE",
            "scene_contract": {
                "k_close_mode": "K_B_CHILD_SELF_RESOLVE",
                "beat_chain": _k_b_beat_chain(),
            },
        },
    }
    chat = {
        "scene_title": "测试",
        "story_type": "K",
        "k_close_mode": "K_B_CHILD_SELF_RESOLVE",
        "dialogue": _k_b_dialogue_ok(),
    }
    paths = export_gold_chat_files(
        source_id="BV_TEST_K_MODE",
        row=row,
        chat=chat,
        config=Config(),
    )
    import json

    data = json.loads((tmp_path / "BV_TEST_K_MODE.json").read_text(encoding="utf-8"))
    assert data.get("k_close_mode") == "K_B_CHILD_SELF_RESOLVE"
    assert data["daily_story"]["k_close_mode"] == "K_B_CHILD_SELF_RESOLVE"
    assert paths["json"]


def test_finalize_pre_export_kb_preserves_tail():
    """P1：导出前 _k_pin_close 不得把 K-B 尾改成劝失败/僵持。"""
    from app.services.gold_story.gold_chat.finalize import _finalize_k_pre_export

    chat = {
        "story_type": "K",
        "k_close_mode": "K_B_CHILD_SELF_RESOLVE",
        "scene_title": "测试",
        "dialogue": _k_b_dialogue_ok(),
    }
    row = {"title": "测试", "mechanism": "M12", "structure_type": "K"}

    def attach(ch, _row):
        return ch

    def gate(_ch):
        return 75

    out, _ = _finalize_k_pre_export(
        chat,
        row,
        mechanism="M12",
        attach_score=attach,
        gate_score=gate,
    )
    tail = "".join(d["line"] for d in out["dialogue"][-4:])
    assert "一起走" in tail or "还玩" in tail
    assert "不掺和" in tail
    assert "快分开" not in tail
    assert "管不了" not in tail
    assert "不理就不理" not in tail


def test_unknown_patch_preserves_child_reconcile_line():
    """P1：K_UNKNOWN 勿把「咱们和好，一起走吧」改成僵持。"""
    from app.services.daily_story.story_types.k.patch import patch_k_body

    story = {
        "story_type": "K",
        "k_close_mode": "K_UNKNOWN",
        "dialogue": [
            {"speaker": "灿灿", "line": "你推我！"},
            {"speaker": "昭昭", "line": "你还推！"},
            {"speaker": "灿灿", "line": "讨厌！"},
            {"speaker": "昭昭", "line": "妈，评评理！"},
            {"speaker": "妈妈", "line": "不评理。"},
            {"speaker": "灿灿", "line": "哼！"},
            {"speaker": "昭昭", "line": "你还敢！"},
            {"speaker": "灿灿", "line": "来啊！"},
            {"speaker": "昭昭", "line": "咱们和好，一起走吧。"},
            {"speaker": "灿灿", "line": "行啊一起走！"},
            {"speaker": "妈妈", "line": "不掺和就对了。"},
        ],
    }
    patch_k_body(story)
    blob = "".join(d["line"] for d in story["dialogue"])
    assert "咱们和好，一起走吧" in blob
    assert "我才不理你" not in blob


def test_structure_hint_kb_no_stalemate_contradiction():
    from app.services.gold_story.gold_chat.type_bridge import structure_type_hint

    hint = structure_type_hint(
        structure_type="K",
        mechanism="M12",
        k_close_mode="K_B_CHILD_SELF_RESOLVE",
    )
    assert "孩子自行恢复互动" in hint
    assert "收束须僵持不和好" not in hint
    assert "大人躲/叹/劝失败" not in hint or "禁止" in hint


def test_k_b_validate_passes_child_led_hehao_not_h_ritual():
    """孩子末段「咱们和好」不得被 RE_H_RITUAL 误杀。"""
    story = {
        "story_type": "K",
        "k_close_mode": "K_B_CHILD_SELF_RESOLVE",
        "punchline_explain": "K类：自行收场",
        "dialogue": [
            {"speaker": "灿灿", "line": "你推我！抢枕头！"},
            {"speaker": "昭昭", "line": "你才推！来啊！"},
            {"speaker": "灿灿", "line": "讨厌！打你！"},
            {"speaker": "昭昭", "line": "妈，评评理！"},
            {"speaker": "妈妈", "line": "不评理，你们自己解决。"},
            {"speaker": "灿灿", "line": "哼！"},
            {"speaker": "昭昭", "line": "你还敢！"},
            {"speaker": "灿灿", "line": "来啊！"},
            {"speaker": "昭昭", "line": "咱们和好，一起走吧。"},
            {"speaker": "灿灿", "line": "行啊一起走！"},
            {"speaker": "妈妈", "line": "不掺和就对了。"},
        ],
    }
    errors: list[str] = []
    append_k_body_errors(story, errors)
    assert errors == []


def test_resolve_check_accepts_short_yes_after_invite():
    from app.services.daily_story.story_types.k.resolve_check import (
        kid_self_resolve_in_tail,
    )

    assert kid_self_resolve_in_tail(
        ["昭昭", "灿灿"],
        ["吃不吃冰棍？", "要。"],
    )


def test_resolve_check_rejects_invite_then_refusal():
    from app.services.daily_story.story_types.k.resolve_check import (
        kid_self_resolve_in_tail,
    )

    speakers = [
        "灿灿",
        "昭昭",
        "灿灿",
        "昭昭",
        "灿灿",
        "昭昭",
    ]
    lines = [
        "哼！",
        "你还敢！",
        "来啊！",
        "还玩不玩？",
        "不要，我拒绝。",
        "谁怕谁！",
    ]
    assert not kid_self_resolve_in_tail(speakers, lines)
    assert not kid_self_resolve_in_tail(
        ["昭昭", "灿灿"],
        ["还玩不玩？", "不要，我才不跟你一起玩！"],
    )


def test_k_b_score_punchline_allows_child_hehao():
    from app.services.daily_story.story_types.k.quality import score_punchline

    story = {
        "story_type": "K",
        "k_close_mode": "K_B_CHILD_SELF_RESOLVE",
        "dialogue": _k_b_dialogue_ok(),
    }
    lines = [d["line"] for d in story["dialogue"]]
    sp = [d["speaker"] for d in story["dialogue"]]
    lines[-4] = "咱们和好，一起走吧。"
    bonus, details = score_punchline(lines, sp, "", "", story=story)
    assert bonus > 0
    assert not any("H仪式" in d for d in details)


def test_k_b_score_punchline_no_bonus_on_rejected_invite():
    from app.services.daily_story.story_types.k.quality import score_punchline

    dialogue = [
        {"speaker": "灿灿", "line": "你推我！抢枕头！"},
        {"speaker": "昭昭", "line": "你才推！来啊！"},
        {"speaker": "灿灿", "line": "讨厌！打你！"},
        {"speaker": "昭昭", "line": "妈，评评理！"},
        {"speaker": "妈妈", "line": "不评理，别找我评。"},
        {"speaker": "灿灿", "line": "哼！"},
        {"speaker": "昭昭", "line": "你还敢！"},
        {"speaker": "灿灿", "line": "来啊！"},
        {"speaker": "昭昭", "line": "还玩不玩？"},
        {"speaker": "灿灿", "line": "不要，我才不跟你一起玩！"},
        {"speaker": "妈妈", "line": "不掺和就对了。"},
    ]
    lines = [d["line"] for d in dialogue]
    sp = [d["speaker"] for d in dialogue]
    story = {"story_type": "K", "k_close_mode": "K_B_CHILD_SELF_RESOLVE"}
    bonus, details = score_punchline(lines, sp, "", "", story=story)
    assert "孩子自行恢复互动" not in details or bonus <= 4


def test_k_b_validate_rejects_parent_invite_kid_reject():
    story = {
        "story_type": "K",
        "k_close_mode": "K_B_CHILD_SELF_RESOLVE",
        "dialogue": [
            {"speaker": "灿灿", "line": "你推我！抢枕头！"},
            {"speaker": "昭昭", "line": "你才推！来啊！"},
            {"speaker": "灿灿", "line": "讨厌！打你！"},
            {"speaker": "昭昭", "line": "妈，评评理！"},
            {"speaker": "妈妈", "line": "不评理，别找我评。"},
            {"speaker": "灿灿", "line": "哼！"},
            {"speaker": "昭昭", "line": "你还敢！"},
            {"speaker": "灿灿", "line": "来啊！"},
            {"speaker": "妈妈", "line": "你们一起去玩吧。"},
            {"speaker": "昭昭", "line": "不要，我拒绝。"},
            {"speaker": "灿灿", "line": "我也不去！"},
            {"speaker": "妈妈", "line": "不掺和就对了。"},
            {"speaker": "昭昭", "line": "谁稀罕！"},
            {"speaker": "灿灿", "line": "不理你！"},
        ],
    }
    errors: list[str] = []
    append_k_body_errors(story, errors)
    assert any("K_B" in e for e in errors)


def test_k_b_validate_rejects_parent_narrator_close():
    story = {
        "story_type": "K",
        "k_close_mode": "K_B_CHILD_SELF_RESOLVE",
        "dialogue": _k_b_dialogue_ok(),
    }
    story["dialogue"][-1] = {
        "speaker": "妈妈",
        "line": "不掺和就对了，你看他俩自己就好了。",
    }
    errors: list[str] = []
    append_k_body_errors(story, errors)
    assert any("自言自语" in e or "解说" in e for e in errors)


def test_k_b_patch_rewrites_narrator_close_to_mutter():
    from app.services.daily_story.story_types.k.patch import patch_k_body

    story = {
        "story_type": "K",
        "k_close_mode": "K_B_CHILD_SELF_RESOLVE",
        "closing_intent": "妈妈放下碗对爸爸说：不掺和就对了。",
        "dialogue": _k_b_dialogue_ok(),
    }
    story["dialogue"][-1] = {
        "speaker": "妈妈",
        "line": "跟孩他爸说，不掺和就对了，咱俩别插手。",
    }
    patch_k_body(story)
    last = story["dialogue"][-1]["line"]
    assert "爸" not in last
    assert "你看" not in last
    assert "不掺和" in last
    errors: list[str] = []
    append_k_body_errors(story, errors)
    assert not any("自言自语" in e for e in errors)


def test_k_b_patch_inserts_self_resolve_when_missing():
    from app.services.daily_story.story_types.k.patch import patch_k_body

    story = _k_stalemate_story()
    story["k_close_mode"] = "K_B_CHILD_SELF_RESOLVE"
    story["dialogue"] = story["dialogue"][:12]
    story["dialogue"][-1] = {"speaker": "妈妈", "line": "不掺和就对了。"}
    patch_k_body(story)
    blob = "".join(d["line"] for d in story["dialogue"])
    assert "还玩不玩" in blob or "吃不吃" in blob
    errors: list[str] = []
    append_k_body_errors(story, errors)
    assert not any("K_B_MISSING" in e for e in errors)


def test_k_b_collapse_keeps_last_resolve_invite_only():
    from app.services.daily_story.story_types.k.patch import patch_k_body

    dlg = _k_b_dialogue_ok()[:-1] + [
        {"speaker": "昭昭", "line": "姐姐，吃不吃冰棍呀？"},
        {"speaker": "灿灿", "line": "来啊！谁怕谁吧！"},
        {"speaker": "昭昭", "line": "咱俩一起走啊！"},
        {"speaker": "灿灿", "line": "我也不让，你服不服！"},
        {"speaker": "昭昭", "line": "还玩不玩？一起吧。"},
        {"speaker": "灿灿", "line": "行啊！一起玩！"},
        {"speaker": "妈妈", "line": "不掺和就对了。"},
    ]
    story = {
        "story_type": "K",
        "k_close_mode": "K_B_CHILD_SELF_RESOLVE",
        "closing_intent": "不掺和就对了。",
        "dialogue": dlg,
    }
    patch_k_body(story)
    blob = "".join(d["line"] for d in story["dialogue"])
    assert "吃不吃冰棍" not in blob
    assert "还玩不玩" in blob
    assert blob.count("谁怕谁") <= 2


def test_k_b_weak_lai_a_counts_as_accept_after_food_invite():
    from app.services.daily_story.story_types.k.resolve_check import (
        kid_self_resolve_in_tail,
    )

    assert kid_self_resolve_in_tail(
        ["昭昭", "灿灿"],
        ["吃不吃冰棍？", "来啊！谁怕谁吧！"],
    )


def test_k_b_structure_escalation_uses_four_kb_layers_not_advise_fail():
    from app.services.daily_story.quality import score_daily_story

    story = {
        "story_type": "K",
        "k_close_mode": "K_B_CHILD_SELF_RESOLVE",
        "conflict_core": "昭昭和灿灿扭打，妈妈旁观。",
        "punchline_explain": "K类：旁观后自行和好。",
        "dialogue": _k_b_dialogue_ok(),
    }
    q = score_daily_story(story, skip_relevancy=True)
    assert q["structure_score"] == 80
    assert not any("冲突推进不足" in r for r in q.get("reasons") or [])


def test_k_a_object_damage_counts_as_real_escalation_layer():
    from app.services.daily_story.quality import score_daily_story

    story = {
        "story_type": "K",
        "k_close_mode": "K_A_PARENT_FAIL_STALEMATE",
        "conflict_core": "姐弟争抢同一个东西，妈妈劝不动。",
        "punchline_explain": "K类：大人想止争，结果争抢把东西扯坏，最后仍僵持。",
        "dialogue": [
            {"speaker": "昭昭", "line": "这是我的，你别抢！"},
            {"speaker": "灿灿", "line": "明明我先抓到的，松手！"},
            {"speaker": "昭昭", "line": "我就抓着，你拿不走！"},
            {"speaker": "灿灿", "line": "你才该松手，给我！"},
            {"speaker": "昭昭", "line": "哎呀，被你扯成两半了！"},
            {"speaker": "灿灿", "line": "大的那半归我，你别碰！"},
            {"speaker": "妈妈", "line": "你们别抢了，先分开。"},
            {"speaker": "昭昭", "line": "我不让，大的明明是我的！"},
            {"speaker": "灿灿", "line": "我也不让，你别想拿走！"},
            {"speaker": "妈妈", "line": "唉，我管不了你们了。"},
            {"speaker": "昭昭", "line": "哼，我就不理你！"},
            {"speaker": "灿灿", "line": "不理就不理，谁怕谁！"},
        ],
    }
    q = score_daily_story(story, skip_relevancy=True)
    assert not any("冲突推进不足" in r for r in q.get("reasons") or [])


def test_k_b_p1_fixes_incite_fragment_and_defiance():
    from app.services.daily_story.story_types.k.patch import patch_k_body
    from app.services.daily_story.story_types.k.validate import append_k_body_errors

    dlg = [
        {"speaker": "昭昭", "line": "妈！姐姐先动手的，她抢我积木还推我！"},
        {"speaker": "妈妈", "line": "不评理。我吃饭呢，你俩接着打！"},
        {"speaker": "灿灿", "line": "妈——他踢我！呜，谁怕谁啊…了呢…"},
        {"speaker": "妈妈", "line": "不能哭。墙上有规矩，自己看。"},
        {"speaker": "昭昭", "line": "你别想让我认输，这事还没完！"},
        {"speaker": "灿灿", "line": "没完就没完，我也不会让你！"},
        {"speaker": "昭昭", "line": "你再说一遍试试，我就是不服！"},
        {"speaker": "灿灿", "line": "说就说，谁怕谁啊！"},
        {"speaker": "昭昭", "line": "你胡说，明明是你先拿我蓝的换吧！"},
        {"speaker": "灿灿", "line": "你得意什么，我也不认输！"},
        {"speaker": "昭昭", "line": "再来，你试试看啊！"},
        {"speaker": "灿灿", "line": "你过来试试，看我不挠你啊！"},
        {"speaker": "昭昭", "line": "姐，吃不吃冰棍呢！"},
        {"speaker": "灿灿", "line": "要！给我拿一根啊！"},
        {"speaker": "妈妈", "line": "不掺和就对了。"},
    ]
    story = {
        "story_type": "K",
        "k_close_mode": "K_B_CHILD_SELF_RESOLVE",
        "closing_intent": "不掺和就对了。",
        "dialogue": dlg,
    }
    patch_k_body(story)
    mom2 = next(d["line"] for d in story["dialogue"] if d["speaker"] == "妈妈")
    assert "接着打" not in mom2
    blob = "".join(d["line"] for d in story["dialogue"])
    assert "…了呢" not in blob
    assert "换吧" not in blob
    assert "换的" in blob or "蓝的" in blob
    errors: list[str] = []
    append_k_body_errors(story, errors)
    assert not any("怂恿" in e or "破碎" in e for e in errors)


def test_k_b_skips_loser_monotonic_even_after_mom_tears_line():
    from app.services.daily_story.story_types.k.patch import patch_k_body

    story = {
        "story_type": "K",
        "k_close_mode": "K_B_CHILD_SELF_RESOLVE",
        "conflict_core": "昭昭和灿灿扭打，妈妈旁观。",
        "closing_intent": "不掺和就对了。",
        "dialogue": _k_b_dialogue_ok(),
    }
    story["dialogue"][5] = {"speaker": "妈妈", "line": "不能哭，眼泪收回去。"}
    story["dialogue"][7] = {"speaker": "昭昭", "line": "你别过来，你试试看啊！"}
    patch_k_body(story)
    assert story["dialogue"][7]["line"] != "呜，你欺负人！"


def test_k_b_compress_drops_repeated_kid_line_not_fixed_swap():
    from app.services.daily_story.story_types.k.patch import patch_k_body

    dlg = [
        {"speaker": "灿灿", "line": "你站住！这事还没完啊！"},
        {"speaker": "昭昭", "line": "是你先拽我衣服的！枕头还我啊！"},
        {"speaker": "灿灿", "line": "你再闹试试！"},
        {"speaker": "昭昭", "line": "妈！姐姐先动手的，你管不管她！"},
        {"speaker": "灿灿", "line": "妈你看他踢我！呜……我胳膊都红！"},
        {"speaker": "妈妈", "line": "不能哭。规矩刚说完，眼泪收回去。"},
        {"speaker": "昭昭", "line": "你别想让我认输，这事还没完！"},
        {"speaker": "灿灿", "line": "说就说，谁怕谁啊！"},
        {"speaker": "昭昭", "line": "呜，你欺负人！"},
        {"speaker": "灿灿", "line": "我也不让，咱们就这么僵着！"},
        {"speaker": "昭昭", "line": "呜，你欺负人！"},
        {"speaker": "灿灿", "line": "打累了，我喘口气再跟你算账，别跑啊！"},
        {"speaker": "昭昭", "line": "呜，你欺负人！"},
        {"speaker": "灿灿", "line": "还玩不玩？一起吧。"},
        {"speaker": "昭昭", "line": "行啊！一起玩！"},
        {"speaker": "妈妈", "line": "不掺和就对了。"},
    ]
    story = {
        "story_type": "K",
        "k_close_mode": "K_B_CHILD_SELF_RESOLVE",
        "closing_intent": "不掺和就对了。",
        "dialogue": dlg,
    }
    patch_k_body(story)
    blob = "".join(d["line"] for d in story["dialogue"])
    assert blob.count("呜，你欺负人") <= 1
    assert "还玩不玩" in blob


def test_k_b_parent_short_buchanhe_expanded_to_mutter():
    from app.services.daily_story.story_types.k.patch import patch_k_body

    story = {
        "story_type": "K",
        "k_close_mode": "K_B_CHILD_SELF_RESOLVE",
        "closing_intent": "妈妈对爸爸说：不掺和就对了。",
        "dialogue": _k_b_dialogue_ok(),
    }
    story["dialogue"][-1] = {"speaker": "妈妈", "line": "不掺和就对了。"}
    patch_k_body(story)
    assert "……" in story["dialogue"][-1]["line"] or "自己弄" in story["dialogue"][-1]["line"]


def test_k_patch_strips_goujian_narration_in_dialogue():
    from app.services.daily_story.story_types.k.patch import patch_k_body

    story = {
        "story_type": "K",
        "k_close_mode": "K_B_CHILD_SELF_RESOLVE",
        "dialogue": _k_b_dialogue_ok(),
    }
    story["dialogue"][-3] = {
        "speaker": "昭昭",
        "line": "勾肩搭背，咱俩一起去，快点啊！",
    }
    patch_k_body(story)
    line = story["dialogue"][-3]["line"]
    assert "勾肩" not in line
    assert "一起" in line


def test_k_b_patch_grounds_ungrounded_punchline():
    from app.services.daily_story.story_types.k.patch import patch_k_body

    story = {
        "story_type": "K",
        "k_close_mode": "K_B_CHILD_SELF_RESOLVE",
        "punchline_explain": "K类：扭打后勾肩搭背吃冰棍。",
        "dialogue": _k_b_dialogue_ok(),
    }
    patch_k_body(story)
    assert "勾肩搭背" not in story["punchline_explain"]
    assert "自行收场" in story["punchline_explain"]


def test_self_name_legal_not_suspicion():
    from app.services.daily_story.story_types.k.dialogue_quality import (
        collect_k_dialogue_suspicions,
    )

    assert not collect_k_dialogue_suspicions(["我叫昭昭，我才不怕！"], ["昭昭"])
    assert collect_k_dialogue_suspicions(["昭昭你等着说呀！"], ["昭昭"])


def _k_b_tail_duplicate_dialogue() -> list[dict[str, str]]:
    """末段接住句与更早某句逐字重复的 K-B 稿（抽象场景，不含单篇词）。"""
    lines = [
        ("灿灿", "你别动我的东西，这是我先拿到手的玩具啊！"),
        ("灿灿", "行啊！一起玩！"),
        ("昭昭", "谁先拿到就算谁的，你可千万不要再赖皮了。"),
        ("灿灿", "我才没有赖皮，明明就是你先动手推我的呀。"),
        ("昭昭", "你再推我一下试试看，我可是一点都不怕你的。"),
        ("灿灿", "你先动手打我的，我现在就要去告诉妈妈了啊。"),
        ("妈妈", "不评理，规矩都写在墙上了，你们自己看着办。"),
        ("昭昭", "哼，那我也绝对不会让着你的，你等着瞧吧！"),
        ("灿灿", "我也不让，看你能把我怎么样，有本事试试啊！"),
        ("昭昭", "你再说一遍我就真的动手了，到时候别怪我！"),
        ("灿灿", "来啊，谁怕谁啊，我可是真的一点都不怕你呢！"),
        ("昭昭", "……姐姐，还玩不玩？我们两个一起接着玩吧。"),
        ("灿灿", "行啊！一起玩！"),
        ("妈妈", "不掺和就对了，让他们自己慢慢弄去吧，嗯。"),
    ]
    return [{"speaker": sp, "line": ln} for sp, ln in lines]


def test_k_b_dedupe_keeps_self_resolve_tail_by_dropping_earlier_duplicate():
    """近义句去重不得拆掉已成立的 K-B「孩子自行恢复互动」末段。

    该补丁跑在 patch_k_b_ensure_self_resolve_tail 之后，会按归一化整句去重；
    末段的接住句若与更早某句重复，删「后出现」会只剩邀约句 → punchline 归零。
    与「字数过砍就不改」同构：优化补丁不得破坏已成立的收束不变量——正确做法是
    改删同组更早的那句（保留承载不变量的后句），而不是整批放弃留下重复句。
    """
    from app.services.daily_story.story_types.k.patch import (
        patch_k_dedupe_near_lines,
    )
    from app.services.daily_story.story_types.k.resolve_check import (
        kid_self_resolve_in_tail,
    )

    dialogue = _k_b_tail_duplicate_dialogue()

    def _tail_ok(rows: list[dict[str, str]]) -> bool:
        return kid_self_resolve_in_tail(
            [row["speaker"] for row in rows],
            [row["line"] for row in rows],
        )

    story = {
        "story_type": "K",
        "k_close_mode": "K_B_CHILD_SELF_RESOLVE",
        "dialogue": [dict(row) for row in dialogue],
    }
    assert _tail_ok(story["dialogue"]), "前提：去重前末段不变量已成立"

    notes = patch_k_dedupe_near_lines(story)

    assert notes == ["K近义句去重×1"], "应改删更早的重复句，而不是整批跳过"
    assert _tail_ok(story["dialogue"]), "末段不变量必须保持成立"
    assert len(story["dialogue"]) == len(dialogue) - 1
    # 保留的是承载不变量的「后出现」接住句，删掉的是更早的孤儿同义句
    carriers = [
        i for i, row in enumerate(story["dialogue"]) if row["line"] == "行啊！一起玩！"
    ]
    assert len(carriers) == 1
    assert story["dialogue"][carriers[0] - 1]["line"].startswith("……姐姐，还玩不玩")


def test_k_a_dedupe_still_drops_duplicate_lines():
    """非 K-B 不受守卫影响：重复句照常去重（守卫不是一概不删）。"""
    from app.services.daily_story.story_types.k.patch import (
        patch_k_dedupe_near_lines,
    )
    from app.services.daily_story.story_types.k.resolve_check import (
        kid_self_resolve_in_tail,
    )

    dialogue = _k_b_tail_duplicate_dialogue()
    story = {
        "story_type": "K",
        "k_close_mode": "K_A_PARENT_FAIL_STALEMATE",
        "dialogue": [dict(row) for row in dialogue],
    }
    before = len(story["dialogue"])

    notes = patch_k_dedupe_near_lines(story)

    assert notes, "K-A 路径应照常去重"
    assert len(story["dialogue"]) < before
    # 同一段稿在 K-B 下是「不变量已成立」的，K-A 下本就无需保护
    assert not kid_self_resolve_in_tail(
        [row["speaker"] for row in story["dialogue"]],
        [row["line"] for row in story["dialogue"]],
    )



# K-B 家长立场回归集（专家裁决：词表只做高精度预筛，抽象行为立场才是判据）。
# 正/负例只断言不变量，不绑定任何单篇剧情字面。
_KB_PARENT_STANCE_PASS_CASES = [
    "我不喊了，你们自己玩",
    "我当没看见",
    "我不裁判，谁对谁错你们自己说",
    "我吃瓜，别问我",
    "我退出，别找我",
    "别推了，我拉架",
    "你们俩自己看着办",
]

_KB_PARENT_STANCE_FAIL_CASES = [
    "灿灿你不对，道歉",
    "昭昭你赢了",
    "我也来推",
    "看我不收拾你",
]


def _k_b_dialogue_with_parent_line(parent_line: str) -> list[dict[str, str]]:
    dialogue = [
        dict(item)
        for item in _k_b_dialogue_ok()
        if item["speaker"] not in ("妈妈", "爸爸")
    ]
    dialogue.insert(4, {"speaker": "妈妈", "line": parent_line})
    return dialogue


def _k_b_parent_body_errors(parent_line: str) -> list[str]:
    story = {
        "story_type": "K",
        "k_close_mode": "K_B_CHILD_SELF_RESOLVE",
        "punchline_explain": "K类：孩子自行恢复互动",
        "dialogue": _k_b_dialogue_with_parent_line(parent_line),
    }
    errors: list[str] = []
    append_k_body_errors(story, errors)
    return errors


def test_k_b_parent_non_intervention_stance_accepts_synonyms():
    for parent_line in _KB_PARENT_STANCE_PASS_CASES:
        errors = _k_b_parent_body_errors(parent_line)
        assert not any("正文须有家长挡回" in e for e in errors), parent_line


def test_k_b_parent_adjudication_stance_still_rejected():
    for parent_line in _KB_PARENT_STANCE_FAIL_CASES:
        errors = _k_b_parent_body_errors(parent_line)
        assert any("正文须有家长挡回" in e for e in errors), parent_line
