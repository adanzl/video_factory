from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any, cast

from app.repositories import sql_exec as sql
from app.services.gold_story.collect.funny import DEFAULT_FUNNY_SIGNAL
from app.services.gold_story.types import (
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
# H0/H1 先入库占位；H5 pick 只取 active/promoted，不会命中
PENDING_MECHANISM = "PENDING"
PENDING_STRUCTURE = "P"


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


def find_near_duplicate(story_raw: str, *, exclude_id: int | None = None) -> dict[str, Any] | None:
    """库内近重复：转载换 BV、LLM 抽稿措辞不同仍能命中。"""
    compact_new = compact_story_raw(story_raw)
    if len(compact_new) < NEAR_DUP_LCS_MIN:
        return None
    rows = sql.fetchall(
        """
        SELECT id, source_id, title,
               json_extract(payload_json, '$.story_raw') AS story_raw
        FROM gold_story WHERE (? IS NULL OR id != ?)
        """,
        (exclude_id, exclude_id),
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


def search_cursor(key: str, *, advance_from: int | None = None) -> int:
    """预览只读；搜索成功后 CAS 推进，失败和并发旧请求不覆盖进度。"""
    if advance_from is None:
        exists = sql.fetchone("SELECT 1 FROM sqlite_master WHERE type='table' AND name='gold_story_search_cursor'")
        if not exists:
            sql.commit()
            return 0
    if advance_from is not None:
        sql.execute("""INSERT INTO gold_story_search_cursor(search_key, position) VALUES (?, ?)
            ON CONFLICT(search_key) DO UPDATE SET position=excluded.position
            WHERE gold_story_search_cursor.position=?""",
            (key, advance_from + 1, advance_from))
    row = sql.fetchone("SELECT position FROM gold_story_search_cursor WHERE search_key=?", (key,))
    sql.commit()
    return int(row["position"]) if row else 0


def get_story(gold_story_id: int, *, include_payload_snapshot: bool = False) -> dict:
    row = sql.fetchone(
        f"SELECT {_GOLD_STORY_COLUMNS} FROM gold_story WHERE id = ?",
        (gold_story_id,),
    )
    sql.commit()
    if row is None:
        raise KeyError(f"gold_story {gold_story_id} not found")
    result = _row_to_dict(row)
    if include_payload_snapshot:
        result["_payload_json_snapshot"] = row.get("payload_json")
    return result


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


def is_gold_chat_daily_story(daily_story_id: int) -> bool:
    """该 daily_story 是否由 gold_chat 导入。"""
    row = sql.fetchone(
        """
        SELECT 1 AS found
        FROM gold_story
        WHERE gold_chat_daily_story_id = ?
        LIMIT 1
        """,
        (int(daily_story_id),),
    )
    sql.commit()
    return row is not None


def get_by_gold_chat_daily_story_id(daily_story_id: int) -> dict | None:
    """按已导入的 daily_story id 取来源金故事及其校验契约。"""
    row = sql.fetchone(
        f"""
        SELECT {_GOLD_STORY_COLUMNS}
        FROM gold_story
        WHERE gold_chat_daily_story_id = ?
        LIMIT 1
        """,
        (int(daily_story_id),),
    )
    sql.commit()
    return _row_to_dict(row) if row is not None else None


def _list_where(
    *,
    status: str | None = None,
    structure_type: str | None = None,
    mechanism: str | None = None,
    has_story: bool | None = None,
    exclude_archived: bool = False,
) -> tuple[str, list[Any]]:
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
    if has_story is True:
        clauses.append("gold_chat_daily_story_id IS NOT NULL")
    elif has_story is False:
        clauses.append("gold_chat_daily_story_id IS NULL")
    if exclude_archived:
        clauses.append("status != ?")
        params.append("archived")
    if not clauses:
        return "", []
    return " WHERE " + " AND ".join(clauses), params


def list_stories_with_payload_marker(
    marker: str,
    *,
    limit: int = 50,
) -> list[dict]:
    """按 payload_json 子串找出候选行，调用方再做字段级过滤。"""
    text = str(marker or "").strip()
    if not text:
        return []
    limit = max(1, min(int(limit), 200))
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    rows = sql.fetchall(
        f"""
        SELECT {_GOLD_STORY_COLUMNS}
        FROM gold_story
        WHERE payload_json LIKE ? ESCAPE '\\'
        ORDER BY id DESC
        LIMIT ?
        """,
        (f"%{escaped}%", limit),
    )
    sql.commit()
    return [_row_to_dict(row) for row in rows]


def list_stories(
    *,
    status: str | None = None,
    structure_type: str | None = None,
    mechanism: str | None = None,
    has_story: bool | None = None,
    exclude_archived: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    where, params = _list_where(
        status=status,
        structure_type=structure_type,
        mechanism=mechanism,
        has_story=has_story,
        exclude_archived=exclude_archived,
    )
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


def count_stories(
    *,
    status: str | None = None,
    structure_type: str | None = None,
    mechanism: str | None = None,
    has_story: bool | None = None,
    exclude_archived: bool = False,
) -> int:
    where, params = _list_where(
        status=status,
        structure_type=structure_type,
        mechanism=mechanism,
        has_story=has_story,
        exclude_archived=exclude_archived,
    )
    row = sql.fetchone(
        f"SELECT COUNT(*) AS cnt FROM gold_story{where}",
        tuple(params) if params else None,
    )
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
    from app.services.gold_story.collect.funny import plan_funny_rescore

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
    """原子修改指定字段，避免读改写整个 payload 覆盖并发更新的任务版本。"""
    if not patch:
        return
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    pairs = ", ".join("?, json(?)" for _ in patch)
    params: list[Any] = []
    for key, value in patch.items():
        params.extend(("$." + json.dumps(key, ensure_ascii=False), json.dumps(value, ensure_ascii=False)))
    result = sql.execute(
        f"UPDATE gold_story SET payload_json = json_set(COALESCE(payload_json, '{{}}'), {pairs}), updated_at = ? WHERE id = ?",
        (*params, now, int(gold_story_id)),
    )
    if result.rowcount != 1:
        sql.rollback()
        raise KeyError(f"gold_story not found: {gold_story_id}")
    sql.commit()


def claim_chat_task(gold_story_id: int, task: dict[str, Any]) -> bool:
    """跨请求/进程原子领取同一故事，过期任务才允许替换。"""
    result = sql.execute(
        """UPDATE gold_story SET payload_json = json_set(COALESCE(payload_json, '{}'),
               '$.gold_chat_task', json(?)) WHERE id = ? AND (
               COALESCE(json_extract(payload_json, '$.gold_chat_task.status'), '')
                   NOT IN ('queued', 'running') OR
               COALESCE(json_extract(payload_json, '$.gold_chat_task.expires_at'), 0) <= ?)
        """,
        (json.dumps(task, ensure_ascii=False), gold_story_id, task["started_at"]),
    )
    claimed = result.rowcount == 1
    sql.commit()
    return claimed


def update_chat_task(gold_story_id: int, task: dict[str, Any]) -> None:
    """旧执行器不能覆盖同一故事后来创建的任务。"""
    sql.execute(
        """UPDATE gold_story SET payload_json = json_set(payload_json,
               '$.gold_chat_task', json(?)) WHERE id = ?
               AND json_extract(payload_json, '$.gold_chat_task.task_id') = ?
               AND json_extract(payload_json, '$.gold_chat_task.status') IN ('queued', 'running')""",
        (json.dumps(task, ensure_ascii=False), gold_story_id, task["task_id"]),
    )
    sql.commit()


def expire_chat_task(gold_story_id: int, task: dict[str, Any]) -> None:
    """到期任务和旧标记一起结束；不得覆盖另一执行器已写入的终态。"""
    sql.execute(
        """UPDATE gold_story SET payload_json = json_set(payload_json,
               '$.gold_chat_task', json(?), '$.gold_chat_convert_status', NULL,
               '$.gold_chat_convert_started_at', NULL) WHERE id = ?
               AND json_extract(payload_json, '$.gold_chat_task.task_id') = ?
               AND json_extract(payload_json, '$.gold_chat_task.status') IN ('queued', 'running')
               AND json_extract(payload_json, '$.gold_chat_task.expires_at') <= ?""",
        (json.dumps(task, ensure_ascii=False), gold_story_id, task["task_id"], task["finished_at"]),
    )
    sql.commit()


def publish_chat_export(gold_story_id: int, patch: dict[str, Any], *, task_id: str | None = None,
                        task_owner_id: int | None = None, expected_row: dict[str, Any]) -> None:
    """单次提交导出版本和成功摘要；过期或被替换的执行器不能发布。"""
    result = sql.execute(
        """UPDATE gold_story SET payload_json = json_patch(COALESCE(payload_json, '{}'), json(?)),
               updated_at = ? WHERE id = ? AND payload_json IS ?
               AND COALESCE(mechanism, '') = ? AND COALESCE(structure_type, '') = ?
               AND (? IS NULL OR EXISTS (
               SELECT 1 FROM gold_story AS owner WHERE owner.id=? AND
               json_extract(owner.payload_json, '$.gold_chat_task.task_id') = ? AND
               json_extract(owner.payload_json, '$.gold_chat_task.status') = 'running' AND
               json_extract(owner.payload_json, '$.gold_chat_task.expires_at') > ?))""",
        (json.dumps(patch, ensure_ascii=False), datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
         gold_story_id, expected_row["_payload_json_snapshot"],
         expected_row.get("mechanism") or "", expected_row.get("structure_type") or "",
         task_id, task_owner_id or gold_story_id, task_id, datetime.now(timezone.utc).timestamp()),
    )
    if result.rowcount != 1:
        sql.rollback()
        raise RuntimeError("转换任务已结束或被替换，禁止发布旧执行器的稿件")
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


def update_mechanism_and_structure(
    gold_story_id: int,
    *,
    mechanism: str,
    structure_type: str,
) -> None:
    """同时更新 mechanism 与 structure_type（须合法配对）。"""
    get_story(int(gold_story_id))
    mech = normalize_mechanism(mechanism)
    st = normalize_structure_type(structure_type)
    validate_mechanism_structure_pair(mech, st)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    sql.execute(
        """
        UPDATE gold_story
        SET mechanism = ?, structure_type = ?, updated_at = ?
        WHERE id = ?
        """,
        (mech, st, now, int(gold_story_id)),
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
    expected_row: dict[str, Any] | None = None,
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
    from app.services.gold_story.gold_chat.status import gold_chat_converting_from_payload
    from app.repositories import repo_daily_story
    from copy import deepcopy

    fresh = get_story(gold_story_id, include_payload_snapshot=True)
    if gold_chat_converting_from_payload(fresh.get("payload") or {}):
        raise RuntimeError("对话转换进行中，不能重导素材")
    if expected_row is not None and any(fresh.get(key) != expected_row.get(key)
            for key in ("payload", "status", "mechanism", "structure_type", "conflict_core", "title", "gold_chat_daily_story_id")):
        raise RuntimeError("采集期间来源已变化，请刷新后重试")
    payload.pop("collect_failure", None)
    old_payload = fresh.get("payload") or {}
    daily_id = fresh.get("gold_chat_daily_story_id")
    # 旧库可能只有平铺文件、没有版本路径；已处理条目重导也须封住旧缓存。
    invalidate = fresh["status"] not in {"pending", "processing"} or bool(old_payload.get("gold_chat_json") or daily_id)
    if invalidate:
        payload["gold_chat_source_revision"] = uuid.uuid4().hex
        payload["gold_chat_stale"] = {"reason": "素材已重新导入，请重新转换并导入日常", "at": now}
        # 历史正式稿文件和路径保留；旧候选不能再作为当前来源的待审稿。
        for key in ("gold_chat_review_status", "gold_chat_review_pending_candidate",
                    "gold_chat_failed_candidate", "gold_chat_candidate_contract"):
            payload.pop(key, None)
    with sql.atomic():
        changed = sql.execute(
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
            WHERE id = ? AND payload_json IS ? AND status IS ? AND gold_chat_daily_story_id IS ?
              AND mechanism IS ? AND structure_type IS ? AND conflict_core IS ? AND title IS ?
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
                fresh["_payload_json_snapshot"], fresh["status"], fresh.get("gold_chat_daily_story_id"),
                fresh.get("mechanism"), fresh.get("structure_type"), fresh.get("conflict_core"), fresh.get("title"),
            ),
        )
        if changed.rowcount != 1:
            raise RuntimeError("采集期间来源已变化，请刷新后重试")
        if invalidate and daily_id:
            daily = repo_daily_story.get_story(int(daily_id))
            story = deepcopy(daily.get("story") or {})
            quality = story.setdefault("quality", {})
            quality["source_stale"] = True
            quality["production_reasons"] = ["来源素材已重新导入，需重新转换并导入新稿"]
            repo_daily_story.update_story(int(daily_id), story=story, status="review_pending")
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


def insert_pending(
    *,
    source: str,
    source_id: str,
    url: str,
    title: str | None = None,
    engagement_score: float | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """H0/H1 后先落库为 pending，OCR/结构化异步排队。"""
    source = str(source or "").strip() or "bili"
    source_id = str(source_id or "").strip()
    if not source_id:
        raise ValueError("source_id required")
    existing = sql.fetchone(
        "SELECT id, status FROM gold_story WHERE source = ? AND source_id = ?",
        (source, source_id),
    )
    if existing:
        sql.commit()
        return {
            "action": "skip",
            "reason": "duplicate_source",
            "id": int(existing["id"]),
            "status": existing["status"],
        }

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    body = dict(payload or {})
    body.setdefault("pipeline_stage", "queued")
    c_hash = content_hash(f"pending:{source}:{source_id}")
    result = sql.execute(
        """
        INSERT INTO gold_story (
            source, source_id, url, status, mechanism, structure_type,
            theme_family, title, conflict_core, auto_score, engagement_score,
            content_hash, transcript_backend, transcript_path, payload_json,
            created_at, updated_at
        ) VALUES (?, ?, ?, 'pending', ?, ?, NULL, ?, NULL, 0, ?, ?, NULL, NULL, ?, ?, ?)
        """,
        (
            source,
            source_id,
            str(url or ""),
            PENDING_MECHANISM,
            PENDING_STRUCTURE,
            title,
            engagement_score,
            c_hash,
            json.dumps(body, ensure_ascii=False),
            now,
            now,
        ),
    )
    sql.commit()
    return {
        "action": "insert",
        "id": int(result.lastrowid),  # type: ignore[arg-type,assignment]
        "status": "pending",
    }


def reset_processing_to_pending() -> int:
    """服务重启后：processing → pending，便于队列重新认领。"""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    result = sql.execute(
        """
        UPDATE gold_story
        SET status = 'pending', updated_at = ?,
            payload_json = json_remove(COALESCE(payload_json, '{}'), '$.collect_claim_id')
        WHERE status = 'processing'
        """,
        (now,),
    )
    sql.commit()
    return int(result.rowcount or 0)


def claim_next_pending() -> dict[str, Any] | None:
    """逐条认领；每次恢复生成新归属标记，旧执行器不能续跑或收口。"""
    while True:
        row = sql.fetchone("SELECT id FROM gold_story WHERE status='pending' ORDER BY id ASC LIMIT 1")
        if row is None:
            sql.commit()
            return None
        gid = int(row["id"])
        claim_id = uuid.uuid4().hex
        result = sql.execute("""UPDATE gold_story SET status='processing', updated_at=datetime('now'),
                payload_json=json_set(COALESCE(payload_json, '{}'), '$.collect_claim_id', ?)
            WHERE id=? AND status='pending'""", (claim_id, gid))
        sql.commit()
        if result.rowcount != 1:
            continue
        try:
            claimed = get_story(gid, include_payload_snapshot=True)
        except KeyError:
            continue
        if claimed["status"] == "processing" and claimed["payload"].get("collect_claim_id") == claim_id:
            return claimed


def begin_collect_attempt(gold_story_id: int, *, max_attempts: int, claim_id: str | None = None) -> dict | None:
    """执行前持久化计数，崩溃恢复不能重置尝试预算。"""
    result = sql.execute("""UPDATE gold_story SET payload_json=json_set(
            COALESCE(payload_json, '{}'), '$.collect_attempts',
            COALESCE(json_extract(payload_json, '$.collect_attempts'), 0)+1),
            updated_at=datetime('now')
        WHERE id=? AND status='processing'
          AND COALESCE(json_extract(payload_json, '$.collect_attempts'), 0) < ?
          AND (? IS NULL OR json_extract(payload_json, '$.collect_claim_id')=?)""",
        (gold_story_id, max_attempts, claim_id, claim_id))
    sql.commit()
    if result.rowcount != 1:
        return None
    try:
        row = get_story(gold_story_id, include_payload_snapshot=True)
    except KeyError:
        return None
    if row["status"] != "processing" or (claim_id is not None and row["payload"].get("collect_claim_id") != claim_id):
        return None
    return row


def record_collect_failure(
    gold_story_id: int, outcome: dict[str, Any], *, retry: bool, expected_row: dict[str, Any],
) -> bool:
    """仅收口当前认领的快照，不能覆盖归档、人工编辑或其他采集结果。"""
    rejected = outcome.get("action") in {"reject", "skip"}
    key = "$.audit" if rejected else "$.collect_failure"
    value = ({"pass": False, "stage": outcome.get("stage") or "pipeline",
              "reject_reasons": [str(outcome.get("reason") or outcome.get("error") or "pipeline_reject")]}
             if rejected else outcome)
    status = "rejected" if rejected else ("processing" if retry else "failed")
    result = sql.execute("""UPDATE gold_story SET status=?, payload_json=json_set(
            COALESCE(payload_json, '{}'), ?, json(?)),
            updated_at=datetime('now') WHERE id=? AND status='processing'
              AND payload_json IS ? AND mechanism IS ? AND structure_type IS ?
              AND conflict_core IS ? AND title IS ? AND gold_chat_daily_story_id IS ?""",
        (status, key, json.dumps(value, ensure_ascii=False), gold_story_id,
         expected_row["_payload_json_snapshot"], expected_row.get("mechanism"),
         expected_row.get("structure_type"), expected_row.get("conflict_core"),
         expected_row.get("title"), expected_row.get("gold_chat_daily_story_id")))
    sql.commit()
    return result.rowcount == 1


def release_changed_collect_claim(gold_story_id: int, *, claim_id: str, outcome: dict[str, Any]) -> bool:
    """保留人工修改，结束本执行器仍持有但已失效的任务；不碰其他执行器。"""
    result = sql.execute("""UPDATE gold_story SET status='failed', updated_at=datetime('now'),
            payload_json=json_set(payload_json, '$.collect_failure', json(?))
        WHERE id=? AND status='processing' AND json_extract(payload_json, '$.collect_claim_id')=?""",
        (json.dumps(outcome, ensure_ascii=False), gold_story_id, claim_id))
    sql.commit()
    return result.rowcount == 1


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


def set_story_status(gold_story_id: int, *, status: str) -> None:
    """仅更新 status，不改动 payload。"""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    sql.execute(
        """
        UPDATE gold_story
        SET status = ?, updated_at = ?
        WHERE id = ?
        """,
        (status, now, gold_story_id),
    )
    sql.commit()
