from __future__ import annotations

import logging
import time

from app.core import pipeline
from app.core.pipelines import (
    executor_for_stage,
    is_material_job,
    next_stage_class,
    stage_class_for,
)
from app.services.job.job_mgr import job_mgr
from app.repositories import job_log_repo, job_repo
from app.repositories.connection import connection
from worker.context import JobContext
from worker.stages.base import StageExecutor

logger = logging.getLogger(__name__)


def _reload_job(job_id: int) -> dict:
    with connection() as conn:
        return job_repo.get_job(conn, job_id)


def _execute_stage(job_id: int, stage_cls: type[StageExecutor], ctx: JobContext) -> None:
    job = ctx.job
    executor = executor_for_stage(stage_cls.name, job)
    stage_name = stage_cls.name

    with connection() as conn:
        job_log_repo.append_log(conn, job_id, stage_name, "stage started")

    logger.info("=== %s started (pipeline=%s) ===", stage_cls.__name__, job.get("pipeline"))
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
    next_cls = next_stage_class(stage_cls, job)
    if next_cls is not None and next_cls.name == "publish" and pipeline.should_stop_before_publish(job):
        return job_mgr.mark_done(job_id)

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
    hold: bool = False,
    intro_hold_tail_sec: float | None = None,
    intro_orientation: str | None = None,
    tts_speech_rate: float | None = None,
    tts_voice_id: str | None = None,
    script_segment_target_sec: float | None = None,
    script_max_title_length: int | None = None,
    script_narration_target_words: int | None = None,
    script_skip_title_optimize: bool = False,
    script_supplementary_info: str | None = None,
    material_narration: str | None = None,
) -> dict:
    job = _reload_job(job_id)
    ctx = JobContext.from_job(
        job,
        rerun_segment_indices=tuple(segment_indices) if segment_indices else None,
        segment_scope=segment_scope,
        intro_hold_tail_sec=intro_hold_tail_sec,
        intro_orientation=intro_orientation,
        tts_speech_rate=tts_speech_rate,
        tts_voice_id=tts_voice_id,
        script_segment_target_sec=script_segment_target_sec,
        script_max_title_length=script_max_title_length,
        script_narration_target_words=script_narration_target_words,
        script_skip_title_optimize=script_skip_title_optimize,
        script_supplementary_info=script_supplementary_info,
        material_narration=material_narration,
    )
    _execute_stage(job_id, stage_cls, ctx)

    if not advance:
        stage_name = stage_cls.name
        with connection() as conn:
            job_repo.update_job(conn, job_id, stage=stage_name, status="pending")
            job_log_repo.append_log(conn, job_id, stage_name, "partial stage done")
        return _reload_job(job_id)

    done = _advance_after_stage(
        job_id,
        stage_cls,
        status="idle" if hold else "pending",
    )
    if done is not None:
        return done
    return _reload_job(job_id)


def _run_from(
    job_id: int,
    start_cls: type[StageExecutor],
    *,
    segment_indices: list[int] | None = None,
    segment_scope: str | None = None,
    intro_hold_tail_sec: float | None = None,
    intro_orientation: str | None = None,
    tts_speech_rate: float | None = None,
    tts_voice_id: str | None = None,
    script_segment_target_sec: float | None = None,
    script_max_title_length: int | None = None,
    script_narration_target_words: int | None = None,
    script_skip_title_optimize: bool = False,
    script_supplementary_info: str | None = None,
    material_narration: str | None = None,
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
            segment_scope=scope if stage_cls.name == "segment" else None,
            intro_hold_tail_sec=intro_hold_tail_sec if stage_cls.name == "intro" else None,
            intro_orientation=intro_orientation if stage_cls.name == "intro" else None,
            tts_speech_rate=tts_speech_rate if stage_cls.name == "tts" else None,
            tts_voice_id=tts_voice_id if stage_cls.name == "tts" else None,
            script_segment_target_sec=script_segment_target_sec if stage_cls.name == "script" else None,
            script_max_title_length=script_max_title_length if stage_cls.name == "script" else None,
            script_narration_target_words=(
                script_narration_target_words if stage_cls.name == "script" else None
            ),
            script_skip_title_optimize=(
                script_skip_title_optimize if stage_cls.name == "script" else False
            ),
            script_supplementary_info=(
                script_supplementary_info if stage_cls.name == "script" else None
            ),
            material_narration=material_narration if stage_cls.name == "script" else None,
        )
        _execute_stage(job_id, stage_cls, ctx)

        done = _advance_after_stage(job_id, stage_cls, status="running")
        if done is not None:
            return done

        stage_cls = next_stage_class(stage_cls, job)
        rerun_segments = None
        scope = None
        material_narration = None

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

    job = _reload_job(job_id)

    if only_stage:
        job_mgr.mark_running(job_id)
        return _run_one_stage(job_id, stage_class_for(only_stage, job))

    if from_stage:
        return _run_from(job_id, stage_class_for(from_stage, job))

    if job["stage"] == "done":
        return job
    return _run_from(job_id, stage_class_for(job["stage"], job))


def run_prepare(job_id: int, *, to_end: bool = False) -> dict:
    from worker.stages.material.prepare import MaterialPrepareStage

    if to_end:
        return _run_from(job_id, MaterialPrepareStage)
    return _run_one_stage(job_id, MaterialPrepareStage, hold=True)


def run_script(
    job_id: int,
    *,
    to_end: bool = False,
    segment_target_sec: float | None = None,
    max_title_length: int | None = None,
    narration_target_words: int | None = None,
    skip_title_optimize: bool = False,
    supplementary_info: str | None = None,
    material_narration: str | None = None,
) -> dict:
    job = _reload_job(job_id)
    script_cls = stage_class_for("script", job)
    if to_end:
        return _run_from(
            job_id,
            script_cls,
            script_segment_target_sec=segment_target_sec,
            script_max_title_length=max_title_length,
            script_narration_target_words=narration_target_words,
            script_skip_title_optimize=skip_title_optimize,
            script_supplementary_info=supplementary_info,
            material_narration=material_narration,
        )
    return _run_one_stage(
        job_id,
        script_cls,
        hold=True,
        script_segment_target_sec=segment_target_sec,
        script_max_title_length=max_title_length,
        script_narration_target_words=narration_target_words,
        script_skip_title_optimize=skip_title_optimize,
        script_supplementary_info=supplementary_info,
        material_narration=material_narration,
    )


def run_intro(
    job_id: int,
    *,
    to_end: bool = False,
    hold_tail_sec: float | None = None,
    orientation: str | None = None,
) -> dict:
    job = _reload_job(job_id)
    intro_cls = stage_class_for("intro", job)
    if to_end:
        return _run_from(
            job_id,
            intro_cls,
            intro_hold_tail_sec=hold_tail_sec,
            intro_orientation=orientation,
        )
    return _run_one_stage(
        job_id,
        intro_cls,
        hold=True,
        intro_hold_tail_sec=hold_tail_sec,
        intro_orientation=orientation,
    )


def run_cover(job_id: int, *, to_end: bool = False) -> dict:
    job = _reload_job(job_id)
    cover_cls = stage_class_for("cover", job)
    if to_end:
        return _run_from(job_id, cover_cls)
    return _run_one_stage(job_id, cover_cls, hold=True)


def run_tts(
    job_id: int,
    *,
    to_end: bool = False,
    speech_rate: float | None = None,
    voice_id: str | None = None,
) -> dict:
    job = _reload_job(job_id)
    tts_cls = stage_class_for("tts", job)
    if to_end:
        return _run_from(
            job_id,
            tts_cls,
            tts_speech_rate=speech_rate,
            tts_voice_id=voice_id,
        )
    return _run_one_stage(
        job_id,
        tts_cls,
        hold=True,
        tts_speech_rate=speech_rate,
        tts_voice_id=voice_id,
    )


def run_merge(job_id: int, *, to_end: bool = False) -> dict:
    job = _reload_job(job_id)
    merge_cls = stage_class_for("merge", job)
    if to_end:
        return _run_from(job_id, merge_cls)
    return _run_one_stage(job_id, merge_cls, hold=True)


def run_publish(job_id: int, *, to_end: bool = False) -> dict:
    job = _reload_job(job_id)
    publish_cls = stage_class_for("publish", job)
    if to_end:
        return _run_from(job_id, publish_cls)
    return _run_one_stage(job_id, publish_cls, hold=True)


def run_segment_all(
    job_id: int,
    *,
    to_end: bool = False,
    segment_indices: list[int] | None = None,
) -> dict:
    job = _reload_job(job_id)
    if is_material_job(job):
        raise ValueError("segment stage is not available for material pipeline jobs")
    from worker.stages.standard.host import HostStage

    segment_cls = stage_class_for("segment", job)
    job_mgr.mark_running(job_id)
    _run_one_stage(
        job_id,
        segment_cls,
        segment_indices=segment_indices,
        segment_scope="all",
        advance=True,
    )
    if not to_end:
        return _reload_job(job_id)
    return _run_from(job_id, HostStage)


def run_segment_images(
    job_id: int,
    *,
    to_end: bool = False,
    segment_indices: list[int] | None = None,
) -> dict:
    job = _reload_job(job_id)
    if is_material_job(job):
        raise ValueError("segment stage is not available for material pipeline jobs")
    from worker.stages.standard.host import HostStage

    segment_cls = stage_class_for("segment", job)
    job_mgr.mark_running(job_id)
    _run_one_stage(
        job_id,
        segment_cls,
        segment_indices=segment_indices,
        segment_scope="images",
        advance=False,
    )
    if not to_end:
        return _reload_job(job_id)

    _run_one_stage(
        job_id,
        segment_cls,
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
    job = _reload_job(job_id)
    if is_material_job(job):
        raise ValueError("segment stage is not available for material pipeline jobs")
    from worker.stages.standard.host import HostStage

    segment_cls = stage_class_for("segment", job)
    job_mgr.mark_running(job_id)
    _run_one_stage(
        job_id,
        segment_cls,
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
