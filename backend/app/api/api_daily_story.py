from __future__ import annotations

import logging

from flask import Blueprint

from app.api.errors import APIError
from app.api.utils import (
    get_json_body,
    get_query,
    json_ok,
    parse_id,
    parse_int,
    parse_int_list,
    parse_query_int,
    parse_str,
)
from app.services.daily_story.daily_story_mgr import daily_story_mgr

bp = Blueprint("api_daily_story", __name__, url_prefix="/v_factory/api/daily_story")

logger = logging.getLogger(__name__)


@bp.get("/list")
def list_stories_route():
    status = get_query("status")
    limit = parse_query_int("limit", 50, minimum=1, maximum=200)
    offset = parse_query_int("offset", 0, minimum=0)
    return json_ok(daily_story_mgr.list_stories(status=status, limit=limit, offset=offset))


@bp.get("/get")
def get_story_route():
    story_id = parse_id(field="id")
    try:
        return json_ok(daily_story_mgr.get_story(story_id))
    except KeyError:
        raise APIError("故事不存在")


@bp.post("/generate")
def generate_story_route():
    data = get_json_body()
    theme = parse_str(data, "theme")
    logger.info("[DAILY_STORY] api /generate theme=%r", theme)
    return json_ok(daily_story_mgr.generate_and_save(theme))


@bp.post("/delete")
def delete_stories_route():
    data = get_json_body()
    ids = parse_int_list(data, "ids")
    if not ids:
        raise APIError("ids is required")
    return json_ok(daily_story_mgr.delete_stories(ids))
