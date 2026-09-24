"""gold_chat 转换测试。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.gold_story.gold_chat import convert as gc
from app.services.gold_story.gold_chat import expand as gex
from app.services.gold_story.gold_chat import finalize as gcf
from app.services.gold_story.gold_chat import refine as grf
from app.services.gold_story.gold_chat import export as gce


def _sample_row() -> dict:
    return {
        "id": 1,
        "source_id": "BV1TEST0001",
        "url": "https://www.bilibili.com/video/BV1TEST0001",
        "title": "测试标题",
        "mechanism": "M6",
        "structure_type": "A",
        "status": "active",
        "conflict_core": "弟弟幻想报复姐姐，开门秒怂",
        "payload": {
            "setting": "卧室门口",
            "beat": ["被欺负", "关门幻想", "开门怂", "姐姐得意"],
            "dialogue_seed": [
                {"speaker": "昭昭", "intent": "抱怨被欺负"},
                {"speaker": "灿灿", "intent": "得意威胁"},
            ],
            "closing_intent": "昭昭缩回角落",
            "banned_literals": ["小姨", "萌娃"],
            "funny_why": "幻想与怂的反差",
        },
    }


def _sample_chat() -> dict:
    lines = [
        {"speaker": "昭昭", "line": "你刚才又抢我遥控器，我还不敢说。"},
        {"speaker": "灿灿", "line": "谁让你手慢，我先用就是我的。"},
        {"speaker": "昭昭", "line": "那我关上门，我在里面练功夫，等会儿打回来。"},
        {"speaker": "灿灿", "line": "你练啊，开门我看你还敢不敢。"},
        {"speaker": "昭昭", "line": "我……我先看看你在不在门口。"},
        {"speaker": "灿灿", "line": "在啊，你出来试试。"},
        {"speaker": "昭昭", "line": "算了算了，我先不跟你计较。"},
        {"speaker": "灿灿", "line": "刚才不是说要打回来吗？"},
        {"speaker": "昭昭", "line": "我就是先歇一会儿，又不是怕你。"},
        {"speaker": "灿灿", "line": "那你把门打开，别躲里面。"},
        {"speaker": "昭昭", "line": "不开，我要再练两招。"},
        {"speaker": "灿灿", "line": "行，你练，我等着。"},
        {"speaker": "昭昭", "line": "好了好了，遥控器还你一半行吧。"},
        {"speaker": "灿灿", "line": "这还差不多，明天继续。"},
    ]
    while gc.dialogue_total_chars({"dialogue": lines}) < 240:
        lines.append(
            {
                "speaker": "昭昭",
                "line": "我就是先歇一会儿，又不是怕你。",
            }
        )
    return {
        "scene_title": "关门练功",
        "setting": "卧室门口",
        "key": "关门练功",
        "conflict_core": "弟弟幻想报复姐姐，开门秒怂",
        "dialogue": lines,
        "punchline_explain": "A类嘴硬加码：幻想英勇开门就怂",
    }


def test_validate_gold_chat_ok():
    story = _sample_chat()
    gc.validate_gold_chat(story, banned_literals=["小姨"])


def test_ensure_gold_chat_min_chars_pads_short_story():
    """near-miss（差 ≤40）可本地垫满；大缺口不硬凑。"""
    story = {
        "story_type": "J",
        "dialogue": [
            {"speaker": "昭昭", "line": "这是我的地盘，你快走开听见没有呀真的！"},
            {"speaker": "灿灿", "line": "我先趴在这儿的，该你马上走开听见没有！"},
            {"speaker": "昭昭", "line": "哼，看招，我先推你一下试试看啊真的！"},
            {"speaker": "灿灿", "line": "你敢打我，我就马上告诉妈妈去啊真的！"},
            {"speaker": "昭昭", "line": "就打你，你抢了我的位置啊真的不行！"},
            {"speaker": "灿灿", "line": "谁赢谁说了算，咱们现在来比呀啊！"},
            {"speaker": "昭昭", "line": "我拿出最强形态，再出拳打你啊听见！"},
            {"speaker": "灿灿", "line": "草莓熊肘击，我砸你肚子一下听清楚！"},
            {"speaker": "昭昭", "line": "哎哟我输了，你也太厉害啦呀真的！"},
            {"speaker": "灿灿", "line": "玩具都归我，你到那边去躺着吧啊！"},
            {"speaker": "昭昭", "line": "等长大再算账，我现在怕你啊真的！"},
            {"speaker": "灿灿", "line": "我说了算，你乖乖躺好别动呀听见！"},
        ],
    }
    chars = gc.dialogue_total_chars(story)
    assert chars < gc.DAILY_STORY_BODY_CHARS_MIN
    assert gc.DAILY_STORY_BODY_CHARS_MIN - chars <= gc.GOLD_CHAT_NEAR_MISS_DEFICIT_MAX
    out, changed = gc._ensure_gold_chat_min_chars(story)
    assert changed
    assert gc.dialogue_total_chars(out) >= gc.DAILY_STORY_BODY_CHARS_MIN

    # 大缺口：剥灌尾后不靠粒子硬凑到 240（仍可中段加句，但空短稿不够）
    short = {
        "story_type": "J",
        "dialogue": [
            {"speaker": "昭昭", "line": "看招！"},
            {"speaker": "灿灿", "line": "谁赢谁说了算！"},
        ]
        * 6,
    }
    out_short, _ = gc._ensure_gold_chat_min_chars(short)
    assert gc.dialogue_total_chars(out_short) < gc.DAILY_STORY_BODY_CHARS_MIN


def test_validate_gold_chat_rejects_banned():
    story = _sample_chat()
    story["dialogue"][0]["line"] = "小姨又欺负我"
    with pytest.raises(ValueError, match="禁词"):
        gc.validate_gold_chat(story, banned_literals=["小姨"])


def test_validate_gold_chat_rejects_relay_and_paren():
    story = _sample_chat()
    story["dialogue"][0]["line"] = "妈妈说了，抢不过就躲着点。"
    with pytest.raises(ValueError, match="转述"):
        gc.validate_gold_chat(story)
    story["dialogue"][0]["line"] = "（从厨房走出来）昭昭，你说啥？"
    with pytest.raises(ValueError, match="括号"):
        gc.validate_gold_chat(story)


def test_normalize_chat_speakers_keeps_father():
    story = _sample_chat()
    story["dialogue"][0]["speaker"] = "爸爸"
    out = gc._normalize_chat_speakers(story)
    assert out["dialogue"][0]["speaker"] == "爸爸"


def test_normalize_chat_speakers_father_alias_to_dad():
    story = _sample_chat()
    story["dialogue"][0]["speaker"] = "老爸"
    out = gc._normalize_chat_speakers(story)
    assert out["dialogue"][0]["speaker"] == "爸爸"


def test_gate_gold_chat_structure_score_raises_when_low():
    with pytest.raises(ValueError, match=r"structure_score:63"):
        gc._gate_gold_chat_structure_score(
            {"quality": {"structure_score": 63, "score": 63}}
        )


def test_gate_gold_chat_structure_score_ok():
    assert gc._gate_gold_chat_structure_score(
        {"quality": {"structure_score": 80, "score": 80}}
    ) == 80


def test_lift_structure_second_prompt_includes_previous_validation_error():
    """定点修稿第二轮须带上轮校验/门控错误，勿只重复结构分反馈。"""
    prompts: list[str] = []
    chat = _sample_chat()
    chat["quality"] = {
        "structure_score": 60,
        "score": 60,
        "reasons": ["无破功软收"],
    }
    row = _sample_row()

    def fake_fix(_chat: dict, fb: str, **_kwargs: object) -> dict:
        prompts.append(fb)
        out = dict(_chat)
        if len(prompts) == 1:
            raise ValueError("正文总字数须≥240")
        out["quality"] = {"structure_score": 80, "score": 80, "reasons": []}
        return out

    out, struct = gcf._lift_gold_chat_structure_with_llm(
        chat,
        row,
        st_final="N",
        mech="M6",
        banned=[],
        mom_max=1,
        attach_score=lambda c, _r: c,
        gate_score=lambda _c: 80,
        normalize_chat=lambda c: c,
        fix_llm=fake_fix,
        validate_chat=lambda _c: None,
        max_attempts=2,
    )
    assert struct == 80
    assert len(prompts) == 2
    assert "正文总字数须≥240" in prompts[1]
    assert "上一轮未过" in prompts[1]
    assert out["quality"]["structure_score"] == 80


def test_attach_gold_chat_structure_score_writes_quality():
    row = _sample_row()
    chat = _sample_chat()
    out = gc._attach_gold_chat_structure_score(chat, row)
    assert isinstance(out.get("quality"), dict)
    assert out["story_type"] == "A"
    assert "structure_score" in out["quality"]


def _bypass_structure_gate(monkeypatch):
    monkeypatch.setattr(
        gc,
        "_attach_gold_chat_structure_score",
        lambda chat, _row: {
            **chat,
            "quality": {"structure_score": 80, "score": 80, "summary": "结构80"},
        },
    )
    monkeypatch.setattr(gc, "_gate_gold_chat_structure_score", lambda _chat: 80)
    # 测试夹具对白过不了 A–L 契约机审；跳过精修对齐
    monkeypatch.setattr(gc, "refine_gold_chat_align", lambda story, **_kw: story)
    monkeypatch.setattr(grf, "refine_gold_chat_align", lambda story, **_kw: story)


def test_gold_story_to_gold_chat_retries_when_one_line_short(monkeypatch):
    """差 1 句：不本地硬插注水句；须 FIX 扩写或扩写重抽。"""
    calls: dict[str, int | bool] = {"n": 0}
    _bypass_structure_gate(monkeypatch)

    def fake_chat(system: str, _user: str, **_kwargs) -> dict:
        if "编辑" in system:
            calls["fix"] = True
            return _sample_chat()
        calls["n"] = int(calls["n"]) + 1
        chat = _sample_chat()
        if int(calls["n"]) == 1:
            chat["dialogue"] = chat["dialogue"][:11]
        return chat

    monkeypatch.setattr(gc, "_chat_json", fake_chat)
    monkeypatch.setattr(gex, "_chat_json", fake_chat)
    monkeypatch.setattr(gc, "EXPAND_CANDIDATE_COUNT", 1)
    monkeypatch.setattr(gex, "EXPAND_CANDIDATE_COUNT", 1)
    monkeypatch.setattr(gc, "EXPAND_REGENERATE_MAX", 5)
    monkeypatch.setattr(gex, "EXPAND_REGENERATE_MAX", 5)
    out = gc.gold_story_to_gold_chat(_sample_row())
    assert len(out["dialogue"]) >= 12
    blob = "".join(str(d.get("line") or "") for d in out["dialogue"])
    assert "你给我听好了" not in blob


def test_gold_story_to_gold_chat_rejects_when_far_too_short(monkeypatch):
    _bypass_structure_gate(monkeypatch)

    def fake_chat(_system: str, _user: str, **_kwargs) -> dict:
        bad = _sample_chat()
        bad["dialogue"] = bad["dialogue"][:2]
        return bad

    monkeypatch.setattr(gc, "_chat_json", fake_chat)
    monkeypatch.setattr(gex, "_chat_json", fake_chat)
    monkeypatch.setattr(gc, "EXPAND_CANDIDATE_COUNT", 1)
    monkeypatch.setattr(gex, "EXPAND_CANDIDATE_COUNT", 1)
    with pytest.raises(ValueError, match="篇幅驳回"):
        gc.gold_story_to_gold_chat(_sample_row())


def test_bump_short_regen_helpers():
    err11 = "对白句数须≥12，当前11; 正文总字数须≥240，当前155"
    assert gc._is_regenerable_line_short_error(err11)
    assert gc._bump_short_regen_or_reject(err11, 0) == 1
    assert gc._bump_short_regen_or_reject(err11, 2) == 3
    with pytest.raises(ValueError, match="重生成3次仍不达标"):
        gc._bump_short_regen_or_reject(err11, 3)
    err10 = "对白句数须≥12，当前10"
    assert gc._is_regenerable_line_short_error(err10)
    assert gc._bump_short_regen_or_reject(err10, 0) == 1
    err9 = "对白句数须≥12，当前9"
    assert gc._is_regenerable_line_short_error(err9)
    err8 = "对白句数须≥12，当前8"
    assert not gc._is_regenerable_line_short_error(err8)
    with pytest.raises(ValueError, match="本地垫字仍不足"):
        gc._bump_short_regen_or_reject(err8, 0)
    # 字数 near-miss / 大缺口均可重生成（勿立刻「本地垫字仍不足」）
    err_chars = "正文总字数须≥240，当前235"
    assert gc._char_deficit_from_error(err_chars) == 5
    assert gc._is_regenerable_short_error(err_chars)
    assert gc._bump_short_regen_or_reject(err_chars, 0) == 1
    err_short = "正文总字数须≥240，当前117"
    assert gc._is_regenerable_short_error(err_short)
    assert gc._bump_short_regen_or_reject(err_short, 0) == 1
    with pytest.raises(ValueError, match="重生成3次仍不达标"):
        gc._bump_short_regen_or_reject(err_chars, 3)


def test_attach_gold_chat_structure_score_skips_opening_penalty_for_body():
    """计分前清空 discovery_opening，避免前 2 句被当开场扣分。"""
    row = _sample_row()
    row["structure_type"] = "J"
    row["title"] = "世子之争"
    chat = {
        "scene_title": "世子之争",
        "setting": "地板垫上，灿灿和昭昭在抢垫子",
        "conflict_core": "昭昭先动手，灿灿一锤镇住",
        "punchline_explain": "J类权威压住：一锤肘击后镇住",
        "story_type": "J",
        "dialogue": [
            {"speaker": "昭昭", "line": "这垫子是我的地盘你走开！"},
            {"speaker": "灿灿", "line": "谁赢谁说了算玩具归我！"},
            {"speaker": "昭昭", "line": "拿出最强形态来打我！"},
            {"speaker": "灿灿", "line": "草莓熊肘击砸你肚子！"},
            {"speaker": "昭昭", "line": "啊我输了你太厉害啦！"},
            {"speaker": "灿灿", "line": "以后玩具都归我安排！"},
            {"speaker": "昭昭", "line": "哼等我长大再跟你算！"},
            {"speaker": "灿灿", "line": "这局我已经镇住你了！"},
            {"speaker": "昭昭", "line": "再求你一次松口行不行！"},
            {"speaker": "灿灿", "line": "不行规矩就是这样定的！"},
            {"speaker": "昭昭", "line": "那我保证这次听你的话！"},
            {"speaker": "灿灿", "line": "保证也没用现在听我的！"},
        ],
    }
    out = gc._attach_gold_chat_structure_score(chat, row)
    reasons = " ".join(str(r) for r in (out.get("quality") or {}).get("reasons") or [])
    assert "开场未满" not in reasons
    assert "J开场缺求放行" not in reasons
    assert "缺发现开场" not in reasons
    score = int((out.get("quality") or {}).get("structure_score") or 0)
    assert score >= 75, (score, reasons)


def test_gold_chat_structure_score_skips_bili_title_relevancy():
    """gold_chat 结构分不按 B 站标题字面跑题（保真走 beat/契约）。"""
    row = _sample_row()
    row["title"] = "世子之争"
    chat = _sample_chat()
    chat["scene_title"] = "垫子争夺战"
    chat["story_type"] = "J"
    chat["dialogue"] = [
        {"speaker": "昭昭", "line": "这沙发我先占好了，你挪开！"},
        {"speaker": "灿灿", "line": "不行，我先来的，该你走！"},
    ] * 6
    out = gc._attach_gold_chat_structure_score(chat, row)
    reasons = " ".join(str(r) for r in (out.get("quality") or {}).get("reasons") or [])
    assert "跑题" not in reasons


def test_validate_expand_expands_short_with_fix_before_regen(monkeypatch):
    """偏短时先 FIX 句内扩写，勿立刻整稿重生成。"""
    calls = {"fix": 0}

    short = _sample_chat()
    short["story_type"] = "J"
    short["dialogue"] = [
        {"speaker": "昭昭", "line": "看招！"},
        {"speaker": "灿灿", "line": "你敢！"},
    ] * 6
    assert gc.dialogue_total_chars(short) < gc.DAILY_STORY_BODY_CHARS_MIN

    def fake_fix(story, errors, **_kw):
        calls["fix"] += 1
        assert "正文总字数须≥" in errors
        return _sample_chat()

    monkeypatch.setattr(gc, "_fix_chat_with_llm", fake_fix)
    monkeypatch.setattr(gex, "_fix_chat_with_llm", fake_fix)
    monkeypatch.setattr(gc, "_ensure_gold_chat_min_chars", lambda s, **kw: (s, False))
    import app.services.gold_story.gold_chat.length as glength
    monkeypatch.setattr(glength, "_ensure_gold_chat_min_chars", lambda s, **kw: (s, False))
    monkeypatch.setattr(gex, "_ensure_gold_chat_min_chars", lambda s, **kw: (s, False))
    out = gc._validate_expand_chat(
        short,
        banned_literals=[],
        source_type="field",
        mom_lines_max=0,
        structure_type="J",
    )
    assert calls["fix"] == 1
    assert len(out["dialogue"]) >= 12


def test_apply_deterministic_shorten_trims_one_char():
    story = _sample_chat()
    story["dialogue"][0]["line"] = "你刚才又抢我遥控器，我还不敢说呀！"
    assert len(story["dialogue"][0]["line"]) == 17  # sanity
    long_line = "你" * 24 + "呀"
    assert len(long_line) == 25
    story["dialogue"][0]["line"] = long_line
    out, changed = gc._apply_deterministic_shorten(story)
    assert changed
    assert len(out["dialogue"][0]["line"]) <= gc.CHAT_MAX_LINE_CHARS


def test_validate_expand_shortens_before_full_fix(monkeypatch):
    calls: list[str] = []

    def fake_validate(story, **kwargs):
        for item in story.get("dialogue") or []:
            if len(str(item.get("line") or "")) > gc.CHAT_MAX_LINE_CHARS:
                raise ValueError(
                    f"单句过长(max=31>{gc.CHAT_MAX_LINE_CHARS})"
                )
        return None

    def fake_shorten(story, **_kw):
        calls.append("shorten")
        out = dict(story)
        rows = [dict(x) for x in out["dialogue"]]
        rows[0]["line"] = str(rows[0]["line"])[: gc.CHAT_MAX_LINE_CHARS]
        out["dialogue"] = rows
        return out

    monkeypatch.setattr(gc, "validate_gold_chat", fake_validate)
    monkeypatch.setattr(gc, "_shorten_overlong_lines_with_llm", fake_shorten)
    monkeypatch.setattr(gex, "_shorten_overlong_lines_with_llm", fake_shorten)

    def _boom(*_a, **_k):
        raise AssertionError("should not full fix")

    monkeypatch.setattr(gc, "_fix_chat_with_llm", _boom)
    monkeypatch.setattr(gex, "_fix_chat_with_llm", _boom)
    story = _sample_chat()
    story["dialogue"][0]["line"] = "你" * 31
    out = gc._validate_expand_chat(
        story,
        banned_literals=[],
        source_type="field",
        mom_lines_max=1,
    )
    assert calls == ["shorten"]
    assert len(out["dialogue"][0]["line"]) <= gc.CHAT_MAX_LINE_CHARS


def test_gold_story_to_gold_chat(monkeypatch):
    _bypass_structure_gate(monkeypatch)

    def fake_chat(_system: str, _user: str, **_kwargs) -> dict:
        return _sample_chat()

    monkeypatch.setattr(gc, "_chat_json", fake_chat)
    monkeypatch.setattr(gex, "_chat_json", fake_chat)
    out = gc.gold_story_to_gold_chat(_sample_row())
    assert out["scene_title"] == "关门练功"
    assert len(out["dialogue"]) >= 4
    assert out["quality"]["structure_score"] == 80


def test_convert_failure_preserves_existing_export(tmp_path, monkeypatch):
    from app.services.gold_story.gold_chat.finalize import GoldChatAcceptanceBlocked

    sid = "BV1KEEPEXPORT"
    export_dir = tmp_path / "gold_chat"
    export_dir.mkdir(parents=True)
    json_path = export_dir / f"{sid}.json"
    original = '{"keep": true}'
    json_path.write_text(original, encoding="utf-8")

    row = _sample_row()
    row["source_id"] = sid
    row["id"] = 96

    monkeypatch.setattr(gc, "gold_chat_export_dir", lambda _cfg=None: export_dir)
    monkeypatch.setattr(gce, "gold_chat_export_dir", lambda _cfg=None: export_dir)
    _bypass_structure_gate(monkeypatch)
    monkeypatch.setattr(
        gc,
        "gold_story_to_gold_chat",
        lambda _r, **kw: _sample_chat(),
    )
    monkeypatch.setattr(
        gc,
        "apply_gold_chat_normalizations",
        lambda chat, **_kw: (chat, []),
    )
    monkeypatch.setattr(
        gc,
        "_refine_after_normalize",
        lambda chat, _row, **_kw: chat,
    )
    monkeypatch.setattr(gc, "_rebuild_h3a_h3b_on_convert", lambda r: r)
    monkeypatch.setattr(gc, "_persist_structure_correction", lambda r, _n: r)
    monkeypatch.setattr(gc, "_resolve_structure_row", lambda r: (r, []))
    monkeypatch.setattr(gc, "_persist_m5_h_contract_if_needed", lambda r: r)

    def _fail_finalize(*_args, **_kwargs):
        raise GoldChatAcceptanceBlocked("终检语义硬伤：第[2]句·错位：测试")

    monkeypatch.setattr(gcf, "run_gold_chat_finalize", _fail_finalize)

    with pytest.raises(GoldChatAcceptanceBlocked):
        gc.convert_gold_chat(row)

    assert json_path.read_text(encoding="utf-8") == original


def test_rebuild_h3a_h3b_on_convert_refreshes_contract(monkeypatch):
    """重转切入点：用 story_raw+H3 重跑 H3a/H3b 写回契约。"""
    patched: dict = {}
    cores: list[str] = []

    def fake_build_scene(**_kwargs):
        return {
            "story_type": "I",
            "location": "客厅",
            "characters": ["灿灿", "昭昭", "妈妈"],
            "object": "小学单科成绩单",
            "conflict": "昭昭宣扬灿灿考了低分，妈妈责备戳痛处",
            "mechanism": "宣传高分该谢、低分怪分数",
            "beat_chain": [
                {"beat": 1, "speaker": "灿灿", "intent": "责备宣传"},
                {"beat": 2, "speaker": "昭昭", "intent": "双标辩解"},
                {"beat": 3, "speaker": "妈妈", "intent": "冰箱反问"},
                {"beat": 4, "speaker": "昭昭", "intent": "嘴硬"},
            ],
            "closing_intent": "昭昭嘴硬",
            "mom_lines_max": 2,
            "remap_note": "戏核家长须保留出场",
            "banned_literals": [],
            "contract_confidence": 0.9,
        }

    def fake_build_seed(**_kwargs):
        return {
            "setting": "客厅，灿灿攥着成绩单",
            "dialogue_seed": [
                {"speaker": "灿灿", "intent": "责备宣传低分"},
                {"speaker": "昭昭", "intent": "双标辩解"},
                {"speaker": "妈妈", "intent": "冰箱反问"},
                {"speaker": "昭昭", "intent": "嘴硬"},
            ],
            "closing_intent": "昭昭嘴硬",
            "speaker_map_note": "妈妈保留",
            "dialogue_confidence": 0.9,
        }

    monkeypatch.setattr(
        "app.services.gold_story.collect.llm.build_scene_contract",
        fake_build_scene,
    )
    monkeypatch.setattr(
        "app.services.gold_story.collect.llm.build_dialogue_seed",
        fake_build_seed,
    )
    monkeypatch.setattr(
        gc.repo_gold_story,
        "patch_story_payload",
        lambda gid, patch: patched.update({"gid": gid, **patch}),
    )
    monkeypatch.setattr(
        gc.repo_gold_story,
        "update_conflict_core",
        lambda gid, core: cores.append(core),
    )

    row = {
        "id": 44,
        "title": "分数宣传",
        "mechanism": "M11",
        "structure_type": "I",
        "conflict_core": "站外旧核：高考高分口吻残留",
        "theme_family": "分数",
        "payload": {
            "story_raw": "姐姐考了差分化妹妹宣传，妈妈责备并用冰箱反问。" * 3,
            "beat": [
                "妹妹宣扬，妈妈责备",
                "妹妹辩称双标",
                "妈妈反问冰箱",
                "妈妈点出开好头",
            ],
            "scene_contract": {
                "characters": ["灿灿", "昭昭"],
                "mom_lines_max": 0,
                "object": "站外旧分数口吻",
            },
            "source_type": "field",
            "structure_confidence": 0.8,
        },
    }
    out = gc._rebuild_h3a_h3b_on_convert(row)
    sc = out["payload"]["scene_contract"]
    assert "妈妈" in sc["characters"]
    assert int(sc["mom_lines_max"]) >= 2
    assert "高考" not in str(out.get("conflict_core") or "")
    assert "低分" in str(out.get("conflict_core") or "")
    assert cores and "低分" in cores[0]
    assert any(
        isinstance(r, dict) and r.get("speaker") == "妈妈"
        for r in out["payload"]["dialogue_seed"]
    )
    assert patched.get("gid") == 44


def test_sanitize_pad_suffix_strips_compound_tails():
    story = {
        "dialogue": [
            {
                "speaker": "昭昭",
                "line": "那跟我有啥关系不行了吧真的了呢。",
            },
            {
                "speaker": "灿灿",
                "line": "你别再宣传了真的了呢",
            },
            {
                "speaker": "妈妈",
                "line": "评论冰箱还得会制冷吗？",
            },
        ]
    }
    out, changed = gc.patch_sanitize_pad_suffix(story)
    assert changed
    lines = [str(x["line"]) for x in out["dialogue"]]
    assert "真的了呢" not in lines[0]
    assert "不行了吧" not in lines[0]
    assert "真的了呢" not in lines[1]
    assert "冰箱" in lines[2]


def test_sanitize_pad_suffix_strips_glued_buxing():
    """粘连垫字「知道不行/关系不行」应剥；真拒绝「还不行」保留。"""
    story = {
        "dialogue": [
            {"speaker": "昭昭", "line": "姐数学58分，全班都知道不行！"},
            {
                "speaker": "昭昭",
                "line": "跟我没关系不行，我才不怕呢。",
            },
            {"speaker": "灿灿", "line": "这样还不行！"},
        ]
    }
    out, changed = gc.patch_sanitize_pad_suffix(story)
    assert changed
    lines = [str(x["line"]) for x in out["dialogue"]]
    assert "知道不行" not in lines[0]
    assert "都知道" in lines[0]
    assert "关系不行" not in lines[1]
    assert "没关系" in lines[1]
    assert lines[2] == "这样还不行！"


def test_parse_conflict_propaganda_roles():
    from app.services.gold_story.gold_chat.validate import (
        _parse_conflict_propaganda_roles,
    )

    roles = _parse_conflict_propaganda_roles(
        "昭昭到处说姐姐考了58分，妈妈责备昭昭戳姐姐痛处"
    )
    assert roles == ("昭昭", "灿灿")


def test_patch_score_propaganda_speakers_realigns():
    story = {
        "conflict_core": "昭昭到处说灿灿考了58分",
        "dialogue": [
            {"speaker": "昭昭", "line": "她考高分我宣传，她得谢我。"},
            {"speaker": "昭昭", "line": "你到处说，我同学都笑我。"},
            {"speaker": "灿灿", "line": "我宣传高分你谢我，宣传低分你怪我。"},
            {"speaker": "灿灿", "line": "低分被怪是分数问题，怪我咯。"},
        ],
    }
    out, changed = gc.patch_score_propaganda_speakers(
        story, conflict_text=story["conflict_core"]
    )
    assert changed
    assert out["dialogue"][1]["speaker"] == "灿灿"
    assert out["dialogue"][2]["speaker"] == "昭昭"
    assert out["dialogue"][3]["speaker"] == "昭昭"


def test_patch_collapse_empty_sibling_repeats():
    story = {
        "dialogue": [
            {"speaker": "灿灿", "line": "别说了！"},
            {"speaker": "灿灿", "line": "别说了！"},
            {"speaker": "灿灿", "line": "别说了！"},
        ]
    }
    out, changed = gc.patch_collapse_empty_sibling_repeats(story)
    assert changed
    assert out["dialogue"][0]["line"] == "别说了！"
    assert out["dialogue"][1]["line"] != "别说了！"


def test_format_role_binding_block_propaganda():
    from app.services.gold_story.gold_chat.prompts import format_role_binding_block

    block = format_role_binding_block(
        "昭昭到处说姐姐考了58分，妈妈责备昭昭戳姐姐痛处"
    )
    assert "宣传方 = 昭昭" in block
    assert "受害方 = 灿灿" in block


def test_export_gold_chat_files(tmp_path, monkeypatch):
    monkeypatch.setattr(gc, "gold_chat_export_dir", lambda _cfg=None: tmp_path)
    monkeypatch.setattr(gce, "gold_chat_export_dir", lambda _cfg=None: tmp_path)
    row = _sample_row()
    chat = _sample_chat()
    paths = gc.export_gold_chat_files(
        source_id=row["source_id"],
        row=row,
        chat=chat,
    )
    assert Path(paths["json"]).is_file()
    assert Path(paths["markdown"]).is_file()
    payload = json.loads(Path(paths["json"]).read_text(encoding="utf-8"))
    assert payload["daily_story"]["scene_title"] == "关门练功"


def test_gold_chat_summary_from_payload():
    summary = gc.gold_chat_summary(
        "BV1TEST0001",
        row={
            "source_id": "BV1TEST0001",
            "payload": {
                "gold_chat_exported_at": "2026-08-24T00:00:00+00:00",
                "gold_chat_scene_title": "嘴硬心软",
                "gold_chat_lines": 18,
                "gold_chat_chars": 260,
                "bili_title": "东北弟弟打架被姐姐骂",
            },
        },
    )
    assert summary["has_gold_chat"] is True
    assert summary["scene_title"] == "嘴硬心软"
    assert summary["chat_lines"] == 18
    assert summary["bili_title"] == "东北弟弟打架被姐姐骂"


def test_import_gold_chat_daily_story_insert_and_reimport(
    app_ctx, tmp_path, monkeypatch,
):
    from app.repositories import repo_daily_story, repo_gold_story

    with app_ctx.app_context():
        inserted = repo_gold_story.insert_or_skip(
            source="bilibili",
            source_id="BV1TESTIMPORT01",
            url="https://www.bilibili.com/video/BV1TESTIMPORT01",
            mechanism="M6",
            structure_type="A",
            story_raw="导入测试专用故事" * 20,
            payload={
                "setting": "卧室门口",
                "beat": ["被欺负", "关门幻想", "开门怂", "姐姐得意"],
                "dialogue_seed": [
                    {"speaker": "昭昭", "intent": "抱怨被欺负"},
                    {"speaker": "灿灿", "intent": "得意威胁"},
                ],
                "closing_intent": "昭昭缩回角落",
                "banned_literals": ["小姨", "萌娃"],
                "funny_why": "幻想与怂的反差",
            },
            title="测试标题",
            conflict_core="弟弟幻想报复姐姐，开门秒怂",
            extract_confidence=0.8,
            structure_confidence=0.8,
            dialogue_confidence=0.8,
            auto_score=0.9,
            status="active",
        )
        assert inserted.get("action") == "insert"
        row = repo_gold_story.get_story(int(inserted["id"]))
        row["payload"]["scene_contract"] = {"mom_lines_max": 0}

    chat = _sample_chat()
    monkeypatch.setattr(gc, "gold_chat_export_dir", lambda _cfg=None: tmp_path)
    monkeypatch.setattr(gce, "gold_chat_export_dir", lambda _cfg=None: tmp_path)
    gc.export_gold_chat_files(source_id=row["source_id"], row=row, chat=chat)
    captured_mom_max: list[int | None] = []
    original_validate = gc.validate_gold_chat

    def capture_validate(story, **kwargs):
        captured_mom_max.append(kwargs.get("mom_lines_max"))
        return original_validate(
            story,
            **{**kwargs, "mom_lines_max": 1},
        )

    monkeypatch.setattr(gc, "validate_gold_chat", capture_validate)

    with app_ctx.app_context():
        out = gc.import_gold_chat_daily_story(row, review=False)
        assert out["action"] == "insert"
        assert captured_mom_max[0] == 0
        ds_id = int(out["daily_story_id"])
        saved = repo_daily_story.get_story(ds_id)
        assert saved["story"]["scene_title"] == "关门练功"

        row["gold_chat_daily_story_id"] = ds_id
        skip = gc.import_gold_chat_daily_story(row, review=False)
        assert skip["action"] == "skip"

        chat2 = dict(chat)
        chat2["scene_title"] = "新标题"
        gc.export_gold_chat_files(source_id=row["source_id"], row=row, chat=chat2)
        updated = gc.import_gold_chat_daily_story(row, force=True, review=False)
        assert updated["action"] == "update"
        saved2 = repo_daily_story.get_story(ds_id)
        assert saved2["story"]["scene_title"] == "新标题"


def test_resolve_gold_chat_snippet_same_source():
    from app.services.gold_story.collect.llm import (
        GOLD_CHAT_LINES_SNIPPET,
        GOLD_CHAT_LINES_SNIPPET_SOURCE_ID,
        resolve_gold_chat_snippet,
    )

    note = resolve_gold_chat_snippet(GOLD_CHAT_LINES_SNIPPET_SOURCE_ID)
    assert "不注入全文正例" in note
    assert "未满 240" in note
    assert "18–24" not in note
    assert GOLD_CHAT_LINES_SNIPPET not in note


def test_format_dialogue_seed_marks_spoken_lines():
    text = gc._format_dialogue_seed(
        [
            {"speaker": "灿灿", "intent": "零食归我，作业本归你，公平吧？"},
            {"speaker": "昭昭", "intent": "立规反杀"},
        ]
    )
    assert "要点" in text
    assert "勿逐字照抄" in text
    assert "intent：立规反杀" in text


def test_closing_for_prompt_shortens_long():
    long = (
        "灿灿求饶但嘴硬收场：昭昭用灿灿自己立的规矩"
        "「零食归我，作业本归你」堵住，灿灿语塞，答应归还零食，末句嘴硬约下次"
    )
    out = gc._closing_for_prompt(long)
    assert len(out) < len(long)
    assert "灿灿求饶但嘴硬收场" in out


def test_expand_regen_feedback_includes_short_error():
    from app.services.gold_story.gold_chat.prompts import (
        format_expand_regen_feedback,
    )

    fb = format_expand_regen_feedback(
        "正文总字数须≥240，当前214",
        None,
        structure_type="C",
        mechanism="M2",
    )
    assert "未满" in fb or "≥240" in fb
    assert "214" in fb or "错误" in fb


def test_gold_chat_scenario_rules_are_contract_scoped():
    from app.services.gold_story.gold_chat.prompts import (
        format_scenario_rules_block,
    )

    unrelated = format_scenario_rules_block(
        mechanism="M9",
        structure_type="N",
        conflict_text="昭昭提出荒诞问题，灿灿认真回答",
        closing_intent="昭昭被答案噎住",
    )
    assert "互毁" not in unrelated
    assert "上药" not in unrelated

    mediation = format_scenario_rules_block(
        mechanism="M5",
        structure_type="H",
        conflict_text="灿灿先弄坏昭昭的画，双方互毁后妈妈调解",
        closing_intent="妈妈涂药后收束",
    )
    assert "本场互毁" in mediation
    assert "本场调解" in mediation
    assert "本场上药" in mediation

    # 「不和好」不得因含子串「和好」而注入调解
    denied = format_scenario_rules_block(
        mechanism="M8",
        structure_type="J",
        conflict_text="昭昭先动手抢垫子",
        closing_intent="灿灿压住，昭昭怂退，不和好，妈妈不出场",
    )
    assert "本场调解" not in denied
    assert "定责" not in denied

    # 中段拒和 + 结尾要求和好 → 仍注入和好/调解
    mid_refuse = format_scenario_rules_block(
        mechanism="M5",
        structure_type="H",
        conflict_text="灿灿拒绝和好，说不和好，冲突升级",
        closing_intent="妈妈调解后姐弟拉手和好",
    )
    assert "本场调解" in mid_refuse or "本场和好" in mid_refuse


def test_gold_chat_align_refine_prompts_are_type_scoped():
    from app.services.gold_story.gold_chat.prompts import (
        format_align_refine_system,
        format_align_refine_user,
    )

    sys_j = format_align_refine_system(mechanism="M8", structure_type="J")
    user_j = format_align_refine_user(
        issues_block="（无）",
        align_block="checklist",
        story_json="{}",
        chars_min=240,
        chars_max=370,
        banned_literals="（无）",
        mom_lines_max=1,
        max_line=24,
        mechanism="M8",
        structure_type="J",
        closing_intent="灿灿压住，昭昭怂退",
    )
    j_all = sys_j + user_j
    assert "保真-互毁" not in j_all
    assert "保真-和好" not in j_all
    assert "保真-M5" not in j_all
    assert "不打了" not in j_all
    assert "拉手" not in j_all
    assert "不得减少正文总字数" not in j_all
    assert "改短" in j_all or "改短或扩写" in j_all
    assert "≥240" in user_j or "≥{chars_min}" not in user_j

    # 否定契约：不和好 + 妈妈不出场 → 禁止和好/定责
    deny_closing = "灿灿压住，昭昭怂退，不和好，妈妈不出场"
    sys_deny = format_align_refine_system(
        mechanism="M8",
        structure_type="J",
        closing_intent=deny_closing,
    )
    user_deny = format_align_refine_user(
        issues_block="（无）",
        align_block="checklist",
        story_json="{}",
        chars_min=240,
        chars_max=370,
        banned_literals="（无）",
        mom_lines_max=1,
        max_line=24,
        mechanism="M8",
        structure_type="J",
        closing_intent=deny_closing,
    )
    deny_all = sys_deny + user_deny
    assert "保真-和好" not in deny_all
    assert "保真-H定责" not in deny_all
    assert "妈妈分层定责" not in deny_all

    # 中段「不和好」不得覆盖结尾和好要求
    mid_refuse_closing = "妈妈调解后姐弟拉手和好"
    mid_refuse_conflict = "灿灿拒绝和好，说不和好，冲突升级"
    user_mid = format_align_refine_user(
        issues_block="（无）",
        align_block="checklist",
        story_json="{}",
        chars_min=240,
        chars_max=370,
        banned_literals="（无）",
        mom_lines_max=1,
        max_line=24,
        mechanism="M5",
        structure_type="H",
        closing_intent=mid_refuse_closing,
        conflict_text=mid_refuse_conflict,
    )
    assert "保真-和好" in user_mid
    assert "保真-H定责" in user_mid

    sys_h = format_align_refine_system(
        mechanism="M5",
        structure_type="H",
        closing_intent="灿灿问还打不打架，拉手和好",
        conflict_text="互毁后妈妈调解",
    )
    user_h = format_align_refine_user(
        issues_block="（无）",
        align_block="checklist",
        story_json="{}",
        chars_min=240,
        chars_max=370,
        banned_literals="（无）",
        mom_lines_max=1,
        max_line=24,
        mechanism="M5",
        structure_type="H",
        closing_intent="灿灿问还打不打架，拉手和好",
        conflict_text="互毁后妈妈调解",
    )
    h_all = sys_h + user_h
    assert "M5 立规" in sys_h
    assert "保真-互毁" in user_h
    assert "保真-和好" in user_h
    assert "拉手" in h_all


def test_is_truncation_error():
    assert gc._is_truncation_error(
        "LLM output truncated (finish_reason=length)；对白 JSON 须短小"
    )
    assert not gc._is_truncation_error("正文总字数须≥240，当前214")


def test_resolve_gold_chat_snippet_cross_source():
    from app.services.gold_story.collect.llm import (
        GOLD_CHAT_LINES_SNIPPET,
        resolve_gold_chat_snippet,
    )

    assert resolve_gold_chat_snippet("BV1OTHER") == GOLD_CHAT_LINES_SNIPPET


def test_normalize_enriches_setting_from_bowl_lines():
    chat = {
        "setting": "餐桌旁，灿灿和昭昭在吵架",
        "story_type": "C",
        "dialogue": [
            {"speaker": "昭昭", "line": "你碗里肉这么多，凭什么不能给我夹一块！"},
            {"speaker": "灿灿", "line": "你碗里那青菜不香吗？"},
        ],
    }
    row = {
        "structure_type": "C",
        "mechanism": "M2",
        "payload": {
            "scene_contract": {
                "location": "餐桌",
                "object": "肉",
                "characters": ["灿灿", "昭昭"],
            }
        },
    }
    out, notes = gc.apply_gold_chat_normalizations(chat, row=row)
    assert "肉" in str(out.get("setting") or "")
    assert "青菜" in str(out.get("setting") or "")
    assert any("冲突物" in n for n in notes)


def test_gate_forced_m14_p_rejects_when_not_q():
    """无拆穿反噬链的假 P 仍结构驳回；能纠到 Q 的不走此门。"""
    row = {
        "id": 99,
        "mechanism": "M14",
        "structure_type": "P",
        "conflict_core": "两人互骂了一会儿就散了",
        "payload": {
            "story_raw": "姐弟互骂几句，没有道具整蛊也没有认怂。",
            "beat": ["互骂", "散场"],
            "closing_intent": "散了",
            "dialogue_seed": [
                {"speaker": "灿灿", "intent": "骂一句"},
                {"speaker": "昭昭", "intent": "回骂"},
            ],
        },
    }
    with pytest.raises(ValueError, match="forced-m14p-not-prank"):
        gc._gate_forced_m14_p_or_raise(row)


def test_resolve_row_75_to_m15_q_allows_convert_gate():
    row = {
        "id": 75,
        "mechanism": "M14",
        "structure_type": "P",
        "conflict_core": "灿灿抽签耍赖，借口胃小推食，妈妈看穿让洗碗",
        "payload": {
            "story_raw": (
                "妈妈和灿灿玩抽签吃饭，灿灿耍赖重抽、逞强吃辣，"
                "最后借口胃小把剩食推给妈妈，妈妈看穿心思让她洗碗。"
            ),
            "beat": ["抽签", "逞强", "推食", "洗碗"],
            "closing_intent": "妈妈笑着让灿灿洗碗，看穿她的小心思",
            "dialogue_seed": [
                {"speaker": "灿灿", "intent": "耍赖重抽"},
                {"speaker": "灿灿", "intent": "推食借口胃小"},
                {"speaker": "妈妈", "intent": "看穿心思让洗碗"},
            ],
            "structure_mapping_note": "M2→M14+P",
        },
    }
    out, notes = gc._resolve_structure_row(row)
    assert out["mechanism"] == "M15"
    assert out["structure_type"] == "Q"
    assert any("cheat-expose" in n or "M15" in n for n in notes)
    gc._gate_forced_m14_p_or_raise(out)  # 已是 Q，不应抛


def test_local_hard_repairs_punchline_and_mom():
    story = _sample_chat()
    story.pop("punchline_explain", None)
    story["story_type"] = "A"
    story["dialogue"] = list(story["dialogue"]) + [
        {"speaker": "妈妈", "line": "别吵了先吃饭。"},
        {"speaker": "妈妈", "line": "吃完再理论。"},
    ]
    out = gc._apply_gold_chat_local_hard_repairs(
        story, structure_type="A", mom_lines_max=1
    )
    assert "punchline_explain" in out
    assert str(out["punchline_explain"]).startswith("A类")
    mom_n = sum(
        1
        for d in out["dialogue"]
        if isinstance(d, dict) and d.get("speaker") == "妈妈"
    )
    assert mom_n <= 1


def test_reject_message_not_pad_when_missing_fields():
    err = "缺少字段: punchline_explain; 妈妈台词须≤1句，当前2; 正文总字数须≥240，当前226"
    msg = gc._short_content_reject_message(err)
    assert "校验驳回" in msg
    assert "本地垫字仍不足" not in msg
    assert gc._has_non_short_hard_errors(err)


def test_structure_cons_lists_mom_penalty_and_log_cons():
    from app.services.daily_story.quality import (
        score_daily_story,
        structure_cons_for_log,
    )

    dialogue = [
        {"speaker": "妈妈", "line": "你作业写完了吗？"},
        {"speaker": "昭昭", "line": "妈，我屁股Q弹，你打我吧。"},
        {"speaker": "妈妈", "line": "你说什么？"},
        {"speaker": "灿灿", "line": "噗，弹簧屁股吗？"},
        {"speaker": "妈妈", "line": "都给我消停。"},
        {"speaker": "昭昭", "line": "因为弹，所以打了不哭呀。"},
        {"speaker": "灿灿", "line": "为什么？"},
        {"speaker": "昭昭", "line": "因为Q弹就能救场呀。"},
        {"speaker": "灿灿", "line": "你这歪理也太绝了。"},
        {"speaker": "昭昭", "line": "我说得通吧。"},
        {"speaker": "灿灿", "line": "那……我说不过你。"},
        {"speaker": "昭昭", "line": "行吧。"},
    ]
    base = {
        "story_type": "N",
        "conflict_core": "Q弹救场",
        "punchline_explain": "N类正经胡说",
        "dialogue": dialogue,
    }
    q_default = score_daily_story(dict(base))
    cons_default = q_default.get("structure_cons") or []
    assert any("妈妈台词偏多（3句）" in str(c) for c in cons_default)
    assert structure_cons_for_log(q_default)

    with_contract = dict(base)
    with_contract["_gold_chat_mom_lines_max"] = 3
    q_contract = score_daily_story(with_contract)
    cons_contract = q_contract.get("structure_cons") or []
    assert not any("妈妈台词偏多" in str(c) for c in cons_contract)

    over = dict(with_contract)
    over["dialogue"] = list(dialogue) + [
        {"speaker": "妈妈", "line": "灿灿快去写作业。"},
    ]
    q_over = score_daily_story(over)
    assert any("妈妈台词偏多（4句）" in str(c) for c in q_over.get("structure_cons") or [])


def test_structure_score_feedback_and_fail_log_use_structure_cons():
    import logging

    from app.services.gold_story.gold_chat.prompts import (
        format_structure_score_feedback,
    )

    quality = {
        "structure_score": 70,
        "structure_cons": ["妈妈台词偏多（3句）"],
        "reasons": ["结构70", "妈妈台词偏多（3句）"],
    }
    fb = format_structure_score_feedback("structure_score:70", {"quality": quality})
    assert "偏多" in fb

    logger_name = "app.services.gold_story.gold_chat.convert"
    mod_logger = logging.getLogger(logger_name)
    captured: list[str] = []

    class _CaptureHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            captured.append(record.getMessage())

    handler = _CaptureHandler()
    handler.setLevel(logging.INFO)
    saved_level = mod_logger.level
    saved_propagate = mod_logger.propagate
    saved_handlers = mod_logger.handlers[:]
    try:
        mod_logger.handlers = [handler]
        mod_logger.propagate = False
        mod_logger.setLevel(logging.INFO)
        chat = {"story_type": "N", "dialogue": [{"speaker": "昭昭", "line": "测"}]}
        gc.log_gold_chat_structure_score_fail(chat, quality, structure_type="N")
    finally:
        mod_logger.setLevel(saved_level)
        mod_logger.propagate = saved_propagate
        mod_logger.handlers[:] = saved_handlers

    assert captured
    assert "妈妈台词偏多" in captured[0]
    assert "reasons=" in captured[0]


def test_structure_cons_excludes_humor_regex_diagnostics():
    from app.services.daily_story.quality import structure_cons_for_log

    quality = {
        "structure_cons": ["妈妈台词偏多（3句）"],
        "reasons": [
            "结构70",
            "妈妈台词偏多（3句）",
            "好笑诊断：末句缺回旋",
        ],
    }
    cons = structure_cons_for_log(quality)
    assert cons == ["妈妈台词偏多（3句）"]
    assert not any("好笑" in c for c in cons)

    empty_key = {"structure_cons": [], "reasons": ["好笑诊断：xxx"]}
    assert structure_cons_for_log(empty_key) == []
