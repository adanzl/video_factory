"""媒体文件 API：时长查询、图片查看、静态媒体下发。"""

from __future__ import annotations

import logging

from flask import Blueprint, abort, jsonify, request, send_file

from app.api.errors import APIError
from app.api.utils import get_query, json_ok, parse_int
from app.services.media.media_serve_mgr import media_serve_mgr

log = logging.getLogger(__name__)


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


@bp.get("/view/<path:filepath>")
def pic_view(filepath: str):
    """按路径查看图片，支持 w、h 参数按比例缩放并缓存。"""

    w_raw = request.args.get("w")
    h_raw = request.args.get("h")

    # 解析 w、h
    w_val, h_val = None, None
    if w_raw is not None or h_raw is not None:
        w_val, err = parse_int(w_raw or "0", "w")
        h_val, err = parse_int(h_raw or "0", "h")
        if err or (w_val is not None and w_val <= 0) or (h_val is not None and h_val <= 0):
            return jsonify({"error": "w 和 h 必须为正整数"}), 400

    try:
        path, mimetype = media_serve_mgr.get_pic_view_path(filepath, w_val, h_val)
        return send_file(path, mimetype=mimetype, as_attachment=False)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except FileNotFoundError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        log.error("[Pic] 查看失败: %s", e)
        return jsonify({"error": f"图片处理失败: {e}"}), 500
