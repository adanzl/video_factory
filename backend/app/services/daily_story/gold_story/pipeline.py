"""H0–H4 金故事采集编排。"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from app.config import Config
from app.repositories import repo_gold_story
from app.services.daily_story.gold_story.collect import (
    VideoCandidate,
    collect_candidates,
    engagement_norm,
    write_candidate_list,
)
from app.services.daily_story.gold_story import llm_steps
from app.services.daily_story.gold_story import review as gs_review
from app.services.daily_story.gold_story.export_story import export_story_files
from app.services.daily_story.gold_story.funny_signal import passes_funny_gate_from_payload
from app.services.daily_story.gold_story.scene_contract import sanitize_banned_literals
from app.services.daily_story.gold_story.transcript import (
    repaired_transcript_path,
    save_repaired_transcript,
    transcribe_bilibili,
)

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
) -> dict[str, Any]:
    """单条 BV：H0b → H0c → H2 → H3 → H3a → H3b → H4a → H4。"""
    cfg = config or Config()
    base: dict[str, Any] = {
        "source_id": candidate.source_id,
        "title": candidate.title,
        "keyword": candidate.keyword,
    }

    if _existing_source(candidate.source, candidate.source_id):
        return {**base, "action": "skip", "reason": "already_in_db"}

    transcript_path = cfg.gold_story_transcript_dir / f"{candidate.source_id}.txt"
    transcript_text = _read_transcript(transcript_path)

    if not transcript_text and not skip_transcript:
        try:
            tx = transcribe_bilibili(candidate.source_id, config=cfg)
            if tx.get("action") in {"ok", "skip"}:
                transcript_path = Path(str(tx.get("transcript_path") or transcript_path))
                transcript_text = _read_transcript(transcript_path)
            else:
                return {**base, "action": "error", "stage": "H0b", "error": tx}
        except Exception as exc:
            logger.warning(
                "gold_story H0b failed bvid=%s: %s",
                candidate.source_id,
                exc,
            )
            if not candidate.description and not candidate.top_replies:
                return {**base, "action": "error", "stage": "H0b", "error": str(exc)}

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
        return {**base, "action": "reject", "reason": str(exc)}
    except Exception as exc:
        return {**base, "action": "error", "stage": "LLM", "error": str(exc)}

    story_raw_text = str(h2["story_raw"])
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
    banned = sanitize_banned_literals(
        h3.get("banned_literals") or h3a.get("banned_literals"),
        scene_contract=h3a,
        beat=h3.get("beat") if isinstance(h3.get("beat"), list) else [],
    )
    payload: dict[str, Any] = {
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
        transcript_backend="faster-whisper",
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


def run_collect_pipeline(
    *,
    config: Config | None = None,
    max_candidates: int | None = None,
    keywords: list[str] | None = None,
    skip_transcript: bool = False,
    dry_run: bool = False,
    write_list: bool = True,
) -> dict[str, Any]:
    """H0–H4 一次跑完。"""
    from app.repositories.schema import apply_gold_story_schema
    from app.repositories import sql_exec as sql
    from app.repositories.db_obj import db

    conn = db.session.connection().connection.dbapi_connection
    apply_gold_story_schema(conn)
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
    inserted_active = 0
    inserted_rejected = 0
    for row in candidates:
        outcome = process_candidate(
            row,
            config=cfg,
            skip_transcript=skip_transcript,
            dry_run=dry_run,
        )
        results.append(outcome)
        if outcome.get("action") == "insert":
            inserted_active += 1
        elif outcome.get("action") == "reject" and outcome.get("reason") == "audit_failed":
            inserted_rejected += 1

    return {
        "candidates": len(candidates),
        "inserted": inserted_active,
        "inserted_rejected": inserted_rejected,
        "results": results,
        "candidates_file": str(cfg.gold_story_candidates_file),
    }
