"""分镜 clip 合成：对外请使用 clip_mgr。"""

from app.services.media.clip.mgr import ClipMgr, ClipProvider, clip_mgr

__all__ = ["ClipMgr", "ClipProvider", "clip_mgr"]
