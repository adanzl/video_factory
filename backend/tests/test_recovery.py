from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from unittest.mock import patch

import pytest

from app.repositories.schema import apply_schema


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


def test_recover_stuck_jobs_only_recovers_segment_stage(memory_conn: sqlite3.Connection) -> None:
    """验证 recover_stuck_jobs 只恢复 running+segment 的任务。"""
    j1 = _insert_job(memory_conn, title="video gen job", stage="segment", status="running")
    j2 = _insert_job(memory_conn, title="tts job", stage="tts", status="running")
    j3 = _insert_job(memory_conn, title="done job", stage="done", status="done")

    run_job_calls: list[int] = []

    def _fake_run_job(job_id: int) -> None:
        run_job_calls.append(job_id)

    def _run_now(func):
        func()

    with (
        patch("worker.recovery.connection", side_effect=lambda: _mock_connection(memory_conn)),
        patch("worker.recovery.run_in_background", side_effect=_run_now),
        patch("worker.loop.run_job", side_effect=_fake_run_job),
    ):
        from worker.recovery import recover_stuck_jobs

        count = recover_stuck_jobs()

    assert count == 1, f"expected 1 recovery, got {count}"

    # j1 should be reset to pending
    row = memory_conn.execute(
        "SELECT status FROM video_job WHERE id = ?", (j1,)
    ).fetchone()
    assert row["status"] == "pending"

    # j2 should still be running
    row = memory_conn.execute(
        "SELECT status FROM video_job WHERE id = ?", (j2,)
    ).fetchone()
    assert row["status"] == "running", "non-segment jobs should not be recovered"

    # j3 should still be done
    row = memory_conn.execute(
        "SELECT status FROM video_job WHERE id = ?", (j3,)
    ).fetchone()
    assert row["status"] == "done"

    # j1 should have a warning log
    assert _count_logs(memory_conn, j1) == 1

    # run_job should have been called for j1
    assert run_job_calls == [j1]


def test_recover_stuck_jobs_no_stuck_jobs(memory_conn: sqlite3.Connection) -> None:
    """没有卡住的任务时，恢复数为 0。"""
    _insert_job(memory_conn, title="done job", stage="done", status="done")
    _insert_job(memory_conn, title="pending job", stage="segment", status="pending")

    with (
        patch("worker.recovery.connection", side_effect=lambda: _mock_connection(memory_conn)),
        patch("worker.recovery.run_in_background"),
        patch("worker.loop.run_job"),
    ):
        from worker.recovery import recover_stuck_jobs

        count = recover_stuck_jobs()

    assert count == 0
