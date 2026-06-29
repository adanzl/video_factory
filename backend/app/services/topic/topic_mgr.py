"""选题库业务管理。"""

from __future__ import annotations

import logging
import re

from app.config import get_settings
from app.repositories import job_repo, title_repo
from app.repositories.connection import connection
from app.services.job.job_mgr import job_mgr
from app.utils.job_info import (
    CONTENT_STYLE_HISTORICAL_MYSTERY,
    ORIENTATION_LANDSCAPE,
    default_orientation_for_pipeline,
    merge_job_info,
)
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


def _extract_keyword(title: str) -> str:
    """从标题提取核心关键词（人名/地名/事件名），用于去重。"""
    text = re.sub(r"[？?！!，,。.、\s\"\'“”]", "", title)
    if not text:
        return text
    # 按常用虚词/介词拆段，取第一段（通常是实体名）
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
            return title_repo.list_titles(
                conn, status=status, limit=limit, offset=offset
            )

    def add_topics(
        self,
        items: list[dict],
        *,
        source: str = "manual",
        dedup_keyword: bool = False,
    ) -> dict:
        settings = get_settings()
        max_len = settings.max_title_length
        added: list[dict] = []
        skipped = 0
        seen_keywords: set[str] = set()
        with connection() as conn:
            if dedup_keyword:
                seen_keywords = _existing_keywords(conn)
            for item in items:
                raw_title = str(item.get("title") or "").strip()
                if not raw_title:
                    skipped += 1
                    continue
                title = normalize_title(raw_title, max_len=max_len)
                if dedup_keyword:
                    raw_kw = item.get("keyword") or ""
                    keywords = [k.strip() for k in raw_kw.split(",") if k.strip()]
                    if not keywords:
                        kw = None
                    else:
                        hit = any(k in seen_keywords for k in keywords)
                        if hit:
                            skipped += 1
                            continue
                        kw = raw_kw
                        for k in keywords:
                            seen_keywords.add(k)
                else:
                    kw = None
                row = title_repo.insert_title(
                    conn,
                    title=title,
                    track=item.get("track"),
                    template=item.get("template"),
                    hook=item.get("hook"),
                    source=source,
                    keyword=kw if dedup_keyword else None,
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
        result = self.add_topics(topics, source="llm", dedup_keyword=True)
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

    def delete_low_score_titles(self, max_score: int) -> dict:
        with connection() as conn:
            ids = title_repo.list_ids_below_score(conn, max_score)
            deleted = title_repo.delete_titles(conn, ids)
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
                rows = title_repo.list_by_ids(conn, title_ids)
            else:
                rows = title_repo.list_queued(conn)

            jobs: list[dict] = []
            for row in rows:
                if row["status"] != "queued":
                    continue
                if row.get("job_id"):
                    continue
                is_history = row.get("track") == "历史悬案"
                job = job_repo.create_job(
                    conn,
                    row["title"],
                    skip_publish=skip_publish,
                    stage="script",
                    status="idle",
                    info=merge_job_info(
                        None,
                        orientation=ORIENTATION_LANDSCAPE,
                        content_style=(
                            CONTENT_STYLE_HISTORICAL_MYSTERY
                            if is_history
                            else None
                        ),
                        narration_target_words=1800 if is_history else None,
                        segment_target_sec=10 if is_history else None,
                    ),
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
