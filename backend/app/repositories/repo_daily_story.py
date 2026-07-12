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
            SELECT id, theme, story_json, status, created_at, updated_at
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
            SELECT id, theme, story_json, status, created_at, updated_at
            FROM daily_story
            ORDER BY id DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        ).fetchall()
    return [_row_to_dict(row) for row in rows]


def get_story(conn: sqlite3.Connection, story_id: int) -> dict:
    row = conn.execute(
        "SELECT id, theme, story_json, status, created_at, updated_at FROM daily_story WHERE id = ?",
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
) -> int:
    cur = conn.execute(
        """
        INSERT INTO daily_story (theme, story_json)
        VALUES (?, ?)
        """,
        (theme, json.dumps(story, ensure_ascii=False)),
    )
    return cur.lastrowid  # type: ignore[return-value]


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
    story: dict[str, Any],
) -> dict:
    conn.execute(
        """
        UPDATE daily_story SET story_json = ?, updated_at = datetime('now')
        WHERE id = ?
        """,
        (json.dumps(story, ensure_ascii=False), story_id),
    )
    return get_story(conn, story_id)
