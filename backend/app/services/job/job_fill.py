"""补全成片：已有产物不重做，只补缺口。"""
from __future__ import annotations

from pathlib import Path

from app.core.pipelines import is_material_job
from app.repositories import repo_job, repo_job_log, repo_segment
from app.repositories.sql_exec import atomic
from app.utils.final_asset import resolve_final_path_file
from worker.context import JobContext

_AUDIO_CLIP_EXTS = (".mp3", ".wav")


def file_ok(path: Path | None) -> bool:
    if path is None:
        return False
    try:
        return path.is_file() and path.stat().st_size > 0
    except OSError:
        return False


def _path_of(raw: object) -> Path | None:
    text = str(raw or "").strip()
    if not text:
        return None
    return Path(text)


def script_body_ready(script: object) -> bool:
    """口播和分镜正文已在，补全时不得整篇重写。"""
    if not isinstance(script, dict):
        return False
    segments = script.get("segments") or []
    if not segments:
        return False
    for seg in segments:
        if not isinstance(seg, dict):
            continue
        text = str(seg.get("text") or "").strip()
        dialogue = seg.get("dialogue") or []
        spoken = text
        if not spoken and isinstance(dialogue, list):
            spoken = "".join(
                str(line.get("text") or "").strip()
                for line in dialogue
                if isinstance(line, dict)
            )
        if spoken:
            return True
    return False


def script_prompt_gaps(job: dict, script: dict) -> list[int]:
    """缺 image_prompt 的分镜。素材线不出图，视为没有缺口。"""
    if is_material_job(job):
        return []
    gaps: list[int] = []
    for seg in script.get("segments") or []:
        if not isinstance(seg, dict):
            continue
        if str(seg.get("image_prompt") or "").strip():
            continue
        gaps.append(int(seg.get("segment_index") or 0))
    return [index for index in gaps if index > 0]


def script_brief_gaps(job: dict, script: dict, prompt_gaps: list[int]) -> list[int]:
    """日常故事里，缺提示词且缺画面概述的分镜。"""
    pipeline = str(job.get("pipeline") or "").strip()
    if pipeline != "chat":
        return []
    wanted = set(prompt_gaps)
    gaps: list[int] = []
    for seg in script.get("segments") or []:
        if not isinstance(seg, dict):
            continue
        index = int(seg.get("segment_index") or 0)
        if index not in wanted:
            continue
        if str(seg.get("visual_brief") or "").strip():
            continue
        gaps.append(index)
    return gaps


def audio_clip_file(audio_dir: Path, segment_index: int) -> Path | None:
    clips_dir = audio_dir / "clips"
    for ext in _AUDIO_CLIP_EXTS:
        path = clips_dir / f"{segment_index}{ext}"
        if file_ok(path):
            return path
    return None


def narration_file(media_dir: Path) -> Path | None:
    audio_dir = media_dir / "audio"
    for name in ("narration.mp3", "narration.wav"):
        path = audio_dir / name
        if file_ok(path):
            return path
    return None


def tts_files_ready(media_dir: Path, segments: list[dict]) -> bool:
    if narration_file(media_dir) is None:
        return False
    audio_dir = media_dir / "audio"
    if not file_ok(audio_dir / "subtitles.srt"):
        return False
    if not file_ok(audio_dir / "subtitle_cues.json"):
        return False
    if not segments:
        return False
    for seg in segments:
        index = int(seg.get("segment_index") or 0)
        if audio_clip_file(audio_dir, index) is None:
            return False
    return True


def tts_db_ready(job: dict) -> bool:
    return file_ok(_path_of(job.get("audio_path"))) and file_ok(_path_of(job.get("subtitle_path")))


def _located(job: dict, key: str, fallback: Path) -> Path | None:
    recorded = _path_of(job.get(key))
    if file_ok(recorded):
        return recorded
    if file_ok(fallback):
        return fallback
    return None


def intro_assets(job: dict, media_dir: Path) -> dict[str, Path | None]:
    assets = {
        "intro": _located(job, "intro_path", media_dir / "intro.mp4"),
        "cover": _located(job, "cover_path", media_dir / "cover.jpg"),
    }
    if str(job.get("pipeline") or "").strip() == "chat":
        assets["end"] = _located(job, "end_path", media_dir / "end.mp4")
    return assets


def final_file(job: dict, media_dir: Path) -> Path | None:
    recorded = resolve_final_path_file(job.get("final_path"))
    if recorded and file_ok(Path(recorded)):
        return Path(recorded)
    fallback = media_dir / "final.mp4"
    if file_ok(fallback):
        return fallback
    return None


def segment_media_ready(segments: list[dict], media_dir: Path) -> bool:
    """与分镜阶段的复用规则一致：静图可吃磁盘，成片必须 DB 仍指向文件。"""
    from app.services.segment.segment_mgr import segment_mgr

    if not segments:
        return False
    images_dir = media_dir / "images"
    clips_dir = media_dir / "segments"
    for seg in segments:
        if segment_mgr._existing_image_path(seg, images_dir) is None:
            return False
        if segment_mgr._existing_clip_path(seg, clips_dir) is None:
            return False
    return True


def stage_outputs_complete(
    job: dict,
    stage_name: str,
    *,
    media_dir: Path,
    segments: list[dict] | None = None,
) -> bool:
    """该阶段产物是否已经齐，补全时可以整段跳过。"""
    if stage_name == "prepare":
        return _located(job, "base_path", media_dir / "base.mp4") is not None
    if stage_name == "script":
        script = job.get("script_json")
        if not script_body_ready(script):
            return False
        assert isinstance(script, dict)
        return not script_prompt_gaps(job, script)
    if stage_name == "tts":
        rows = segments or []
        return tts_files_ready(media_dir, rows) and tts_db_ready(job)
    if stage_name == "segment":
        return segment_media_ready(segments or [], media_dir)
    if stage_name == "intro":
        assets = intro_assets(job, media_dir)
        return all(path is not None for path in assets.values())
    if stage_name == "merge":
        return final_file(job, media_dir) is not None
    return False


def mark_script_rebuilt(ctx: JobContext) -> None:
    """正文是这次新写的，下游旧文件对不上，下一阶段先清掉。"""
    if ctx.fill_state is not None:
        ctx.fill_state["script_rebuilt"] = True
    ctx.note_filled()


def take_script_rebuilt(ctx: JobContext) -> bool:
    if ctx.fill_state is None or not ctx.fill_state.get("script_rebuilt"):
        return False
    ctx.fill_state["script_rebuilt"] = False
    return True


def clear_downstream_media(media_dir: Path) -> None:
    """清掉和旧脚本绑定的配音、分镜、片头和成片。基底视频保留。"""
    audio_dir = media_dir / "audio"
    if audio_dir.exists():
        for path in audio_dir.rglob("*"):
            if path.is_file():
                path.unlink(missing_ok=True)
    for folder, pattern in (("images", "*.png"), ("segments", "*.mp4")):
        directory = media_dir / folder
        if directory.exists():
            for path in directory.glob(pattern):
                path.unlink(missing_ok=True)
    for name in (
        "intro.mp4",
        "cover.jpg",
        "end.mp4",
        "final.mp4",
        "body.mp4",
        "body_with_audio.mp4",
    ):
        (media_dir / name).unlink(missing_ok=True)


def fill_existing_script(ctx: JobContext, stage_name: str) -> bool:
    """脚本正文已在时补缺提示词。返回 True 表示本阶段已处理，不要整篇重生成。"""
    from app.services.llm.llm_mgr import llm_mgr
    from app.utils.job_info import content_style_from_job, resolve_include_sd15_prompt

    job_id = int(ctx.job["id"])
    with atomic():
        job = repo_job.get_job(job_id)
    script_raw = job.get("script_json")
    if not isinstance(script_raw, dict) or not script_body_ready(script_raw):
        return False
    script = dict(script_raw)
    script["segments"] = [
        dict(seg) if isinstance(seg, dict) else seg
        for seg in (script.get("segments") or [])
    ]
    prompt_gaps = script_prompt_gaps(job, script)
    if not prompt_gaps:
        with atomic():
            repo_job_log.append_log(job_id, stage_name, "script already complete, skip")
        return True
    brief_gaps = script_brief_gaps(job, script, prompt_gaps)
    if brief_gaps:
        llm_mgr.fill_visual_briefs(script, job=job, segment_indices=brief_gaps)
        if str(job.get("pipeline") or "").strip() == "chat":
            from app.services.daily_story.speaker import (
                allowed_cast_from_segment,
                scrub_leaked_speaker_names,
            )
            from app.services.script.visual_brief import scrub_daily_visual_brief

            wanted = set(brief_gaps)
            for seg in script.get("segments") or []:
                if int(seg.get("segment_index") or 0) not in wanted:
                    continue
                allowed = allowed_cast_from_segment(seg)
                cleaned = scrub_leaked_speaker_names(str(seg.get("visual_brief") or ""), allowed)
                cleaned = scrub_daily_visual_brief(cleaned)
                seg["visual_brief"] = cleaned
    if str(job.get("pipeline") or "").strip() == "chat":
        from app.utils.job_info import apply_keyframe_video_providers

        apply_keyframe_video_providers(script.get("segments") or [])
    supplementary = str(script.get("supplementary_info") or "").strip() or None
    llm_mgr.fill_image_prompts_with_retries(
        script,
        supplementary_info=supplementary,
        job=job,
        segment_indices=prompt_gaps,
        include_sd15_prompt=resolve_include_sd15_prompt(job),
    )
    from app.services.script.image_prompt import wrap_image_prompts

    wrap_image_prompts(
        script.get("segments") or [],
        content_style=content_style_from_job(job),
        setting=str(script.get("setting") or "").strip() or None,
        segment_indices=prompt_gaps,
    )
    script.pop("_llm_timing", None)
    with atomic():
        repo_job.update_job(job_id, script_json=script)
        repo_segment.insert_segments(job_id, script.get("segments") or [])
        repo_job_log.append_log(
            job_id,
            stage_name,
            f"filled missing image prompts: {prompt_gaps}",
        )
    return True


def repair_tts_pointers(job_id: int, media_dir: Path, stage_name: str) -> None:
    """配音文件已在、库里的路径空着时，只把指针补上。"""
    narration = narration_file(media_dir)
    subtitle = media_dir / "audio" / "subtitles.srt"
    if narration is None or not file_ok(subtitle):
        return
    with atomic():
        job = repo_job.get_job(job_id)
        updates: dict[str, str] = {}
        if not file_ok(_path_of(job.get("audio_path"))):
            updates["audio_path"] = str(narration.resolve())
        if not file_ok(_path_of(job.get("subtitle_path"))):
            updates["subtitle_path"] = str(subtitle.resolve())
        if not updates:
            repo_job_log.append_log(job_id, stage_name, "tts already complete, skip")
            return
        repo_job.update_job(job_id, **updates)
        repo_job_log.append_log(job_id, stage_name, "tts files kept, repaired paths")


def try_skip_merge(ctx: JobContext, stage_name: str) -> bool:
    """成片文件已在、且本轮没有新产物时跳过合成。"""
    if not ctx.fill_missing:
        return False
    if ctx.filled_this_run():
        return False
    job_id = int(ctx.job["id"])
    media_dir = ctx.media_dir
    with atomic():
        job = repo_job.get_job(job_id)
    found = final_file(job, media_dir)
    if found is None:
        return False
    recorded = resolve_final_path_file(job.get("final_path"))
    with atomic():
        if not recorded or not file_ok(Path(recorded)):
            from app.services.media.ffmpeg_utils import probe_duration
            from app.utils.final_asset import build_final_asset

            repo_job.update_job(
                job_id,
                final_path=build_final_asset(found, duration=probe_duration(found)),
            )
            repo_job_log.append_log(job_id, stage_name, "final file kept, repaired path")
        else:
            repo_job_log.append_log(job_id, stage_name, "final already exists, skip merge")
    return True


def skip_complete_tts(ctx: JobContext, stage_name: str) -> bool:
    """配音文件和库路径都齐时跳过合成。返回 True 表示调用方应直接返回。"""
    job_id = int(ctx.job["id"])
    media_dir = ctx.media_dir
    with atomic():
        job = repo_job.get_job(job_id)
        segments = repo_segment.list_segments(job_id)
    if not tts_files_ready(media_dir, segments):
        return False
    repair_tts_pointers(job_id, media_dir, stage_name)
    return True
