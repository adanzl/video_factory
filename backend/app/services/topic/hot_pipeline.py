"""B 站热搜 → 选题流水线（采集 / L1 / L2 / 生成 / 打分）。"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.services.llm.llm_mgr import llm_mgr
from app.services.topic.hot_fetcher import fetch_all_hot_keywords
from app.services.topic.hot_filter import filter_hot_keywords
from app.services.topic.hot_theme import convert_hot_to_themes
from app.services.topic.title_scorer import score_title, status_from_score

logger = logging.getLogger(__name__)

HOT_SOURCE = "热搜"


@dataclass(frozen=True)
class HotPipelineOptions:
    limit: int = 50
    l1_rules: bool = False
    count_per_theme: int = 3
    use_theme_llm: bool = True
    convert_themes: bool = True
    generate_titles: bool = True


def run_hot_pipeline(options: HotPipelineOptions | None = None) -> dict:
    opts = options or HotPipelineOptions()
    limit = max(1, min(opts.limit, 50))
    count_per_theme = max(1, min(opts.count_per_theme, 20))

    fetched = fetch_all_hot_keywords(limit=limit)
    kept, rejected = filter_hot_keywords(fetched, use_llm=not opts.l1_rules)

    payload: dict = {
        "summary": {
            "fetched": len(fetched),
            "kept": len(kept),
            "rejected": len(rejected),
            "l1_rules": opts.l1_rules,
        },
        "kept": [
            {
                "keyword": r.item.keyword,
                "show_name": r.item.show_name,
                "mode": r.mode,
                "reason": r.reason,
            }
            for r in kept
        ],
        "rejected": [
            {
                "keyword": r.item.keyword,
                "show_name": r.item.show_name,
                "reason": r.reason,
            }
            for r in rejected
        ],
    }

    if not kept or not opts.convert_themes:
        payload["themes"] = []
        payload["topics"] = []
        payload["summary"]["themes"] = 0
        payload["summary"]["topics"] = 0
        payload["summary"]["queued"] = 0
        return payload

    themes = convert_hot_to_themes(kept, use_llm=opts.use_theme_llm)
    payload["themes"] = [t.to_dict() for t in themes]
    payload["summary"]["themes"] = len(themes)

    if not opts.generate_titles or not themes:
        payload["topics"] = []
        payload["summary"]["topics"] = 0
        payload["summary"]["queued"] = 0
        return payload

    scored_topics: list[dict] = []
    for theme_row in themes:
        topics = llm_mgr.generate_topics(theme_row.theme, count=count_per_theme)
        for topic in topics:
            result = score_title(
                topic["title"],
                track=topic.get("track") or theme_row.track,
                template=topic.get("template"),
                hook=topic.get("hook"),
            )
            scored_topics.append(
                {
                    "keyword": theme_row.keyword,
                    "theme": theme_row.theme,
                    "title": topic["title"],
                    "track": topic.get("track"),
                    "template": topic.get("template"),
                    "hook": topic.get("hook"),
                    "total": result.total,
                    "status": status_from_score(result),
                    "rejected_reason": result.rejected_reason,
                    "score_detail": result.to_dict(),
                }
            )

    payload["topics"] = scored_topics
    payload["summary"]["topics"] = len(scored_topics)
    payload["summary"]["queued"] = sum(1 for t in scored_topics if t["status"] == "queued")
    logger.info(
        "[HOT] pipeline done fetched=%d kept=%d themes=%d topics=%d queued=%d",
        payload["summary"]["fetched"],
        payload["summary"]["kept"],
        payload["summary"]["themes"],
        payload["summary"]["topics"],
        payload["summary"]["queued"],
    )
    return payload


def persist_scored_hot_topics(
    topics: list[dict],
    *,
    min_score: int = 70,
) -> dict:
    """将打分后的热搜选题写入 title 表，source=热搜。"""
    from app.config import get_settings
    from app.repositories import title_repo
    from app.repositories.connection import connection
    from app.services.llm.llm_topics import normalize_title

    added: list[dict] = []
    skipped = 0
    settings = get_settings()
    max_len = settings.max_title_length

    with connection() as conn:
        for item in topics:
            total = item.get("total")
            if total is None or int(total) < min_score:
                skipped += 1
                continue
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
                source=HOT_SOURCE,
            )
            if row is None:
                skipped += 1
                continue
            updated = title_repo.update_title(
                conn,
                row["id"],
                score=item.get("total"),
                score_detail=item.get("score_detail"),
                status=item.get("status") or "pending",
            )
            added.append(updated)

    return {"added": added, "skipped": skipped, "count": len(added), "source": HOT_SOURCE}
