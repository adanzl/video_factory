"""投稿模块总入口。"""

from __future__ import annotations

from pathlib import Path

__all__ = ["PublishMgr", "publish_mgr"]


class PublishMgr:
    """投稿管理器。"""

    def publish(
        self,
        *,
        title: str,
        video_path: Path,
        cover_path: Path | None,
    ) -> dict:
        return self._publish_bili(
            title=title,
            video_path=video_path,
            cover_path=cover_path,
        )

    def _publish_bili(
        self,
        *,
        title: str,
        video_path: Path,
        cover_path: Path | None,
    ) -> dict:
        """B 站开放平台投稿（待接入）。"""
        return {
            "platform": "bilibili",
            "status": "skipped",
            "message": "publish adapter not configured",
            "title": title,
            "video_path": str(video_path),
            "cover_path": str(cover_path) if cover_path else None,
        }


publish_mgr = PublishMgr()
