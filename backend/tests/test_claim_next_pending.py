"""claim_next_pending 原子领取。"""

from __future__ import annotations

from app.repositories import repo_job


def test_claim_next_pending_sets_running_and_returns_job(app_ctx) -> None:
    created = repo_job.create_job("claim me")
    job_id = int(created["id"])
    repo_job.update_job(job_id, status="pending")

    claimed = repo_job.claim_next_pending()
    assert claimed is not None
    assert claimed["id"] == job_id
    assert claimed["status"] == "running"

    assert repo_job.claim_next_pending() is None


def test_claim_next_pending_empty_queue(app_ctx) -> None:
    assert repo_job.claim_next_pending() is None


def test_claim_next_pending_skips_non_pending(app_ctx) -> None:
    a = repo_job.create_job("running")
    b = repo_job.create_job("pending")
    repo_job.update_job(int(a["id"]), status="running")
    repo_job.update_job(int(b["id"]), status="pending")

    claimed = repo_job.claim_next_pending()
    assert claimed is not None
    assert claimed["id"] == int(b["id"])
    assert claimed["status"] == "running"
