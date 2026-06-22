"""Pexels 视频搜索。"""

from __future__ import annotations

from app.services.clip_search.models import StockClip
from app.services.clip_search.providers._http import get_json

_PEXELS_SEARCH = "https://api.pexels.com/videos/search"


def _pick_video_file(files: list[dict]) -> dict | None:
    if not files:
        return None
    hd = [f for f in files if str(f.get("quality", "")).lower() == "hd"]
    pool = hd or files
    pool = sorted(pool, key=lambda f: int(f.get("width") or 0), reverse=True)
    return pool[0] if pool else None


def search_pexels(
    query: str,
    *,
    api_key: str,
    per_page: int,
    orientation: str | None,
    timeout: float,
) -> list[StockClip]:
    params: dict[str, str | int] = {"query": query, "per_page": per_page}
    if orientation in {"portrait", "landscape", "square"}:
        params["orientation"] = orientation
    data = get_json(
        _PEXELS_SEARCH,
        headers={"Authorization": api_key},
        params=params,
        timeout=timeout,
    )
    clips: list[StockClip] = []
    for item in data.get("videos") or []:
        if not isinstance(item, dict):
            continue
        video_id = item.get("id")
        files = item.get("video_files") or []
        if not isinstance(files, list):
            files = []
        picked = _pick_video_file([f for f in files if isinstance(f, dict)])
        if video_id is None or not picked or not picked.get("link"):
            continue
        user = item.get("user") if isinstance(item.get("user"), dict) else {}
        clips.append(
            StockClip(
                id=f"pexels:{video_id}",
                provider="pexels",
                title=str(item.get("url") or f"Pexels #{video_id}"),
                preview_url=str(item.get("image") or picked["link"]),
                video_url=str(picked["link"]),
                page_url=str(item.get("url") or "https://www.pexels.com"),
                license="Pexels License",
                duration_sec=float(item["duration"]) if item.get("duration") else None,
                width=int(picked["width"]) if picked.get("width") else None,
                height=int(picked["height"]) if picked.get("height") else None,
                author=str(user.get("name")) if user.get("name") else None,
            )
        )
    return clips
