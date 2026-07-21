"""日常故事业务管理。"""

from __future__ import annotations

import logging
from typing import Any

from app.repositories import repo_daily_story, repo_job, repo_job_log, repo_segment
from app.repositories.connection import connection
from app.services.llm.llm_mgr import llm_mgr
from app.utils.job_info import merge_job_info, merge_job_script_params

logger = logging.getLogger(__name__)


class DailyStoryMgr:
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
            return {"items": items, "total": total}

    def get_story(self, story_id: int) -> dict:
        with connection() as conn:
            return repo_daily_story.get_story(conn, story_id)

    def generate_and_save(self, theme: str) -> dict[str, Any]:
        story = llm_mgr.generate_daily_story(theme)
        with connection() as conn:
            story_id = repo_daily_story.insert_story(conn, theme=theme, story=story)
            return repo_daily_story.get_story(conn, story_id)

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
            DEFAULT_DAILY_STORY_PHRASE_GAP_SEC,
            DEFAULT_DAILY_STORY_SPEECH_CHARS_PER_SEC,
        )
        from worker.stages.daily_story.tts import DEFAULT_DAILY_SPEAKER_CONFIGS

        with connection() as conn:
            story = repo_daily_story.get_story(conn, story_id)
            story_content = story.get("story") or {}
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
        """更新日常故事内容。"""
        with connection() as conn:
            return repo_daily_story.update_story(conn, story_id, story=story)

    def regenerate_story(self, story_id: int) -> dict:
        """重新生成日常故事（替换内容，不创建新记录）。"""
        with connection() as conn:
            old = repo_daily_story.get_story(conn, story_id)
            theme = old.get("theme", "")
        new_story = llm_mgr.generate_daily_story(theme)
        with connection() as conn:
            return repo_daily_story.update_story(conn, story_id, story=new_story)


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
