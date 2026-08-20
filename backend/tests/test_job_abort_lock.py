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


def test_is_worker_active_reflects_lock(monkeypatch):
    mgr = JobMgr()
    job_id = 79
    job_cancel.clear(job_id)
    assert not mgr.is_worker_active(job_id)
    lock = mgr._job_lock(job_id)
    assert lock.acquire(blocking=False)
    try:
        assert mgr.is_worker_active(job_id)
    finally:
        lock.release()
        assert not mgr.is_worker_active(job_id)


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


def test_abort_zombie_running_sets_abort_hold(monkeypatch, noop_atomic):
    from app.utils.job_info import job_abort_hold

    mgr = JobMgr()
    job_id = 78
    logged: list[str] = []
    updates: list[dict] = []

    monkeypatch.setattr(
        mgr,
        "get_job",
        lambda jid: {"id": jid, "status": "running", "stage": "tts", "info": {}},
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
    result = mgr.abort_job(job_id)
    assert result["status"] == "pending"
    assert updates and updates[0].get("info", {}).get("abort_hold") is True


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


def test_abort_while_worker_busy_but_pending_keeps_cancel(monkeypatch, noop_atomic):
    """DB 已 pending 但 worker 仍持锁时，中止须挂 cancel，禁止误清导致继续跑。"""
    mgr = JobMgr()
    job_id = 79
    logged: list[str] = []
    updates: list[dict] = []

    monkeypatch.setattr(
        mgr,
        "get_job",
        lambda jid: {"id": jid, "status": "pending", "stage": "segment"},
    )
    monkeypatch.setattr(
        _job_mgr_mod.repo_job_log,
        "append_log",
        lambda _jid, _stage, msg, **_k: logged.append(msg),
    )
    monkeypatch.setattr(
        _job_mgr_mod.repo_job,
        "get_job",
        lambda jid: {"id": jid, "status": "pending", "stage": "segment"},
    )

    def _update(jid, **fields):
        updates.append(fields)
        return {"id": jid, "status": fields.get("status", "pending"), **fields}

    monkeypatch.setattr(_job_mgr_mod.repo_job, "update_job", _update)

    lock = mgr._job_lock(job_id)
    assert lock.acquire(blocking=False)

    try:
        job_cancel.clear(job_id)
        result = mgr.abort_job(job_id)
        assert result["status"] == "pending"
        assert job_cancel.is_cancelled(job_id)
        assert any("waiting for worker to stop" in msg for msg in logged)
    finally:
        lock.release()
        job_cancel.clear(job_id)


def test_submit_action_respects_abort_during_prepare(monkeypatch, noop_atomic):
    """prepare 期间用户点中止，submit 不得 clear cancel 后 mark_running。"""
    mgr = JobMgr()
    job_id = 80
    status = {"v": "pending"}
    mark_running_calls: list[int] = []
    workers: list = []

    monkeypatch.setattr(
        mgr,
        "get_job",
        lambda jid: {"id": jid, "status": status["v"], "stage": "segment", "info": {}},
    )
    monkeypatch.setattr(
        _job_mgr_mod,
        "run_in_background",
        lambda fn, **_k: workers.append(fn),
    )

    def _mark_running(jid: int) -> dict:
        mark_running_calls.append(jid)
        status["v"] = "running"
        return {"id": jid, "status": "running"}

    monkeypatch.setattr(mgr, "mark_running", _mark_running)

    prepare_started = threading.Event()
    release_prepare = threading.Event()

    def slow_prepare(*_a, **_k) -> None:
        prepare_started.set()
        assert release_prepare.wait(timeout=5)
        job_cancel.request(job_id)

    monkeypatch.setattr(_job_mgr_mod, "prepare_rerun_artifacts", slow_prepare)

    job_cancel.clear(job_id)
    thread = threading.Thread(
        target=lambda: mgr.submit_action(
            job_id,
            "segment/images",
            lambda: None,
            prepare=True,
            sync=False,
        )
    )
    thread.start()
    assert prepare_started.wait(timeout=2)

    release_prepare.set()
    thread.join(timeout=5)
    assert not thread.is_alive()
    assert mark_running_calls == []
    assert workers == []
    assert status["v"] == "pending"
    assert job_cancel.is_cancelled(job_id)
    job_cancel.clear(job_id)


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


def test_advance_after_merge_enters_publish(app_ctx) -> None:
    """merge 完成后进入 publish/pending，可单独执行发布。"""
    from app.repositories import repo_job
    from worker.loop import _advance_after_stage, _reload_job
    from worker.stages.standard.merge import MergeStage

    job = repo_job.create_job(
        "merge then publish",
        stage="merge",
        status="pending",
        pipeline="chat",
    )
    result = _advance_after_stage(int(job["id"]), MergeStage, status="pending")
    assert result is None
    updated = _reload_job(int(job["id"]))
    assert updated["stage"] == "publish"
    assert updated["status"] == "pending"


def test_run_one_stage_merge_lands_on_publish(app_ctx, monkeypatch) -> None:
    """单步 merge 只执行合成，然后停在发布阶段。"""
    from app.repositories import repo_job
    from worker import loop
    from worker.stages.standard.merge import MergeStage

    executed: list[str] = []

    def fake_execute(job_id: int, stage_cls, ctx) -> None:
        executed.append(stage_cls.name)

    monkeypatch.setattr(loop, "_execute_stage", fake_execute)
    job = repo_job.create_job(
        "one stage merge",
        stage="merge",
        status="pending",
        pipeline="chat",
    )
    result = loop._run_one_stage(int(job["id"]), MergeStage, hold=True)
    assert executed == ["merge"]
    assert result["stage"] == "publish"
    assert result["status"] == "pending"


def test_run_one_stage_publish_holds_without_upload(app_ctx, monkeypatch) -> None:
    """发布阶段只补元数据，未手动投稿时停在 publish/pending。"""
    from app.repositories import repo_job
    from worker import loop
    from worker.stages.common.publish import PublishStage

    executed: list[str] = []

    def fake_execute(job_id: int, stage_cls, ctx) -> None:
        executed.append(stage_cls.name)

    monkeypatch.setattr(loop, "_execute_stage", fake_execute)
    job = repo_job.create_job(
        "one stage publish",
        stage="publish",
        status="pending",
        pipeline="chat",
    )
    result = loop._run_one_stage(int(job["id"]), PublishStage, hold=True)
    assert executed == ["publish"]
    assert result["stage"] == "publish"
    assert result["status"] == "pending"


def test_run_from_merge_stops_before_publish(app_ctx, monkeypatch) -> None:
    """连续跑时 merge 之后进入 publish/pending，不自动执行发布。"""
    from app.repositories import repo_job
    from worker import loop
    from worker.stages.standard.merge import MergeStage

    executed: list[str] = []

    def fake_execute(job_id: int, stage_cls, ctx) -> None:
        executed.append(stage_cls.name)

    monkeypatch.setattr(loop, "_execute_stage", fake_execute)
    job = repo_job.create_job(
        "run from merge",
        stage="merge",
        status="pending",
        pipeline="chat",
    )
    result = loop._run_from(int(job["id"]), MergeStage)
    assert executed == ["merge"]
    assert result["stage"] == "publish"
    assert result["status"] == "pending"


def test_chat_type_info_message_format() -> None:
    from app.services.daily_story.story_types import chat_type_info_message

    assert chat_type_info_message("A") == "[A权威翻车]"
    assert chat_type_info_message("A", success=True) == "[A权威翻车] SUCCESS"
    assert chat_type_info_message("C", success=True) == "[C公平执念] SUCCESS"
    assert chat_type_info_message(None) is None
    assert chat_type_info_message("Z") is None


def test_create_chat_job_writes_type_info(app_ctx) -> None:
    """chat 建任务时信息栏写入矛盾类型。"""
    from app.repositories import repo_daily_story
    from app.services.daily_story.daily_story_mgr import daily_story_mgr

    story_id = repo_daily_story.insert_story(
        theme="抢酸奶",
        story={
            "scene_title": "明明酸奶我先抢",
            "dialogue": [{"speaker": "昭昭", "line": "给我"}],
        },
        story_type="A",
        status="active",
    )
    job = daily_story_mgr.create_job(story_id)
    assert job["pipeline"] == "chat"
    assert job["error_message"] == "[A权威翻车]"
    assert job["status"] == "pending"


def test_mark_done_chat_writes_success_info(app_ctx) -> None:
    """chat 成功完成时信息栏写成 [类型] SUCCESS。"""
    from app.repositories import repo_daily_story, repo_job
    from app.services.job.job_mgr import job_mgr

    story_id = repo_daily_story.insert_story(
        theme="抢酸奶",
        story={
            "scene_title": "测试",
            "dialogue": [{"speaker": "昭昭", "line": "给我"}],
        },
        story_type="C",
        status="active",
    )
    job = repo_job.create_job(
        "测试",
        pipeline="chat",
        material_id=story_id,
        info={"daily_story_id": story_id},
        error_message="[C公平执念]",
    )
    done = job_mgr.mark_done(int(job["id"]))
    assert done["error_message"] == "[C公平执念] SUCCESS"


def test_update_job_publish_true_writes_chat_success_info(app_ctx) -> None:
    """标记已发布时，chat 任务信息栏同步 SUCCESS。"""
    from app.repositories import repo_daily_story, repo_job
    from app.services.job.job_mgr import job_mgr

    story_id = repo_daily_story.insert_story(
        theme="抢酸奶",
        story={
            "scene_title": "测试",
            "dialogue": [{"speaker": "昭昭", "line": "给我"}],
        },
        story_type="A",
        status="active",
    )
    job = repo_job.create_job(
        "测试",
        pipeline="chat",
        stage="publish",
        status="pending",
        material_id=story_id,
        info={"daily_story_id": story_id},
        error_message="[A权威翻车]",
    )
    updated = job_mgr.update_job(int(job["id"]), publish=True)
    assert updated["status"] == "done"
    assert updated["error_message"] == "[A权威翻车] SUCCESS"
