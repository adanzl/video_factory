"""API 层通用工具：请求解析、响应封装。"""

from __future__ import annotations

from typing import Any

from flask import jsonify, request

from app.api.errors import APIError

JsonDict = dict[str, Any]


def get_json_body(*, required: bool = True) -> JsonDict:
    """安全获取 JSON body。"""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        if required:
            raise APIError("request body must be JSON object")
        return {}
    return data


def parse_query_int(
    name: str,
    default: int,
    *,
    minimum: int = 0,
    maximum: int | None = None,
) -> int:
    """从 query string 解析整数。"""
    raw = request.args.get(name, default)
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise APIError(f"invalid {name}") from exc
    if value < minimum:
        raise APIError(f"{name} must be >= {minimum}")
    if maximum is not None and value > maximum:
        raise APIError(f"{name} must be <= {maximum}")
    return value


def parse_id(data: JsonDict | None = None, *, field: str = "id") -> int:
    """从 JSON body 或 query string 解析正整数 ID。"""
    if data is not None and field in data:
        raw = data[field]
    else:
        raw = request.args.get(field)
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise APIError(f"{field} is required") from exc
    if value <= 0:
        raise APIError(f"{field} must be positive")
    return value


def parse_str(data: JsonDict, field: str, *, required: bool = True) -> str | None:
    """解析非空字符串字段。"""
    value = data.get(field)
    if value is None:
        if required:
            raise APIError(f"{field} is required")
        return None
    if not isinstance(value, str) or not value.strip():
        raise APIError(f"{field} is required")
    return value.strip()


def parse_bool(data: JsonDict, field: str, *, default: bool = False) -> bool:
    """解析布尔字段。"""
    if field not in data:
        return default
    value = data[field]
    if not isinstance(value, bool):
        raise APIError(f"{field} must be boolean")
    return value


def parse_optional_float(
    data: JsonDict,
    field: str,
    *,
    minimum: float = 0.0,
    maximum: float = 5.0,
) -> float | None:
    """解析可选浮点字段；缺失时返回 None。"""
    if field not in data:
        return None
    raw = data[field]
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise APIError(f"{field} must be a number") from exc
    if value < minimum:
        raise APIError(f"{field} must be >= {minimum}")
    if value > maximum:
        raise APIError(f"{field} must be <= {maximum}")
    return value


def parse_int_list(
    data: JsonDict,
    field: str,
    *,
    allow_empty: bool = False,
) -> list[int] | None:
    """解析整数列表；字段缺失时返回 None。"""
    if field not in data:
        return None
    raw = data[field]
    if not isinstance(raw, list) or not all(isinstance(item, int) for item in raw):
        raise APIError(f"{field} must be a list of integers")
    if not raw and not allow_empty:
        raise APIError(f"{field} 不能为空")
    return list(raw)


def get_query(name: str, *, default: str | None = None) -> str | None:
    """读取 query string 字符串参数。"""
    value = request.args.get(name)
    if value is None or value == "":
        return default
    return value


def json_ok(data: Any = None, *, status: int = 200):
    """返回 JSON 成功响应。"""
    return jsonify(data), status


def json_created(data: Any):
    """返回 201 Created。"""
    return json_ok(data, status=201)


def json_accepted(data: Any):
    """返回 202 Accepted（异步任务已接受）。"""
    return json_ok(data, status=202)
