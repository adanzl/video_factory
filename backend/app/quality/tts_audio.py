"""tts 阶段：配音音频质检。"""

from __future__ import annotations

from pathlib import Path

from app.config import get_settings
from app.quality.models import QualityReport
from app.services.media.audio_analysis import LoudnessStats, SilenceStats, analyze_loudness, analyze_silence
from app.services.tts.tts_mgr import SubtitleCue

__all__ = ["check_tts_audio"]


def _cue_totals(cues: list[SubtitleCue]) -> dict[int, float]:
    totals: dict[int, float] = {}
    for cue in cues:
        totals[cue.segment_index] = totals.get(cue.segment_index, 0.0) + cue.duration_sec
    return totals


def check_tts_audio(
    audio_path: Path | None,
    duration_sec: float,
    *,
    subtitle_cues: list[SubtitleCue] | None = None,
    segments: list[dict] | None = None,
    loudness: LoudnessStats | None = None,
    silence: SilenceStats | None = None,
    min_duration_sec: float | None = None,
) -> QualityReport:
    """文件、总时长、静音、响度、字幕时间轴对齐。"""
    settings = get_settings()
    if audio_path is None or not audio_path.exists():
        return QualityReport(
            level="major",
            step="tts",
            fail_stage="tts",
            details={"reason": "missing audio"},
        )

    min_duration = 30.0 if min_duration_sec is None else min_duration_sec
    if duration_sec < min_duration:
        return QualityReport(
            level="major",
            step="tts",
            fail_stage="tts",
            details={
                "reason": "audio too short",
                "duration_sec": duration_sec,
                "min_duration_sec": min_duration,
            },
        )

    if loudness is None:
        loudness = analyze_loudness(audio_path)
    if silence is None:
        silence = analyze_silence(
            audio_path,
            noise_db=settings.audio_silence_noise_db,
        )

    details: dict = {
        "duration_sec": duration_sec,
        "integrated_lufs": loudness.integrated_lufs,
        "true_peak_dbtp": loudness.true_peak_dbtp,
        "max_silence_gap_sec": silence.max_gap_sec,
    }

    if silence.max_gap_sec > settings.audio_max_silence_gap_sec:
        return QualityReport(
            level="major",
            step="tts",
            fail_stage="tts",
            details={
                **details,
                "reason": "silence gap too long",
                "limit_sec": settings.audio_max_silence_gap_sec,
            },
        )

    edge_silence = max(silence.leading_silence_sec, silence.trailing_silence_sec)
    if edge_silence > settings.audio_max_edge_silence_sec:
        return QualityReport(
            level="minor",
            step="tts",
            details={
                **details,
                "reason": "leading/trailing silence too long",
                "edge_silence_sec": edge_silence,
                "limit_sec": settings.audio_max_edge_silence_sec,
            },
        )

    if loudness.integrated_lufs is not None:
        delta = abs(loudness.integrated_lufs - settings.audio_target_lufs)
        if delta > settings.audio_loudness_tolerance_lu:
            return QualityReport(
                level="minor",
                step="tts",
                details={
                    **details,
                    "reason": "loudness off target after normalize",
                    "target_lufs": settings.audio_target_lufs,
                    "delta_lu": delta,
                },
            )

    if subtitle_cues and segments:
        cue_by_index = _cue_totals(subtitle_cues)
        bad_ids: list[int] = []
        for seg in segments:
            index = seg["segment_index"]
            expected = cue_by_index.get(index, 0.0)
            actual = float(seg.get("duration_sec") or 0.0)
            if abs(expected - actual) > settings.tts_cue_duration_tolerance_sec:
                bad_ids.append(seg["id"])
        if bad_ids:
            return QualityReport(
                level="minor",
                step="tts",
                bad_segment_ids=bad_ids,
                details={
                    **details,
                    "reason": "subtitle cue duration mismatch",
                    "tolerance_sec": settings.tts_cue_duration_tolerance_sec,
                },
            )

    return QualityReport(level="pass", step="tts", details=details)
