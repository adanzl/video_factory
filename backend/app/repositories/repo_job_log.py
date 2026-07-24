from __future__ import annotations

from app.repositories import sql_exec as sql


def append_log(
    job_id: int,
    stage: str,
    message: str,
    level: str = "info",
) -> None:
    sql.execute(
        """
        INSERT INTO job_log (job_id, stage, level, message)
        VALUES (?, ?, ?, ?)
        """,
        (job_id, stage, level, message),
    )
    sql.commit()


def delete_logs(job_id: int) -> int:
    result = sql.execute(
        "DELETE FROM job_log WHERE job_id = ?",
        (job_id,),
    )
    sql.commit()
    return result.rowcount


def list_logs(job_id: int) -> list[dict]:
    rows = sql.fetchall(
        """
        SELECT stage, level, message, created_at
        FROM job_log
        WHERE job_id = ?
        ORDER BY id
        """,
        (job_id,),
    )
    sql.commit()
    return rows
