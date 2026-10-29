"""gold_chat API 测试。"""

from __future__ import annotations

import pytest

from app.repositories import repo_gold_story
from app.services.gold_story.gold_chat import convert as gc
from app.services.gold_story.gold_chat import export as gce
from app.services.gold_story.gold_chat import finalize as gcf


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


@pytest.mark.parametrize("batch", [False, True])
@pytest.mark.parametrize("failed", [False, True])
def test_legacy_client_without_async_receives_result_or_error_not_task(app_ctx, monkeypatch, batch, failed):
    import importlib
    mgr = importlib.import_module("app.services.gold_story.gold_story_mgr")
    expected = {"ok": 1, "selected": 1} if batch else {"action": "ok", "chat_lines": 12}

    def convert(**_kwargs):
        if failed:
            raise ValueError("network:503 Service Unavailable")
        return expected

    monkeypatch.setattr(mgr.gold_story_mgr, "batch_convert" if batch else "convert_one", convert)
    monkeypatch.setattr(mgr.gold_story_mgr, "submit_batch_conversion" if batch else "submit_conversion",
                        lambda **_kw: pytest.fail("旧客户端不能收到异步任务回执"))
    response = app_ctx.test_client().post(
        "/v_factory/api/gold_chat/batch" if batch else "/v_factory/api/gold_chat/convert",
        json={"ids": [160]} if batch else {"id": 160},
    )
    assert response.status_code == (400 if failed else 200)
    body = response.get_json()
    assert "task_id" not in body
    if failed:
        assert "503" in body["error"]
    else:
        assert body == expected


def test_async_conversion_persists_task_and_duplicate_submission_reattaches(app_ctx, monkeypatch):
    import importlib
    mgr = importlib.import_module("app.services.gold_story.gold_story_mgr")
    gid = int(_insert_sample(app_ctx)["id"])
    callbacks = []
    monkeypatch.setattr(mgr, "run_in_background", callbacks.append)
    monkeypatch.setattr(mgr.gold_story_mgr, "_convert_one_unlocked",
                        lambda **_kw: {"action": "ok", "chat_lines": 12})
    client = app_ctx.test_client()
    submitted = client.post("/v_factory/api/gold_chat/convert", json={"id": gid, "async": True})
    assert submitted.status_code == 202
    task = submitted.get_json()
    assert task["status"] == "queued"
    duplicate = client.post("/v_factory/api/gold_chat/convert", json={"id": gid, "async": True}).get_json()
    assert duplicate["task_id"] == task["task_id"]
    assert len(callbacks) == 1
    callbacks[0]()
    result = client.get(f"/v_factory/api/gold_chat/convert?id={gid}&task_id={task['task_id']}")
    assert result.get_json()["status"] == "succeeded"
    assert result.get_json()["result"]["chat_lines"] == 12
    assert client.get(f"/v_factory/api/gold_chat/convert?id={gid}&task_id=wrong").status_code == 404


def test_async_conversion_records_failure_and_expired_task(app_ctx, monkeypatch):
    import importlib
    mgr = importlib.import_module("app.services.gold_story.gold_story_mgr")
    gid = int(_insert_sample(app_ctx)["id"])
    callbacks = []
    monkeypatch.setattr(mgr, "run_in_background", callbacks.append)

    def fail(**_kw):
        raise ValueError("候选第4句前提缺失")

    monkeypatch.setattr(mgr.gold_story_mgr, "_convert_one_unlocked", fail)
    client = app_ctx.test_client()
    task = client.post("/v_factory/api/gold_chat/convert", json={"id": gid, "async": True}).get_json()
    callbacks[0]()
    result = mgr.gold_story_mgr.conversion_task(gid, task["task_id"])
    assert result["status"] == "failed"
    assert result["error"] == "候选第4句前提缺失"
    result.update(status="running", expires_at=1)
    # 模拟进程中断留下的状态；正常更新已不允许把终态改回 running。
    repo_gold_story.patch_story_payload(gid, {"gold_chat_task": result,
        "gold_chat_convert_status": "converting",
        "gold_chat_convert_started_at": "2099-01-01T00:00:00+00:00"})
    expired = mgr.gold_story_mgr.conversion_task(gid, task["task_id"])
    assert expired["status"] == "failed"
    assert expired["code"] == "task_interrupted"
    assert mgr.gold_story_mgr.convert_status()["ids"] == []
    result.update(status="succeeded")
    repo_gold_story.update_chat_task(gid, result)
    assert mgr.gold_story_mgr.conversion_task(gid, task["task_id"])["status"] == "failed"


def _accepted_api_chat(chat, row, *, funny_score=11):
    from app.services.daily_story.quality import gold_story_review_contract, stamp_gold_chat_acceptance_quality

    stamp_gold_chat_acceptance_quality(
        chat, review_issues=[], humor={"funny_score": funny_score} if funny_score is not None else None,
        chatter_signals=[], semantic_pass=True, review_contract=gold_story_review_contract(row, chat),
    )
    return chat


@pytest.mark.parametrize("funny_score", [11, 9, None])
def test_api_list_and_convert(app_ctx, monkeypatch, tmp_path, funny_score):
    inserted = _insert_sample(app_ctx)
    assert inserted.get("action") == "insert"
    gid = int(inserted["id"])

    monkeypatch.setattr(gc, "gold_chat_export_dir", lambda _cfg=None: tmp_path)
    monkeypatch.setattr(gce, "gold_chat_export_dir", lambda _cfg=None: tmp_path)

    def fake_chat(_row, **kwargs):
        return _sample_chat()

    monkeypatch.setattr(gc, "gold_story_to_gold_chat", fake_chat)
    monkeypatch.setattr(gc, "_refine_after_normalize", lambda chat, *_a, **_kw: chat)
    monkeypatch.setattr(gc, "_rebuild_h3a_h3b_on_convert", lambda row: row)
    monkeypatch.setattr(
        gc,
        "_attach_gold_chat_structure_score",
        lambda chat, _row: {
            **chat,
            "quality": {"structure_score": 80, "score": 80, "summary": "结构80"},
        },
    )
    monkeypatch.setattr(gc, "_gate_gold_chat_structure_score", lambda _chat: 80)
    monkeypatch.setattr(
        gcf,
        "run_gold_chat_final_acceptance",
        lambda chat, row, sid: _accepted_api_chat(chat, row, funny_score=funny_score),
    )

    client = app_ctx.test_client()
    list_resp = client.get("/v_factory/api/gold_chat/list?limit=10")
    assert list_resp.status_code == 200
    payload = list_resp.get_json()
    assert payload["total"] >= 1
    row = next(x for x in payload["items"] if x["id"] == gid)
    assert row["has_gold_chat"] is False

    convert_resp = client.post(
        "/v_factory/api/gold_chat/convert",
        json={"id": gid, "async": False},
    )
    if funny_score != 11:
        assert convert_resp.status_code == 400
        assert "好笑" in str(convert_resp.get_json())
        detail = client.get(f"/v_factory/api/gold_chat/get?id={gid}").get_json()
        assert detail["has_gold_chat"] is False
        fresh = repo_gold_story.get_story(gid)
        from app.services.gold_story.gold_chat.status import gold_chat_recovery

        recovery = gold_chat_recovery(fresh)
        assert recovery["candidate"]["dialogue"]
        assert "好笑" in recovery["candidate"]["quality"]["review_failure_reason"]
        assert not (tmp_path / (fresh["source_id"] + ".json")).exists()
        return
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
    from app.services.gold_story import export_story as es

    transcript_dir = tmp_path / "transcripts"
    transcript_dir.mkdir()
    (transcript_dir / "BV1TESTAPI01.txt").write_text("test", encoding="utf-8")

    class PatchedConfig(config_mod.Config):
        def __init__(self):
            super().__init__()
            self.gold_story_transcript_dir = transcript_dir
            self.gold_story_media_workspace = tmp_path / "media"

    monkeypatch.setattr(config_mod, "Config", PatchedConfig)
    monkeypatch.setattr("app.services.gold_story.gold_story_mgr.Config", PatchedConfig)
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


def test_api_archive(app_ctx):
    inserted = _insert_sample(app_ctx)
    gid = int(inserted["id"])
    client = app_ctx.test_client()

    resp = client.post("/v_factory/api/gold_chat/archive", json={"ids": [gid]})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["archived"] == 1
    assert gid in body["ids"]

    again = client.post("/v_factory/api/gold_chat/archive", json={"ids": [gid]})
    assert again.status_code == 200
    assert again.get_json()["archived"] == 0
    assert again.get_json()["skipped"] == 1

    list_resp = client.get("/v_factory/api/gold_chat/list?status=archived&limit=50")
    assert list_resp.status_code == 200
    ids = {x["id"] for x in list_resp.get_json()["items"]}
    assert gid in ids
    row = next(x for x in list_resp.get_json()["items"] if x["id"] == gid)
    assert row["status"] == "archived"

    hidden = client.get("/v_factory/api/gold_chat/list?exclude_archived=true&limit=50")
    assert hidden.status_code == 200
    hidden_ids = {x["id"] for x in hidden.get_json()["items"]}
    assert gid not in hidden_ids


def test_api_collect(app_ctx, monkeypatch):
    from app.services.gold_story import gold_story_mgr as mgr_mod

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
    from app.services.gold_story import gold_story_mgr as mgr_mod

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
    from app.services.gold_story import gold_story_mgr as mgr_mod

    mgr_mod.reset_collect_state()
    client = app_ctx.test_client()
    resp = client.post("/v_factory/api/gold_chat/reimport", json={})
    assert resp.status_code == 400


def test_api_batch(app_ctx, monkeypatch, tmp_path):
    inserted = _insert_sample(app_ctx)
    gid = int(inserted["id"])
    monkeypatch.setattr(gc, "gold_chat_export_dir", lambda _cfg=None: tmp_path)
    monkeypatch.setattr(gce, "gold_chat_export_dir", lambda _cfg=None: tmp_path)
    monkeypatch.setattr(
        gc,
        "gold_story_to_gold_chat",
        lambda _row, **kwargs: _sample_chat(),
    )
    monkeypatch.setattr(gc, "_refine_after_normalize", lambda chat, *_a, **_kw: chat)
    monkeypatch.setattr(gc, "_rebuild_h3a_h3b_on_convert", lambda row: row)
    monkeypatch.setattr(
        gc,
        "_attach_gold_chat_structure_score",
        lambda chat, _row: {
            **chat,
            "quality": {"structure_score": 80, "score": 80, "summary": "结构80"},
        },
    )
    monkeypatch.setattr(gc, "_gate_gold_chat_structure_score", lambda _chat: 80)
    monkeypatch.setattr(
        gcf,
        "run_gold_chat_final_acceptance",
        lambda chat, row, sid: _accepted_api_chat(chat, row),
    )

    client = app_ctx.test_client()
    batch_resp = client.post(
        "/v_factory/api/gold_chat/batch",
        json={"ids": [gid], "max": 1, "async": False},
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
        "app.services.gold_story.gold_story_mgr.convert_gold_chat",
        boom,
    )

    client = app_ctx.test_client()
    convert_resp = client.post("/v_factory/api/gold_chat/convert", json={"id": gid, "async": False})
    assert convert_resp.status_code == 400
    assert "不足" in convert_resp.get_json()["error"]

    get_resp = client.get(f"/v_factory/api/gold_chat/get?id={gid}")
    assert get_resp.status_code == 200
    detail = get_resp.get_json()
    err = detail.get("gold_chat_error") or {}
    assert "不足" in err.get("error", "")
    assert err.get("failed_at")

    list_resp = client.get("/v_factory/api/gold_chat/list?limit=100")
    assert list_resp.status_code == 200
    row = next(x for x in list_resp.get_json()["items"] if x["id"] == gid)
    assert row.get("has_gold_chat") is False
    list_err = row.get("gold_chat_error") or {}
    assert "不足" in list_err.get("error", "")
    assert list_err.get("failed_at")


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
        "app.services.gold_story.gold_story_mgr.Config",
        PatchedConfig,
    )
    monkeypatch.setattr(
        "app.services.gold_story.export_story.Config",
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


def test_async_start_failure_releases_task_and_lock(app_ctx, monkeypatch):
    import importlib
    mgr = importlib.import_module("app.services.gold_story.gold_story_mgr")
    gid = int(_insert_sample(app_ctx)["id"])

    def fail_start(_run):
        raise OSError("无法启动后台任务")

    monkeypatch.setattr(mgr, "run_in_background", fail_start)
    with pytest.raises(OSError):
        mgr.gold_story_mgr.submit_conversion(gold_story_id=gid)
    task = repo_gold_story.get_story(gid)["payload"]["gold_chat_task"]
    assert task["status"] == "failed"
    assert task["code"] == "task_start_failed"
    assert mgr._CONVERT_LOCK.acquire(blocking=False)
    mgr._CONVERT_LOCK.release()


def test_async_batch_completes_and_query_missing_story_returns_404(app_ctx, monkeypatch):
    import importlib
    mgr = importlib.import_module("app.services.gold_story.gold_story_mgr")
    gid = int(_insert_sample(app_ctx)["id"])
    callbacks = []
    monkeypatch.setattr(mgr, "run_in_background", callbacks.append)
    monkeypatch.setattr(mgr, "run_gold_chat_batch", lambda **kw: {"ok": 1, "selected": len(kw["gold_story_ids"])})
    client = app_ctx.test_client()
    response = client.post("/v_factory/api/gold_chat/batch", json={"ids": [gid], "async": True})
    assert response.status_code == 202
    task = response.get_json()
    callbacks[0]()
    done = mgr.gold_story_mgr.conversion_task(gid, task["task_id"])
    assert done["status"] == "succeeded"
    assert done["result"] == {"ok": 1, "selected": 1}
    assert client.get("/v_factory/api/gold_chat/convert?id=999999&task_id=unknown").status_code == 404


@pytest.mark.parametrize("outcome", ["ok", "semantic_failure", "timeout", "publish_failure", "source_changed"])
def test_review_candidate_reuses_body_and_preserves_old_export(app_ctx, monkeypatch, tmp_path, outcome):
    import importlib
    import time
    from copy import deepcopy
    from app.services.gold_story.gold_chat.status import record_gold_chat_failure, gold_chat_recovery
    from app.services.gold_story.gold_chat import import_story
    from app.services.daily_story.quality import gold_story_review_contract, stamp_story_review_binding

    mgr = importlib.import_module("app.services.gold_story.gold_story_mgr")
    gid = int(_insert_sample(app_ctx)["id"])
    row = repo_gold_story.get_story(gid)
    monkeypatch.setattr(gce, "gold_chat_export_dir", lambda _cfg=None: tmp_path)
    monkeypatch.setattr(gce, "export_story_files", lambda **kw: None)
    old = _sample_chat()
    paths = gce.export_gold_chat_files(source_id=row["source_id"], row=row, chat=old)
    repo_gold_story.patch_story_payload(gid, {"gold_chat_json": paths["json"], "gold_chat_md": paths["markdown"]})
    candidate = deepcopy(old)
    candidate["dialogue"][0]["line"] = "我这次已经把事情说清楚啦。"
    error = gcf.GoldChatAcceptanceIncomplete("review unavailable", candidate=candidate)
    record_gold_chat_failure(gid, error, stage="finalize")
    row = repo_gold_story.get_story(gid)
    revision = gold_chat_recovery(row)["revision"]
    validations = []
    monkeypatch.setattr(import_story, "validate_gold_chat_story_for_row", lambda *a: validations.append(1))

    def score(chat, row):
        chat["quality"] = {"structure_score": 80, "humor": {"funny_score": 12}}
        return chat

    def accept(chat, row, **kwargs):
        assert kwargs["preserve_dialogue"] is True
        if outcome == "semantic_failure":
            raise gcf.GoldChatSemanticBlocked("错误不能放行")
        if outcome == "timeout":
            time.sleep(1)
        if outcome == "source_changed":
            repo_gold_story.patch_story_payload(gid, {"closing_intent": "审核期间修改契约"})
        stamp_story_review_binding(chat, semantic_pass=True, review_contract=gold_story_review_contract(row, chat))
        return chat

    monkeypatch.setattr(gc, "_attach_gold_chat_structure_score", score)
    monkeypatch.setattr(gcf, "run_gold_chat_final_acceptance", accept)
    monkeypatch.setattr(gc, "gold_story_to_gold_chat", lambda *a, **k: pytest.fail("恢复审核不得重生成"))
    if outcome == "timeout":
        monkeypatch.setenv("GOLD_CHAT_TIME_BUDGET_S", "0.05")
    if outcome == "publish_failure":
        monkeypatch.setattr(gc, "_backfill_gold_story_after_export", lambda *a, **k: (_ for _ in ()).throw(OSError("DB write failed")))
    callbacks = []
    monkeypatch.setattr(mgr, "run_in_background", callbacks.append)
    client = app_ctx.test_client()
    response = client.post("/v_factory/api/gold_chat/review", json={"id": gid, "revision": revision})
    assert response.status_code == 202
    task = response.get_json()
    duplicate = client.post("/v_factory/api/gold_chat/review", json={"id": gid, "revision": revision})
    assert duplicate.get_json()["task_id"] == task["task_id"]
    assert len(callbacks) == 1
    callbacks[0]()
    result = client.get(f"/v_factory/api/gold_chat/convert?id={gid}&task_id={task['task_id']}").get_json()
    fresh = repo_gold_story.get_story(gid)
    exported = gce.load_gold_chat_for_row(fresh)
    if outcome == "ok":
        assert result["status"] == "succeeded"
        assert len(validations) >= 2
        assert exported["daily_story"]["dialogue"] == candidate["dialogue"]
        assert gold_chat_recovery(fresh) is None
        assert client.post("/v_factory/api/gold_chat/review", json={"id": gid, "revision": revision}).status_code == 409
    else:
        assert result["status"] == "failed"
        if outcome == "timeout":
            assert result["code"] == "time_budget_exceeded"
        assert exported["daily_story"] == old
        if outcome == "source_changed":
            assert "契约已变化" in result["error"]
            assert gold_chat_recovery(fresh)["revision"] is None
        assert len(list((tmp_path / ".versions" / row["source_id"]).iterdir())) == 1
        assert gold_chat_recovery(fresh)["candidate"]["dialogue"] == candidate["dialogue"]
    assert client.get("/v_factory/api/gold_chat/convert").get_json()["ids"] == []


def test_review_candidate_rejects_changed_source_and_revision(app_ctx, monkeypatch):
    import importlib
    from app.services.gold_story.gold_chat.status import record_gold_chat_failure, gold_chat_recovery
    mgr = importlib.import_module("app.services.gold_story.gold_story_mgr")
    gid = int(_insert_sample(app_ctx)["id"])
    record_gold_chat_failure(gid, gcf.GoldChatAcceptanceIncomplete("pending", candidate=_sample_chat()))
    revision = gold_chat_recovery(repo_gold_story.get_story(gid))["revision"]
    monkeypatch.setattr(mgr, "run_in_background", lambda fn: pytest.fail("不得启动过期候选"))
    client = app_ctx.test_client()
    assert client.post("/v_factory/api/gold_chat/review", json={"id": gid, "revision": "old"}).status_code == 409
    repo_gold_story.patch_story_payload(gid, {"closing_intent": "来源已修改"})
    assert client.post("/v_factory/api/gold_chat/review", json={"id": gid, "revision": revision}).status_code == 409
    detail = client.get(f"/v_factory/api/gold_chat/get?id={gid}").get_json()
    assert detail["gold_chat_recovery"]["revision"] is None


def test_compact_payload_legacy_conversion_remains_visible(app_ctx):
    from app.services.gold_story.gold_chat.status import mark_gold_chat_converting, list_gold_chat_converting, clear_gold_chat_converting
    gid = int(_insert_sample(app_ctx)["id"])
    mark_gold_chat_converting(gid)
    assert gid in list_gold_chat_converting()["ids"]
    clear_gold_chat_converting(gid)
    assert gid not in list_gold_chat_converting()["ids"]


def test_publish_cas_uses_exact_db_snapshot_and_rejects_changed_payload(app_ctx):
    import json
    from app.repositories import sql_exec as sql
    gid = int(_insert_sample(app_ctx)["id"])
    # 兼容外部写入的 Unicode 转义、空白及键序，不重编码后误判冲突。
    raw = json.dumps({"z": "中文", "a": {"field": 1}}, ensure_ascii=True, indent=4)
    sql.execute("UPDATE gold_story SET payload_json=? WHERE id=?", (raw, gid))
    sql.commit()
    row = repo_gold_story.get_story(gid, include_payload_snapshot=True)
    repo_gold_story.publish_chat_export(gid, {"gold_chat_json": "v1.json"}, expected_row=row)
    assert repo_gold_story.get_story(gid)["payload"]["gold_chat_json"] == "v1.json"
    stale = repo_gold_story.get_story(gid, include_payload_snapshot=True)
    repo_gold_story.patch_story_payload(gid, {"closing_intent": "changed"})
    with pytest.raises(RuntimeError):
        repo_gold_story.publish_chat_export(gid, {"gold_chat_json": "v2.json"}, expected_row=stale)
    assert repo_gold_story.get_story(gid)["payload"]["gold_chat_json"] == "v1.json"


@pytest.mark.parametrize("accepted", [True, False])
def test_polish_uses_reviewed_db_version_and_keeps_previous_on_rejection(app_ctx, monkeypatch, tmp_path, accepted):
    from copy import deepcopy
    from app.services.gold_story.gold_chat import polish, import_story
    from app.services.daily_story.quality import stamp_story_review_binding, gold_story_review_contract
    gid = int(_insert_sample(app_ctx)["id"])
    row = repo_gold_story.get_story(gid)
    monkeypatch.setattr(gce, "gold_chat_export_dir", lambda _cfg=None: tmp_path)
    monkeypatch.setattr(gce, "export_story_files", lambda **kw: None)
    old = _sample_chat()
    paths = gce.export_gold_chat_files(source_id=row["source_id"], row=row, chat=old)
    repo_gold_story.patch_story_payload(gid, {"gold_chat_json": paths["json"], "gold_chat_md": paths["markdown"]})
    proposed = deepcopy(old)
    proposed["dialogue"][0]["line"] = "这次我把前因后果都讲清楚了。"
    monkeypatch.setattr(polish, "collect_gold_chat_polish_issues", lambda *a: [])
    monkeypatch.setattr(polish, "polish_gold_chat_wording", lambda *a, **k: (deepcopy(proposed), 1))
    monkeypatch.setattr(polish, "_repair_gold_chat_after_polish", lambda chat: chat)
    monkeypatch.setattr(gc, "_ensure_gold_chat_min_chars", lambda chat, **kw: (chat, []))
    monkeypatch.setattr(import_story, "validate_gold_chat_story_for_row", lambda *a: None)
    def score(chat, row):
        chat["quality"] = {"structure_score": 80, "humor": {"funny_score": 12}}
        return chat
    def review(chat, row, **kw):
        if not accepted:
            raise gcf.GoldChatSemanticBlocked("润色未通过")
        stamp_story_review_binding(chat, semantic_pass=True, review_contract=gold_story_review_contract(row, chat))
        return chat
    monkeypatch.setattr(gc, "_attach_gold_chat_structure_score", score)
    monkeypatch.setattr(gcf, "run_gold_chat_final_acceptance", review)
    if accepted:
        result = polish.polish_gold_chat_export(row["source_id"])
        saved = gce.load_gold_chat_for_row(repo_gold_story.get_story(gid))
        assert saved["daily_story"]["dialogue"] == result["daily_story"]["dialogue"]
        assert saved["daily_story"]["dialogue"] != old["dialogue"]
    else:
        with pytest.raises(gcf.GoldChatSemanticBlocked):
            polish.polish_gold_chat_export(row["source_id"])
        assert gce.load_gold_chat_for_row(repo_gold_story.get_story(gid))["daily_story"] == old


def test_missing_committed_file_is_not_skipped_as_already_exported(app_ctx, monkeypatch, tmp_path):
    import importlib
    mgr = importlib.import_module("app.services.gold_story.gold_story_mgr")
    gid = int(_insert_sample(app_ctx)["id"])
    repo_gold_story.patch_story_payload(gid, {"gold_chat_exported_at": "2026-10-23",
        "gold_chat_json": str(tmp_path / ".versions" / "missing" / "story.json")})
    calls = []
    def convert(row, **kwargs):
        calls.append(row["id"])
        return {"ok": True, "chat_lines": 12}
    monkeypatch.setattr(mgr, "convert_gold_chat", convert)
    result = mgr.gold_story_mgr.convert_one(gold_story_id=gid)
    assert result["action"] == "ok"
    assert calls == [gid]


@pytest.mark.parametrize("state", ["running", "expired", "replaced", "failed"])
def test_publish_checks_batch_owner_and_expiry_without_polling(app_ctx, state):
    import time
    owner = int(_insert_sample(app_ctx)["id"])
    child = repo_gold_story.insert_pending(source="bili", source_id="BV1CHILD001", url="", title="子任务")["id"]
    now = time.time()
    task = {"task_id": "batch-owner", "status": "running", "started_at": now - 10,
            "expires_at": now - 1 if state == "expired" else now + 60}
    assert repo_gold_story.claim_chat_task(owner, task)
    if state == "failed":
        repo_gold_story.update_chat_task(owner, {**task, "status": "failed"})
    elif state == "replaced":
        repo_gold_story.patch_story_payload(owner, {"gold_chat_task": {**task, "task_id": "replacement"}})
    row = repo_gold_story.get_story(child, include_payload_snapshot=True)
    def publish():
        repo_gold_story.publish_chat_export(child, {"gold_chat_json": "new.json"}, expected_row=row,
                                           task_id="batch-owner", task_owner_id=owner)
    if state == "running":
        publish()
        assert repo_gold_story.get_story(child)["payload"]["gold_chat_json"] == "new.json"
    else:
        with pytest.raises(RuntimeError, match="任务已结束"):
            publish()
        assert not repo_gold_story.get_story(child)["payload"].get("gold_chat_json")


def test_batch_refreshes_each_row_deduplicates_and_reports_missing_targets(app_ctx, monkeypatch, tmp_path):
    from app.services.gold_story.gold_chat import batch
    first = int(_insert_sample(app_ctx)["id"])
    second = repo_gold_story.insert_pending(source="bili", source_id="BV1BATCH002", url="", title="第二条")["id"]
    calls = []
    def convert(row, **kwargs):
        calls.append(row["id"])
        if row["id"] == first:
            repo_gold_story.patch_story_payload(second, {"user_note": "latest source"})
        else:
            assert row["payload"]["user_note"] == "latest source"
        return {"chat_lines": 2}
    monkeypatch.setattr(batch, "convert_gold_chat", convert)
    monkeypatch.setattr(batch, "_write_batch_report", lambda *a: tmp_path / "report.json")
    result = batch.run_gold_chat_batch(gold_story_ids=[first, first, 999999, second], skip_existing=False)
    assert calls == [first, second]
    assert result["ok"] == 2 and result["failed"] == 1
    assert any(item.get("gold_story_id") == 999999 and item["action"] == "error" for item in result["results"])


def test_async_batch_propagates_publication_owner(app_ctx, monkeypatch, tmp_path):
    import importlib
    from app.services.gold_story.gold_chat import batch
    mgr = importlib.import_module("app.services.gold_story.gold_story_mgr")
    first = int(_insert_sample(app_ctx)["id"])
    second = repo_gold_story.insert_pending(source="bili", source_id="BV1BATCH002", url="", title="第二条")["id"]
    callbacks = []
    captured = []
    monkeypatch.setattr(mgr, "run_in_background", callbacks.append)
    monkeypatch.setattr(batch, "_write_batch_report", lambda *a: tmp_path / "report.json")
    def convert(row, **kwargs):
        captured.append((row["id"], row.get("_gold_chat_task_id"), row.get("_gold_chat_task_owner_id")))
        return {"chat_lines": 2}
    monkeypatch.setattr(batch, "convert_gold_chat", convert)
    task = mgr.gold_story_mgr.submit_batch_conversion(gold_story_ids=[first, second], force=True)
    callbacks[0]()
    assert captured == [(first, task["task_id"], first), (second, task["task_id"], first)]
    assert mgr.gold_story_mgr.conversion_task(first, task["task_id"])["result"]["ok"] == 2


@pytest.mark.parametrize("target", [{"ids": [999999]}, {"source_ids": ["BV1MISSING01"]}])
def test_async_batch_missing_targets_are_not_server_errors(app_ctx, monkeypatch, target):
    import importlib
    mgr = importlib.import_module("app.services.gold_story.gold_story_mgr")
    monkeypatch.setattr(mgr, "run_in_background", lambda *a: pytest.fail("missing batch must not start"))
    assert app_ctx.test_client().post("/v_factory/api/gold_chat/batch", json={**target, "async": True}).status_code == 404


def test_expired_batch_does_not_start_later_items_or_overwrite_failure_metadata(app_ctx, monkeypatch, tmp_path):
    import time
    from app.services.gold_story.gold_chat import batch
    first = int(_insert_sample(app_ctx)["id"])
    second = repo_gold_story.insert_pending(source="bili", source_id="BV1BATCH002", url="", title="第二条")["id"]
    now = time.time()
    task = {"task_id": "owner", "status": "running", "started_at": now, "expires_at": now + 60}
    repo_gold_story.claim_chat_task(first, task)
    monkeypatch.setattr(batch, "_write_batch_report", lambda *a: tmp_path / "report.json")
    calls = []
    def convert(row, **kwargs):
        calls.append(row["id"])
        repo_gold_story.patch_story_payload(first, {"gold_chat_task": {**task, "expires_at": now - 1}, "gold_chat_last_error": "keep newer state"})
        raise RuntimeError("old executor stopped")
    monkeypatch.setattr(batch, "convert_gold_chat", convert)
    result = batch.run_gold_chat_batch(gold_story_ids=[first, second], skip_existing=False, task_id="owner", task_owner_id=first)
    assert calls == [first] and result["failed"] == 2
    assert repo_gold_story.get_story(first)["payload"]["gold_chat_last_error"] == "keep newer state"


def test_collection_failure_reason_is_visible_and_disappears_after_success(app_ctx):
    gid = int(_insert_sample(app_ctx)["id"])
    repo_gold_story.patch_story_payload(gid, {"collect_attempts": 3,
        "collect_failure": {"stage": "H0b", "error": "视频下载超时", "retryable": True}})
    repo_gold_story.set_story_status(gid, status="failed")
    client = app_ctx.test_client()
    detail = client.get(f"/v_factory/api/gold_chat/get?id={gid}").get_json()
    rows = client.get("/v_factory/api/gold_chat/list").get_json()["items"]
    expected = {"error": "视频下载超时", "stage": "H0b", "attempts": 3}
    assert detail["collect_error"] == expected
    assert next(row for row in rows if row["id"] == gid)["collect_error"] == expected
    repo_gold_story.set_story_status(gid, status="active")
    assert "collect_error" not in client.get(f"/v_factory/api/gold_chat/get?id={gid}").get_json()



def test_restore_rejects_incomplete_automatic_rejection(app_ctx):
    gid = repo_gold_story.insert_pending(source="bili", source_id="BV1RESTORE01", url="", outcome={
        "action": "reject", "stage": "H0c", "reason": "source_unusable",
    })["id"]
    response = app_ctx.test_client().post("/v_factory/api/gold_chat/restore", json={"ids": [gid], "from_status": "rejected"})
    assert response.status_code == 200
    body = response.get_json()
    assert body["restored"] == 0
    assert "重新导入" in body["results"][0]["error"]
    assert repo_gold_story.get_story(gid)["status"] == "rejected"


def test_restore_manual_rejection_restores_original_audit(app_ctx):
    gid = _insert_sample(app_ctx)["id"]
    audit = {"pass": True, "stage": "llm", "reject_reasons": []}
    repo_gold_story.update_story_status(gid, status="active", audit=audit)
    client = app_ctx.test_client()
    assert client.post("/v_factory/api/gold_chat/reject", json={"ids": [gid]}).status_code == 200
    body = client.post("/v_factory/api/gold_chat/restore", json={"ids": [gid], "from_status": "rejected"}).get_json()
    assert body["restored"] == 1
    row = repo_gold_story.get_story(gid)
    assert row["status"] == "active" and row["payload"]["audit"] == audit


def test_unarchive_rejected_source_does_not_make_it_active(app_ctx):
    gid = repo_gold_story.insert_pending(source="bili", source_id="BV1RESTORE02", url="", outcome={
        "action": "reject", "stage": "H0c", "reason": "source_unusable",
    })["id"]
    audit = repo_gold_story.get_story(gid)["payload"]["audit"]
    client = app_ctx.test_client()
    assert client.post("/v_factory/api/gold_chat/archive", json={"ids": [gid]}).status_code == 200
    body = client.post("/v_factory/api/gold_chat/restore", json={"ids": [gid], "from_status": "archived"}).get_json()
    assert body["restored"] == 1
    row = repo_gold_story.get_story(gid)
    assert row["status"] == "rejected" and row["payload"]["audit"] == audit
