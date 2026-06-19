from __future__ import annotations

import logging
import time

from app.core import pipeline
from app.services.job.job_mgr import job_mgr
from app.repositories import job_log_repo, job_repo
from app.repositories.connection import connection
from worker.context import JobContext
from worker.stages.base import StageExecutor
from worker.stages.cover import CoverStage
from worker.stages.host import HostStage
from worker.stages.intro import IntroStage
from worker.stages.merge import MergeStage
from worker.stages.publish import PublishStage
from worker.stages.registry import executor_for, stage_class
from worker.stages.script import ScriptStage
from worker.stages.segment import SegmentStage
from worker.stages.tts import TTSStage

logger = logging.getLogger(__name__)


def _reload_job(job_id: int) -> dict:
    with connection() as conn:
        return job_repo.get_job(conn, job_id)


def _execute_stage(job_id: int, stage_cls: type[StageExecutor], ctx: JobContext) -> None:
    executor = executor_for(stage_cls)
    stage_name = stage_cls.name

    with connection() as conn:
        job_log_repo.append_log(conn, job_id, stage_name, "stage started")

    logger.info("=== %s started ===", stage_cls.__name__)
    t0 = time.time()
    try:
        executor.run(ctx)
    except Exception as exc:
        logger.error("=== %s failed after %.1fs: %s ===", stage_cls.__name__, time.time() - t0, exc)
        job_mgr.mark_failed(job_id, stage_name, str(exc))
        raise
    logger.info("=== %s done in %.1fs ===", stage_cls.__name__, time.time() - t0)


def _advance_after_stage(job_id: int, stage_cls: type[StageExecutor], *, status: str) -> dict | None:
    job = _reload_job(job_id)
    if stage_cls.next_stage is PublishStage and pipeline.should_stop_before_publish(job):
        return job_mgr.mark_done(job_id)

    next_cls = stage_cls.next_stage
    if next_cls is None:
        return job_mgr.mark_done(job_id)

    next_name = next_cls.name
    with connection() as conn:
        job_repo.update_job(conn, job_id, stage=next_name, status=status)
        job_log_repo.append_log(conn, job_id, stage_cls.name, f"stage done, next={next_name}")
    return None


def _run_one_stage(
    job_id: int,
    stage_cls: type[StageExecutor],
    *,
    segment_indices: list[int] | None = None,
    segment_scope: str | None = None,
    advance: bool = True,
) -> dict:
    job = _reload_job(job_id)
    ctx = JobContext.from_job(
        job,
        rerun_segment_indices=tuple(segment_indices) if segment_indices else None,
        segment_scope=segment_scope,
    )
    _execute_stage(job_id, stage_cls, ctx)

    if not advance:
        stage_name = stage_cls.name
        with connection() as conn:
            job_repo.update_job(conn, job_id, stage=stage_name, status="pending")
            job_log_repo.append_log(conn, job_id, stage_name, "partial stage done")
        return _reload_job(job_id)

    done = _advance_after_stage(job_id, stage_cls, status="pending")
    if done is not None:
        return done
    return _reload_job(job_id)


def _run_from(
    job_id: int,
    start_cls: type[StageExecutor],
    *,
    segment_indices: list[int] | None = None,
    segment_scope: str | None = None,
) -> dict:
    job_mgr.mark_running(job_id)
    stage_cls: type[StageExecutor] | None = start_cls
    rerun_segments = tuple(segment_indices) if segment_indices else None
    scope = segment_scope

    while stage_cls is not None:
        job = _reload_job(job_id)
        ctx = JobContext.from_job(
            job,
            rerun_segment_indices=rerun_segments,
            segment_scope=scope if stage_cls is SegmentStage else None,
        )
        _execute_stage(job_id, stage_cls, ctx)

        done = _advance_after_stage(job_id, stage_cls, status="running")
        if done is not None:
            return done

        stage_cls = stage_cls.next_stage
        rerun_segments = None
        scope = None

    return _reload_job(job_id)


def run_job(
    job_id: int,
    *,
    from_stage: str | None = None,
    only_stage: str | None = None,
    segment_indices: list[int] | None = None,
    segment_scope: str | None = None,
) -> dict:
    """CLI / drain_pending 入口；字符串 stage 名仅在此处解析一次。"""
    if from_stage and only_stage:
        raise ValueError("--from-stage 与 --only-stage 不能同时使用")

    if only_stage:
        job_mgr.mark_running(job_id)
        return _run_one_stage(
            job_id,
            stage_class(only_stage),
            segment_indices=segment_indices,
            segment_scope=segment_scope,
        )

    if from_stage:
        return _run_from(
            job_id,
            stage_class(from_stage),
            segment_indices=segment_indices,
            segment_scope=segment_scope,
        )

    job = _reload_job(job_id)
    if job["stage"] == "done":
        return job
    return _run_from(job_id, stage_class(job["stage"]))


def run_script(job_id: int, *, to_end: bool = False) -> dict:
    if to_end:
        return _run_from(job_id, ScriptStage)
    return _run_one_stage(job_id, ScriptStage)


def run_intro(job_id: int, *, to_end: bool = False) -> dict:
    if to_end:
        return _run_from(job_id, IntroStage)
    return _run_one_stage(job_id, IntroStage)


def run_cover(job_id: int, *, to_end: bool = False) -> dict:
    if to_end:
        return _run_from(job_id, CoverStage)
    return _run_one_stage(job_id, CoverStage)


def run_tts(job_id: int, *, to_end: bool = False) -> dict:
    if to_end:
        return _run_from(job_id, TTSStage)
    return _run_one_stage(job_id, TTSStage)


def run_merge(job_id: int, *, to_end: bool = False) -> dict:
    if to_end:
        return _run_from(job_id, MergeStage)
    return _run_one_stage(job_id, MergeStage)


def run_publish(job_id: int, *, to_end: bool = False) -> dict:
    if to_end:
        return _run_from(job_id, PublishStage)
    return _run_one_stage(job_id, PublishStage)


def run_segment_images(
    job_id: int,
    *,
    to_end: bool = False,
    segment_indices: list[int] | None = None,
) -> dict:
    job_mgr.mark_running(job_id)
    _run_one_stage(
        job_id,
        SegmentStage,
        segment_indices=segment_indices,
        segment_scope="images",
        advance=False,
    )
    if not to_end:
        return _reload_job(job_id)

    _run_one_stage(
        job_id,
        SegmentStage,
        segment_indices=segment_indices,
        segment_scope="clips",
        advance=True,
    )
    return _run_from(job_id, HostStage)


def run_segment_clips(
    job_id: int,
    *,
    to_end: bool = False,
    segment_indices: list[int] | None = None,
) -> dict:
    job_mgr.mark_running(job_id)
    _run_one_stage(
        job_id,
        SegmentStage,
        segment_indices=segment_indices,
        segment_scope="clips",
        advance=True,
    )
    if not to_end:
        return _reload_job(job_id)
    return _run_from(job_id, HostStage)


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
