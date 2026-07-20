"""claim_next_pending 原子领取。"""

from __future__ import annotations

import sqlite3

from app.repositories import repo_job
from app.repositories.schema import apply_schema


def test_claim_next_pending_sets_running_and_returns_job() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    apply_schema(conn)
    created = repo_job.create_job(conn, "claim me")
    job_id = int(created["id"])
    repo_job.update_job(conn, job_id, status="pending")

    claimed = repo_job.claim_next_pending(conn)
    assert claimed is not None
    assert claimed["id"] == job_id
    assert claimed["status"] == "running"

    assert repo_job.claim_next_pending(conn) is None


def test_claim_next_pending_empty_queue() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    apply_schema(conn)
    assert repo_job.claim_next_pending(conn) is None


def test_claim_next_pending_skips_non_pending() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    apply_schema(conn)
    a = repo_job.create_job(conn, "running")
    b = repo_job.create_job(conn, "pending")
    repo_job.update_job(conn, int(a["id"]), status="running")
    repo_job.update_job(conn, int(b["id"]), status="pending")

    claimed = repo_job.claim_next_pending(conn)
    assert claimed is not None
    assert claimed["id"] == int(b["id"])
    assert claimed["status"] == "running"
