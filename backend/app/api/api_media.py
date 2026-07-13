"""媒体文件 API：时长查询、静态媒体下发。"""

from __future__ import annotations

from flask import Blueprint, abort, send_file

from app.api.errors import APIError
from app.api.utils import get_query, json_ok
from app.services.media.media_serve_mgr import media_serve_mgr

bp = Blueprint("api_media", __name__, url_prefix="/v_factory/api/media")


@bp.get("/getDuration")
def get_duration_route():
    """获取媒体文件时长（秒）。"""
    file_path = get_query("path")
    if not file_path:
        raise APIError("path is required")
    try:
        return json_ok(media_serve_mgr.get_duration(file_path))
    except FileNotFoundError as exc:
        raise APIError(str(exc), status_code=404, code="not_found") from exc
    except ValueError as exc:
        raise APIError(str(exc), status_code=400, code="bad_request") from exc
    except OSError as exc:
        raise APIError(f"cannot probe duration: {exc}", status_code=500) from exc


@bp.get("/files/<path:filepath>")
def serve_media_file(filepath: str):
    """按路径返回媒体文件，支持 Range 请求。"""
    try:
        data = media_serve_mgr.prepare_serve_file(filepath)
    except FileNotFoundError:
        abort(404)
    except ValueError:
        abort(400)
    except OSError:
        abort(500)
    return send_file(data["path"], mimetype=data["mimetype"], conditional=True, max_age=604800)
