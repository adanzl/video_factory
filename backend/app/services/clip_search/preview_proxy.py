"""代理外部素材视频预览，解决浏览器跨域与编码兼容问题。"""

from __future__ import annotations

import logging
from urllib.parse import urlparse

import requests
from flask import Response, request, stream_with_context

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

_FORWARD_HEADERS = frozenset(
    {
        "range",
        "if-range",
        "if-modified-since",
        "if-none-match",
    }
)

_EXCLUDE_RESPONSE_HEADERS = frozenset(
    {
        "content-encoding",
        "transfer-encoding",
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailers",
        "upgrade",
    }
)

_PREVIEW_TIMEOUT_SEC = 60.0
_PREVIEW_USER_AGENT = "VideoFactory/1.0 (+clip-preview)"


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


def proxy_clip_preview(url: str) -> Response:
    validated = validate_preview_url(url)
    forward: dict[str, str] = {"User-Agent": _PREVIEW_USER_AGENT}
    for name in _FORWARD_HEADERS:
        value = request.headers.get(name)
        if value:
            forward[name] = value

    try:
        upstream = requests.get(
            validated,
            headers=forward,
            stream=True,
            timeout=_PREVIEW_TIMEOUT_SEC,
            allow_redirects=True,
        )
    except requests.RequestException as exc:
        logger.warning("clip preview proxy failed: %s %s", validated, exc)
        raise ValueError(f"cannot fetch preview: {exc}") from exc

    if upstream.status_code >= 400:
        upstream.close()
        raise ValueError(f"upstream returned {upstream.status_code}")

    response_headers = {
        name: value
        for name, value in upstream.headers.items()
        if name.lower() not in _EXCLUDE_RESPONSE_HEADERS
    }
    if "Content-Type" not in response_headers:
        response_headers["Content-Type"] = "video/mp4"

    return Response(
        stream_with_context(upstream.iter_content(chunk_size=65536)),
        status=upstream.status_code,
        headers=response_headers,
    )
