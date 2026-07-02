"""成片视频质检。"""

from __future__ import annotations

from pathlib import Path

from app.config import get_settings
from app.quality.models import QualityReport
from app.services.tts.audio_analysis import LoudnessStats, analyze_loudness
from app.services.media.ffmpeg_utils import probe_duration

__all__ = ["check_merged_video"]


def check_merged_video(
    final_path: Path | None,
    *,
    loudness: LoudnessStats | None = None,
    min_duration_sec: float | None = None,
    max_duration_sec: float | None = None,
) -> QualityReport:
    """文件、时长带、合成后响度。"""
    settings = get_settings()
    if final_path is None or not final_path.exists():
        return QualityReport(
            level="major",
            step="final",
            fail_stage="merge",
            details={"reason": "missing final video"},
        )

    duration = probe_duration(final_path)
    details: dict = {"duration_sec": duration}
    min_dur = settings.final_min_duration_sec if min_duration_sec is None else min_duration_sec
    max_dur = settings.final_max_duration_sec if max_duration_sec is None else max_duration_sec

    if duration < min_dur:
        return QualityReport(
            level="major",
            step="final",
            fail_stage="merge",
            details={
                **details,
                "reason": "final too short",
                "min_duration_sec": min_dur,
            },
        )
    if duration > max_dur:
        return QualityReport(
            level="major",
            step="final",
            fail_stage="merge",
            details={
                **details,
                "reason": "final too long",
                "max_duration_sec": max_dur,
            },
        )

    if loudness is None:
        loudness = analyze_loudness(final_path)
    details["integrated_lufs"] = loudness.integrated_lufs
    details["true_peak_dbtp"] = loudness.true_peak_dbtp

    if loudness.integrated_lufs is not None:
        delta = abs(loudness.integrated_lufs - settings.audio_target_lufs)
        if delta > settings.audio_loudness_tolerance_lu + 1.0:
            return QualityReport(
                level="minor",
                step="final",
                details={
                    **details,
                    "reason": "final loudness off target",
                    "target_lufs": settings.audio_target_lufs,
                    "delta_lu": delta,
                },
            )

    return QualityReport(level="pass", step="final", details=details)
