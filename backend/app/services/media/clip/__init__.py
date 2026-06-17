"""分镜 clip 合成：对外请使用 clip.mgr。"""

from app.services.media.clip.mgr import ClipProvider, build_segment_clip, get_clip_provider

__all__ = ["ClipProvider", "build_segment_clip", "get_clip_provider"]
