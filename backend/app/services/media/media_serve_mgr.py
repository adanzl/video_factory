"""媒体文件 HTTP 服务：时长查询、文件下发。"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from app.services.media.ffmpeg_utils import probe_duration
from app.utils.media_path import allowed_media_roots, normalize_media_path, resolve_media_serve_path

logger = logging.getLogger(__name__)

MIMETYPE_MAP = {
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".aac": "audio/aac",
    ".ogg": "audio/ogg",
    ".m4a": "audio/mp4",
    ".mp4": "video/mp4",
    ".avi": "video/x-msvideo",
    ".mkv": "video/x-matroska",
    ".mov": "video/quicktime",
    ".webm": "video/webm",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".vtt": "text/vtt",
    ".srt": "application/x-subrip",
}


class MediaServeMgr:
    """媒体文件访问业务逻辑。"""

    def __init__(self) -> None:
        self.allowed_roots = allowed_media_roots()

    def get_duration(self, file_path: str) -> dict[str, Any]:
        path = normalize_media_path(
            file_path,
            allowed_roots=self.allowed_roots,
            must_be_file=True,
        )
        duration = probe_duration(Path(path))
        return {"duration": duration, "path": path}

    def prepare_serve_file(self, filepath: str) -> dict[str, Any]:
        path = resolve_media_serve_path(filepath, allowed_roots=self.allowed_roots)
        ext = os.path.splitext(path)[1].lower()
        mimetype = MIMETYPE_MAP.get(ext, "application/octet-stream")
        logger.info("[MEDIA] Serving file: %s (MIME: %s)", path, mimetype)
        return {"path": path, "mimetype": mimetype}


media_serve_mgr = MediaServeMgr()

__all__ = ["MIMETYPE_MAP", "MediaServeMgr", "media_serve_mgr"]
