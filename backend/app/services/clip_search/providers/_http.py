"""片段搜索 HTTP 工具。"""

from __future__ import annotations

import logging

import requests

logger = logging.getLogger(__name__)


def get_json(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    params: dict[str, str | int] | None = None,
    timeout: float,
) -> dict:
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as exc:
        logger.warning("clip search request failed: %s %s", url, exc)
        raise
    if not isinstance(data, dict):
        raise ValueError("invalid JSON response")
    return data
