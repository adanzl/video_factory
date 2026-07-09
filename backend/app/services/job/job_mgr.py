"""Job 业务管理：CRUD、状态流转、stage 动作提交。"""

from __future__ import annotations

import logging
import re
import shutil
import threading
from collections.abc import Callable
from pathlib import Path

from app.exceptions import is_expected_job_failure
from app.utils.job_cancel import JobCancelledError, job_cancel
from app.services.job.job_reset import prepare_for_action, prepare_job_rerun
from app.repositories import repo_job_log, repo_job, repo_segment
from app.repositories.connection import connection
from app.utils.async_util import run_in_background
from app.utils.job_info import (
    default_orientation_for_pipeline,
    merge_job_info,
    merge_job_script_params,
    resolve_image_provider,
    resolve_include_sd15_prompt,
)

logger = logging.getLogger(__name__)

_API_UPDATABLE = frozenset({"title", "skip_publish", "status"})
_VALID_STATUSES = frozenset({"pending", "running", "done", "failed"})


def _script_action_detail(
    *,
    job: dict,
    to_end: bool,
    title: str | None,
    segment_target_sec: float | None,
    max_title_length: int | None,
    estimated_duration_min: float | None,
    narration_target_words: int | None,
    speech_chars_per_sec: float | None,
    skip_title_optimize: bool,
    generate_image_prompts: bool,
    supplementary_info: str | None,
    video_timeline: str | None,
    orientation: str | None,
    content_style: str | None,
) -> str:
    from app.utils.job_info import content_style_from_job, orientation_for_resolve

    effective_title = (title or job.get("title") or "").strip()
    parts = [
        f"to_end={to_end}",
        f"title={effective_title!r}",
    ]
    if segment_target_sec is not None:
        parts.append(f"segment_target_sec={segment_target_sec}")
    if max_title_length is not None:
        parts.append(f"max_title_length={max_title_length}")
    if estimated_duration_min is not None:
        parts.append(f"estimated_duration_min={estimated_duration_min}")
    if narration_target_words is not None:
        parts.append(f"narration_target_words={narration_target_words}")
    if speech_chars_per_sec is not None:
        parts.append(f"speech_chars_per_sec={speech_chars_per_sec}")
    if skip_title_optimize:
        parts.append("skip_title_optimize=True")
    if generate_image_prompts:
        parts.append("generate_image_prompts=True")
        provider = resolve_image_provider(job)
        parts.append(f"image_provider={provider}")
        parts.append(f"include_sd15_prompt={resolve_include_sd15_prompt(job)}")
    orient = orientation or orientation_for_resolve(job) or "portrait"
    style = content_style or content_style_from_job(job)
    parts.append(f"orientation={orient}")
    parts.append(f"content_style={style}")
    extra = (supplementary_info or "").strip()
    if extra:
        parts.append(f"supplementary_info=[{len(extra)}]")
    timeline = (video_timeline or "").strip()
    if timeline:
        parts.append(f"video_timeline=[{len(timeline)}]")
    return ", ".join(parts)


def _image_prompts_action_detail(
    job: dict,
    *,
    segment_indices: list[int] | None = None,
) -> str:
    script = job.get("script_json") or {}
    segments = script.get("segments") or []
    provider = resolve_image_provider(job)
    scope = (
        f"segment_indices={segment_indices}"
        if segment_indices
        else f"segments={len(segments)}"
    )
    return (
        f"{scope}, "
        f"image_provider={provider}, "
        f"include_sd15_prompt={resolve_include_sd15_prompt(job)}"
    )


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
            return repo_job.list_jobs(conn, status=status, limit=limit, offset=offset)

    def get_job(self, job_id: int) -> dict:
        from pathlib import Path

        with connection() as conn:
            job = repo_job.get_job(conn, job_id)

        audio_path = job.get("audio_path")
        if audio_path:
            clips_dir = Path(audio_path).parent / "clips"
            if clips_dir.is_dir():
                clips = sorted(
                    (clips_dir / f).name
                    for f in (p.name for p in clips_dir.glob("*.mp3"))
                )
                job["tts_clips"] = [str(clips_dir / name) for name in clips]
            else:
                job["tts_clips"] = []
        else:
            job["tts_clips"] = []
        return job

    def get_segments(self, job_id: int) -> list[dict]:
        from pathlib import Path

        from app.services.tts.tts_mgr import tts_mgr
        from app.utils.media import resolve_segment_duration_sec, script_segment_duration_sec

        with connection() as conn:
            job = repo_job.get_job(conn, job_id)
            segments = repo_segment.list_segments(conn, job_id)

        script = job.get("script_json") or {}
        script_by_index: dict[int, dict] = {}
        for item in script.get("segments") or []:
            if isinstance(item, dict) and item.get("segment_index") is not None:
                script_by_index[int(item["segment_index"])] = item

        tts_by_index: dict[int, float] = {}
        audio_path = job.get("audio_path")
        if audio_path:
            cues_path = tts_mgr.subtitle_cues_path_for(Path(audio_path).parent)
            if cues_path.is_file():
                tts_by_index = tts_mgr.segment_durations_from_cues(
                    tts_mgr.load_subtitle_cues(cues_path)
                )

        for segment in segments:
            index = int(segment["segment_index"])
            script_seg = script_by_index.get(index)
            script_dur = script_segment_duration_sec(script_seg)
            if script_dur is not None:
                segment["script_duration_sec"] = script_dur

            tts_dur = tts_by_index.get(index)
            if tts_dur is not None:
                segment["tts_duration_sec"] = tts_dur

            db_dur = segment.get("duration_sec")
            if db_dur is not None and float(db_dur) > 0:
                continue
            if tts_dur is not None:
                segment["duration_sec"] = tts_dur
                continue
            resolved = resolve_segment_duration_sec(segment, script_seg=script_seg)
            if resolved is not None:
                segment["duration_sec"] = resolved
        return segments

    def update_segment_text(self, job_id: int, segment_index: int, text: str) -> dict:
        """修改分镜文案，同步更新 video_segment 表与 script_json。"""
        cleaned = text.strip()
        if not cleaned:
            raise ValueError("text is empty")
        with connection() as conn:
            job = repo_job.get_job(conn, job_id)
            segments = repo_segment.list_segments(conn, job_id)
            target = next(
                (s for s in segments if int(s["segment_index"]) == segment_index), None
            )
            if target is None:
                raise KeyError(f"segment {segment_index} not found")
            repo_segment.update_segment(conn, int(target["id"]), text=cleaned)
            # 同步 script_json
            script = dict(job.get("script_json") or {})
            script_segments = list(script.get("segments") or [])
            narration_parts: list[str] = []
            found = False
            for i, seg in enumerate(script_segments):
                if int(seg.get("segment_index", 0)) == segment_index:
                    seg = dict(seg)
                    seg["text"] = cleaned
                    script_segments[i] = seg
                    found = True
                narration_parts.append(str(seg.get("text") or ""))
            if not found:
                raise KeyError(f"segment {segment_index} not found in script_json")
            script["segments"] = script_segments
            script["narration"] = "".join(narration_parts)
            script["word_count"] = sum(len(p) for p in narration_parts)
            repo_job.update_job(conn, job_id, script_json=script)
            repo_job_log.append_log(
                conn, job_id, "segment",
                f"segment #{segment_index} text updated ({len(cleaned)} chars)",
            )
            return repo_job.get_job(conn, job_id)

    def get_logs(self, job_id: int) -> list[dict]:
        with connection() as conn:
            repo_job.get_job(conn, job_id)
            return repo_job_log.list_logs(conn, job_id)

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
            job = repo_job.create_job(
                conn,
                cleaned,
                skip_publish=skip_publish,
                stage="script",
                status="pending",
                pipeline="standard",
                info=merge_job_info(
                    None,
                    orientation=default_orientation_for_pipeline("standard"),
                ),
            )
            repo_job_log.append_log(conn, job["id"], "title", f"created job: {cleaned}")
            return job

    def update_job_info(
        self,
        job_id: int,
        *,
        orientation: str | None = None,
        content_style: str | None = None,
        intro_category: str | None = None,
        image_provider: str | None = None,
        video_provider: str | None = None,
    ) -> dict:
        from app.utils.job_info import (
            normalize_content_style,
            normalize_image_provider,
            normalize_intro_category,
            normalize_orientation,
            normalize_video_provider,
        )

        patch: dict[str, str] = {}
        if orientation is not None:
            normalized = normalize_orientation(orientation)
            if normalized not in {"portrait", "landscape"}:
                raise ValueError("orientation must be portrait or landscape")
            patch["orientation"] = normalized
        if content_style is not None:
            normalized = normalize_content_style(content_style)
            if normalized is None:
                raise ValueError(
                    "content_style must be science_child, life_experience or history_mystery"
                )
            patch["content_style"] = normalized
        if intro_category is not None:
            normalized = normalize_intro_category(intro_category)
            if normalized is None:
                raise ValueError("intro_category must be 百科 or 历史悬案")
            patch["intro_category"] = normalized
        if image_provider is not None:
            normalized = normalize_image_provider(image_provider)
            if normalized is None:
                raise ValueError(
                    "image_provider must be z_image_t2i, wan_t2i, sd15_t2i, or agnes_t2i"
                )
            patch["image_provider"] = normalized
        if video_provider is not None:
            normalized = normalize_video_provider(video_provider)
            if normalized is None:
                raise ValueError("video_provider must be ffmpeg, wan_i2v, or agnes_i2v")
            patch["video_provider"] = normalized
        if not patch:
            raise ValueError("no updatable info fields provided")
        with connection() as conn:
            job = repo_job.get_job(conn, job_id)
            job = repo_job.update_job(
                conn,
                job_id,
                info=merge_job_info(job.get("info"), **patch),
            )
            repo_job_log.append_log(
                conn,
                job_id,
                "api",
                f"updated info: {', '.join(f'{k}={v!r}' for k, v in patch.items())}",
            )
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
            job = repo_job.get_job(conn, job_id)
            if "title" in updates:
                script = job.get("script_json")
                if isinstance(script, dict):
                    synced = dict(script)
                    synced["title"] = re.sub(r"\s+", "", updates["title"].strip())
                    updates["script_json"] = synced
            job = repo_job.update_job(conn, job_id, **updates)
            repo_job_log.append_log(conn, job_id, "api", f"updated fields: {', '.join(updates)}")
            return job

    def abort_job(self, job_id: int) -> dict:
        job = self.get_job(job_id)
        was_running = job["status"] == "running"
        if was_running:
            job_cancel.request(job_id)
        else:
            job_cancel.clear(job_id)
        with connection() as conn:
            job = repo_job.update_job(
                conn,
                job_id,
                status="pending",
                fail_stage=None,
                error_message=None,
            )
            repo_job_log.append_log(
                conn,
                job_id,
                "api",
                "abort requested" if was_running else "job aborted to pending",
            )
            return job

    def _skip_if_aborted(self, job_id: int) -> dict | None:
        if job_cancel.is_cancelled(job_id):
            return self.get_job(job_id)
        return None

    def mark_running(self, job_id: int) -> dict:
        skipped = self._skip_if_aborted(job_id)
        if skipped is not None:
            return skipped
        with connection() as conn:
            return repo_job.update_job(conn, job_id, status="running")

    def mark_done(self, job_id: int) -> dict:
        skipped = self._skip_if_aborted(job_id)
        if skipped is not None:
            job_cancel.clear(job_id)
            return skipped
        with connection() as conn:
            return repo_job.update_job(conn, job_id, stage="done", status="done")

    def mark_failed(self, job_id: int, stage: str, message: str) -> dict:
        skipped = self._skip_if_aborted(job_id)
        if skipped is not None:
            job_cancel.clear(job_id)
            return skipped
        with connection() as conn:
            repo_job_log.append_log(conn, job_id, stage, message, level="error")
            return repo_job.update_job(
                conn,
                job_id,
                status="failed",
                error_message=message,
            )

    def mark_aborted(self, job_id: int, stage: str) -> dict:
        job_cancel.clear(job_id)
        with connection() as conn:
            repo_job_log.append_log(
                conn,
                job_id,
                stage,
                "任务已中止",
                level="warning",
            )
            return repo_job.update_job(
                conn,
                job_id,
                status="pending",
                fail_stage=None,
                error_message=None,
            )

    def delete_job(self, job_id: int) -> None:
        with connection() as conn:
            repo_job.delete_job(conn, job_id)

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
                repo_job_log.append_log(conn, job_id, "api", "cleaned local media files")

            return {
                "id": job_id,
                "cleaned": cleaned,
                "media_dir": str(media_dir),
            }
        finally:
            lock.release()

    def _run_in_background(
        self,
        job_id: int,
        action: str,
        run: Callable[[], None],
        *,
        segment_indices: list[int] | None = None,
        action_detail: str | None = None,
    ) -> dict:
        lock = self._job_lock(job_id)
        if not lock.acquire(blocking=False):
            raise JobBusyError(f"job {job_id} is running")

        try:
            job = self.get_job(job_id)
            if job["status"] == "running":
                raise JobBusyError(f"job {job_id} is running")

            prepare_for_action(job_id, action, segment_indices=segment_indices)
            job_cancel.clear(job_id)
            self.mark_running(job_id)

            fail_stage = action.split("/")[0]

            def _worker() -> None:
                if action_detail:
                    logger.info(
                        "job %s action [%s] started in background thread: %s",
                        job_id,
                        action,
                        action_detail,
                    )
                else:
                    logger.info(
                        "job %s action [%s] started in background thread",
                        job_id,
                        action,
                    )
                try:
                    run()
                except JobCancelledError:
                    logger.info("job %s action %s aborted", job_id, action)
                    job_cancel.clear(job_id)
                    job = self.get_job(job_id)
                    if job["status"] == "running":
                        self.mark_aborted(job_id, fail_stage)
                except Exception as exc:
                    if is_expected_job_failure(exc):
                        logger.error(
                            "job %s action %s failed: %s", job_id, action, exc
                        )
                    else:
                        logger.exception(
                            "job %s action %s failed: %s", job_id, action, exc
                        )
                    job = self.get_job(job_id)
                    if job["status"] == "running":
                        self.mark_failed(job_id, fail_stage, str(exc))

            run_in_background(_worker)
            return self.get_job(job_id)
        finally:
            lock.release()

    def _persist_image_provider(self, job_id: int, image_provider: str | None) -> None:
        if image_provider is None:
            return
        with connection() as conn:
            job = repo_job.get_job(conn, job_id)
            repo_job.update_job(
                conn,
                job_id,
                info=merge_job_info(job.get("info"), image_provider=image_provider),
            )

    def _persist_video_provider(self, job_id: int, video_provider: str | None) -> None:
        if video_provider is None:
            return
        with connection() as conn:
            job = repo_job.get_job(conn, job_id)
            repo_job.update_job(
                conn,
                job_id,
                info=merge_job_info(job.get("info"), video_provider=video_provider),
            )

    def run_script(
        self,
        job_id: int,
        *,
        to_end: bool = False,
        title: str | None = None,
        segment_target_sec: float | None = None,
        max_title_length: int | None = None,
        estimated_duration_min: float | None = None,
        narration_target_words: int | None = None,
        speech_chars_per_sec: float | None = None,
        skip_title_optimize: bool = False,
        generate_image_prompts: bool = False,
        supplementary_info: str | None = None,
        video_timeline: str | None = None,
        orientation: str | None = None,
        content_style: str | None = None,
        segment_index: int | None = None,
    ) -> dict:
        """生成文案。实现：worker/loop.run_script → worker/stages/*/script.py"""
        from worker.loop import run_script

        with connection() as conn:
            job = repo_job.get_job(conn, job_id)
            repo_job.update_job(
                conn,
                job_id,
                info=merge_job_script_params(
                    job.get("info"),
                    segment_target_sec=segment_target_sec,
                    max_title_length=max_title_length,
                    estimated_duration_min=estimated_duration_min,
                    narration_target_words=narration_target_words,
                    speech_chars_per_sec=speech_chars_per_sec,
                    skip_title_optimize=skip_title_optimize,
                    generate_image_prompts=generate_image_prompts,
                    supplementary_info=supplementary_info,
                    video_timeline=video_timeline,
                    orientation=orientation,
                    content_style=content_style,
                ),
            )

        if title is not None:
            cleaned = title.strip()
            if not cleaned:
                raise ValueError("title is empty")
            job = self.get_job(job_id)
            if cleaned != job["title"]:
                self.update_job(job_id, title=cleaned)

        job = self.get_job(job_id)
        detail = _script_action_detail(
            job=job,
            to_end=to_end,
            title=title,
            segment_target_sec=segment_target_sec,
            max_title_length=max_title_length,
            estimated_duration_min=estimated_duration_min,
            narration_target_words=narration_target_words,
            speech_chars_per_sec=speech_chars_per_sec,
            skip_title_optimize=skip_title_optimize,
            generate_image_prompts=generate_image_prompts,
            supplementary_info=supplementary_info,
            video_timeline=video_timeline,
            orientation=orientation,
            content_style=content_style,
        )
        if segment_index is not None:
            detail += f", segment_index={segment_index}"
        return self._run_in_background(
            job_id,
            "script",
            lambda: run_script(
                job_id,
                to_end=to_end,
                segment_target_sec=segment_target_sec,
                max_title_length=max_title_length,
                narration_target_words=narration_target_words,
                speech_chars_per_sec=speech_chars_per_sec,
                skip_title_optimize=skip_title_optimize,
                generate_image_prompts=generate_image_prompts,
                supplementary_info=supplementary_info,
                video_timeline=video_timeline,
                segment_index=segment_index,
            ),
            action_detail=detail,
        )

    def generate_script(
        self,
        job_id: int,
        *,
        prompt_type: str = "image_prompt",
        segment_indices: list[int] | None = None,
    ) -> dict:
        """生成指定类型的提示词（文案、画面描述、文生图等）。
        实现：worker/loop.run_script_prompts"""
        from worker.loop import run_script_prompts

        job = self.get_job(job_id)
        return self._run_in_background(
            job_id,
            "script",
            lambda: run_script_prompts(job_id, prompt_type=prompt_type, segment_indices=segment_indices),
            action_detail=_image_prompts_action_detail(job, segment_indices=segment_indices),
        )

    def preview_script_prompts(
        self,
        job_id: int,
        *,
        title: str | None = None,
        segment_target_sec: float | None = None,
        max_title_length: int | None = None,
        estimated_duration_min: float | None = None,
        narration_target_words: int | None = None,
        speech_chars_per_sec: float | None = None,
        skip_title_optimize: bool = False,
        supplementary_info: str | None = None,
        video_timeline: str | None = None,
        orientation: str | None = None,
        content_style: str | None = None,
    ) -> list[dict[str, str]]:
        from app.services.script.script_mgr import script_mgr

        job = self.get_job(job_id)
        if orientation is not None or content_style is not None:
            job = dict(job)
            patch: dict[str, str] = {}
            if orientation is not None:
                patch["orientation"] = orientation
            if content_style is not None:
                patch["content_style"] = content_style
            job["info"] = merge_job_info(job.get("info"), **patch)
        source_title = (title or job["title"] or "").strip()
        if not source_title:
            raise ValueError("title is empty")
        script = job.get("script_json")
        if script is not None and not isinstance(script, dict):
            script = None
        return script_mgr.collect_prompts(
            job,
            source_title,
            segment_target_sec=segment_target_sec,
            max_title_length=max_title_length,
            narration_target_words=narration_target_words,
            speech_chars_per_sec=speech_chars_per_sec,
            supplementary_info=supplementary_info,
            video_timeline=video_timeline,
            script=script,
            skip_title_optimize=skip_title_optimize,
            preview_followups=True,
        )

    def generate_video_description(self, job_id: int) -> dict:
        from app.services.llm.llm_mgr import llm_mgr

        with connection() as conn:
            job = repo_job.get_job(conn, job_id)
            script = job.get("script_json")
            if not isinstance(script, dict):
                raise ValueError("script not ready")
            title = str(script.get("title") or job.get("title") or "").strip()
            narration = str(script.get("narration") or "").strip()
            if not title:
                raise ValueError("title is empty")
            if not narration:
                raise ValueError("narration is empty")

            description = llm_mgr.generate_video_description(title, narration)
            updated_script = dict(script)
            updated_script["video_description"] = description

            job = repo_job.update_job(conn, job_id, script_json=updated_script)
            repo_job_log.append_log(conn, job_id, "script", "video description regenerated")
            return {"video_description": description, "job": job}

    def run_intro(
        self,
        job_id: int,
        *,
        to_end: bool = False,
        hold_tail_sec: float | None = None,
        orientation: str | None = None,
        orientation_preference: str | None = None,
        intro_category: str | None = None,
    ) -> dict:
        """生成片头。实现：worker/loop.run_intro → worker/stages/intro/"""
        from worker.loop import run_intro

        info_patch: dict = {}
        if orientation_preference is not None:
            info_patch["orientation"] = orientation_preference
        if intro_category is not None:
            from app.utils.job_info import normalize_intro_category

            normalized = normalize_intro_category(intro_category)
            if normalized is None:
                raise ValueError("intro_category must be 百科 or 历史悬案")
            info_patch["intro_category"] = normalized
        if info_patch:
            with connection() as conn:
                job = repo_job.get_job(conn, job_id)
                repo_job.update_job(
                    conn,
                    job_id,
                    info=merge_job_info(job.get("info"), **info_patch),
                )

        return self._run_in_background(
            job_id,
            "intro",
            lambda: run_intro(
                job_id,
                to_end=to_end,
                hold_tail_sec=hold_tail_sec,
                orientation=orientation,
            ),
        )

    def run_cover(self, job_id: int, *, to_end: bool = False) -> dict:
        """仅重新生成封面，不动片头视频。"""
        import tempfile

        from PIL import Image

        from app.config import get_settings
        from app.services.intro.cover_layout import (
            build_cover_image_prompt,
            compose_cover_image,
            cover_canvas_size,
        )
        from app.services.media.ffmpeg_utils import probe_video_size
        from app.services.segment.image.image_agnes import AgnesImageProvider
        from worker.stages.intro.base import _cover_subject_from_job, resolve_intro_title

        def _generate() -> None:
            with connection() as conn:
                job = repo_job.get_job(conn, job_id)
            settings = get_settings()
            title = resolve_intro_title(job)

            intro_path = job.get("intro_path")
            if intro_path:
                try:
                    width, height = probe_video_size(Path(intro_path))
                except Exception:
                    width, height = settings.video_width, settings.video_height
            else:
                if settings.video_width > settings.video_height:
                    width, height = settings.video_width, settings.video_height
                else:
                    width, height = settings.video_height, settings.video_width

            cw, ch, _ = cover_canvas_size(width, height)
            subject = _cover_subject_from_job(job)
            cover_prompt = build_cover_image_prompt(cw=cw, ch=ch, subject=subject)

            media_dir = settings.video_data_dir / str(job_id)
            cover_path = media_dir / "cover.jpg"

            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                tmp_path = Path(tmp.name)
            try:
                AgnesImageProvider().generate(cover_prompt, tmp_path, size=f"{cw}x{ch}")
                img = Image.open(tmp_path)
                composed = compose_cover_image(
                    img,
                    title,
                    brand_name=settings.brand_name,
                    host_intro_path=settings.host_intro_path,
                )
                composed.convert("RGB").save(cover_path, quality=92)
            finally:
                tmp_path.unlink(missing_ok=True)

            with connection() as conn:
                repo_job.update_job(conn, job_id, cover_path=str(cover_path.resolve()))
                repo_job_log.append_log(
                    conn, job_id, "cover", f"cover regenerated: {cover_path} ({cw}x{ch})"
                )

            self.mark_done(job_id)

        return self._run_in_background(job_id, "cover", _generate)

    def run_tts(
        self,
        job_id: int,
        *,
        to_end: bool = False,
        speech_rate: float | None = None,
        voice_id: str | None = None,
    ) -> dict:
        """生成配音。实现：worker/loop.run_tts → worker/stages/common/tts.py"""
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
        image_provider: str | None = None,
        video_provider: str | None = None,
    ) -> dict:
        """重跑分镜静图与图生视频。实现：worker/loop.run_segment_all → worker/stages/standard/segment.py"""
        from worker.loop import run_segment_all

        self._persist_image_provider(job_id, image_provider)
        self._persist_video_provider(job_id, video_provider)
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
        image_provider: str | None = None,
    ) -> dict:
        """重出分镜静图。实现：worker/loop.run_segment_images → worker/stages/standard/segment.py"""
        from worker.loop import run_segment_images

        self._persist_image_provider(job_id, image_provider)
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
        video_provider: str | None = None,
    ) -> dict:
        """重跑图生视频。实现：worker/loop.run_segment_clips → worker/stages/standard/segment.py"""
        from worker.loop import run_segment_clips

        self._persist_video_provider(job_id, video_provider)

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
        """合成成片。实现：worker/loop.run_merge → merge stage（按 pipeline 分发）"""
        from worker.loop import run_merge

        return self._run_in_background(
            job_id,
            "merge",
            lambda: run_merge(job_id, to_end=to_end),
        )

    def run_prepare(self, job_id: int, *, to_end: bool = False) -> dict:
        """素材任务：复制基底视频。实现：worker/loop.run_prepare → worker/stages/material/prepare.py"""
        from worker.loop import run_prepare

        return self._run_in_background(
            job_id,
            "prepare",
            lambda: run_prepare(job_id, to_end=to_end),
        )

    def run_publish(self, job_id: int, *, to_end: bool = False) -> dict:
        """发布。实现：worker/loop.run_publish → worker/stages/common/publish.py"""
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

__all__ = ["JobBusyError", "JobCancelledError", "JobMgr", "job_mgr"]
