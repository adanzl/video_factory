"""重跑前清理：清空目标 stage 产物及其下游，保留上游。"""

from __future__ import annotations

import shutil
from pathlib import Path

from app.core.pipelines import (
    PIPELINE_MATERIAL,
    is_material_job,
    resolve_pipeline,
    stage_index,
    stages_for,
)
from app.repositories import job_log_repo, job_repo, segment_repo
from app.repositories.connection import connection

__all__ = ["prepare_for_action", "prepare_job_rerun", "reset_job_from_stage"]

# 重跑这些 stage 时只刷新自身产物，不影响下游（封面/发布不导致成片或配音失效）
_STAGES_SKIP_DOWNSTREAM_CLEAR = frozenset({"cover", "publish"})


def _material_script_reset_seed(job: dict) -> dict | None:
    script_json = job.get("script_json")
    if not isinstance(script_json, dict):
        return None
    pending = script_json.get("pending_narration")
    if pending:
        return {
            "pending_narration": pending,
            "script_mode": script_json.get("script_mode", "manual"),
        }
    if script_json.get("script_mode") == "manual" and script_json.get("narration"):
        return {
            "pending_narration": script_json["narration"],
            "script_mode": "manual",
        }
    return None


def _delete_files(paths: list[Path]) -> None:
    for path in paths:
        if path.exists():
            path.unlink()


def _archive_file(src: Path, dest: Path) -> None:
    if not src.exists():
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)


def _archive_wan_clips(media_dir: Path, *, clip_names: list[str] | None = None) -> None:
    """重跑前将图生视频分镜 clip 归档到 segments_wan/，避免被覆盖删除。"""
    clips_dir = media_dir / "segments"
    if not clips_dir.exists():
        return
    clips = (
        [clips_dir / name for name in clip_names]
        if clip_names
        else sorted(clips_dir.glob("*.mp4"))
    )
    if not any(p.exists() for p in clips):
        return
    archive_dir = media_dir / "segments_wan"
    archive_dir.mkdir(parents=True, exist_ok=True)
    for clip in clips:
        if clip.exists():
            _archive_file(clip, archive_dir / clip.name)


def _archive_wan_merge(media_dir: Path) -> None:
    """重跑 merge 前归档成片，保留图生视频版本。"""
    for src_name, dest_name in (
        ("final.mp4", "final_wan.mp4"),
        ("body.mp4", "body_wan.mp4"),
        ("body_with_audio.mp4", "body_with_audio_wan.mp4"),
    ):
        _archive_file(media_dir / src_name, media_dir / dest_name)


def _clear_merge_artifacts(media_dir: Path) -> None:
    _archive_wan_merge(media_dir)
    _delete_files(
        [
            media_dir / "final.mp4",
            media_dir / "body.mp4",
            media_dir / "body_with_audio.mp4",
        ]
    )


def _clear_tts_artifacts(conn, job_id: int, media_dir: Path) -> None:
    segment_repo.clear_segment_durations(conn, job_id)
    job_repo.update_job(conn, job_id, audio_path=None, subtitle_path=None, tts_usage_json=None)
    audio_dir = media_dir / "audio"
    for name in ("narration.mp3", "subtitles.srt", "subtitle_cues.json"):
        _delete_files([audio_dir / name])
    clips_dir = audio_dir / "clips"
    if clips_dir.exists():
        for pattern in ("*.mp3",):
            for clip in clips_dir.glob(pattern):
                clip.unlink()


def _clear_segment_clips(conn, job_id: int, media_dir: Path) -> None:
    """TTS 变更后：clip 依赖字幕时间轴，静图可保留。"""
    _archive_wan_clips(media_dir)
    segment_repo.clear_segment_clips(conn, job_id, None)
    segment_repo.clear_segment_durations(conn, job_id)
    clips_dir = media_dir / "segments"
    if clips_dir.exists():
        for clip in clips_dir.glob("*.mp4"):
            clip.unlink()


def _clear_all_segment_media(conn, job_id: int, media_dir: Path) -> None:
    _archive_wan_clips(media_dir)
    segment_repo.clear_segment_media(conn, job_id, None)
    images_dir = media_dir / "images"
    if images_dir.exists():
        for img in images_dir.glob("*.png"):
            img.unlink()
    clips_dir = media_dir / "segments"
    if clips_dir.exists():
        for clip in clips_dir.glob("*.mp4"):
            clip.unlink()


def _clear_partial_segment_media(
    conn,
    job_id: int,
    media_dir: Path,
    segment_indices: list[int],
) -> None:
    segment_repo.clear_segment_clips_only(conn, job_id, segment_indices)
    clip_names = [f"{index}.mp4" for index in segment_indices]
    _archive_wan_clips(media_dir, clip_names=clip_names)
    for index in segment_indices:
        _delete_files([media_dir / "segments" / f"{index}.mp4"])


def _clear_downstream(conn, job_id: int, stage: str, media_dir: Path, job: dict) -> None:
    """清空 stage 之后各阶段的产物（不含 stage 自身）。"""
    if stage in _STAGES_SKIP_DOWNSTREAM_CLEAR:
        return
    if not media_dir.exists():
        return

    pipe = resolve_pipeline(job)
    idx = stage_index(stage, job)

    if idx < stage_index("cover", job):
        job_repo.update_job(conn, job_id, cover_path=None)
        _delete_files([media_dir / "cover.jpg"])

    if pipe == PIPELINE_MATERIAL:
        if idx < stage_index("merge", job):
            job_repo.update_job(conn, job_id, final_path=None)
            _clear_merge_artifacts(media_dir)
        return

    if idx < stage_index("segment", job):
        _clear_segment_clips(conn, job_id, media_dir)

    if idx < stage_index("merge", job):
        job_repo.update_job(conn, job_id, final_path=None)
        _clear_merge_artifacts(media_dir)


def _clear_segment_images(
    conn,
    job_id: int,
    media_dir: Path,
    segment_indices: list[int] | None,
) -> None:
    segment_repo.clear_segment_media(conn, job_id, segment_indices)
    if segment_indices:
        for index in segment_indices:
            _delete_files([media_dir / "images" / f"{index}.png"])
            _delete_files([media_dir / "segments" / f"{index}.mp4"])
        return
    images_dir = media_dir / "images"
    if images_dir.exists():
        for img in images_dir.glob("*.png"):
            img.unlink()
    _archive_wan_clips(media_dir)
    clips_dir = media_dir / "segments"
    if clips_dir.exists():
        for clip in clips_dir.glob("*.mp4"):
            clip.unlink()


def _clear_stage_self(
    conn,
    job_id: int,
    stage: str,
    media_dir: Path,
    job: dict,
    *,
    segment_indices: list[int] | None,
    segment_scope: str | None = None,
) -> None:
    """清空 stage 自身产物，以便重新执行。"""
    pipe = resolve_pipeline(job)

    if stage == "prepare":
        _delete_files([media_dir / "base.mp4", media_dir / "base_meta.json"])
        job_repo.update_job(conn, job_id, base_path=None)
        return

    if stage in {"title", "script"}:
        preserve_base = pipe == PIPELINE_MATERIAL and stage == "script"
        reset_script_json = None
        if preserve_base:
            reset_script_json = _material_script_reset_seed(job)
        segment_repo.delete_segments(conn, job_id)
        job_repo.update_job(
            conn,
            job_id,
            script_json=reset_script_json,
            audio_path=None,
            subtitle_path=None,
            tts_usage_json=None,
            intro_path=None,
            cover_path=None,
            final_path=None,
            quality_report=None,
        )
        if media_dir.exists():
            if not preserve_base:
                _delete_files([media_dir / "base.mp4", media_dir / "base_meta.json"])
            _clear_tts_artifacts(conn, job_id, media_dir)
            if pipe != PIPELINE_MATERIAL:
                _clear_all_segment_media(conn, job_id, media_dir)
            _clear_merge_artifacts(media_dir)
            merge_work = media_dir / "merge_work"
            if merge_work.exists():
                shutil.rmtree(merge_work)
        return

    if stage == "intro":
        job_repo.update_job(conn, job_id, intro_path=None, cover_path=None)
        if media_dir.exists():
            _delete_files([media_dir / "intro.mp4", media_dir / "intro.png"])
        return

    if stage == "cover":
        job_repo.update_job(conn, job_id, cover_path=None)
        if media_dir.exists():
            _delete_files([media_dir / "cover.jpg"])
        return

    if stage == "tts" and media_dir.exists():
        _clear_tts_artifacts(conn, job_id, media_dir)
        return

    if stage == "segment" and media_dir.exists():
        if segment_scope == "clips":
            if segment_indices:
                _clear_partial_segment_media(conn, job_id, media_dir, segment_indices)
            else:
                _clear_segment_clips(conn, job_id, media_dir)
        elif segment_scope == "images":
            _clear_segment_images(conn, job_id, media_dir, segment_indices)
        elif segment_indices:
            _clear_partial_segment_media(conn, job_id, media_dir, segment_indices)
        else:
            _clear_all_segment_media(conn, job_id, media_dir)
        return

    if stage == "merge":
        job_repo.update_job(conn, job_id, final_path=None)
        if media_dir.exists():
            _clear_merge_artifacts(media_dir)


def prepare_for_action(
    job_id: int,
    action: str,
    *,
    segment_indices: list[int] | None = None,
) -> dict:
    """按 API 动作名清理产物并将 job 指到对应 stage。"""
    if action == "segment/images":
        stage = "segment"
        segment_scope = "images"
    elif action == "segment/clips":
        stage = "segment"
        segment_scope = "clips"
    elif action == "segment/all":
        stage = "segment"
        segment_scope = None
    elif action == "script/imagePrompts":
        with connection() as conn:
            job = job_repo.get_job(conn, job_id)
            script = job.get("script_json")
            if not isinstance(script, dict):
                raise ValueError("script not ready")
            if not (script.get("segments") or []):
                raise ValueError("no segments")
            job_log_repo.append_log(conn, job_id, "script", f"action={action}")
            return job_repo.update_job(
                conn,
                job_id,
                status="pending",
                fail_stage=None,
                error_message=None,
            )
    else:
        stage = action
        segment_scope = None

    if segment_indices is not None:
        if not action.startswith("segment/"):
            raise ValueError("segments 仅可用于 segment/all、segment/images 或 segment/clips")
        if not segment_indices:
            raise ValueError("segments 不能为空")

    from app.config import get_settings

    settings = get_settings()
    media_dir = settings.video_data_dir / str(job_id)

    with connection() as conn:
        job = job_repo.get_job(conn, job_id)
        if stage not in stages_for(job) or stage == "done":
            raise ValueError(f"invalid action: {action}")
        if is_material_job(job) and action.startswith("segment/"):
            raise ValueError(f"action not supported for material pipeline: {action}")
        _clear_stage_self(
            conn,
            job_id,
            stage,
            media_dir,
            job,
            segment_indices=segment_indices,
            segment_scope=segment_scope,
        )
        _clear_downstream(conn, job_id, stage, media_dir, job)

        job = job_repo.update_job(
            conn,
            job_id,
            stage=stage,
            status="pending",
            fail_stage=None,
            error_message=None,
        )
        detail = f"action={action}"
        if segment_indices:
            detail += f", segments={segment_indices}"
        job_log_repo.append_log(conn, job_id, stage, detail)
        return job


def prepare_job_rerun(
    job_id: int,
    stage: str,
    *,
    segment_indices: list[int] | None = None,
    mode: str = "from",
) -> dict:
    """准备重跑（CLI）：清空 stage 自身 + 下游产物，并将 job 指到 stage。"""
    if mode not in {"from", "only"}:
        raise ValueError(f"invalid rerun mode: {mode}")
    if segment_indices is not None:
        if stage != "segment":
            raise ValueError("--segments 仅可与 segment 阶段联用")
        if not segment_indices:
            raise ValueError("--segments 不能为空")

    from app.config import get_settings

    settings = get_settings()
    media_dir = settings.video_data_dir / str(job_id)

    with connection() as conn:
        job = job_repo.get_job(conn, job_id)
        if stage not in stages_for(job) or stage == "done":
            raise ValueError(f"invalid stage: {stage}")
        _clear_stage_self(
            conn,
            job_id,
            stage,
            media_dir,
            job,
            segment_indices=segment_indices,
            segment_scope=None,
        )
        _clear_downstream(conn, job_id, stage, media_dir, job)

        job = job_repo.update_job(
            conn,
            job_id,
            stage=stage,
            status="pending",
            fail_stage=None,
            error_message=None,
        )
        detail = f"rerun [{mode}] stage={stage}"
        if segment_indices:
            detail += f", segments={segment_indices}"
        job_log_repo.append_log(conn, job_id, stage, detail)
        return job


def reset_job_from_stage(
    job_id: int,
    from_stage: str,
    *,
    segment_indices: list[int] | None = None,
) -> dict:
    return prepare_job_rerun(
        job_id,
        from_stage,
        segment_indices=segment_indices,
        mode="from",
    )
