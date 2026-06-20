from __future__ import annotations

from flask import Blueprint

from app.api.errors import APIError
from app.api.utils import (
    get_json_body,
    get_query,
    json_ok,
    parse_bool,
    parse_int_list,
    parse_query_int,
    parse_str,
)
from app.services.llm.llm_mgr import llm_mgr
from app.services.topic.topic_mgr import topic_mgr

bp = Blueprint("api_topic", __name__, url_prefix="/v_factory/api/topic")


def _parse_count(data: dict, *, default: int = 10) -> int:
    raw = data.get("count", default)
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise APIError("count must be integer") from exc
    if value < 1 or value > 20:
        raise APIError("count must be between 1 and 20")
    return value


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
    system_prompt = parse_str(data, "system_prompt", required=False)
    user_prompt = parse_str(data, "user_prompt", required=False)
    save = parse_bool(data, "save", default=False)
    count = _parse_count(data)

    if not theme and not user_prompt:
        raise APIError("theme or user_prompt is required")

    if save:
        result = topic_mgr.generate_and_save(
            theme or "",
            count=count,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
        return json_ok(result)

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


@bp.post("/score")
def score_topics_route():
    data = get_json_body(required=False)
    ids = parse_int_list(data or {}, "ids", allow_empty=True)
    return json_ok(topic_mgr.score_titles(ids))


@bp.post("/enqueue")
def enqueue_topics_route():
    data = get_json_body(required=False)
    ids = parse_int_list(data or {}, "ids", allow_empty=True)
    skip_publish = parse_bool(data or {}, "skip_publish", default=True)
    return json_ok(
        topic_mgr.enqueue_titles(ids, skip_publish=skip_publish)
    )


@bp.post("/delete")
def delete_topics_route():
    data = get_json_body()
    ids = parse_int_list(data, "ids")
    if not ids:
        raise APIError("ids is required")
    return json_ok(topic_mgr.delete_titles(ids))
