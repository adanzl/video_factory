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
    assert detail["dump"]["story_raw"]
    assert detail["has_gold_chat"] is True
    assert detail["gold_chat"]["daily_story"]["scene_title"] == "关门练功"

    list_resp2 = client.get("/v_factory/api/gold_chat/list?limit=10")
    row2 = next(x for x in list_resp2.get_json()["items"] if x["id"] == gid)
    assert row2["has_gold_chat"] is True


def test_api_list_all_statuses(app_ctx):
    with app_ctx.app_context():
        repo_gold_story.insert_or_skip(
            source="bilibili",
            source_id="BV1TESTALL01",
            url="https://www.bilibili.com/video/BV1TESTALL01",
            mechanism="M6",
            structure_type="A",
            story_raw="active样例" * 20,
            payload={"beat": ["a", "b", "c", "d"]},
            title="active样例",
            auto_score=0.9,
            status="active",
        )
        repo_gold_story.insert_or_skip(
            source="bilibili",
            source_id="BV1TESTALL02",
            url="https://www.bilibili.com/video/BV1TESTALL02",
            mechanism="M6",
            structure_type="A",
            story_raw="rejected样例" * 20,
            payload={"beat": ["a", "b", "c", "d"]},
            title="rejected样例",
            auto_score=0.56,
            status="rejected",
        )

    client = app_ctx.test_client()
    active_resp = client.get("/v_factory/api/gold_chat/list?status=active&limit=50")
    assert active_resp.status_code == 200
    active_ids = {x["source_id"] for x in active_resp.get_json()["items"]}
    assert "BV1TESTALL01" in active_ids
    assert "BV1TESTALL02" not in active_ids

    all_resp = client.get("/v_factory/api/gold_chat/list?limit=50")
    assert all_resp.status_code == 200
    all_ids = {x["source_id"] for x in all_resp.get_json()["items"]}
    assert "BV1TESTALL01" in all_ids
    assert "BV1TESTALL02" in all_ids


def test_api_collect(app_ctx, monkeypatch):
    def fake_collect(*, max_candidates=10, **_kwargs):
        return {
            "candidates": 2,
            "inserted": 1,
            "inserted_rejected": 0,
            "results": [
                {"source_id": "BV1NEW001", "action": "insert", "status": "active", "id": 99},
                {"source_id": "BV1OLD001", "action": "skip", "reason": "already_in_db"},
            ],
            "candidates_file": "/tmp/candidates.txt",
        }

    monkeypatch.setattr(
        "app.services.daily_story.gold_story.gold_chat_mgr.run_collect_pipeline",
        fake_collect,
    )

    client = app_ctx.test_client()
    resp = client.post("/v_factory/api/gold_chat/collect", json={"max": 10})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["workflow"] == "gold_story_collect"
    assert body["max"] == 10
    assert body["inserted"] == 1
    assert body["skipped"] == 1
    assert body["failed"] == 0


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


def test_api_get_dump_without_gold_chat(app_ctx):
    inserted = _insert_sample(app_ctx)
    gid = int(inserted["id"])
    client = app_ctx.test_client()
    resp = client.get(f"/v_factory/api/gold_chat/get?id={gid}")
    assert resp.status_code == 200
    detail = resp.get_json()
    assert detail["id"] == gid
    assert detail["dump"]["story_raw"]
    assert detail["has_gold_chat"] is False
    assert detail["gold_chat"] is None


def test_api_get_transcript(app_ctx, tmp_path, monkeypatch):
    inserted = _insert_sample(app_ctx)
    gid = int(inserted["id"])
    transcript_dir = tmp_path / "transcripts"
    transcript_dir.mkdir()
    (transcript_dir / "BV1TESTAPI01.txt").write_text(
        "昭昭：你好。\n灿灿：怎么了？",
        encoding="utf-8",
    )
    (transcript_dir / "BV1TESTAPI01.repaired.txt").write_text(
        "昭昭：你好。\n灿灿：怎么了？",
        encoding="utf-8",
    )

    import app.config as config_mod

    real_config = config_mod.Config

    class PatchedConfig(real_config):
        def __init__(self):
            super().__init__()
            self.gold_story_transcript_dir = transcript_dir

    monkeypatch.setattr(config_mod, "Config", PatchedConfig)
    monkeypatch.setattr(
        "app.services.daily_story.gold_story.gold_chat_mgr.Config",
        PatchedConfig,
    )
    monkeypatch.setattr(
        "app.services.daily_story.gold_story.export_story.Config",
        PatchedConfig,
    )

    client = app_ctx.test_client()
    resp = client.get(f"/v_factory/api/gold_chat/transcript?id={gid}")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["has_transcript"] is True
    assert body["has_repaired"] is True
    assert "昭昭" in body["transcript_raw"]
    assert body["transcript_chars"] > 0


def test_api_get_transcript_empty(app_ctx):
    inserted = _insert_sample(app_ctx)
    gid = int(inserted["id"])
    client = app_ctx.test_client()
    resp = client.get(f"/v_factory/api/gold_chat/transcript?id={gid}")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["has_transcript"] is False
    assert body["transcript"] == ""
