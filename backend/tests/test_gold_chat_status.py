"""gold_chat 失败落库与详情回读。"""

from __future__ import annotations

from app.repositories import repo_gold_story
from app.services.daily_story.gold_story.gold_chat.status import (
    clear_gold_chat_failure,
    gold_chat_error_from_payload,
    record_gold_chat_failure,
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
