from __future__ import annotations

import logging
import time

from app.core import pipeline

logger = logging.getLogger(__name__)
from app.core.job_service import mark_done, mark_failed, mark_running
from app.repositories import job_log_repo, job_repo
from app.repositories.connection import connection
from worker.context import JobContext
from worker.stages.cover import CoverStage
from worker.stages.host import HostStage
from worker.stages.intro import IntroStage
from worker.stages.merge import MergeStage
from worker.stages.publish import PublishStage
from worker.stages.script import ScriptStage
from worker.stages.segment import SegmentStage
from worker.stages.title import TitleStage
from worker.stages.tts import TTSStage

EXECUTORS = {
    "title": TitleStage(),
    "script": ScriptStage(),
    "cover": CoverStage(),
    "intro": IntroStage(),
    "tts": TTSStage(),
    "segment": SegmentStage(),
    "host": HostStage(),
    "merge": MergeStage(),
    "publish": PublishStage(),
}


def _reload_job(job_id: int) -> dict:
    with connection() as conn:
        return job_repo.get_job(conn, job_id)


def _run_one_stage(
    job_id: int,
    stage: str,
    *,
    segment_indices: list[int] | None = None,
) -> dict:
    job = _reload_job(job_id)
    rerun_segments = tuple(segment_indices) if segment_indices else None
    ctx = JobContext.from_job(job, rerun_segment_indices=rerun_segments)
    executor = EXECUTORS.get(stage)
    if executor is None:
        raise ValueError(f"no executor for stage {stage}")

    with connection() as conn:
        job_log_repo.append_log(conn, job_id, stage, "stage started")

    t0 = time.time()
    try:
        executor.run(ctx)
    except Exception as exc:
        logger.error("stage %s failed after %.1fs: %s", stage, time.time() - t0, exc)
        mark_failed(job_id, stage, str(exc))
        raise
    elapsed = time.time() - t0
    logger.info("stage %s done in %.1fs", stage, elapsed)

    job = _reload_job(job_id)
    next_stage = pipeline.next_stage(stage)
    if next_stage == "publish" and job.get("skip_publish"):
        return mark_done(job_id)
    with connection() as conn:
        job_repo.update_job(conn, job_id, stage=next_stage, status="pending")
        job_log_repo.append_log(conn, job_id, stage, f"stage done, next={next_stage}")
    return _reload_job(job_id)


def run_job(
    job_id: int,
    *,
    from_stage: str | None = None,
    only_stage: str | None = None,
    segment_indices: list[int] | None = None,
) -> dict:
    if from_stage and only_stage:
        raise ValueError("--from-stage 与 --only-stage 不能同时使用")

    job = _reload_job(job_id)
    mark_running(job_id)
    stage = from_stage or only_stage or job["stage"]
    if stage == "done":
        return job

    if only_stage:
        if only_stage != stage:
            stage = only_stage
        return _run_one_stage(job_id, stage, segment_indices=segment_indices)

    rerun_segments = tuple(segment_indices) if segment_indices else None

    while stage != "done":
        job = _reload_job(job_id)
        ctx = JobContext.from_job(job, rerun_segment_indices=rerun_segments)
        executor = EXECUTORS.get(stage)
        if executor is None:
            raise ValueError(f"no executor for stage {stage}")

        with connection() as conn:
            job_log_repo.append_log(conn, job_id, stage, "stage started")
        logger.info("=== stage %s started ===", stage)
        t0 = time.time()
        try:
            executor.run(ctx)
        except Exception as exc:
            logger.error("=== stage %s failed after %.1fs: %s ===", stage, time.time() - t0, exc)
            mark_failed(job_id, stage, str(exc))
            raise
        logger.info("=== stage %s done in %.1fs ===", stage, time.time() - t0)

        next_stage = pipeline.next_stage(stage)
        job = _reload_job(job_id)
        if next_stage == "publish" and job.get("skip_publish"):
            mark_done(job_id)
            return _reload_job(job_id)
        with connection() as conn:
            job_repo.update_job(conn, job_id, stage=next_stage, status="running")
        stage = next_stage
        rerun_segments = None
        if stage == "done":
            mark_done(job_id)
            break

    return _reload_job(job_id)


def drain_pending() -> int:
    count = 0
    while True:
        with connection() as conn:
            job = job_repo.claim_next_pending(conn)
        if job is None:
            break
        run_job(job["id"])
        count += 1
    return count
