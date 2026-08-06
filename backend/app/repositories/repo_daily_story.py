from __future__ import annotations

import json
from typing import Any

from app.repositories import sql_exec as sql

_MISSING = object()

_DAILY_STORY_COLUMNS = (
    "id, theme, story_json, status, created_at, updated_at, job_id, story_type, key"
)


def _normalize_key(raw: Any) -> str | None:
    k = str(raw or "").strip()
    return k or None


def _row_to_dict(row: dict) -> dict:
    data = dict(row)
    if data.get("story_json"):
        data["story"] = json.loads(data["story_json"])
    else:
        data["story"] = {}
    data.pop("story_json", None)
    # 表列 key 为权威；补进 story 便于前端编辑同一份 JSON
    col_key = _normalize_key(data.get("key"))
    story = data.get("story")
    if isinstance(story, dict):
        if col_key:
            story["key"] = col_key
            data["key"] = col_key
        else:
            nested = _normalize_key(story.get("key"))
            data["key"] = nested
    else:
        data["key"] = col_key
    return data


def _list_where(
    *,
    status: str | None = None,
    story_type: str | None = None,
) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if status:
        clauses.append("status = ?")
        params.append(status)
    if story_type:
        clauses.append("story_type = ?")
        params.append(story_type)
    if not clauses:
        return "", []
    return " WHERE " + " AND ".join(clauses), params


def count_stories(
    *,
    status: str | None = None,
    story_type: str | None = None,
) -> int:
    where, params = _list_where(status=status, story_type=story_type)
    row = sql.fetchone(
        f"SELECT COUNT(*) AS cnt FROM daily_story{where}",
        tuple(params) if params else None,
    )
    sql.commit()
    return row["cnt"] if row else 0


def list_stories(
    *,
    status: str | None = None,
    story_type: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    where, params = _list_where(status=status, story_type=story_type)
    rows = sql.fetchall(
        f"""
        SELECT {_DAILY_STORY_COLUMNS}
        FROM daily_story{where}
        ORDER BY id DESC
        LIMIT ? OFFSET ?
        """,
        (*params, limit, offset),
    )
    sql.commit()
    return [_row_to_dict(row) for row in rows]


def list_recent_themes(limit: int = 40) -> list[str]:
    """最近入库主题（去重保序），做出题避重负样本。"""
    limit = max(1, min(limit, 100))
    rows = sql.fetchall(
        """
        SELECT theme FROM daily_story
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit * 2,),
    )
    sql.commit()
    out: list[str] = []
    seen: set[str] = set()
    for row in rows or []:
        t = str(row.get("theme") or "").strip()
        if not t or t in seen:
            continue
        seen.add(t)
        out.append(t)
        if len(out) >= limit:
            break
    return out


def list_recent_keys(limit: int = 40) -> list[str]:
    """最近入库内容标签 key（去重保序），做出题避重。"""
    limit = max(1, min(limit, 100))
    rows = sql.fetchall(
        """
        SELECT key FROM daily_story
        WHERE key IS NOT NULL AND TRIM(key) != ''
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit * 2,),
    )
    sql.commit()
    out: list[str] = []
    seen: set[str] = set()
    for row in rows or []:
        k = _normalize_key(row.get("key"))
        if not k or k in seen:
            continue
        seen.add(k)
        out.append(k)
        if len(out) >= limit:
            break
    return out


def get_story(story_id: int) -> dict:
    row = sql.fetchone(
        f"SELECT {_DAILY_STORY_COLUMNS} FROM daily_story WHERE id = ?",
        (story_id,),
    )
    sql.commit()
    if row is None:
        raise KeyError(f"daily_story {story_id} not found")
    return _row_to_dict(row)


def insert_story(
    *,
    theme: str,
    story: dict[str, Any],
    status: str = "active",
    story_type: str | None = None,
    key: str | None = None,
) -> int:
    story_key = _normalize_key(key) or _normalize_key(
        story.get("key") if isinstance(story, dict) else None
    )
    cur = sql.execute(
        """
        INSERT INTO daily_story (theme, story_json, status, story_type, key)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            theme,
            json.dumps(story, ensure_ascii=False),
            status,
            story_type,
            story_key,
        ),
    )
    story_id = int(cur.lastrowid)
    sql.commit()
    return story_id


def set_job_id(story_id: int, job_id: int) -> None:
    sql.execute(
        "UPDATE daily_story SET job_id = ?, updated_at = datetime('now') WHERE id = ?",
        (job_id, story_id),
    )
    sql.commit()


def delete_stories(ids: list[int]) -> int:
    if not ids:
        return 0
    placeholders = ",".join("?" for _ in ids)
    cur = sql.execute(
        f"DELETE FROM daily_story WHERE id IN ({placeholders})",
        ids,
    )
    sql.commit()
    return cur.rowcount


def update_story(
    story_id: int,
    *,
    story: dict[str, Any] | None = None,
    status: str | None = None,
    story_type: str | None | object = _MISSING,
    key: str | None | object = _MISSING,
) -> dict:
    if (
        story is None
        and status is None
        and story_type is _MISSING
        and key is _MISSING
    ):
        return get_story(story_id)
    sets: list[str] = ["updated_at = datetime('now')"]
    params: list[Any] = []
    if story is not None:
        sets.append("story_json = ?")
        params.append(json.dumps(story, ensure_ascii=False))
        # 写 story 时默认同步 key 列（除非显式传 key=）
        if key is _MISSING:
            nested = _normalize_key(story.get("key"))
            sets.append("key = ?")
            params.append(nested)
    if status is not None:
        sets.append("status = ?")
        params.append(status)
    if story_type is not _MISSING:
        sets.append("story_type = ?")
        params.append(story_type)
    if key is not _MISSING:
        sets.append("key = ?")
        params.append(_normalize_key(key))
    params.append(story_id)
    sql.execute(
        f"UPDATE daily_story SET {', '.join(sets)} WHERE id = ?",
        params,
    )
    sql.commit()
    return get_story(story_id)
