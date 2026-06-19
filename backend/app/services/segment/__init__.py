"""分镜生产：ImageProvider / ClipProvider 等子流程，不由 pipeline 单独暴露。"""

from app.services.segment.segment_mgr import SegmentMgr, SegmentProduceResult, segment_mgr

__all__ = ["SegmentMgr", "SegmentProduceResult", "segment_mgr"]
