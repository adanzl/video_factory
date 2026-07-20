from __future__ import annotations

import logging

from flask import Blueprint

from app.api.errors import APIError
from app.api.utils import (
    get_json_body,
    get_query,
    json_created,
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
    limit = parse_query_int("limit", 15, required=False, minimum=1, maximum=200)
    offset = parse_query_int("offset", 0, required=False, minimum=0)
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


@bp.post("/themes")
def generate_themes_route():
    data = get_json_body(required=False) or {}
    count = parse_int(data, "count", 15, minimum=1, maximum=15)
    logger.info("[DAILY_STORY] api /themes count=%d", count)
    return json_ok(daily_story_mgr.generate_themes(count))


@bp.post("/create_job")
def create_job_route():
    data = get_json_body()
    story_id = parse_id(data)
    speech_chars_per_sec = data.get("speech_chars_per_sec")
    phrase_gap_sec = data.get("phrase_gap_sec")
    logger.info(
        "[DAILY_STORY] api /create_job story_id=%d speech_rate=%s gap=%s",
        story_id, speech_chars_per_sec, phrase_gap_sec,
    )
    try:
        job = daily_story_mgr.create_job(
            story_id,
            speech_chars_per_sec=speech_chars_per_sec,
            phrase_gap_sec=phrase_gap_sec,
        )
    except KeyError:
        raise APIError("故事不存在")
    return json_created(job)


@bp.post("/update")
def update_story_route():
    data = get_json_body()
    story_id = parse_id(data)
    story = data.get("story")
    if not isinstance(story, dict):
        raise APIError("story is required", status_code=400)
    logger.info("[DAILY_STORY] api /update story_id=%d", story_id)
    try:
        return json_ok(daily_story_mgr.update_story(story_id, story=story))
    except KeyError:
        raise APIError("故事不存在")


@bp.post("/sync_to_job")
def sync_to_job_route():
    data = get_json_body()
    story_id = parse_id(data)
    story = data.get("story")
    logger.info("[DAILY_STORY] api /sync_to_job story_id=%d", story_id)
    try:
        return json_ok(daily_story_mgr.sync_to_job(story_id, story=story))
    except ValueError as e:
        raise APIError(str(e))
    except KeyError:
        raise APIError("故事不存在")


@bp.post("/regenerate")
def regenerate_story_route():
    data = get_json_body()
    story_id = parse_id(data)
    logger.info("[DAILY_STORY] api /regenerate story_id=%d", story_id)
    try:
        return json_ok(daily_story_mgr.regenerate_story(story_id))
    except KeyError:
        raise APIError("故事不存在")
