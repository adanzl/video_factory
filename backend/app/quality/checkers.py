"""各生产步骤的质检规则。"""

from __future__ import annotations

import re
from pathlib import Path

from app.config import get_settings
from app.quality.models import QualityReport
from app.services.media.audio_analysis import LoudnessStats, SilenceStats, analyze_loudness, analyze_silence
from app.services.media.ffmpeg_utils import probe_duration
from app.services.tts.tts_mgr import SubtitleCue

__all__ = [
    "check_copy",
    "check_final",
    "check_segment_clips",
    "check_storyboard",
    "check_tts_audio",
    "check_visual",
]


def _narration_chars(narration: str) -> int:
    return len(re.sub(r"\s+", "", narration))


def check_copy(script: dict) -> QualityReport:
    """文案：口播稿长度、违禁表述。"""
    narration = script.get("narration", "")
    word_count = _narration_chars(narration)
    if word_count < 200:
        return QualityReport(
            level="major",
            step="copy",
            fail_stage="script",
            details={"reason": "narration too short", "word_count": word_count},
        )
    banned = ["包治百病", "稳赚不赔"]
    for word in banned:
        if word in narration:
            return QualityReport(
                level="major",
                step="copy",
                fail_stage="script",
                details={"reason": f"banned phrase: {word}"},
            )
    return QualityReport(level="pass", step="copy", details={"word_count": word_count})


def check_storyboard(script: dict) -> QualityReport:
    """剧本：标题、分镜数量与字段完整性。"""
    settings = get_settings()
    title = re.sub(r"\s+", "", (script.get("title") or "").strip())
    if not title:
        return QualityReport(
            level="major",
            step="storyboard",
            fail_stage="script",
            details={"reason": "title is empty"},
        )
    if len(title) > settings.max_title_length:
        return QualityReport(
            level="major",
            step="storyboard",
            fail_stage="script",
            details={
                "reason": "title too long",
                "title_length": len(title),
                "max_length": settings.max_title_length,
            },
        )

    segments = script.get("segments") or []
    if settings.segment_target_sec > 0:
        narration_chars = _narration_chars(script.get("narration", ""))
        cap = max(20, int(settings.segment_target_sec * 7.5))
        needed = max(1, (narration_chars + cap - 1) // cap)
        if len(segments) < needed:
            return QualityReport(
                level="major",
                step="storyboard",
                fail_stage="script",
                details={
                    "reason": "too few segments",
                    "segment_count": len(segments),
                    "min_expected": needed,
                    "segment_target_sec": settings.segment_target_sec,
                },
            )
        hard_cap = int(cap * 1.15)
        long_segments: list[dict] = []
        for seg in segments:
            seg_chars = _narration_chars(seg.get("text") or "")
            if seg_chars > hard_cap:
                long_segments.append(
                    {
                        "segment_index": seg.get("segment_index"),
                        "chars": seg_chars,
                        "max_chars": cap,
                    }
                )
        if long_segments:
            return QualityReport(
                level="major",
                step="storyboard",
                fail_stage="script",
                details={
                    "reason": "segment text too long",
                    "segments": long_segments,
                    "segment_target_sec": settings.segment_target_sec,
                },
            )

    bad: list[int] = []
    for idx, seg in enumerate(segments):
        if not (seg.get("text") or "").strip():
            bad.append(idx)
    if bad:
        return QualityReport(
            level="major",
            step="storyboard",
            fail_stage="script",
            details={"reason": "empty segment text", "bad_segment_indexes": bad},
        )
    return QualityReport(
        level="pass",
        step="storyboard",
        details={"segment_count": len(segments), "title_length": len(title)},
    )


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
) -> QualityReport:
    """配音：文件、总时长、静音、响度、字幕时间轴对齐。"""
    settings = get_settings()
    if audio_path is None or not audio_path.exists():
        return QualityReport(
            level="major",
            step="tts",
            fail_stage="tts",
            details={"reason": "missing audio"},
        )

    min_duration = 30.0
    if duration_sec < min_duration:
        return QualityReport(
            level="major",
            step="tts",
            fail_stage="tts",
            details={"reason": "audio too short", "duration_sec": duration_sec},
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


def check_visual(segments: list[dict]) -> QualityReport:
    """画面：分镜静图是否齐全。"""
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
    """分镜片段：clip 是否齐全。"""
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


def check_final(
    final_path: Path | None,
    *,
    loudness: LoudnessStats | None = None,
) -> QualityReport:
    """成片：文件、时长带、合成后响度。"""
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

    if duration < settings.final_min_duration_sec:
        return QualityReport(
            level="major",
            step="final",
            fail_stage="merge",
            details={
                **details,
                "reason": "final too short",
                "min_duration_sec": settings.final_min_duration_sec,
            },
        )
    if duration > settings.final_max_duration_sec:
        return QualityReport(
            level="major",
            step="final",
            fail_stage="merge",
            details={
                **details,
                "reason": "final too long",
                "max_duration_sec": settings.final_max_duration_sec,
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
