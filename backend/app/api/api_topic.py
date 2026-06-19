from __future__ import annotations

from flask import Blueprint

from app.api.errors import APIError
from app.api.utils import get_json_body, json_ok, parse_str
from app.services.llm.llm_mgr import llm_mgr

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


@bp.post("/gen")
def generate_topic_route():
    """生成选题标题列表，支持自定义 system / user 提示词。"""
    data = get_json_body()
    theme = parse_str(data, "theme", required=False)
    system_prompt = parse_str(data, "system_prompt", required=False)
    user_prompt = parse_str(data, "user_prompt", required=False)
    count = _parse_count(data)

    if not theme and not user_prompt:
        raise APIError("theme or user_prompt is required")

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
