"""H0–H4 金故事采集编排。"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from app.config import Config
from app.repositories import repo_gold_story
from app.services.daily_story.gold_story.collect import llm as llm_steps
from app.services.daily_story.gold_story.collect import review as gs_review
from app.services.daily_story.gold_story.collect.funny import (
    compute_audience_funny_metrics,
    metrics_to_payload,
    passes_funny_gate_from_payload,
)
from app.services.daily_story.gold_story.collect.search import (
    VideoCandidate,
    _bili_http,
    collect_candidates,
    engagement_norm,
    fetch_top_replies,
    fetch_video_meta,
    write_candidate_list,
)
from app.services.daily_story.gold_story.export_story import export_story_files
from app.services.daily_story.gold_story.scene import sanitize_banned_literals
from app.services.daily_story.gold_story.transcript import (
    repaired_transcript_path,
    save_repaired_transcript,
    transcribe_bilibili,
)
from app.services.daily_story.gold_story.transcript.download import normalize_bv

logger = logging.getLogger(__name__)


def _read_transcript(path: Path) -> str:
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8").strip()


def _existing_source(source: str, source_id: str) -> bool:
    return repo_gold_story.has_source(source=source, source_id=source_id)


def process_candidate(
    candidate: VideoCandidate,
    *,
    config: Config | None = None,
    skip_transcript: bool = False,
    dry_run: bool = False,
    overwrite_existing: bool = False,
    force_transcript: bool = False,
    existing_row: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """单条 BV：H0b → H0c → H2 → H3 → H3a → H3b → H4a → H4。

    overwrite_existing=True 时走已入库回写，不插入新行。
    """
    cfg = config or Config()
    base: dict[str, Any] = {
        "source_id": candidate.source_id,
        "title": candidate.title,
        "keyword": candidate.keyword,
    }

    if existing_row is None and _existing_source(candidate.source, candidate.source_id):
        existing_row = repo_gold_story.get_by_source_id(
            source_id=candidate.source_id,
            source=candidate.source,
        )
    if existing_row and not overwrite_existing:
        return {**base, "action": "skip", "reason": "already_in_db"}

    transcript_path = cfg.gold_story_transcript_dir / f"{candidate.source_id}.txt"
    transcript_text = _read_transcript(transcript_path)
    tx: dict[str, Any] | None = None

    need_transcript = force_transcript or (not transcript_text and not skip_transcript)
    if need_transcript:
        try:
            tx = transcribe_bilibili(
                candidate.source_id,
                config=cfg,
                skip_existing=not force_transcript,
            )
            if tx.get("action") in {"ok", "skip"}:
                transcript_path = Path(str(tx.get("transcript_path") or transcript_path))
                transcript_text = _read_transcript(transcript_path)
            elif overwrite_existing:
                return {**base, "action": "error", "stage": "H0b", "error": tx}
            else:
                return {**base, "action": "error", "stage": "H0b", "error": tx}
        except Exception as exc:
            logger.warning(
                "gold_story H0b failed bvid=%s: %s",
                candidate.source_id,
                exc,
            )
            if overwrite_existing:
                return {**base, "action": "error", "stage": "H0b", "error": str(exc)}
            if not candidate.description and not candidate.top_replies:
                return {**base, "action": "error", "stage": "H0b", "error": str(exc)}

    if overwrite_existing and not transcript_text:
        return {**base, "action": "error", "stage": "H0b", "error": "empty transcript"}

    transcript_for_h2 = transcript_text
    h0c_meta: dict[str, Any] = {}
    if transcript_text and cfg.gold_story_transcript_repair:
        try:
            h0c = llm_steps.repair_transcript(
                title=candidate.title,
                transcript=transcript_text,
                description=candidate.description,
            )
            rep_path = repaired_transcript_path(cfg, candidate.source_id)
            transcript_for_h2 = save_repaired_transcript(rep_path, h0c["lines"])
            h0c_meta = {
                "transcript_repaired_path": str(rep_path),
                "transcript_repair_confidence": h0c.get("repair_confidence"),
                "transcript_speakers": h0c.get("speakers") or [],
                "transcript_repair_notes": h0c.get("repair_notes") or "",
            }
        except Exception as exc:
            logger.warning(
                "gold_story H0c failed bvid=%s: %s",
                candidate.source_id,
                exc,
            )

    if dry_run:
        return {
            **base,
            "action": "dry_run",
            "transcript_chars": len(transcript_text),
            "transcript_repaired_chars": len(transcript_for_h2),
            "reply_count": len(candidate.top_replies),
        }

    try:
        h2 = llm_steps.extract_story_raw(
            title=candidate.title,
            transcript=transcript_for_h2,
            description=candidate.description,
            replies=list(candidate.top_replies),
        )
        story_raw_text = str(h2["story_raw"])
        near = repo_gold_story.find_near_duplicate(story_raw_text)
        self_id = int(existing_row["id"]) if existing_row and existing_row.get("id") else None
        if near and (self_id is None or int(near["id"]) != self_id):
            return {
                **base,
                "action": "skip",
                "reason": "duplicate_similar_story",
                "id": near["id"],
                "similar_source_id": near["source_id"],
                "similar_ratio": near["ratio"],
                "similar_lcs": near["lcs"],
            }
        h3 = llm_steps.structurize_story(
            title=candidate.title,
            story_raw=h2["story_raw"],
        )
        source_type = str(h2.get("source_type") or "field").strip().lower()
        h3a = llm_steps.build_scene_contract(
            story_raw=h2["story_raw"],
            h3=h3,
            source_type=source_type,
        )
        h3b = llm_steps.build_dialogue_seed(
            story_raw=h2["story_raw"],
            h3=h3,
            scene_contract=h3a,
        )
    except ValueError as exc:
        logger.info(
            "gold_story LLM reject bvid=%s reason=%s",
            candidate.source_id,
            exc,
        )
        return {**base, "action": "reject", "reason": str(exc), "stage": "LLM"}
    except Exception as exc:
        return {**base, "action": "error", "stage": "LLM", "error": str(exc)}

    audit = gs_review.audit_story(
        title=str(h3.get("title") or candidate.title),
        video_title=candidate.title,
        story_raw=story_raw_text,
        conflict_core=str(h3.get("conflict_core") or ""),
        transcript=transcript_for_h2,
        description=candidate.description,
        h3=h3,
        h3a=h3a,
        h3b=h3b,
        config=cfg,
    )
    insert_status = "active" if audit.get("pass") else "rejected"

    norm = engagement_norm(candidate.view_count, candidate.reply_count)
    funny_payload = dict(candidate.funny_metrics or {})
    old_payload: dict[str, Any] = {}
    if overwrite_existing and existing_row:
        raw_old = existing_row.get("payload")
        if isinstance(raw_old, dict):
            old_payload = dict(raw_old)
    banned = sanitize_banned_literals(
        h3.get("banned_literals") or h3a.get("banned_literals"),
        scene_contract=h3a,
        beat=h3.get("beat") if isinstance(h3.get("beat"), list) else [],
    )
    payload: dict[str, Any] = {
        **old_payload,
        "perspective": h2.get("perspective"),
        "source_type": source_type,
        "story_raw": story_raw_text,
        "scene_contract": h3a,
        "contract_confidence": h3a.get("contract_confidence"),
        "funny_why": h3.get("funny_why"),
        "beat": h3.get("beat") or [],
        "banned_literals": banned,
        "dialogue_seed": h3b.get("dialogue_seed") or [],
        "closing_intent": h3b.get("closing_intent") or h3a.get("closing_intent"),
        "speaker_map_note": h3b.get("speaker_map_note") or h3a.get("remap_note"),
        "setting": h3b.get("setting") or h3a.get("location"),
        "structure_mapping_note": h3.get("structure_mapping_note"),
        "extract_confidence": h2.get("extract_confidence"),
        "structure_confidence": h3.get("structure_confidence"),
        "dialogue_confidence": h3b.get("dialogue_confidence"),
        "search_keyword": candidate.keyword,
        "engagement_norm": norm,
        "audit": audit,
        **funny_payload,
        **h0c_meta,
    }
    funny_ok, funny_reason = passes_funny_gate_from_payload(payload, level="l2")
    if not funny_ok:
        insert_status = "rejected"
        audit = {
            **audit,
            "pass": False,
            "stage": "funny_signal",
            "reject_reasons": [funny_reason],
        }
        payload["audit"] = audit

    transcript_backend = "faster-whisper"
    if tx:
        transcript_backend = str(
            tx.get("transcript_backend") or tx.get("engine") or "faster-whisper"
        )

    if overwrite_existing and existing_row:
        gid = int(existing_row["id"])
        updated = repo_gold_story.update_story_from_pipeline(
            gid,
            mechanism=str(h3["mechanism"]),
            structure_type=str(h3["structure_type"]),
            title=str(h3.get("title") or candidate.title),
            conflict_core=str(h3.get("conflict_core") or ""),
            story_raw=story_raw_text,
            payload=payload,
            transcript_backend=transcript_backend,
            transcript_path=str(transcript_path) if transcript_text else None,
            engagement_score=float(norm),
            engagement_norm=norm,
            status=insert_status,
        )
        fresh = repo_gold_story.get_story(gid)
        paths = export_story_files(source_id=candidate.source_id, row=fresh, config=cfg)
        action = "ok" if insert_status == "active" else "reject"
        reason = None
        if action == "reject":
            reason = (
                "low_audience_laugh"
                if funny_reason.startswith("low_") or funny_reason == "cute_not_funny"
                else "audit_failed"
            )
        return {
            **base,
            "id": gid,
            "action": action,
            "reason": reason,
            "status": insert_status,
            "audit_pass": audit.get("pass"),
            "audit_reasons": audit.get("reject_reasons") or [],
            "transcript_chars": len(transcript_text),
            "transcript_repaired_chars": len(transcript_for_h2),
            "story_raw_chars": len(story_raw_text),
            "auto_score": updated.get("auto_score"),
            "export": paths,
        }

    result = repo_gold_story.insert_or_skip(
        source=candidate.source,
        source_id=candidate.source_id,
        url=candidate.url,
        mechanism=str(h3["mechanism"]),
        structure_type=str(h3["structure_type"]),
        story_raw=story_raw_text,
        payload=payload,
        title=str(h3.get("title") or candidate.title),
        conflict_core=str(h3.get("conflict_core") or ""),
        theme_family=str(h3.get("theme_family") or "") or None,
        engagement_score=float(norm),
        engagement_norm=norm,
        transcript_backend=transcript_backend,
        transcript_path=str(transcript_path) if transcript_text else None,
        status=insert_status,
    )
    if result.get("action") == "insert" and result.get("id"):
        row = repo_gold_story.get_story(int(result["id"]))
        paths = export_story_files(source_id=candidate.source_id, row=row, config=cfg)
        result["export"] = paths
    action = result.get("action")
    if action == "insert" and insert_status == "rejected":
        result["action"] = "reject"
        result["reason"] = (
            "low_audience_laugh"
            if funny_reason.startswith("low_") or funny_reason == "cute_not_funny"
            else "audit_failed"
        )
        result["audit_reasons"] = audit.get("reject_reasons") or []
    return {**base, **result, "audit_pass": audit.get("pass"), "status": insert_status}


def _build_candidate_from_bvid(
    source_id: str,
    *,
    config: Config,
    existing_row: dict[str, Any] | None = None,
) -> VideoCandidate:
    """拉 B 站元数据 + 热评，拼 H0 候选。已有行时元数据失败可降级。"""
    try:
        meta = fetch_video_meta(source_id, config=config)
        replies = fetch_top_replies(int(meta.get("aid") or 0), config=config, limit=8)
    except Exception as exc:
        if existing_row is None:
            raise
        logger.warning("overwrite meta failed bvid=%s: %s", source_id, exc)
        meta = {
            "title": existing_row.get("title") or source_id,
            "description": "",
            "view_count": 0,
            "reply_count": 0,
            "url": str(existing_row.get("url") or ""),
            "cid": 0,
        }
        replies = []

    http = _bili_http(config)
    funny = compute_audience_funny_metrics(
        source_id=source_id,
        cid=int(meta.get("cid") or 0),
        view_count=int(meta.get("view_count") or 0),
        reply_count=int(meta.get("reply_count") or 0),
        replies=replies,
        session=http,
    )
    source = "bili"
    if existing_row:
        source = str(existing_row.get("source") or "bili")
    return VideoCandidate(
        source=source,
        source_id=source_id,
        url=str(meta.get("url") or (existing_row or {}).get("url") or ""),
        title=str(meta.get("title") or (existing_row or {}).get("title") or ""),
        description=str(meta.get("description") or ""),
        view_count=int(meta.get("view_count") or 0),
        reply_count=int(meta.get("reply_count") or 0),
        keyword="",
        top_replies=tuple(replies),
        cid=int(meta.get("cid") or 0),
        funny_metrics=metrics_to_payload(funny),
    )


def overwrite_existing_story(
    gold_story_id: int,
    *,
    config: Config | None = None,
    force_transcript: bool = True,
) -> dict[str, Any]:
    """已入库条目再跑 H0b–H4，回写同一行。"""
    cfg = config or Config()
    row = repo_gold_story.get_story(int(gold_story_id))
    source_id = str(row.get("source_id") or "").strip()
    base = {
        "id": gold_story_id,
        "source_id": source_id,
        "title": row.get("title"),
    }
    if not source_id:
        return {**base, "action": "error", "error": "missing source_id"}

    candidate = _build_candidate_from_bvid(
        source_id,
        config=cfg,
        existing_row=row,
    )
    outcome = process_candidate(
        candidate,
        config=cfg,
        overwrite_existing=True,
        force_transcript=force_transcript,
        existing_row=row,
    )
    return {**base, **outcome}


def import_or_overwrite_source(
    source_id: str,
    *,
    config: Config | None = None,
    force_transcript: bool = True,
) -> dict[str, Any]:
    """按 BV 导入：已有则覆盖，没有则走 H0b–H4 新入库。"""
    cfg = config or Config()
    try:
        bvid = normalize_bv(source_id)
    except ValueError as exc:
        return {
            "source_id": str(source_id or "").strip(),
            "action": "error",
            "error": str(exc),
        }

    existing = repo_gold_story.get_by_source_id(source_id=bvid)
    if existing:
        return overwrite_existing_story(
            int(existing["id"]),
            config=cfg,
            force_transcript=force_transcript,
        )

    base = {"source_id": bvid}
    try:
        candidate = _build_candidate_from_bvid(bvid, config=cfg)
    except Exception as exc:
        logger.warning("reimport meta failed bvid=%s: %s", bvid, exc)
        return {**base, "action": "error", "stage": "H0", "error": str(exc)}

    outcome = process_candidate(
        candidate,
        config=cfg,
        overwrite_existing=False,
        force_transcript=force_transcript,
    )
    return {**base, **outcome}


def overwrite_existing_stories(
    gold_story_ids: list[int],
    *,
    config: Config | None = None,
    force_transcript: bool = True,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for gid in gold_story_ids:
        try:
            results.append(
                overwrite_existing_story(
                    int(gid),
                    config=config,
                    force_transcript=force_transcript,
                )
            )
        except KeyError:
            results.append(
                {"id": gid, "action": "error", "error": f"gold_story {gid} not found"}
            )
    return results


def reimport_stories(
    *,
    gold_story_ids: list[int] | None = None,
    source_ids: list[str] | None = None,
    force_transcript: bool = True,
    config: Config | None = None,
    on_progress: Any | None = None,
) -> dict[str, Any]:
    """从 BV 重新导入金稿：已有覆盖，没有则新入库。"""
    cfg = config or Config()
    results: list[dict[str, Any]] = []
    seen_ids: set[int] = set()
    seen_bvs: set[str] = set()

    work: list[tuple[str, int | str]] = []
    for gid in gold_story_ids or []:
        work.append(("id", int(gid)))
    for raw in source_ids or []:
        work.append(("bv", str(raw or "").strip()))

    total = len(work)

    def _emit_progress(idx: int, *, processing: tuple[str, int | str] | None) -> None:
        if on_progress is None:
            return
        queued_ids: list[int] = []
        queued_bvs: list[str] = []
        for kind, value in work[idx + 1 :]:
            if kind == "id":
                queued_ids.append(int(value))
            elif kind == "bv" and value:
                queued_bvs.append(str(value))
        proc_id: int | None = None
        proc_bv: str | None = None
        if processing is not None:
            p_kind, p_val = processing
            if p_kind == "id":
                proc_id = int(p_val)
                try:
                    row = repo_gold_story.get_story(proc_id)
                    proc_bv = str(row.get("source_id") or "").strip() or None
                except KeyError:
                    proc_bv = None
            elif p_kind == "bv" and p_val:
                try:
                    proc_bv = normalize_bv(str(p_val))
                except ValueError:
                    proc_bv = str(p_val).strip() or None
        on_progress(
            {
                "processed": idx,
                "requested": total,
                "processing_id": proc_id,
                "processing_source_id": proc_bv,
                "queued_ids": queued_ids,
                "queued_source_ids": queued_bvs,
                "results": list(results),
            }
        )

    for idx, (kind, value) in enumerate(work):
        _emit_progress(idx, processing=(kind, value))
        if kind == "id":
            gid = int(value)
            try:
                outcome = overwrite_existing_story(
                    gid,
                    config=cfg,
                    force_transcript=force_transcript,
                )
            except KeyError:
                outcome = {
                    "id": gid,
                    "action": "error",
                    "error": f"gold_story {gid} not found",
                }
            sid = str(outcome.get("source_id") or "").strip()
            if outcome.get("id"):
                seen_ids.add(int(outcome["id"]))
            if sid:
                seen_bvs.add(sid)
            results.append(outcome)
            continue

        raw = str(value or "").strip()
        if not raw:
            continue
        try:
            bvid = normalize_bv(raw)
        except ValueError as exc:
            results.append(
                {
                    "source_id": raw,
                    "action": "error",
                    "error": str(exc),
                }
            )
            continue
        if bvid in seen_bvs:
            continue
        existing = repo_gold_story.get_by_source_id(source_id=bvid)
        if existing and int(existing["id"]) in seen_ids:
            continue
        outcome = import_or_overwrite_source(
            bvid,
            config=cfg,
            force_transcript=force_transcript,
        )
        if outcome.get("id"):
            seen_ids.add(int(outcome["id"]))
        seen_bvs.add(bvid)
        results.append(outcome)

    updated = sum(1 for r in results if r.get("action") == "ok")
    inserted = sum(1 for r in results if r.get("action") == "insert")
    rejected = sum(1 for r in results if r.get("action") == "reject")
    failed = sum(1 for r in results if r.get("action") == "error")
    return {
        "requested": len(results),
        "updated": updated,
        "inserted": inserted,
        "rejected": rejected,
        "failed": failed,
        "ok": updated + inserted + rejected,
        "results": results,
    }


def enqueue_collect_candidates(
    *,
    config: Config | None = None,
    max_candidates: int | None = None,
    keywords: list[str] | None = None,
    write_list: bool = True,
    on_progress: Any | None = None,
) -> dict[str, Any]:
    """H0/H1：搜索后立刻 pending 入库（不做 OCR）。"""
    from app.repositories.schema import apply_gold_story_schema
    from app.repositories import sql_exec as sql
    from app.repositories.db_obj import db

    conn = db.session.connection().connection.dbapi_connection
    apply_gold_story_schema(conn)  # type: ignore[union-attr]
    sql.commit()

    cfg = config or Config()
    candidates = collect_candidates(
        config=cfg,
        max_candidates=max_candidates,
        keywords=keywords,
    )
    if write_list:
        write_candidate_list(candidates, cfg.gold_story_candidates_file)

    results: list[dict[str, Any]] = []
    enqueued = 0
    skipped = 0

    def _snapshot() -> dict[str, Any]:
        return {
            "phase": "enqueue",
            "candidates": len(candidates),
            "enqueued": enqueued,
            "skipped": skipped,
            "processed": 0,
            "inserted": 0,
            "inserted_rejected": 0,
            "gate_rejected": 0,
            "results": list(results),
            "candidates_file": str(cfg.gold_story_candidates_file),
        }

    if on_progress is not None:
        try:
            on_progress(_snapshot())
        except Exception:
            logger.exception("gold_story enqueue on_progress failed")

    for row in candidates:
        payload = {
            "bili_title": row.title,
            "search_keyword": row.keyword,
            "pipeline_stage": "queued",
            **(row.funny_metrics or {}),
        }
        try:
            outcome = repo_gold_story.insert_pending(
                source=row.source,
                source_id=row.source_id,
                url=row.url,
                title=row.title,
                engagement_score=float(engagement_norm(row.view_count, row.reply_count)),
                payload=payload,
            )
        except Exception as exc:
            logger.exception("gold_story enqueue failed bvid=%s", row.source_id)
            outcome = {
                "source_id": row.source_id,
                "title": row.title,
                "action": "error",
                "error": str(exc),
            }
            results.append(outcome)
            if on_progress is not None:
                try:
                    on_progress(_snapshot())
                except Exception:
                    logger.exception("gold_story enqueue on_progress failed")
            continue

        item = {
            "source_id": row.source_id,
            "title": row.title,
            "keyword": row.keyword,
            **outcome,
        }
        results.append(item)
        if outcome.get("action") == "insert":
            enqueued += 1
        else:
            skipped += 1
        if on_progress is not None:
            try:
                on_progress(_snapshot())
            except Exception:
                logger.exception("gold_story enqueue on_progress failed")

    return _snapshot()


def _finalize_pending_failure(
    gold_story_id: int,
    *,
    reason: str,
    stage: str = "pipeline",
) -> None:
    repo_gold_story.update_story_status(
        int(gold_story_id),
        status="rejected",
        audit={
            "pass": False,
            "stage": stage,
            "reject_reasons": [reason],
        },
    )


def drain_pending_stories(
    *,
    config: Config | None = None,
    skip_transcript: bool = False,
    force_transcript: bool = True,
    dry_run: bool = False,
    limit: int | None = None,
    on_progress: Any | None = None,
) -> dict[str, Any]:
    """异步队列：pending → OCR/H0c/H2–H4 → active|rejected。"""
    cfg = config or Config()
    results: list[dict[str, Any]] = []
    inserted_active = 0
    inserted_rejected = 0
    gate_rejected = 0
    failed = 0
    processed = 0

    def _snapshot() -> dict[str, Any]:
        return {
            "phase": "process",
            "processed": processed,
            "inserted": inserted_active,
            "inserted_rejected": inserted_rejected,
            "gate_rejected": gate_rejected,
            "failed": failed,
            "results": list(results),
        }

    while True:
        if limit is not None and processed >= max(0, int(limit)):
            break
        row = repo_gold_story.claim_next_pending()
        if row is None:
            break
        gid = int(row["id"])
        source_id = str(row.get("source_id") or "")
        if dry_run:
            repo_gold_story.update_story_status(gid, status="pending")
            results.append(
                {
                    "id": gid,
                    "source_id": source_id,
                    "action": "dry_run",
                }
            )
            processed += 1
            continue

        try:
            candidate = _build_candidate_from_bvid(
                source_id,
                config=cfg,
                existing_row=row,
            )
            outcome = process_candidate(
                candidate,
                config=cfg,
                skip_transcript=skip_transcript,
                overwrite_existing=True,
                # 有稿则复用；无稿才转写（不必 force 重跑）
                force_transcript=False,
                existing_row=row,
            )
        except Exception as exc:
            logger.exception("gold_story drain failed id=%s bv=%s", gid, source_id)
            _finalize_pending_failure(gid, reason=str(exc), stage="drain")
            outcome = {
                "id": gid,
                "source_id": source_id,
                "action": "error",
                "error": str(exc),
            }
            failed += 1
            results.append(outcome)
            processed += 1
            if on_progress is not None:
                try:
                    on_progress(_snapshot())
                except Exception:
                    logger.exception("gold_story drain on_progress failed")
            continue

        action = str(outcome.get("action") or "")
        status = str(outcome.get("status") or "")
        # 早退（OCR/LLM 软拒）未回写 status 时，收口为 rejected
        if action in {"error", "reject", "skip"} and status not in {"active", "rejected"}:
            reason = str(
                outcome.get("reason")
                or outcome.get("error")
                or action
            )
            _finalize_pending_failure(
                gid,
                reason=reason,
                stage=str(outcome.get("stage") or action),
            )
            outcome = {**outcome, "status": "rejected", "id": gid}
            if action == "error":
                failed += 1
            else:
                gate_rejected += 1
        elif action == "ok" or status == "active":
            inserted_active += 1
        elif action == "reject" or status == "rejected":
            inserted_rejected += 1

        results.append(outcome)
        processed += 1
        if on_progress is not None:
            try:
                on_progress(_snapshot())
            except Exception:
                logger.exception("gold_story drain on_progress failed")

    return _snapshot()


def run_collect_pipeline(
    *,
    config: Config | None = None,
    max_candidates: int | None = None,
    keywords: list[str] | None = None,
    skip_transcript: bool = False,
    dry_run: bool = False,
    write_list: bool = True,
    on_progress: Any | None = None,
) -> dict[str, Any]:
    """H0/H1 先 pending 入库，再异步队列跑 OCR→结构化。"""
    cfg = config or Config()

    def _emit(partial: dict[str, Any]) -> None:
        if on_progress is None:
            return
        try:
            on_progress(partial)
        except Exception:
            logger.exception("gold_story collect on_progress failed")

    enq = enqueue_collect_candidates(
        config=cfg,
        max_candidates=max_candidates,
        keywords=keywords,
        write_list=write_list,
        on_progress=on_progress,
    )
    _emit({**enq, "phase": "enqueued"})

    if dry_run:
        return {
            **enq,
            "phase": "done",
            "processed": 0,
            "inserted": 0,
            "inserted_rejected": 0,
            "gate_rejected": 0,
        }

    drain = drain_pending_stories(
        config=cfg,
        skip_transcript=skip_transcript,
        force_transcript=not skip_transcript,
        dry_run=False,
        on_progress=on_progress,
    )
    return {
        "phase": "done",
        "candidates": enq.get("candidates", 0),
        "enqueued": enq.get("enqueued", 0),
        "skipped": enq.get("skipped", 0),
        "processed": drain.get("processed", 0),
        "inserted": drain.get("inserted", 0),
        "inserted_rejected": drain.get("inserted_rejected", 0),
        "gate_rejected": drain.get("gate_rejected", 0),
        "failed": drain.get("failed", 0),
        "results": list(enq.get("results") or []) + list(drain.get("results") or []),
        "candidates_file": enq.get("candidates_file"),
    }
