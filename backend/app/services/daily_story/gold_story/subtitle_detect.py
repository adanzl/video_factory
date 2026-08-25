"""烧录字幕检测与字幕带 ROI 定位。

业务规则：正片对白字幕在全片垂直位置固定；UP 主说明/解说层
出现帧少且 y 位偏高。检测时多样本聚类，取跨帧最稳定的一条带。
"""

from __future__ import annotations

import logging
import shutil
import statistics
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from app.config import Config

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SubtitleRegion:
    """全帧归一化字幕裁切区：y_ratio 为顶边，h_ratio 为带高。"""

    y_ratio: float
    h_ratio: float
    method: str = "edge_band"
    samples: int = 0
    confidence: float = 0.0

    def clamp(self, *, max_h_ratio: float = 0.12) -> SubtitleRegion:
        y = max(0.0, min(float(self.y_ratio), 0.98))
        h = max(0.04, min(float(self.h_ratio), float(max_h_ratio)))
        if y + h > 1.0:
            h = max(0.04, 1.0 - y)
        return SubtitleRegion(
            y_ratio=y,
            h_ratio=h,
            method=self.method,
            samples=self.samples,
            confidence=self.confidence,
        )

    def crop_vf_expr(self, *, max_h_ratio: float = 0.12) -> str:
        region = self.clamp(max_h_ratio=max_h_ratio)
        return f"crop=iw:ih*{region.h_ratio}:0:ih*{region.y_ratio}"


def _ffmpeg() -> str:
    path = shutil.which("ffmpeg")
    if not path:
        raise RuntimeError("ffmpeg is required but was not found on PATH")
    return path


def probe_duration(video_path: Path) -> float:
    return _probe_duration(video_path)


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


def extract_sample_frame(
    video_path: Path,
    *,
    output_path: Path,
    timestamp_sec: float,
    region: SubtitleRegion | None = None,
    crop_bottom_ratio: float = 0.20,
) -> Path:
    """抽取单帧；region 优先，否则回退固定底栏。"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if region is not None:
        vf = region.crop_vf_expr()
    else:
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


def extract_full_sample_frame(
    video_path: Path,
    *,
    output_path: Path,
    timestamp_sec: float,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        _ffmpeg(),
        "-y",
        "-ss",
        f"{max(timestamp_sec, 0.0):.3f}",
        "-i",
        str(video_path),
        "-frames:v",
        "1",
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, encoding="utf-8")
    if result.returncode != 0:
        stderr = (result.stderr or "").strip() or "unknown ffmpeg error"
        raise RuntimeError(f"ffmpeg sample frame failed: {stderr}")
    return output_path


def roi_has_text_band(image_path: Path, *, min_edge_ratio: float = 0.015) -> bool:
    """ROI 是否存在稳定高对比文字带（不跑 OCR）。"""
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


def _bands_from_edge_profile(gray: np.ndarray) -> list[tuple[int, int]]:
    import cv2

    if gray.size == 0:
        return []
    blurred = cv2.GaussianBlur(gray, (3, 3), 0)
    edges = cv2.Canny(blurred, 80, 180)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (11, 3))
    edges = cv2.dilate(edges, kernel, iterations=1)
    profile = np.sum(edges > 0, axis=1).astype(float)
    if profile.size == 0 or float(profile.max()) <= 0:
        return []

    thresh = max(float(profile.max()) * 0.35, 8.0)
    bands: list[tuple[int, int]] = []
    in_band = False
    start = 0
    for idx, value in enumerate(profile):
        if value >= thresh and not in_band:
            in_band = True
            start = idx
        elif value < thresh and in_band:
            in_band = False
            if idx - start >= 3:
                bands.append((start, idx))
    if in_band and len(profile) - start >= 3:
        bands.append((start, len(profile)))
    return bands


def _merge_nearby_bands(
    bands: list[tuple[int, int]],
    *,
    max_gap: int = 8,
    max_height: int | None = None,
) -> list[tuple[int, int]]:
    """合并相邻文字带；超过 max_height（约 2 行字幕）则不并层。"""
    if not bands:
        return []
    ordered = sorted(bands, key=lambda band: band[0])
    merged: list[tuple[int, int]] = []
    cur_start, cur_end = ordered[0]
    for start, end in ordered[1:]:
        gap = start - cur_end
        merged_h = max(cur_end, end) - cur_start
        if gap <= max_gap and (max_height is None or merged_h <= max_height):
            cur_end = max(cur_end, end)
            continue
        merged.append((cur_start, cur_end))
        cur_start, cur_end = start, end
    merged.append((cur_start, cur_end))
    return merged


@dataclass(frozen=True, slots=True)
class _BandObservation:
    """单帧检测到的一条文字带（全帧归一化坐标）。"""

    y_ratio: float
    h_ratio: float

    @property
    def y_center(self) -> float:
        return float(self.y_ratio) + float(self.h_ratio) * 0.5


def _band_to_ratios(
    y0: int,
    y1: int,
    *,
    frame_h: int,
    pad_ratio: float = 0.12,
    max_h_ratio: float = 0.10,
) -> tuple[float, float] | None:
    pad = max(int((y1 - y0) * pad_ratio), max(int(frame_h * 0.004), 2))
    y0 = max(0, y0 - pad)
    y1 = min(frame_h, y1 + pad)
    band_h = y1 - y0
    if band_h <= 0:
        return None
    max_h_px = max(int(frame_h * max_h_ratio), 8)
    if band_h > max_h_px:
        # 说明层/多行解说：裁到字幕最大高度，锚在带底（靠近画面底边）
        y0 = max(0, y1 - max_h_px)
        band_h = y1 - y0
    return y0 / float(frame_h), band_h / float(frame_h)


def _filter_subtitle_observations(
    observations: list[_BandObservation],
    *,
    max_h_ratio: float,
) -> list[_BandObservation]:
    """第一步筛选：丢弃高于「最多 2 行」的Observation（多为说明层）。"""
    limit = float(max_h_ratio) * 1.05
    return [obs for obs in observations if float(obs.h_ratio) <= limit]


def list_subtitle_bands_from_gray(
    gray: np.ndarray,
    *,
    search_bottom_ratio: float = 0.35,
    min_h_ratio: float = 0.02,
    max_h_ratio: float = 0.10,
) -> list[_BandObservation]:
    """在底部搜索区列出文字带；单带高度不超过 max_h_ratio（约 2 行）。"""
    if gray.ndim != 2 or gray.size == 0:
        return []

    frame_h, _frame_w = gray.shape
    search_ratio = max(0.15, min(float(search_bottom_ratio), 0.5))
    search_y = int(frame_h * (1.0 - search_ratio))
    roi = gray[search_y:, :]
    max_h_px = max(int(frame_h * max_h_ratio), 8)
    raw_bands = _merge_nearby_bands(
        _bands_from_edge_profile(roi),
        max_height=max_h_px,
    )
    if not raw_bands:
        return []

    min_h = max(int(frame_h * min_h_ratio), 3)
    max_h = max(int(frame_h * max_h_ratio), min_h + 1)
    out: list[_BandObservation] = []
    for y0_roi, y1_roi in raw_bands:
        band_h_px = y1_roi - y0_roi
        if band_h_px > max_h:
            continue
        if band_h_px < min_h:
            center = (y0_roi + y1_roi) // 2
            half = min_h // 2
            y0_roi = max(0, center - half)
            y1_roi = min(roi.shape[0], center + half)
            band_h_px = y1_roi - y0_roi
        ratios = _band_to_ratios(
            search_y + y0_roi,
            search_y + y1_roi,
            frame_h=frame_h,
            max_h_ratio=max_h_ratio,
        )
        if ratios is None:
            continue
        y_ratio, h_ratio = ratios
        if h_ratio > max_h_ratio * 1.05:
            continue
        out.append(_BandObservation(y_ratio=y_ratio, h_ratio=h_ratio))
    return out


def _cluster_observations(
    observations: list[_BandObservation],
    *,
    y_center_tol: float,
) -> list[list[_BandObservation]]:
    if not observations:
        return []
    tol = max(float(y_center_tol), 0.008)
    ordered = sorted(observations, key=lambda obs: obs.y_center)
    clusters: list[list[_BandObservation]] = []
    for obs in ordered:
        if not clusters or abs(obs.y_center - clusters[-1][0].y_center) > tol:
            clusters.append([obs])
            continue
        clusters[-1].append(obs)
    return clusters


def _select_fixed_dialogue_cluster(
    clusters: list[list[_BandObservation]],
    *,
    sample_frames: int,
    min_hit_ratio: float = 0.2,
    max_h_ratio: float = 0.10,
) -> list[_BandObservation] | None:
    """取跨帧出现最频繁、高度像对白字幕（≤2 行）的文字带。"""
    if not clusters:
        return None
    min_hits = max(2, int(sample_frames * min_hit_ratio))

    def _cluster_median_h(cluster: list[_BandObservation]) -> float:
        return statistics.median([obs.h_ratio for obs in cluster])

    eligible = [
        cluster
        for cluster in clusters
        if len(cluster) >= min_hits and _cluster_median_h(cluster) <= max_h_ratio * 1.05
    ]
    pool = eligible or [
        cluster
        for cluster in clusters
        if _cluster_median_h(cluster) <= max_h_ratio * 1.05
    ]
    if not pool:
        pool = clusters

    def _score(cluster: list[_BandObservation]) -> tuple[int, float]:
        return (len(cluster), statistics.mean([obs.y_center for obs in cluster]))

    return max(pool, key=_score)


def _region_from_cluster(
    cluster: list[_BandObservation],
    *,
    max_h_ratio: float,
    min_h_ratio: float,
) -> SubtitleRegion:
    """聚类 → 固定高度字幕窗（最多 2 行），y 锚定在带底边。"""
    y_bottom = statistics.median([obs.y_ratio + obs.h_ratio for obs in cluster])
    h_ratio = max(float(min_h_ratio), min(float(max_h_ratio), float(max_h_ratio)))
    y_ratio = y_bottom - h_ratio
    y_ratio = max(0.0, min(y_ratio, 1.0 - h_ratio))
    confidence = min(1.0, 0.35 + len(cluster) * 0.08)
    return SubtitleRegion(
        y_ratio=y_ratio,
        h_ratio=h_ratio,
        method="edge_band_fixed",
        samples=len(cluster),
        confidence=confidence,
    ).clamp(max_h_ratio=max_h_ratio)


def fallback_subtitle_region(config: Config | None = None) -> SubtitleRegion:
    cfg = config or Config()
    max_h = float(cfg.gold_story_ocr_region_max_h_ratio)
    y = 1.0 - max_h
    return SubtitleRegion(
        y_ratio=y,
        h_ratio=max_h,
        method="fallback_fixed",
        samples=0,
        confidence=0.25,
    ).clamp(max_h_ratio=max_h)


def detect_subtitle_region(
    video_path: Path,
    *,
    workspace: Path,
    duration_sec: float | None = None,
    config: Config | None = None,
) -> SubtitleRegion:
    """多样本聚类固定对白字幕带；失败时回退固定底栏。"""
    cfg = config or Config()
    if not cfg.gold_story_ocr_region_detect:
        return fallback_subtitle_region(cfg)

    if duration_sec is None or duration_sec <= 0:
        duration_sec = _probe_duration(video_path)
    if duration_sec <= 0:
        return fallback_subtitle_region(cfg)

    sample_points = tuple(
        round(ratio, 3)
        for ratio in (
            0.08,
            0.16,
            0.24,
            0.32,
            0.40,
            0.48,
            0.56,
            0.64,
            0.72,
            0.80,
            0.88,
            0.94,
        )
    )
    frame_dir = workspace / "region_detect"
    frame_dir.mkdir(parents=True, exist_ok=True)

    observations: list[_BandObservation] = []
    sampled_frames = 0
    search_ratio = float(cfg.gold_story_ocr_region_search_ratio)
    cluster_tol = float(cfg.gold_story_ocr_region_cluster_tol)
    max_h_ratio = float(cfg.gold_story_ocr_region_max_h_ratio)
    min_h_ratio = float(cfg.gold_story_ocr_region_min_h_ratio)

    try:
        import cv2
    except ImportError:
        logger.warning("opencv missing, subtitle region fallback")
        return fallback_subtitle_region(cfg)

    for idx, ratio in enumerate(sample_points):
        ts = max(duration_sec * ratio, 0.0)
        frame_path = frame_dir / f"full_{idx:02d}.jpg"
        try:
            extract_full_sample_frame(
                video_path,
                output_path=frame_path,
                timestamp_sec=ts,
            )
            gray = cv2.imread(str(frame_path), cv2.IMREAD_GRAYSCALE)
            if gray is None:
                continue
            sampled_frames += 1
            observations.extend(
                list_subtitle_bands_from_gray(
                    gray,
                    search_bottom_ratio=search_ratio,
                    min_h_ratio=min_h_ratio,
                    max_h_ratio=max_h_ratio,
                )
            )
        except Exception as exc:
            logger.debug("subtitle region sample failed ts=%.2f: %s", ts, exc)

    observations = _filter_subtitle_observations(
        observations,
        max_h_ratio=max_h_ratio,
    )
    clusters = _cluster_observations(observations, y_center_tol=cluster_tol)
    picked = _select_fixed_dialogue_cluster(
        clusters,
        sample_frames=max(sampled_frames, 1),
        min_hit_ratio=float(cfg.gold_story_ocr_region_min_hit_ratio),
        max_h_ratio=max_h_ratio,
    )
    if picked is None:
        logger.info(
            "subtitle region detect fallback bvid=%s frames=%s bands=%s",
            video_path.stem,
            sampled_frames,
            len(observations),
        )
        return fallback_subtitle_region(cfg)

    merged = _region_from_cluster(
        picked,
        max_h_ratio=max_h_ratio,
        min_h_ratio=min_h_ratio,
    )
    logger.info(
        "subtitle region bvid=%s y=%.3f h=%.3f hits=%s/%s frames=%s conf=%.2f",
        video_path.stem,
        merged.y_ratio,
        merged.h_ratio,
        merged.samples,
        len(observations),
        sampled_frames,
        merged.confidence,
    )
    return merged


def detect_burned_subtitles(
    video_path: Path,
    *,
    workspace: Path,
    duration_sec: float | None = None,
    sample_points: tuple[float, ...] = (0.2, 0.5, 0.8),
    hits_required: int = 2,
    config: Config | None = None,
) -> bool:
    """连续多帧字幕 ROI 有文字带 → 判定烧录字幕。"""
    cfg = config or Config()
    if duration_sec is None or duration_sec <= 0:
        duration_sec = _probe_duration(video_path)
    if duration_sec <= 0:
        return False

    region = detect_subtitle_region(
        video_path,
        workspace=workspace / "region",
        duration_sec=duration_sec,
        config=cfg,
    )
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
                region=region,
            )
            if roi_has_text_band(frame_path):
                hits += 1
        except Exception:
            continue
    return hits >= hits_required
