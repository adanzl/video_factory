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
        ("妈妈", "你看，不掺和就对了。"),
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
