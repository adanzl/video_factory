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
    out = gc.gold_story_to_gold_chat(_sample_row())
    assert len(out["dialogue"]) >= 4
    assert calls["n"] == 1
    assert calls.get("fix") is True


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
        out = gc.import_gold_chat_daily_story(row)
        assert out["action"] == "insert"
        ds_id = int(out["daily_story_id"])
        saved = repo_daily_story.get_story(ds_id)
        assert saved["story"]["scene_title"] == "关门练功"

        row["gold_chat_daily_story_id"] = ds_id
        skip = gc.import_gold_chat_daily_story(row)
        assert skip["action"] == "skip"

        chat2 = dict(chat)
        chat2["scene_title"] = "新标题"
        gc.export_gold_chat_files(source_id=row["source_id"], row=row, chat=chat2)
        updated = gc.import_gold_chat_daily_story(row, force=True)
        assert updated["action"] == "update"
        saved2 = repo_daily_story.get_story(ds_id)
        assert saved2["story"]["scene_title"] == "新标题"
