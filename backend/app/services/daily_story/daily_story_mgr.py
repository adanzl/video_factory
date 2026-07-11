"""日常故事业务管理。"""

from __future__ import annotations

import logging
from typing import Any

from app.repositories import repo_daily_story
from app.repositories.connection import connection
from app.services.llm.llm_mgr import llm_mgr

logger = logging.getLogger(__name__)


class DailyStoryMgr:
    def list_stories(
        self,
        *,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        with connection() as conn:
            return repo_daily_story.list_stories(
                conn, status=status, limit=limit, offset=offset
            )

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


daily_story_mgr = DailyStoryMgr()
