from __future__ import annotations

import logging

from flask import Blueprint

from app.api.errors import APIError
from app.api.utils import (
    get_json_body,
    get_query,
    json_ok,
    parse_bool,
    parse_int,
    parse_int_list,
    parse_query_int,
    parse_str,
)
from app.services.llm.llm_mgr import llm_mgr
from app.services.topic.topic_mgr import topic_mgr

bp = Blueprint("api_topic", __name__, url_prefix="/v_factory/api/topic")

logger = logging.getLogger(__name__)


@bp.get("/list")
def list_titles_route():
    status = get_query("status")
    limit = parse_query_int("limit", 50, minimum=1, maximum=200)
    offset = parse_query_int("offset", 0, minimum=0)
    return json_ok(topic_mgr.list_titles(status=status, limit=limit, offset=offset))


@bp.post("/gen")
def generate_topic_route():
    """生成选题标题列表，支持自定义 system / user 提示词。"""
    data = get_json_body()
    theme = parse_str(data, "theme", required=False)
    user_prompt = parse_str(data, "user_prompt", required=False)
    if not theme and not user_prompt:
        raise APIError("theme or user_prompt is required")

    count = parse_int(data, "count", 10, minimum=1, maximum=20)
    save = parse_bool(data, "save", default=False)
    system_prompt = parse_str(data, "system_prompt", required=False)

    logger.info(
        "[TOPIC] api /gen theme=%r count=%d save=%s custom_prompt=%s",
        theme or "",
        count,
        save,
        bool(system_prompt or user_prompt),
    )

    if save:
        return json_ok(
            topic_mgr.generate_and_save(
                theme or "",
                count=count,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
        )

    topics = llm_mgr.generate_topics(
        theme or "",
        count=count,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
    )
    return json_ok(
        {
            "theme": theme or "",
            "count": len(topics),
            "topics": topics,
            "titles": [item["title"] for item in topics],
        }
    )


@bp.post("/hot")
def import_hot_topics_route():
    """从 B 站热搜采集、筛选、生成标题并写入选题库（source=热搜）。"""
    data = get_json_body(required=False)
    limit = parse_int(data, "limit", 50, minimum=1, maximum=50)
    count_per_theme = parse_int(data, "count_per_theme", 3, minimum=1, maximum=20)
    l1_rules = parse_bool(data, "l1_rules", default=False)
    use_theme_llm = parse_bool(data, "use_theme_llm", default=True)
    if "min_score" in data:
        min_score = parse_int(data, "min_score", 70, minimum=0, maximum=100)
    elif data.get("only_queued") is False:
        min_score = 0
    else:
        min_score = 70

    logger.info(
        "[TOPIC] api /hot limit=%d count_per_theme=%d l1_rules=%s min_score=%d",
        limit,
        count_per_theme,
        l1_rules,
        min_score,
    )
    return json_ok(
        topic_mgr.import_from_hot_search(
            limit=limit,
            l1_rules=l1_rules,
            count_per_theme=count_per_theme,
            use_theme_llm=use_theme_llm,
            min_score=min_score,
        )
    )


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


@bp.post("/delete")
def delete_topics_route():
    data = get_json_body()
    ids = parse_int_list(data, "ids")
    if not ids:
        raise APIError("ids is required")
    return json_ok(topic_mgr.delete_titles(ids))
