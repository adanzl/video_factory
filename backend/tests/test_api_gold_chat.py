"""gold_chat API 测试。"""

from __future__ import annotations

import pytest

from app.repositories import repo_gold_story
from app.services.daily_story.gold_story import gold_chat_convert as gc


def _insert_sample(app_ctx) -> dict:
    with app_ctx.app_context():
        result = repo_gold_story.insert_or_skip(
            source="bilibili",
            source_id="BV1TESTAPI01",
            url="https://www.bilibili.com/video/BV1TESTAPI01",
            mechanism="M6",
            structure_type="A",
            story_raw="测试故事" * 20,
            payload={
                "beat": ["a", "b", "c", "d"],
                "dialogue_seed": [
                    {"speaker": "昭昭", "intent": "抱怨"},
                    {"speaker": "灿灿", "intent": "得意"},
                ],
                "closing_intent": "收束",
                "banned_literals": ["测试禁词"],
                "setting": "客厅",
            },
            title="API测试金故事",
            conflict_core="姐弟抢东西",
            extract_confidence=0.8,
            structure_confidence=0.8,
            dialogue_confidence=0.8,
            auto_score=0.9,
            status="active",
        )
        return result


def _sample_chat() -> dict:
    lines = [
        {"speaker": "昭昭", "line": "你刚才又抢我遥控器，我还不敢说。"},
        {"speaker": "灿灿", "line": "谁让你手慢，我先用就是我的。"},
    ]
    while gc.dialogue_total_chars({"dialogue": lines}) < 240:
        lines.append({"speaker": "昭昭", "line": "我就是先歇一会儿，又不是怕你。"})
    return {
        "scene_title": "关门练功",
        "setting": "卧室门口",
        "key": "关门练功",
        "conflict_core": "弟弟幻想报复姐姐，开门秒怂",
        "dialogue": lines,
        "punchline_explain": "A类嘴硬加码：幻想英勇开门就怂",
    }


def test_api_list_and_convert(app_ctx, monkeypatch, tmp_path):
    inserted = _insert_sample(app_ctx)
    assert inserted.get("action") == "insert"
    gid = int(inserted["id"])

    monkeypatch.setattr(gc, "gold_chat_export_dir", lambda _cfg=None: tmp_path)

    def fake_chat(_row):
        return _sample_chat()

    monkeypatch.setattr(gc, "gold_story_to_gold_chat", fake_chat)

    client = app_ctx.test_client()
    list_resp = client.get("/v_factory/api/gold_chat/list?limit=10")
    assert list_resp.status_code == 200
    payload = list_resp.get_json()
    assert payload["total"] >= 1
    row = next(x for x in payload["items"] if x["id"] == gid)
    assert row["has_gold_chat"] is False

    convert_resp = client.post(
        "/v_factory/api/gold_chat/convert",
        json={"id": gid},
    )
    assert convert_resp.status_code == 200
    convert_data = convert_resp.get_json()
    assert convert_data["action"] == "ok"
    assert convert_data["chat_lines"] >= 4

    get_resp = client.get(f"/v_factory/api/gold_chat/get?id={gid}")
    assert get_resp.status_code == 200
    detail = get_resp.get_json()
    assert detail["daily_story"]["scene_title"] == "关门练功"

    list_resp2 = client.get("/v_factory/api/gold_chat/list?limit=10")
    row2 = next(x for x in list_resp2.get_json()["items"] if x["id"] == gid)
    assert row2["has_gold_chat"] is True


def test_api_batch(app_ctx, monkeypatch, tmp_path):
    inserted = _insert_sample(app_ctx)
    gid = int(inserted["id"])
    monkeypatch.setattr(gc, "gold_chat_export_dir", lambda _cfg=None: tmp_path)
    monkeypatch.setattr(gc, "gold_story_to_gold_chat", lambda _row: _sample_chat())

    client = app_ctx.test_client()
    batch_resp = client.post(
        "/v_factory/api/gold_chat/batch",
        json={"ids": [gid], "max": 1},
    )
    assert batch_resp.status_code == 200
    report = batch_resp.get_json()
    assert report["ok"] == 1
    assert report["results"][0]["action"] == "ok"


def test_api_get_missing_export(app_ctx):
    inserted = _insert_sample(app_ctx)
    gid = int(inserted["id"])
    client = app_ctx.test_client()
    resp = client.get(f"/v_factory/api/gold_chat/get?id={gid}")
    assert resp.status_code == 404
