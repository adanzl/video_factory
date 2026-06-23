"""视频片段聚合搜索 API。"""

from __future__ import annotations

import requests
from flask import Blueprint

from app.api.errors import APIError
from app.api.utils import get_json_body, get_query, json_ok, parse_id, parse_optional_int, parse_query_int, parse_str
from app.services.clip_search.clip_search_mgr import clip_search_mgr
from app.services.clip_search.preview_proxy import proxy_clip_preview
from app.services.job.job_mgr import JobBusyError, job_mgr

bp = Blueprint("api_clips", __name__, url_prefix="/v_factory/api/clips")

_VALID_PROVIDERS = frozenset({"pexels", "pixabay", "nasa"})
_VALID_ORIENTATIONS = frozenset({"portrait", "landscape", "square"})


def _parse_providers(raw: str | None) -> tuple[str, ...] | None:
    if raw is None or not str(raw).strip():
        return None
    names = [part.strip().lower() for part in str(raw).split(",") if part.strip()]
    if not names:
        return None
    unknown = [name for name in names if name not in _VALID_PROVIDERS]
    if unknown:
        raise APIError(f"unknown providers: {', '.join(unknown)}")
    return tuple(dict.fromkeys(names))


def _parse_query_str(
    name: str,
    *,
    required: bool = False,
    max_length: int = 200,
) -> str | None:
    raw = get_query(name)
    if raw is None:
        if required:
            raise APIError(f"{name} is required")
        return None
    value = raw.strip()
    if not value:
        if required:
            raise APIError(f"{name} is required")
        return None
    if len(value) > max_length:
        raise APIError(f"{name} too long (max {max_length})")
    return value


@bp.get("/sources")
def list_sources_route():
    return json_ok(clip_search_mgr.list_providers())


@bp.get("/preview")
def preview_clip_route():
    """代理外部素材视频，支持 Range 请求供浏览器播放。"""
    url = _parse_query_str("url", required=True, max_length=2048)
    try:
        return proxy_clip_preview(url)
    except ValueError as exc:
        raise APIError(str(exc), status_code=400) from exc


@bp.get("/search")
def search_clips_route():
    query = _parse_query_str("q", required=True, max_length=120)
    per_page = parse_query_int("per_page", 24, minimum=1, maximum=60)
    providers = _parse_providers(_parse_query_str("providers", required=False))
    orientation_raw = _parse_query_str("orientation", required=False)
    orientation = None
    if orientation_raw:
        orientation = orientation_raw.strip().lower()
        if orientation not in _VALID_ORIENTATIONS:
            raise APIError(f"orientation must be one of: {', '.join(sorted(_VALID_ORIENTATIONS))}")
    try:
        result = clip_search_mgr.search(
            query,
            per_page=per_page,
            providers=providers,
            orientation=orientation,
        )
    except ValueError as exc:
        raise APIError(str(exc), status_code=400) from exc
    return json_ok(result.to_dict())


@bp.post("/import-segment")
def import_segment_clip_route():
    """下载素材库视频并写入任务分段。"""
    data = get_json_body()
    job_id = parse_id(data)
    segment_index = parse_optional_int(data, "segment_index", minimum=1)
    if segment_index is None:
        raise APIError("segment_index is required")
    video_url = parse_str(data, "video_url", required=True)
    if len(video_url) > 2048:
        raise APIError("video_url too long (max 2048)")
    job_mgr.get_job(job_id)
    try:
        segment = clip_search_mgr.import_to_segment(job_id, segment_index, video_url)
    except JobBusyError as exc:
        raise APIError(str(exc), status_code=409, code="job_busy") from exc
    except KeyError as exc:
        raise APIError(str(exc), status_code=404) from exc
    except ValueError as exc:
        raise APIError(str(exc), status_code=400) from exc
    except requests.RequestException as exc:
        raise APIError(f"download failed: {exc}", status_code=502) from exc
    return json_ok(segment)
