"""代理外部素材视频预览，解决浏览器跨域与编码兼容问题。"""

from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

from flask import redirect

logger = logging.getLogger(__name__)

_ALLOWED_HOST_SUFFIXES = (
    "videos.pexels.com",
    "static-videos.pexels.com",
    "images.pexels.com",
    "player.vimeo.com",
    "cdn.pixabay.com",
    "pixabay.com",
    "images-assets.nasa.gov",
)


def _host_allowed(hostname: str) -> bool:
    host = hostname.lower().strip(".")
    if not host:
        return False
    return any(host == suffix or host.endswith(f".{suffix}") for suffix in _ALLOWED_HOST_SUFFIXES)


def validate_preview_url(url: str) -> str:
    cleaned = url.strip()
    if not cleaned:
        raise ValueError("url is required")
    if len(cleaned) > 2048:
        raise ValueError("url too long")
    parsed = urlparse(cleaned)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("url must be http or https")
    if not parsed.hostname or not _host_allowed(parsed.hostname):
        raise ValueError("url host not allowed")
    return cleaned


def proxy_clip_preview(url: str):
    """校验后 302 到 CDN，由浏览器直连拉流（支持 Range，避免 gevent 代理大文件）。"""
    validated = validate_preview_url(url)
    logger.debug("[CLIP] preview redirect -> %s", validated)
    return redirect(validated, code=302)
