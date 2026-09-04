"""run_in_os_thread 在 gevent 环境下的集成验证。"""

from __future__ import annotations

import subprocess
import sys
import textwrap
import threading
import time
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[1]


def _run_gevent_simulation_script() -> subprocess.CompletedProcess[str]:
    script = textwrap.dedent(
        f"""
        import sys
        sys.path.insert(0, {str(_BACKEND)!r})

        from gevent import monkey
        monkey.patch_all(subprocess=True, thread=False, queue=False)

        import threading
        import time

        import gevent
        from gevent import sleep as gevent_sleep

        import tempfile
        from pathlib import Path

        from app.config import config
        from app.core import create_app
        from app.repositories import repo_gold_story
        from app.repositories.database import get_app
        from app.utils.async_util import _on_gevent_hub, run_in_os_thread

        errors: list[str] = []
        hub_ticks: list[float] = []
        done = threading.Event()

        with tempfile.TemporaryDirectory() as tmp:
            config.sqlite_path = Path(tmp) / "sim.db"
            app = create_app()

            def worker() -> None:
                try:
                    if _on_gevent_hub():
                        errors.append("worker must run off gevent hub")
                        return
                    with get_app().app_context():
                        outcome = repo_gold_story.insert_pending(
                            source="bili",
                            source_id="BV1OSTHREAD01",
                            url="https://www.bilibili.com/video/BV1OSTHREAD01",
                            title="os thread sim",
                        )
                        if outcome.get("action") != "insert":
                            errors.append(f"unexpected insert outcome: {{outcome}}")
                        # 模拟 whisper/ffmpeg 阻塞
                        time.sleep(1.2)
                        row = repo_gold_story.get_by_source_id(source_id="BV1OSTHREAD01")
                        if row is None:
                            errors.append("row missing after insert")
                except Exception as exc:
                    errors.append(f"worker failed: {{exc!r}}")
                finally:
                    done.set()

            def hub_counter() -> None:
                for _ in range(30):
                    hub_ticks.append(time.time())
                    gevent_sleep(0.05)

            with app.app_context():
                run_in_os_thread(worker)
                counter = gevent.spawn(hub_counter)
                deadline = time.time() + 8
                while not done.is_set() and time.time() < deadline:
                    gevent_sleep(0.05)
                if not done.is_set():
                    errors.append("worker timeout")
                gevent.joinall([counter], timeout=2)

            if len(hub_ticks) < 10:
                errors.append(f"hub not responsive: ticks={{len(hub_ticks)}}")
            if errors:
                print("FAIL", "; ".join(errors))
                raise SystemExit(1)
            print("PASS ticks={{}}".format(len(hub_ticks)))
        """
    )
    return subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(_BACKEND),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def test_run_in_os_thread_gevent_hub_stays_responsive_with_db() -> None:
    """子线程写库 + 阻塞 sleep 时，hub greenlet 仍应能调度。"""
    proc = _run_gevent_simulation_script()
    assert proc.returncode == 0, (
        f"simulation failed\nstdout={proc.stdout}\nstderr={proc.stderr}"
    )
    assert "PASS" in proc.stdout


def test_run_in_os_thread_subprocess_off_hub(app_ctx) -> None:
    """gevent patch 下 OS 线程应走 run_subprocess_cmd（safe），不能裸 subprocess.run。"""
    from app.utils.async_util import _on_gevent_hub, run_in_os_thread, run_subprocess_cmd

    done = threading.Event()
    result: dict[str, object] = {}

    def worker() -> None:
        from app.repositories.database import get_app

        with get_app().app_context():
            result["on_hub"] = _on_gevent_hub()
            if _on_gevent_hub():
                result["subprocess_ok"] = False
                done.set()
                return
            code, out, _err = run_subprocess_cmd(
                [sys.executable, "-c", "print('ok')"],
                timeout=10,
                check=True,
            )
            result["subprocess_ok"] = code == 0 and out.strip() == "ok"
        done.set()

    run_in_os_thread(worker)
    assert done.wait(timeout=5), "worker did not finish"
    assert result.get("on_hub") is False
    assert result.get("subprocess_ok") is True


def test_gold_story_reimport_worker_runs_in_os_thread(app_ctx, monkeypatch) -> None:
    """金故事 reimport：OS 线程内应能更新 _REIMPORT_STATE。"""
    from app.services.gold_story import gold_story_mgr as mgr_mod

    mgr_mod.reset_collect_state()
    finished = threading.Event()
    captured: dict[str, object] = {}

    def fake_reimport(**_kwargs):
        time.sleep(0.3)
        return {
            "requested": 1,
            "updated": 1,
            "inserted": 0,
            "rejected": 0,
            "failed": 0,
            "ok": 1,
            "results": [{"id": 1, "source_id": "BV1TEST", "action": "ok"}],
        }

    monkeypatch.setattr(mgr_mod, "reimport_stories", fake_reimport)

    real_run = mgr_mod.run_in_os_thread

    def capture_and_run(func, **kwargs):
        captured["func"] = func
        real_run(func, **kwargs)

    monkeypatch.setattr(mgr_mod, "run_in_os_thread", capture_and_run)

    mgr_mod.gold_story_mgr.reimport(source_ids=["BV1TEST"])
    assert "func" in captured

    worker = threading.Thread(target=captured["func"])  # type: ignore[arg-type]
    worker.start()
    assert worker.is_alive()

    # 主线程（pytest）在 worker 阻塞期间仍可继续
    time.sleep(0.05)
    status = mgr_mod.gold_story_mgr.reimport_status()
    assert status["status"] == "running"

    worker.join(timeout=5)
    assert not worker.is_alive()
    status = mgr_mod.gold_story_mgr.reimport_status()
    assert status["status"] == "done"
    assert status["ok"] == 1
    finished.set()
    assert finished.is_set()
