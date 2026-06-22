"""NASA Image and Video Library 搜索（无需 API Key）。"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from app.services.clip_search.models import StockClip
from app.services.clip_search.providers._http import get_json

logger = logging.getLogger(__name__)

_NASA_SEARCH = "https://images-api.nasa.gov/search"
_NASA_ASSET = "https://images-api.nasa.gov/asset/{nasa_id}"


def _pick_mp4_url(asset_items: list) -> str | None:
    candidates: list[tuple[int, str]] = []
    for row in asset_items:
        if not isinstance(row, str):
            continue
        lower = row.lower()
        if not lower.endswith(".mp4"):
            continue
        if "~orig" in lower or "~large" in lower:
            candidates.append((3, row))
        elif "~medium" in lower:
            candidates.append((2, row))
        else:
            candidates.append((1, row))
    if not candidates:
        return None
    candidates.sort(key=lambda pair: pair[0], reverse=True)
    return candidates[0][1]


def _resolve_nasa_video(nasa_id: str, *, timeout: float) -> str | None:
    try:
        items = get_json(_NASA_ASSET.format(nasa_id=nasa_id), timeout=timeout)
    except Exception:
        return None
    if not isinstance(items, list):
        return None
    return _pick_mp4_url(items)


def search_nasa(
    query: str,
    *,
    per_page: int,
    timeout: float,
) -> list[StockClip]:
    data = get_json(
        _NASA_SEARCH,
        params={"q": query, "media_type": "video"},
        timeout=timeout,
    )
    collection = data.get("collection") if isinstance(data.get("collection"), dict) else {}
    items = collection.get("items") if isinstance(collection.get("items"), list) else []

    candidates: list[tuple[str, str, str | None]] = []
    for item in items[: per_page * 2]:
        if not isinstance(item, dict):
            continue
        meta_list = item.get("data")
        if not isinstance(meta_list, list) or not meta_list:
            continue
        meta = meta_list[0]
        if not isinstance(meta, dict):
            continue
        nasa_id = meta.get("nasa_id")
        if not nasa_id:
            continue
        title = str(meta.get("title") or nasa_id).strip()
        thumb = None
        links = item.get("links")
        if isinstance(links, list) and links:
            link0 = links[0]
            if isinstance(link0, dict) and link0.get("href"):
                thumb = str(link0["href"])
        candidates.append((str(nasa_id), title, thumb))
        if len(candidates) >= per_page:
            break

    clips: list[StockClip] = []
    if not candidates:
        return clips

    resolved: dict[str, str | None] = {}
    worker_timeout = max(4.0, timeout / 2)
    with ThreadPoolExecutor(max_workers=min(6, len(candidates))) as pool:
        futures = {
            pool.submit(_resolve_nasa_video, nasa_id, timeout=worker_timeout): nasa_id
            for nasa_id, _, _ in candidates
        }
        for future in as_completed(futures):
            nasa_id = futures[future]
            try:
                resolved[nasa_id] = future.result()
            except Exception as exc:
                logger.warning("nasa asset resolve failed %s: %s", nasa_id, exc)
                resolved[nasa_id] = None

    for nasa_id, title, thumb in candidates:
        video_url = resolved.get(nasa_id)
        if not video_url:
            continue
        clips.append(
            StockClip(
                id=f"nasa:{nasa_id}",
                provider="nasa",
                title=title,
                preview_url=thumb or video_url,
                video_url=video_url,
                page_url=f"https://images.nasa.gov/details-{nasa_id}",
                license="NASA Media (see usage guidelines)",
                author="NASA",
            )
        )
    return clips
