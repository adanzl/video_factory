"""日常故事业务管理。"""

from __future__ import annotations

import logging
from typing import Any

from app.repositories import repo_daily_story, repo_job, repo_job_log, repo_segment
from app.repositories.connection import connection
from app.services.llm.llm_mgr import llm_mgr
from app.utils.async_util import run_in_background
from app.utils.job_info import merge_job_info, merge_job_script_params

logger = logging.getLogger(__name__)

_STATUS_PROCESSING = "processing"
_STATUS_ACTIVE = "active"
_STATUS_FAILED = "failed"


def _story_has_content(story: dict[str, Any] | None) -> bool:
    if not isinstance(story, dict):
        return False
    return bool(story.get("dialogue") or [])


def _ensure_story_quality(row: dict, *, persist: bool = False, conn=None) -> dict:
    """旧稿无 quality 时补打分；persist=True 时写回 DB。"""
    from app.services.daily_story.quality import attach_daily_story_quality

    story = row.get("story")
    if not isinstance(story, dict):
        return row
    if not (story.get("dialogue") or []):
        return row
    quality = story.get("quality")
    if isinstance(quality, dict) and quality.get("grade"):
        return row
    attach_daily_story_quality(story)
    row["story"] = story
    if persist and conn is not None and row.get("id") is not None:
        repo_daily_story.update_story(conn, int(row["id"]), story=story)
    return row


class DailyStoryMgr:
    def _queue_story_generation(
        self,
        story_id: int,
        theme: str,
        *,
        is_regenerate: bool,
    ) -> None:
        action = "regenerate" if is_regenerate else "generate"

        def _worker() -> None:
            try:
                story = llm_mgr.generate_daily_story(theme)
                new_score = story.get("quality", {}).get("score", 0)
                with connection() as conn:
                    old_row = repo_daily_story.get_story(conn, story_id)
                    old_story = old_row.get("story") if old_row else None
                    old_score = (
                        old_story.get("quality", {}).get("score", 0)
                        if isinstance(old_story, dict) else 0
                    )
                    if old_score > new_score:
                        logger.info(
                            "[DAILY_STORY] async %s keeping old (score %d > new %d) "
                            "story_id=%d theme=%r",
                            action, old_score, new_score, story_id, theme,
                        )
                        repo_daily_story.update_story(
                            conn, story_id, status=_STATUS_ACTIVE,
                        )
                    else:
                        repo_daily_story.update_story(
                            conn, story_id, story=story, status=_STATUS_ACTIVE,
                        )
                logger.info(
                    "[DAILY_STORY] async %s done story_id=%d theme=%r score=%d",
                    action, story_id, theme, new_score,
                )
            except Exception as exc:
                logger.error(
                    "[DAILY_STORY] async %s failed story_id=%d theme=%r: %s",
                    action,
                    story_id,
                    theme,
                    exc,
                )
                with connection() as conn:
                    repo_daily_story.update_story(
                        conn,
                        story_id,
                        status=_STATUS_FAILED,
                    )

        run_in_background(_worker)
        logger.info(
            "[DAILY_STORY] async %s queued story_id=%d theme=%r",
            action,
            story_id,
            theme,
        )

    def recover_processing_stories(self) -> int:
        """服务重启后恢复卡在 processing 的日常故事生成。"""
        with connection() as conn:
            rows = repo_daily_story.list_stories(
                conn,
                status=_STATUS_PROCESSING,
                limit=200,
                offset=0,
            )

        if not rows:
            logger.info("no stuck daily stories to recover")
            return 0

        for row in rows:
            story_id = int(row["id"])
            theme = str(row.get("theme") or "").strip()
            if not theme:
                logger.warning(
                    "[DAILY_STORY] recovery skipped story_id=%d: empty theme",
                    story_id,
                )
                with connection() as conn:
                    repo_daily_story.update_story(
                        conn,
                        story_id,
                        status=_STATUS_FAILED,
                    )
                continue

            is_regenerate = _story_has_content(row.get("story"))
            logger.warning(
                "[DAILY_STORY] recovering stuck story_id=%d theme=%r regenerate=%s",
                story_id,
                theme,
                is_regenerate,
            )
            self._queue_story_generation(
                story_id,
                theme,
                is_regenerate=is_regenerate,
            )

        logger.warning(
            "recovered %d stuck daily story/stories",
            len(rows),
        )
        return len(rows)

    def list_stories(
        self,
        *,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict:
        """返回 {items: [...], total: N}。"""
        with connection() as conn:
            items = repo_daily_story.list_stories(
                conn, status=status, limit=limit, offset=offset
            )
            total = repo_daily_story.count_stories(conn, status=status)
            # 列表补分（内存）；打开详情 get 时再持久化
            items = [_ensure_story_quality(item) for item in items]
            return {"items": items, "total": total}

    def get_story(self, story_id: int) -> dict:
        with connection() as conn:
            row = repo_daily_story.get_story(conn, story_id)
            return _ensure_story_quality(row, persist=True, conn=conn)

    def generate_and_save(self, theme: str) -> dict[str, Any]:
        """异步生成：先落 processing 占位，立刻返回，后台写结果。"""
        theme = (theme or "").strip()
        if not theme:
            raise ValueError("theme is empty")
        with connection() as conn:
            story_id = repo_daily_story.insert_story(
                conn,
                theme=theme,
                story={},
                status=_STATUS_PROCESSING,
            )
            row = repo_daily_story.get_story(conn, story_id)

        self._queue_story_generation(story_id, theme, is_regenerate=False)
        return row

    def delete_stories(self, ids: list[int]) -> dict[str, Any]:
        with connection() as conn:
            deleted = repo_daily_story.delete_stories(conn, ids)
        return {"deleted": deleted, "ids": ids}

    def generate_themes(self, count: int = 15) -> list[str]:
        return llm_mgr.generate_daily_story_themes(count)

    def create_job(
        self,
        story_id: int,
        *,
        skip_publish: bool = False,
        speech_chars_per_sec: float | None = None,
        phrase_gap_sec: float | None = None,
    ) -> dict:
        """基于日常故事创建视频任务（pipeline=daily_story）。"""
        from app.repositories import repo_job, repo_job_log
        from app.utils.job_info import (
            DEFAULT_BGM_VOLUME_DB,
            DEFAULT_DAILY_STORY_BGM_MATERIAL_ID,
            DEFAULT_DAILY_STORY_PHRASE_GAP_SEC,
            DEFAULT_DAILY_STORY_SPEECH_CHARS_PER_SEC,
        )
        from worker.stages.daily_story.tts import DEFAULT_DAILY_SPEAKER_CONFIGS

        with connection() as conn:
            story = repo_daily_story.get_story(conn, story_id)
            status = str(story.get("status") or "")
            if status == _STATUS_PROCESSING:
                raise ValueError("故事正在生成中，请稍后再创建任务")
            story_content = story.get("story") or {}
            if not (story_content.get("dialogue") or []):
                raise ValueError("故事内容为空，无法创建任务")
            title = (story_content.get("scene_title") or "").strip()
            if not title:
                title = story.get("theme", f"日常故事-{story_id}")

            cps = (
                float(speech_chars_per_sec)
                if speech_chars_per_sec is not None
                else DEFAULT_DAILY_STORY_SPEECH_CHARS_PER_SEC
            )
            gap = (
                float(phrase_gap_sec)
                if phrase_gap_sec is not None
                else DEFAULT_DAILY_STORY_PHRASE_GAP_SEC
            )
            info = merge_job_info(
                merge_job_script_params(None, speech_chars_per_sec=cps),
                daily_story_id=story_id,
                orientation="landscape",
                video_provider="ffmpeg",
                bgm={
                    "enabled": True,
                    "material_id": DEFAULT_DAILY_STORY_BGM_MATERIAL_ID,
                    "volume_db": DEFAULT_BGM_VOLUME_DB,
                },
                subtitle={"enabled": False},
            )
            speaker_configs = {
                name: dict(cfg) for name, cfg in DEFAULT_DAILY_SPEAKER_CONFIGS.items()
            }
            speaker_configs["phrase_gap_sec"] = gap
            info["tts"] = {"speaker_configs": speaker_configs}
            job = repo_job.create_job(
                conn,
                title,
                skip_publish=skip_publish,
                stage="script",
                status="pending",
                pipeline="chat",
                material_id=story_id,
                info=info,
            )
            repo_job_log.append_log(
                conn,
                job["id"],
                "api",
                f"created daily story job: story_id={story_id}, title={title!r}",
            )
            repo_daily_story.set_job_id(conn, story_id, job["id"])
            return job

    def update_story(self, story_id: int, *, story: dict[str, Any]) -> dict:
        """更新日常故事内容（保存时重算观感分）。"""
        from app.services.daily_story.quality import attach_daily_story_quality

        if isinstance(story, dict):
            attach_daily_story_quality(story)
        with connection() as conn:
            return repo_daily_story.update_story(conn, story_id, story=story)

    def regenerate_story(self, story_id: int) -> dict:
        """异步重新生成：立刻标 processing 返回，后台替换内容。"""
        with connection() as conn:
            old = repo_daily_story.get_story(conn, story_id)
            if str(old.get("status") or "") == _STATUS_PROCESSING:
                return old
            theme = str(old.get("theme") or "").strip()
            if not theme:
                raise ValueError("theme is empty")
            row = repo_daily_story.update_story(
                conn,
                story_id,
                status=_STATUS_PROCESSING,
            )

        self._queue_story_generation(story_id, theme, is_regenerate=True)
        return row

    def sync_to_job(self, story_id: int, *, story: dict[str, Any] | None = None) -> dict:
        """更新故事内容并同步到已有任务，重置脚本阶段使其重新生成。"""
        with connection() as conn:
            old = repo_daily_story.get_story(conn, story_id)
            job_id = old.get("job_id")
            if not job_id:
                raise ValueError("该故事尚未创建任务，无法同步")

            # 更新故事内容
            if story:
                repo_daily_story.update_story(conn, story_id, story=story)

            # 重置任务脚本阶段
            job = repo_job.get_job(conn, job_id)
            title = (story or {}).get("scene_title", "") or old.get("story", {}).get("scene_title", "") or job["title"]
            repo_job.update_job(
                conn,
                job_id,
                title=title.strip(),
                stage="script",
                status="pending",
                script_json=None,
            )
            repo_segment.delete_segments(conn, job_id)

            repo_job_log.append_log(
                conn,
                job_id,
                "api",
                f"synced daily story #{story_id} to job #{job_id}, stage reset to script",
            )
            return repo_job.get_job(conn, job_id)


daily_story_mgr = DailyStoryMgr()
