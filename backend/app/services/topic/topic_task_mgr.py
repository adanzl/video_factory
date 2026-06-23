"""选题后台任务（内存态，用于耗时 LLM / 采集流水线）。"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from app.utils.async_util import run_in_background

logger = logging.getLogger(__name__)

_TASK_TTL_SEC = 3600
_MAX_TASKS = 100


@dataclass
class TopicTask:
    id: str
    kind: str
    status: str  # running | done | failed
    created_at: float = field(default_factory=time.time)
    result: dict[str, Any] | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "task_id": self.id,
            "kind": self.kind,
            "status": self.status,
        }
        if self.status == "done" and self.result is not None:
            payload["result"] = self.result
        if self.status == "failed" and self.error:
            payload["error"] = self.error
        return payload


class TopicTaskMgr:
    def __init__(self) -> None:
        self._tasks: dict[str, TopicTask] = {}
        self._lock = threading.Lock()

    def _prune_old_tasks(self) -> None:
        now = time.time()
        expired = [
            task_id
            for task_id, task in self._tasks.items()
            if now - task.created_at > _TASK_TTL_SEC
        ]
        for task_id in expired:
            self._tasks.pop(task_id, None)

        if len(self._tasks) <= _MAX_TASKS:
            return

        sorted_ids = sorted(
            self._tasks,
            key=lambda task_id: self._tasks[task_id].created_at,
        )
        for task_id in sorted_ids[: len(self._tasks) - _MAX_TASKS]:
            self._tasks.pop(task_id, None)

    def start(self, kind: str, run: Callable[[], dict[str, Any]]) -> TopicTask:
        task = TopicTask(id=str(uuid.uuid4()), kind=kind, status="running")
        with self._lock:
            self._prune_old_tasks()
            self._tasks[task.id] = task

        def _worker() -> None:
            logger.info("[TOPIC] task %s (%s) started", task.id, kind)
            try:
                result = run()
                with self._lock:
                    task.status = "done"
                    task.result = result
                logger.info("[TOPIC] task %s (%s) done", task.id, kind)
            except Exception as exc:
                logger.exception("[TOPIC] task %s (%s) failed: %s", task.id, kind, exc)
                with self._lock:
                    task.status = "failed"
                    task.error = str(exc)

        run_in_background(_worker)
        return task

    def get(self, task_id: str) -> TopicTask | None:
        with self._lock:
            return self._tasks.get(task_id)


topic_task_mgr = TopicTaskMgr()
