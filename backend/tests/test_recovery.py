from __future__ import annotations

from unittest.mock import patch

import pytest

from app.repositories import repo_job, repo_job_log
from app.services.job.job_mgr import job_mgr


def _insert_job(
    *,
    title: str,
    stage: str = "script",
    status: str = "pending",
    pipeline: str = "standard",
) -> int:
    job = repo_job.create_job(
        title,
        stage=stage,
        status=status,
        pipeline=pipeline,
    )
    if status != "pending":
        repo_job.update_job(int(job["id"]), status=status, stage=stage)
    return int(job["id"])


def test_recover_stuck_jobs_resets_all_non_terminal(app_ctx) -> None:
    j1 = _insert_job(title="video gen job", stage="segment", status="running")
    j2 = _insert_job(title="tts job", stage="tts", status="running")
    j3 = _insert_job(title="done job", stage="done", status="done")

    continued: list[int] = []

    def _continue(job_id: int, *, sync: bool = True, allow_running: bool = False):
        continued.append(job_id)
        return {"id": job_id, "status": "running"}

    with patch.object(job_mgr, "continue_job", side_effect=_continue):
        from worker.recovery import recover_stuck_jobs

        count = recover_stuck_jobs()

    assert count == 2, f"expected 2 recoveries, got {count}"

    assert repo_job.get_job(j1)["status"] == "pending"
    assert repo_job.get_job(j2)["status"] == "pending"
    assert repo_job.get_job(j3)["status"] == "done"
    assert continued == [j1, j2]


def test_recover_stuck_jobs_logs_warning(app_ctx) -> None:
    job_id = _insert_job(title="stuck", stage="script", status="running")

    with patch.object(job_mgr, "continue_job", return_value={"id": job_id}):
        from worker.recovery import recover_stuck_jobs

        recover_stuck_jobs()

    logs = repo_job_log.list_logs(job_id)
    assert any("auto-recovered" in log["message"] for log in logs)


def test_recover_skips_busy_job(app_ctx) -> None:
    from app.services.job.job_mgr import JobBusyError

    job_id = _insert_job(title="busy", stage="tts", status="running")

    with patch.object(
        job_mgr, "continue_job", side_effect=JobBusyError("busy")
    ):
        from worker.recovery import recover_stuck_jobs

        count = recover_stuck_jobs()

    assert count == 1
    assert repo_job.get_job(job_id)["status"] == "pending"
