"""选题库业务管理。"""

from __future__ import annotations

import logging

from app.config import get_settings
from app.repositories import job_repo, title_repo
from app.repositories.connection import connection
from app.services.job.job_mgr import job_mgr
from app.services.llm.llm_mgr import llm_mgr
from app.services.llm.llm_topics import normalize_title
from app.services.topic.hot_pipeline import (
    HOT_SOURCE,
    HotPipelineOptions,
    persist_scored_hot_topics,
    run_hot_pipeline,
)
from app.services.topic.title_scorer import score_title, status_from_score
from app.services.topic.topic_task_mgr import topic_task_mgr

logger = logging.getLogger(__name__)

_RUN_MODES = frozenset({"none", "script", "full"})


class TopicMgr:
    def list_titles(
        self,
        *,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        with connection() as conn:
            return title_repo.list_titles(
                conn, status=status, limit=limit, offset=offset
            )

    def add_topics(
        self,
        items: list[dict],
        *,
        source: str = "manual",
    ) -> dict:
        settings = get_settings()
        max_len = settings.max_title_length
        added: list[dict] = []
        skipped = 0
        with connection() as conn:
            for item in items:
                raw_title = str(item.get("title") or "").strip()
                if not raw_title:
                    skipped += 1
                    continue
                title = normalize_title(raw_title, max_len=max_len)
                row = title_repo.insert_title(
                    conn,
                    title=title,
                    track=item.get("track"),
                    template=item.get("template"),
                    hook=item.get("hook"),
                    source=source,
                )
                if row is None:
                    skipped += 1
                else:
                    added.append(row)
        return {"added": added, "skipped": skipped, "count": len(added)}

    def generate_and_save(
        self,
        theme: str,
        *,
        count: int = 10,
        system_prompt: str | None = None,
        user_prompt: str | None = None,
    ) -> dict:
        logger.info("[TOPIC] save start theme=%r count=%d", theme, count)
        topics = llm_mgr.generate_topics(
            theme,
            count=count,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
        result = self.add_topics(topics, source="llm")
        logger.info(
            "[TOPIC] save done theme=%r generated=%d added=%d skipped=%d",
            theme,
            len(topics),
            result["count"],
            result["skipped"],
        )
        return {
            "theme": theme,
            "generated": len(topics),
            **result,
        }

    def score_titles(self, title_ids: list[int] | None = None) -> dict:
        with connection() as conn:
            if title_ids:
                rows = title_repo.list_by_ids(conn, title_ids)
            else:
                rows = title_repo.list_pending_score(conn)

            scored: list[dict] = []
            for row in rows:
                if row["status"] == "enqueued":
                    continue
                result = score_title(
                    row["title"],
                    track=row.get("track"),
                    template=row.get("template"),
                    hook=row.get("hook"),
                )
                status = status_from_score(result)
                updated = title_repo.update_title(
                    conn,
                    row["id"],
                    score=result.total,
                    score_detail=result.to_dict(),
                    status=status,
                )
                scored.append(updated)
        return {"scored": scored, "count": len(scored)}

    def delete_titles(self, title_ids: list[int]) -> dict:
        with connection() as conn:
            deleted = title_repo.delete_titles(conn, title_ids)
        return {"deleted": deleted, "ids": title_ids}

    def enqueue_titles(
        self,
        title_ids: list[int] | None = None,
        *,
        skip_publish: bool = True,
        run_mode: str = "script",
    ) -> dict:
        if run_mode not in _RUN_MODES:
            raise ValueError(f"run_mode must be one of {sorted(_RUN_MODES)}")

        with connection() as conn:
            if title_ids:
                rows = title_repo.list_by_ids(conn, title_ids)
            else:
                rows = title_repo.list_queued(conn)

            jobs: list[dict] = []
            for row in rows:
                if row["status"] != "queued":
                    continue
                if row.get("job_id"):
                    continue
                job = job_repo.create_job(
                    conn,
                    row["title"],
                    skip_publish=skip_publish,
                    stage="script",
                    status="idle",
                )
                title_repo.update_title(
                    conn,
                    row["id"],
                    status="enqueued",
                    job_id=job["id"],
                )
                jobs.append(job)

        if run_mode == "script":
            for job in jobs:
                job_mgr.run_script(job["id"], to_end=False)
        elif run_mode == "full":
            for job in jobs:
                job_mgr.run_script(job["id"], to_end=True)

        logger.info(
            "[TOPIC] enqueue done count=%d run_mode=%s job_ids=%s",
            len(jobs),
            run_mode,
            [job["id"] for job in jobs],
        )
        return {"jobs": jobs, "count": len(jobs), "run_mode": run_mode}

    def import_from_hot_search(
        self,
        *,
        limit: int = 50,
        l1_rules: bool = False,
        count_per_theme: int = 3,
        use_theme_llm: bool = True,
        min_score: int = 70,
    ) -> dict:
        logger.info(
            "[TOPIC] hot import start limit=%d l1_rules=%s count_per_theme=%d min_score=%d",
            limit,
            l1_rules,
            count_per_theme,
            min_score,
        )
        payload = run_hot_pipeline(
            HotPipelineOptions(
                limit=limit,
                l1_rules=l1_rules,
                count_per_theme=count_per_theme,
                use_theme_llm=use_theme_llm,
                convert_themes=True,
                generate_titles=True,
            )
        )
        topics = payload.get("topics") or []
        save_result = persist_scored_hot_topics(topics, min_score=min_score)
        result = {
            **payload,
            **save_result,
        }
        logger.info(
            "[TOPIC] hot import done added=%d skipped=%d themes=%d",
            save_result["count"],
            save_result["skipped"],
            payload.get("summary", {}).get("themes", 0),
        )
        return result

    def start_import_from_hot_search(
        self,
        *,
        limit: int = 50,
        l1_rules: bool = False,
        count_per_theme: int = 3,
        use_theme_llm: bool = True,
        min_score: int = 70,
    ) -> dict:
        task = topic_task_mgr.start(
            "hot_import",
            lambda: self.import_from_hot_search(
                limit=limit,
                l1_rules=l1_rules,
                count_per_theme=count_per_theme,
                use_theme_llm=use_theme_llm,
                min_score=min_score,
            ),
        )
        return task.to_dict()


topic_mgr = TopicMgr()
