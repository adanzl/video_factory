"""Job 业务管理：CRUD、状态流转、stage 动作提交。"""

from __future__ import annotations

import logging
import re
import shutil
import threading
from collections.abc import Callable
from pathlib import Path

from app.utils.job_cancel import JobCancelledError, job_cancel
from app.services.job.job_reset import prepare_for_action, prepare_job_rerun
from app.repositories import job_log_repo, job_repo, segment_repo
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
    narration_target_words: int | None,
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
    if narration_target_words is not None:
        parts.append(f"narration_target_words={narration_target_words}")
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
        parts.append(f"supplementary_info={len(extra)}chars")
    timeline = (video_timeline or "").strip()
    if timeline:
        parts.append(f"video_timeline={len(timeline)}chars")
    return ", ".join(parts)


def _image_prompts_action_detail(job: dict) -> str:
    script = job.get("script_json") or {}
    segments = script.get("segments") or []
    provider = resolve_image_provider(job)
    return (
        f"segments={len(segments)}, "
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
            return job_repo.list_jobs(conn, status=status, limit=limit, offset=offset)

    def get_job(self, job_id: int) -> dict:
        with connection() as conn:
            return job_repo.get_job(conn, job_id)

    def get_segments(self, job_id: int) -> list[dict]:
        from app.utils.media import resolve_segment_duration_sec

        with connection() as conn:
            job = job_repo.get_job(conn, job_id)
            segments = segment_repo.list_segments(conn, job_id)

        script = job.get("script_json") or {}
        script_by_index: dict[int, dict] = {}
        for item in script.get("segments") or []:
            if isinstance(item, dict) and item.get("segment_index") is not None:
                script_by_index[int(item["segment_index"])] = item

        for segment in segments:
            if segment.get("duration_sec") is not None:
                continue
            resolved = resolve_segment_duration_sec(
                segment,
                script_seg=script_by_index.get(int(segment["segment_index"])),
            )
            if resolved is not None:
                segment["duration_sec"] = resolved
        return segments

    def get_logs(self, job_id: int) -> list[dict]:
        with connection() as conn:
            job_repo.get_job(conn, job_id)
            return job_log_repo.list_logs(conn, job_id)

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
            job = job_repo.create_job(
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
            job_log_repo.append_log(conn, job["id"], "title", f"created job: {cleaned}")
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
            job = job_repo.get_job(conn, job_id)
            job = job_repo.update_job(
                conn,
                job_id,
                info=merge_job_info(job.get("info"), **patch),
            )
            job_log_repo.append_log(
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
            job = job_repo.get_job(conn, job_id)
            if "title" in updates:
                script = job.get("script_json")
                if isinstance(script, dict):
                    synced = dict(script)
                    synced["title"] = re.sub(r"\s+", "", updates["title"].strip())
                    updates["script_json"] = synced
            job = job_repo.update_job(conn, job_id, **updates)
            job_log_repo.append_log(conn, job_id, "api", f"updated fields: {', '.join(updates)}")
            return job

    def reset_job(self, job_id: int) -> dict:
        """强制将任务状态重置为 pending（不清除 stage 与产物）。"""
        job_cancel.clear(job_id)
        with connection() as conn:
            job_repo.get_job(conn, job_id)
            job = job_repo.update_job(
                conn,
                job_id,
                status="pending",
                fail_stage=None,
                error_message=None,
            )
            job_log_repo.append_log(conn, job_id, "api", "job status reset to pending")
            return job

    def delete_job(self, job_id: int) -> None:
        with connection() as conn:
            job_repo.delete_job(conn, job_id)

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
                job_log_repo.append_log(conn, job_id, "api", "cleaned local media files")

            return {
                "id": job_id,
                "cleaned": cleaned,
                "media_dir": str(media_dir),
            }
        finally:
            lock.release()

    def mark_running(self, job_id: int) -> dict:
        with connection() as conn:
            return job_repo.update_job(conn, job_id, status="running")

    def mark_done(self, job_id: int) -> dict:
        with connection() as conn:
            return job_repo.update_job(conn, job_id, stage="done", status="done")

    def mark_failed(self, job_id: int, stage: str, message: str) -> dict:
        with connection() as conn:
            job_log_repo.append_log(conn, job_id, stage, message, level="error")
            return job_repo.update_job(
                conn,
                job_id,
                status="failed",
                error_message=message,
            )

    def mark_aborted(self, job_id: int, stage: str) -> dict:
        job_cancel.clear(job_id)
        with connection() as conn:
            job_log_repo.append_log(
                conn,
                job_id,
                stage,
                "任务已中止",
                level="warning",
            )
            return job_repo.update_job(conn, job_id, status="pending")

    def abort_job(self, job_id: int) -> dict:
        job = self.get_job(job_id)
        if job["status"] != "running":
            raise ValueError(f"job {job_id} is not running")
        job_cancel.request(job_id)
        with connection() as conn:
            job_log_repo.append_log(conn, job_id, "api", "abort requested")
        return self.get_job(job_id)

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
                    job = self.get_job(job_id)
                    if job["status"] == "running":
                        self.mark_aborted(job_id, fail_stage)
                except Exception as exc:
                    logger.exception("job %s action %s failed: %s", job_id, action, exc)
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
            job = job_repo.get_job(conn, job_id)
            job_repo.update_job(
                conn,
                job_id,
                info=merge_job_info(job.get("info"), image_provider=image_provider),
            )

    def _persist_video_provider(self, job_id: int, video_provider: str | None) -> None:
        if video_provider is None:
            return
        with connection() as conn:
            job = job_repo.get_job(conn, job_id)
            job_repo.update_job(
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
        narration_target_words: int | None = None,
        skip_title_optimize: bool = False,
        generate_image_prompts: bool = False,
        supplementary_info: str | None = None,
        video_timeline: str | None = None,
        orientation: str | None = None,
        content_style: str | None = None,
    ) -> dict:
        """生成文案。实现：worker/loop.run_script → worker/stages/*/script.py"""
        from worker.loop import run_script

        with connection() as conn:
            job = job_repo.get_job(conn, job_id)
            job_repo.update_job(
                conn,
                job_id,
                info=merge_job_script_params(
                    job.get("info"),
                    segment_target_sec=segment_target_sec,
                    max_title_length=max_title_length,
                    narration_target_words=narration_target_words,
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
            narration_target_words=narration_target_words,
            skip_title_optimize=skip_title_optimize,
            generate_image_prompts=generate_image_prompts,
            supplementary_info=supplementary_info,
            video_timeline=video_timeline,
            orientation=orientation,
            content_style=content_style,
        )
        return self._run_in_background(
            job_id,
            "script",
            lambda: run_script(
                job_id,
                to_end=to_end,
                segment_target_sec=segment_target_sec,
                max_title_length=max_title_length,
                narration_target_words=narration_target_words,
                skip_title_optimize=skip_title_optimize,
                generate_image_prompts=generate_image_prompts,
                supplementary_info=supplementary_info,
                video_timeline=video_timeline,
            ),
            action_detail=detail,
        )

    def generate_image_prompts(self, job_id: int) -> dict:
        """为已有脚本补全文生图提示词。实现：worker/loop.run_script_image_prompts"""
        from worker.loop import run_script_image_prompts

        job = self.get_job(job_id)
        return self._run_in_background(
            job_id,
            "script/imagePrompts",
            lambda: run_script_image_prompts(job_id),
            action_detail=_image_prompts_action_detail(job),
        )

    def preview_script_prompts(
        self,
        job_id: int,
        *,
        title: str | None = None,
        segment_target_sec: float | None = None,
        max_title_length: int | None = None,
        narration_target_words: int | None = None,
        skip_title_optimize: bool = False,
        supplementary_info: str | None = None,
        video_timeline: str | None = None,
        orientation: str | None = None,
        content_style: str | None = None,
    ) -> list[dict[str, str]]:
        from app.services.llm.llm_script_prompts import collect_script_prompts

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
        return collect_script_prompts(
            job,
            source_title,
            segment_target_sec=segment_target_sec,
            max_title_length=max_title_length,
            narration_target_words=narration_target_words,
            supplementary_info=supplementary_info,
            video_timeline=video_timeline,
            script=script,
            skip_title_optimize=skip_title_optimize,
            preview_followups=True,
        )

    def generate_video_description(self, job_id: int) -> dict:
        from app.services.llm.llm_mgr import llm_mgr
        from app.services.llm.llm_script_prompts import build_video_description_prompts

        with connection() as conn:
            job = job_repo.get_job(conn, job_id)
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

            prompts = list(updated_script.get("llm_prompts") or [])
            desc_prompt = build_video_description_prompts(title, narration)
            prompts = [item for item in prompts if item.get("step") != "video_description"]
            prompts.append(desc_prompt)
            updated_script["llm_prompts"] = prompts

            job = job_repo.update_job(conn, job_id, script_json=updated_script)
            job_log_repo.append_log(conn, job_id, "script", "video description regenerated")
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
                job = job_repo.get_job(conn, job_id)
                job_repo.update_job(
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
        """兼容旧 API：封面已并入 intro 阶段。"""
        return self.run_intro(job_id, to_end=to_end)

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
