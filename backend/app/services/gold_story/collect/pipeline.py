"""H0–H4 金故事采集编排。"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

import requests

from app.config import Config
from app.repositories import repo_gold_story
from app.services.gold_story.collect import llm as llm_steps
from app.services.gold_story.collect import review as gs_review
from app.services.gold_story.collect.funny import (
    audit_with_funny_rejection,
    compute_audience_funny_metrics,
    metrics_to_payload,
    passes_funny_gate_from_payload,
)
from app.services.gold_story.collect.search import (
    VideoCandidate,
    _bili_http,
    collect_candidates,
    engagement_norm,
    fetch_top_replies,
    fetch_video_meta,
    title_reject_reason,
    write_candidate_list,
)
from app.services.gold_story.export_story import export_story_files
from app.services.gold_story.scene import sanitize_banned_literals
from app.services.gold_story.structure_resolve import sync_h3_from_scene_contract
from app.services.gold_story.transcript import (
    repaired_transcript_path,
    save_repaired_transcript,
    format_dialogue_transcript,
    transcribe_bilibili,
)
from app.services.gold_story.transcript.download import VideoTooLongError, normalize_bv

logger = logging.getLogger(__name__)

_COLLECT_MAX_ATTEMPTS = 3


def _execution_failure(exc: Exception, stage: str) -> dict[str, Any]:
    """网络临时故障和模型输出错误可重试；程序错误不能当内容驳回。"""
    retryable = isinstance(exc, llm_steps.ModelOutputError)
    cause: BaseException | None = exc
    seen: set[int] = set()
    while cause is not None and id(cause) not in seen:
        seen.add(id(cause))
        code = getattr(cause, "status_code", None)
        response = getattr(cause, "response", None)
        if code is None and response is not None:
            code = getattr(response, "status_code", None)
        retryable |= isinstance(cause, (TimeoutError, ConnectionError, requests.Timeout, requests.ConnectionError))
        retryable |= isinstance(code, int) and (code == 429 or 500 <= code < 600)
        cause = cause.__cause__
    return {"action": "error", "stage": stage, "error": str(exc), "retryable": retryable}


def _read_transcript(path: Path) -> str:
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8").strip()


def _existing_source(source: str, source_id: str) -> bool:
    return repo_gold_story.has_source(source=source, source_id=source_id)


def _export_collection_result(row: dict[str, Any], config: Config) -> dict[str, Any]:
    """入库已经提交；导出失败须单独报告，不能重跑生成或伪装成并发跳过。"""
    try:
        return {"export": export_story_files(source_id=str(row["source_id"]), row=row, config=config)}
    except Exception as exc:
        logger.warning("gold_story export failed id=%s: %s", row["id"], exc)
        return {"action": "error", "stage": "export", "error": str(exc),
                "retryable": False, "persisted": True}


def process_candidate(
    candidate: VideoCandidate,
    *,
    config: Config | None = None,
    skip_transcript: bool = False,
    dry_run: bool = False,
    overwrite_existing: bool = False,
    force_transcript: bool = False,
    existing_row: dict[str, Any] | None = None,
    repair_feedback: str = "",
    resolution_cache: dict[str, Any] | None = None,
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
    if existing_row:
        from app.services.gold_story.gold_chat.status import gold_chat_converting_from_payload
        if gold_chat_converting_from_payload(existing_row.get("payload") or {}):
            return {**base, "action": "error", "stage": "reimport", "error": "对话转换进行中，不能重导素材", "retryable": False}

    if dry_run:
        return {**base, "action": "dry_run"}

    # H1 标题门控：孕产/分娩、育儿课、游戏 IP 这类题材，标题就能判死。
    # 队列里早已入队（或手工重导）的 BV 也走这里，避免继续白下载+转写。
    title_reason = title_reject_reason(candidate.title)
    if title_reason and title_reason != "empty_title":
        logger.info(
            "gold_story h1 skip bvid=%s reason=%s title=%r",
            candidate.source_id,
            title_reason,
            candidate.title[:40],
        )
        return {
            **base,
            "action": "reject",
            "stage": "H1",
            "reason": title_reason,
        }

    # H1 时长门控：合集/直播回放（如 7 小时)转写要几小时，且抽不出单条故事。
    # 放在 H0b 之前，避免白下载、白抽帧、白跑 ASR。
    max_duration = int(getattr(cfg, "gold_story_max_duration_sec", 0) or 0)
    duration_sec = int(candidate.duration_sec or 0)
    if max_duration > 0 and duration_sec > max_duration:
        logger.info(
            "gold_story h1 skip bvid=%s reason=too_long duration=%ss max=%ss title=%r",
            candidate.source_id,
            duration_sec,
            max_duration,
            candidate.title[:40],
        )
        return {
            **base,
            "action": "reject",
            "stage": "H1",
            "reason": "too_long",
            "duration_sec": duration_sec,
        }

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
            else:
                return {**base, "action": "error", "stage": "H0b", "error": tx, "retryable": False}
        except VideoTooLongError as exc:
            logger.info(
                "gold_story h0b skip bvid=%s reason=too_long: %s",
                candidate.source_id,
                exc,
            )
            return {
                **base,
                "action": "reject",
                "stage": "H0b",
                "reason": "too_long",
                "error": str(exc),
            }
        except Exception as exc:
            logger.warning(
                "gold_story H0b failed bvid=%s: %s",
                candidate.source_id,
                exc,
            )
            return {**base, **_execution_failure(exc, "H0b")}

    if not transcript_text:
        return {**base, "action": "reject", "stage": "H0b", "reason": "source_unusable:empty_transcript"}

    transcript_for_h2 = transcript_text
    # 本轮未修复时不能继承上一轮成功的 confidence/path/notes。
    h0c_meta: dict[str, Any] = {
        "transcript_repaired_path": None,
        "transcript_repair_confidence": None,
        "transcript_speakers": [],
        "transcript_repair_notes": "",
        "transcript_unusable_lines": None,
        "transcript_scene_line_indices": None,
        "transcript_scene_evidence": None,
        "transcript_resolution": None,
        "transcript_resolution_repair_audit": None,
    }
    cross_check = (tx or {}).get("cross_check")
    if tx is None:
        from app.services.gold_story.transcript.transcript import read_transcript_metadata

        metadata = read_transcript_metadata(cfg, candidate.source_id, transcript_path)
        cross_check = metadata.get("cross_check")
        if not metadata and existing_row:
            cross_check = (existing_row.get("payload") or {}).get("transcript_cross_check")
    transcript_failure = ""
    transcript_failure_stage = "H0b"
    resolution: dict[str, Any] | None = None
    if isinstance(cross_check, dict) and cross_check.get("available") and cross_check.get("passed") is False:
        from app.services.gold_story.transcript.transcript import read_transcript_metadata

        candidates = (tx or {}).get("transcript_candidates")
        if not candidates:
            candidates = read_transcript_metadata(cfg, candidate.source_id, transcript_path).get("transcript_candidates")
        old_payload = (existing_row or {}).get("payload") or {}
        previous = resolution_cache or old_payload.get("transcript_resolution") or (old_payload.get("collect_failure") or {}).get("transcript_resolution")
        try:
            resolution = llm_steps.reconcile_transcripts(candidates or [], previous=previous)
        except Exception as exc:
            return {**base, **_execution_failure(exc, "H0b reconciliation"), "transcript_cross_check": cross_check}
        h0c_meta["transcript_resolution"] = resolution
        if resolution.get("status") != "resolved" or not cfg.gold_story_transcript_repair:
            return {**base, "action": "error", "stage": "H0b", "reason": "transcript_conflict",
                    "error": "转写分歧尚未解决：" + str(resolution.get("reason") or "需要启用完整场景审核"),
                    "retryable": False, "transcript_cross_check": cross_check, "transcript_resolution": resolution}
        transcript_text = str(resolution["text"])
        transcript_for_h2 = transcript_text
    if transcript_for_h2 and cfg.gold_story_transcript_repair:
        try:
            h0c = llm_steps.repair_transcript(
                title=candidate.title,
                transcript=transcript_text,
                description=candidate.description,
                require_complete_scene=True,
                feedback=repair_feedback,
            )
            if resolution is not None:
                h0c_meta["transcript_resolution_repair_audit"] = llm_steps.review_transcript_repair(
                    transcript=transcript_text, repaired=format_dialogue_transcript(h0c["lines"]),
                )
            rep_path = repaired_transcript_path(cfg, candidate.source_id)
            transcript_for_h2 = save_repaired_transcript(rep_path, h0c["lines"])
            h0c_meta.update({
                "transcript_repaired_path": str(rep_path),
                "transcript_repair_confidence": h0c.get("repair_confidence"),
                "transcript_speakers": h0c.get("speakers") or [],
                "transcript_repair_notes": h0c.get("repair_notes") or "",
                "transcript_unusable_lines": h0c.get("unusable_lines") or 0,
                "transcript_scene_line_indices": h0c.get("scene_line_indices"),
                "transcript_scene_evidence": h0c.get("scene_evidence"),
            })
        except Exception as exc:
            logger.warning(
                "gold_story H0c failed bvid=%s: %s",
                candidate.source_id,
                exc,
            )
            if not isinstance(exc, llm_steps.SourceRejected):
                return {**base, **_execution_failure(exc, "H0c"), "transcript_resolution": resolution,
                        "transcript_cross_check": cross_check}
            transcript_failure = str(exc)
            transcript_failure_stage = "H0c"
            transcript_for_h2 = ""

    source_inputs = []
    if transcript_for_h2:
        source_inputs.append("transcript")
    if str(candidate.description or "").strip():
        source_inputs.append("description")
    if any(str(reply or "").strip() for reply in candidate.top_replies):
        source_inputs.append("replies")
    if transcript_failure or not transcript_for_h2.strip():
        return {**base, "action": "reject", "stage": transcript_failure_stage,
                "reason": "source_unusable", "error": transcript_failure or "empty repaired transcript",
                "transcript_cross_check": cross_check, "transcript_resolution": resolution}
    h0c_meta.update({
        "transcript_status": "unusable" if transcript_failure else ("usable" if transcript_for_h2 else "missing"),
        "transcript_failure_reason": transcript_failure or None,
        "source_inputs": source_inputs,
    })

    try:
        source_feedback = ""
        for source_attempt in range(2):
            h2 = llm_steps.extract_story_raw(
                title=candidate.title, transcript=transcript_for_h2,
                description=candidate.description, replies=list(candidate.top_replies),
                source_feedback=source_feedback,
            )
            story_raw_text = str(h2["story_raw"])
            try:
                source_audit = llm_steps.review_story_source(transcript=transcript_for_h2, story_raw=story_raw_text)
                break
            except ValueError as exc:
                if source_attempt or not str(exc).startswith("H2 source_unfaithful:"):
                    raise
                source_feedback = str(exc)
        self_id = int(existing_row["id"]) if existing_row and existing_row.get("id") else None
        near = repo_gold_story.find_near_duplicate(story_raw_text, exclude_id=self_id)
        if near:
            return {
                **base,
                "action": "skip",
                "reason": "duplicate_similar_story",
                **({"id": self_id} if self_id is not None else {}),
                "duplicate_id": near["id"],
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
            video_title=candidate.title,
        )
        h3, sync_notes = sync_h3_from_scene_contract(
            h3, h3a, story_raw=str(h2.get("story_raw") or "")
        )
        if sync_notes:
            note = str(h3.get("structure_mapping_note") or "").strip()
            suffix = ";".join(sync_notes)
            h3["structure_mapping_note"] = (
                f"{note};{suffix}".strip(";") if note else suffix
            )
            # 契约字母与列对齐
            h3a = dict(h3a)
            h3a["story_type"] = str(h3.get("structure_type") or h3a.get("story_type"))
        h3b = llm_steps.build_dialogue_seed(
            story_raw=h2["story_raw"],
            h3=h3,
            scene_contract=h3a,
            video_title=candidate.title,
        )
    except ValueError as exc:
        if not isinstance(exc, llm_steps.SourceRejected):
            return {**base, **_execution_failure(exc, "LLM")}
        logger.info(
            "gold_story LLM reject bvid=%s reason=%s",
            candidate.source_id,
            exc,
        )
        return {**base, "action": "reject", "reason": str(exc), "stage": "LLM"}
    except Exception as exc:
        return {**base, **_execution_failure(exc, "LLM")}

    try:
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
    except Exception as exc:
        return {**base, **_execution_failure(exc, "H4a")}
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
        # 站外原视频标题：H3 会把库内 title 换成短标题，原题是角色分工/抱怨方向
        # 的最强线索，重转（H3a/H3b rebuild）时必须还能拿到
        "source_title": candidate.title,
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
        "source_fidelity_audit": source_audit,
        **funny_payload,
        **h0c_meta,
        # 两路转写交叉验证结果（缺失即未做验证，不是失败）。
        # 保留在 payload 里，便于日后回看这条 seed 的原始素材可信度。
        "transcript_cross_check": cross_check,
    }
    funny_ok, funny_reason = passes_funny_gate_from_payload(payload, level="l2")
    if not funny_ok:
        insert_status = "rejected"
        audit = audit_with_funny_rejection(audit, funny_reason)
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
            expected_row=existing_row,
        )
        fresh = repo_gold_story.get_story(gid)
        export_result = _export_collection_result(fresh, cfg)
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
            **export_result,
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
        result.update(_export_collection_result(row, cfg))
    action = result.get("action")
    if action == "insert" and insert_status == "rejected":
        result["action"] = "reject"
        result["reason"] = (
            "low_audience_laugh"
            if funny_reason.startswith("low_") or funny_reason == "cute_not_funny"
            else "audit_failed"
        )
        result["audit_reasons"] = audit.get("reject_reasons") or []
    if action == "skip":
        if result.get("reason") in {"duplicate_content_hash", "duplicate_similar_story"}:
            result["duplicate_id"] = result.pop("id", None)
        return {**base, **result, "audit_pass": audit.get("pass")}
    return {**base, **result, "audit_pass": audit.get("pass"), "status": insert_status}


def _build_candidate_from_bvid(
    source_id: str,
    *,
    config: Config,
    existing_row: dict[str, Any] | None = None,
) -> VideoCandidate:
    """拉取真实元数据；故障向队列上报，不能用零分伪装成内容驳回。"""
    meta = fetch_video_meta(source_id, config=config)
    replies = fetch_top_replies(int(meta.get("aid") or 0), config=config, limit=8)

    http = _bili_http(config)
    funny = compute_audience_funny_metrics(
        source_id=source_id,
        cid=int(meta.get("cid") or 0),
        view_count=int(meta.get("view_count") or 0),
        reply_count=int(meta.get("reply_count") or 0),
        replies=replies,
        session=http,
        strict=True,
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
        duration_sec=int(meta.get("duration") or 0),
    )


def _run_reimport_attempts(
    source_id: str, *, config: Config, force_transcript: bool,
    existing_row: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], VideoCandidate | None]:
    """手动导入共用有限重试；不重复处理已提交结果，不覆盖期间发生的修改。"""
    candidate: VideoCandidate | None = None
    refresh_transcript = force_transcript
    repair_feedback = ""
    resolution_cache: dict[str, Any] | None = None
    for attempt in range(1, _COLLECT_MAX_ATTEMPTS + 1):
        if attempt > 1 and existing_row:
            fresh = repo_gold_story.get_story(int(existing_row["id"]), include_payload_snapshot=True)
            fields = ("_payload_json_snapshot", "status", "mechanism", "structure_type",
                      "conflict_core", "title", "gold_chat_daily_story_id")
            if any(fresh.get(key) != existing_row.get(key) for key in fields):
                return {"action": "error", "stage": "reimport", "reason": "source_changed",
                        "error": "采集期间素材已被修改，请刷新后重新导入", "retryable": False,
                        "attempts": attempt - 1}, candidate
        stage = "H0"
        try:
            candidate = _build_candidate_from_bvid(source_id, config=config, existing_row=existing_row)
            stage = "reimport" if existing_row else "import"
            outcome = process_candidate(
                candidate, config=config, overwrite_existing=existing_row is not None,
                force_transcript=refresh_transcript, existing_row=existing_row,
                repair_feedback=repair_feedback, resolution_cache=resolution_cache,
            )
        except Exception as exc:
            from app.repositories import sql_exec as sql
            sql.rollback()
            outcome = _execution_failure(exc, stage)
        outcome = {**outcome, "attempts": attempt}
        if (outcome.get("action") != "error" or not outcome.get("retryable")
                or outcome.get("persisted") or attempt == _COLLECT_MAX_ATTEMPTS):
            return outcome, candidate
        # 已完成转写后的模型失败复用本轮转写，避免重下原视频。
        if outcome.get("stage") in {"H0b reconciliation", "H0c", "LLM", "H4a"}:
            refresh_transcript = False
        if outcome.get("stage") == "H0c":
            repair_feedback = str(outcome.get("error") or "")
            resolution_cache = outcome.get("transcript_resolution")
        time.sleep(min(2 ** (attempt - 1), 4))
    raise RuntimeError("采集重试预算无效")


def overwrite_existing_story(
    gold_story_id: int,
    *,
    config: Config | None = None,
    force_transcript: bool = True,
) -> dict[str, Any]:
    """已入库条目再跑 H0b–H4，回写同一行。"""
    cfg = config or Config()
    row = repo_gold_story.get_story(int(gold_story_id), include_payload_snapshot=True)
    source_id = str(row.get("source_id") or "").strip()
    base = {
        "id": gold_story_id,
        "source_id": source_id,
        "title": row.get("title"),
    }
    if not source_id:
        return {**base, "action": "error", "error": "missing source_id"}
    from app.services.gold_story.gold_chat.status import gold_chat_converting_from_payload
    if gold_chat_converting_from_payload(row.get("payload") or {}):
        return {**base, "action": "error", "stage": "reimport",
                "error": "对话转换进行中，不能重导素材", "retryable": False}

    outcome, _ = _run_reimport_attempts(
        source_id, config=cfg, force_transcript=force_transcript, existing_row=row,
    )
    merged = {**base, **outcome, "id": gold_story_id, "source_id": source_id}
    # 跑完 H3 的结果已在 process_candidate 里写过 status。早退没有 status，要在这里收口，
    # 否则失败条目会一直停在旧的「采集失败」。
    if merged.get("status") or merged.get("action") not in {"reject", "skip", "error"}:
        return merged
    if repo_gold_story.apply_reimport_gate(gold_story_id, merged, expected_row=row):
        status = "rejected" if merged.get("action") in {"reject", "skip"} else "failed"
        return {**merged, "status": status, "persisted": True}
    logger.warning(
        "gold_story reimport gate not saved id=%s action=%s",
        gold_story_id,
        merged.get("action"),
    )
    return {**merged, "persisted": False}


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
    outcome, candidate = _run_reimport_attempts(bvid, config=cfg, force_transcript=force_transcript)
    terminal = outcome.get("action") in {"reject", "error"} or (
        outcome.get("action") == "skip"
        and outcome.get("reason") in {"duplicate_similar_story", "duplicate_content_hash", "auto_score_below_threshold"}
    )
    # 先写终态再展示失败/驳回；不把失败请求加入自动队列。
    if terminal and not outcome.get("status") and not outcome.get("persisted"):
        stored = repo_gold_story.insert_pending(
            source=candidate.source if candidate else "bili", source_id=bvid,
            url=candidate.url if candidate else f"https://www.bilibili.com/video/{bvid}",
            title=candidate.title if candidate else bvid,
            payload={"source_title": candidate.title if candidate else bvid}, outcome=outcome,
        )
        if stored.get("action") == "insert":
            outcome = {**outcome, "id": stored["id"], "status": stored["status"], "persisted": True}
        else:
            outcome = {**stored, "persisted": False}
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
    for gid in dict.fromkeys(gold_story_ids or []):
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
        try:
            on_progress({
                "processed": idx,
                "requested": total,
                "processing_id": proc_id,
                "processing_source_id": proc_bv,
                "queued_ids": queued_ids,
                "queued_source_ids": queued_bvs,
                "results": list(results),
            })
        except Exception:
            logger.exception("gold_story reimport on_progress failed")

    for idx, (kind, value) in enumerate(work):
        _emit_progress(idx, processing=(kind, value))
        if kind == "id":
            gid = int(value)
            if gid in seen_ids:
                continue
            seen_ids.add(gid)
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
            except Exception as exc:
                from app.repositories import sql_exec as sql
                sql.rollback()
                outcome = {"id": gid, **_execution_failure(exc, "reimport")}
            sid = str(outcome.get("source_id") or "").strip()
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
        try:
            outcome = import_or_overwrite_source(
                bvid,
                config=cfg,
                force_transcript=force_transcript,
            )
        except Exception as exc:
            from app.repositories import sql_exec as sql
            sql.rollback()
            outcome = {"source_id": bvid, **_execution_failure(exc, "import")}
        if outcome.get("id"):
            seen_ids.add(int(outcome["id"]))
        seen_bvs.add(bvid)
        results.append(outcome)

    updated = sum(1 for r in results if r.get("action") == "ok")
    inserted = sum(1 for r in results if r.get("action") == "insert")
    rejected = sum(1 for r in results if r.get("action") != "error"
                   and (r.get("action") == "reject" or r.get("status") == "rejected"))
    skipped = sum(1 for r in results if r.get("action") == "skip" and r.get("status") != "rejected")
    failed = sum(1 for r in results if r.get("action") == "error")
    return {
        "requested": len(results),
        "updated": updated,
        "inserted": inserted,
        "rejected": rejected,
        "skipped": skipped,
        "failed": failed,
        "ok": updated + inserted,
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
    failed = 0

    def _snapshot() -> dict[str, Any]:
        return {
            "phase": "enqueue",
            "candidates": len(candidates),
            "enqueued": enqueued,
            "skipped": skipped,
            "failed": failed,
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
            "duration_sec": int(row.duration_sec or 0),
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
            sql.rollback()
            failed += 1
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


def drain_pending_stories(
    *,
    config: Config | None = None,
    skip_transcript: bool = False,
    force_transcript: bool = False,
    dry_run: bool = False,
    limit: int | None = None,
    on_progress: Any | None = None,
) -> dict[str, Any]:
    """异步队列：pending → OCR/H0c/H2–H4 → active|rejected。"""
    cfg = config or Config()
    if dry_run:
        rows = repo_gold_story.list_stories(status="pending", limit=limit or 100000)
        return {"phase": "done", "processed": 0, "inserted": 0, "inserted_rejected": 0,
                "gate_rejected": 0, "failed": 0,
                "results": [{"id": row["id"], "source_id": row["source_id"], "action": "dry_run"} for row in rows]}
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

    def _source_changed(gid: int, source_id: str, claim_id: str) -> dict[str, Any]:
        nonlocal failed
        outcome = {"id": gid, "source_id": source_id, "action": "error", "stage": "drain",
                   "reason": "source_changed", "error": "采集期间素材已被修改，本次执行已停止，请重新导入",
                   "retryable": False}
        if repo_gold_story.release_changed_collect_claim(gid, claim_id=claim_id, outcome=outcome):
            failed += 1
            return {**outcome, "status": "failed"}
        return {"id": gid, "source_id": source_id, "action": "superseded", "reason": "source_changed"}

    while True:
        if limit is not None and processed >= max(0, int(limit)):
            break
        row = repo_gold_story.claim_next_pending()
        if row is None:
            break
        gid = int(row["id"])
        source_id = str(row.get("source_id") or "")
        claim_id = str((row.get("payload") or {}).get("collect_claim_id") or "")
        while True:
            attempt_row = repo_gold_story.begin_collect_attempt(gid, max_attempts=_COLLECT_MAX_ATTEMPTS, claim_id=claim_id)
            if attempt_row is None:
                outcome = {"action": "error", "stage": "drain", "error": "采集尝试次数已耗尽", "retryable": False}
            else:
                row = attempt_row
                try:
                    candidate = _build_candidate_from_bvid(source_id, config=cfg, existing_row=row)
                    outcome = process_candidate(candidate, config=cfg, skip_transcript=skip_transcript,
                                                overwrite_existing=True, force_transcript=force_transcript, existing_row=row)
                except Exception as exc:
                    outcome = _execution_failure(exc, "drain")
            if outcome.get("action") != "error":
                break
            if outcome.get("persisted"):
                failed += 1
                break
            attempts = int((row.get("payload") or {}).get("collect_attempts") or 0)
            retry = bool(outcome.get("retryable")) and attempts < _COLLECT_MAX_ATTEMPTS
            if not repo_gold_story.record_collect_failure(gid, outcome, retry=retry, expected_row=row):
                outcome = _source_changed(gid, source_id, claim_id)
                break
            logger.warning("gold_story collect failed id=%s attempt=%s retry=%s: %s", gid, attempts, retry, outcome.get("error"))
            if not retry:
                outcome = {**outcome, "id": gid, "source_id": source_id, "status": "failed"}
                failed += 1
                break
            time.sleep(min(2 ** max(0, attempts - 1), 4))

        action = str(outcome.get("action") or "")
        status = str(outcome.get("status") or "")
        # 早退（OCR/LLM 软拒）未回写 status 时，收口为 rejected
        if action in {"reject", "skip"} and status not in {"active", "rejected"}:
            if repo_gold_story.record_collect_failure(gid, outcome, retry=False, expected_row=row):
                outcome = {**outcome, "status": "rejected", "id": gid}
                gate_rejected += 1
            else:
                outcome = _source_changed(gid, source_id, claim_id)
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
    if dry_run:
        candidates = collect_candidates(config=cfg, max_candidates=max_candidates,
                                        keywords=keywords, advance_cursor=False)
        return {"phase": "done", "candidates": len(candidates), "enqueued": 0,
                "processed": 0, "inserted": 0, "inserted_rejected": 0, "failed": 0,
                "results": [{"source_id": item.source_id, "title": item.title,
                             "action": "dry_run"} for item in candidates]}

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

    def _with_enqueue(partial: dict[str, Any]) -> dict[str, Any]:
        return {**enq, **partial,
                "failed": int(enq.get("failed") or 0) + int(partial.get("failed") or 0),
                "results": list(enq.get("results") or []) + list(partial.get("results") or [])}

    drain = drain_pending_stories(
        config=cfg,
        skip_transcript=skip_transcript,
        force_transcript=False,
        dry_run=False,
        on_progress=lambda partial: _emit(_with_enqueue(partial)),
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
        "failed": int(enq.get("failed") or 0) + int(drain.get("failed") or 0),
        "results": list(enq.get("results") or []) + list(drain.get("results") or []),
        "candidates_file": enq.get("candidates_file"),
    }
