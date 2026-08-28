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
    parse_optional_str,
)
from app.services.daily_story.gold_story.gold_story_mgr import gold_story_mgr

bp = Blueprint(
    "api_gold_chat",
    __name__,
    url_prefix="/v_factory/api/gold_chat",
)

logger = logging.getLogger(__name__)


def _parse_source_id_list(data: dict, field: str = "source_ids") -> list[str] | None:
    raw = data.get(field)
    if raw is None:
        return None
    if isinstance(raw, list):
        out = [str(x).strip() for x in raw if str(x).strip()]
        return out or None
    if isinstance(raw, str):
        out = [s.strip() for s in raw.split(",") if s.strip()]
        return out or None
    raise APIError(f"{field} must be string or list")


@bp.get("/list")
def list_route():
    status = get_query("status")
    if status in ("", "all", "*"):
        status = None
    has_story_raw = (get_query("has_story") or "").strip().lower()
    has_story: bool | None = None
    if has_story_raw in ("1", "true", "yes"):
        has_story = True
    elif has_story_raw in ("0", "false", "no"):
        has_story = False
    limit = parse_query_int("limit", 15, required=False, minimum=1, maximum=200)
    offset = parse_query_int("offset", 0, required=False, minimum=0)
    return json_ok(
        gold_story_mgr.list_items(
            status=status,
            has_story=has_story,
            limit=limit,
            offset=offset,
        ),
    )


@bp.get("/get")
def get_route():
    gold_story_id: int | None = None
    source_id = get_query("source_id")
    if get_query("id"):
        gold_story_id = parse_id(field="id")
    if gold_story_id is None and not source_id:
        raise APIError("id 或 source_id 必填", status_code=400)
    try:
        return json_ok(
            gold_story_mgr.get_chat(
                gold_story_id=gold_story_id,
                source_id=source_id,
            ),
        )
    except KeyError:
        raise APIError("金故事不存在", status_code=404)


@bp.get("/transcript")
def transcript_route():
    gold_story_id: int | None = None
    source_id = get_query("source_id")
    if get_query("id"):
        gold_story_id = parse_id(field="id")
    if gold_story_id is None and not source_id:
        raise APIError("id 或 source_id 必填", status_code=400)
    try:
        return json_ok(
            gold_story_mgr.get_transcript(
                gold_story_id=gold_story_id,
                source_id=source_id,
            ),
        )
    except KeyError:
        raise APIError("金故事不存在", status_code=404)


@bp.post("/convert")
def convert_route():
    data = get_json_body()
    gold_story_id = parse_int(data, "id", 0, minimum=0, maximum=10_000_000)
    if gold_story_id <= 0:
        gold_story_id = None
    source_id = parse_optional_str(data, "source_id")
    force = parse_bool(data, "force", default=False)
    if gold_story_id is None and not source_id:
        raise APIError("id 或 source_id 必填", status_code=400)
    logger.info(
        "[GOLD_CHAT] convert id=%s source_id=%s force=%s",
        gold_story_id,
        source_id,
        force,
    )
    try:
        return json_ok(
            gold_story_mgr.convert_one(
                gold_story_id=gold_story_id,
                source_id=source_id,
                force=force,
            ),
        )
    except KeyError:
        raise APIError("金故事不存在", status_code=404)
    except ValueError as exc:
        logger.error("[GOLD_CHAT] convert failed id=%s source_id=%s: %s", gold_story_id, source_id, exc)
        raise APIError(str(exc), status_code=400)


@bp.get("/collect")
def collect_status_route():
    return json_ok(gold_story_mgr.collect_status())


@bp.post("/collect")
def collect_route():
    data = get_json_body(required=False) or {}
    max_items = parse_int(data, "max", 10, minimum=1, maximum=50)
    logger.info("[GOLD_CHAT] collect max=%d", max_items)
    try:
        return json_ok(gold_story_mgr.collect(max_candidates=max_items))
    except RuntimeError as exc:
        raise APIError(str(exc), status_code=409, code="collect_busy") from exc


@bp.get("/reimport")
def reimport_status_route():
    return json_ok(gold_story_mgr.reimport_status())


@bp.post("/reimport")
def reimport_route():
    data = get_json_body(required=False) or {}
    gold_story_ids = parse_int_list(data, "ids", allow_empty=False)
    source_ids = _parse_source_id_list(data) or []
    source_id = parse_optional_str(data, "source_id")
    if source_id:
        source_ids = [source_id, *source_ids]
    force_transcript = parse_bool(data, "force_transcript", default=True)
    if not gold_story_ids and not source_ids:
        raise APIError("ids 或 source_id 必填", status_code=400)
    logger.info(
        "[GOLD_CHAT] reimport ids=%s source_ids=%s force_transcript=%s",
        gold_story_ids,
        source_ids,
        force_transcript,
    )
    try:
        return json_ok(
            gold_story_mgr.reimport(
                gold_story_ids=gold_story_ids,
                source_ids=source_ids,
                force_transcript=force_transcript,
            ),
        )
    except RuntimeError as exc:
        raise APIError(str(exc), status_code=409, code="reimport_busy") from exc
    except ValueError as exc:
        raise APIError(str(exc), status_code=400)


@bp.post("/batch")
def batch_route():
    data = get_json_body(required=False) or {}
    max_items = parse_int(data, "max", 10, minimum=1, maximum=50)
    status = parse_optional_str(data, "status") or "active"
    force = parse_bool(data, "force", default=False)
    gold_story_ids = parse_int_list(data, "ids", allow_empty=False)
    source_ids = _parse_source_id_list(data)
    logger.info(
        "[GOLD_CHAT] batch max=%d status=%s force=%s ids=%s source_ids=%s",
        max_items,
        status,
        force,
        gold_story_ids,
        source_ids,
    )
    result = gold_story_mgr.batch_convert(
        max_items=max_items,
        status=status,
        gold_story_ids=gold_story_ids,
        source_ids=source_ids,
        force=force,
    )
    logger.info(
        "[GOLD_CHAT] batch done requested=%d selected=%d ok=%d skipped=%d failed=%d",
        max_items,
        result.get("selected", 0),
        result.get("ok", 0),
        result.get("skipped", 0),
        result.get("failed", 0),
    )
    return json_ok(result)


@bp.post("/reject")
def reject_route():
    data = get_json_body()
    ids = parse_int_list(data, "ids")
    if not ids:
        raise APIError("ids 必填", status_code=400)
    logger.info("[GOLD_CHAT] reject ids=%s", ids)
    try:
        return json_ok(gold_story_mgr.reject_stories(ids))
    except ValueError as exc:
        raise APIError(str(exc), status_code=400)


@bp.post("/delete")
def delete_route():
    data = get_json_body()
    ids = parse_int_list(data, "ids")
    if not ids:
        raise APIError("ids 必填", status_code=400)
    logger.info("[GOLD_CHAT] delete ids=%s", ids)
    try:
        return json_ok(gold_story_mgr.delete_stories(ids))
    except ValueError as exc:
        raise APIError(str(exc), status_code=400)


@bp.post("/import")
def import_route():
    data = get_json_body()
    gold_story_id = parse_int(data, "id", 0, minimum=0, maximum=10_000_000)
    if gold_story_id <= 0:
        gold_story_id = None
    source_id = parse_optional_str(data, "source_id")
    force = parse_bool(data, "force", default=False)
    if gold_story_id is None and not source_id:
        raise APIError("id 或 source_id 必填", status_code=400)
    logger.info(
        "[GOLD_CHAT] import id=%s source_id=%s force=%s",
        gold_story_id,
        source_id,
        force,
    )
    try:
        return json_ok(
            gold_story_mgr.import_one(
                gold_story_id=gold_story_id,
                source_id=source_id,
                force=force,
            ),
        )
    except KeyError:
        raise APIError("金故事不存在", status_code=404)
    except FileNotFoundError as exc:
        raise APIError(str(exc), status_code=404)
    except ValueError as exc:
        raise APIError(str(exc), status_code=400)
