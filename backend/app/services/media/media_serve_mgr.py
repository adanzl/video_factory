"""媒体文件 HTTP 服务：时长查询、文件下发、图片缩放查看。"""

from __future__ import annotations

import hashlib
import logging
import os
import time
from pathlib import Path
from typing import Any

from PIL import Image

from app.config import get_settings
from app.services.media.ffmpeg_utils import probe_duration
from app.utils.async_util import run_in_background
from app.utils.media_path import allowed_media_roots, normalize_media_path, resolve_media_serve_path

logger = logging.getLogger(__name__)

MIMETYPE_MAP = {
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".aac": "audio/aac",
    ".ogg": "audio/ogg",
    ".m4a": "audio/mp4",
    ".mp4": "video/mp4",
    ".avi": "video/x-msvideo",  # cSpell: disable-line
    ".mkv": "video/x-matroska",  # cSpell: disable-line
    ".mov": "video/quicktime",  # cSpell: disable-line
    ".webm": "video/webm",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".vtt": "text/vtt",
    ".srt": "application/x-subrip",  # cSpell: disable-line
}


_PIC_CACHE_TTL_SEC = 3 * 24 * 3600  # 3 天
_PIC_CACHE_CLEAN_INTERVAL_SEC = 3600  # 每小时扫一次


def _pic_cache_cleaner(cache_dir: Path) -> None:
    """后台 greenlet：定期清理过期缓存文件。"""
    import gevent

    while True:
        gevent.sleep(_PIC_CACHE_CLEAN_INTERVAL_SEC)
        if not cache_dir.is_dir():
            continue
        now = time.time()
        removed = 0
        for entry in os.scandir(str(cache_dir)):
            if entry.is_file():
                try:
                    age = now - entry.stat().st_atime
                    if age > _PIC_CACHE_TTL_SEC:
                        os.unlink(entry.path)
                        removed += 1
                except OSError:
                    pass
        if removed:
            logger.info("[Pic] 缓存清理: 删除了 %d 个过期文件", removed)


class MediaServeMgr:
    """媒体文件访问业务逻辑。"""

    def __init__(self) -> None:
        self.allowed_roots = allowed_media_roots()
        self._start_cache_cleaner()

    def _start_cache_cleaner(self) -> None:
        try:
            cache_dir = get_settings().root_dir / "data" / "pic_cache"
            run_in_background(lambda: _pic_cache_cleaner(cache_dir))
        except Exception:
            logger.warning("[Pic] 启动缓存清理失败", exc_info=True)

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
        return {"path": path, "mimetype": mimetype}

    def get_pic_view_path(self, filepath: str, w_val: int | None, h_val: int | None) -> tuple[str, str]:
        """
        图片查看入口。
        如果未指定 w/h 则返回原图，否则按指定尺寸缩放后返回缓存路径。
        """
        path = resolve_media_serve_path(filepath, allowed_roots=self.allowed_roots)
        ext = os.path.splitext(path)[1].lower()
        mimetype = MIMETYPE_MAP.get(ext, "application/octet-stream")

        if w_val is None and h_val is None:
            return path, mimetype

        settings = get_settings()
        cache_dir = settings.root_dir / "data" / "pic_cache"
        cache_dir.mkdir(parents=True, exist_ok=True)

        # 缓存 key：原路径 + 尺寸 + 源文件 mtime（源文件更新时自动重建缓存）
        src_stat = os.stat(path)
        src_mtime = int(src_stat.st_mtime)
        key_str = f"{path}__{w_val or ''}x{h_val or ''}__{src_mtime}"
        key = hashlib.md5(key_str.encode()).hexdigest()
        cache_path = cache_dir / f"{key}{ext}"

        if cache_path.exists():
            try:
                os.utime(str(cache_path), None)
            except OSError:
                pass
            logger.debug("[Pic] 缓存命中: %s", cache_path)
            return str(cache_path), mimetype

        # PIL 缩放
        img = Image.open(path)
        ow, oh = img.size
        if w_val and h_val:
            new_w, new_h = w_val, h_val
        elif w_val:
            new_w = w_val
            new_h = max(1, round(oh * w_val / ow))
        else:
            new_h = h_val
            new_w = max(1, round(ow * h_val / oh))

        resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        resized.save(cache_path)
        logger.info("[Pic] 缩放 %s → %s (%dx%d)", path, cache_path, new_w, new_h)
        return str(cache_path), mimetype


media_serve_mgr = MediaServeMgr()

__all__ = ["MIMETYPE_MAP", "MediaServeMgr", "media_serve_mgr"]
