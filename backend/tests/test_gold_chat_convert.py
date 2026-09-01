"""gold_chat 转换测试。"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app.services.daily_story.gold_story.gold_chat import convert as gc
from app.services.daily_story.gold_story.gold_chat import export as gce
from app.services.daily_story.gold_story.gold_chat import patch as gcp


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
    lines = _sample_chat()["dialogue"][:12]
    for item in lines:
        item["line"] = str(item["line"])[:18]
    story = {**_sample_chat(), "dialogue": lines}
    out, changed = gc._ensure_gold_chat_min_chars(story)
    assert changed
    assert gc.dialogue_total_chars(out) >= gc.DAILY_STORY_BODY_CHARS_MIN


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


def test_normalize_chat_speakers_father_to_mom():
    story = _sample_chat()
    story["dialogue"][0]["speaker"] = "爸爸"
    out = gc._normalize_chat_speakers(story)
    assert out["dialogue"][0]["speaker"] == "妈妈"


def test_gate_gold_chat_structure_score_raises_when_low():
    with pytest.raises(ValueError, match=r"structure_score:63"):
        gc._gate_gold_chat_structure_score(
            {"quality": {"structure_score": 63, "score": 63}}
        )


def test_gate_gold_chat_structure_score_ok():
    assert gc._gate_gold_chat_structure_score(
        {"quality": {"structure_score": 80, "score": 80}}
    ) == 80


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
    # 测试夹具对白过不了 A–L 契约机审；跳过 Pass2 对齐精修
    monkeypatch.setattr(gc, "refine_gold_chat_align", lambda story, **_kw: story)


def test_gold_story_to_gold_chat_retries_when_one_line_short(monkeypatch):
    calls: dict[str, int | bool] = {"n": 0}
    _bypass_structure_gate(monkeypatch)

    def fake_chat(system: str, _user: str, **_kwargs) -> dict:
        if "编辑" in system:
            calls["fix"] = True
            return _sample_chat()
        calls["n"] = int(calls["n"]) + 1
        chat = _sample_chat()
        if int(calls["n"]) <= 2:
            chat["dialogue"] = chat["dialogue"][:11]
        return chat

    monkeypatch.setattr(gc, "_chat_json", fake_chat)
    monkeypatch.setattr(gc, "PASS1_CANDIDATE_COUNT", 1)
    monkeypatch.setattr(gc, "PASS1_REGENERATE_MAX", 5)
    out = gc.gold_story_to_gold_chat(_sample_row())
    assert len(out["dialogue"]) >= 12
    assert int(calls["n"]) >= 3
    assert calls.get("fix") is not True


def test_gold_story_to_gold_chat_rejects_when_far_too_short(monkeypatch):
    _bypass_structure_gate(monkeypatch)

    def fake_chat(_system: str, _user: str, **_kwargs) -> dict:
        bad = _sample_chat()
        bad["dialogue"] = bad["dialogue"][:2]
        return bad

    monkeypatch.setattr(gc, "_chat_json", fake_chat)
    monkeypatch.setattr(gc, "PASS1_CANDIDATE_COUNT", 1)
    with pytest.raises(ValueError, match="篇幅驳回"):
        gc.gold_story_to_gold_chat(_sample_row())


def test_gold_story_to_gold_chat_rejects_after_three_one_line_short_regens(monkeypatch):
    _bypass_structure_gate(monkeypatch)

    def fake_chat(_system: str, _user: str, **_kwargs) -> dict:
        bad = _sample_chat()
        bad["dialogue"] = bad["dialogue"][:11]
        return bad

    monkeypatch.setattr(gc, "_chat_json", fake_chat)
    monkeypatch.setattr(gc, "PASS1_CANDIDATE_COUNT", 1)
    with pytest.raises(ValueError, match="重生成3次仍不达标"):
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
    # 字数 near-miss（如 235/240）也应可重生成，勿冒充「重生成3次」
    err_chars = "正文总字数须≥240，当前235"
    assert gc._char_deficit_from_error(err_chars) == 5
    assert gc._is_regenerable_short_error(err_chars)
    assert gc._bump_short_regen_or_reject(err_chars, 0) == 1
    with pytest.raises(ValueError, match="重生成3次仍不达标"):
        gc._bump_short_regen_or_reject(err_chars, 3)


def test_ensure_gold_chat_min_chars_survives_sanitize_strip():
    """垫满后剥叠语气词又短 → 须再垫回 ≥240（回归 235 假驳回）。"""
    from app.services.daily_story.prompts import DAILY_STORY_BODY_CHARS_MIN

    story = _sample_chat()
    total = gc.dialogue_total_chars(story)
    # 剪到差 5 字，并塞可被 sanitize 剥掉的叠尾
    trim = total - DAILY_STORY_BODY_CHARS_MIN + 5
    dlg = story["dialogue"]
    last = dlg[-3]
    line = str(last["line"])
    assert len(line) > trim
    core = line[:-trim].rstrip("！。？…!")
    last["line"] = core + "呢呢！"
    assert gc.dialogue_total_chars(story) < DAILY_STORY_BODY_CHARS_MIN
    out, changed = gc._ensure_gold_chat_min_chars(story)
    assert changed
    assert gc.dialogue_total_chars(out) >= DAILY_STORY_BODY_CHARS_MIN
    assert "呢呢" not in "".join(str(x.get("line") or "") for x in out["dialogue"])


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


def test_body_only_gold_chat_12_lines_skips_opening_penalty():
    """gold_chat 无 discovery_opening、≥12 句时不扣「缺发现开场」。"""
    from app.services.daily_story.quality import score_daily_story

    story = {
        "scene_title": "世子之争",
        "setting": "地板垫上，灿灿和昭昭在抢垫子",
        "conflict_core": "昭昭先动手，灿灿一锤镇住",
        "punchline_explain": "J类权威压住",
        "story_type": "J",
        "dialogue": [
            {"speaker": "昭昭", "line": "世子之争我先占这垫子！"},
            {"speaker": "灿灿", "line": "不行，谁赢谁说了算！"},
        ]
        * 6,
    }
    q = score_daily_story(story, theme="世子之争")
    assert "缺发现开场" not in " ".join(q.get("reasons") or [])


def test_gold_story_to_gold_chat_retries_on_validate_error(monkeypatch):
    calls: dict[str, int | bool] = {"n": 0}
    _bypass_structure_gate(monkeypatch)

    def fake_chat(system: str, _user: str, **_kwargs) -> dict:
        if "编辑" in system:
            calls["fix"] = True
            return _sample_chat()
        calls["n"] = int(calls["n"]) + 1
        bad = _sample_chat()
        bad["dialogue"][0]["line"] = "妈妈说了，抢不过就躲着点。"
        return bad

    monkeypatch.setattr(gc, "_chat_json", fake_chat)
    monkeypatch.setattr(gc, "PASS1_CANDIDATE_COUNT", 1)
    monkeypatch.setattr(gc, "PASS1_REGENERATE_MAX", 1)
    out = gc.gold_story_to_gold_chat(_sample_row())
    assert len(out["dialogue"]) >= 4
    assert calls["n"] == 1
    assert calls.get("fix") is True


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


def test_validate_pass1_shortens_before_full_fix(monkeypatch):
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
    monkeypatch.setattr(gc, "_fix_chat_with_llm", lambda *_a, **_k: (_ for _ in ()).throw(
        AssertionError("should not full fix")
    ))
    story = _sample_chat()
    story["dialogue"][0]["line"] = "你" * 31
    out = gc._validate_pass1_chat(
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
    out = gc.gold_story_to_gold_chat(_sample_row())
    assert out["scene_title"] == "关门练功"
    assert len(out["dialogue"]) >= 4
    assert out["quality"]["structure_score"] == 80


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

    chat = _sample_chat()
    monkeypatch.setattr(gc, "gold_chat_export_dir", lambda _cfg=None: tmp_path)
    monkeypatch.setattr(gce, "gold_chat_export_dir", lambda _cfg=None: tmp_path)
    gc.export_gold_chat_files(source_id=row["source_id"], row=row, chat=chat)

    with app_ctx.app_context():
        out = gc.import_gold_chat_daily_story(row, review=False)
        assert out["action"] == "insert"
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
    from app.services.daily_story.gold_story.collect.llm import (
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


def test_pass1_regen_feedback_includes_short_error():
    from app.services.daily_story.gold_story.gold_chat.prompts import (
        format_pass1_regen_feedback,
    )

    fb = format_pass1_regen_feedback(
        "正文总字数须≥240，当前214",
        None,
        structure_type="C",
        mechanism="M2",
    )
    assert "未满" in fb or "≥240" in fb
    assert "214" in fb or "错误" in fb


def test_pass1_regen_feedback_includes_truncated():
    from app.services.daily_story.gold_story.gold_chat.prompts import (
        format_pass1_regen_feedback,
    )

    fb = format_pass1_regen_feedback(
        "LLM output truncated (finish_reason=length)；对白 JSON 须短小",
        None,
        structure_type="C",
        mechanism="M2",
    )
    assert "截断" in fb or "过长" in fb
    assert "≥240" in fb or "写满" in fb
    assert "最多扩 1 句" not in fb
    assert "禁止复读" in fb or "循环" in fb


def test_is_truncation_error():
    assert gc._is_truncation_error(
        "LLM output truncated (finish_reason=length)；对白 JSON 须短小"
    )
    assert not gc._is_truncation_error("正文总字数须≥240，当前214")


def test_c_force_sibling_alternate_includes_tail():
    story = {
        "story_type": "C",
        "dialogue": [
            {"speaker": "灿灿", "line": f"句{i}"}
            for i in range(10)
        ],
    }
    # 人为制造末段连说
    story["dialogue"][8]["speaker"] = "昭昭"
    story["dialogue"][9]["speaker"] = "昭昭"
    out, changed = gc.patch_c_force_sibling_alternate(story)
    assert changed
    speakers = [d["speaker"] for d in out["dialogue"]]
    for i in range(1, len(speakers)):
        if speakers[i] in {"昭昭", "灿灿"} and speakers[i - 1] in {"昭昭", "灿灿"}:
            assert speakers[i] != speakers[i - 1]


def test_c_possession_criterion_rewrite():
    story = {
        "story_type": "C",
        "dialogue": [
            {"speaker": "灿灿", "line": "我先摸到的，该我！"},
            {"speaker": "昭昭", "line": "谁先吃到归谁"},
            {"speaker": "灿灿", "line": "谁先吃光谁赢"},
        ],
    }
    out, changed = gc.patch_c_possession_criterion(story)
    assert changed
    blob = "".join(str(x.get("line") or "") for x in out["dialogue"])
    assert "摸到" not in blob
    assert "吃到" not in blob
    assert "吃光" not in blob
    assert "拿到" in blob
    from app.services.daily_story.story_types.c.validate import _criterion_drift_error

    lines = [str(x.get("line") or "") for x in out["dialogue"]]
    assert _criterion_drift_error(lines) is None


def test_strip_c_tone_stack_and_safe_pad():
    stacked = "我先拿到的了呢了呀！"
    assert "了呢了呀" not in gc._strip_c_tone_stack_line(stacked)
    story = {
        "story_type": "C",
        "dialogue": [
            {"speaker": "灿灿", "line": "零食归我了呢了呀"},
            {"speaker": "昭昭", "line": "你等着呢呀"},
        ],
    }
    out, changed = gc.patch_sanitize_c_tone_stack(story)
    assert changed
    for item in out["dialogue"]:
        assert not gc._RE_C_TONE_STACK.search(str(item["line"]))
    padded, n = gc._pad_gold_chat_line("我先拿到", 1, used=set(), story_type="C")
    assert n == 1
    assert padded in ("我先拿到啊", "我先拿到吧")
    # 已有语气词：可补短可拍词，但禁叠语气词尾
    same, n2 = gc._pad_gold_chat_line("我先拿到啊", 2, used=set(), story_type="C")
    assert "了呢了呀" not in same
    assert same.startswith("我先拿到啊")
    if n2:
        assert same != "我先拿到啊"


def test_resolve_gold_chat_snippet_cross_source():
    from app.services.daily_story.gold_story.collect.llm import (
        GOLD_CHAT_LINES_SNIPPET,
        resolve_gold_chat_snippet,
    )

    assert resolve_gold_chat_snippet("BV1OTHER") == GOLD_CHAT_LINES_SNIPPET


def test_patch_gold_chat_near_miss_chars():
    story = _sample_chat()
    from app.services.daily_story.prompts import DAILY_STORY_BODY_CHARS_MIN

    total = gc.dialogue_total_chars(story)
    trim = total - DAILY_STORY_BODY_CHARS_MIN + 2
    assert trim > 0
    dlg = story["dialogue"]
    last = dlg[-1]
    line = str(last["line"])
    last["line"] = line[:-trim]
    deficit = DAILY_STORY_BODY_CHARS_MIN - gc.dialogue_total_chars(story)
    assert 0 < deficit <= gc.GOLD_CHAT_NEAR_MISS_DEFICIT_MAX
    patched, changed = gc._patch_gold_chat_near_miss_chars(story)
    assert changed
    assert gc.dialogue_total_chars(patched) >= DAILY_STORY_BODY_CHARS_MIN


def test_pad_gold_chat_line_uses_daily_pad():
    line = "让你玩你咋不哭呢？"
    new, added = gc._pad_gold_chat_line(line, 1)
    assert added == 1
    assert "了呢" in new


def test_patch_sanitize_pad_suffix():
    story = {
        "dialogue": [
            {"speaker": "灿灿", "line": "让你玩你咋不哭呢呢？"},
            {"speaker": "灿灿", "line": "还嘴硬？你呀呢！"},
            {"speaker": "昭昭", "line": "行了吧呢！"},
            {"speaker": "灿灿", "line": "别光嘴上说啊呢。"},
        ],
    }
    out, changed = gc.patch_sanitize_pad_suffix(story)
    assert changed
    lines = [d["line"] for d in out["dialogue"]]
    assert "呢呢" not in "".join(lines)
    assert "你呀呢" not in "".join(lines)
    assert "啊呢" not in "".join(lines)


def test_patch_trim_redundant_ne_suffix_keeps_cancan_and_close():
    story = {
        "dialogue": [
            {"speaker": "昭昭", "line": "你碗里肉这么多，凭什么不能给我夹一块呢！"},
            {"speaker": "灿灿", "line": "那也不行，妈妈说过吃多肉会变胖呢！"},
            {"speaker": "昭昭", "line": "我不管，我就吃一块呢！"},
            {"speaker": "灿灿", "line": "你说话不算话呢！"},
            {"speaker": "昭昭", "line": "哼，不吃就不吃呢！"},
            {"speaker": "昭昭", "line": "这妹妹，八百个心眼子呢！"},
        ],
    }
    out, notes = gcp.patch_trim_redundant_ne_suffix(story, max_ne_suffix=4)
    lines = [d["line"] for d in out["dialogue"]]
    assert any("去冗余呢" in n for n in notes)
    assert lines[0].endswith("夹一块！")
    assert lines[2].endswith("吃一块！")
    assert lines[1].endswith("变胖呢！")
    assert lines[5].endswith("八百个心眼子呢！")
    assert sum(1 for ln in lines if re.search(r"呢[！。!?？]$", ln)) <= 4


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
