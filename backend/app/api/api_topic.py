from __future__ import annotations

import logging

from flask import Blueprint

from app.api.errors import APIError
from app.api.utils import (
    get_json_body,
    get_query,
    json_ok,
    parse_bool,
    parse_id,
    parse_int,
    parse_int_list,
    parse_query_int,
    parse_str,
)
from app.services.topic.catalog import TOPIC_CATEGORIES, catalog_for_api
from app.services.topic.topic_mgr import topic_mgr

bp = Blueprint("api_topic", __name__, url_prefix="/v_factory/api/topic")

logger = logging.getLogger(__name__)


@bp.get("/catalog")
def topic_catalog_route():
    """选题大分类、模板与提示配置。"""
    return json_ok({"categories": catalog_for_api()})


@bp.get("/list")
def list_titles_route():
    status = get_query("status")
    limit = parse_query_int("limit", 50, minimum=1, maximum=200)
    offset = parse_query_int("offset", 0, minimum=0)
    return json_ok(topic_mgr.list_titles(status=status, limit=limit, offset=offset))


@bp.post("/gen")
def generate_topic_route():
    """生成选题标题列表，支持大分类 + 关键词，或自定义 prompt。"""
    data = get_json_body()
    theme = parse_str(data, "theme", required=False)
    user_prompt = parse_str(data, "user_prompt", required=False)
    system_prompt = parse_str(data, "system_prompt", required=False)
    category = parse_str(data, "category", required=False)
    keywords = parse_str(data, "keywords", required=False)

    custom_prompt = bool(system_prompt or user_prompt)
    if not custom_prompt:
        if not category:
            raise APIError("category is required unless using custom prompts")
        if category not in TOPIC_CATEGORIES:
            raise APIError(f"category must be one of: {', '.join(sorted(TOPIC_CATEGORIES))}")
        if not theme and not keywords:
            raise APIError("theme or keywords is required for structured generation")

    count = parse_int(data, "count", 10, minimum=1, maximum=20)
    save = parse_bool(data, "save", default=False)

    logger.info(
        "[TOPIC] api /gen category=%r theme=%r count=%d save=%s custom_prompt=%s",
        category or "",
        theme or "",
        count,
        save,
        custom_prompt,
    )

    if save:
        return json_ok(
            topic_mgr.generate_and_save(
                theme or "",
                count=count,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                category=category,
                keywords=keywords or None,
            )
        )

    topics = topic_mgr.generate_topics(
        theme or "",
        count=count,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        category=category,
        keywords=keywords or None,
    )
    return json_ok(
        {
            "category": category or "",
            "theme": theme or "",
            "count": len(topics),
            "topics": topics,
            "titles": [item["title"] for item in topics],
        }
    )


@bp.post("/optimize")
def optimize_topic_route():
    """对单条选题 LLM 优化重写并重新打分。"""
    data = get_json_body()
    title_id = parse_id(data)
    direction = (data.get("direction") or "").strip() or None
    logger.info("[TOPIC] api /optimize id=%d direction=%r", title_id, direction)
    return json_ok(topic_mgr.optimize_title(title_id, direction=direction))


@bp.post("/score")
def score_topics_route():
    data = get_json_body(required=False)
    ids = parse_int_list(data or {}, "ids", allow_empty=True)
    return json_ok(topic_mgr.score_titles(ids))


@bp.post("/enqueue")
def enqueue_topics_route():
    data = get_json_body(required=False)
    ids = parse_int_list(data, "ids", allow_empty=True)
    skip_publish = parse_bool(data, "skip_publish", default=True)
    run_mode = data.get("run_mode", "script")
    if not isinstance(run_mode, str) or run_mode not in {"none", "script", "full"}:
        raise APIError("run_mode must be none, script, or full")
    return json_ok(
        topic_mgr.enqueue_titles(ids, skip_publish=skip_publish, run_mode=run_mode)
    )


@bp.post("/update")
def update_topic_route():
    """手动修改选题标题/分类/模板/钩子。"""
    data = get_json_body()
    title_id = parse_id(data)
    title = parse_str(data, "title", required=False) or None
    category = parse_str(data, "category", required=False) or None
    template = parse_str(data, "template", required=False) or None
    hook = parse_str(data, "hook", required=False) or None
    if category and category not in TOPIC_CATEGORIES:
        raise APIError(f"category must be one of: {', '.join(sorted(TOPIC_CATEGORIES))}")
    result = topic_mgr.update_title(
        title_id,
        title=title,
        category=category,
        template=template,
        hook=hook,
    )
    if result is None:
        raise APIError("标题不存在")
    return json_ok({"title": result})


@bp.post("/delete")
def delete_topics_route():
    data = get_json_body()
    ids = parse_int_list(data, "ids")
    if not ids:
        raise APIError("ids is required")
    return json_ok(topic_mgr.delete_titles(ids))


@bp.post("/delete-low")
def delete_low_score_topics_route():
    data = get_json_body(required=False)
    max_score = parse_int(data or {}, "max_score", 75, minimum=0, maximum=100)
    return json_ok(topic_mgr.delete_low_score_titles(max_score))
