"""gold_chat 转换结果落库（成功清错、失败可追溯）。"""

from __future__ import annotations

import logging
import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from app.repositories import repo_gold_story

logger = logging.getLogger(__name__)

# 单条转换含多次 LLM 重试，正常会跑很久。进程中断后超过此时长不再当成转换中。
_CONVERTING_STALE_SEC = 6 * 60 * 60

_GOLD_CHAT_ERROR_CLEAR_KEYS = (
    "gold_chat_last_error",
    "gold_chat_last_failed_at",
    "gold_chat_review_status",
    "gold_chat_review_pending_candidate",
    "gold_chat_failed_candidate",
    "gold_chat_candidate_contract",
)


def gold_chat_source_text(row: dict[str, Any]) -> str:
    """仅为显式授权、且仍绑定当前原文的重构提供生成依据；不改原始素材。"""
    payload = row.get("payload") or {}
    original = str(row.get("story_raw") or payload.get("story_raw") or "")
    adaptation = payload.get("gold_chat_adaptation")
    if adaptation is None:
        return original
    if not isinstance(adaptation, dict):
        raise ValueError("授权重构记录格式无效")
    source_id = str(row.get("source_id") or "")
    if (adaptation.get("mode") != "authorized_reconstruction"
            or adaptation.get("approved") is not True
            or not source_id or adaptation.get("source_id") != source_id
            or not adaptation.get("approved_at") or not adaptation.get("approval_note")):
        raise ValueError("重构素材缺少当前来源的明确授权记录")
    digest = hashlib.sha256(original.encode()).hexdigest()
    if adaptation.get("original_sha256") != digest:
        raise ValueError("原始素材已变化，旧重构授权失效")
    text = adaptation.get("story_raw")
    if not isinstance(text, str) or len(text.strip()) < 40:
        raise ValueError("授权重构素材为空或过短")
    return text.strip()


def gold_chat_candidate_contract(row: dict[str, Any]) -> dict[str, Any]:
    from app.services.daily_story.quality import gold_story_review_contract

    return {"contract": gold_story_review_contract(row), "source_raw": gold_chat_source_text(row)}


def gold_chat_recovery(row: dict[str, Any]) -> dict[str, Any] | None:
    """候选、契约和恢复规则共同形成版本；只允许重审当前来源下的稳定候选。"""
    payload = row.get("payload") or {}
    if payload.get("gold_chat_review_status") == "review_pending":
        candidate = payload.get("gold_chat_review_pending_candidate")
    else:
        candidate = (payload.get("gold_chat_failed_candidate") or {}).get("candidate")
    if not isinstance(candidate, dict) or not candidate.get("dialogue"):
        return None
    contract = payload.get("gold_chat_candidate_contract")
    if not isinstance(contract, dict) or contract != gold_chat_candidate_contract(row):
        return {"candidate": candidate, "revision": None,
                "reason": "候选缺少来源快照或来源契约已变化，请重新转换"}
    encoded = json.dumps({"version": 1, "candidate": candidate, "contract": contract},
                         ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {"candidate": candidate, "revision": hashlib.sha256(encoded.encode()).hexdigest()}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def mark_gold_chat_converting(gold_story_id: int) -> None:
    """转换开始时写入 payload，供列表/状态接口跨进程读到「转换中」。"""
    gid = int(gold_story_id)
    if gid <= 0:
        return
    try:
        repo_gold_story.patch_story_payload(
            gid,
            {
                "gold_chat_convert_status": "converting",
                "gold_chat_convert_started_at": _now_iso(),
            },
        )
    except Exception:
        logger.warning(
            "[GOLD_CHAT] mark converting failed id=%s",
            gid,
            exc_info=True,
        )


def clear_gold_chat_converting(gold_story_id: int) -> None:
    """转换结束（成功或失败）后清掉「转换中」。"""
    gid = int(gold_story_id)
    if gid <= 0:
        return
    try:
        repo_gold_story.patch_story_payload(
            gid,
            {
                "gold_chat_convert_status": None,
                "gold_chat_convert_started_at": None,
            },
        )
    except Exception:
        logger.warning(
            "[GOLD_CHAT] clear converting failed id=%s",
            gid,
            exc_info=True,
        )


def gold_chat_converting_from_payload(
    payload: dict[str, Any] | None,
    *,
    now: datetime | None = None,
) -> bool:
    """payload 是否表示这条金故事正在转对话。过期标记视为已结束。"""
    if not isinstance(payload, dict):
        return False
    task = payload.get("gold_chat_task")
    if isinstance(task, dict) and task.get("task_id"):
        current_time = now or datetime.now(timezone.utc)
        return (task.get("status") in {"queued", "running"}
                and current_time.timestamp() < float(task.get("expires_at") or 0))
    if str(payload.get("gold_chat_convert_status") or "").strip() != "converting":
        return False
    started_raw = str(payload.get("gold_chat_convert_started_at") or "").strip()
    if not started_raw:
        return False
    try:
        started = datetime.fromisoformat(started_raw)
    except ValueError:
        return False
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    age = (current - started).total_seconds()
    return age <= _CONVERTING_STALE_SEC


def list_gold_chat_converting() -> dict[str, Any]:
    """当前仍在转换中的金故事。CLI 与 Web 分进程，只认库里的标记。"""
    rows = repo_gold_story.list_stories_with_payload_marker(
        marker='"gold_chat_convert_status"',
    )
    tasks = repo_gold_story.list_stories_with_payload_marker(marker='"gold_chat_task"')
    rows = list({row["id"]: row for row in [*rows, *tasks]}.values())
    ids: list[int] = []
    source_ids: list[str] = []
    for row in rows:
        payload = row.get("payload")
        if not gold_chat_converting_from_payload(
            payload if isinstance(payload, dict) else None,
        ):
            continue
        gid = int(row.get("id") or 0)
        if gid > 0:
            ids.append(gid)
        sid = str(row.get("source_id") or "").strip()
        if sid:
            source_ids.append(sid)
    running = bool(ids or source_ids)
    return {
        "workflow": "gold_chat_convert",
        "status": "running" if running else "idle",
        "ids": ids,
        "source_ids": source_ids,
    }


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
        if candidate_source == "current":
            patch["gold_chat_candidate_contract"] = getattr(
                exc, "gold_chat_candidate_contract", None,
            ) or gold_chat_candidate_contract(row)
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
            patch["gold_chat_failed_candidate"] = None
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
