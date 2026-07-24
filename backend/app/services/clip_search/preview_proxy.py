"""代理外部素材视频预览，解决浏览器跨域与 MIME 识别问题。"""
from __future__ import annotations
import logging
from urllib.parse import urlparse
import requests
from flask import Response, request
logger = logging.getLogger(__name__)
_ALLOWED_HOST_SUFFIXES = ('videos.pexels.com', 'static-videos.pexels.com', 'images.pexels.com', 'player.vimeo.com', 'cdn.pixabay.com', 'pixabay.com', 'images-assets.nasa.gov')
_SKIP_RESPONSE_HEADERS = frozenset({'connection', 'keep-alive', 'proxy-authenticate', 'proxy-authorization', 'te', 'trailers', 'transfer-encoding', 'upgrade'})

def _host_allowed(hostname: str) -> bool:
    host = hostname.lower().strip('.')
    if not host:
        return False
    return any((host == suffix or host.endswith(f'.{suffix}') for suffix in _ALLOWED_HOST_SUFFIXES))

def validate_preview_url(url: str) -> str:
    cleaned = url.strip()
    if not cleaned:
        raise ValueError('url is required')
    if len(cleaned) > 2048:
        raise ValueError('url too long')
    parsed = urlparse(cleaned)
    if parsed.scheme not in {'http', 'https'}:
        raise ValueError('url must be http or https')
    if not parsed.hostname or not _host_allowed(parsed.hostname):
        raise ValueError('url host not allowed')
    return cleaned

def proxy_clip_preview(url: str):
    """校验后流式转发 CDN 视频，支持 Range 供浏览器播放。"""
    validated = validate_preview_url(url)
    forward_headers: dict[str, str] = {}
    range_header = request.headers.get('Range')
    if range_header:
        forward_headers['Range'] = range_header
    try:
        upstream = requests.get(validated, headers=forward_headers, stream=True, timeout=(10, 120))
    except requests.RequestException as exc:
        logger.warning('clip preview upstream request failed: %s %s', validated, exc)
        raise ValueError(f'upstream request failed: {exc}') from exc
    if upstream.status_code >= 400:
        upstream.close()
        raise ValueError(f'upstream returned {upstream.status_code}')
    headers = [(name, value) for name, value in upstream.headers.items() if name.lower() not in _SKIP_RESPONSE_HEADERS]
    if not any((name.lower() == 'content-type' for name, _ in headers)):
        headers.append(('Content-Type', 'video/mp4'))
    if not any((name.lower() == 'accept-ranges' for name, _ in headers)):
        headers.append(('Accept-Ranges', 'bytes'))
    logger.debug('[CLIP] preview stream -> %s status=%s', validated, upstream.status_code)

    def generate():
        try:
            for chunk in upstream.iter_content(chunk_size=65536):
                if chunk:
                    yield chunk
        finally:
            upstream.close()
    return Response(generate(), status=upstream.status_code, headers=headers)
