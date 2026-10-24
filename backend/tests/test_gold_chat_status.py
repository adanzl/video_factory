"""gold_chat 失败落库与详情回读。"""

from __future__ import annotations

import pytest

from app.repositories import repo_gold_story
from app.services.gold_story.gold_chat.status import (
    clear_gold_chat_failure,
    gold_chat_error_from_payload,
    gold_chat_failed_candidate_from_payload,
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


def test_finalize_failure_stores_failed_candidate_separately(app_ctx):
    """终检失败稿落 gold_chat_failed_candidate，并清掉旧「待审核」混合状态。"""
    from app.services.gold_story.gold_chat.finalize import GoldChatAcceptanceIncomplete

    gid = _insert_row(app_ctx)
    stale_pending = {
        "scene_title": "旧候选",
        "dialogue": [{"speaker": "昭昭", "line": "这是上一版遗留的待审核稿。"}],
    }
    with app_ctx.app_context():
        repo_gold_story.patch_story_payload(
            gid,
            {
                "gold_chat_review_status": "review_pending",
                "gold_chat_review_pending_candidate": stale_pending,
            },
        )
        exc = GoldChatAcceptanceIncomplete(
            "审核证据无效（第[6-11]句·重复），已保留上次导出稿",
            candidate={
                "scene_title": "终检失败稿",
                "dialogue": [{"speaker": "昭昭", "line": "这版终检没过。"}],
            },
        )
        record_gold_chat_failure(gid, exc, stage="finalize")
        payload = repo_gold_story.get_story(gid).get("payload") or {}

    assert payload["gold_chat_review_status"] == "candidate_failed"
    assert payload["gold_chat_review_pending_candidate"] is None
    record = payload["gold_chat_failed_candidate"]
    assert record["candidate_source"] == "current"
    assert record["exported"] is False
    assert record["needs_manual_review"] is True
    assert record["failed_stage"] == "finalize"
    assert "审核证据无效" in record["failed_reason"]
    assert record["candidate"]["scene_title"] == "终检失败稿"
    assert record["candidate"]["quality"]["review_status"] == "failed"

    assert gold_chat_review_pending_from_payload(payload) is None
    failed = gold_chat_failed_candidate_from_payload(payload)
    assert failed is not None
    assert failed["candidate_source"] == "current"
    assert failed["candidate"]["scene_title"] == "终检失败稿"


def test_failed_candidate_visible_even_with_old_export(app_ctx):
    payload = {
        "gold_chat_last_error": "审核证据无效（第[6-11]句·重复），已保留上次导出稿",
        "gold_chat_last_failed_at": "2026-10-16T06:00:00+00:00",
        "gold_chat_exported_at": "2026-10-15T07:00:00+00:00",
        "gold_chat_review_status": "candidate_failed",
        "gold_chat_failed_candidate": {
            "candidate": {
                "scene_title": "终检失败稿",
                "dialogue": [{"speaker": "昭昭", "line": "这版终检没过。"}],
                "quality": {"review_status": "failed"},
            },
            "failed_stage": "finalize",
            "failed_reason": "审核证据无效（第[6-11]句·重复），已保留上次导出稿",
            "failed_at": "2026-10-16T06:00:00+00:00",
            "candidate_source": "current",
            "exported": False,
            "needs_manual_review": True,
        },
    }
    err = gold_chat_error_from_payload(payload, has_gold_chat=True)
    assert err is not None
    assert err["review_status"] == "candidate_failed"


def test_failed_candidate_falls_back_to_last_stable(app_ctx):
    """异常未带候选时回退上一次失败候选，并显式标出来源避免误认。"""
    from app.services.gold_story.gold_chat.finalize import GoldChatAcceptanceIncomplete

    gid = _insert_row(app_ctx)
    with app_ctx.app_context():
        repo_gold_story.patch_story_payload(
            gid,
            {
                "gold_chat_failed_candidate": {
                    "candidate": {
                        "scene_title": "上次失败稿",
                        "dialogue": [{"speaker": "昭昭", "line": "保留上一版。"}],
                    },
                    "candidate_source": "current",
                },
            },
        )
        exc = GoldChatAcceptanceIncomplete(
            "语义审核未完成（LLM 超时或解析失败）"
        )
        record_gold_chat_failure(gid, exc, stage="finalize")
        payload = repo_gold_story.get_story(gid).get("payload") or {}

    record = payload["gold_chat_failed_candidate"]
    assert record["candidate_source"] == "fallback_last_stable"
    assert record["candidate"]["scene_title"] == "上次失败稿"


def test_clear_gold_chat_failure_drops_failed_candidate(app_ctx):
    gid = _insert_row(app_ctx)
    with app_ctx.app_context():
        payload = {
            "gold_chat_failed_candidate": {
                "candidate": {"scene_title": "失败稿"},
            },
        }
        repo_gold_story.patch_story_payload(gid, payload)
        record_gold_chat_failure(gid, RuntimeError("对白不足"))
        clear_gold_chat_failure(gid, source_id="BV1STATFAIL01")
        payload = repo_gold_story.get_story(gid).get("payload") or {}

    assert gold_chat_failed_candidate_from_payload(payload) is None
    assert gold_chat_error_from_payload(payload) is None


def test_converting_flag_visible_on_list_and_status(app_ctx):
    from app.services.gold_story.gold_chat.status import (
        clear_gold_chat_converting,
        gold_chat_converting_from_payload,
        list_gold_chat_converting,
        mark_gold_chat_converting,
    )
    from app.services.gold_story.gold_story_mgr import gold_story_mgr

    gid = _insert_row(app_ctx)
    with app_ctx.app_context():
        mark_gold_chat_converting(gid)
        payload = repo_gold_story.get_story(gid).get("payload") or {}
        assert gold_chat_converting_from_payload(payload) is True
        listed = gold_story_mgr.list_items(limit=20)
        item = next(row for row in listed["items"] if row["id"] == gid)
        assert item["gold_chat_converting"] is True
        running = list_gold_chat_converting()
        assert running["status"] == "running"
        assert gid in running["ids"]
        clear_gold_chat_converting(gid)
        payload = repo_gold_story.get_story(gid).get("payload") or {}
        assert gold_chat_converting_from_payload(payload) is False
        assert gid not in list_gold_chat_converting()["ids"]


def test_converting_stale_or_empty_not_shown():
    from datetime import datetime, timedelta, timezone

    from app.services.gold_story.gold_chat.status import (
        gold_chat_converting_from_payload,
    )

    old = (datetime.now(timezone.utc) - timedelta(hours=7)).isoformat()
    assert gold_chat_converting_from_payload(
        {
            "gold_chat_convert_status": "converting",
            "gold_chat_convert_started_at": old,
        }
    ) is False
    assert gold_chat_converting_from_payload({}) is False
    assert gold_chat_converting_from_payload(
        {"gold_chat_convert_status": "converting"}
    ) is False


def _adaptation_row():
    import hashlib
    original = "原始素材保留原样，作为用户授权的具体对象。" * 3
    return {"source_id": "BVadaptation", "story_raw": original, "payload": {"story_raw": original,
        "gold_chat_adaptation": {"mode": "authorized_reconstruction", "approved": True,
            "source_id": "BVadaptation", "original_sha256": hashlib.sha256(original.encode()).hexdigest(),
            "approved_at": "2026-10-23T12:00:00Z", "approval_note": "用户明确允许重构",
            "story_raw": "这是经过用户授权后重新创作的素材，新增情节独立保存，不覆盖原始故事。" * 3}}}


def test_authorized_adaptation_binds_original_and_source_identity():
    from copy import deepcopy
    import pytest
    from app.services.gold_story.gold_chat.status import gold_chat_source_text
    row = _adaptation_row()
    before = deepcopy(row)
    assert gold_chat_source_text(row) == row["payload"]["gold_chat_adaptation"]["story_raw"]
    assert row == before
    for field, value in [("approved", False), ("source_id", "another-source"),
                         ("original_sha256", "changed"), ("approved_at", ""),
                         ("approval_note", ""), ("mode", "automatic"), ("story_raw", "短")]:
        invalid = deepcopy(row)
        invalid["payload"]["gold_chat_adaptation"][field] = value
        with pytest.raises(ValueError):
            gold_chat_source_text(invalid)
    row["story_raw"] += "原文已更新"
    with pytest.raises(ValueError, match="原始素材已变化"):
        gold_chat_source_text(row)
    assert gold_chat_source_text({"payload": {"story_raw": "普通素材"}}) == "普通素材"


def test_adaptation_changes_invalidate_review_contract_and_export_retains_original(tmp_path):
    import json
    from app.config import Config
    from app.services.daily_story.quality import gold_story_review_contract
    from app.services.gold_story.gold_chat.export import export_gold_chat_files
    row = _adaptation_row()
    before = gold_story_review_contract(row)
    row["payload"]["gold_chat_adaptation"]["story_raw"] += "新增一处情节"
    assert gold_story_review_contract(row) != before
    cfg = Config()
    cfg.gold_story_transcript_dir = tmp_path / "transcripts"
    paths = export_gold_chat_files(source_id=row["source_id"], row=row,
                                  chat={"dialogue": [{"speaker": "妈妈", "line": "测试导出。"}]},
                                  config=cfg, publish=False)
    from pathlib import Path
    result = json.loads(Path(paths["json"]).read_text())
    assert result["gold_meta"]["original_story_raw"] == row["story_raw"]
    assert result["gold_meta"]["adaptation"] == row["payload"]["gold_chat_adaptation"]
    markdown = Path(paths["markdown"]).read_text()
    assert "用户授权重构" in markdown and row["story_raw"] in markdown


@pytest.mark.parametrize("task_state", ["succeeded", "failed", "expired", "running"])
@pytest.mark.parametrize("new_marker", [False, True])
def test_old_task_does_not_hide_new_legacy_conversion(task_state, new_marker):
    from datetime import datetime, timedelta, timezone
    from app.services.gold_story.gold_chat.status import gold_chat_converting_from_payload
    now = datetime.now(timezone.utc)
    task = {"task_id": "previous", "status": "running" if task_state == "expired" else task_state,
            "started_at": (now - timedelta(seconds=120)).timestamp(),
            "expires_at": (now + timedelta(seconds=-60 if task_state == "expired" else 60)).timestamp()}
    if task_state in {"succeeded", "failed"}:
        task["finished_at"] = (now - timedelta(seconds=30)).timestamp()
    payload = {"gold_chat_task": task, "gold_chat_convert_status": "converting",
               "gold_chat_convert_started_at": (now - timedelta(seconds=5 if new_marker else 100)).isoformat()}
    assert gold_chat_converting_from_payload(payload, now=now) is (new_marker or task_state == "running")


def test_reimport_is_blocked_during_legacy_conversion_after_completed_task(app_ctx, monkeypatch):
    import time
    from app.services.gold_story.collect import pipeline
    from app.services.gold_story.gold_chat.status import mark_gold_chat_converting, clear_gold_chat_converting
    gid = _insert_row(app_ctx)
    now = time.time()
    task = {"task_id": "previous", "status": "running", "started_at": now - 60, "expires_at": now + 120}
    repo_gold_story.claim_chat_task(gid, task)
    repo_gold_story.update_chat_task(gid, {**task, "status": "succeeded", "finished_at": now - 30})
    mark_gold_chat_converting(gid)
    monkeypatch.setattr(pipeline, "_build_candidate_from_bvid", lambda *a, **k: pytest.fail("conversion in progress must block reimport"))
    result = pipeline.overwrite_existing_story(gid)
    assert result["action"] == "error" and "转换进行中" in result["error"]
    clear_gold_chat_converting(gid)
