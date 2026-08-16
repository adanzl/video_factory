"""Abort / 后台锁：防止中止后立刻重入。"""

from __future__ import annotations

import importlib
import threading
from contextlib import nullcontext

import pytest

from app.services.job.job_mgr import JobBusyError, JobMgr
from app.utils.job_cancel import job_cancel

_job_mgr_mod = importlib.import_module("app.services.job.job_mgr")
_db_mod = importlib.import_module("app.repositories.database")


def test_run_in_background_holds_lock_until_worker_done(monkeypatch):
    mgr = JobMgr()
    job_id = 4242
    status = {"v": "pending"}
    started = threading.Event()
    release_run = threading.Event()
    workers: list = []

    monkeypatch.setattr(
        mgr, "get_job", lambda jid: {"id": jid, "status": status["v"]}
    )

    def _mark_running(jid: int) -> dict:
        status["v"] = "running"
        return {"id": jid, "status": "running"}

    monkeypatch.setattr(mgr, "mark_running", _mark_running)
    monkeypatch.setattr(_job_mgr_mod, "prepare_rerun_artifacts", lambda *_a, **_k: None)
    monkeypatch.setattr(
        _job_mgr_mod,
        "run_in_background",
        lambda fn, **_k: workers.append(fn),
    )
    monkeypatch.setattr(
        _db_mod,
        "get_app",
        lambda: type("FakeApp", (), {"app_context": staticmethod(nullcontext)})(),
    )

    def slow_run() -> None:
        started.set()
        assert release_run.wait(timeout=5)
        status["v"] = "pending"

    job_cancel.clear(job_id)
    mgr._run_in_background(job_id, "tts", slow_run)
    assert len(workers) == 1
    assert mgr._job_lock(job_id).locked()

    thread = threading.Thread(target=workers[0])
    thread.start()
    assert started.wait(timeout=2)

    with pytest.raises(JobBusyError):
        mgr._run_in_background(job_id, "segment", lambda: None)

    release_run.set()
    thread.join(timeout=5)
    assert not thread.is_alive()
    assert not mgr._job_lock(job_id).locked()

    workers.clear()
    mgr._run_in_background(job_id, "segment", lambda: None)
    assert len(workers) == 1
    workers[0]()
    assert not mgr._job_lock(job_id).locked()


def test_abort_with_active_worker_resets_pending_but_keeps_cancel(monkeypatch, noop_atomic):
    mgr = JobMgr()
    job_id = 77
    logged: list[str] = []
    updates: list[dict] = []

    monkeypatch.setattr(
        mgr,
        "get_job",
        lambda jid: {"id": jid, "status": "running", "stage": "tts"},
    )

    monkeypatch.setattr(
        _job_mgr_mod.repo_job_log,
        "append_log",
        lambda _jid, _stage, msg, **_k: logged.append(msg),
    )
    monkeypatch.setattr(
        _job_mgr_mod.repo_job,
        "get_job",
        lambda jid: {"id": jid, "status": "pending", "stage": "tts"},
    )

    def _update(jid, **fields):
        updates.append(fields)
        return {"id": jid, "status": fields.get("status", "pending"), **fields}

    monkeypatch.setattr(_job_mgr_mod.repo_job, "update_job", _update)

    # 模拟 worker 持锁
    lock = mgr._job_lock(job_id)
    assert lock.acquire(blocking=False)

    try:
        job_cancel.clear(job_id)
        result = mgr.abort_job(job_id)
        assert result["status"] == "pending"
        assert job_cancel.is_cancelled(job_id)
        assert updates and updates[0].get("status") == "pending"
        assert logged and "reset to pending" in logged[0]
    finally:
        lock.release()
        job_cancel.clear(job_id)


def test_abort_zombie_running_resets_to_pending(monkeypatch, noop_atomic):
    mgr = JobMgr()
    job_id = 78
    logged: list[str] = []
    updates: list[dict] = []

    monkeypatch.setattr(
        mgr,
        "get_job",
        lambda jid: {"id": jid, "status": "running", "stage": "tts"},
    )

    monkeypatch.setattr(
        _job_mgr_mod.repo_job_log,
        "append_log",
        lambda _jid, _stage, msg, **_k: logged.append(msg),
    )

    def _update(jid, **fields):
        updates.append(fields)
        return {"id": jid, "status": fields.get("status"), **fields}

    monkeypatch.setattr(_job_mgr_mod.repo_job, "update_job", _update)

    job_cancel.clear(job_id)
    # 未持锁 → 视为僵尸 running
    result = mgr.abort_job(job_id)
    assert result["status"] == "pending"
    assert updates and updates[0].get("status") == "pending"
    assert not job_cancel.is_cancelled(job_id)
    assert logged and "no active worker" in logged[0]


def test_mark_done_while_cancelled_becomes_aborted(monkeypatch, noop_atomic):
    mgr = JobMgr()
    job_id = 88
    updates: list[dict] = []

    monkeypatch.setattr(
        mgr,
        "get_job",
        lambda jid: {"id": jid, "status": "running", "stage": "tts"},
    )
    monkeypatch.setattr(
        _job_mgr_mod.repo_job_log,
        "append_log",
        lambda *_a, **_k: None,
    )

    def _update(jid, **fields):
        updates.append(fields)
        return {"id": jid, "status": fields.get("status"), **fields}

    monkeypatch.setattr(_job_mgr_mod.repo_job, "update_job", _update)

    job_cancel.request(job_id)
    result = mgr.mark_done(job_id)
    assert result["status"] == "pending"
    assert updates and updates[0].get("status") == "pending"
    assert not job_cancel.is_cancelled(job_id)


def test_update_job_publish_true_marks_done(app_ctx) -> None:
    """标记已发布时，未在跑的任务自动切到 done。"""
    from app.repositories import repo_job
    from app.services.job.job_mgr import job_mgr

    job = repo_job.create_job(
        "publish marks done",
        skip_publish=False,
        stage="publish",
        status="pending",
        pipeline="chat",
    )
    job_id = int(job["id"])
    updated = job_mgr.update_job(job_id, publish=True)
    assert updated["publish"] is True
    assert updated["stage"] == "done"
    assert updated["status"] == "done"


def test_update_job_publish_true_keeps_running(app_ctx) -> None:
    """运行中标记已发布，不打断 worker。"""
    from app.repositories import repo_job
    from app.services.job.job_mgr import job_mgr

    job = repo_job.create_job(
        "publish while running",
        stage="merge",
        status="running",
    )
    job_id = int(job["id"])
    updated = job_mgr.update_job(job_id, publish=True)
    assert updated["publish"] is True
    assert updated["stage"] == "merge"
    assert updated["status"] == "running"


def test_advance_after_merge_marks_done_without_skip_publish(app_ctx) -> None:
    """merge 完成后即使 skip_publish=0，也不停在 publish/pending。"""
    from app.repositories import repo_job
    from worker.loop import _advance_after_stage
    from worker.stages.standard.merge import MergeStage

    job = repo_job.create_job(
        "merge then done",
        skip_publish=False,
        stage="merge",
        status="pending",
        pipeline="chat",
    )
    result = _advance_after_stage(int(job["id"]), MergeStage, status="pending")
    assert result is not None
    assert result["stage"] == "done"
    assert result["status"] == "done"
