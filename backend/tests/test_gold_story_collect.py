"""金故事 H0/H1 采集测试。"""

from __future__ import annotations

from app.services.daily_story.gold_story.collect import (
    engagement_norm,
    passes_h1_filter,
)


def test_engagement_norm():
    assert engagement_norm(500_000, 500) == 1.0
    assert engagement_norm(0, 0) == 0.0


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
    from app.services.daily_story.gold_story.collect import search as search_mod
    from app.services.daily_story.gold_story.collect.funny import (
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
    from app.services.daily_story.gold_story.collect import pipeline as pl
    from app.services.daily_story.gold_story.collect.search import VideoCandidate

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
    from app.services.daily_story.gold_story.collect import pipeline as pl

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
