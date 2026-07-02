from __future__ import annotations

import json
import sqlite3
from typing import Any


def _row_to_dict(row: sqlite3.Row) -> dict:
    data = dict(row)
    if data.get("score_detail"):
        data["score_detail"] = json.loads(data["score_detail"])
    return data


def list_titles(
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
            SELECT id, title, category, template, hook, score, score_detail,
                   status, job_id, source, keyword, created_at, updated_at
            FROM title
            WHERE status = ?
            ORDER BY id DESC
            LIMIT ? OFFSET ?
            """,
            (status, limit, offset),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT id, title, category, template, hook, score, score_detail,
                   status, job_id, source, keyword, created_at, updated_at
            FROM title
            ORDER BY id DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        ).fetchall()
    return [_row_to_dict(row) for row in rows]


def get_title(conn: sqlite3.Connection, title_id: int) -> dict:
    row = conn.execute("SELECT * FROM title WHERE id = ?", (title_id,)).fetchone()
    if row is None:
        raise KeyError(f"title {title_id} not found")
    return _row_to_dict(row)


def find_by_titles(conn: sqlite3.Connection, titles: list[str]) -> set[str]:
    if not titles:
        return set()
    placeholders = ",".join("?" for _ in titles)
    rows = conn.execute(
        f"SELECT title FROM title WHERE title IN ({placeholders})",
        titles,
    ).fetchall()
    return {row["title"] for row in rows}


def insert_title(
    conn: sqlite3.Connection,
    *,
    title: str,
    category: str | None = None,
    template: str | None = None,
    hook: str | None = None,
    source: str = "manual",
    keyword: str | None = None,
) -> dict | None:
    cur = conn.execute(
        """
        INSERT OR IGNORE INTO title (title, category, template, hook, source, keyword)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (title, category, template, hook, source, keyword),
    )
    if cur.rowcount == 0:
        return None
    return get_title(conn, cur.lastrowid)


def update_title(conn: sqlite3.Connection, title_id: int, **fields: Any) -> dict:
    allowed = {
        "title",
        "category",
        "template",
        "hook",
        "score",
        "score_detail",
        "status",
        "job_id",
        "source",
        "keyword",
    }
    parts: list[str] = ["updated_at = datetime('now')"]
    values: list[Any] = []
    for key, value in fields.items():
        if key not in allowed:
            continue
        if key == "score_detail" and value is not None:
            value = json.dumps(value, ensure_ascii=False)
        parts.append(f"{key} = ?")
        values.append(value)
    values.append(title_id)
    conn.execute(
        f"UPDATE title SET {', '.join(parts)} WHERE id = ?",
        values,
    )
    return get_title(conn, title_id)


def delete_titles(conn: sqlite3.Connection, title_ids: list[int]) -> int:
    if not title_ids:
        return 0
    placeholders = ",".join("?" for _ in title_ids)
    cur = conn.execute(
        f"DELETE FROM title WHERE id IN ({placeholders})",
        title_ids,
    )
    return cur.rowcount


def list_by_ids(conn: sqlite3.Connection, title_ids: list[int]) -> list[dict]:
    if not title_ids:
        return []
    placeholders = ",".join("?" for _ in title_ids)
    rows = conn.execute(
        f"SELECT * FROM title WHERE id IN ({placeholders})",
        title_ids,
    ).fetchall()
    return [_row_to_dict(row) for row in rows]


def list_pending_score(conn: sqlite3.Connection, *, limit: int = 200) -> list[dict]:
    rows = conn.execute(
        """
        SELECT * FROM title
        WHERE status = 'pending' OR score IS NULL
        ORDER BY id
        LIMIT ?
        """,
        (max(1, min(limit, 500)),),
    ).fetchall()
    return [_row_to_dict(row) for row in rows]


def list_ids_below_score(
    conn: sqlite3.Connection,
    max_score: int,
    *,
    exclude_enqueued: bool = True,
) -> list[int]:
    """返回 score 已存在且严格低于 max_score 的选题 id。"""
    if exclude_enqueued:
        rows = conn.execute(
            """
            SELECT id FROM title
            WHERE score IS NOT NULL AND score < ? AND status != 'enqueued'
            ORDER BY id
            """,
            (max_score,),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT id FROM title
            WHERE score IS NOT NULL AND score < ?
            ORDER BY id
            """,
            (max_score,),
        ).fetchall()
    return [row["id"] for row in rows]


def list_queued(conn: sqlite3.Connection, *, limit: int = 200) -> list[dict]:
    rows = conn.execute(
        """
        SELECT * FROM title
        WHERE status = 'queued'
        ORDER BY score DESC, id
        LIMIT ?
        """,
        (max(1, min(limit, 500)),),
    ).fetchall()
    return [_row_to_dict(row) for row in rows]
