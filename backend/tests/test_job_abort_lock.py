"""Abort / 后台锁：防止中止后立刻重入。"""

from __future__ import annotations

import importlib
import threading

import pytest

from app.services.job.job_mgr import JobBusyError, JobMgr
from app.utils.job_cancel import job_cancel

_job_mgr_mod = importlib.import_module("app.services.job.job_mgr")


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
    monkeypatch.setattr(_job_mgr_mod, "prepare_for_action", lambda *_a, **_k: None)
    monkeypatch.setattr(
        _job_mgr_mod,
        "run_in_background",
        lambda fn, **_k: workers.append(fn),
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


def test_abort_with_active_worker_keeps_running(monkeypatch):
    mgr = JobMgr()
    job_id = 77
    logged: list[str] = []

    monkeypatch.setattr(
        mgr,
        "get_job",
        lambda jid: {"id": jid, "status": "running", "stage": "tts"},
    )

    class _Conn:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr(_job_mgr_mod, "connection", lambda: _Conn())
    monkeypatch.setattr(
        _job_mgr_mod.repo_job_log,
        "append_log",
        lambda _c, _jid, _stage, msg, **_k: logged.append(msg),
    )
    monkeypatch.setattr(
        _job_mgr_mod.repo_job,
        "get_job",
        lambda _c, jid: {"id": jid, "status": "running", "stage": "tts"},
    )

    def _forbid_update(*_a, **_k):
        pytest.fail("active-worker abort must not update status")

    monkeypatch.setattr(_job_mgr_mod.repo_job, "update_job", _forbid_update)

    # 模拟 worker 持锁
    lock = mgr._job_lock(job_id)
    assert lock.acquire(blocking=False)

    try:
        job_cancel.clear(job_id)
        result = mgr.abort_job(job_id)
        assert result["status"] == "running"
        assert job_cancel.is_cancelled(job_id)
        assert logged and "waiting for worker" in logged[0]
    finally:
        lock.release()
        job_cancel.clear(job_id)


def test_abort_zombie_running_resets_to_pending(monkeypatch):
    mgr = JobMgr()
    job_id = 78
    logged: list[str] = []
    updates: list[dict] = []

    monkeypatch.setattr(
        mgr,
        "get_job",
        lambda jid: {"id": jid, "status": "running", "stage": "tts"},
    )

    class _Conn:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr(_job_mgr_mod, "connection", lambda: _Conn())
    monkeypatch.setattr(
        _job_mgr_mod.repo_job_log,
        "append_log",
        lambda _c, _jid, _stage, msg, **_k: logged.append(msg),
    )

    def _update(_c, jid, **fields):
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


def test_mark_done_while_cancelled_becomes_aborted(monkeypatch):
    mgr = JobMgr()
    job_id = 88
    updates: list[dict] = []

    class _Conn:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr(_job_mgr_mod, "connection", lambda: _Conn())
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

    def _update(_c, jid, **fields):
        updates.append(fields)
        return {"id": jid, "status": fields.get("status"), **fields}

    monkeypatch.setattr(_job_mgr_mod.repo_job, "update_job", _update)

    job_cancel.request(job_id)
    result = mgr.mark_done(job_id)
    assert result["status"] == "pending"
    assert updates and updates[0].get("status") == "pending"
    assert not job_cancel.is_cancelled(job_id)
