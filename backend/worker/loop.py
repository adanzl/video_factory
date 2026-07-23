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
from app.utils.job_cancel import JobCancelledError, job_cancel
from app.services.job.job_mgr import job_mgr
from app.repositories import repo_job_log, repo_job
from app.repositories.connection import connection
from worker.context import JobContext
from worker.stages.base import StageExecutor

logger = logging.getLogger(__name__)


def _reload_job(job_id: int) -> dict:
    with connection() as conn:
        return repo_job.get_job(conn, job_id)


def _execute_stage(job_id: int, stage_cls: type[StageExecutor], ctx: JobContext) -> None:
    job_cancel.raise_if_cancelled(job_id)
    job = ctx.job
    executor = executor_for_stage(stage_cls.name, job)
    stage_name = stage_cls.name

    with connection() as conn:
        repo_job_log.append_log(conn, job_id, stage_name, "stage started")

    logger.info("=== %s started (pipeline=%s) ===", stage_cls.__name__, job.get("pipeline"))
    t0 = time.time()
    try:
        executor.run(ctx)
    except JobCancelledError:
        raise
    except Exception as exc:
        logger.error("=== %s failed after %.1fs: %s ===", stage_cls.__name__, time.time() - t0, exc)
        job_mgr.mark_failed(job_id, stage_name, str(exc))
        raise
    logger.info("=== %s done in %.1fs ===", stage_cls.__name__, time.time() - t0)


def _advance_after_stage(job_id: int, stage_cls: type[StageExecutor], *, status: str) -> dict | None:
    job_cancel.raise_if_cancelled(job_id)
    job = _reload_job(job_id)
    next_cls = next_stage_class(stage_cls, job)
    if next_cls is not None and next_cls.name == "publish" and pipeline.should_stop_before_publish(job):
        return job_mgr.mark_done(job_id)

    if next_cls is None:
        return job_mgr.mark_done(job_id)

    next_name = next_cls.name
    with connection() as conn:
        repo_job.update_job(conn, job_id, stage=next_name, status=status)
        repo_job_log.append_log(conn, job_id, stage_cls.name, f"stage done, next={next_name}")
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
    tts_speaker_configs: dict | None = None,
    script_segment_target_sec: float | None = None,
    script_max_title_length: int | None = None,
    script_narration_target_words: int | None = None,
    script_speech_chars_per_sec: float | None = None,
    script_skip_title_optimize: bool = False,
    script_generate_image_prompts: bool = False,
    script_supplementary_info: str | None = None,
    script_video_timeline: str | None = None,
    script_segment_index: int | None = None,
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
        tts_speaker_configs=tts_speaker_configs,
        script_segment_target_sec=script_segment_target_sec,
        script_max_title_length=script_max_title_length,
        script_narration_target_words=script_narration_target_words,
        script_speech_chars_per_sec=script_speech_chars_per_sec,
        script_skip_title_optimize=script_skip_title_optimize,
        script_generate_image_prompts=script_generate_image_prompts,
        script_supplementary_info=script_supplementary_info,
        script_video_timeline=script_video_timeline,
        script_segment_index=script_segment_index,
        material_narration=material_narration,
    )
    _execute_stage(job_id, stage_cls, ctx)

    if not advance:
        job_cancel.raise_if_cancelled(job_id)
        stage_name = stage_cls.name
        with connection() as conn:
            repo_job.update_job(conn, job_id, stage=stage_name, status="pending")
            repo_job_log.append_log(conn, job_id, stage_name, "partial stage done")
        return _reload_job(job_id)

    done = _advance_after_stage(
        job_id,
        stage_cls,
        status="pending",
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
    tts_speaker_configs: dict | None = None,
    script_segment_target_sec: float | None = None,
    script_max_title_length: int | None = None,
    script_narration_target_words: int | None = None,
    script_speech_chars_per_sec: float | None = None,
    script_skip_title_optimize: bool = False,
    script_generate_image_prompts: bool = False,
    script_supplementary_info: str | None = None,
    script_video_timeline: str | None = None,
    script_segment_index: int | None = None,
    material_narration: str | None = None,
) -> dict:
    job_mgr.mark_running(job_id)
    stage_cls: type[StageExecutor] | None = start_cls
    rerun_segments = tuple(segment_indices) if segment_indices else None
    scope = segment_scope

    while stage_cls is not None:
        job_cancel.raise_if_cancelled(job_id)
        job = _reload_job(job_id)
        ctx = JobContext.from_job(
            job,
            rerun_segment_indices=rerun_segments,
            segment_scope=scope if stage_cls.name == "segment" else None,
            intro_hold_tail_sec=intro_hold_tail_sec if stage_cls.name == "intro" else None,
            intro_orientation=intro_orientation if stage_cls.name == "intro" else None,
            tts_speech_rate=tts_speech_rate if stage_cls.name == "tts" else None,
            tts_voice_id=tts_voice_id if stage_cls.name == "tts" else None,
            tts_speaker_configs=tts_speaker_configs if stage_cls.name == "tts" else None,
            script_segment_target_sec=script_segment_target_sec if stage_cls.name == "script" else None,
            script_max_title_length=script_max_title_length if stage_cls.name == "script" else None,
            script_narration_target_words=(
                script_narration_target_words if stage_cls.name == "script" else None
            ),
            script_speech_chars_per_sec=(
                script_speech_chars_per_sec if stage_cls.name == "script" else None
            ),
            script_skip_title_optimize=(
                script_skip_title_optimize if stage_cls.name == "script" else False
            ),
            script_generate_image_prompts=(
                script_generate_image_prompts if stage_cls.name == "script" else False
            ),
            script_supplementary_info=(
                script_supplementary_info if stage_cls.name == "script" else None
            ),
            script_video_timeline=(
                script_video_timeline if stage_cls.name == "script" else None
            ),
            script_segment_index=(
                script_segment_index if stage_cls.name == "script" else None
            ),
            material_narration=material_narration if stage_cls.name == "script" else None,
        )
        _execute_stage(job_id, stage_cls, ctx)

        job_cancel.raise_if_cancelled(job_id)
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
    speech_chars_per_sec: float | None = None,
    skip_title_optimize: bool = False,
    generate_image_prompts: bool = False,
    supplementary_info: str | None = None,
    video_timeline: str | None = None,
    material_narration: str | None = None,
    segment_index: int | None = None,
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
            script_speech_chars_per_sec=speech_chars_per_sec,
            script_skip_title_optimize=skip_title_optimize,
            script_generate_image_prompts=generate_image_prompts,
            script_supplementary_info=supplementary_info,
            script_video_timeline=video_timeline,
            script_segment_index=segment_index,
            material_narration=material_narration,
        )
    return _run_one_stage(
        job_id,
        script_cls,
        hold=True,
        script_segment_target_sec=segment_target_sec,
        script_max_title_length=max_title_length,
        script_narration_target_words=narration_target_words,
        script_speech_chars_per_sec=speech_chars_per_sec,
        script_skip_title_optimize=skip_title_optimize,
        script_generate_image_prompts=generate_image_prompts,
        script_supplementary_info=supplementary_info,
        script_video_timeline=video_timeline,
        script_segment_index=segment_index,
        material_narration=material_narration,
    )


def run_script_prompts(
    job_id: int,
    *,
    prompt_type: str = "image_prompt",
    segment_indices: list[int] | None = None,
) -> dict:
    """为已有脚本生成指定类型的提示词（不重置脚本阶段）。
    type 取值：narration, visual_brief, image_prompt, motion, sd15
    """
    from app.services.script.script_mgr import script_mgr

    job = _reload_job(job_id)
    script = job.get("script_json")
    if not isinstance(script, dict):
        raise ValueError("script not ready")
    segments = script.get("segments") or []
    if not segments:
        raise ValueError("no segments")

    if prompt_type in ("image_prompt", "motion", "sd15"):
        return _run_image_prompts(job_id, segment_indices=segment_indices)
    if prompt_type == "visual_brief":
        return _run_visual_brief(job_id, segment_indices=segment_indices)
    if prompt_type == "narration":
        return _run_narration(job_id)
    raise ValueError(f"unsupported prompt_type: {prompt_type}")


def _run_image_prompts(
    job_id: int,
    *,
    segment_indices: list[int] | None = None,
) -> dict:
    """为已有脚本补全文生图提示词（含 motion_prompt、sd15_prompt_en）。"""
    from app.quality.quality_mgr import apply_quality_checks, check_image_prompt
    from app.repositories import repo_job_log, repo_job, repo_segment
    from app.services.llm.llm_mgr import llm_mgr
    from app.services.script.script_mgr import script_mgr
    from app.utils.job_info import resolve_image_provider, resolve_include_sd15_prompt
    from worker.stages.standard.script import _log_llm_timing

    job = _reload_job(job_id)
    script = job.get("script_json")
    if not isinstance(script, dict):
        raise ValueError("script not ready")
    segments = script.get("segments") or []
    if not segments:
        raise ValueError("no segments")

    image_provider = resolve_image_provider(job)
    include_sd15_prompt = resolve_include_sd15_prompt(job)
    logger.info(
        "job %s script/imagePrompts: %s image_provider=%s include_sd15_prompt=%s",
        job_id,
        f"segment_indices={segment_indices}" if segment_indices else f"segments={len(segments)}",
        image_provider,
        include_sd15_prompt,
    )

    supplementary_raw = script.get("supplementary_info")
    supplementary_info = (
        str(supplementary_raw).strip() if supplementary_raw else None
    ) or None

    updated = dict(script)

    from app.config import get_settings
    skip_quality = get_settings().skip_script_quality_check
    llm_mgr.fill_image_prompts_with_retries(
        updated,
        supplementary_info=supplementary_info,
        job=job,
        segment_indices=segment_indices,
        include_sd15_prompt=include_sd15_prompt,
        skip_quality_check=skip_quality,
    )
    _log_llm_timing(job_id, "script", updated)

    prompts = list(updated.get("llm_prompts") or [])
    img_prompt = script_mgr.build_image_prompts(
        updated,
        supplementary_info=supplementary_info,
        job=job,
        segment_indices=segment_indices,
        include_sd15_prompt=include_sd15_prompt,
    )
    prompts = [item for item in prompts if item.get("step") != "image_prompts"]
    prompts.append(img_prompt)
    updated["llm_prompts"] = prompts
    updated["generate_image_prompts"] = True
    updated["include_sd15_prompt"] = include_sd15_prompt
    updated.pop("_llm_timing", None)

    # 用 dialogue 估算时间，注入到 motion_prompt
    from app.services.media.media_mgr import _inject_mouth_motion
    for seg in updated.get("segments") or []:
        mp = seg.get("motion_prompt")
        dl = seg.get("dialogue")
        if mp and dl:
            cues = [(d.get("text", ""), len(d.get("text", "")) * 0.25) for d in dl]
            seg["motion_prompt"] = _inject_mouth_motion(mp, seg, cues)

    from app.services.script.board_timeline import parse_video_timeline
    from app.utils.media import assign_segment_timings

    segment_target_sec = updated.get("segment_target_sec")
    if segment_target_sec is None:
        segment_target_sec = get_settings().segment_target_sec
    video_timeline_raw = updated.get("video_timeline")
    assign_segment_timings(
        updated,
        segment_target_sec=float(segment_target_sec) if segment_target_sec else None,
        video_timeline=parse_video_timeline(video_timeline_raw)
        if video_timeline_raw
        else None,
    )

    from app.utils.job_info import content_style_from_job
    from app.services.script.image_prompt import wrap_image_prompts

    content_style = content_style_from_job(job)
    target_segments = [
        seg for seg in (updated.get("segments") or [])
        if segment_indices is None or int(seg.get("segment_index", 0)) in segment_indices
    ]
    wrap_image_prompts(target_segments, content_style=content_style)

    with connection() as conn:
        if skip_quality:
            from app.quality.image_prompt import skip_image_prompt_check
            quality_report = skip_image_prompt_check()
            logger.info(
                "job %s script/imagePrompts quality skipped (SKIP_SCRIPT_QUALITY_CHECK)",
                job_id,
            )
        else:
            quality_report = check_image_prompt(
                updated,
                sd15_mode=include_sd15_prompt,
                segment_indices=segment_indices,
            )
            if quality_report.level == "major":
                logger.error(
                    "job %s script/imagePrompts quality major: %s",
                    job_id,
                    quality_report.details,
                )
        apply_quality_checks(
            conn,
            job_id,
            "script",
            {"image_prompts": quality_report},
            existing_report=job.get("quality_report"),
        )
        repo_job.update_job(conn, job_id, script_json=updated)
        repo_segment.insert_segments(conn, job_id, updated["segments"])
        repo_job_log.append_log(
            conn,
            job_id,
            "script",
            (
                f"image prompts generated: segment_indices={segment_indices}, "
                f"image_provider={image_provider}, include_sd15_prompt={include_sd15_prompt}"
                if segment_indices
                else f"image prompts generated: segments={len(updated['segments'])}, "
                f"image_provider={image_provider}, include_sd15_prompt={include_sd15_prompt}"
            ),
        )
        repo_job.update_job(conn, job_id, status="pending")
    return _reload_job(job_id)


def _run_visual_brief(
    job_id: int,
    *,
    segment_indices: list[int] | None = None,
) -> dict:
    """为已有脚本重新生成画面描述（visual_brief）。

    segment_indices 非空时只更新这些分镜，其余 visual_brief 保持不变。
    """
    from app.repositories import repo_job_log, repo_job, repo_segment
    from app.services.llm.llm_mgr import llm_mgr
    from app.utils.job_info import CONTENT_STYLE_DAILY_STORY, content_style_from_job

    job = _reload_job(job_id)
    script = dict(job.get("script_json") or {})
    if not script.get("segments"):
        raise ValueError("script has no segments")

    logger.info(
        "job %s script/visualBrief: %s",
        job_id,
        f"segment_indices={segment_indices}"
        if segment_indices
        else f"segments={len(script.get('segments') or [])}",
    )

    updated = llm_mgr.fill_visual_briefs(
        script,
        job=job,
        segment_indices=segment_indices,
    )

    if content_style_from_job(job) == CONTENT_STYLE_DAILY_STORY:
        from app.services.daily_story.cast import (
            scrub_cast_leaks,
            speakers_from_dialogue,
        )

        wanted = {int(i) for i in segment_indices} if segment_indices else None
        for seg in updated.get("segments") or []:
            idx = int(seg.get("segment_index") or 0)
            if wanted is not None and idx not in wanted:
                continue
            allowed = speakers_from_dialogue(seg.get("dialogue") or [])
            cleaned = scrub_cast_leaks(str(seg.get("visual_brief") or ""), allowed)
            if cleaned != seg.get("visual_brief"):
                seg["visual_brief"] = cleaned

    with connection() as conn:
        repo_job.update_job(conn, job_id, script_json=updated)
        repo_segment.insert_segments(conn, job_id, updated.get("segments", []))
        repo_job_log.append_log(
            conn,
            job_id,
            "script",
            (
                f"visual_brief regenerated: segment_indices={segment_indices}"
                if segment_indices
                else "visual_brief regenerated"
            ),
        )
        repo_job.update_job(conn, job_id, status="pending")
    logger.info(
        "job %s visual_brief regenerated %s",
        job_id,
        f"segment_indices={segment_indices}" if segment_indices else "all",
    )
    return _reload_job(job_id)


def _run_narration(job_id: int) -> dict:
    """为已有脚本重新生成文案+分镜（narration + segments + visual_brief）。"""
    from app.repositories import repo_job_log, repo_job, repo_segment

    job = _reload_job(job_id)

    from app.services.script.script_mgr import script_mgr

    title = (job.get("title") or "").strip()
    if not title:
        raise ValueError("title is empty")

    updated = script_mgr.generate_board(
        title,
        job=job,
    )

    with connection() as conn:
        repo_job.update_job(conn, job_id, script_json=updated)
        repo_segment.insert_segments(conn, job_id, updated.get("segments", []))
        repo_job_log.append_log(
            conn, job_id, "script", "narration regenerated",
        )
        repo_job.update_job(conn, job_id, status="pending")
    logger.info("job %s narration regenerated", job_id)
    return _reload_job(job_id)


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
    """兼容入口：转发 job_mgr.run_cover（仅刷封面，不是 intro）。"""
    from app.services.job.job_mgr import job_mgr

    return job_mgr.run_cover(job_id, to_end=to_end)


def run_tts(
    job_id: int,
    *,
    to_end: bool = False,
    speech_rate: float | None = None,
    voice_id: str | None = None,
    speaker_configs: dict | None = None,
) -> dict:
    job = _reload_job(job_id)
    tts_cls = stage_class_for("tts", job)
    if to_end:
        return _run_from(
            job_id,
            tts_cls,
            tts_speech_rate=speech_rate,
            tts_voice_id=voice_id,
            tts_speaker_configs=speaker_configs,
        )
    return _run_one_stage(
        job_id,
        tts_cls,
        hold=True,
        tts_speech_rate=speech_rate,
        tts_voice_id=voice_id,
        tts_speaker_configs=speaker_configs,
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
    return _run_from(job_id, next_stage_class(segment_cls, job))


def run_segment_images(
    job_id: int,
    *,
    to_end: bool = False,
    segment_indices: list[int] | None = None,
) -> dict:
    job = _reload_job(job_id)
    if is_material_job(job):
        raise ValueError("segment stage is not available for material pipeline jobs")

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
    return _run_from(job_id, next_stage_class(segment_cls, job))


def run_segment_clips(
    job_id: int,
    *,
    to_end: bool = False,
    segment_indices: list[int] | None = None,
) -> dict:
    job = _reload_job(job_id)
    if is_material_job(job):
        raise ValueError("segment stage is not available for material pipeline jobs")

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
    return _run_from(job_id, next_stage_class(segment_cls, job))


def drain_pending() -> int:
    """领取并同步执行所有 pending（经 job_mgr 持锁）。"""
    from app.services.job.job_mgr import JobBusyError, job_mgr

    count = 0
    while True:
        with connection() as conn:
            job = repo_job.claim_next_pending(conn)
        if job is None:
            break
        try:
            job_mgr.continue_job(job["id"], sync=True, allow_running=True)
        except JobBusyError:
            logger.warning(
                "drain skipped job %s: already locked; reset to pending",
                job["id"],
            )
            with connection() as conn:
                repo_job.update_job(conn, job["id"], status="pending")
            continue
        count += 1
    return count
