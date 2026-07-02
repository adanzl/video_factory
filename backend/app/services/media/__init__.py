"""媒体合成包。对外请使用 media_mgr；分镜 clip 见 segment.clip。"""

from app.services.media.media_mgr import MediaMgr, media_mgr

__all__ = ["MediaMgr", "media_mgr"]
