"""gold_chat API 测试。"""

from __future__ import annotations

import pytest

from app.repositories import repo_gold_story
from app.services.daily_story.gold_story.gold_chat import convert as gc
from app.services.daily_story.gold_story.gold_chat import export as gce


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
    n = 0
    while gc.dialogue_total_chars({"dialogue": lines}) < 240:
        n += 1
        if n % 2:
            lines.append({"speaker": "昭昭", "line": f"我再练一招，你别敲门{n}。"})
        else:
            lines.append({"speaker": "灿灿", "line": f"门缝里我看着你呢{n}。"})
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
    monkeypatch.setattr(gce, "gold_chat_export_dir", lambda _cfg=None: tmp_path)

    def fake_chat(_row):
        return _sample_chat()

    monkeypatch.setattr(gc, "gold_story_to_gold_chat", fake_chat)
    monkeypatch.setattr(
        gc,
        "_attach_gold_chat_structure_score",
        lambda chat, _row: {
            **chat,
            "quality": {"structure_score": 80, "score": 80, "summary": "结构80"},
        },
    )
    monkeypatch.setattr(gc, "_gate_gold_chat_structure_score", lambda _chat: 80)

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
    all_items = all_resp.get_json()["items"]
    all_ids = {x["source_id"] for x in all_items}
    assert "BV1TESTALL01" in all_ids
    assert "BV1TESTALL02" in all_ids
    listed_ids = [int(x["id"]) for x in all_items]
    assert listed_ids == sorted(listed_ids, reverse=True)


def test_api_list_has_story(app_ctx):
    with app_ctx.app_context():
        has_row = repo_gold_story.insert_or_skip(
            source="bilibili",
            source_id="BV1HASSTORY01",
            url="https://www.bilibili.com/video/BV1HASSTORY01",
            mechanism="M6",
            structure_type="A",
            story_raw="已导入日常故事样例" * 20,
            payload={"beat": ["a", "b", "c", "d"]},
            title="已导入日常故事",
            auto_score=0.9,
            status="active",
        )
        no_row = repo_gold_story.insert_or_skip(
            source="bilibili",
            source_id="BV1HASSTORY02",
            url="https://www.bilibili.com/video/BV1HASSTORY02",
            mechanism="M6",
            structure_type="A",
            story_raw="未导入日常故事样例" * 20,
            payload={"beat": ["a", "b", "c", "d"]},
            title="未导入日常故事",
            auto_score=0.9,
            status="active",
        )
        assert has_row.get("action") == "insert"
        assert no_row.get("action") == "insert"
        repo_gold_story.set_gold_chat_daily_story_id(int(has_row["id"]), 999)

    client = app_ctx.test_client()
    yes_resp = client.get("/v_factory/api/gold_chat/list?has_story=true&limit=50")
    assert yes_resp.status_code == 200
    yes_ids = {x["source_id"] for x in yes_resp.get_json()["items"]}
    assert "BV1HASSTORY01" in yes_ids
    assert "BV1HASSTORY02" not in yes_ids
    yes_row = next(x for x in yes_resp.get_json()["items"] if x["source_id"] == "BV1HASSTORY01")
    assert yes_row["gold_chat_daily_story_id"] == 999

    no_resp = client.get("/v_factory/api/gold_chat/list?has_story=false&limit=50")
    assert no_resp.status_code == 200
    no_ids = {x["source_id"] for x in no_resp.get_json()["items"]}
    assert "BV1HASSTORY01" not in no_ids
    assert "BV1HASSTORY02" in no_ids


def test_api_delete(app_ctx, tmp_path, monkeypatch):
    inserted = _insert_sample(app_ctx)
    gid = int(inserted["id"])

    import app.config as config_mod
    from app.services.daily_story.gold_story import export_story as es

    transcript_dir = tmp_path / "transcripts"
    transcript_dir.mkdir()
    (transcript_dir / "BV1TESTAPI01.txt").write_text("test", encoding="utf-8")

    class PatchedConfig(config_mod.Config):
        def __init__(self):
            super().__init__()
            self.gold_story_transcript_dir = transcript_dir
            self.gold_story_media_workspace = tmp_path / "media"

    monkeypatch.setattr(config_mod, "Config", PatchedConfig)
    monkeypatch.setattr("app.services.daily_story.gold_story.gold_story_mgr.Config", PatchedConfig)
    monkeypatch.setattr(es, "Config", PatchedConfig)

    client = app_ctx.test_client()
    resp = client.post("/v_factory/api/gold_chat/delete", json={"ids": [gid]})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["deleted"] == 1
    assert gid in body["ids"]

    list_resp = client.get("/v_factory/api/gold_chat/list?limit=50")
    ids = {x["id"] for x in list_resp.get_json()["items"]}
    assert gid not in ids


def test_api_reject(app_ctx):
    inserted = _insert_sample(app_ctx)
    gid = int(inserted["id"])
    client = app_ctx.test_client()

    resp = client.post("/v_factory/api/gold_chat/reject", json={"ids": [gid]})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["rejected"] == 1
    assert gid in body["ids"]

    again = client.post("/v_factory/api/gold_chat/reject", json={"ids": [gid]})
    assert again.status_code == 200
    assert again.get_json()["rejected"] == 0
    assert again.get_json()["skipped"] == 1

    list_resp = client.get("/v_factory/api/gold_chat/list?status=rejected&limit=50")
    assert list_resp.status_code == 200
    ids = {x["id"] for x in list_resp.get_json()["items"]}
    assert gid in ids
    row = next(x for x in list_resp.get_json()["items"] if x["id"] == gid)
    assert row["status"] == "rejected"

def test_api_collect(app_ctx, monkeypatch):
    from app.services.daily_story.gold_story import gold_story_mgr as mgr_mod

    mgr_mod.reset_collect_state()
    workers: list = []

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

    monkeypatch.setattr(mgr_mod, "run_collect_pipeline", fake_collect)
    monkeypatch.setattr(mgr_mod, "run_in_os_thread", lambda func, **_kwargs: workers.append(func))

    client = app_ctx.test_client()
    resp = client.post("/v_factory/api/gold_chat/collect", json={"max": 10})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["workflow"] == "gold_story_collect"
    assert body["status"] == "running"
    assert body["max"] == 10
    assert body["inserted"] == 0
    assert len(workers) == 1

    busy = client.post("/v_factory/api/gold_chat/collect", json={"max": 10})
    assert busy.status_code == 409
    assert busy.get_json()["code"] == "collect_busy"

    workers[0]()
    status = client.get("/v_factory/api/gold_chat/collect").get_json()
    assert status["status"] == "done"
    assert status["inserted"] == 1
    assert status["skipped"] == 1
    assert status["failed"] == 0
    mgr_mod.reset_collect_state()


def test_api_reimport(app_ctx, monkeypatch):
    from app.services.daily_story.gold_story import gold_story_mgr as mgr_mod

    mgr_mod.reset_collect_state()
    workers: list = []

    def fake_reimport(**_kwargs):
        return {
            "requested": 1,
            "updated": 1,
            "inserted": 0,
            "rejected": 0,
            "failed": 0,
            "ok": 1,
            "results": [
                {
                    "id": 13,
                    "source_id": "BV1Ci4y1L7jg",
                    "action": "ok",
                },
            ],
        }

    monkeypatch.setattr(mgr_mod, "reimport_stories", fake_reimport)
    monkeypatch.setattr(mgr_mod, "run_in_os_thread", lambda func, **_kwargs: workers.append(func))

    client = app_ctx.test_client()
    resp = client.post(
        "/v_factory/api/gold_chat/reimport",
        json={"source_id": "BV1Ci4y1L7jg"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["workflow"] == "gold_story_reimport"
    assert body["status"] == "running"
    assert body["source_ids"] == ["BV1Ci4y1L7jg"]
    assert len(workers) == 1

    busy = client.post(
        "/v_factory/api/gold_chat/reimport",
        json={"ids": [13]},
    )
    assert busy.status_code == 409
    assert busy.get_json()["code"] == "reimport_busy"

    collect_free = client.post("/v_factory/api/gold_chat/collect", json={"max": 10})
    # 采集与重新导入互不锁：reimport 运行中 collect 可正常启动
    assert collect_free.status_code == 200
    assert collect_free.get_json()["workflow"] == "gold_story_collect"
    assert collect_free.get_json()["status"] == "running"

    workers[0]()
    status = client.get("/v_factory/api/gold_chat/reimport").get_json()
    assert status["status"] == "done"
    assert status["updated"] == 1
    assert status["ok"] == 1
    mgr_mod.reset_collect_state()


def test_api_reimport_requires_target(app_ctx):
    from app.services.daily_story.gold_story import gold_story_mgr as mgr_mod

    mgr_mod.reset_collect_state()
    client = app_ctx.test_client()
    resp = client.post("/v_factory/api/gold_chat/reimport", json={})
    assert resp.status_code == 400


def test_api_batch(app_ctx, monkeypatch, tmp_path):
    inserted = _insert_sample(app_ctx)
    gid = int(inserted["id"])
    monkeypatch.setattr(gc, "gold_chat_export_dir", lambda _cfg=None: tmp_path)
    monkeypatch.setattr(gce, "gold_chat_export_dir", lambda _cfg=None: tmp_path)
    monkeypatch.setattr(gc, "gold_story_to_gold_chat", lambda _row: _sample_chat())
    monkeypatch.setattr(
        gc,
        "_attach_gold_chat_structure_score",
        lambda chat, _row: {
            **chat,
            "quality": {"structure_score": 80, "score": 80, "summary": "结构80"},
        },
    )
    monkeypatch.setattr(gc, "_gate_gold_chat_structure_score", lambda _chat: 80)

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
    assert detail.get("gold_chat_error") is None


def test_api_convert_failure_records_error(app_ctx, monkeypatch):
    inserted = _insert_sample(app_ctx)
    gid = int(inserted["id"])

    def boom(_row, *, config=None):
        raise ValueError("对白 10 句/110 字不足")

    monkeypatch.setattr(
        "app.services.daily_story.gold_story.gold_story_mgr.convert_gold_chat",
        boom,
    )

    client = app_ctx.test_client()
    convert_resp = client.post("/v_factory/api/gold_chat/convert", json={"id": gid})
    assert convert_resp.status_code == 400
    assert "不足" in convert_resp.get_json()["error"]

    get_resp = client.get(f"/v_factory/api/gold_chat/get?id={gid}")
    assert get_resp.status_code == 200
    detail = get_resp.get_json()
    err = detail.get("gold_chat_error") or {}
    assert "不足" in err.get("error", "")
    assert err.get("failed_at")


def test_api_get_includes_audit(app_ctx):
    with app_ctx.app_context():
        inserted = repo_gold_story.insert_or_skip(
            source="bilibili",
            source_id="BV1TESTAUDIT01",
            url="https://www.bilibili.com/video/BV1TESTAUDIT01",
            mechanism="M6",
            structure_type="A",
            story_raw="机审驳回样例" * 20,
            payload={
                "beat": ["a", "b", "c", "d"],
                "audit": {
                    "pass": False,
                    "stage": "llm",
                    "reject_reasons": ["冲突太短", "家长当唯一主角"],
                    "llm": {
                        "sibling_fit": 0.2,
                        "age_fit": 0.1,
                        "conflict_usable": 0.2,
                        "mapping_fit": 0.3,
                        "audit_notes": "原稿家长独白过多",
                    },
                },
            },
            title="机审驳回样例",
            auto_score=0.9,
            status="rejected",
        )
        gid = int(inserted["id"])

    client = app_ctx.test_client()
    resp = client.get(f"/v_factory/api/gold_chat/get?id={gid}")
    assert resp.status_code == 200
    detail = resp.get_json()
    audit = detail.get("audit") or {}
    assert audit.get("pass") is False
    assert audit.get("stage") == "llm"
    assert "冲突太短" in (audit.get("reject_reasons") or [])
    assert audit.get("audit_notes") == "原稿家长独白过多"
    assert audit.get("llm_scores", {}).get("sibling_fit") == 0.2


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
        "app.services.daily_story.gold_story.gold_story_mgr.Config",
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
