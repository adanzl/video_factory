from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

from app.repositories import sql_exec as sql
from app.services.daily_story.gold_story.funny_signal import DEFAULT_FUNNY_SIGNAL
from app.services.daily_story.gold_story.types import (
    normalize_mechanism,
    normalize_structure_type,
    validate_mechanism_structure_pair,
)

_GOLD_STORY_COLUMNS = (
    "id, source, source_id, url, status, mechanism, structure_type, "
    "theme_family, title, conflict_core, auto_score, engagement_score, "
    "content_hash, times_used, avg_humor_delta, copy_hits, "
    "transcript_backend, transcript_path, payload_json, "
    "created_at, updated_at, last_used_at"
)

_MIN_AUTO_SCORE = 0.55


def normalize_story_raw(text: str) -> str:
    t = str(text or "").strip().lower()
    t = re.sub(r"\s+", " ", t)
    return t


def content_hash(story_raw: str) -> str:
    return hashlib.sha256(normalize_story_raw(story_raw).encode()).hexdigest()


def _funny_signal_from_payload(payload: dict[str, Any]) -> float | None:
    raw = payload.get("funny_signal")
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def compute_auto_score(
    *,
    funny_signal: float | None = None,
    engagement_norm: float | None = None,
    extract_confidence: float = 0.0,
    structure_confidence: float = 0.0,
    dialogue_confidence: float = 0.0,
) -> float:
    """auto_score 以观众 funny_signal 为主（0.45），LLM 置信为辅。"""
    _ = engagement_norm
    fs = DEFAULT_FUNNY_SIGNAL if funny_signal is None else float(funny_signal)
    return round(
        0.45 * fs
        + 0.20 * float(extract_confidence)
        + 0.20 * float(structure_confidence)
        + 0.15 * float(dialogue_confidence),
        4,
    )


def _row_to_dict(row: dict) -> dict:
    data = dict(row)
    raw = data.get("payload_json") or "{}"
    try:
        data["payload"] = json.loads(raw)
    except json.JSONDecodeError:
        data["payload"] = {}
    data.pop("payload_json", None)
    return data


def has_source(*, source: str, source_id: str) -> bool:
    row = sql.fetchone(
        "SELECT id FROM gold_story WHERE source = ? AND source_id = ?",
        (source, source_id),
    )
    sql.commit()
    return row is not None


def get_story(gold_story_id: int) -> dict:
    row = sql.fetchone(
        f"SELECT {_GOLD_STORY_COLUMNS} FROM gold_story WHERE id = ?",
        (gold_story_id,),
    )
    sql.commit()
    if row is None:
        raise KeyError(f"gold_story {gold_story_id} not found")
    return _row_to_dict(row)


def get_by_source_id(
    *,
    source_id: str,
    source: str = "bilibili",
) -> dict | None:
    row = sql.fetchone(
        f"""
        SELECT {_GOLD_STORY_COLUMNS}
        FROM gold_story
        WHERE source = ? AND source_id = ?
        """,
        (source, source_id),
    )
    sql.commit()
    return _row_to_dict(row) if row else None


def list_stories(
    *,
    status: str | None = None,
    structure_type: str | None = None,
    mechanism: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    clauses: list[str] = []
    params: list[Any] = []
    if status:
        clauses.append("status = ?")
        params.append(status)
    if structure_type:
        clauses.append("structure_type = ?")
        params.append(structure_type)
    if mechanism:
        clauses.append("mechanism = ?")
        params.append(mechanism)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    rows = sql.fetchall(
        f"""
        SELECT {_GOLD_STORY_COLUMNS}
        FROM gold_story{where}
        ORDER BY auto_score DESC, id DESC
        LIMIT ? OFFSET ?
        """,
        (*params, limit, offset),
    )
    sql.commit()
    return [_row_to_dict(row) for row in rows]


def count_stories(*, status: str | None = None) -> int:
    if status:
        row = sql.fetchone(
            "SELECT COUNT(*) AS cnt FROM gold_story WHERE status = ?",
            (status,),
        )
    else:
        row = sql.fetchone("SELECT COUNT(*) AS cnt FROM gold_story")
    sql.commit()
    return int(row["cnt"]) if row else 0


def delete_stories_by_status(status: str) -> int:
    """删除指定 status 的金故事。"""
    st = str(status or "").strip()
    if not st:
        return 0
    sql.execute(
        "DELETE FROM gold_story_inject_log WHERE gold_story_id IN "
        "(SELECT id FROM gold_story WHERE status = ?)",
        (st,),
    )
    result = sql.execute("DELETE FROM gold_story WHERE status = ?", (st,))
    sql.commit()
    return int(result.rowcount or 0)


def delete_stories_except(keep_ids: list[int]) -> int:
    """删除不在 keep_ids 内的 gold_story（及关联 inject_log）。"""
    ids = sorted({int(x) for x in keep_ids if int(x) > 0})
    if not ids:
        raise ValueError("keep_ids 不能为空")
    placeholders = ",".join("?" * len(ids))
    sql.execute(
        f"DELETE FROM gold_story_inject_log WHERE gold_story_id NOT IN ({placeholders})",
        tuple(ids),
    )
    result = sql.execute(
        f"DELETE FROM gold_story WHERE id NOT IN ({placeholders})",
        tuple(ids),
    )
    sql.commit()
    return int(result.rowcount or 0)


def patch_story_payload(gold_story_id: int, patch: dict[str, Any]) -> None:
    """合并 payload 字段（如 funny_signal）。"""
    row = get_story(int(gold_story_id))
    payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
    merged = {**payload, **patch}
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    sql.execute(
        "UPDATE gold_story SET payload_json = ?, updated_at = ? WHERE id = ?",
        (json.dumps(merged, ensure_ascii=False), now, int(gold_story_id)),
    )
    sql.commit()


def update_story_from_pipeline(
    gold_story_id: int,
    *,
    mechanism: str,
    structure_type: str,
    title: str,
    conflict_core: str,
    story_raw: str,
    payload: dict[str, Any],
    transcript_path: str | None = None,
    transcript_backend: str | None = None,
    engagement_score: float | None = None,
    engagement_norm: float = 0.7,
    extract_confidence: float | None = None,
    structure_confidence: float | None = None,
    dialogue_confidence: float | None = None,
    auto_score: float | None = None,
    status: str = "active",
) -> dict[str, Any]:
    """H0c–H4 重跑后回写 gold_story。"""
    mechanism = normalize_mechanism(mechanism)
    structure_type = normalize_structure_type(structure_type)
    validate_mechanism_structure_pair(mechanism, structure_type)
    extract_confidence = float(
        extract_confidence
        if extract_confidence is not None
        else payload.get("extract_confidence", 0.0)
    )
    structure_confidence = float(
        structure_confidence
        if structure_confidence is not None
        else payload.get("structure_confidence", 0.0)
    )
    dialogue_confidence = float(
        dialogue_confidence
        if dialogue_confidence is not None
        else payload.get("dialogue_confidence", 0.0)
    )
    score = (
        float(auto_score)
        if auto_score is not None
        else compute_auto_score(
            funny_signal=_funny_signal_from_payload(payload),
            engagement_norm=engagement_norm,
            extract_confidence=extract_confidence,
            structure_confidence=structure_confidence,
            dialogue_confidence=dialogue_confidence,
        )
    )
    payload = dict(payload)
    payload["story_raw"] = story_raw
    payload["extract_confidence"] = extract_confidence
    payload["structure_confidence"] = structure_confidence
    payload["dialogue_confidence"] = dialogue_confidence
    c_hash = content_hash(story_raw)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    sql.execute(
        """
        UPDATE gold_story
        SET mechanism = ?,
            structure_type = ?,
            title = ?,
            conflict_core = ?,
            auto_score = ?,
            engagement_score = ?,
            content_hash = ?,
            transcript_backend = ?,
            transcript_path = ?,
            payload_json = ?,
            status = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (
            mechanism,
            structure_type,
            title,
            conflict_core,
            score,
            engagement_score,
            c_hash,
            transcript_backend,
            transcript_path,
            json.dumps(payload, ensure_ascii=False),
            status,
            now,
            gold_story_id,
        ),
    )
    sql.commit()
    return {"id": gold_story_id, "auto_score": score, "status": status}


def insert_or_skip(
    *,
    source: str,
    source_id: str,
    url: str,
    mechanism: str,
    structure_type: str,
    story_raw: str,
    payload: dict[str, Any],
    title: str | None = None,
    conflict_core: str | None = None,
    theme_family: str | None = None,
    engagement_score: float | None = None,
    engagement_norm: float = 0.7,
    extract_confidence: float | None = None,
    structure_confidence: float | None = None,
    dialogue_confidence: float | None = None,
    auto_score: float | None = None,
    transcript_backend: str | None = None,
    transcript_path: str | None = None,
    status: str = "active",
) -> dict[str, Any]:
    """H4 入库：过线则 INSERT，否则 skip。返回 action/id/reason。"""
    mechanism = normalize_mechanism(mechanism)
    structure_type = normalize_structure_type(structure_type)
    validate_mechanism_structure_pair(mechanism, structure_type)
    extract_confidence = float(
        extract_confidence
        if extract_confidence is not None
        else payload.get("extract_confidence", 0.0)
    )
    structure_confidence = float(
        structure_confidence
        if structure_confidence is not None
        else payload.get("structure_confidence", 0.0)
    )
    dialogue_confidence = float(
        dialogue_confidence
        if dialogue_confidence is not None
        else payload.get("dialogue_confidence", 0.0)
    )
    score = (
        float(auto_score)
        if auto_score is not None
        else compute_auto_score(
            funny_signal=_funny_signal_from_payload(payload),
            engagement_norm=engagement_norm,
            extract_confidence=extract_confidence,
            structure_confidence=structure_confidence,
            dialogue_confidence=dialogue_confidence,
        )
    )
    if score < _MIN_AUTO_SCORE:
        return {
            "action": "skip",
            "reason": "auto_score_below_threshold",
            "auto_score": score,
        }

    payload = dict(payload)
    payload.setdefault("story_raw", story_raw)
    payload.setdefault("extract_confidence", extract_confidence)
    payload.setdefault("structure_confidence", structure_confidence)
    payload.setdefault("dialogue_confidence", dialogue_confidence)

    c_hash = content_hash(story_raw)
    dup = sql.fetchone(
        "SELECT id FROM gold_story WHERE content_hash = ?",
        (c_hash,),
    )
    if dup:
        sql.commit()
        return {
            "action": "skip",
            "reason": "duplicate_content_hash",
            "id": int(dup["id"]),
        }

    existing = sql.fetchone(
        "SELECT id FROM gold_story WHERE source = ? AND source_id = ?",
        (source, source_id),
    )
    if existing:
        sql.commit()
        return {
            "action": "skip",
            "reason": "duplicate_source",
            "id": int(existing["id"]),
        }

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    result = sql.execute(
        """
        INSERT INTO gold_story (
            source, source_id, url, status, mechanism, structure_type,
            theme_family, title, conflict_core, auto_score, engagement_score,
            content_hash, transcript_backend, transcript_path, payload_json,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            source,
            source_id,
            url,
            status,
            mechanism,
            structure_type,
            theme_family,
            title,
            conflict_core,
            score,
            engagement_score,
            c_hash,
            transcript_backend,
            transcript_path,
            json.dumps(payload, ensure_ascii=False),
            now,
            now,
        ),
    )
    sql.commit()
    new_id = int(result.lastrowid or 0)
    return {"action": "insert", "id": new_id, "auto_score": score}


def pick(
    *,
    theme: str,
    story_type: str,
    theme_family: str | None = None,
    limit: int = 1,
) -> list[dict]:
    """H5 检索：structure_type 必须匹配，promoted 优先。"""
    story_type = normalize_structure_type(story_type)
    limit = max(1, min(limit, 10))
    theme_q = f"%{str(theme or '').strip()}%"
    clauses = [
        "status IN ('promoted', 'active')",
        "structure_type = ?",
    ]
    params: list[Any] = [story_type]
    if theme_family:
        clauses.append("theme_family = ?")
        params.append(theme_family)
    else:
        clauses.append(
            "(theme_family IS NULL OR theme_family = '' OR ? LIKE '%' || theme_family || '%')"
        )
        params.append(str(theme or "").strip())
    where = " AND ".join(clauses)
    rows = sql.fetchall(
        f"""
        SELECT {_GOLD_STORY_COLUMNS}
        FROM gold_story
        WHERE {where}
        ORDER BY
            CASE status WHEN 'promoted' THEN 0 ELSE 1 END,
            auto_score DESC,
            id DESC
        LIMIT ?
        """,
        (*params, limit),
    )
    sql.commit()
    return [_row_to_dict(row) for row in rows]


def fetch_recent_inject_mechanisms(
    *,
    story_type: str,
    limit: int = 3,
) -> list[str]:
    """近 N 次注入用过的 mechanism（H5 降权）。"""
    story_type = normalize_structure_type(story_type)
    limit = max(1, min(limit, 10))
    rows = sql.fetchall(
        """
        SELECT g.mechanism
        FROM gold_story_inject_log l
        JOIN gold_story g ON g.id = l.gold_story_id
        WHERE l.story_type = ?
        ORDER BY l.created_at DESC
        LIMIT ?
        """,
        (story_type, limit),
    )
    sql.commit()
    return [str(row["mechanism"]) for row in rows if row.get("mechanism")]


def record_inject(
    *,
    gold_story_id: int,
    daily_story_id: int | None = None,
    job_id: int | None = None,
    theme: str | None = None,
    story_type: str | None = None,
    humor_score: int | None = None,
    baseline_humor: int | None = None,
    humor_delta: float | None = None,
    copy_hit: int = 0,
) -> int:
    """H9：写入 inject_log 并更新 gold_story 使用统计。"""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    result = sql.execute(
        """
        INSERT INTO gold_story_inject_log (
            gold_story_id, daily_story_id, job_id, theme, story_type,
            humor_score, baseline_humor, humor_delta, copy_hit, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            gold_story_id,
            daily_story_id,
            job_id,
            theme,
            story_type,
            humor_score,
            baseline_humor,
            humor_delta,
            copy_hit,
            now,
        ),
    )
    sql.execute(
        """
        UPDATE gold_story
        SET times_used = times_used + 1,
            last_used_at = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (now, now, gold_story_id),
    )
    sql.commit()
    return int(result.lastrowid or 0)


def update_story_status(
    gold_story_id: int,
    *,
    status: str,
    audit: dict[str, Any] | None = None,
) -> None:
    """更新 status；可选合并 payload.audit。"""
    row = get_story(gold_story_id)
    payload = dict(row.get("payload") or {})
    if audit is not None:
        payload["audit"] = audit
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    sql.execute(
        """
        UPDATE gold_story
        SET status = ?, payload_json = ?, updated_at = ?
        WHERE id = ?
        """,
        (status, json.dumps(payload, ensure_ascii=False), now, gold_story_id),
    )
    sql.commit()
