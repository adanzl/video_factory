"""gold_chat 转换测试。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.daily_story.gold_story import gold_chat_convert as gc


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


def test_gold_story_to_gold_chat_retries_when_too_short(monkeypatch):
    calls: dict[str, int | bool] = {"n": 0}

    def fake_chat(system: str, _user: str) -> dict:
        if "编辑" in system:
            calls["fix"] = True
            return _sample_chat()
        calls["n"] = int(calls["n"]) + 1
        bad = _sample_chat()
        bad["dialogue"] = bad["dialogue"][:2]
        return bad

    monkeypatch.setattr(gc, "_chat_json", fake_chat)
    monkeypatch.setattr(gc, "PASS1_CANDIDATE_COUNT", 1)
    monkeypatch.setattr(gc, "PASS1_REGENERATE_MAX", 1)
    out = gc.gold_story_to_gold_chat(_sample_row())
    assert len(out["dialogue"]) >= 4
    assert calls["n"] == 1
    assert calls.get("fix") is True


def test_gold_story_to_gold_chat_retries_on_validate_error(monkeypatch):
    calls: dict[str, int | bool] = {"n": 0}

    def fake_chat(system: str, _user: str) -> dict:
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
    long_line = "你" * 30 + "！"
    assert len(long_line) == 31
    story["dialogue"][0]["line"] = long_line
    out, changed = gc._apply_deterministic_shorten(story)
    assert changed
    assert len(out["dialogue"][0]["line"]) <= 30


def test_validate_pass1_shortens_before_full_fix(monkeypatch):
    calls: list[str] = []

    def fake_validate(story, **kwargs):
        for item in story.get("dialogue") or []:
            if len(str(item.get("line") or "")) > 30:
                raise ValueError("单句过长(max=31>30)")
        return None

    def fake_shorten(story, **_kw):
        calls.append("shorten")
        out = dict(story)
        rows = [dict(x) for x in out["dialogue"]]
        rows[0]["line"] = str(rows[0]["line"])[:30]
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
    assert len(out["dialogue"][0]["line"]) <= 30


def test_gold_story_to_gold_chat(monkeypatch):
    def fake_chat(_system: str, _user: str) -> dict:
        return _sample_chat()

    monkeypatch.setattr(gc, "_chat_json", fake_chat)
    out = gc.gold_story_to_gold_chat(_sample_row())
    assert out["scene_title"] == "关门练功"
    assert len(out["dialogue"]) >= 4


def test_export_gold_chat_files(tmp_path, monkeypatch):
    monkeypatch.setattr(
        gc,
        "gold_chat_export_dir",
        lambda _cfg=None: tmp_path,
    )
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
    from app.services.daily_story.gold_story.llm_steps import (
        GOLD_CHAT_LINES_SNIPPET,
        GOLD_CHAT_LINES_SNIPPET_SOURCE_ID,
        resolve_gold_chat_snippet,
    )

    note = resolve_gold_chat_snippet(GOLD_CHAT_LINES_SNIPPET_SOURCE_ID)
    assert "不注入全文正例" in note
    assert GOLD_CHAT_LINES_SNIPPET not in note


def test_resolve_gold_chat_snippet_cross_source():
    from app.services.daily_story.gold_story.llm_steps import (
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


def test_pad_gold_chat_line_skips_duplicate_ne():
    line = "让你玩你咋不哭呢？"
    new, added = gc._pad_gold_chat_line(line, 1)
    assert added == 0
    assert new == line


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
