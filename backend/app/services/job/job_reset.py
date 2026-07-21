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
from app.utils.stage_names import normalize_stage
from app.repositories import repo_job_log, repo_job, repo_segment
from app.repositories.connection import connection

__all__ = [
    "prepare_rerun",
    "prepare_for_action",
    "prepare_job_rerun",
    "reset_job_from_stage",
]

# 重跑 publish / tts 时不扫下游文件树；tts 只清 DB clip_path（见
# _clear_tts_artifacts），分镜 mp4 留给 segment 按需重生成
_STAGES_SKIP_DOWNSTREAM_CLEAR = frozenset({"publish", "tts"})


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
    repo_segment.clear_segment_durations(conn, job_id)
    # 新配音时长会变；清 DB clip_path，避免 segment/merge 复用旧时间轴
    repo_segment.clear_segment_clips(conn, job_id)
    repo_job.update_job(
        conn, job_id, audio_path=None, subtitle_path=None, tts_usage_json=None
    )
    if not media_dir.exists():
        return
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
    repo_segment.clear_segment_clips(conn, job_id, None)
    clips_dir = media_dir / "segments"
    if clips_dir.exists():
        for clip in clips_dir.glob("*.mp4"):
            clip.unlink()


def _clear_all_segment_media(conn, job_id: int, media_dir: Path) -> None:
    _archive_wan_clips(media_dir)
    repo_segment.clear_segment_media(conn, job_id, None)
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
    repo_segment.clear_segment_clips_only(conn, job_id, segment_indices)
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

    if stage == "script":
        repo_job.update_job(conn, job_id, cover_path=None)
        _delete_files([media_dir / "cover.jpg"])

    if pipe == PIPELINE_MATERIAL:
        if idx < stage_index("merge", job):
            repo_job.update_job(conn, job_id, final_path=None)
            _clear_merge_artifacts(media_dir)
        return

    if idx < stage_index("segment", job):
        _clear_segment_clips(conn, job_id, media_dir)

    if idx < stage_index("merge", job):
        repo_job.update_job(conn, job_id, final_path=None)
        _clear_merge_artifacts(media_dir)


def _clear_segment_images(
    conn,
    job_id: int,
    media_dir: Path,
    segment_indices: list[int] | None,
) -> None:
    repo_segment.clear_segment_media(conn, job_id, segment_indices)
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
        repo_job.update_job(conn, job_id, base_path=None)
        return

    if stage in {"title", "script"}:
        preserve_base = pipe == PIPELINE_MATERIAL and stage == "script"
        reset_script_json = None
        if preserve_base:
            reset_script_json = _material_script_reset_seed(job)
        repo_segment.delete_segments(conn, job_id)
        repo_job.update_job(
            conn,
            job_id,
            script_json=reset_script_json,
            intro_path=None,
            cover_path=None,
            end_path=None,
            final_path=None,
            quality_report=None,
        )
        if media_dir.exists():
            if not preserve_base:
                _delete_files([media_dir / "base.mp4", media_dir / "base_meta.json"])
            if pipe != PIPELINE_MATERIAL:
                _clear_all_segment_media(conn, job_id, media_dir)
            _clear_merge_artifacts(media_dir)
            _delete_files([media_dir / "end.mp4"])
            merge_work = media_dir / "merge_work"
            if merge_work.exists():
                shutil.rmtree(merge_work)
        return

    if stage == "intro":
        # 片头/封面重生成时同步清片尾（chat 流水线会在 intro 阶段重出 end.mp4）
        repo_job.update_job(
            conn, job_id, intro_path=None, cover_path=None, end_path=None
        )
        if media_dir.exists():
            _delete_files(
                [
                    media_dir / "intro.mp4",
                    media_dir / "intro.png",
                    media_dir / "cover.jpg",
                    media_dir / "end.mp4",
                ]
            )
        return

    if stage == "tts":
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
        repo_job.update_job(conn, job_id, final_path=None)
        if media_dir.exists():
            _clear_merge_artifacts(media_dir)


def _resolve_action(
    action: str,
) -> tuple[str, str | None] | tuple[None, None]:
    """解析 action → (stage, segment_scope)。cover/end 返回 (None, None)。"""
    if action == "segment/images":
        return "segment", "images"
    if action == "segment/clips":
        return "segment", "clips"
    if action == "segment/all":
        return "segment", None
    if action in {"cover", "end"}:
        return None, None
    return normalize_stage(action), None


def _prepare_cover_or_end(job_id: int, action: str) -> dict:
    from app.config import get_settings

    settings = get_settings()
    media_dir = settings.video_data_dir / str(job_id)
    with connection() as conn:
        if action == "cover":
            repo_job.update_job(conn, job_id, cover_path=None)
            if media_dir.exists():
                _delete_files([media_dir / "cover.jpg"])
            log_msg = f"action={action} (cover only)"
        else:
            repo_job.update_job(conn, job_id, end_path=None)
            if media_dir.exists():
                _delete_files([media_dir / "end.mp4"])
            log_msg = f"action={action}"
        repo_job_log.append_log(conn, job_id, "intro", log_msg)
        return repo_job.update_job(
            conn,
            job_id,
            status="pending",
            fail_stage=None,
            error_message=None,
        )


def prepare_rerun(
    job_id: int,
    action: str,
    *,
    segment_indices: list[int] | None = None,
    mode: str = "from",
) -> dict:
    """统一重跑清理：清空目标产物并将 job 指到对应 stage。

    ``action`` 与 API 一致，支持 ``script`` / ``tts`` / ``segment`` /
    ``segment/images`` / ``segment/clips`` / ``segment/all`` / ``cover`` /
    ``end`` 等。

    ``mode`` 仅写入日志（``from`` / ``only``）；清理始终为本 stage + 下游。
    ``cover`` / ``end`` 只清文件，不改 stage 指针。
    """
    if mode not in {"from", "only"}:
        raise ValueError(f"invalid rerun mode: {mode}")

    if action in {"cover", "end"}:
        if segment_indices is not None:
            raise ValueError("segments 不可用于 cover/end")
        return _prepare_cover_or_end(job_id, action)

    stage, segment_scope = _resolve_action(action)
    assert stage is not None

    if segment_indices is not None:
        if stage != "segment":
            raise ValueError(
                "segments 仅可用于 segment / segment/all / "
                "segment/images / segment/clips"
            )
        if not segment_indices:
            raise ValueError("segments 不能为空")

    from app.config import get_settings

    settings = get_settings()
    media_dir = settings.video_data_dir / str(job_id)

    with connection() as conn:
        job = repo_job.get_job(conn, job_id)
        if stage not in stages_for(job) or stage == "done":
            raise ValueError(f"invalid action: {action}")
        if is_material_job(job) and (
            action.startswith("segment/") or action == "segment"
        ):
            raise ValueError(
                f"action not supported for material pipeline: {action}"
            )
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

        job = repo_job.update_job(
            conn,
            job_id,
            stage=stage,
            status="pending",
            fail_stage=None,
            error_message=None,
        )
        detail = f"rerun [{mode}] action={action}"
        if segment_indices:
            detail += f", segments={segment_indices}"
        repo_job_log.append_log(conn, job_id, stage, detail)
        return job


def prepare_for_action(
    job_id: int,
    action: str,
    *,
    segment_indices: list[int] | None = None,
) -> dict:
    """兼容旧名 → :func:`prepare_rerun`。"""
    return prepare_rerun(
        job_id, action, segment_indices=segment_indices, mode="from"
    )


def prepare_job_rerun(
    job_id: int,
    stage: str,
    *,
    segment_indices: list[int] | None = None,
    mode: str = "from",
) -> dict:
    """兼容 CLI 旧名 → :func:`prepare_rerun`（``stage`` 当作 action）。"""
    return prepare_rerun(
        job_id,
        stage,
        segment_indices=segment_indices,
        mode=mode,
    )


def reset_job_from_stage(
    job_id: int,
    from_stage: str,
    *,
    segment_indices: list[int] | None = None,
) -> dict:
    return prepare_rerun(
        job_id,
        from_stage,
        segment_indices=segment_indices,
        mode="from",
    )
