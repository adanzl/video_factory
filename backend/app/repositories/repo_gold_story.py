from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from difflib import SequenceMatcher
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
    "gold_chat_daily_story_id, "
    "created_at, updated_at, last_used_at"
)

_MIN_AUTO_SCORE = 0.55
_COMPACT_STORY_RE = re.compile(r"[\s\W_]+", re.UNICODE)
NEAR_DUP_LCS_MIN = 16


def normalize_story_raw(text: str) -> str:
    t = str(text or "").strip().lower()
    t = re.sub(r"\s+", " ", t)
    return t


def compact_story_raw(text: str) -> str:
    """去空白标点，统一近形字，便于转载比对。"""
    t = str(text or "").strip().lower().replace("唧", "叽")
    return _COMPACT_STORY_RE.sub("", t)


def content_hash(story_raw: str) -> str:
    return hashlib.sha256(normalize_story_raw(story_raw).encode()).hexdigest()


def story_raw_similarity(left: str, right: str) -> tuple[float, int]:
    """返回 (ratio, 最长公共子串长度)。"""
    a = compact_story_raw(left)
    b = compact_story_raw(right)
    if not a or not b:
        return 0.0, 0
    matcher = SequenceMatcher(None, a, b, autojunk=False)
    longest = max((block.size for block in matcher.get_matching_blocks()), default=0)
    return round(matcher.ratio(), 4), int(longest)


def is_near_duplicate_story(left: str, right: str) -> bool:
    _ratio, longest = story_raw_similarity(left, right)
    return longest >= NEAR_DUP_LCS_MIN


def find_near_duplicate(story_raw: str) -> dict[str, Any] | None:
    """库内近重复：转载换 BV、LLM 抽稿措辞不同仍能命中。"""
    compact_new = compact_story_raw(story_raw)
    if len(compact_new) < NEAR_DUP_LCS_MIN:
        return None
    rows = sql.fetchall(
        """
        SELECT id, source_id, title,
               json_extract(payload_json, '$.story_raw') AS story_raw
        FROM gold_story
        """,
    )
    sql.commit()
    best: dict[str, Any] | None = None
    for row in rows:
        ratio, longest = story_raw_similarity(story_raw, str(row["story_raw"] or ""))
        if longest < NEAR_DUP_LCS_MIN:
            continue
        cand = {
            "id": int(row["id"]),
            "source_id": str(row["source_id"] or ""),
            "title": row["title"],
            "ratio": ratio,
            "lcs": longest,
        }
        if best is None or cand["lcs"] > best["lcs"] or (
            cand["lcs"] == best["lcs"] and cand["ratio"] > best["ratio"]
        ):
            best = cand
    return best


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
    source: str | None = "bilibili",
) -> dict | None:
    sid = str(source_id or "").strip()
    if not sid:
        return None
    if source:
        row = sql.fetchone(
            f"""
            SELECT {_GOLD_STORY_COLUMNS}
            FROM gold_story
            WHERE source = ? AND source_id = ?
            """,
            (source, sid),
        )
        if row is not None:
            sql.commit()
            return _row_to_dict(row)
    row = sql.fetchone(
        f"""
        SELECT {_GOLD_STORY_COLUMNS}
        FROM gold_story
        WHERE source_id = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (sid,),
    )
    sql.commit()
    return _row_to_dict(row) if row else None


def update_story_source_fields(
    gold_story_id: int,
    *,
    url: str | None = None,
    title: str | None = None,
    engagement_score: float | None = None,
) -> None:
    """回写站外元数据（如 B 站 title/url）。"""
    fields: list[str] = []
    params: list[Any] = []
    if url is not None:
        fields.append("url = ?")
        params.append(str(url).strip())
    if title is not None:
        fields.append("title = ?")
        params.append(str(title).strip())
    if engagement_score is not None:
        fields.append("engagement_score = ?")
        params.append(float(engagement_score))
    if not fields:
        return
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    fields.append("updated_at = ?")
    params.append(now)
    params.append(int(gold_story_id))
    sql.execute(
        f"UPDATE gold_story SET {', '.join(fields)} WHERE id = ?",
        tuple(params),
    )
    sql.commit()


def set_gold_chat_daily_story_id(
    gold_story_id: int,
    daily_story_id: int | None,
) -> None:
    """标注 gold_chat 已导入的日常故事 id（重导仍指向同一行）。"""
    ds_id = int(daily_story_id) if daily_story_id else None
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    sql.execute(
        """
        UPDATE gold_story
        SET gold_chat_daily_story_id = ?, updated_at = ?
        WHERE id = ?
        """,
        (ds_id, now, int(gold_story_id)),
    )
    patch: dict[str, Any] = {"gold_chat_imported_at": now}
    if ds_id:
        patch["gold_chat_daily_story_id"] = ds_id
    patch_story_payload(int(gold_story_id), patch)


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
        ORDER BY id DESC
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


def delete_stories_by_ids(gold_story_ids: list[int]) -> int:
    """按 id 删除 gold_story（及关联 inject_log）。"""
    ids = sorted({int(x) for x in gold_story_ids if int(x) > 0})
    if not ids:
        return 0
    placeholders = ",".join("?" * len(ids))
    sql.execute(
        f"DELETE FROM gold_story_inject_log WHERE gold_story_id IN ({placeholders})",
        tuple(ids),
    )
    result = sql.execute(
        f"DELETE FROM gold_story WHERE id IN ({placeholders})",
        tuple(ids),
    )
    sql.commit()
    return int(result.rowcount or 0)


def list_all_stories() -> list[dict]:
    rows = sql.fetchall(
        f"SELECT {_GOLD_STORY_COLUMNS} FROM gold_story ORDER BY id DESC",
    )
    sql.commit()
    return [_row_to_dict(row) for row in rows]


def apply_funny_rescore(
    gold_story_id: int,
    *,
    payload: dict[str, Any],
    auto_score: float,
    status: str,
) -> None:
    """回写重评后的 funny_signal / auto_score / status。"""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    sql.execute(
        """
        UPDATE gold_story
        SET payload_json = ?, auto_score = ?, status = ?, updated_at = ?
        WHERE id = ?
        """,
        (
            json.dumps(payload, ensure_ascii=False),
            float(auto_score),
            str(status),
            now,
            int(gold_story_id),
        ),
    )
    sql.commit()


def rescore_all_funny() -> list[dict[str, Any]]:
    """全库按当前权重重算 funny_signal，并重套 L2 门控。"""
    from app.services.daily_story.gold_story.funny_signal import plan_funny_rescore

    results: list[dict[str, Any]] = []
    for row in list_all_stories():
        plan = plan_funny_rescore(row)
        gid = int(row["id"])
        if plan.get("skipped"):
            results.append(plan)
            continue
        payload = plan["payload"]
        score = compute_auto_score(
            funny_signal=_funny_signal_from_payload(payload),
            extract_confidence=float(payload.get("extract_confidence") or 0),
            structure_confidence=float(payload.get("structure_confidence") or 0),
            dialogue_confidence=float(payload.get("dialogue_confidence") or 0),
        )
        apply_funny_rescore(
            gid,
            payload=payload,
            auto_score=score,
            status=str(plan["status"]),
        )
        results.append(
            {
                "id": gid,
                "source_id": row.get("source_id"),
                "title": row.get("title"),
                "skipped": False,
                "old_status": plan.get("old_status"),
                "status": plan["status"],
                "old_signal": plan.get("old_signal"),
                "funny_signal": plan.get("funny_signal"),
                "auto_score": score,
                "l2_ok": plan.get("l2_ok"),
                "l2_reason": plan.get("l2_reason"),
            }
        )
    return results


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


def update_conflict_core(gold_story_id: int, conflict_core: str) -> None:
    """更新 conflict_core 列（M5+H 契约修复回写）。"""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    sql.execute(
        "UPDATE gold_story SET conflict_core = ?, updated_at = ? WHERE id = ?",
        (str(conflict_core or "").strip(), now, int(gold_story_id)),
    )
    sql.commit()


def update_structure_type(gold_story_id: int, structure_type: str) -> None:
    """更新 structure_type（须与 mechanism 合法配对）。"""
    row = get_story(int(gold_story_id))
    mechanism = str(row.get("mechanism") or "")
    st = normalize_structure_type(structure_type)
    validate_mechanism_structure_pair(mechanism, st)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    sql.execute(
        "UPDATE gold_story SET structure_type = ?, updated_at = ? WHERE id = ?",
        (st, now, int(gold_story_id)),
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

    near = find_near_duplicate(story_raw)
    if near:
        return {
            "action": "skip",
            "reason": "duplicate_similar_story",
            "id": int(near["id"]),
            "similar_source_id": near["source_id"],
            "similar_ratio": near["ratio"],
            "similar_lcs": near["lcs"],
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
