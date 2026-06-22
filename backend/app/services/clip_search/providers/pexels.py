"""Pexels 视频搜索。"""

from __future__ import annotations

from app.services.clip_search.models import StockClip
from app.services.clip_search.providers._http import get_json

_PEXELS_SEARCH = "https://api.pexels.com/videos/search"


def _is_browser_mp4(file: dict) -> bool:
    link = str(file.get("link") or "")
    file_type = str(file.get("file_type") or "").lower()
    quality = str(file.get("quality") or "").lower()
    if not link:
        return False
    if quality == "hls" or ".m3u8" in link.lower():
        return False
    if file_type and "mp4" not in file_type:
        return False
    return True


def _pick_video_file(files: list[dict]) -> dict | None:
    candidates = [f for f in files if isinstance(f, dict) and _is_browser_mp4(f)]
    if not candidates:
        return None
    # sd/hd 比 uhd 更易在浏览器中解码；同档优先较高分辨率
    quality_rank = {"sd": 3, "hd": 2, "uhd": 1}
    candidates.sort(
        key=lambda f: (
            quality_rank.get(str(f.get("quality", "")).lower(), 0),
            int(f.get("width") or 0),
        ),
        reverse=True,
    )
    return candidates[0]


def _pexels_title(item: dict, video_id: object) -> str:
    url = str(item.get("url") or "").rstrip("/")
    if url:
        slug = url.rsplit("/", 1)[-1]
        # 如 discover-authentic-chinese-street-culture-36382074 → 可读标题
        if slug and not slug.isdigit():
            parts = slug.rsplit("-", 1)
            text = parts[0] if len(parts) == 2 and parts[1].isdigit() else slug
            return text.replace("-", " ").strip() or f"Pexels #{video_id}"
    return f"Pexels #{video_id}"


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
                title=_pexels_title(item, video_id),
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
