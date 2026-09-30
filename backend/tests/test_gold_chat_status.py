"""gold_chat 失败落库与详情回读。"""

from __future__ import annotations

from app.repositories import repo_gold_story
from app.services.gold_story.gold_chat.status import (
    clear_gold_chat_failure,
    gold_chat_error_from_payload,
    gold_chat_review_pending_from_payload,
    record_gold_chat_failure,
    record_gold_chat_success_timing,
)


def _insert_row(app_ctx) -> int:
    with app_ctx.app_context():
        result = repo_gold_story.insert_or_skip(
            source="bilibili",
            source_id="BV1STATFAIL01",
            url="https://www.bilibili.com/video/BV1STATFAIL01",
            mechanism="M6",
            structure_type="A",
            story_raw="失败落库测试" * 20,
            payload={"setting": "客厅"},
            title="失败落库测试",
            conflict_core="测试",
            auto_score=0.8,
            status="active",
        )
        return int(result["id"])


def test_record_and_read_gold_chat_failure(app_ctx):
    gid = _insert_row(app_ctx)
    with app_ctx.app_context():
        record_gold_chat_failure(
            gid,
            ValueError("setting 缺允许地点"),
            source_id="BV1STATFAIL01",
            stage="convert",
        )
        row = repo_gold_story.get_story(gid)
        payload = row.get("payload") or {}
        err = gold_chat_error_from_payload(payload)
        assert err is not None
        assert err["error"] == "setting 缺允许地点"
        assert err.get("failed_at")
        stats = payload.get("gold_chat_convert_stats") or {}
        assert stats["runs"] == 1
        assert stats["failures"] == 1
        assert stats["last_status"] == "failed"


def test_gold_chat_timing_stats_keep_real_stages_on_success_and_failure(app_ctx):
    gid = _insert_row(app_ctx)
    success_timing = {
        "version": 1,
        "status": "success",
        "stage": "done",
        "total_ms": 120.5,
        "stages_ms": {"contract": 10.0, "draft": 50.0, "finalize": 60.5},
    }
    with app_ctx.app_context():
        record_gold_chat_success_timing(gid, success_timing)
        exc = RuntimeError("终验失败")
        exc.gold_chat_timing = {
            "version": 1,
            "status": "failed",
            "stage": "finalize",
            "total_ms": 80.25,
            "stages_ms": {"contract": 10.0, "draft": 50.0, "finalize": 20.25},
        }
        record_gold_chat_failure(gid, exc, stage="convert")
        payload = repo_gold_story.get_story(gid).get("payload") or {}

    assert payload["gold_chat_last_error_stage"] == "finalize"
    assert payload["gold_chat_last_timing"]["stage"] == "finalize"
    assert "export_backfill" not in payload["gold_chat_last_timing"]["stages_ms"]
    stats = payload["gold_chat_convert_stats"]
    assert stats["runs"] == 2
    assert stats["successes"] == 1
    assert stats["failures"] == 1
    assert stats["success_duration_ms_sum"] == 120.5
    assert stats["failure_duration_ms_sum"] == 80.25
    assert stats["last_status"] == "failed"
    assert stats["last_stage"] == "finalize"


def test_clear_gold_chat_failure(app_ctx):
    gid = _insert_row(app_ctx)
    with app_ctx.app_context():
        record_gold_chat_failure(gid, RuntimeError("对白不足"))
        clear_gold_chat_failure(gid, source_id="BV1STATFAIL01")
        row = repo_gold_story.get_story(gid)
        payload = row.get("payload") or {}
        assert gold_chat_error_from_payload(payload) is None
        assert payload.get("gold_chat_last_error") is None


def test_gold_chat_error_from_payload_empty():
    assert gold_chat_error_from_payload(None) is None
    assert gold_chat_error_from_payload({}) is None
    assert gold_chat_error_from_payload({"gold_chat_last_error": "  "}) is None


def test_gold_chat_error_suppressed_when_export_on_disk():
    payload = {
        "gold_chat_last_error": "终检本地硬伤：重复",
        "gold_chat_last_failed_at": "2026-09-23T03:07:25+00:00",
        "gold_chat_exported_at": "2026-09-23T03:07:11+00:00",
    }
    assert gold_chat_error_from_payload(payload, has_gold_chat=True) is None
    assert gold_chat_error_from_payload(payload, has_gold_chat=False) is None


def test_review_pending_failure_visible_even_with_old_export():
    candidate = {
        "scene_title": "待审核候选",
        "dialogue": [{"speaker": "昭昭", "line": "这版还要人工确认。"}],
        "quality": {"review_status": "review_pending"},
    }
    payload = {
        "gold_chat_last_error": "gold_chat修稿预算耗尽 stage=final_acceptance",
        "gold_chat_last_failed_at": "2026-09-30T08:00:00+00:00",
        "gold_chat_last_error_stage": "convert",
        "gold_chat_exported_at": "2026-09-29T08:00:00+00:00",
        "gold_chat_review_status": "review_pending",
        "gold_chat_review_pending_candidate": candidate,
    }

    err = gold_chat_error_from_payload(payload, has_gold_chat=True)
    assert err is not None
    assert err["review_status"] == "review_pending"
    pending = gold_chat_review_pending_from_payload(payload)
    assert pending is not None
    assert pending["status"] == "review_pending"
    assert pending["candidate"] == candidate
    assert "预算耗尽" in pending["error"]
    bare_fail = {"gold_chat_last_error": "structure_score:60"}
    assert gold_chat_error_from_payload(bare_fail)["error"] == "structure_score:60"
