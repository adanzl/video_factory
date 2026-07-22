from __future__ import annotations

import json
import sqlite3
from typing import Any


def _row_to_dict(row: sqlite3.Row) -> dict:
    data = dict(row)
    if data.get("story_json"):
        data["story"] = json.loads(data["story_json"])
    else:
        data["story"] = {}
    data.pop("story_json", None)
    return data


def count_stories(
    conn: sqlite3.Connection,
    *,
    status: str | None = None,
) -> int:
    if status:
        row = conn.execute(
            "SELECT COUNT(*) AS cnt FROM daily_story WHERE status = ?",
            (status,),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT COUNT(*) AS cnt FROM daily_story",
        ).fetchone()
    return row["cnt"] if row else 0


def list_stories(
    conn: sqlite3.Connection,
    *,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    if status:
        rows = conn.execute(
            """
            SELECT id, theme, story_json, status, created_at, updated_at, job_id
            FROM daily_story
            WHERE status = ?
            ORDER BY id DESC
            LIMIT ? OFFSET ?
            """,
            (status, limit, offset),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT id, theme, story_json, status, created_at, updated_at, job_id
            FROM daily_story
            ORDER BY id DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        ).fetchall()
    return [_row_to_dict(row) for row in rows]


def get_story(conn: sqlite3.Connection, story_id: int) -> dict:
    row = conn.execute(
        "SELECT id, theme, story_json, status, created_at, updated_at, job_id FROM daily_story WHERE id = ?",
        (story_id,),
    ).fetchone()
    if row is None:
        raise KeyError(f"daily_story {story_id} not found")
    return _row_to_dict(row)


def insert_story(
    conn: sqlite3.Connection,
    *,
    theme: str,
    story: dict[str, Any],
    status: str = "active",
) -> int:
    cur = conn.execute(
        """
        INSERT INTO daily_story (theme, story_json, status)
        VALUES (?, ?, ?)
        """,
        (theme, json.dumps(story, ensure_ascii=False), status),
    )
    return cur.lastrowid  # type: ignore[return-value]


def set_job_id(conn: sqlite3.Connection, story_id: int, job_id: int) -> None:
    """回填 job_id 到 daily_story 表，建立强关联。"""
    conn.execute(
        "UPDATE daily_story SET job_id = ?, updated_at = datetime('now') WHERE id = ?",
        (job_id, story_id),
    )


def delete_stories(conn: sqlite3.Connection, ids: list[int]) -> int:
    if not ids:
        return 0
    placeholders = ",".join("?" for _ in ids)
    cur = conn.execute(
        f"DELETE FROM daily_story WHERE id IN ({placeholders})",
        ids,
    )
    return cur.rowcount


def update_story(
    conn: sqlite3.Connection,
    story_id: int,
    *,
    story: dict[str, Any] | None = None,
    status: str | None = None,
) -> dict:
    if story is None and status is None:
        return get_story(conn, story_id)
    sets: list[str] = ["updated_at = datetime('now')"]
    params: list[Any] = []
    if story is not None:
        sets.append("story_json = ?")
        params.append(json.dumps(story, ensure_ascii=False))
    if status is not None:
        sets.append("status = ?")
        params.append(status)
    params.append(story_id)
    conn.execute(
        f"UPDATE daily_story SET {', '.join(sets)} WHERE id = ?",
        params,
    )
    return get_story(conn, story_id)
