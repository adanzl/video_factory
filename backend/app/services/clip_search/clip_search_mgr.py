"""视频片段搜索门面。"""

from __future__ import annotations

from app.services.clip_search.aggregator import list_provider_status, search_clips
from app.services.clip_search.import_segment import import_clip_to_segment

__all__ = ["clip_search_mgr", "list_provider_status", "search_clips"]


class ClipSearchMgr:
    list_providers = staticmethod(list_provider_status)
    search = staticmethod(search_clips)
    import_to_segment = staticmethod(import_clip_to_segment)


clip_search_mgr = ClipSearchMgr()
