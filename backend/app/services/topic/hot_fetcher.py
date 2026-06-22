"""B 站热搜采集（网页端非公开接口，仅供策划参考）。"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from typing import Any

import requests

logger = logging.getLogger(__name__)

_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.bilibili.com/",
}

_SQUARE_URL = "https://api.bilibili.com/x/web-interface/wbi/search/square"
_HOTWORD_URL = "https://s.search.bilibili.com/main/hotword"


@dataclass(frozen=True)
class HotKeyword:
    keyword: str
    show_name: str
    heat_score: int | None
    word_type: int | None
    source: str
    pos: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _parse_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _merge_keywords(items: list[HotKeyword]) -> list[HotKeyword]:
    seen: set[str] = set()
    out: list[HotKeyword] = []
    for item in items:
        key = item.keyword.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def fetch_search_square(*, limit: int = 50, timeout: float = 15.0) -> list[HotKeyword]:
    limit = max(1, min(limit, 50))
    resp = requests.get(
        _SQUARE_URL,
        params={"limit": limit},
        headers=_DEFAULT_HEADERS,
        timeout=timeout,
    )
    resp.raise_for_status()
    payload = resp.json()
    if payload.get("code") != 0:
        raise RuntimeError(f"search/square error: {payload.get('message')}")

    rows = payload.get("data", {}).get("trending", {}).get("list") or []
    out: list[HotKeyword] = []
    for idx, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            continue
        keyword = str(row.get("keyword") or "").strip()
        if not keyword:
            continue
        show_name = str(row.get("show_name") or keyword).strip()
        out.append(
            HotKeyword(
                keyword=keyword,
                show_name=show_name,
                heat_score=_parse_int(row.get("heat_score")),
                word_type=None,
                source="search_square",
                pos=idx,
            )
        )
    logger.info("[HOT] fetch search_square count=%d", len(out))
    return out


def fetch_main_hotword(*, timeout: float = 15.0) -> list[HotKeyword]:
    resp = requests.get(_HOTWORD_URL, headers=_DEFAULT_HEADERS, timeout=timeout)
    resp.raise_for_status()
    payload = resp.json()
    if payload.get("code") != 0:
        raise RuntimeError(f"main/hotword error: {payload.get('exp_str')}")

    rows = payload.get("list") or []
    out: list[HotKeyword] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        keyword = str(row.get("keyword") or "").strip()
        if not keyword:
            continue
        show_name = str(row.get("show_name") or keyword).strip()
        out.append(
            HotKeyword(
                keyword=keyword,
                show_name=show_name,
                heat_score=_parse_int(row.get("heat_score")),
                word_type=_parse_int(row.get("word_type")),
                source="main_hotword",
                pos=_parse_int(row.get("pos")),
            )
        )
    logger.info("[HOT] fetch main_hotword count=%d", len(out))
    return out


def fetch_all_hot_keywords(*, limit: int = 50) -> list[HotKeyword]:
    """合并热搜广场与搜索热词，按 keyword 去重。"""
    square = fetch_search_square(limit=limit)
    hotword = fetch_main_hotword()
    merged = _merge_keywords(square + hotword)
    logger.info(
        "[HOT] fetch merged square=%d hotword=%d unique=%d",
        len(square),
        len(hotword),
        len(merged),
    )
    return merged
