from __future__ import annotations

from app.core.job_reset import prepare_job_rerun, reset_job_from_stage
from app.repositories import job_log_repo, job_repo
from app.repositories.connection import connection


def create_job_from_title(
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


def mark_running(job_id: int) -> dict:
    with connection() as conn:
        return job_repo.update_job(conn, job_id, status="running")


def mark_done(job_id: int) -> dict:
    with connection() as conn:
        return job_repo.update_job(conn, job_id, stage="done", status="done")


def mark_failed(job_id: int, stage: str, message: str) -> dict:
    with connection() as conn:
        job_log_repo.append_log(conn, job_id, stage, message, level="error")
        return job_repo.update_job(
            conn,
            job_id,
            status="failed",
            error_message=message,
        )


__all__ = [
    "create_job_from_title",
    "mark_done",
    "mark_failed",
    "mark_running",
    "prepare_job_rerun",
    "reset_job_from_stage",
]
