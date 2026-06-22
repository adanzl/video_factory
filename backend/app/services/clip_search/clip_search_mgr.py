"""视频片段搜索门面。"""

from __future__ import annotations

from app.services.clip_search.aggregator import list_provider_status, search_clips

__all__ = ["clip_search_mgr", "list_provider_status", "search_clips"]


class ClipSearchMgr:
    list_providers = staticmethod(list_provider_status)
    search = staticmethod(search_clips)


clip_search_mgr = ClipSearchMgr()
