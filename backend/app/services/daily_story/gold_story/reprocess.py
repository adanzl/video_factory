"""金故事重跑：H0b 转写 → H0c–H4 回写（基于真实逐字稿）。"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from app.config import Config
from app.repositories import repo_gold_story
from app.services.daily_story.gold_story.collect import (
    engagement_norm,
    fetch_top_replies,
    fetch_video_meta,
    _bili_http,
)
from app.services.daily_story.gold_story.funny_signal import (
    compute_audience_funny_metrics,
    metrics_to_payload,
    passes_funny_gate_from_payload,
)
from app.services.daily_story.gold_story.export_story import export_story_files
from app.services.daily_story.gold_story import llm_steps
from app.services.daily_story.gold_story import review as gs_review
from app.services.daily_story.gold_story.transcript import (
    repaired_transcript_path,
    save_repaired_transcript,
    transcribe_bilibili,
)

logger = logging.getLogger(__name__)

KEEP_ACTIVE_IDS = (18, 23, 31, 34)
KEEP_ACTIVE_BVS = (
    "BV1sh411G7aX",
    "BV18vLh6yEvm",
    "BV1ND4y1X7Mm",
    "BV1ms411a7im",
)
# 兼容旧脚本引用
KEEP_SIX_IDS = KEEP_ACTIVE_IDS
KEEP_SIX_BVS = KEEP_ACTIVE_BVS


def _read_transcript(path: Path) -> str:
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8").strip()


def reprocess_gold_story(
    gold_story_id: int,
    *,
    config: Config | None = None,
    force_transcript: bool = True,
) -> dict[str, Any]:
    """单条：Whisper 转写 + H0c/H2/H3/H3a/H3b/H4a 回写。"""
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

    try:
        meta = fetch_video_meta(source_id, config=cfg)
        replies = fetch_top_replies(int(meta.get("aid") or 0), config=cfg, limit=8)
    except Exception as exc:
        logger.warning("reprocess meta failed bvid=%s: %s", source_id, exc)
        meta = {
            "title": row.get("title") or source_id,
            "description": "",
            "view_count": 0,
            "reply_count": 0,
        }
        replies = []

    try:
        tx = transcribe_bilibili(
            source_id,
            config=cfg,
            skip_existing=not force_transcript,
        )
        if tx.get("action") == "error":
            return {**base, "action": "error", "stage": "H0b", "error": tx}
        transcript_path = Path(str(tx.get("transcript_path") or ""))
        transcript_text = _read_transcript(transcript_path)
        if not transcript_text:
            return {**base, "action": "error", "stage": "H0b", "error": "empty transcript"}
    except Exception as exc:
        return {**base, "action": "error", "stage": "H0b", "error": str(exc)}

    transcript_for_h2 = transcript_text
    h0c_meta: dict[str, Any] = {}
    if cfg.gold_story_transcript_repair:
        try:
            h0c = llm_steps.repair_transcript(
                title=str(meta.get("title") or row.get("title") or ""),
                transcript=transcript_text,
                description=str(meta.get("description") or ""),
            )
            rep_path = repaired_transcript_path(cfg, source_id)
            transcript_for_h2 = save_repaired_transcript(rep_path, h0c["lines"])
            h0c_meta = {
                "transcript_repaired_path": str(rep_path),
                "transcript_repair_confidence": h0c.get("repair_confidence"),
                "transcript_speakers": h0c.get("speakers") or [],
                "transcript_repair_notes": h0c.get("repair_notes") or "",
            }
        except Exception as exc:
            logger.warning("reprocess H0c failed bvid=%s: %s", source_id, exc)

    video_title = str(meta.get("title") or row.get("title") or "")
    try:
        h2 = llm_steps.extract_story_raw(
            title=video_title,
            transcript=transcript_for_h2,
            description=str(meta.get("description") or ""),
            replies=replies,
        )
        h3 = llm_steps.structurize_story(
            title=video_title,
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
        return {**base, "action": "reject", "reason": str(exc)}
    except Exception as exc:
        return {**base, "action": "error", "stage": "LLM", "error": str(exc)}

    story_raw_text = str(h2["story_raw"])
    audit = gs_review.audit_story(
        title=str(h3.get("title") or video_title),
        video_title=video_title,
        story_raw=story_raw_text,
        conflict_core=str(h3.get("conflict_core") or ""),
        transcript=transcript_for_h2,
        description=str(meta.get("description") or ""),
        h3=h3,
        h3a=h3a,
        h3b=h3b,
        config=cfg,
    )
    insert_status = "active" if audit.get("pass") else "rejected"
    norm = engagement_norm(
        int(meta.get("view_count") or 0),
        int(meta.get("reply_count") or 0),
    )
    http = _bili_http(cfg)
    funny = compute_audience_funny_metrics(
        source_id=source_id,
        cid=int(meta.get("cid") or 0),
        view_count=int(meta.get("view_count") or 0),
        reply_count=int(meta.get("reply_count") or 0),
        replies=replies,
        session=http,
    )
    funny_payload = metrics_to_payload(funny)
    old_payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
    payload: dict[str, Any] = {
        **old_payload,
        "perspective": h2.get("perspective"),
        "source_type": source_type,
        "story_raw": story_raw_text,
        "scene_contract": h3a,
        "contract_confidence": h3a.get("contract_confidence"),
        "funny_why": h3.get("funny_why"),
        "beat": h3.get("beat") or [],
        "banned_literals": h3.get("banned_literals") or [],
        "dialogue_seed": h3b.get("dialogue_seed") or [],
        "closing_intent": h3b.get("closing_intent") or h3a.get("closing_intent"),
        "speaker_map_note": h3b.get("speaker_map_note") or h3a.get("remap_note"),
        "setting": h3b.get("setting") or h3a.get("location"),
        "structure_mapping_note": h3.get("structure_mapping_note"),
        "extract_confidence": h2.get("extract_confidence"),
        "structure_confidence": h3.get("structure_confidence"),
        "dialogue_confidence": h3b.get("dialogue_confidence"),
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

    updated = repo_gold_story.update_story_from_pipeline(
        gold_story_id,
        mechanism=str(h3["mechanism"]),
        structure_type=str(h3["structure_type"]),
        title=str(h3.get("title") or video_title),
        conflict_core=str(h3.get("conflict_core") or ""),
        story_raw=story_raw_text,
        payload=payload,
        transcript_backend="faster-whisper",
        transcript_path=str(transcript_path),
        engagement_score=float(norm),
        status=insert_status,
    )
    fresh = repo_gold_story.get_story(gold_story_id)
    paths = export_story_files(source_id=source_id, row=fresh, config=cfg)
    return {
        **base,
        "action": "ok" if insert_status == "active" else "reject",
        "status": insert_status,
        "audit_pass": audit.get("pass"),
        "transcript_chars": len(transcript_text),
        "transcript_repaired_chars": len(transcript_for_h2),
        "story_raw_chars": len(story_raw_text),
        "auto_score": updated.get("auto_score"),
        "export": paths,
    }


def reprocess_many(
    gold_story_ids: list[int],
    *,
    config: Config | None = None,
    force_transcript: bool = True,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for gid in gold_story_ids:
        try:
            results.append(
                reprocess_gold_story(
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
