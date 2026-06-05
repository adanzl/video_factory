from __future__ import annotations

import json
import sqlite3
from typing import Any


def _row_to_dict(row: sqlite3.Row) -> dict:
    data = dict(row)
    if data.get("script_json"):
        data["script_json"] = json.loads(data["script_json"])
    if data.get("quality_report"):
        data["quality_report"] = json.loads(data["quality_report"])
    data["skip_publish"] = bool(data.get("skip_publish"))
    return data


def create_job(
    conn: sqlite3.Connection,
    title: str,
    *,
    skip_publish: bool = True,
    stage: str = "script",
    status: str = "pending",
) -> dict:
    cur = conn.execute(
        """
        INSERT INTO video_job (title, stage, status, skip_publish)
        VALUES (?, ?, ?, ?)
        """,
        (title, stage, status, int(skip_publish)),
    )
    job_id = cur.lastrowid
    return get_job(conn, job_id)


def get_job(conn: sqlite3.Connection, job_id: int) -> dict:
    row = conn.execute(
        "SELECT * FROM video_job WHERE id = ?",
        (job_id,),
    ).fetchone()
    if row is None:
        raise KeyError(f"job {job_id} not found")
    return _row_to_dict(row)


def update_job(conn: sqlite3.Connection, job_id: int, **fields: Any) -> dict:
    allowed = {
        "title",
        "stage",
        "status",
        "fail_stage",
        "retry_count",
        "skip_publish",
        "script_json",
        "quality_report",
        "final_path",
        "cover_path",
        "intro_path",
        "audio_path",
        "subtitle_path",
        "error_message",
    }
    parts: list[str] = ["updated_at = datetime('now')"]
    values: list[Any] = []
    for key, value in fields.items():
        if key not in allowed:
            continue
        if key in {"script_json", "quality_report"} and value is not None:
            value = json.dumps(value, ensure_ascii=False)
        if key == "skip_publish":
            value = int(bool(value))
        parts.append(f"{key} = ?")
        values.append(value)
    values.append(job_id)
    conn.execute(
        f"UPDATE video_job SET {', '.join(parts)} WHERE id = ?",
        values,
    )
    return get_job(conn, job_id)


def claim_next_pending(conn: sqlite3.Connection) -> dict | None:
    row = conn.execute(
        """
        SELECT * FROM video_job
        WHERE status = 'pending'
        ORDER BY id
        LIMIT 1
        """
    ).fetchone()
    if row is None:
        return None
    conn.execute(
        """
        UPDATE video_job
        SET status = 'running', updated_at = datetime('now')
        WHERE id = ? AND status = 'pending'
        """,
        (row["id"],),
    )
    return get_job(conn, row["id"])
