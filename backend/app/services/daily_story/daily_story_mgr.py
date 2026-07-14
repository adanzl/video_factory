"""日常故事业务管理。"""

from __future__ import annotations

import logging
from typing import Any

from app.repositories import repo_daily_story
from app.repositories.connection import connection
from app.services.llm.llm_mgr import llm_mgr
from app.utils.job_info import merge_job_info

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

    def generate_themes(self, count: int = 2) -> list[str]:
        return llm_mgr.generate_daily_story_themes(count)

    def create_job(self, story_id: int, *, skip_publish: bool = False) -> dict:
        """基于日常故事创建视频任务（pipeline=daily_story）。"""
        from app.repositories import repo_job, repo_job_log

        with connection() as conn:
            story = repo_daily_story.get_story(conn, story_id)
            story_content = story.get("story") or {}
            title = (story_content.get("scene_title") or "").strip()
            if not title:
                title = story.get("theme", f"日常故事-{story_id}")

            job = repo_job.create_job(
                conn,
                title,
                skip_publish=skip_publish,
                stage="script",
                status="pending",
                pipeline="chat",
                material_id=story_id,
                info=merge_job_info(None, daily_story_id=story_id),
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


daily_story_mgr = DailyStoryMgr()
