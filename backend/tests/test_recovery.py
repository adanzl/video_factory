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


def test_recover_skips_abort_hold(app_ctx) -> None:
    from app.utils.job_info import merge_job_info

    job_id = _insert_job(title="aborted", stage="segment", status="running")
    repo_job.update_job(
        job_id,
        info=merge_job_info(None, abort_hold=True),
    )

    with patch.object(job_mgr, "continue_job") as mock_continue:
        from worker.recovery import recover_stuck_jobs

        count = recover_stuck_jobs()

    assert count == 0
    mock_continue.assert_not_called()
    assert repo_job.get_job(job_id)["status"] == "pending"
    logs = repo_job_log.list_logs(job_id)
    assert any("skipped auto-recover: user aborted" in log["message"] for log in logs)


def test_recover_stuck_gold_story_pending_resets_processing(
    app_ctx,
    monkeypatch,
) -> None:
    from app.repositories import repo_gold_story
    from app.services.daily_story.gold_story import gold_story_mgr as mgr_mod

    mgr_mod.reset_collect_state()
    repo_gold_story.insert_pending(
        source="bili",
        source_id="BV1RECOVER01",
        url="https://www.bilibili.com/video/BV1RECOVER01",
        title="recover test",
    )
    claimed = repo_gold_story.claim_next_pending()
    assert claimed is not None
    assert claimed["status"] == "processing"

    workers: list = []

    def fake_drain(**_kwargs):
        return {
            "phase": "process",
            "processed": 1,
            "inserted": 1,
            "inserted_rejected": 0,
            "gate_rejected": 0,
            "failed": 0,
            "results": [],
        }

    monkeypatch.setattr(mgr_mod, "drain_pending_stories", fake_drain)
    monkeypatch.setattr(
        mgr_mod,
        "run_in_os_thread",
        lambda func, **_kwargs: workers.append(func),
    )

    from worker.recovery import recover_stuck_gold_story_pending

    count = recover_stuck_gold_story_pending()
    assert count == 1
    assert len(workers) == 1

    row = repo_gold_story.get_by_source_id(source_id="BV1RECOVER01")
    assert row["status"] == "pending"

    workers[0]()
    status = mgr_mod.gold_story_mgr.collect_status()
    assert status["status"] == "done"
    assert status.get("recovered") is True
    assert status["processed"] == 1
    mgr_mod.reset_collect_state()


def test_recover_stuck_gold_story_pending_noop_when_idle(app_ctx) -> None:
    from app.services.daily_story.gold_story import gold_story_mgr as mgr_mod

    mgr_mod.reset_collect_state()
    from worker.recovery import recover_stuck_gold_story_pending

    assert recover_stuck_gold_story_pending() == 0
