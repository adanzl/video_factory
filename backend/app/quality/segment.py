"""segment 阶段：分镜出图与 clip 质检。"""

from __future__ import annotations

from app.quality.models import QualityReport

__all__ = ["check_segment_clips", "check_segment_images"]


def check_segment_images(segments: list[dict]) -> QualityReport:
    """分镜静图是否齐全。"""
    missing = [seg["id"] for seg in segments if not seg.get("image_path")]
    if missing:
        return QualityReport(
            level="minor",
            step="visual",
            bad_segment_ids=missing,
            details={"reason": "missing images"},
        )
    return QualityReport(level="pass", step="visual")


def check_segment_clips(segments: list[dict]) -> QualityReport:
    """分镜 clip 是否齐全。"""
    missing = [seg["id"] for seg in segments if not seg.get("clip_path")]
    if missing:
        return QualityReport(
            level="major",
            step="clip",
            fail_stage="segment",
            bad_segment_ids=missing,
            details={"reason": "missing clips"},
        )
    return QualityReport(level="pass", step="clip", details={"clip_count": len(segments)})
