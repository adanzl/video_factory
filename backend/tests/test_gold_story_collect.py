"""金故事 H0/H1 采集测试。"""

from __future__ import annotations

import pytest

from app.services.gold_story.collect import (
    engagement_norm,
    passes_h1_filter,
)


def test_engagement_norm():
    assert engagement_norm(500_000, 500) == 1.0
    assert engagement_norm(0, 0) == 0.0


def test_h0c_retry_keeps_resolution_and_returns_validation_feedback(monkeypatch):
    from app.config import Config
    from app.services.gold_story.collect import pipeline as p
    from app.services.gold_story.collect.search import VideoCandidate
    candidate = VideoCandidate(source="bili", source_id="BV1RETRY0001", url="", title="test",
                               description="", view_count=1, reply_count=1, keyword="")
    monkeypatch.setattr(p, "_build_candidate_from_bvid", lambda *_a, **_kw: candidate)
    monkeypatch.setattr(p.time, "sleep", lambda *_a: None)
    resolution = {"status": "resolved", "source": "ocr", "evidence_hash": "same-evidence"}
    seen = []
    def process(*_a, **kwargs):
        seen.append(kwargs)
        if len(seen) == 1:
            return {"action": "error", "stage": "H0c", "retryable": True,
                    "error": "scene jumps across dialogue", "transcript_resolution": resolution}
        return {"action": "ok", "status": "active"}
    monkeypatch.setattr(p, "process_candidate", process)
    result, _ = p._run_reimport_attempts(candidate.source_id, config=Config(), force_transcript=True)
    assert result["attempts"] == 2
    assert seen[1]["force_transcript"] is False
    assert seen[1]["resolution_cache"] == resolution
    assert seen[1]["repair_feedback"] == "scene jumps across dialogue"


@pytest.mark.parametrize("failure", ["cross_check", "cross_resolved", "repair", "repair_audit", "clip_audit", "recovered", "cross_missing", "cross_unavailable"])
@pytest.mark.parametrize("independent", ["none", "replies", "description"])
@pytest.mark.parametrize("cached", [False, True])
def test_reimport_never_uses_bad_transcript_or_stale_repair_metadata(
    tmp_path, monkeypatch, failure, independent, cached,
):
    import json
    from app.config import Config
    from app.services.gold_story.collect import pipeline as p
    from app.services.gold_story.collect.search import VideoCandidate

    cfg = Config()
    cfg.gold_story_transcript_dir = tmp_path / "transcripts"
    cfg.gold_story_transcript_dir.mkdir()
    cfg.gold_story_media_workspace = tmp_path / "media"
    cfg.gold_story_transcript_repair = True
    sid = "BV1pA4m1378V"
    transcript_path = cfg.gold_story_transcript_dir / f"{sid}.txt"
    transcript_path.write_text("时间地区点赞数与听不清碎片", encoding="utf-8")
    cross = {"available": True, "passed": failure not in {"cross_check", "cross_resolved"}, "agreement": 0.043 if failure in {"cross_check", "cross_resolved"} else 0.9}
    if failure == "cross_missing":
        cross = None
    elif failure == "cross_unavailable":
        cross = {"available": False}
    is_failure = failure in {"cross_check", "repair", "repair_audit"}
    metadata_dir = cfg.gold_story_media_workspace / "metadata"
    metadata_dir.mkdir(parents=True)
    (metadata_dir / f"{sid}.json").write_text(json.dumps({"transcript_path": str(transcript_path), "cross_check": cross}))
    existing = {"id": 10, "source_id": sid, "payload": {"transcript_repair_confidence": 0.8,
                "transcript_repair_notes": "上一次的修复说明", "transcript_repaired_path": "old.repaired.txt",
                "transcript_cross_check": {"available": True, "passed": True}}}
    if not is_failure:
        existing["payload"].update({"transcript_status": "unusable", "transcript_failure_reason": "上一轮失败"})
    candidate = VideoCandidate(
        source="bili", source_id=sid, url=f"https://www.bilibili.com/video/{sid}",
        title="姐弟日常", description="简介中有完整的独立故事" if independent == "description" else "",
        view_count=200000, reply_count=100, keyword="姐弟",
        top_replies=("热评中有完整的独立故事",) if independent == "replies" else (),
    )
    monkeypatch.setattr(p, "transcribe_bilibili", lambda *_a, **_kw: {
        "action": "ok", "transcript_path": str(transcript_path), "cross_check": cross, "transcript_backend": "ocr",
    })
    def audit(**_kw):
        if failure == "repair_audit":
            raise p.llm_steps.ModelOutputError("transcript repair unfaithful: invented speaker")
        return {"faithful": True, "reason": "原文可核实"}
    monkeypatch.setattr(p.llm_steps, "review_transcript_repair", audit)
    if failure == "cross_resolved":
        monkeypatch.setattr(p.llm_steps, "reconcile_transcripts", lambda *_a, **_kw: {
            "status": "resolved", "source": "ocr", "text": "独立审核确认的OCR原文"})
        def audit_repair(**kwargs):
            assert kwargs["transcript"] == "独立审核确认的OCR原文"
            assert kwargs["repaired"] == "昭昭：本轮有效修复稿"
            return {"faithful": True, "reason": "原文可核实"}
        monkeypatch.setattr(p.llm_steps, "review_transcript_repair", audit_repair)
    def repair(**_kw):
        assert failure != "cross_check", "明确不可靠的转写不应再消耗修复调用"
        if failure == "cross_resolved":
            assert _kw["transcript"] == "独立审核确认的OCR原文"
        if failure == "repair":
            raise p.llm_steps.SourceRejected("H0c low repair_confidence=0.20")
        return {"lines": [{"speaker": "昭昭", "text": "本轮有效修复稿"}],
                "repair_confidence": 0.9, "repair_notes": "本轮修复成功"}
    monkeypatch.setattr(p.llm_steps, "repair_transcript", repair)
    extracted = []
    def extract(**kwargs):
        extracted.append(kwargs)
        assert kwargs["transcript"] == ("" if is_failure else "昭昭：本轮有效修复稿")
        return {"story_raw": "来自独立来源的完整故事" * 12, "source_type": "mixed"}
    monkeypatch.setattr(p.llm_steps, "extract_story_raw", extract)
    monkeypatch.setattr(p.llm_steps, "review_story_source", lambda **_kw: {"faithful": True})
    monkeypatch.setattr(p.repo_gold_story, "find_near_duplicate", lambda *_a, **_kw: None)
    monkeypatch.setattr(p.llm_steps, "structurize_story", lambda **_kw: {"mechanism": "M6", "structure_type": "N"})
    monkeypatch.setattr(p.llm_steps, "build_scene_contract", lambda **_kw: {})
    monkeypatch.setattr(p, "sync_h3_from_scene_contract", lambda h3, *_a, **_kw: (h3, []))
    monkeypatch.setattr(p.llm_steps, "build_dialogue_seed", lambda **_kw: {})
    monkeypatch.setattr(p.gs_review, "audit_story", lambda **_kw: {"pass": failure != "clip_audit"})
    monkeypatch.setattr(p, "passes_funny_gate_from_payload", lambda *_a, **_kw: (True, "ok"))
    saved = []
    def update(_gid, **kwargs):
        saved.append(kwargs)
        return {"auto_score": 0.8}
    monkeypatch.setattr(p.repo_gold_story, "update_story_from_pipeline", update)
    monkeypatch.setattr(p.repo_gold_story, "get_story", lambda _gid: existing)
    monkeypatch.setattr(p, "export_story_files", lambda **_kw: {})

    result = p.process_candidate(candidate, config=cfg, overwrite_existing=True,
                                 force_transcript=not cached, existing_row=existing,
                                 clip_transcript=({"transcript_path": str(transcript_path), "cross_check": cross,
                                                   "source_clip": {"start_sec": 10, "end_sec": 40}}
                                                  if failure == "clip_audit" else None))
    if failure == "clip_audit":
        assert result["action"] == "reject" and result["stage"] == "H4a"
        assert result["source_clip"] == {"start_sec": 10, "end_sec": 40}
        assert len(extracted) == 1 and saved == []
    elif is_failure:
        assert result["action"] == ("error" if failure in {"cross_check", "repair_audit"} else "reject")
        if failure == "repair_audit":
            assert "unfaithful" in result["error"]
            assert result["retryable"] is True
        else:
            assert result["reason"] == ("transcript_conflict" if failure == "cross_check" else "source_unusable")
        if failure == "cross_check":
            assert result["retryable"] is False
        assert result["stage"] == ("H0b" if failure == "cross_check" else "H0c")
        assert extracted == saved == []
        assert existing["payload"]["transcript_repair_confidence"] == 0.8
    else:
        assert result["action"] == "ok"
        assert len(extracted) == len(saved) == 1
        payload = saved[0]["payload"]
        assert payload["transcript_cross_check"] == cross
        if failure == "cross_resolved":
            assert payload["transcript_resolution"]["source"] == "ocr"
            assert payload["transcript_resolution_repair_audit"]["faithful"] is True
        assert payload["transcript_repair_audit"]["faithful"] is True
        assert payload["transcript_status"] == "usable"
        assert payload["source_inputs"] == ["transcript"] + ([] if independent == "none" else [independent])
        assert payload["transcript_repair_confidence"] == 0.9
        assert payload["transcript_repair_notes"] == "本轮修复成功"
        assert payload["transcript_failure_reason"] is None


def test_h1_passes_with_high_view():
    ok, reason = passes_h1_filter(
        title="姐弟吵架名场面",
        view_count=200_000,
        reply_count=10,
    )
    assert ok is True
    assert reason == "ok"


def test_h1_rejects_exclude_title():
    ok, reason = passes_h1_filter(
        title="萌娃英语启蒙教程",
        view_count=500_000,
        reply_count=100,
    )
    assert ok is False
    assert reason == "exclude_title"


def test_h1_rejects_low_engagement():
    ok, reason = passes_h1_filter(
        title="姐弟日常",
        view_count=1000,
        reply_count=2,
    )
    assert ok is False
    assert reason == "low_engagement"


def test_collect_candidates_skips_already_in_db(app_ctx, monkeypatch):
    from app.repositories import repo_gold_story
    from app.services.gold_story.collect import search as search_mod
    from app.services.gold_story.collect.funny import (
        AudienceFunnyMetrics,
        metrics_to_payload,
    )

    repo_gold_story.insert_or_skip(
        source="bili",
        source_id="BV1ALREADY01",
        url="https://www.bilibili.com/video/BV1ALREADY01",
        mechanism="M11",
        structure_type="I",
        story_raw="已入库故事" * 20,
        payload={"beat": ["a", "b", "c", "d"]},
        title="已入库",
        auto_score=0.8,
        status="active",
    )

    monkeypatch.setattr(
        search_mod,
        "search_keywords",
        lambda _cfg: ["姐弟吵架"],
    )
    monkeypatch.setattr(
        search_mod,
        "search_bilibili",
        lambda *_a, **_k: ["BV1ALREADY01", "BV1FRESH0001"],
    )

    def fake_meta(bvid, **_kwargs):
        return {
            "title": "姐弟吵架名场面",
            "description": "",
            "view_count": 200_000,
            "reply_count": 80,
            "url": f"https://www.bilibili.com/video/{bvid}",
            "aid": 1,
            "cid": 1,
        }

    monkeypatch.setattr(search_mod, "fetch_video_meta", fake_meta)
    monkeypatch.setattr(search_mod, "fetch_top_replies", lambda *_a, **_k: ["哈哈"])
    funny = AudienceFunnyMetrics(
        danmaku_total=100,
        danmaku_laugh_score=100.0,
        danmaku_laugh_ratio=0.5,
        comment_laugh_ratio=0.4,
        view_reply_ratio_norm=0.5,
        funny_signal=0.8,
        cute_not_funny=False,
        danmaku_fetch_ok=True,
    )
    monkeypatch.setattr(
        search_mod,
        "compute_audience_funny_metrics",
        lambda **_k: funny,
    )
    monkeypatch.setattr(
        search_mod,
        "passes_funny_gate",
        lambda *_a, **_k: (True, "ok"),
    )
    monkeypatch.setattr(
        search_mod,
        "metrics_to_payload",
        metrics_to_payload,
    )

    rows = search_mod.collect_candidates(max_candidates=5)
    assert [r.source_id for r in rows] == ["BV1FRESH0001"]


def test_enqueue_pending_before_ocr(app_ctx, monkeypatch):
    """采集应先 pending 入库，不在入队阶段跑 OCR。"""
    from app.repositories import repo_gold_story
    from app.services.gold_story.collect import pipeline as pl
    from app.services.gold_story.collect.search import VideoCandidate

    calls: list[str] = []

    def boom(*_a, **_k):
        calls.append("ocr")
        raise AssertionError("enqueue must not OCR")

    monkeypatch.setattr(pl, "transcribe_bilibili", boom)
    monkeypatch.setattr(
        pl,
        "collect_candidates",
        lambda **_k: [
            VideoCandidate(
                source="bili",
                source_id="BV1PEND00001",
                url="https://www.bilibili.com/video/BV1PEND00001",
                title="排队测试",
                description="",
                view_count=100_000,
                reply_count=50,
                keyword="姐弟吵架",
                top_replies=(),
                cid=1,
                funny_metrics={"funny_signal": 0.8},
            )
        ],
    )

    report = pl.enqueue_collect_candidates(max_candidates=1, write_list=False)
    assert report["enqueued"] == 1
    assert calls == []
    row = repo_gold_story.get_by_source_id(source_id="BV1PEND00001")
    assert row is not None
    assert row["status"] == "pending"
    claimed = repo_gold_story.claim_next_pending()
    assert claimed is not None
    assert claimed["status"] == "processing"
    assert repo_gold_story.claim_next_pending() is None


def test_near_duplicate_catches_reprint_wording():
    from app.repositories.repo_gold_story import is_near_duplicate_story

    original = (
        "东北一辆车里，姐姐突然灵魂拷问：“我爱学习，你爱吗？”"
        "弟弟语塞。姐姐说：“都是一个爸爸妈妈生的，凭什么我爱学习你不爱？”"
        "弟弟嘟囔：“你听不懂我说话，我也听不懂你说话，这就完了呗。”"
        "姐姐回击：“我是听不懂你说话，大舌叽叽的。”弟弟彻底败下阵来。"
    )
    reprint = (
        "行驶的车里弟弟嘴硬说和姐姐相同。姐姐反问：“我就是爱学习，你爱吗？”"
        "又说都是一个爸爸妈妈生出来的。弟弟只能嘟囔："
        "“你听不懂我说话，我也听不懂你说话，这就完了得了呗。”"
        "姐姐不依不饶：“我是听不懂你说话，大舌唧叽的。”弟弟彻底败下阵来。"
    )
    other = (
        "客厅里两人为抢遥控器吵起来，妈妈让谁先放手谁先选。"
        "弟弟先放手却被姐姐反悔，最后妈妈把遥控器收回去了。"
    )
    assert is_near_duplicate_story(original, reprint) is True
    assert is_near_duplicate_story(original, other) is False


def test_insert_skips_similar_reprint(app_ctx):
    from app.repositories import repo_gold_story

    original = (
        "东北一辆车里，姐姐突然灵魂拷问：“我爱学习，你爱吗？”"
        "弟弟语塞。姐姐说：“都是一个爸爸妈妈生的，凭什么我爱学习你不爱？”"
        "弟弟嘟囔：“你听不懂我说话，我也听不懂你说话，这就完了呗。”"
        "姐姐回击：“我是听不懂你说话，大舌叽叽的。”弟弟彻底败下阵来。"
    )
    reprint = (
        "行驶的车里弟弟嘴硬说和姐姐相同。姐姐反问：“我就是爱学习，你爱吗？”"
        "又说都是一个爸爸妈妈生出来的。弟弟只能嘟囔："
        "“你听不懂我说话，我也听不懂你说话，这就完了得了呗。”"
        "姐姐不依不饶：“我是听不懂你说话，大舌唧叽的。”弟弟彻底败下阵来。"
    )
    first = repo_gold_story.insert_or_skip(
        source="bili",
        source_id="BV1ORIGTEST01",
        url="https://www.bilibili.com/video/BV1ORIGTEST01",
        mechanism="M11",
        structure_type="I",
        story_raw=original,
        payload={"story_raw": original, "beat": ["a", "b", "c", "d"]},
        title="原片灵魂拷问",
        auto_score=0.8,
        status="active",
    )
    assert first.get("action") == "insert"
    second = repo_gold_story.insert_or_skip(
        source="bili",
        source_id="BV1REPRINT001",
        url="https://www.bilibili.com/video/BV1REPRINT001",
        mechanism="M11",
        structure_type="I",
        story_raw=reprint,
        payload={"story_raw": reprint, "beat": ["a", "b", "c", "d"]},
        title="转载灵魂拷问",
        auto_score=0.8,
        status="active",
    )
    assert second.get("action") == "skip"
    assert second.get("reason") == "duplicate_similar_story"
    assert int(second.get("id")) == int(first["id"])  # type: ignore[arg-type]


def test_reimport_stories_from_id_and_bv(app_ctx, monkeypatch):
    from app.repositories import repo_gold_story
    from app.services.gold_story.collect import pipeline as pl

    inserted = repo_gold_story.insert_or_skip(
        source="bili",
        source_id="BV1REIMPORT01",
        url="https://www.bilibili.com/video/BV1REIMPORT01",
        mechanism="M6",
        structure_type="A",
        story_raw="旧稿" * 20,
        payload={"beat": ["a", "b", "c", "d"]},
        title="旧标题",
        auto_score=0.8,
        status="active",
    )
    gid = int(inserted["id"])
    calls: list[tuple[str, object]] = []

    def fake_overwrite(gold_story_id, **_kwargs):
        calls.append(("overwrite", int(gold_story_id)))
        return {"id": int(gold_story_id), "source_id": "BV1REIMPORT01", "action": "ok"}

    def fake_import(source_id, **_kwargs):
        calls.append(("import", source_id))
        return {"source_id": source_id, "action": "insert", "id": 99}

    monkeypatch.setattr(pl, "overwrite_existing_story", fake_overwrite)
    monkeypatch.setattr(pl, "import_or_overwrite_source", fake_import)

    report = pl.reimport_stories(
        gold_story_ids=[gid],
        source_ids=["https://www.bilibili.com/video/BV1NEWID0001"],
        force_transcript=True,
    )
    assert report["requested"] == 2
    assert report["updated"] == 1
    assert report["inserted"] == 1
    assert report["failed"] == 0
    assert calls == [("overwrite", gid), ("import", "BV1NEWID0001")]


def test_reimport_stories_on_progress(app_ctx, monkeypatch):
    from app.repositories import repo_gold_story
    from app.services.gold_story.collect import pipeline as pl

    rows = []
    for i in range(3):
        inserted = repo_gold_story.insert_or_skip(
            source="bili",
            source_id=f"BV1PROGTEST{i}",
            url=f"https://www.bilibili.com/video/BV1PROGTEST{i}",
            mechanism="M6",
            structure_type="A",
            story_raw=f"稿{i}" * 20,
            payload={"beat": ["a", "b", "c", "d"]},
            title=f"进度{i}",
            auto_score=0.8,
            status="active",
        )
        rows.append(int(inserted["id"]))

    def fake_overwrite(gold_story_id, **_kwargs):
        row = repo_gold_story.get_story(int(gold_story_id))
        return {
            "id": int(gold_story_id),
            "source_id": str(row.get("source_id") or ""),
            "action": "ok",
        }

    monkeypatch.setattr(pl, "overwrite_existing_story", fake_overwrite)
    progress: list[dict] = []

    pl.reimport_stories(
        gold_story_ids=rows,
        force_transcript=True,
        on_progress=lambda p: progress.append(dict(p)),
    )
    assert progress
    first = progress[0]
    assert first["processed"] == 0
    assert first["processing_id"] == rows[0]
    assert first["queued_ids"] == rows[1:]
    assert len(progress) == len(rows)
    assert progress[-1]["processing_id"] == rows[-1]


def _pending_source(source_id="BV1RETRY0001"):
    from app.repositories import repo_gold_story
    return repo_gold_story.insert_pending(source="bili", source_id=source_id,
                                         url=f"https://www.bilibili.com/video/{source_id}", title="姐弟日常")["id"]


@pytest.mark.parametrize("recover", [False, True])
@pytest.mark.parametrize("succeeds", [False, True])
def test_collect_retries_transient_errors_with_durable_budget(app_ctx, monkeypatch, recover, succeeds):
    import requests
    from app.repositories import repo_gold_story as repo
    from app.services.gold_story.collect import pipeline as p
    gid = _pending_source()
    if recover:
        repo.claim_next_pending()
        repo.begin_collect_attempt(gid, max_attempts=3)
        repo.reset_processing_to_pending()
    attempts = []
    sleeps = []
    def candidate(*_args, **_kwargs):
        attempts.append(repo.get_story(gid)["payload"]["collect_attempts"])
        if succeeds and attempts[-1] == 3:
            return object()
        raise requests.Timeout("upstream timeout")
    def process(*_args, **_kwargs):
        repo.update_story_status(gid, status="active")
        return {"id": gid, "action": "ok", "status": "active"}
    monkeypatch.setattr(p, "_build_candidate_from_bvid", candidate)
    monkeypatch.setattr(p, "process_candidate", process)
    monkeypatch.setattr(p.time, "sleep", sleeps.append)
    report = p.drain_pending_stories()
    assert attempts == ([2, 3] if recover else [1, 2, 3])
    row = repo.get_story(gid)
    assert row["payload"]["collect_attempts"] == 3
    assert row["status"] == ("active" if succeeds else "failed")
    assert "audit" not in row["payload"]
    assert report["failed"] == (0 if succeeds else 1)
    assert report["processed"] == 1
    assert len(sleeps) == len(attempts) - 1
    assert p.drain_pending_stories()["processed"] == 0


@pytest.mark.parametrize("code,retryable", [(429, True), (503, True), (403, False), (404, False)])
def test_collect_http_errors_are_not_content_rejections(code, retryable):
    import requests
    from app.services.gold_story.collect.pipeline import _execution_failure
    response = requests.Response(); response.status_code = code
    original = requests.HTTPError("HTTP error", response=response)
    wrapped = ValueError("request failed"); wrapped.__cause__ = original
    assert _execution_failure(wrapped, "H0c") == {
        "action": "error", "stage": "H0c", "error": "request failed", "retryable": retryable,
    }


@pytest.mark.parametrize("kind", ["reject", "error"])
def test_collect_content_rejection_and_permanent_execution_failure_stay_distinct(app_ctx, monkeypatch, kind):
    from app.repositories import repo_gold_story as repo
    from app.services.gold_story.collect import pipeline as p
    gid = _pending_source()
    monkeypatch.setattr(p, "_build_candidate_from_bvid", lambda *a, **k: object())
    monkeypatch.setattr(p, "process_candidate", lambda *a, **k: {
        "action": kind, "stage": "H0b", "reason": "source_unusable" if kind == "reject" else None,
        "error": "permanent", "retryable": False,
    })
    monkeypatch.setattr(p.time, "sleep", lambda *_a: pytest.fail("must not retry"))
    p.drain_pending_stories()
    row = repo.get_story(gid)
    assert row["status"] == ("rejected" if kind == "reject" else "failed")
    assert row["payload"]["collect_attempts"] == 1
    assert ("audit" in row["payload"]) == (kind == "reject")


def test_collect_recovery_does_not_run_exhausted_attempt(app_ctx, monkeypatch):
    from app.repositories import repo_gold_story as repo
    from app.services.gold_story.collect import pipeline as p
    gid = _pending_source(); repo.claim_next_pending()
    for _ in range(3): repo.begin_collect_attempt(gid, max_attempts=3)
    repo.reset_processing_to_pending()
    monkeypatch.setattr(p, "_build_candidate_from_bvid", lambda *a, **k: pytest.fail("budget exhausted"))
    assert p.drain_pending_stories()["failed"] == 1
    assert repo.get_story(gid)["status"] == "failed"


def test_collect_preview_does_not_write_database_files_or_cursor(app_ctx, tmp_path, monkeypatch):
    from app.config import Config
    from app.repositories import sql_exec as sql
    from app.services.gold_story.collect import pipeline as p, search
    cfg = Config(); cfg.gold_story_candidates_file = tmp_path / "candidates.txt"
    gid = _pending_source()
    before = sql.fetchall("SELECT * FROM gold_story"); sql.commit()
    monkeypatch.setattr(search, "search_bilibili", lambda *a, **k: [])
    monkeypatch.setattr(p, "write_candidate_list", lambda *a: pytest.fail("preview wrote file"))
    monkeypatch.setattr(p, "transcribe_bilibili", lambda *a, **k: pytest.fail("preview transcribed"))
    assert p.run_collect_pipeline(config=cfg, dry_run=True)["enqueued"] == 0
    report = p.drain_pending_stories(config=cfg, dry_run=True)
    assert report["results"] == [{"id": gid, "source_id": "BV1RETRY0001", "action": "dry_run"}]
    assert report["processed"] == 0
    assert sql.fetchall("SELECT * FROM gold_story") == before
    assert sql.fetchall("SELECT * FROM gold_story_search_cursor") == []
    sql.commit()
    assert not cfg.gold_story_candidates_file.exists()


def test_search_paginates_rotates_persistently_and_preview_does_not_advance(app_ctx, monkeypatch):
    from app.config import Config
    from app.repositories import sql_exec as sql
    from app.services.gold_story.collect import search
    cfg = Config(); cfg.gold_story_search_max_page = 4
    calls = []
    def query(keyword, **kwargs):
        calls.append((keyword, kwargs["page"]))
        return []
    monkeypatch.setattr(search, "search_bilibili", query)
    def run(preview=False):
        calls.clear()
        search.collect_candidates(config=cfg, keywords=["甲", "乙"], advance_cursor=not preview)
        return list(calls)
    assert run() == [("甲", 1), ("乙", 1), ("甲", 2), ("乙", 2), ("甲", 3), ("乙", 3)]
    # 新调用没有进程内游标也从库中继续；预览不消耗下一位置。
    assert run(True)[0] == ("乙", 1)
    assert run()[0] == ("乙", 1)
    assert run() == [("甲", 2), ("乙", 2), ("甲", 3), ("乙", 3), ("甲", 4), ("乙", 4)]
    state = sql.fetchall("SELECT * FROM gold_story_search_cursor"); sql.commit()
    def broken(*a, **k): raise TimeoutError("search offline")
    monkeypatch.setattr(search, "search_bilibili", broken)
    with pytest.raises(RuntimeError, match="搜索均失败"):
        run()
    assert sql.fetchall("SELECT * FROM gold_story_search_cursor") == state
    sql.commit()


def test_search_finds_later_page_and_deduplicates_across_pages(app_ctx, monkeypatch):
    from app.services.gold_story.collect import search
    from app.repositories import repo_gold_story as repo
    _pending_source("BV1OLD000001")
    monkeypatch.setattr(search, "search_bilibili", lambda *a, **k: ["BV1OLD000001"] if k["page"] == 1 else ["BV1NEW000001", "BV1OLD000001"])
    inspected = []
    def meta(bv, **k):
        inspected.append(bv)
        return {"title": "姐弟日常", "description": "", "view_count": 200000, "reply_count": 100,
                "aid": 1, "cid": 1, "url": "https://www.bilibili.com/video/" + bv}
    monkeypatch.setattr(search, "fetch_video_meta", meta)
    monkeypatch.setattr(search, "fetch_top_replies", lambda *a, **k: [])
    monkeypatch.setattr(search, "compute_audience_funny_metrics", lambda **k: None)
    monkeypatch.setattr(search, "metrics_to_payload", lambda x: {})
    found = search.collect_candidates(keywords=["姐弟", "萌娃"], max_candidates=2)
    assert [item.source_id for item in found] == ["BV1NEW000001"]
    assert inspected == ["BV1NEW000001"]
    assert repo.count_stories() == 1


def test_metadata_outage_never_becomes_zero_score_candidate(app_ctx, monkeypatch):
    import requests
    from app.config import Config
    from app.repositories import repo_gold_story
    from app.services.gold_story.collect import pipeline as p
    gid = _pending_source()
    def offline(*a, **k): raise requests.Timeout("B站超时")
    monkeypatch.setattr(p, "fetch_video_meta", offline)
    with pytest.raises(requests.Timeout):
        p._build_candidate_from_bvid("BV1RETRY0001", config=Config(), existing_row=repo_gold_story.get_story(gid))


def test_danmaku_outage_propagates_in_strict_collection(monkeypatch):
    import requests
    from app.services.gold_story.collect import funny
    def offline(**k): raise requests.Timeout("弹幕超时")
    monkeypatch.setattr(funny, "fetch_danmaku_texts", offline)
    with pytest.raises(requests.Timeout):
        funny.compute_audience_funny_metrics(source_id="BV1RETRY0001", cid=1,
            view_count=100000, reply_count=100, replies=[], session=requests.Session(), strict=True)


def test_reimport_busy_does_not_fetch_or_change_source(app_ctx, monkeypatch):
    import time
    from app.repositories import repo_gold_story as repo
    from app.services.gold_story.collect import pipeline as p
    gid = _pending_source()
    repo.claim_chat_task(gid, {"task_id": "test", "status": "running", "started_at": time.time(), "expires_at": time.time()+60})
    before = repo.get_story(gid)
    monkeypatch.setattr(p, "_build_candidate_from_bvid", lambda *a, **k: pytest.fail("busy story must not fetch"))
    result = p.overwrite_existing_story(gid)
    assert result["action"] == "error" and "转换进行中" in result["error"]
    assert repo.get_story(gid) == before


def _failed_collect_source(source_id="BV1FAIL00001"):
    from app.repositories import repo_gold_story as repo
    gid = _pending_source(source_id)
    claimed = repo.claim_next_pending()
    assert claimed is not None and claimed["id"] == gid
    assert repo.record_collect_failure(
        gid,
        {"action": "error", "stage": "H0c", "error": "410 Client Error: Gone", "retryable": False},
        retry=False,
        expected_row=claimed,
    )
    return gid


def test_reimport_content_rejection_replaces_collect_failure(app_ctx, monkeypatch):
    from app.repositories import repo_gold_story as repo
    from app.services.gold_story.collect import pipeline as p
    gid = _failed_collect_source()
    monkeypatch.setattr(p, "_build_candidate_from_bvid", lambda *a, **k: object())
    monkeypatch.setattr(p, "process_candidate", lambda *a, **k: {
        "action": "reject", "stage": "H0c", "reason": "source_unusable",
        "error": "H0c source_unusable: no complete source scene",
    })
    result = p.overwrite_existing_story(gid)
    row = repo.get_story(gid)
    assert result["status"] == "rejected" and result["persisted"] is True
    assert row["status"] == "rejected"
    assert "collect_failure" not in row["payload"]
    assert row["payload"]["audit"]["stage"] == "H0c"
    assert row["payload"]["audit"]["reject_reasons"] == [
        "H0c source_unusable: no complete source scene",
    ]


def test_reimport_execution_error_replaces_stale_collect_failure(app_ctx, monkeypatch):
    from app.repositories import repo_gold_story as repo
    from app.services.gold_story.collect import pipeline as p
    gid = _failed_collect_source("BV1FAIL00002")
    monkeypatch.setattr(p, "_build_candidate_from_bvid", lambda *a, **k: object())
    monkeypatch.setattr(p, "process_candidate", lambda *a, **k: {
        "action": "error", "stage": "H0c", "error": "upstream timeout", "retryable": True,
    })
    result = p.overwrite_existing_story(gid)
    row = repo.get_story(gid)
    assert result["status"] == "failed" and result["persisted"] is True
    assert row["status"] == "failed"
    assert row["payload"]["collect_failure"]["error"] == "upstream timeout"


def test_reimport_gate_does_not_overwrite_concurrent_edit(app_ctx, monkeypatch):
    from app.repositories import repo_gold_story as repo
    from app.repositories import sql_exec as sql
    from app.services.gold_story.collect import pipeline as p
    gid = _failed_collect_source("BV1FAIL00003")

    def edit_during_reimport(*_args, **_kwargs):
        sql.execute("UPDATE gold_story SET title=? WHERE id=?", ("改过的标题", gid))
        sql.commit()
        return {"action": "reject", "stage": "H0c", "error": "H0c source_unusable: no complete source scene"}

    monkeypatch.setattr(p, "_build_candidate_from_bvid", lambda *a, **k: object())
    monkeypatch.setattr(p, "process_candidate", edit_during_reimport)
    result = p.overwrite_existing_story(gid)
    row = repo.get_story(gid)
    assert result["persisted"] is False
    assert row["status"] == "failed"
    assert row["title"] == "改过的标题"
    assert "410" in row["payload"]["collect_failure"]["error"]


def test_cli_preview_does_not_recover_jobs_or_migrate_schema(app_ctx, monkeypatch, capsys):
    from app.config import config
    from app.repositories import sql_exec as sql
    from app.services.gold_story.collect import search
    from scripts import gold_story_cron_collect as cli
    from app import core
    _pending_source()
    sql.execute("DROP TABLE gold_story_search_cursor"); sql.commit()
    before = sql.fetchall("SELECT * FROM gold_story"); sql.commit()
    monkeypatch.setattr(cli, "Config", lambda: config)
    monkeypatch.setattr(core, "_recover_stuck_jobs", lambda: pytest.fail("preview must not recover jobs"))
    monkeypatch.setattr(core, "_recover_stuck_gold_story_pending", lambda: pytest.fail("preview must not drain queue"))
    monkeypatch.setattr(search, "search_bilibili", lambda *a, **k: [])
    assert cli.main(["run", "--dry-run"]) == 1  # zero candidates
    assert sql.fetchall("SELECT * FROM gold_story") == before
    assert sql.fetchone("SELECT 1 FROM sqlite_master WHERE name='gold_story_search_cursor'") is None
    sql.commit()
    assert '"enqueued": 0' in capsys.readouterr().out


def test_unfaithful_extraction_is_repaired_once_then_blocked_before_structure(tmp_path, monkeypatch):
    from app.config import Config
    from app.services.gold_story.collect import pipeline as p
    from app.services.gold_story.collect.search import VideoCandidate
    cfg = Config(); cfg.gold_story_transcript_dir = tmp_path; cfg.gold_story_transcript_repair = False
    sid = "BV1RETRY0001"; (tmp_path / (sid + '.txt')).write_text("妈妈：关灯睡觉\n孩子：知道了")
    candidate = VideoCandidate(source="bili", source_id=sid, url="", title="姐弟日常", description="", view_count=0, reply_count=0, keyword="")
    monkeypatch.setattr(p, "_existing_source", lambda *a: False)
    attempts = []
    def extract(**kwargs):
        attempts.append(kwargs)
        return {"story_raw": "门铃响了，孩子跑出去开门。"}
    def audit(**kwargs): raise p.llm_steps.ModelOutputError("H2 source_unfaithful: 门铃响了")
    monkeypatch.setattr(p.llm_steps, "extract_story_raw", extract)
    monkeypatch.setattr(p.llm_steps, "review_story_source", audit)
    monkeypatch.setattr(p.llm_steps, "structurize_story", lambda **k: pytest.fail("unfaithful source reached H3"))
    result = p.process_candidate(candidate, config=cfg)
    assert result["action"] == "error" and "source_unfaithful" in result["error"]
    assert result["retryable"] is True
    assert len(attempts) == 2
    assert not attempts[0]["source_feedback"]
    assert "门铃响了" in attempts[1]["source_feedback"]


def test_reimport_blocks_legacy_flat_export_without_payload_path(app_ctx, tmp_path, monkeypatch):
    import json
    from app.repositories import repo_gold_story as repo
    from app.services.gold_story.gold_chat import export
    sid = "BV1LEGACY001"
    result = repo.insert_or_skip(source="bili", source_id=sid, url="", mechanism="M11", structure_type="I",
        story_raw="姐弟互相追问最后无言以对" * 20, payload={}, auto_score=0.9, status="active")
    row = repo.get_story(result['id'])
    legacy = tmp_path / (sid + '.json');legacy.write_text(json.dumps({'daily_story': {'dialogue': []}}))
    monkeypatch.setattr(export, 'gold_chat_export_dir', lambda _cfg=None: tmp_path)
    assert export.load_gold_chat_for_row(row)
    repo.update_story_from_pipeline(row['id'], mechanism='M11', structure_type='I', title='重导',
        conflict_core='追问', story_raw='新的来源对话' * 30, payload=row['payload'], expected_row=row)
    assert export.load_gold_chat_for_row(repo.get_story(row['id'])) is None
    assert legacy.is_file()


@pytest.mark.parametrize("stage", ["metadata", "comments", "danmaku"])
@pytest.mark.parametrize("partial", [False, True])
def test_search_isolates_candidate_outages_without_losing_progress(app_ctx, monkeypatch, stage, partial):
    from app.repositories import sql_exec as sql
    from app.services.gold_story.collect import search
    monkeypatch.setattr(search, "search_bilibili", lambda *a, **k: ["BV1BROKEN001", "BV1HEALTHY01"] if partial else ["BV1BROKEN001"])
    def meta(bv, **kwargs):
        if stage == "metadata" and bv == "BV1BROKEN001":
            raise TimeoutError("view unavailable")
        return {"title": "姐弟日常", "description": "", "view_count": 200000, "reply_count": 100,
                "aid": 1 if bv == "BV1BROKEN001" else 2, "cid": 1, "url": "https://www.bilibili.com/video/" + bv}
    def replies(aid, **kwargs):
        if stage == "comments" and aid == 1:
            raise TimeoutError("comments unavailable")
        return []
    def funny(**kwargs):
        if stage == "danmaku" and kwargs["source_id"] == "BV1BROKEN001":
            if kwargs.get("strict"):
                raise TimeoutError("danmaku unavailable")
            pytest.fail("search must not score unavailable audience evidence")
        return None
    monkeypatch.setattr(search, "fetch_video_meta", meta)
    monkeypatch.setattr(search, "fetch_top_replies", replies)
    monkeypatch.setattr(search, "compute_audience_funny_metrics", funny)
    monkeypatch.setattr(search, "metrics_to_payload", lambda x: {})
    if partial:
        result = search.collect_candidates(keywords=["姐弟"], max_candidates=2)
        assert [item.source_id for item in result] == ["BV1HEALTHY01"]
    else:
        with pytest.raises(RuntimeError, match="候选.*失败"):
            search.collect_candidates(keywords=["姐弟"], max_candidates=2)
    assert sql.fetchall("SELECT * FROM gold_story_search_cursor") == []
    sql.commit()


@pytest.mark.parametrize("outcome", ["reject", "error"])
@pytest.mark.parametrize("edit", ["archived", "payload"])
def test_collect_failure_cannot_overwrite_concurrent_changes(app_ctx, monkeypatch, outcome, edit):
    from app.repositories import repo_gold_story as repo
    from app.services.gold_story.collect import pipeline as p
    gid = _pending_source()
    monkeypatch.setattr(p, "_build_candidate_from_bvid", lambda *a, **k: object())
    saved = []
    def process(*a, **k):
        if edit == "archived":
            repo.set_story_status(gid, status="archived")
        else:
            repo.patch_story_payload(gid, {"user_note": "keep concurrent edit"})
        saved.append(repo.get_story(gid))
        return {"action": outcome, "stage": "H0b", "reason": "unusable", "error": "offline", "retryable": True}
    monkeypatch.setattr(p, "process_candidate", process)
    monkeypatch.setattr(p.time, "sleep", lambda *a: pytest.fail("superseded attempt must not retry"))
    result = p.drain_pending_stories()
    assert len(saved) == 1
    fresh = repo.get_story(gid)
    if edit == "archived":
        assert fresh == saved[0]
    else:
        assert fresh["status"] == "failed"
        assert fresh["payload"]["user_note"] == "keep concurrent edit"
        assert fresh["payload"]["collect_attempts"] == 1
        assert result["failed"] == 1
    assert result["results"][0]["reason"] == "source_changed"


@pytest.mark.parametrize("report,expected", [
    ({"candidates": 1, "failed": 1}, 1),
    ({"candidates": 2, "inserted": 1, "failed": 1}, 1),
    ({"candidates": 1, "inserted": 1, "failed": 0}, 0),
    ({"candidates": 1, "gate_rejected": 1, "failed": 0}, 0),
    ({"candidates": 0, "processed": 1, "gate_rejected": 1, "failed": 0}, 0),
    ({"candidates": 0, "processed": 0, "failed": 0}, 1),
])
def test_collect_cli_exit_code_reports_execution_failure(app_ctx, monkeypatch, report, expected):
    from scripts import gold_story_cron_collect as cli
    monkeypatch.setattr(cli, "_cli_app", lambda *a, **k: app_ctx)
    monkeypatch.setattr(cli, "run_collect_pipeline", lambda **k: report)
    assert cli.main(["run"]) == expected


def test_reimport_duplicate_ids_run_once_and_continue_after_item_failure(app_ctx, monkeypatch):
    from app.services.gold_story.collect import pipeline as p
    ids = [_pending_source("BV1BATCH0001"), _pending_source("BV1BATCH0002")]
    calls = []
    def overwrite(gid, **kwargs):
        calls.append(gid)
        if gid == ids[0]:
            raise OSError("item unavailable")
        return {"id": gid, "action": "ok", "source_id": "BV1BATCH0002"}
    monkeypatch.setattr(p, "overwrite_existing_story", overwrite)
    report = p.reimport_stories(gold_story_ids=[ids[0], ids[0], ids[1]], source_ids=["BV1BATCH0002"])
    assert calls == ids
    assert report["requested"] == 2 and report["failed"] == 1 and report["updated"] == 1


def test_new_bv_batch_isolates_processing_and_progress_failures(app_ctx, monkeypatch):
    from app.services.gold_story.collect import pipeline as p
    from app.services.gold_story.collect.search import VideoCandidate
    calls = []
    monkeypatch.setattr(p, "_build_candidate_from_bvid", lambda sid, **k: VideoCandidate(
        source="bili", source_id=sid, url="", title="姐弟日常", description="", view_count=1, reply_count=1, keyword=""))
    def process(candidate, **kwargs):
        calls.append(candidate.source_id)
        if candidate.source_id == "BV1BATCH0001":
            raise OSError("storage unavailable")
        return {"action": "insert", "id": 123}
    def progress(report):
        raise RuntimeError("progress subscriber disconnected")
    monkeypatch.setattr(p, "process_candidate", process)
    report = p.reimport_stories(source_ids=["BV1BATCH0001", "BV1BATCH0002", "BV1BATCH0001"], on_progress=progress)
    assert calls == ["BV1BATCH0001", "BV1BATCH0002"]
    assert report["failed"] == 1 and report["inserted"] == 1
    assert report["results"][0]["error"] == "storage unavailable"


def test_reimport_dedupe_excludes_self_before_selecting_best_match(app_ctx, tmp_path, monkeypatch):
    from app.config import Config
    from app.repositories import repo_gold_story as repo
    from app.services.gold_story.collect import pipeline as p
    from app.services.gold_story.collect.search import VideoCandidate
    text = "姐姐拿着书本询问弟弟是否喜欢学习，弟弟说你听不懂我说话我也听不懂你说话，所以彼此一样。姐姐反驳说他只是嘴硬，弟弟无话可说。"
    first = _pending_source("BV1BATCH0001")
    other = _pending_source("BV1BATCH0002")
    repo.patch_story_payload(first, {"story_raw": text})
    repo.patch_story_payload(other, {"story_raw": text + "妈妈听见后笑出了声。"})
    assert repo.find_near_duplicate(text)["id"] == first
    row = repo.get_story(first)
    cfg = Config(); cfg.gold_story_transcript_dir = tmp_path; cfg.gold_story_transcript_repair = False
    (tmp_path / "BV1BATCH0001.txt").write_text(text)
    monkeypatch.setattr(p.llm_steps, "extract_story_raw", lambda **k: {"story_raw": text})
    monkeypatch.setattr(p.llm_steps, "review_story_source", lambda **k: {"faithful": True})
    monkeypatch.setattr(p.llm_steps, "structurize_story", lambda **k: pytest.fail("duplicate reached H3"))
    candidate = VideoCandidate(source="bili", source_id="BV1BATCH0001", url="", title="姐弟日常", description="", view_count=1, reply_count=1, keyword="")
    result = p.process_candidate(candidate, config=cfg, skip_transcript=True, overwrite_existing=True, existing_row=row)
    assert result["reason"] == "duplicate_similar_story"
    assert result["similar_source_id"] == "BV1BATCH0002"
    assert result["id"] == first and result["duplicate_id"] == other


def test_enqueue_failures_survive_aggregate_report_and_progress(app_ctx, monkeypatch):
    from app.services.gold_story.collect import pipeline as p
    from app.services.gold_story.collect.search import VideoCandidate
    candidates = [VideoCandidate(source="bili", source_id=f"BV1BATCH000{i}", url="", title="姐弟日常", description="", view_count=1, reply_count=1, keyword="") for i in (1, 2)]
    monkeypatch.setattr(p, "collect_candidates", lambda **k: candidates)
    original = p.repo_gold_story.insert_pending
    def insert(**kwargs):
        if kwargs["source_id"] == "BV1BATCH0001":
            raise OSError("database write failed")
        return original(**kwargs)
    monkeypatch.setattr(p.repo_gold_story, "insert_pending", insert)
    def drain(**kwargs):
        result = {"phase": "process", "processed": 1, "failed": 1, "results": [{"action": "error", "source_id": "BV1BATCH0002"}]}
        kwargs["on_progress"](result)
        return result
    monkeypatch.setattr(p, "drain_pending_stories", drain)
    updates = []
    result = p.run_collect_pipeline(write_list=False, on_progress=updates.append)
    assert result["enqueued"] == 1 and result["failed"] == 2
    assert updates[-1]["failed"] == 2 and updates[-1]["candidates"] == 2


@pytest.mark.parametrize("queued", [False, True])
@pytest.mark.parametrize("export_fails", [False, True])
def test_collection_export_failure_keeps_committed_story_and_reports_failure(app_ctx, tmp_path, monkeypatch, queued, export_fails):
    from app.config import Config
    from app.repositories import repo_gold_story as repo
    from app.services.gold_story.collect import pipeline as p
    from app.services.gold_story.collect.search import VideoCandidate
    sid = "BV1EXPORT001"
    cfg = Config(); cfg.gold_story_transcript_dir = tmp_path; cfg.gold_story_transcript_repair = False
    (tmp_path / (sid + ".txt")).write_text("妈妈：谁收拾桌上的书本？\n姐姐：我来收拾。\n弟弟：那我擦桌子。")
    candidate = VideoCandidate(source="bili", source_id=sid, url="", title="姐弟日常", description="", view_count=500000, reply_count=500, keyword="", funny_metrics={"funny_signal": 0.8})
    monkeypatch.setattr(p, "_build_candidate_from_bvid", lambda *a, **k: candidate)
    monkeypatch.setattr(p.llm_steps, "extract_story_raw", lambda **k: {"story_raw": "姐弟一起收拾书本并擦干净桌子。" * 15, "extract_confidence": 0.9})
    monkeypatch.setattr(p.llm_steps, "review_story_source", lambda **k: {"faithful": True})
    monkeypatch.setattr(p.llm_steps, "structurize_story", lambda **k: {"mechanism": "M6", "structure_type": "A", "structure_confidence": 0.9})
    monkeypatch.setattr(p.llm_steps, "build_scene_contract", lambda **k: {})
    monkeypatch.setattr(p, "sync_h3_from_scene_contract", lambda h3, *a, **k: (h3, []))
    monkeypatch.setattr(p.llm_steps, "build_dialogue_seed", lambda **k: {"dialogue_confidence": 0.9})
    monkeypatch.setattr(p.gs_review, "audit_story", lambda **k: {"pass": True})
    monkeypatch.setattr(p, "passes_funny_gate_from_payload", lambda *a, **k: (True, "ok"))
    calls = []
    def export(**kwargs):
        calls.append(kwargs["row"]["id"])
        if export_fails:
            raise OSError("export disk full")
        return {"json": "export.json", "markdown": "export.md"}
    monkeypatch.setattr(p, "export_story_files", export)
    if queued:
        _pending_source(sid)
        report = p.drain_pending_stories(config=cfg)
    else:
        report = p.reimport_stories(source_ids=[sid], config=cfg, force_transcript=False)
    stored = repo.get_by_source_id(source_id=sid)
    assert stored["status"] == "active"
    assert len(calls) == 1
    assert report["failed"] == int(export_fails)
    outcome = report["results"][0]
    if export_fails:
        assert outcome["stage"] == "export" and outcome["persisted"] is True
        assert outcome["error"] == "export disk full"
        assert outcome["id"] == stored["id"]
    else:
        assert outcome["export"]["json"] == "export.json"


@pytest.mark.parametrize("force", [None, False, True])
def test_drain_honors_explicit_transcript_refresh_but_reuses_cache_by_default(app_ctx, monkeypatch, force):
    from app.services.gold_story.collect import pipeline as p
    _pending_source()
    monkeypatch.setattr(p, "_build_candidate_from_bvid", lambda *a, **k: object())
    seen = []
    def process(*a, **kwargs):
        seen.append(kwargs["force_transcript"])
        return {"action": "reject", "reason": "source_unusable"}
    monkeypatch.setattr(p, "process_candidate", process)
    p.drain_pending_stories(**({} if force is None else {"force_transcript": force}))
    assert seen == [bool(force)]


def test_collect_recovery_fences_old_runner_before_next_attempt(app_ctx, monkeypatch):
    from app.repositories import repo_gold_story as repo
    from app.services.gold_story.collect import pipeline as p
    gid = _pending_source()
    claims = []
    def offline(*a, **k):
        raise TimeoutError("temporary upstream failure")
    def recover(*a):
        repo.reset_processing_to_pending()
        claims.append(repo.claim_next_pending())
    monkeypatch.setattr(p, "_build_candidate_from_bvid", offline)
    monkeypatch.setattr(p.time, "sleep", recover)
    report = p.drain_pending_stories()
    assert len(claims) == 1
    fresh = repo.get_story(gid)
    assert fresh["status"] == "processing"
    assert fresh["payload"]["collect_attempts"] == 1
    assert report["results"][0]["reason"] == "source_changed"


def test_collect_claim_changes_on_recovery(app_ctx):
    from app.repositories import repo_gold_story as repo
    gid = _pending_source()
    first = repo.claim_next_pending()
    repo.begin_collect_attempt(gid, max_attempts=3)
    repo.reset_processing_to_pending()
    second = repo.claim_next_pending()
    assert first["payload"]["collect_claim_id"] != second["payload"]["collect_claim_id"]
    assert second["payload"]["collect_attempts"] == 1


def test_invalid_model_response_is_execution_failure_not_rejected_source(app_ctx, tmp_path, monkeypatch):
    from app.config import Config
    from app.services.gold_story.collect import pipeline as p
    from app.services.gold_story.collect.search import VideoCandidate
    cfg = Config(); cfg.gold_story_transcript_dir = tmp_path; cfg.gold_story_transcript_repair = True
    sid = "BV1SCHEMA001"; (tmp_path / (sid + '.txt')).write_text("妈妈：关灯睡觉\n孩子：知道了")
    candidate = VideoCandidate(source="bili", source_id=sid, url="", title="姐弟日常", description="", view_count=1, reply_count=1, keyword="")
    monkeypatch.setattr(p.llm_steps, "_chat_json", lambda *a: {})
    result = p.process_candidate(candidate, config=cfg)
    assert result["action"] == "error" and result["stage"] == "H0c"
    assert result["error"].startswith("LLM ")


@pytest.mark.parametrize("title", [
    "姐姐的英语作业被弟弟写成了菜单", "弟弟问妈妈为什么要生孩子",
    "姐姐说我的世界里没有弟弟", "姐弟争论谁才是家里的王者",
    "妈妈怀孕了，姐弟争着给宝宝起名字",
])
def test_title_gate_keeps_ambiguous_family_topics(title):
    from app.services.gold_story.collect.search import title_reject_reason
    assert title_reject_reason(title) is None


@pytest.mark.parametrize("title", ["产房实录", "待产包清单", "生娃全过程", "孕期记录", "英语启蒙教程", "游戏实况"])
def test_title_gate_still_rejects_explicit_excluded_genres(title):
    from app.services.gold_story.collect.search import title_reject_reason
    assert title_reject_reason(title) is not None


@pytest.mark.parametrize("stage", ["H1", "H0c", "LLM"])
def test_new_bv_early_rejection_is_saved(app_ctx, monkeypatch, stage):
    from app.repositories import repo_gold_story as repo
    from app.services.gold_story.collect import pipeline as p
    from app.services.gold_story.collect.search import VideoCandidate
    sid = "BV1EARLY0001"
    candidate = VideoCandidate(source="bili", source_id=sid, url="", title="姐弟日常",
                               description="", view_count=1, reply_count=1, keyword="")
    monkeypatch.setattr(p, "_build_candidate_from_bvid", lambda *a, **k: candidate)
    monkeypatch.setattr(p, "process_candidate", lambda *a, **k: {
        "action": "reject", "stage": stage, "reason": "source_unusable", "error": "没有完整场景",
    })
    result = p.import_or_overwrite_source(sid)
    row = repo.get_by_source_id(source_id=sid)
    assert row is not None
    assert result["id"] == row["id"] and result["status"] == "rejected"
    assert row["payload"]["audit"]["reject_reasons"] == ["没有完整场景"]
    assert row["payload"]["audit"]["reason_code"] == "source_unusable"
    assert repo.claim_next_pending() is None


def test_queued_rejection_preserves_detail_and_clears_old_failure(app_ctx):
    from app.repositories import repo_gold_story as repo
    gid = _pending_source()
    row = repo.claim_next_pending()
    repo.record_collect_failure(gid, {"action": "error", "error": "timeout"}, retry=True, expected_row=row)
    row = repo.get_story(gid, include_payload_snapshot=True)
    assert repo.record_collect_failure(gid, {
        "action": "reject", "stage": "H0c", "reason": "source_unusable", "error": "没有完整场景",
    }, retry=False, expected_row=row)
    row = repo.get_story(gid)
    assert row["payload"]["audit"]["reject_reasons"] == ["没有完整场景"]
    assert "collect_failure" not in row["payload"]


def test_malformed_h3_is_retryable_execution_failure(monkeypatch):
    from app.config import Config
    from app.services.gold_story.collect import pipeline as p
    from app.services.gold_story.collect.search import VideoCandidate
    cfg = Config(); cfg.gold_story_transcript_repair = False
    candidate = VideoCandidate(source="bili", source_id="BV1SCHEMA002", url="", title="姐弟日常",
                               description="", view_count=1, reply_count=1, keyword="")
    monkeypatch.setattr(p, "_read_transcript", lambda *a: "姐姐和弟弟争遥控器")
    monkeypatch.setattr(p, "transcribe_bilibili", lambda *a, **k: {"action": "ok"})
    monkeypatch.setattr(p.llm_steps, "extract_story_raw", lambda **k: {"story_raw": "姐弟争遥控器" * 20})
    monkeypatch.setattr(p.llm_steps, "review_story_source", lambda **k: {"faithful": True})
    monkeypatch.setattr(p.repo_gold_story, "find_near_duplicate", lambda *a, **k: None)
    monkeypatch.setattr(p.llm_steps, "_chat_json", lambda *a: {"mechanism": "BAD"})
    result = p.process_candidate(candidate, config=cfg, existing_row={"id": 1, "payload": {}},
                                 overwrite_existing=True, force_transcript=True)
    assert result["action"] == "error" and result["retryable"] is True
    assert "invalid mechanism" in result["error"]


@pytest.mark.parametrize("content_pass", [True, False])
def test_pipeline_preserves_content_audit_when_funny_gate_fails(monkeypatch, content_pass):
    from app.config import Config
    from app.services.gold_story.collect import pipeline as p
    from app.services.gold_story.collect.search import VideoCandidate
    from app.services.gold_story.collect.funny import next_status_after_funny_rescore
    cfg = Config(); cfg.gold_story_transcript_repair = False
    row = {"id": 1, "source_id": "BV1AUDIT0001", "payload": {}}
    candidate = VideoCandidate(source="bili", source_id=row["source_id"], url="", title="姐弟日常",
                               description="", view_count=1, reply_count=1, keyword="")
    monkeypatch.setattr(p, "_read_transcript", lambda *a: "姐姐和弟弟争遥控器")
    monkeypatch.setattr(p, "transcribe_bilibili", lambda *a, **k: {"action": "ok"})
    monkeypatch.setattr(p.llm_steps, "extract_story_raw", lambda **k: {"story_raw": "姐弟争遥控器" * 20})
    monkeypatch.setattr(p.llm_steps, "review_story_source", lambda **k: {"faithful": True})
    monkeypatch.setattr(p.repo_gold_story, "find_near_duplicate", lambda *a, **k: None)
    monkeypatch.setattr(p.llm_steps, "structurize_story", lambda **k: {"mechanism": "M6", "structure_type": "N"})
    monkeypatch.setattr(p.llm_steps, "build_scene_contract", lambda **k: {})
    monkeypatch.setattr(p, "sync_h3_from_scene_contract", lambda h3, *a, **k: (h3, []))
    monkeypatch.setattr(p.llm_steps, "build_dialogue_seed", lambda **k: {})
    reasons = [] if content_pass else ["dialogue_seed_too_short:1<4"]
    audit = {"pass": content_pass, "rule_pass": content_pass, "stage": "rules", "reject_reasons": reasons}
    monkeypatch.setattr(p.gs_review, "audit_story", lambda **k: audit)
    monkeypatch.setattr(p, "passes_funny_gate_from_payload", lambda *a, **k: (False, "low_funny_signal:0.01<0.1"))
    saved = []
    def save(*a, **k):
        saved.append(k["payload"]["audit"])
        return {"auto_score": 0.5}
    monkeypatch.setattr(p.repo_gold_story, "update_story_from_pipeline", save)
    monkeypatch.setattr(p.repo_gold_story, "get_story", lambda *a: row)
    monkeypatch.setattr(p, "_export_collection_result", lambda *a: {})
    result = p.process_candidate(candidate, config=cfg, existing_row=row, overwrite_existing=True, force_transcript=True)
    assert result["status"] == "rejected"
    assert saved[0]["reject_reasons"] == reasons + ["low_funny_signal:0.01<0.1"]
    status, restored = next_status_after_funny_rescore(status="rejected", audit=saved[0], l2_ok=True, l2_reason="ok")
    assert status == ("active" if content_pass else "rejected")
    assert restored == audit


def test_model_output_retry_budget_ends_as_failed_not_rejected(app_ctx, monkeypatch):
    from app.repositories import repo_gold_story as repo
    from app.services.gold_story.collect import pipeline as p
    gid = _pending_source()
    attempts = []
    def broken(*a, **k):
        attempts.append(1)
        raise p.llm_steps.ModelOutputError("H3 invalid mechanism")
    monkeypatch.setattr(p, "_build_candidate_from_bvid", broken)
    monkeypatch.setattr(p.time, "sleep", lambda *a: None)
    report = p.drain_pending_stories()
    row = repo.get_story(gid)
    assert len(attempts) == 3 and report["failed"] == 1
    assert row["status"] == "failed" and "audit" not in row["payload"]


def test_new_bv_rejection_does_not_overwrite_concurrent_insert(app_ctx, monkeypatch):
    from app.repositories import repo_gold_story as repo
    from app.services.gold_story.collect import pipeline as p
    from app.services.gold_story.collect.search import VideoCandidate
    sid = "BV1CONCUR001"
    candidate = VideoCandidate(source="bili", source_id=sid, url="", title="姐弟日常",
                               description="", view_count=1, reply_count=1, keyword="")
    monkeypatch.setattr(p, "_build_candidate_from_bvid", lambda *a, **k: candidate)
    def reject_after_other_insert(*a, **k):
        repo.insert_pending(source="bili", source_id=sid, url="", title="另一请求写入的标题")
        return {"action": "reject", "stage": "H0c", "reason": "source_unusable"}
    monkeypatch.setattr(p, "process_candidate", reject_after_other_insert)
    result = p.import_or_overwrite_source(sid)
    row = repo.get_by_source_id(source_id=sid)
    assert result["persisted"] is False
    assert row["status"] == "pending" and row["title"] == "另一请求写入的标题"
    assert "audit" not in row["payload"]



def test_reimport_duplicate_target_does_not_skip_next_selected_row(app_ctx, monkeypatch):
    from app.repositories import repo_gold_story as repo
    from app.services.gold_story.collect import pipeline as p
    ids = [_pending_source(f"BV1DUPNEXT0{i}") for i in (1, 2)]
    calls = []
    monkeypatch.setattr(p, "_build_candidate_from_bvid", lambda *a, **k: k["existing_row"])
    def process(row, **k):
        calls.append(row["id"])
        if row["id"] == ids[0]:
            return {"action": "skip", "reason": "duplicate_similar_story", "duplicate_id": ids[1]}
        return {"action": "ok", "status": "active", "id": row["id"]}
    monkeypatch.setattr(p, "process_candidate", process)
    report = p.reimport_stories(gold_story_ids=ids)
    assert calls == ids
    assert report["results"][0]["id"] == ids[0]
    assert report["results"][0]["duplicate_id"] == ids[1]
    assert report["ok"] == 1 and report["rejected"] == 1
    assert repo.get_story(ids[0])["status"] == "rejected"


@pytest.mark.parametrize("existing", [False, True])
@pytest.mark.parametrize("failure_stage", ["metadata", "model"])
@pytest.mark.parametrize("recover", [False, True])
def test_manual_bv_import_retries_and_persists_failures(app_ctx, monkeypatch, existing, failure_stage, recover):
    from app.repositories import repo_gold_story as repo
    from app.services.gold_story.collect import pipeline as p
    from app.services.gold_story.collect.search import VideoCandidate
    sid = "BV1RETRYMAN1"
    gid = _pending_source(sid) if existing else None
    attempts = []
    refresh_flags = []
    candidate = VideoCandidate(source="bili", source_id=sid, url="", title="姐弟日常", description="", view_count=1, reply_count=1, keyword="")
    def meta(*a, **k):
        if failure_stage == "metadata":
            attempts.append(1)
            if not recover or len(attempts) < 2:
                raise TimeoutError("metadata timeout")
        return candidate
    def process(*a, **k):
        refresh_flags.append(k["force_transcript"])
        if failure_stage == "model":
            attempts.append(1)
            if not recover or len(attempts) < 2:
                return {"action": "error", "stage": "LLM", "error": "bad model output", "retryable": True}
        return {"action": "reject", "stage": "H0c", "reason": "source_unusable"}
    monkeypatch.setattr(p, "_build_candidate_from_bvid", meta)
    monkeypatch.setattr(p, "process_candidate", process)
    monkeypatch.setattr(p.time, "sleep", lambda *a: None)
    result = p.import_or_overwrite_source(sid)
    row = repo.get_by_source_id(source_id=sid)
    assert len(attempts) == (2 if recover else 3)
    assert row is not None and result["id"] == row["id"]
    if gid:
        assert row["id"] == gid
    assert row["status"] == ("rejected" if recover else "failed")
    assert row["payload"]["collect_attempts"] == len(attempts)
    if not recover:
        assert row["payload"]["collect_failure"]["error"] in {"metadata timeout", "bad model output"}
    if failure_stage == "model":
        assert refresh_flags == [True] + [False] * (len(attempts) - 1)


def test_manual_import_does_not_retry_permanent_or_persisted_failure(app_ctx, monkeypatch):
    from app.services.gold_story.collect import pipeline as p
    from app.services.gold_story.collect.search import VideoCandidate
    from unittest.mock import Mock
    candidate = VideoCandidate(source="bili", source_id="BV1PERMAN01", url="", title="姐弟日常", description="", view_count=1, reply_count=1, keyword="")
    monkeypatch.setattr(p, "_build_candidate_from_bvid", lambda *a, **k: candidate)
    monkeypatch.setattr(p.time, "sleep", lambda *a: pytest.fail("must not retry"))
    for index, outcome in enumerate([
        {"action": "error", "stage": "H0", "error": "unauthorized", "retryable": False},
        {"action": "error", "stage": "export", "error": "export failed", "retryable": True, "persisted": True},
    ]):
        process = Mock(return_value=outcome)
        monkeypatch.setattr(p, "process_candidate", process)
        p.import_or_overwrite_source(f"BV1PERMAN00{index}")
        assert process.call_count == 1


def test_reimport_summary_does_not_count_rejections_as_success(app_ctx, monkeypatch):
    from app.services.gold_story.collect import pipeline as p
    outcomes = iter([
        {"action": "insert"}, {"action": "ok"}, {"action": "reject"},
        {"action": "skip", "status": "rejected"}, {"action": "skip"}, {"action": "error"},
    ])
    monkeypatch.setattr(p, "import_or_overwrite_source", lambda *a, **k: next(outcomes))
    report = p.reimport_stories(source_ids=[f"BV1SUMMARY0{i}" for i in range(6)])
    assert report["requested"] == 6
    assert (report["ok"], report["rejected"], report["skipped"], report["failed"]) == (2, 2, 1, 1)



def test_manual_retry_stops_after_concurrent_source_change(app_ctx, monkeypatch):
    from app.repositories import repo_gold_story as repo
    from app.repositories import sql_exec as sql
    from app.services.gold_story.collect import pipeline as p
    from unittest.mock import Mock
    gid = _pending_source("BV1CHANGE001")
    monkeypatch.setattr(p, "_build_candidate_from_bvid", lambda *a, **k: object())
    process = Mock(return_value={"action": "error", "stage": "LLM", "error": "retry", "retryable": True})
    monkeypatch.setattr(p, "process_candidate", process)
    def concurrent_edit(*a):
        sql.execute("UPDATE gold_story SET title=? WHERE id=?", ("新标题", gid))
        sql.commit()
    monkeypatch.setattr(p.time, "sleep", concurrent_edit)
    result = p.overwrite_existing_story(gid)
    assert process.call_count == 1
    assert result["reason"] == "source_changed" and result["persisted"] is False
    row = repo.get_story(gid)
    assert row["title"] == "新标题" and row["status"] == "pending"
    assert "collect_failure" not in row["payload"]


def test_new_duplicate_bv_gets_own_record_and_keeps_target_untouched(app_ctx, monkeypatch):
    from app.repositories import repo_gold_story as repo
    from app.services.gold_story.collect import pipeline as p
    from app.services.gold_story.collect.search import VideoCandidate
    other = _pending_source("BV1DUPEOLD01")
    sid = "BV1DUPENEW01"
    candidate = VideoCandidate(source="bili", source_id=sid, url="", title="姐弟日常", description="", view_count=1, reply_count=1, keyword="")
    monkeypatch.setattr(p, "_build_candidate_from_bvid", lambda *a, **k: candidate)
    monkeypatch.setattr(p, "process_candidate", lambda *a, **k: {
        "action": "skip", "reason": "duplicate_similar_story", "duplicate_id": other,
    })
    result = p.import_or_overwrite_source(sid)
    assert result["id"] != other and result["duplicate_id"] == other
    assert result["status"] == "rejected"
    assert repo.get_story(other)["status"] == "pending"
    assert repo.get_story(result["id"])["payload"]["audit"]["duplicate_id"] == other


def test_source_age_rejection_stops_before_mapping_and_retries(tmp_path, monkeypatch):
    from app.config import Config
    from app.services.gold_story.collect import pipeline as p
    from app.services.gold_story.collect.search import VideoCandidate
    cfg = Config()
    cfg.gold_story_transcript_dir = tmp_path
    cfg.gold_story_media_workspace = tmp_path / "media"
    cfg.gold_story_transcript_repair = False
    candidate = VideoCandidate(source="bili", source_id="BV1AGECHECK1", url="", title="家庭趣事",
                               description="", view_count=1, reply_count=1, keyword="")
    (tmp_path / f"{candidate.source_id}.txt").write_text("成年女儿临产，父亲先拖地。")
    monkeypatch.setattr(p, "_existing_source", lambda *_a: False)
    monkeypatch.setattr(p, "_build_candidate_from_bvid", lambda *_a, **_kw: candidate)
    extracted = []
    def extract(**_kwargs):
        extracted.append(True)
        return {"story_raw": "成年女儿临产，父亲先拖地。"}
    monkeypatch.setattr(p.llm_steps, "extract_story_raw", extract)
    def reject(**_kwargs):
        raise p.llm_steps.SourceRejected("H2 age_incompatible_core: 成年生育戏核不适用儿童")
    monkeypatch.setattr(p.llm_steps, "review_story_source", reject)
    monkeypatch.setattr(p.llm_steps, "structurize_story", lambda **_kw: pytest.fail("拒绝的来源不能映射"))
    monkeypatch.setattr(p.time, "sleep", lambda *_a: pytest.fail("不应重试素材拒绝"))
    result, _ = p._run_reimport_attempts(candidate.source_id, config=cfg, force_transcript=False)
    assert result["action"] == "reject" and result["attempts"] == 1
    assert "age_incompatible_core" in result["reason"] and extracted == [True]


@pytest.mark.parametrize('manual', [True, False])
def test_long_collection_route_is_manual_only(monkeypatch, manual):
    from app.config import Config
    from app.services.gold_story.collect import pipeline as p
    from app.services.gold_story.collect.search import VideoCandidate
    candidate = VideoCandidate(source='bili', source_id='BV1TEST00001', url='', title='姐弟日常合集',
                               description='', view_count=200000, reply_count=100, keyword='', duration_sec=793)
    monkeypatch.setattr(p, '_existing_source', lambda *a: False)
    calls = []
    monkeypatch.setattr(p, '_process_collection', lambda *a, **kw: calls.append(kw) or {'action': 'selected'})
    cfg = Config(); cfg.gold_story_max_duration_sec = 600
    result = p.process_candidate(candidate, config=cfg, allow_collection=manual)
    assert result['action'] == ('selected' if manual else 'reject')
    assert len(calls) == int(manual)
    if not manual:
        assert result['reason'] == 'too_long'


def test_collection_attempts_next_clip_without_persisting_failed_candidate(monkeypatch, tmp_path):
    from app.config import Config
    from app.services.gold_story.collect import pipeline as p
    from app.services.gold_story.collect.search import VideoCandidate
    from app.services.gold_story.transcript import transcript as tr
    candidate = VideoCandidate(source='bili', source_id='BV1TEST00001', url='', title='合集',
                               description='', view_count=200000, reply_count=100, keyword='', duration_sec=793)
    cfg = Config(); cfg.gold_story_media_workspace = tmp_path
    cfg.gold_story_collection_max_duration_sec = 1800
    clips = [{'start_sec': s, 'end_sec': s + 20, 'eligible': False,
              'index_review': {'reason': '旧粗索引误判'}} for s in (10, 50)]
    monkeypatch.setattr(tr, 'collection_source', lambda *a: {'segments': [], 'duration_sec': 793})
    monkeypatch.setattr(p.llm_steps, 'select_collection_clips', lambda *a, **kw: clips)
    monkeypatch.setattr(tr, 'transcribe_collection_clip', lambda sid, media, clip, cfg: {'source_clip': clip})
    calls = []
    def process(*a, **kw):
        calls.append(kw)
        return {'action': 'reject', 'stage': 'H4a'} if len(calls) == 1 else {'action': 'ok'}
    monkeypatch.setattr(p, 'process_candidate', process)
    result = p._process_collection(candidate, config=cfg, existing_row=None, overwrite_existing=False)
    assert result['action'] == 'ok'
    assert result['source_clip']['start_sec'] == 50
    assert len(result['clip_attempts']) == 2
    assert (tmp_path / 'collection_clips' / candidate.source_id / 'attempts.json').exists()


def test_collection_resource_limit_does_not_claim_content_failure(monkeypatch):
    from app.config import Config
    from app.services.gold_story.collect import pipeline as p
    from app.services.gold_story.collect.search import VideoCandidate
    candidate = VideoCandidate(source='bili', source_id='BV1TEST00001', url='', title='合集',
                               description='', view_count=1, reply_count=1, keyword='', duration_sec=3600)
    cfg = Config(); cfg.gold_story_collection_max_duration_sec = 1800
    result = p._process_collection(candidate, config=cfg, existing_row=None, overwrite_existing=False)
    assert result['reason'] == 'collection_resource_limit'
    assert result['action'] == 'error' and result['retryable'] is False


def test_collection_model_retry_reuses_clip_and_stops_at_budget(monkeypatch, tmp_path):
    from app.config import Config
    from app.services.gold_story.collect import pipeline as p
    from app.services.gold_story.collect.search import VideoCandidate
    from app.services.gold_story.transcript import transcript as tr
    candidate = VideoCandidate(source='bili', source_id='BV1TEST00001', url='', title='合集',
                               description='', view_count=1, reply_count=1, keyword='', duration_sec=800)
    cfg = Config(); cfg.gold_story_media_workspace = tmp_path; cfg.gold_story_collection_max_duration_sec = 1800
    clip = {'start_sec': 10, 'end_sec': 40, 'eligible': True}
    monkeypatch.setattr(tr, 'collection_source', lambda *a: {'segments': [], 'duration_sec': 800})
    monkeypatch.setattr(p.llm_steps, 'select_collection_clips', lambda *a, **kw: [clip])
    transcribed = []
    def transcribe(*a):
        transcribed.append(1)
        return {'source_clip': clip}
    monkeypatch.setattr(tr, 'transcribe_collection_clip', transcribe)
    monkeypatch.setattr(p.time, 'sleep', lambda *a: None)
    calls = []
    def process(*a, **kw):
        calls.append(kw)
        return {'action': 'error', 'stage': 'LLM', 'error': 'invalid evidence', 'retryable': True}
    monkeypatch.setattr(p, 'process_candidate', process)
    result = p._process_collection(candidate, config=cfg, existing_row=None, overwrite_existing=False)
    assert len(calls) == 3 and len(transcribed) == 1
    assert result['action'] == 'error' and result['retryable'] is False
