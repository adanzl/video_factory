"""选题库业务管理。"""

from __future__ import annotations

import logging
import re

from app.config import get_settings
from app.repositories import repo_job, repo_title
from app.repositories.connection import connection
from app.services.job.job_mgr import job_mgr
from app.utils.job_info import (
    CONTENT_STYLE_HISTORICAL_MYSTERY,
    ORIENTATION_LANDSCAPE,
    merge_job_script_params,
)
from app.services.llm.llm_mgr import llm_mgr
from app.services.topic.catalog import (
    CATEGORY_HISTORY,
    normalize_category,
)
from app.services.topic.prompts.builder import (
    build_topic_optimize_system_prompt,
    build_topic_optimize_user_prompt,
)
from app.services.topic.text import normalize_title
from app.services.topic.scorers import (
    SCORE_THRESHOLD,
    ScoreResult,
    score_title,
    status_from_score,
)

logger = logging.getLogger(__name__)

_RUN_MODES = frozenset({"none", "script", "full"})


def _extract_keyword(title: str) -> str:
    """从标题提取核心关键词（人名/地名/事件名），用于去重。"""
    text = re.sub(r"[？?！!，,。.、\s\"\'“”]", "", title)
    if not text:
        return text
    parts = re.split(r"[的与和被在让将给从以于对把到用打上出]", text, maxsplit=1)
    head = parts[0].strip()
    if 2 <= len(head) <= 8:
        return head
    if len(head) > 8 and head.endswith(("啦", "了", "的")):
        head = head[:-1]
    return head[:6]


def _existing_keywords(conn) -> set[str]:
    rows = conn.execute("SELECT keyword FROM title WHERE keyword IS NOT NULL").fetchall()
    result: set[str] = set()
    for row in rows:
        raw = row["keyword"] or ""
        for kw in raw.split(","):
            k = kw.strip()
            if k:
                result.add(k)
    return result


class TopicMgr:
    def list_titles(
        self,
        *,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        with connection() as conn:
            return repo_title.list_titles(
                conn, status=status, limit=limit, offset=offset
            )

    def add_topics(
        self,
        items: list[dict],
        *,
        source: str = "manual",
        deduplicate_keyword: bool = False,
    ) -> dict:
        settings = get_settings()
        max_len = settings.max_title_length
        added: list[dict] = []
        skipped = 0
        seen_keywords: set[str] = set()
        with connection() as conn:
            if deduplicate_keyword:
                seen_keywords = _existing_keywords(conn)
            for item in items:
                raw_title = str(item.get("title") or "").strip()
                if not raw_title:
                    skipped += 1
                    logger.warning("[TOPIC] skip add: empty title")
                    continue
                title = normalize_title(raw_title, max_len=max_len)
                if deduplicate_keyword:
                    raw_kw = item.get("keyword") or ""
                    keywords = [k.strip() for k in raw_kw.split(",") if k.strip()]
                    if not keywords:
                        kw = None
                    else:
                        hit = any(k in seen_keywords for k in keywords)
                        if hit:
                            skipped += 1
                            logger.warning(
                                "[TOPIC] skip add: keyword conflict title=%r keywords=%s",
                                title,
                                keywords,
                            )
                            continue
                        kw = raw_kw
                        for k in keywords:
                            seen_keywords.add(k)
                else:
                    kw = None
                row = repo_title.insert_title(
                    conn,
                    title=title,
                    category=item.get("category"),
                    template=item.get("template"),
                    hook=item.get("hook"),
                    source=source,
                    keyword=kw if deduplicate_keyword else None,
                )
                if row is None:
                    skipped += 1
                    logger.warning("[TOPIC] skip add: duplicate title=%r", title)
                else:
                    added.append(row)
        return {"added": added, "skipped": skipped, "count": len(added)}

    def generate_topics(
        self,
        theme: str,
        *,
        count: int = 10,
        category: str | None = None,
        keywords: str | list[str] | None = None,
        system_prompt: str | None = None,
        user_prompt: str | None = None,
    ) -> list[dict[str, str]]:
        return llm_mgr.generate_topics(
            theme,
            count=count,
            category=category,
            keywords=keywords,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )

    def generate_and_save(
        self,
        theme: str,
        *,
        count: int = 10,
        category: str | None = None,
        keywords: str | list[str] | None = None,
        system_prompt: str | None = None,
        user_prompt: str | None = None,
    ) -> dict:
        resolved = normalize_category(category)
        logger.info(
            "[TOPIC] save start theme=%r category=%s count=%d",
            theme,
            resolved,
            count,
        )
        topics = self.generate_topics(
            theme,
            count=count,
            category=resolved,
            keywords=keywords,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
        result = self.add_topics(topics, source="llm", deduplicate_keyword=True)
        if result["added"]:
            new_ids = [row["id"] for row in result["added"]]
            self.score_titles(title_ids=new_ids)
        logger.info(
            "[TOPIC] save done theme=%r generated=%d added=%d skipped=%d",
            theme,
            len(topics),
            result["count"],
            result["skipped"],
        )
        return {
            "category": resolved,
            "theme": theme,
            "generated": len(topics),
            **result,
        }

    def optimize_title(self, title_id: int) -> dict:
        with connection() as conn:
            row = repo_title.get_title(conn, title_id)

        if row["status"] == "enqueued":
            raise ValueError("enqueued title cannot be optimized")

        settings = get_settings()
        template = row.get("template")
        category = normalize_category(row.get("category"))
        system_prompt = build_topic_optimize_system_prompt(
            max_title_len=settings.max_title_length,
            category=category,
        )
        user_prompt = build_topic_optimize_user_prompt(
            title=row["title"],
            category=category,
            template=template,
            hook=row.get("hook"),
        )
        logger.info(
            "[TOPIC] optimize start id=%d title=%r category=%r",
            title_id,
            row["title"],
            category,
        )
        topics = self.generate_topics(
            "",
            count=1,
            category=category,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
        item = topics[0]
        item["category"] = category
        if template:
            item["template"] = template
        new_title = normalize_title(
            item["title"],
            max_len=settings.max_title_length,
        )
        if not new_title:
            raise ValueError("LLM returned empty title")

        resolved_template = template or item.get("template")
        preview = score_title(
            new_title,
            category=category,
            template=resolved_template,
            hook=item.get("hook"),
        )
        if preview.total < SCORE_THRESHOLD:
            reason = preview.rejected_reason or f"总分 {preview.total} 低于阈值 {SCORE_THRESHOLD}"
            raise ValueError(f"optimized title rejected: {reason}")

        with connection() as conn:
            if new_title != row["title"]:
                existing = repo_title.find_by_titles(conn, [new_title])
                if new_title in existing:
                    raise ValueError(f"title already exists: {new_title}")
            updated = repo_title.update_title(
                conn,
                title_id,
                title=new_title,
                category=item.get("category"),
                template=item.get("template"),
                hook=item.get("hook"),
                score=None,
                score_detail=None,
                status="pending",
            )

        score_result = self.score_titles([title_id])
        scored = score_result["scored"][0] if score_result["scored"] else updated
        logger.info(
            "[TOPIC] optimize done id=%d old=%r new=%r score=%s",
            title_id,
            row["title"],
            scored["title"],
            scored.get("score"),
        )
        return {"title": scored, "previous": row}

    def score_titles(self, title_ids: list[int] | None = None) -> dict:
        with connection() as conn:
            if title_ids:
                rows = repo_title.list_by_ids(conn, title_ids)
            else:
                rows = repo_title.list_pending_score(conn)

            scored: list[dict] = []
            for row in rows:
                if row["status"] == "enqueued":
                    continue
                result = score_title(
                    row["title"],
                    category=row.get("category"),
                    template=row.get("template"),
                    hook=row.get("hook"),
                )
                status = status_from_score(result)
                updated = repo_title.update_title(
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
            deleted = repo_title.delete_titles(conn, title_ids)
        return {"deleted": deleted, "ids": title_ids}

    def delete_low_score_titles(self, max_score: int) -> dict:
        with connection() as conn:
            ids = repo_title.list_ids_below_score(conn, max_score)
            deleted = repo_title.delete_titles(conn, ids)
        logger.info(
            "[TOPIC] delete low score max_score=%d deleted=%d ids=%s",
            max_score,
            deleted,
            ids,
        )
        return {"deleted": deleted, "ids": ids, "max_score": max_score}

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
                rows = repo_title.list_by_ids(conn, title_ids)
            else:
                rows = repo_title.list_queued(conn)

            jobs: list[dict] = []
            job_hooks: list[str | None] = []
            for row in rows:
                if row["status"] != "queued":
                    continue
                if row.get("job_id"):
                    continue
                is_history = normalize_category(row.get("category")) == CATEGORY_HISTORY
                seg_sec = 15 if not is_history else 10
                hook = (row.get("hook") or "").strip() or None
                job = repo_job.create_job(
                    conn,
                    row["title"],
                    skip_publish=skip_publish,
                    stage="script",
                    status="idle",
                    info=merge_job_script_params(
                        None,
                        orientation=ORIENTATION_LANDSCAPE,
                        content_style=(
                            CONTENT_STYLE_HISTORICAL_MYSTERY
                            if is_history
                            else None
                        ),
                        narration_target_words=1800 if is_history else None,
                        segment_target_sec=seg_sec,
                        skip_title_optimize=True,
                        generate_image_prompts=True,
                        supplementary_info=hook,
                    ),
                )
                repo_title.update_title(
                    conn,
                    row["id"],
                    status="enqueued",
                    job_id=job["id"],
                )
                jobs.append(job)
                job_hooks.append(hook)

        script_kwargs = {
            "skip_title_optimize": True,
            "generate_image_prompts": True,
        }
        if run_mode == "script":
            for job, hook in zip(jobs, job_hooks):
                job_mgr.run_script(
                    job["id"],
                    to_end=False,
                    supplementary_info=hook,
                    **script_kwargs,
                )
        elif run_mode == "full":
            for job, hook in zip(jobs, job_hooks):
                job_mgr.run_script(
                    job["id"],
                    to_end=True,
                    supplementary_info=hook,
                    **script_kwargs,
                )

        logger.info(
            "[TOPIC] enqueue done count=%d run_mode=%s job_ids=%s",
            len(jobs),
            run_mode,
            [job["id"] for job in jobs],
        )
        return {"jobs": jobs, "count": len(jobs), "run_mode": run_mode}


topic_mgr = TopicMgr()

__all__ = [
    "SCORE_THRESHOLD",
    "ScoreResult",
    "TopicMgr",
    "score_title",
    "status_from_score",
    "topic_mgr",
]
