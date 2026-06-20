"""Job 业务管理：CRUD、状态流转、stage 动作提交。"""

from __future__ import annotations

import logging
import shutil
import threading
from collections.abc import Callable
from pathlib import Path

from app.services.job.job_reset import prepare_for_action, prepare_job_rerun
from app.repositories import job_log_repo, job_repo, segment_repo
from app.repositories.connection import connection
from app.utils.async_util import run_in_background

logger = logging.getLogger(__name__)

_API_UPDATABLE = frozenset({"title", "skip_publish", "status"})
_VALID_STATUSES = frozenset({"pending", "running", "done", "failed"})


class JobBusyError(Exception):
    """Job 正在执行，拒绝并发动作。"""


class JobMgr:
    """Job 管理器。"""

    def __init__(self) -> None:
        self._locks: dict[int, threading.Lock] = {}
        self._lock_guard = threading.Lock()

    def _job_lock(self, job_id: int) -> threading.Lock:
        with self._lock_guard:
            lock = self._locks.get(job_id)
            if lock is None:
                lock = threading.Lock()
                self._locks[job_id] = lock
            return lock

    def list_jobs(
        self,
        *,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        with connection() as conn:
            return job_repo.list_jobs(conn, status=status, limit=limit, offset=offset)

    def get_job(self, job_id: int) -> dict:
        with connection() as conn:
            return job_repo.get_job(conn, job_id)

    def get_segments(self, job_id: int) -> list[dict]:
        with connection() as conn:
            job_repo.get_job(conn, job_id)
            return segment_repo.list_segments(conn, job_id)

    def get_logs(self, job_id: int) -> list[dict]:
        with connection() as conn:
            job_repo.get_job(conn, job_id)
            return job_log_repo.list_logs(conn, job_id)

    def create_from_title(
        self,
        title: str,
        *,
        skip_publish: bool = True,
    ) -> dict:
        cleaned = title.strip()
        if not cleaned:
            raise ValueError("title is empty")
        with connection() as conn:
            job = job_repo.create_job(
                conn,
                cleaned,
                skip_publish=skip_publish,
                stage="script",
                status="pending",
            )
            job_log_repo.append_log(conn, job["id"], "title", f"created job: {cleaned}")
            return job

    def update_job(self, job_id: int, **fields: object) -> dict:
        updates = {k: v for k, v in fields.items() if k in _API_UPDATABLE}
        if not updates:
            raise ValueError("no updatable fields provided")
        if "title" in updates:
            title = updates["title"]
            if not isinstance(title, str) or not title.strip():
                raise ValueError("title is empty")
            updates["title"] = title.strip()
        if "skip_publish" in updates and not isinstance(updates["skip_publish"], bool):
            raise ValueError("skip_publish must be boolean")
        if "status" in updates and updates["status"] not in _VALID_STATUSES:
            raise ValueError(f"status must be one of: {', '.join(sorted(_VALID_STATUSES))}")
        with connection() as conn:
            job_repo.get_job(conn, job_id)
            job = job_repo.update_job(conn, job_id, **updates)
            job_log_repo.append_log(conn, job_id, "api", f"updated fields: {', '.join(updates)}")
            return job

    def delete_job(self, job_id: int) -> None:
        with connection() as conn:
            job_repo.delete_job(conn, job_id)

    def clean_job_files(self, job_id: int) -> dict:
        """删除任务本地媒体文件，保留数据库记录。"""
        lock = self._job_lock(job_id)
        if not lock.acquire(blocking=False):
            raise JobBusyError(f"job {job_id} is running")

        try:
            job = self.get_job(job_id)
            if job["status"] == "running":
                raise JobBusyError(f"job {job_id} is running")

            from app.config import get_settings

            media_dir: Path = get_settings().video_data_dir / str(job_id)
            cleaned = False
            if media_dir.exists():
                shutil.rmtree(media_dir)
                cleaned = True

            with connection() as conn:
                job_log_repo.append_log(conn, job_id, "api", "cleaned local media files")

            return {
                "id": job_id,
                "cleaned": cleaned,
                "media_dir": str(media_dir),
            }
        finally:
            lock.release()

    def mark_running(self, job_id: int) -> dict:
        with connection() as conn:
            return job_repo.update_job(conn, job_id, status="running")

    def mark_done(self, job_id: int) -> dict:
        with connection() as conn:
            return job_repo.update_job(conn, job_id, stage="done", status="done")

    def mark_failed(self, job_id: int, stage: str, message: str) -> dict:
        with connection() as conn:
            job_log_repo.append_log(conn, job_id, stage, message, level="error")
            return job_repo.update_job(
                conn,
                job_id,
                status="failed",
                error_message=message,
            )

    def _run_in_background(
        self,
        job_id: int,
        action: str,
        run: Callable[[], None],
        *,
        segment_indices: list[int] | None = None,
    ) -> dict:
        lock = self._job_lock(job_id)
        if not lock.acquire(blocking=False):
            raise JobBusyError(f"job {job_id} is running")

        try:
            job = self.get_job(job_id)
            if job["status"] == "running":
                raise JobBusyError(f"job {job_id} is running")

            prepare_for_action(job_id, action, segment_indices=segment_indices)
            self.mark_running(job_id)

            fail_stage = action.split("/")[0]

            def _worker() -> None:
                logger.info("job %s action [%s] started in background thread", job_id, action)
                try:
                    run()
                except Exception as exc:
                    logger.exception("job %s action %s failed: %s", job_id, action, exc)
                    job = self.get_job(job_id)
                    if job["status"] == "running":
                        self.mark_failed(job_id, fail_stage, str(exc))

            run_in_background(_worker)
            return self.get_job(job_id)
        finally:
            lock.release()

    def run_script(
        self,
        job_id: int,
        *,
        to_end: bool = False,
        title: str | None = None,
        segment_target_sec: float | None = None,
        max_title_length: int | None = None,
        narration_target_words: int | None = None,
    ) -> dict:
        """生成文案。实现：worker/loop.run_script → worker/stages/script.py"""
        from worker.loop import run_script

        if title is not None:
            cleaned = title.strip()
            if not cleaned:
                raise ValueError("title is empty")
            job = self.get_job(job_id)
            if cleaned != job["title"]:
                self.update_job(job_id, title=cleaned)

        return self._run_in_background(
            job_id,
            "script",
            lambda: run_script(
                job_id,
                to_end=to_end,
                segment_target_sec=segment_target_sec,
                max_title_length=max_title_length,
                narration_target_words=narration_target_words,
            ),
        )

    def run_intro(self, job_id: int, *, to_end: bool = False, hold_tail_sec: float | None = None) -> dict:
        """生成片头。实现：worker/loop.run_intro → worker/stages/intro.py"""
        from worker.loop import run_intro

        return self._run_in_background(
            job_id,
            "intro",
            lambda: run_intro(job_id, to_end=to_end, hold_tail_sec=hold_tail_sec),
        )

    def run_cover(self, job_id: int, *, to_end: bool = False) -> dict:
        """生成封面。实现：worker/loop.run_cover → worker/stages/cover.py"""
        from worker.loop import run_cover

        return self._run_in_background(
            job_id,
            "cover",
            lambda: run_cover(job_id, to_end=to_end),
        )

    def run_tts(
        self,
        job_id: int,
        *,
        to_end: bool = False,
        speech_rate: float | None = None,
        voice_id: str | None = None,
    ) -> dict:
        """生成配音。实现：worker/loop.run_tts → worker/stages/tts.py"""
        from worker.loop import run_tts

        return self._run_in_background(
            job_id,
            "tts",
            lambda: run_tts(
                job_id,
                to_end=to_end,
                speech_rate=speech_rate,
                voice_id=voice_id,
            ),
        )

    def run_segment_all(
        self,
        job_id: int,
        *,
        to_end: bool = False,
        segment_indices: list[int] | None = None,
    ) -> dict:
        """重跑分镜静图与图生视频。实现：worker/loop.run_segment_all → worker/stages/segment.py"""
        from worker.loop import run_segment_all

        return self._run_in_background(
            job_id,
            "segment/all",
            lambda: run_segment_all(
                job_id,
                to_end=to_end,
                segment_indices=segment_indices,
            ),
            segment_indices=segment_indices,
        )

    def run_segment_images(
        self,
        job_id: int,
        *,
        to_end: bool = False,
        segment_indices: list[int] | None = None,
    ) -> dict:
        """重出分镜静图。实现：worker/loop.run_segment_images → worker/stages/segment.py"""
        from worker.loop import run_segment_images

        return self._run_in_background(
            job_id,
            "segment/images",
            lambda: run_segment_images(
                job_id,
                to_end=to_end,
                segment_indices=segment_indices,
            ),
            segment_indices=segment_indices,
        )

    def run_segment_clips(
        self,
        job_id: int,
        *,
        to_end: bool = False,
        segment_indices: list[int] | None = None,
    ) -> dict:
        """重跑图生视频。实现：worker/loop.run_segment_clips → worker/stages/segment.py"""
        from worker.loop import run_segment_clips

        return self._run_in_background(
            job_id,
            "segment/clips",
            lambda: run_segment_clips(
                job_id,
                to_end=to_end,
                segment_indices=segment_indices,
            ),
            segment_indices=segment_indices,
        )

    def run_merge(self, job_id: int, *, to_end: bool = False) -> dict:
        """合成成片。实现：worker/loop.run_merge → worker/stages/merge.py"""
        from worker.loop import run_merge

        return self._run_in_background(
            job_id,
            "merge",
            lambda: run_merge(job_id, to_end=to_end),
        )

    def run_publish(self, job_id: int, *, to_end: bool = False) -> dict:
        """发布。实现：worker/loop.run_publish → worker/stages/publish.py"""
        from worker.loop import run_publish

        return self._run_in_background(
            job_id,
            "publish",
            lambda: run_publish(job_id, to_end=to_end),
        )

    def prepare_rerun(
        self,
        job_id: int,
        stage: str,
        *,
        segment_indices: list[int] | None = None,
        mode: str = "from",
    ) -> dict:
        return prepare_job_rerun(
            job_id,
            stage,
            segment_indices=segment_indices,
            mode=mode,
        )


job_mgr = JobMgr()

__all__ = ["JobBusyError", "JobMgr", "job_mgr"]
