from __future__ import annotations

import sqlite3
from typing import Any


def _row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)


def create_material_video(
    conn: sqlite3.Connection,
    *,
    name: str,
    file_path: str,
    duration_sec: float | None = None,
    width: int | None = None,
    height: int | None = None,
    size_bytes: int | None = None,
    thumbnail_path: str | None = None,
    note: str | None = None,
) -> dict:
    cur = conn.execute(
        """
        INSERT INTO material_video (
            name, file_path, duration_sec, width, height,
            size_bytes, thumbnail_path, note
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            name,
            file_path,
            duration_sec,
            width,
            height,
            size_bytes,
            thumbnail_path,
            note,
        ),
    )
    return get_material_video(conn, cur.lastrowid)


def get_material_video(conn: sqlite3.Connection, material_id: int) -> dict:
    row = conn.execute(
        "SELECT * FROM material_video WHERE id = ? AND status IN ('active', 'analyzing')",
        (material_id,),
    ).fetchone()
    if row is None:
        raise KeyError(f"material {material_id} not found")
    return _row_to_dict(row)


def count_material_videos(
    conn: sqlite3.Connection,
) -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS cnt FROM material_video WHERE status != 'deleted'",
    ).fetchone()
    return row["cnt"] if row else 0


def list_material_videos(
    conn: sqlite3.Connection,
    *,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    rows = conn.execute(
        """
        SELECT id, name, file_path, duration_sec, width, height,
               size_bytes, thumbnail_path, note, status, job_id,
               created_at, updated_at
        FROM material_video
        WHERE status != 'deleted'
        ORDER BY id DESC
        LIMIT ? OFFSET ?
        """,
        (limit, offset),
    ).fetchall()
    return [_row_to_dict(row) for row in rows]


def update_material_video(conn: sqlite3.Connection, material_id: int, **fields: Any) -> dict:
    allowed = {
        "name",
        "note",
        "status",
        "job_id",
        "file_path",
        "duration_sec",
        "width",
        "height",
        "size_bytes",
        "thumbnail_path",
    }
    parts: list[str] = ["updated_at = datetime('now')"]
    values: list[Any] = []
    for key, value in fields.items():
        if key not in allowed:
            continue
        parts.append(f"{key} = ?")
        values.append(value)
    if len(parts) == 1:
        raise ValueError("no updatable fields")
    values.append(material_id)
    conn.execute(
        f"UPDATE material_video SET {', '.join(parts)} WHERE id = ?",
        values,
    )
    return get_material_video(conn, material_id)


def soft_delete_material_video(conn: sqlite3.Connection, material_id: int) -> None:
    cur = conn.execute(
        """
        UPDATE material_video
        SET status = 'deleted', updated_at = datetime('now')
        WHERE id = ? AND status = 'active'
        """,
        (material_id,),
    )
    if cur.rowcount == 0:
        raise KeyError(f"material {material_id} not found")
