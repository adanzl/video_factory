"""素材片段搜索：统一结果模型。"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class StockClip:
    """聚合后的可预览视频片段（不入库）。"""

    id: str
    provider: str
    title: str
    preview_url: str
    video_url: str
    page_url: str
    license: str
    duration_sec: float | None = None
    width: int | None = None
    height: int | None = None
    author: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ProviderSearchResult:
    provider: str
    status: str  # ok | skipped | error
    count: int = 0
    reason: str | None = None
    clips: tuple[StockClip, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "status": self.status,
            "count": self.count,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class ClipSearchResponse:
    query: str
    clips: tuple[StockClip, ...]
    providers: tuple[ProviderSearchResult, ...]
    pixabay_query: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "query": self.query,
            "total": len(self.clips),
            "clips": [clip.to_dict() for clip in self.clips],
            "providers": [row.to_dict() for row in self.providers],
        }
        if self.pixabay_query and self.pixabay_query != self.query:
            payload["pixabay_query"] = self.pixabay_query
        return payload
