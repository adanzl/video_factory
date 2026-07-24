from __future__ import annotations

import json
from typing import Any

from app.repositories import sql_exec as sql


def _row_to_dict(row: dict) -> dict:
    data = dict(row)
    if data.get("story_json"):
        data["story"] = json.loads(data["story_json"])
    else:
        data["story"] = {}
    data.pop("story_json", None)
    return data


def count_stories(
    *,
    status: str | None = None,
) -> int:
    if status:
        row = sql.fetchone(
            "SELECT COUNT(*) AS cnt FROM daily_story WHERE status = ?",
            (status,),
        )
    else:
        row = sql.fetchone(
            "SELECT COUNT(*) AS cnt FROM daily_story",
        )
    sql.commit()
    return row["cnt"] if row else 0


def list_stories(
    *,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    if status:
        rows = sql.fetchall(
            """
            SELECT id, theme, story_json, status, created_at, updated_at, job_id
            FROM daily_story
            WHERE status = ?
            ORDER BY id DESC
            LIMIT ? OFFSET ?
            """,
            (status, limit, offset),
        )
    else:
        rows = sql.fetchall(
            """
            SELECT id, theme, story_json, status, created_at, updated_at, job_id
            FROM daily_story
            ORDER BY id DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        )
    sql.commit()
    return [_row_to_dict(row) for row in rows]


def get_story(story_id: int) -> dict:
    row = sql.fetchone(
        "SELECT id, theme, story_json, status, created_at, updated_at, job_id FROM daily_story WHERE id = ?",
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
) -> int:
    cur = sql.execute(
        """
        INSERT INTO daily_story (theme, story_json, status)
        VALUES (?, ?, ?)
        """,
        (theme, json.dumps(story, ensure_ascii=False), status),
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
) -> dict:
    if story is None and status is None:
        return get_story(story_id)
    sets: list[str] = ["updated_at = datetime('now')"]
    params: list[Any] = []
    if story is not None:
        sets.append("story_json = ?")
        params.append(json.dumps(story, ensure_ascii=False))
    if status is not None:
        sets.append("status = ?")
        params.append(status)
    params.append(story_id)
    sql.execute(
        f"UPDATE daily_story SET {', '.join(sets)} WHERE id = ?",
        params,
    )
    sql.commit()
    return get_story(story_id)
