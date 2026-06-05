from __future__ import annotations

import sqlite3


def append_log(
    conn: sqlite3.Connection,
    job_id: int,
    stage: str,
    message: str,
    level: str = "info",
) -> None:
    conn.execute(
        """
        INSERT INTO job_log (job_id, stage, level, message)
        VALUES (?, ?, ?, ?)
        """,
        (job_id, stage, level, message),
    )


def list_logs(conn: sqlite3.Connection, job_id: int) -> list[dict]:
    rows = conn.execute(
        """
        SELECT stage, level, message, created_at
        FROM job_log
        WHERE job_id = ?
        ORDER BY id
        """,
        (job_id,),
    ).fetchall()
    return [dict(row) for row in rows]
