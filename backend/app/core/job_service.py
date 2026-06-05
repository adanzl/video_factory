from __future__ import annotations

from app.core import pipeline
from app.repositories import job_log_repo, job_repo, segment_repo
from app.repositories.connection import connection


def create_job_from_title(
    title: str,
    *,
    skip_publish: bool = True,
) -> dict:
    with connection() as conn:
        job = job_repo.create_job(
            conn,
            title.strip(),
            skip_publish=skip_publish,
            stage="script",
            status="pending",
        )
        job_log_repo.append_log(conn, job["id"], "title", f"created job: {title}")
        return job


def reset_job_from_stage(job_id: int, from_stage: str) -> dict:
    if from_stage not in pipeline.STAGES:
        raise ValueError(f"invalid stage: {from_stage}")
    with connection() as conn:
        job = job_repo.update_job(
            conn,
            job_id,
            stage=from_stage,
            status="pending",
            fail_stage=None,
            error_message=None,
        )
        if from_stage in {"script", "title"}:
            segment_repo.delete_segments(conn, job_id)
        job_log_repo.append_log(conn, job_id, from_stage, f"reset from stage {from_stage}")
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
