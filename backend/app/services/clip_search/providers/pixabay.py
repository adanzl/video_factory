"""Pixabay 视频搜索。"""

from __future__ import annotations

from app.services.clip_search.models import StockClip
from app.services.clip_search.providers._http import get_json

_PIXABAY_SEARCH = "https://pixabay.com/api/videos/"


def _preview_url(item: dict) -> str:
    picture_id = item.get("picture_id")
    if picture_id:
        return f"https://i.vimeocdn.com/video/{picture_id}_640x360.jpg"
    return ""


def _pick_video_variant(videos: dict) -> dict | None:
    for key in ("medium", "small", "large", "tiny"):
        row = videos.get(key)
        if isinstance(row, dict) and row.get("url"):
            return row
    return None


def search_pixabay(
    query: str,
    *,
    api_key: str,
    per_page: int,
    timeout: float,
) -> list[StockClip]:
    data = get_json(
        _PIXABAY_SEARCH,
        params={
            "key": api_key,
            "q": query,
            "per_page": per_page,
            "video_type": "film",
        },
        timeout=timeout,
    )
    clips: list[StockClip] = []
    for item in data.get("hits") or []:
        if not isinstance(item, dict):
            continue
        video_id = item.get("id")
        videos = item.get("videos")
        if video_id is None or not isinstance(videos, dict):
            continue
        picked = _pick_video_variant(videos)
        if not picked:
            continue
        tags = str(item.get("tags") or "").strip()
        title = tags.split(",")[0].strip() if tags else f"Pixabay #{video_id}"
        clips.append(
            StockClip(
                id=f"pixabay:{video_id}",
                provider="pixabay",
                title=title,
                preview_url=_preview_url(item),
                video_url=str(picked["url"]),
                page_url=str(item.get("pageURL") or "https://pixabay.com"),
                license="Pixabay License",
                duration_sec=float(item["duration"]) if item.get("duration") else None,
                width=int(picked["width"]) if picked.get("width") else None,
                height=int(picked["height"]) if picked.get("height") else None,
                author=str(item.get("user")) if item.get("user") else None,
            )
        )
    return clips
