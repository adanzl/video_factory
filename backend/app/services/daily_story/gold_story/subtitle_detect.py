"""烧录字幕区域检测（轻量采样）。"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import numpy as np

from app.config import Config


def _ffmpeg() -> str:
    path = shutil.which("ffmpeg")
    if not path:
        raise RuntimeError("ffmpeg is required but was not found on PATH")
    return path


def extract_sample_frame(
    video_path: Path,
    *,
    output_path: Path,
    timestamp_sec: float,
    crop_bottom_ratio: float = 0.20,
) -> Path:
    """抽取单帧并裁剪底部字幕带。"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    crop_y = 1.0 - crop_bottom_ratio
    vf = f"crop=iw:ih*{crop_bottom_ratio}:0:ih*{crop_y}"
    cmd = [
        _ffmpeg(),
        "-y",
        "-ss",
        f"{max(timestamp_sec, 0.0):.3f}",
        "-i",
        str(video_path),
        "-frames:v",
        "1",
        "-vf",
        vf,
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, encoding="utf-8")
    if result.returncode != 0:
        stderr = (result.stderr or "").strip() or "unknown ffmpeg error"
        raise RuntimeError(f"ffmpeg sample frame failed: {stderr}")
    return output_path


def roi_has_text_band(image_path: Path, *, min_edge_ratio: float = 0.015) -> bool:
    """底部 ROI 是否存在稳定高对比文字带（不跑 OCR）。"""
    try:
        import cv2
    except ImportError as exc:
        raise RuntimeError("opencv-python is required for subtitle detection") from exc

    img = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
    if img is None:
        return False
    blurred = cv2.GaussianBlur(img, (3, 3), 0)
    edges = cv2.Canny(blurred, 80, 180)
    edge_ratio = float(np.count_nonzero(edges)) / float(edges.size)
    std = float(np.std(blurred))
    return edge_ratio >= min_edge_ratio and std >= 18.0


def detect_burned_subtitles(
    video_path: Path,
    *,
    workspace: Path,
    duration_sec: float | None = None,
    sample_points: tuple[float, ...] = (0.2, 0.5, 0.8),
    hits_required: int = 2,
    config: Config | None = None,
) -> bool:
    """连续多帧底部有文字带 → 判定为烧录字幕。"""
    _ = config
    if duration_sec is None or duration_sec <= 0:
        duration_sec = _probe_duration(video_path)
    if duration_sec <= 0:
        return False

    hits = 0
    frame_dir = workspace / "detect"
    frame_dir.mkdir(parents=True, exist_ok=True)
    for idx, ratio in enumerate(sample_points):
        ts = max(duration_sec * ratio, 0.0)
        frame_path = frame_dir / f"sample_{idx:02d}.jpg"
        try:
            extract_sample_frame(
                video_path,
                output_path=frame_path,
                timestamp_sec=ts,
            )
            if roi_has_text_band(frame_path):
                hits += 1
        except Exception:
            continue
    return hits >= hits_required


def _probe_duration(video_path: Path) -> float:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return 0.0
    cmd = [
        ffprobe,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(video_path),
    ]
    result = subprocess.run(cmd, capture_output=True, encoding="utf-8")
    if result.returncode != 0:
        return 0.0
    try:
        return float((result.stdout or "").strip())
    except ValueError:
        return 0.0
