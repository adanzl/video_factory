"""音频分析：静音检测、响度测量与 loudnorm 归一。"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from app.services.media.ffmpeg_utils import (
    loudnorm_measure_log,
    loudnorm_replace,
    probe_duration,
    silence_detect_log,
)

__all__ = [
    "LoudnessStats",
    "SilenceStats",
    "analyze_loudness",
    "analyze_silence",
    "normalize_loudness",
]


@dataclass(frozen=True)
class SilenceStats:
    gaps: tuple[tuple[float, float], ...]  # (start_sec, duration_sec)
    max_gap_sec: float
    total_silence_sec: float
    leading_silence_sec: float
    trailing_silence_sec: float


@dataclass(frozen=True)
class LoudnessStats:
    integrated_lufs: float | None
    true_peak_dbtp: float | None


def analyze_silence(
    path: Path,
    *,
    noise_db: float = -40.0,
    min_duration_sec: float = 0.35,
) -> SilenceStats:
    output = silence_detect_log(path, noise_db=noise_db, min_duration_sec=min_duration_sec)
    starts = [float(v) for v in re.findall(r"silence_start:\s*([0-9.]+)", output)]
    durations = [float(v) for v in re.findall(r"silence_duration:\s*([0-9.]+)", output)]
    gaps = tuple((start, dur) for start, dur in zip(starts, durations, strict=False))
    total = sum(durations)
    max_gap = max(durations) if durations else 0.0
    file_duration = _probe_duration_safe(path)
    leading = durations[0] if starts and starts[0] <= 0.05 else 0.0
    trailing = 0.0
    if starts and durations and file_duration > 0:
        end = starts[-1] + durations[-1]
        if file_duration - end <= 0.15:
            trailing = durations[-1]
    return SilenceStats(
        gaps=gaps,
        max_gap_sec=max_gap,
        total_silence_sec=total,
        leading_silence_sec=leading,
        trailing_silence_sec=trailing,
    )


def analyze_loudness(path: Path) -> LoudnessStats:
    output = loudnorm_measure_log(path)
    integrated = _parse_float(r"Input Integrated:\s*(-?[0-9.]+)\s*LUFS", output)
    true_peak = _parse_float(r"Input True Peak:\s*(-?[0-9.]+)\s*dBTP", output)
    if integrated is None:
        integrated = _parse_float(r"mean_volume:\s*(-?[0-9.]+)\s*dB", output)
    return LoudnessStats(integrated_lufs=integrated, true_peak_dbtp=true_peak)


def normalize_loudness(
    path: Path,
    *,
    target_lufs: float = -16.0,
    true_peak: float = -1.5,
) -> Path:
    return loudnorm_replace(path, target_lufs=target_lufs, true_peak=true_peak)


def _probe_duration_safe(path: Path) -> float:
    try:
        return probe_duration(path)
    except (subprocess.CalledProcessError, ValueError, OSError):
        return 0.0


def _parse_float(pattern: str, text: str) -> float | None:
    match = re.search(pattern, text)
    if not match:
        return None
    return float(match.group(1))
