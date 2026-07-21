from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from unittest.mock import patch

import pytest

from app.repositories.schema import apply_schema
from app.services.job.job_mgr import job_mgr


@pytest.fixture
def memory_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    apply_schema(conn)
    return conn


def _insert_job(
    conn: sqlite3.Connection,
    *,
    title: str,
    stage: str = "script",
    status: str = "pending",
    pipeline: str = "standard",
) -> int:
    conn.execute(
        """
        INSERT INTO video_job (title, stage, status, pipeline)
        VALUES (?, ?, ?, ?)
        """,
        (title, stage, status, pipeline),
    )
    conn.commit()
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def _count_logs(conn: sqlite3.Connection, job_id: int, level: str = "warning") -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS cnt FROM job_log WHERE job_id = ? AND level = ?",
        (job_id, level),
    ).fetchone()
    return row["cnt"]


@contextmanager
def _mock_connection(conn: sqlite3.Connection):
    yield conn


def test_recover_stuck_jobs_resets_all_non_terminal(
    memory_conn: sqlite3.Connection,
) -> None:
    """running 且非 done 的任务都应恢复并经 job_mgr 续跑。"""
    j1 = _insert_job(
        memory_conn, title="video gen job", stage="segment", status="running"
    )
    j2 = _insert_job(memory_conn, title="tts job", stage="tts", status="running")
    j3 = _insert_job(memory_conn, title="done job", stage="done", status="done")

    continued: list[int] = []

    def _continue(job_id: int, *, sync: bool = True, allow_running: bool = False):
        continued.append(job_id)
        return {"id": job_id, "status": "running"}

    with (
        patch(
            "worker.recovery.connection",
            side_effect=lambda: _mock_connection(memory_conn),
        ),
        patch.object(job_mgr, "continue_job", side_effect=_continue),
    ):
        from worker.recovery import recover_stuck_jobs

        count = recover_stuck_jobs()

    assert count == 2, f"expected 2 recoveries, got {count}"

    row = memory_conn.execute(
        "SELECT status FROM video_job WHERE id = ?", (j1,)
    ).fetchone()
    assert row["status"] == "pending"

    row = memory_conn.execute(
        "SELECT status FROM video_job WHERE id = ?", (j2,)
    ).fetchone()
    assert row["status"] == "pending"

    row = memory_conn.execute(
        "SELECT status FROM video_job WHERE id = ?", (j3,)
    ).fetchone()
    assert row["status"] == "done"

    assert _count_logs(memory_conn, j1) == 1
    assert _count_logs(memory_conn, j2) == 1
    assert set(continued) == {j1, j2}


def test_recover_stuck_jobs_no_stuck_jobs(memory_conn: sqlite3.Connection) -> None:
    """没有卡住的任务时，恢复数为 0。"""
    _insert_job(memory_conn, title="done job", stage="done", status="done")
    _insert_job(memory_conn, title="pending job", stage="segment", status="pending")

    with (
        patch(
            "worker.recovery.connection",
            side_effect=lambda: _mock_connection(memory_conn),
        ),
        patch.object(job_mgr, "continue_job") as cont,
    ):
        from worker.recovery import recover_stuck_jobs

        count = recover_stuck_jobs()
        cont.assert_not_called()

    assert count == 0
