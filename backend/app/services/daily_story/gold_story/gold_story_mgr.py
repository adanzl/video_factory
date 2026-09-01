"""金故事对外入口（对齐 daily_story_mgr）。"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, cast

from app.config import Config
from app.repositories import repo_gold_story
from app.services.daily_story.gold_story.gold_chat.batch import run_gold_chat_batch
from app.services.daily_story.gold_story.gold_chat.convert import convert_gold_chat
from app.services.daily_story.gold_story.gold_chat.export import (
    gold_chat_summary,
    load_gold_chat,
    load_gold_chat_for_row,
)
from app.services.daily_story.gold_story.gold_chat.status import (
    gold_chat_error_from_payload,
    record_gold_chat_failure,
)
from app.services.daily_story.gold_story.gold_chat.import_story import (
    import_gold_chat_daily_story,
)
from app.services.daily_story.gold_story.export_story import (
    cleanup_gold_story_files,
    load_transcript_for_row,
)
from app.services.daily_story.gold_story.collect.pipeline import (
    drain_pending_stories,
    reimport_stories,
    run_collect_pipeline,
)
from app.utils.async_util import run_in_os_thread

logger = logging.getLogger(__name__)


def _hub_safe_lock() -> Any:
    """gevent hub 上可让出的锁。

    main.py 使用 ``monkey.patch_all(..., thread=False)``，``threading.Lock``
    是真实 OS 锁。请求 greenlet A 持锁并 yield 后，greenlet B 再
    ``acquire()`` 会堵死整个 hub（接口全部无响应）。必须用 gevent 锁。
    """
    try:
        from gevent.lock import Semaphore

        return Semaphore(1)
    except ImportError:
        return threading.Lock()


_COLLECT_LOCK = _hub_safe_lock()
_COLLECT_STATE: dict[str, Any] = {
    "workflow": "gold_story_collect",
    "status": "idle",
}
_REIMPORT_LOCK = _hub_safe_lock()
_REIMPORT_STATE: dict[str, Any] = {
    "workflow": "gold_story_reimport",
    "status": "idle",
}
_CONVERT_LOCK = _hub_safe_lock()


def _ensure_schema() -> None:
    from app.repositories.db_obj import db
    from app.repositories.schema import apply_gold_story_schema
    from app.repositories import sql_exec as sql

    conn = db.session.connection().connection.dbapi_connection
    apply_gold_story_schema(conn)  # type: ignore[arg-type]
    sql.commit()


def _collect_snapshot() -> dict[str, Any]:
    with _COLLECT_LOCK:
        return dict(_COLLECT_STATE)


def _reimport_snapshot() -> dict[str, Any]:
    with _REIMPORT_LOCK:
        return dict(_REIMPORT_STATE)


def reset_collect_state() -> None:
    with _COLLECT_LOCK:
        _COLLECT_STATE.clear()
        _COLLECT_STATE.update(
            {
                "workflow": "gold_story_collect",
                "status": "idle",
            }
        )
    with _REIMPORT_LOCK:
        _REIMPORT_STATE.clear()
        _REIMPORT_STATE.update(
            {
                "workflow": "gold_story_reimport",
                "status": "idle",
            }
        )


def _summarize_collect_report(
    report: dict[str, Any],
    *,
    max_candidates: int,
) -> dict[str, Any]:
    results = report.get("results") or []
    skipped = int(
        report.get("skipped")  # type: ignore[arg-type]
        if report.get("skipped") is not None
        else sum(1 for r in results if r.get("action") == "skip")
    )
    failed = int(
        report.get("failed")  # type: ignore[arg-type]
        if report.get("failed") is not None
        else sum(1 for r in results if r.get("action") == "error")
    )
    gate_rejected = int(report.get("gate_rejected") or 0)
    if not gate_rejected:
        gate_rejected = sum(
            1
            for r in results
            if r.get("action") == "reject" and not r.get("id")
        )
    return {
        "workflow": "gold_story_collect",
        "max": max_candidates,
        "phase": report.get("phase") or "running",
        "candidates": report.get("candidates", 0),
        "enqueued": report.get("enqueued", 0),
        "processed": report.get("processed", 0),
        "inserted": report.get("inserted", 0),
        "inserted_rejected": report.get("inserted_rejected", 0),
        "gate_rejected": gate_rejected,
        "skipped": skipped,
        "failed": failed,
        "results": results,
        "candidates_file": report.get("candidates_file"),
    }


def _publish_collect_progress(partial: dict[str, Any], *, max_candidates: int) -> None:
    summary = _summarize_collect_report(partial, max_candidates=max_candidates)
    with _COLLECT_LOCK:
        if _COLLECT_STATE.get("status") != "running":
            return
        _COLLECT_STATE.update(
            {
                **summary,
                "status": "running",
                "error": None,
            }
        )


def _run_recovery_drain_job(pending_count: int) -> None:
    """仅 drain 队列（服务重启恢复用）。"""
    from app.repositories.database import get_app

    with get_app().app_context():
        try:
            _ensure_schema()

            def _on_progress(partial: dict[str, Any]) -> None:
                summary = _summarize_collect_report(
                    {
                        **partial,
                        "phase": "process",
                        "candidates": pending_count,
                        "enqueued": pending_count,
                    },
                    max_candidates=pending_count,
                )
                with _COLLECT_LOCK:
                    if _COLLECT_STATE.get("status") != "running":
                        return
                    _COLLECT_STATE.update(
                        {
                            **summary,
                            "status": "running",
                            "recovered": True,
                            "error": None,
                        }
                    )

            report = drain_pending_stories(
                skip_transcript=False,
                dry_run=False,
                on_progress=_on_progress,
            )
            summary = _summarize_collect_report(
                {
                    **report,
                    "phase": "done",
                    "candidates": pending_count,
                    "enqueued": pending_count,
                },
                max_candidates=pending_count,
            )
            with _COLLECT_LOCK:
                _COLLECT_STATE.update(
                    {
                        **summary,
                        "status": "done",
                        "recovered": True,
                        "error": None,
                        "finished_at": time.time(),
                    }
                )
            logger.info(
                "[GOLD_CHAT] recovery drain done pending=%d processed=%s inserted=%s failed=%s",
                pending_count,
                summary.get("processed"),
                summary.get("inserted"),
                summary.get("failed"),
            )
        except Exception as exc:
            logger.exception(
                "[GOLD_CHAT] recovery drain failed pending=%d",
                pending_count,
            )
            with _COLLECT_LOCK:
                _COLLECT_STATE.update(
                    {
                        "status": "error",
                        "recovered": True,
                        "error": str(exc),
                        "finished_at": time.time(),
                    }
                )


def _run_collect_job(max_candidates: int) -> None:
    from app.repositories.database import get_app

    with get_app().app_context():
        try:
            _ensure_schema()
            report = run_collect_pipeline(
                max_candidates=max_candidates,
                skip_transcript=False,
                dry_run=False,
                write_list=True,
                on_progress=lambda p: _publish_collect_progress(
                    p, max_candidates=max_candidates
                ),
            )
            summary = _summarize_collect_report(
                report,
                max_candidates=max_candidates,
            )
            with _COLLECT_LOCK:
                _COLLECT_STATE.update(
                    {
                        **summary,
                        "status": "done",
                        "error": None,
                        "finished_at": time.time(),
                    }
                )
            logger.info(
                "[GOLD_CHAT] collect done max=%d enqueued=%s inserted=%s failed=%s",
                max_candidates,
                summary.get("enqueued"),
                summary.get("inserted"),
                summary.get("failed"),
            )
        except Exception as exc:
            logger.exception("[GOLD_CHAT] collect failed max=%d", max_candidates)
            with _COLLECT_LOCK:
                _COLLECT_STATE.update(
                    {
                        "status": "error",
                        "error": str(exc),
                        "finished_at": time.time(),
                    }
                )


def _run_reimport_job(
    gold_story_ids: list[int],
    source_ids: list[str],
    force_transcript: bool,
) -> None:
    from app.repositories.database import get_app

    with get_app().app_context():
        try:
            _ensure_schema()
            report = reimport_stories(
                gold_story_ids=gold_story_ids or None,
                source_ids=source_ids or None,
                force_transcript=force_transcript,
            )
            with _REIMPORT_LOCK:
                _REIMPORT_STATE.update(
                    {
                        "workflow": "gold_story_reimport",
                        **report,
                        "status": "done",
                        "error": None,
                        "finished_at": time.time(),
                    }
                )
            logger.info(
                "[GOLD_CHAT] reimport done requested=%s ok=%s failed=%s",
                report.get("requested"),
                report.get("ok"),
                report.get("failed"),
            )
        except Exception as exc:
            logger.exception("[GOLD_CHAT] reimport failed")
            with _REIMPORT_LOCK:
                _REIMPORT_STATE.update(
                    {
                        "status": "error",
                        "error": str(exc),
                        "finished_at": time.time(),
                    }
                )


def _row_to_list_item(row: dict[str, Any], *, config: Config) -> dict[str, Any]:
    sid = str(row.get("source_id") or "").strip()
    payload = cast(dict[str, Any], row.get("payload") or {})
    summary = gold_chat_summary(sid, config=config, row=row)
    bili_title = payload.get("bili_title")
    return {
        "id": row.get("id"),
        "source_id": sid,
        "url": payload.get("bili_url") or row.get("url"),
        "title": row.get("title"),
        "bili_title": bili_title,
        "status": row.get("status"),
        "mechanism": row.get("mechanism"),
        "structure_type": row.get("structure_type"),
        "conflict_core": row.get("conflict_core"),
        "auto_score": row.get("auto_score"),
        "gold_chat_daily_story_id": row.get("gold_chat_daily_story_id"),
        "updated_at": row.get("updated_at"),
        **summary,
    }


def _row_to_dump(row: dict[str, Any]) -> dict[str, Any]:
    """金故事 dump（story_raw + 结构化抽取）。"""
    payload = cast(dict[str, Any], row.get("payload") or {})
    dump: dict[str, Any] = {}
    for key in (
        "story_raw",
        "perspective",
        "funny_why",
        "beat",
        "banned_literals",
        "dialogue_seed",
        "setting",
        "closing_intent",
        "speaker_map_note",
        "scene_contract",
        "source_type",
    ):
        val = payload.get(key)
        if val not in (None, "", [], {}):
            dump[key] = val
    story_raw = str(row.get("story_raw") or payload.get("story_raw") or "").strip()
    if story_raw:
        dump["story_raw"] = story_raw
    transcript_path = row.get("transcript_path")
    if transcript_path:
        dump["transcript_path"] = transcript_path
    return dump


def _row_to_audit_summary(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    """详情 API 用：从 payload.audit 提取可展示的机审摘要。"""
    if not isinstance(payload, dict):
        return None
    audit = payload.get("audit")
    if not isinstance(audit, dict):
        return None
    reasons_raw = audit.get("reject_reasons") or audit.get("rule_reasons") or []
    reasons = [str(r).strip() for r in reasons_raw if str(r).strip()]
    llm_raw = audit.get("llm")
    llm = llm_raw if isinstance(llm_raw, dict) else {}
    note = str(llm.get("audit_notes") or "").strip()
    stage = str(audit.get("stage") or "").strip() or None
    passed = audit.get("pass")
    scores: dict[str, Any] = {}
    for key in ("sibling_fit", "age_fit", "conflict_usable", "mapping_fit"):
        val = llm.get(key)
        if val is not None:
            scores[key] = val
    if passed is None and not reasons and not note and not stage:
        return None
    summary: dict[str, Any] = {}
    if passed is not None:
        summary["pass"] = bool(passed)
    if stage:
        summary["stage"] = stage
    if reasons:
        summary["reject_reasons"] = reasons
    if note:
        summary["audit_notes"] = note
    if scores:
        summary["llm_scores"] = scores
    return summary or None


def _row_to_detail_header(row: dict[str, Any]) -> dict[str, Any]:
    raw_payload = row.get("payload")
    payload: dict[str, Any] = raw_payload if isinstance(raw_payload, dict) else {}
    sid = str(row.get("source_id") or "").strip()
    out = {
        "id": row.get("id"),
        "source_id": sid,
        "url": payload.get("bili_url") or row.get("url"),
        "title": row.get("title"),
        "bili_title": payload.get("bili_title"),
        "status": row.get("status"),
        "mechanism": row.get("mechanism"),
        "structure_type": row.get("structure_type"),
        "conflict_core": row.get("conflict_core"),
        "auto_score": row.get("auto_score"),
        "gold_chat_daily_story_id": row.get("gold_chat_daily_story_id"),
    }
    audit = _row_to_audit_summary(payload)
    if audit is not None:
        out["audit"] = audit
    return out


class GoldStoryMgr:
    def list_items(
        self,
        *,
        status: str | None = None,
        has_story: bool | None = None,
        exclude_rejected: bool = False,
        limit: int = 15,
        offset: int = 0,
    ) -> dict[str, Any]:
        _ensure_schema()
        cfg = Config()
        limit = max(1, min(limit, 200))
        offset = max(0, offset)
        rows = repo_gold_story.list_stories(
            status=status or None,
            has_story=has_story,
            exclude_rejected=exclude_rejected,
            limit=limit,
            offset=offset,
        )
        total = repo_gold_story.count_stories(
            status=status or None,
            has_story=has_story,
            exclude_rejected=exclude_rejected,
        )
        items = [_row_to_list_item(row, config=cfg) for row in rows]
        return {"items": items, "total": total, "limit": limit, "offset": offset}

    def get_chat(
        self,
        *,
        gold_story_id: int | None = None,
        source_id: str | None = None,
    ) -> dict[str, Any]:
        _ensure_schema()
        cfg = Config()
        row: dict[str, Any] | None = None
        if gold_story_id is not None:
            row = repo_gold_story.get_story(int(gold_story_id))
            source_id = str(row.get("source_id") or "").strip()
        elif source_id:
            row = repo_gold_story.get_by_source_id(source_id=str(source_id).strip())
        else:
            raise ValueError("id 或 source_id 必填")

        if row is None:
            raise KeyError("金故事不存在")
        if not source_id:
            raise KeyError("gold_story missing source_id")

        payload = cast(dict[str, Any], row.get("payload") or {})
        export = load_gold_chat_for_row(row, config=cfg)
        gold_chat: dict[str, Any] | None = None
        has_gold_chat = export is not None

        if export is not None:
            gold_chat = {
                "chat_chars": export.get("chat_chars"),
                "chat_lines": export.get("chat_lines"),
                "exported_at": export.get("exported_at"),
                "daily_story": export.get("daily_story"),
                "gold_meta": export.get("gold_meta"),
            }
        elif payload.get("gold_chat_exported_at"):
            gold_chat = {
                "export_missing": True,
                "exported_at": payload.get("gold_chat_exported_at"),
                "chat_chars": payload.get("gold_chat_chars"),
                "chat_lines": payload.get("gold_chat_lines"),
                "scene_title": payload.get("gold_chat_scene_title"),
            }

        gold_chat_error = gold_chat_error_from_payload(payload)
        out = {
            **_row_to_detail_header(row),
            "dump": _row_to_dump(row),
            "has_gold_chat": has_gold_chat,
            "gold_chat": gold_chat,
        }
        if gold_chat_error is not None:
            out["gold_chat_error"] = gold_chat_error
        return out

    def get_transcript(
        self,
        *,
        gold_story_id: int | None = None,
        source_id: str | None = None,
    ) -> dict[str, Any]:
        _ensure_schema()
        cfg = Config()
        row: dict[str, Any] | None = None
        if gold_story_id is not None:
            row = repo_gold_story.get_story(int(gold_story_id))
        elif source_id:
            row = repo_gold_story.get_by_source_id(source_id=str(source_id).strip())
        else:
            raise ValueError("id 或 source_id 必填")

        if row is None:
            raise KeyError("金故事不存在")

        return load_transcript_for_row(row, config=cfg)

    def convert_one(
        self,
        *,
        gold_story_id: int | None = None,
        source_id: str | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        _ensure_schema()
        cfg = Config()
        row: dict[str, Any] | None = None
        if gold_story_id is not None:
            row = repo_gold_story.get_story(int(gold_story_id))
        elif source_id:
            row = repo_gold_story.get_by_source_id(source_id=str(source_id).strip())
        else:
            raise ValueError("id 或 source_id 必填")

        if row is None:
            raise KeyError("金故事不存在")

        sid = str(row.get("source_id") or "").strip()
        if not force and gold_chat_summary(sid, config=cfg).get("has_gold_chat"):
            export = load_gold_chat(sid, config=cfg)
            return {
                "action": "skip",
                "reason": "already_exported",
                "source_id": sid,
                "gold_story_id": row.get("id"),
                "export": export,
            }

        logger.info(
            "[GOLD_CHAT] convert_one start id=%s source_id=%s force=%s",
            gold_story_id,
            source_id,
            force,
        )
        # 非阻塞：busy 立刻 409，避免第二路 convert 在 hub 上死等
        if not _CONVERT_LOCK.acquire(blocking=False):
            raise RuntimeError("转换进行中")
        try:
            outcome = convert_gold_chat(row, config=cfg)
            logger.info(
                "[GOLD_CHAT] convert_one ok source_id=%s lines=%s chars=%s score=%s",
                sid,
                outcome.get("chat_lines"),
                outcome.get("chat_chars"),
                outcome.get("structure_score"),
            )
            return {"action": "ok", **outcome}
        except ValueError as exc:
            gid = int(row.get("id") or 0)
            if gid > 0:
                record_gold_chat_failure(
                    gid,
                    exc,
                    source_id=sid,
                    stage="convert",
                )
            raise
        except Exception as exc:
            gid = int(row.get("id") or 0)
            if gid > 0:
                record_gold_chat_failure(
                    gid,
                    exc,
                    source_id=sid,
                    stage="convert",
                )
            logger.exception("[GOLD_CHAT] convert_one failed source_id=%s: %s", sid, exc)
            raise
        finally:
            _CONVERT_LOCK.release()

    def resolve_story_block(
        self,
        *,
        theme: str,
        story_type: str | None,
        theme_family: str | None = None,
        config: Config | None = None,
    ) -> tuple[str, dict[str, Any] | None]:
        from app.services.daily_story.gold_story.story_block import (
            resolve_gold_story_block,
        )

        return resolve_gold_story_block(
            theme=theme,
            story_type=story_type,
            theme_family=theme_family,
            config=config,
        )

    def build_story_block(self, story: dict[str, Any]) -> str:
        from app.services.daily_story.gold_story.story_block import (
            build_gold_story_block,
        )

        return build_gold_story_block(story)

    def import_one(
        self,
        *,
        gold_story_id: int | None = None,
        source_id: str | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        _ensure_schema()
        cfg = Config()
        row: dict[str, Any] | None = None
        if gold_story_id is not None:
            row = repo_gold_story.get_story(int(gold_story_id))
        elif source_id:
            row = repo_gold_story.get_by_source_id(source_id=str(source_id).strip())
        else:
            raise ValueError("id 或 source_id 必填")

        if row is None:
            raise KeyError("金故事不存在")

        return import_gold_chat_daily_story(row, config=cfg, force=force)

    def batch_convert(
        self,
        *,
        max_items: int = 10,
        status: str = "active",
        gold_story_ids: list[int] | None = None,
        source_ids: list[str] | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        if not _CONVERT_LOCK.acquire(blocking=False):
            raise RuntimeError("转换进行中")
        try:
            return run_gold_chat_batch(
                max_items=max_items,
                status=status,
                gold_story_ids=gold_story_ids,
                source_ids=source_ids,
                skip_existing=not force,
            )
        finally:
            _CONVERT_LOCK.release()

    def collect(
        self,
        *,
        max_candidates: int = 10,
    ) -> dict[str, Any]:
        """H0–H4：排队后台采集，立刻返回 running。"""
        max_candidates = max(1, min(int(max_candidates), 50))
        with _COLLECT_LOCK:
            if _COLLECT_STATE.get("status") == "running":
                raise RuntimeError("采集进行中")
            _COLLECT_STATE.clear()
            _COLLECT_STATE.update(
                {
                    "workflow": "gold_story_collect",
                    "status": "running",
                    "max": max_candidates,
                    "phase": "enqueue",
                    "started_at": time.time(),
                    "candidates": 0,
                    "enqueued": 0,
                    "processed": 0,
                    "inserted": 0,
                    "inserted_rejected": 0,
                    "skipped": 0,
                    "failed": 0,
                    "results": [],
                    "error": None,
                }
            )
            snapshot = dict(_COLLECT_STATE)
        run_in_os_thread(lambda n=max_candidates: _run_collect_job(n))
        logger.info("[GOLD_CHAT] collect queued max=%d", max_candidates)
        return snapshot

    def collect_status(self) -> dict[str, Any]:
        return _collect_snapshot()

    def recover_stuck_pending_stories(self) -> int:
        """服务重启后恢复卡在 pending/processing 的采集入库队列。"""
        _ensure_schema()
        reset_count = repo_gold_story.reset_processing_to_pending()
        pending_count = repo_gold_story.count_stories(status="pending")
        if pending_count <= 0:
            if reset_count:
                logger.info(
                    "[GOLD_CHAT] reset %d processing row(s), no pending left",
                    reset_count,
                )
            else:
                logger.info("[GOLD_CHAT] no stuck pending gold stories to recover")
            return 0

        with _COLLECT_LOCK:
            if _COLLECT_STATE.get("status") == "running":
                logger.warning(
                    "[GOLD_CHAT] recovery skipped: collect drain already running"
                )
                return 0
            _COLLECT_STATE.clear()
            _COLLECT_STATE.update(
                {
                    "workflow": "gold_story_collect",
                    "status": "running",
                    "recovered": True,
                    "phase": "process",
                    "max": pending_count,
                    "started_at": time.time(),
                    "candidates": pending_count,
                    "enqueued": pending_count,
                    "processed": 0,
                    "inserted": 0,
                    "inserted_rejected": 0,
                    "gate_rejected": 0,
                    "skipped": 0,
                    "failed": 0,
                    "results": [],
                    "error": None,
                }
            )

        run_in_os_thread(lambda n=pending_count: _run_recovery_drain_job(n))
        logger.warning(
            "[GOLD_CHAT] recovering %d pending gold story/stories "
            "(reset %d processing)",
            pending_count,
            reset_count,
        )
        return pending_count

    def reimport(
        self,
        *,
        gold_story_ids: list[int] | None = None,
        source_ids: list[str] | None = None,
        force_transcript: bool = True,
    ) -> dict[str, Any]:
        """从 BV 后台重跑 H0b–H4，立刻返回 running。"""
        ids = sorted({int(x) for x in (gold_story_ids or []) if int(x) > 0})
        bvs: list[str] = []
        seen: set[str] = set()
        for raw in source_ids or []:
            text = str(raw or "").strip()
            if not text or text in seen:
                continue
            seen.add(text)
            bvs.append(text)
        if not ids and not bvs:
            raise ValueError("ids 或 source_id 必填")
        if len(ids) + len(bvs) > 20:
            raise ValueError("一次最多重新导入 20 条")

        with _REIMPORT_LOCK:
            if _REIMPORT_STATE.get("status") == "running":
                raise RuntimeError("重新导入进行中")
            _REIMPORT_STATE.clear()
            _REIMPORT_STATE.update(
                {
                    "workflow": "gold_story_reimport",
                    "status": "running",
                    "ids": ids,
                    "source_ids": bvs,
                    "force_transcript": bool(force_transcript),
                    "started_at": time.time(),
                    "requested": 0,
                    "updated": 0,
                    "inserted": 0,
                    "rejected": 0,
                    "failed": 0,
                    "ok": 0,
                    "results": [],
                    "error": None,
                }
            )
            snapshot = dict(_REIMPORT_STATE)
        run_in_os_thread(
            lambda: _run_reimport_job(ids, bvs, bool(force_transcript)),
        )
        logger.info(
            "[GOLD_CHAT] reimport queued ids=%s source_ids=%s force_transcript=%s",
            ids,
            bvs,
            force_transcript,
        )
        return snapshot

    def reimport_status(self) -> dict[str, Any]:
        return _reimport_snapshot()

    def reject_stories(self, gold_story_ids: list[int]) -> dict[str, Any]:
        """人工驳回：仅改 status=rejected，不删文件。"""
        _ensure_schema()
        ids = sorted({int(x) for x in gold_story_ids if int(x) > 0})
        if not ids:
            raise ValueError("ids 不能为空")
        ok_ids: list[int] = []
        skipped: list[int] = []
        results: list[dict[str, Any]] = []
        for gid in ids:
            try:
                row = repo_gold_story.get_story(gid)
            except KeyError:
                results.append({"id": gid, "action": "error", "error": "not_found"})
                continue
            sid = str(row.get("source_id") or "").strip()
            old = str(row.get("status") or "").strip()
            if old == "rejected":
                skipped.append(gid)
                results.append(
                    {
                        "id": gid,
                        "source_id": sid,
                        "action": "skip",
                        "reason": "already_rejected",
                    }
                )
                continue
            repo_gold_story.update_story_status(
                gid,
                status="rejected",
                audit={
                    "pass": False,
                    "stage": "manual",
                    "reject_reasons": ["manual_reject"],
                    "prev_status": old or None,
                },
            )
            ok_ids.append(gid)
            results.append(
                {
                    "id": gid,
                    "source_id": sid,
                    "action": "ok",
                    "status": "rejected",
                    "prev_status": old or None,
                }
            )
        return {
            "rejected": len(ok_ids),
            "skipped": len(skipped),
            "ids": ok_ids,
            "results": results,
        }

    def delete_stories(self, gold_story_ids: list[int]) -> dict[str, Any]:
        _ensure_schema()
        cfg = Config()
        ids = sorted({int(x) for x in gold_story_ids if int(x) > 0})
        if not ids:
            raise ValueError("ids 不能为空")
        ok_ids: list[int] = []
        results: list[dict[str, Any]] = []
        files_removed = 0
        for gid in ids:
            try:
                row = repo_gold_story.get_story(gid)
            except KeyError:
                results.append({"id": gid, "action": "error", "error": "not_found"})
                continue
            sid = str(row.get("source_id") or "").strip()
            files_removed += len(cleanup_gold_story_files(sid, config=cfg))
            ok_ids.append(gid)
            results.append({"id": gid, "source_id": sid, "action": "ok"})
        deleted = repo_gold_story.delete_stories_by_ids(ok_ids) if ok_ids else 0
        return {
            "deleted": deleted,
            "ids": ok_ids,
            "results": results,
            "files_removed": files_removed,
        }


gold_story_mgr = GoldStoryMgr()
