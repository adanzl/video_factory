"""gold_chat 转换结果落库（成功清错、失败可追溯）。"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.repositories import repo_gold_story

logger = logging.getLogger(__name__)

_GOLD_CHAT_ERROR_CLEAR_KEYS = (
    "gold_chat_last_error",
    "gold_chat_last_failed_at",
    "gold_chat_review_status",
    "gold_chat_review_pending_candidate",
    "gold_chat_failed_candidate",
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def format_gold_chat_error(exc: BaseException) -> str:
    text = str(exc or "").strip()
    if text:
        return text
    return exc.__class__.__name__


def gold_chat_review_pending_from_payload(
    payload: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """读取修稿预算耗尽后保留的待审核候选；已有成功导出也不隐藏。"""
    if not isinstance(payload, dict):
        return None
    if str(payload.get("gold_chat_review_status") or "").strip() != "review_pending":
        return None
    candidate = payload.get("gold_chat_review_pending_candidate")
    if not isinstance(candidate, dict):
        return None
    out: dict[str, Any] = {
        "status": "review_pending",
        "candidate": candidate,
    }
    err = str(payload.get("gold_chat_last_error") or "").strip()
    if err:
        out["error"] = err
    failed_at = str(payload.get("gold_chat_last_failed_at") or "").strip()
    if failed_at:
        out["failed_at"] = failed_at
    stage = str(payload.get("gold_chat_last_error_stage") or "").strip()
    if stage:
        out["stage"] = stage
    return out


def gold_chat_failed_candidate_from_payload(
    payload: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """读取终检失败时保留的候选稿（与「待审核」候选分字段，避免误认）。"""
    if not isinstance(payload, dict):
        return None
    record = payload.get("gold_chat_failed_candidate")
    if not isinstance(record, dict):
        return None
    candidate = record.get("candidate")
    if not isinstance(candidate, dict):
        return None
    out: dict[str, Any] = {
        "status": "candidate_failed",
        "candidate": candidate,
        "candidate_source": str(record.get("candidate_source") or "current"),
        "needs_manual_review": bool(record.get("needs_manual_review")),
    }
    reason = str(record.get("failed_reason") or "").strip()
    if reason:
        out["error"] = reason
    failed_at = str(record.get("failed_at") or "").strip()
    if failed_at:
        out["failed_at"] = failed_at
    stage = str(record.get("failed_stage") or "").strip()
    if stage:
        out["stage"] = stage
    return out


def gold_chat_error_from_payload(
    payload: dict[str, Any] | None,
    *,
    has_gold_chat: bool = False,
) -> dict[str, str] | None:
    if not isinstance(payload, dict):
        return None
    pending = gold_chat_review_pending_from_payload(payload)
    failed = gold_chat_failed_candidate_from_payload(payload)
    # 普通重转失败：磁盘上已有成功导出时继续隐藏，不遮挡“已导出”。
    # 但已保存候选稿（待审核 / 终检失败稿）时必须可见，方便人工确认。
    if (
        has_gold_chat or str(payload.get("gold_chat_exported_at") or "").strip()
    ) and pending is None and failed is None:
        return None
    err = str(payload.get("gold_chat_last_error") or "").strip()
    if not err:
        return None
    out: dict[str, str] = {"error": err}
    failed_at = str(payload.get("gold_chat_last_failed_at") or "").strip()
    if failed_at:
        out["failed_at"] = failed_at
    if pending is not None:
        out["review_status"] = "review_pending"
    elif failed is not None:
        out["review_status"] = "candidate_failed"
    return out


def _gold_chat_convert_stats(
    payload: dict[str, Any],
    *,
    success: bool,
    timing: dict[str, Any] | None,
) -> dict[str, Any]:
    """累计转换次数/失败次数；耗时只累计真实存在的 total_ms。"""
    raw_stats = payload.get("gold_chat_convert_stats")
    stats: dict[str, Any] = dict(raw_stats) if isinstance(raw_stats, dict) else {}

    def _count(key: str) -> int:
        raw = stats.get(key)
        return int(raw) if isinstance(raw, int) and not isinstance(raw, bool) else 0

    stats["runs"] = _count("runs") + 1
    outcome_key = "successes" if success else "failures"
    stats[outcome_key] = _count(outcome_key) + 1
    stats["last_status"] = "success" if success else "failed"
    if isinstance(timing, dict):
        stage = str(timing.get("stage") or "").strip()
        if stage:
            stats["last_stage"] = stage
        total_raw = timing.get("total_ms")
        if isinstance(total_raw, (int, float)) and not isinstance(total_raw, bool):
            sum_key = "success_duration_ms_sum" if success else "failure_duration_ms_sum"
            prev = stats.get(sum_key)
            prev_num = float(prev) if isinstance(prev, (int, float)) and not isinstance(prev, bool) else 0.0
            stats[sum_key] = round(prev_num + float(total_raw), 3)
    return stats


def record_gold_chat_success_timing(
    gold_story_id: int,
    timing: dict[str, Any],
) -> None:
    """成功转换写入最后一次阶段耗时与累计统计；不计统计落库自身耗时。"""
    gid = int(gold_story_id)
    if gid <= 0:
        return
    row = repo_gold_story.get_story(gid)
    payload_raw = row.get("payload")
    payload: dict[str, Any] = payload_raw if isinstance(payload_raw, dict) else {}
    repo_gold_story.patch_story_payload(
        gid,
        {
            "gold_chat_last_timing": dict(timing),
            "gold_chat_convert_stats": _gold_chat_convert_stats(
                payload,
                success=True,
                timing=timing,
            ),
        },
    )


def record_gold_chat_failure(
    gold_story_id: int,
    exc: BaseException,
    *,
    source_id: str = "",
    stage: str = "convert",
) -> None:
    """转换失败写入 payload，供详情页展示。"""
    gid = int(gold_story_id)
    if gid <= 0:
        return
    message = format_gold_chat_error(exc)
    now = _now_iso()
    timing_raw = getattr(exc, "gold_chat_timing", None)
    timing: dict[str, Any] | None = (
        dict(timing_raw) if isinstance(timing_raw, dict) else None
    )
    timing_stage = str(timing.get("stage") or "").strip() if timing else ""
    recorded_stage = timing_stage or str(stage or "convert").strip() or "convert"
    row = repo_gold_story.get_story(gid)
    payload_raw = row.get("payload")
    payload: dict[str, Any] = payload_raw if isinstance(payload_raw, dict) else {}
    patch: dict[str, Any] = {
        "gold_chat_last_error": message,
        "gold_chat_last_failed_at": now,
        "gold_chat_last_error_stage": recorded_stage,
        "gold_chat_convert_stats": _gold_chat_convert_stats(
            payload,
            success=False,
            timing=timing,
        ),
    }
    if timing is not None:
        patch["gold_chat_last_timing"] = timing
    candidate = getattr(exc, "candidate", None)
    candidate_source = "current"
    if not isinstance(candidate, dict):
        # 异常未带候选时回退上一次失败候选仅作保险：它可能不是本次失败稿，
        # 故显式标出来源，避免人工误认。
        prev = payload.get("gold_chat_failed_candidate")
        prev_candidate = prev.get("candidate") if isinstance(prev, dict) else None
        if isinstance(prev_candidate, dict):
            candidate = prev_candidate
            candidate_source = "fallback_last_stable"
    if isinstance(candidate, dict):
        kind = str(getattr(exc, "candidate_review_status", "review_pending")).strip()
        stored: dict[str, Any] = dict(candidate)
        raw_quality = stored.get("quality")
        quality: dict[str, Any] = (
            dict(raw_quality) if isinstance(raw_quality, dict) else {}
        )
        if kind == "failed":
            # 终检失败（审读未完成/证据不可核验）：失败稿单独落字段，不与
            # 「待审核」候选混用，并清掉旧 pending，避免混合状态被误认。
            quality["review_status"] = "failed"
            quality["review_failure_reason"] = message
            stored["quality"] = quality
            patch["gold_chat_review_status"] = "candidate_failed"
            patch["gold_chat_failed_candidate"] = {
                "candidate": stored,
                "failed_stage": recorded_stage,
                "failed_reason": message,
                "failed_at": now,
                "candidate_source": candidate_source,
                "exported": False,
                "needs_manual_review": True,
            }
            patch["gold_chat_review_pending_candidate"] = None
        else:
            # 修稿预算耗尽保留当前稳定候选供人工确认；不覆盖既有成功导出稿。
            quality["review_status"] = "review_pending"
            quality["review_failure_reason"] = message
            stored["quality"] = quality
            patch["gold_chat_review_status"] = "review_pending"
            patch["gold_chat_review_pending_candidate"] = stored
    repo_gold_story.patch_story_payload(
        gid,
        patch,
    )
    logger.error(
        "[GOLD_CHAT] failure recorded id=%s source_id=%s stage=%s error=%s",
        gid,
        source_id or "?",
        recorded_stage,
        message,
    )


def clear_gold_chat_failure(gold_story_id: int, *, source_id: str = "") -> None:
    """转换成功导出后清除失败记录。"""
    gid = int(gold_story_id)
    if gid <= 0:
        return
    row = repo_gold_story.get_story(gid)
    payload = row.get("payload") or {}
    had_error = bool(str(payload.get("gold_chat_last_error") or "").strip())
    repo_gold_story.patch_story_payload(
        gid,
        {key: None for key in _GOLD_CHAT_ERROR_CLEAR_KEYS}
        | {"gold_chat_last_error_stage": None},
    )
    if had_error:
        logger.info(
            "[GOLD_CHAT] 导出成功，历史失败状态已清理 id=%s source_id=%s",
            gid,
            source_id or "?",
        )
