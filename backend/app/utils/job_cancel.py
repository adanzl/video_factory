"""运行中任务的中止信号（进程内，按 job_id）。"""

from __future__ import annotations

import threading


class JobCancelledError(Exception):
    """用户请求中止任务。"""


class JobCancelRegistry:
    def __init__(self) -> None:
        self._cancelled: set[int] = set()
        self._lock = threading.Lock()

    def request(self, job_id: int) -> None:
        with self._lock:
            self._cancelled.add(job_id)

    def clear(self, job_id: int) -> None:
        with self._lock:
            self._cancelled.discard(job_id)

    def is_cancelled(self, job_id: int) -> bool:
        with self._lock:
            return job_id in self._cancelled

    def raise_if_cancelled(self, job_id: int) -> None:
        if self.is_cancelled(job_id):
            raise JobCancelledError(f"job {job_id} aborted")


def raise_if_job_cancelled(job: dict | None) -> None:
    """从 job 字典读取 id 并检查中止信号（LLM 长调用返回后用）。"""
    if not job:
        return
    job_id = job.get("id")
    if job_id is not None:
        job_cancel.raise_if_cancelled(int(job_id))


job_cancel = JobCancelRegistry()

__all__ = ["JobCancelledError", "JobCancelRegistry", "job_cancel", "raise_if_job_cancelled"]
