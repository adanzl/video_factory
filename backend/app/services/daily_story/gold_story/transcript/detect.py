"""烧录字幕检测与字幕带 ROI 定位。

定带算法：边缘密度行投影 → 中位聚合 → 底部搜索区滑动窗口取峰。
OCR 主路径复用已抽搜索带帧定带（一遍解码）；本模块另留视频抽样入口
供烧录探测等兼容调用。
"""

from __future__ import annotations

import logging
import shutil
import statistics
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from app.config import Config
from app.utils.async_util import run_subprocess_cmd

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
    _, stdout, _ = run_subprocess_cmd(cmd, check=False, timeout=60.0)
    try:
        return float((stdout or "").strip())
    except ValueError:
        return 0.0


def extract_sample_frame(
    video_path: Path,
    *,
    output_path: Path,
    timestamp_sec: float,
    region: SubtitleRegion | None = None,
    crop_bottom_ratio: float = 0.20,
    config: Config | None = None,
    max_h_ratio: float | None = None,
) -> Path:
    """抽取单帧；region 优先，否则回退固定底栏。"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cfg = config or Config()
    max_h = float(
        max_h_ratio
        if max_h_ratio is not None
        else cfg.gold_story_ocr_region_max_h_ratio
    )
    if region is not None:
        vf = region.crop_vf_expr(max_h_ratio=max_h)
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
    run_subprocess_cmd(cmd, check=True)
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
    run_subprocess_cmd(cmd, check=True)
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


def compute_edge_density_profile(gray: np.ndarray) -> np.ndarray:
    """行向边缘密度投影：profile[y] = 该行边缘像素占比。"""
    import cv2

    if gray.ndim != 2 or gray.size == 0:
        return np.zeros(0, dtype=float)
    blurred = cv2.GaussianBlur(gray, (3, 3), 0)
    edges = cv2.Canny(blurred, 80, 180)
    # 轻微横向膨胀，让笔画连成水平带
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (9, 1))
    edges = cv2.dilate(edges, kernel, iterations=1)
    width = max(int(edges.shape[1]), 1)
    profile = np.sum(edges > 0, axis=1).astype(float) / float(width)
    return profile


def _sliding_window_scores(profile: np.ndarray, win_h: int) -> np.ndarray:
    """均值密度滑动窗口；返回长度 H-win_h+1。"""
    if win_h <= 0 or profile.size < win_h:
        return np.zeros(0, dtype=float)
    prefix_sum = np.cumsum(np.insert(profile.astype(float), 0, 0.0))
    return (prefix_sum[win_h:] - prefix_sum[:-win_h]) / float(win_h)


def sliding_window_subtitle_band(
    profile: np.ndarray,
    *,
    search_y0: int,
    min_h: int,
    max_h: int,
    step: int = 2,
) -> tuple[int, int, float] | None:
    """在搜索区内用滑动窗口圈出边缘密度最高的字幕带 (y0, y1, score)。"""
    candidates = collect_sliding_window_candidates(
        profile,
        search_y0=search_y0,
        min_h=min_h,
        max_h=max_h,
        step=step,
        top_k=1,
    )
    return candidates[0] if candidates else None


def collect_sliding_window_candidates(
    profile: np.ndarray,
    *,
    search_y0: int,
    min_h: int,
    max_h: int,
    step: int = 2,
    top_k: int = 5,
) -> list[tuple[int, int, float]]:
    """滑动窗口候选带，按边缘密度分排序。"""
    if profile.size == 0:
        return []
    h_frame = int(profile.size)
    y0_floor = max(0, min(int(search_y0), h_frame - 1))
    min_h = max(3, int(min_h))
    max_h = max(min_h, int(max_h))
    step = max(1, int(step))

    scored: list[tuple[int, int, float]] = []
    for win_h in range(min_h, max_h + 1, step):
        scores = _sliding_window_scores(profile, win_h)
        if scores.size == 0:
            continue
        start_lo = y0_floor
        start_hi = h_frame - win_h
        if start_hi < start_lo:
            continue
        segment = scores[start_lo : start_hi + 1]
        if segment.size == 0:
            continue
        # 取该窗高下的局部峰，避免只盯一个全局点
        peak_idx = int(np.argmax(segment))
        start = start_lo + peak_idx
        score = float(scores[start])
        bottom_bonus = 0.05 * (start + win_h) / float(h_frame)
        compact_bonus = 0.02 * (
            1.0 - (win_h - min_h) / float(max(max_h - min_h, 1))
        )
        scored.append((start, start + win_h, score + bottom_bonus + compact_bonus))

    if not scored:
        return []
    scored.sort(key=lambda row: row[2], reverse=True)
    # NMS：中心距过近只留高分
    kept: list[tuple[int, int, float]] = []
    for y0, y1, score in scored:
        center = 0.5 * (y0 + y1)
        if any(abs(center - 0.5 * (a + b)) < max(8.0, 0.4 * (y1 - y0)) for a, b, _ in kept):
            continue
        kept.append((y0, y1, score))
        if len(kept) >= max(1, int(top_k)):
            break
    return kept


def band_edge_side_contrast_score(
    gray: np.ndarray,
    y0: int,
    y1: int,
    *,
    offset: int = 2,
) -> float:
    """边缘两侧色差：字幕字/底对比高；地板/桌面渐变边缘两侧接近。

    返回 0~1，越高越像烧录字幕。
    """
    import cv2

    if gray.ndim != 2 or gray.size == 0 or y1 <= y0:
        return 0.0
    h, w = gray.shape
    y0 = max(0, min(int(y0), h - 1))
    y1 = max(y0 + 1, min(int(y1), h))
    roi = gray[y0:y1, :]
    if roi.size == 0:
        return 0.0
    blurred = cv2.GaussianBlur(roi, (3, 3), 0)
    edges = cv2.Canny(blurred, 80, 180)
    ys, xs = np.where(edges > 0)
    if ys.size < 12:
        # 边缘太少：用直方图双峰近似（字+底）
        hist = np.bincount(roi.ravel(), minlength=256).astype(float)
        if hist.sum() <= 0:
            return 0.0
        # 粗分低/高两半峰值差
        lo = float(hist[:128].max())
        hi = float(hist[128:].max())
        peak = max(lo, hi)
        other = min(lo, hi)
        return float(np.clip((peak - other) / (peak + 1e-6), 0.0, 1.0))

    off = max(1, int(offset))
    diffs: list[float] = []
    # 子采样，避免过慢
    step = max(1, ys.size // 400)
    for i in range(0, ys.size, step):
        yy = int(ys[i])
        xx = int(xs[i])
        x_l = xx - off
        x_r = xx + off
        if x_l < 0 or x_r >= w:
            continue
        left = float(roi[yy, x_l])
        right = float(roi[yy, x_r])
        diffs.append(abs(left - right))
    if not diffs:
        return 0.0
    # 字幕描边两侧差通常很大；渐变纹理中位数偏低
    med = float(np.median(np.asarray(diffs, dtype=float)))
    return float(np.clip(med / 80.0, 0.0, 1.0))


def mean_band_contrast_over_frames(
    grays: list[np.ndarray],
    y0: int,
    y1: int,
) -> float:
    if not grays:
        return 0.0
    scores = [band_edge_side_contrast_score(g, y0, y1) for g in grays if g is not None]
    if not scores:
        return 0.0
    return float(statistics.median(scores))


def refine_band_by_profile(
    profile: np.ndarray,
    y0: int,
    y1: int,
    *,
    keep_ratio: float = 0.35,
) -> tuple[int, int]:
    """在窗口内按投影阈值收紧上下边界，去掉空白边。"""
    if profile.size == 0 or y1 <= y0:
        return y0, y1
    y0 = max(0, min(y0, profile.size - 1))
    y1 = max(y0 + 1, min(y1, profile.size))
    segment = profile[y0:y1]
    peak = float(segment.max()) if segment.size else 0.0
    if peak <= 1e-6:
        return y0, y1
    thr = peak * float(keep_ratio)
    mask = segment >= thr
    if not np.any(mask):
        return y0, y1
    idx = np.where(mask)[0]
    return y0 + int(idx[0]), y0 + int(idx[-1]) + 1


def _bands_from_edge_profile(gray: np.ndarray) -> list[tuple[int, int]]:
    """兼容旧名：单帧边缘投影 + 滑动窗口，返回若干候选带。"""
    profile = compute_edge_density_profile(gray)
    if profile.size == 0:
        return []
    h = int(profile.size)
    # 在整幅内找主峰，再 NMS 找次峰（供双层检测）
    bands: list[tuple[int, int]] = []
    work = profile.copy()
    min_h = max(3, int(h * 0.02))
    max_h = max(min_h, int(h * 0.12))
    for _ in range(3):
        hit = sliding_window_subtitle_band(
            work,
            search_y0=0,
            min_h=min_h,
            max_h=max_h,
            step=2,
        )
        if hit is None or hit[2] < 0.02:
            break
        y0, y1, _score = hit
        y0, y1 = refine_band_by_profile(profile, y0, y1)
        if y1 - y0 >= 3:
            bands.append((y0, y1))
        # 抑制已选峰，继续找次峰
        pad = max(2, (y1 - y0) // 2)
        lo = max(0, y0 - pad)
        hi = min(h, y1 + pad)
        work[lo:hi] = 0.0
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
    min_y_center: float = 0.0,
) -> list[_BandObservation]:
    """第一步筛选：丢弃超高带 + 画面偏上的说明层。"""
    limit = float(max_h_ratio) * 1.05
    floor = max(0.0, float(min_y_center))
    return [
        obs
        for obs in observations
        if float(obs.h_ratio) <= limit and obs.y_center >= floor
    ]


def list_subtitle_bands_from_gray(
    gray: np.ndarray,
    *,
    search_bottom_ratio: float = 0.35,
    min_h_ratio: float = 0.02,
    max_h_ratio: float = 0.10,
) -> list[_BandObservation]:
    """底部搜索区：边缘密度投影 + 滑动窗口，列出候选字幕带。"""
    if gray.ndim != 2 or gray.size == 0:
        return []

    frame_h, _frame_w = gray.shape
    profile = compute_edge_density_profile(gray)
    if profile.size == 0 or float(profile.max()) <= 0:
        return []

    search_ratio = max(0.15, min(float(search_bottom_ratio), 0.55))
    search_y = int(frame_h * (1.0 - search_ratio))
    min_h = max(int(frame_h * min_h_ratio), 3)
    max_h = max(int(frame_h * max_h_ratio), min_h + 1)

    work = profile.copy()
    out: list[_BandObservation] = []
    for _ in range(3):
        hit = sliding_window_subtitle_band(
            work,
            search_y0=search_y,
            min_h=min_h,
            max_h=max_h,
            step=2,
        )
        if hit is None or hit[2] < 0.015:
            break
        y0, y1, _score = hit
        y0, y1 = refine_band_by_profile(profile, y0, y1)
        ratios = _band_to_ratios(
            y0,
            y1,
            frame_h=frame_h,
            max_h_ratio=max_h_ratio,
        )
        if ratios is not None:
            y_ratio, h_ratio = ratios
            if h_ratio <= max_h_ratio * 1.05:
                out.append(_BandObservation(y_ratio=y_ratio, h_ratio=h_ratio))
        pad = max(2, (y1 - y0) // 2)
        work[max(0, y0 - pad) : min(frame_h, y1 + pad)] = 0.0
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
    min_y_center: float = 0.84,
) -> list[_BandObservation] | None:
    """选对白带：底部先验优先，再比出现次数（不全靠频率，防常驻台标劫持）。"""
    if not clusters:
        return None
    min_hits = max(2, int(sample_frames * min_hit_ratio))
    floor = max(0.0, float(min_y_center))

    def _cluster_median_h(cluster: list[_BandObservation]) -> float:
        return statistics.median([obs.h_ratio for obs in cluster])

    def _cluster_mean_y(cluster: list[_BandObservation]) -> float:
        return statistics.mean([obs.y_center for obs in cluster])

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

    bottom_pool = [c for c in pool if _cluster_mean_y(c) >= floor]
    if bottom_pool:
        pool = bottom_pool

    def _score(cluster: list[_BandObservation]) -> tuple[int, float]:
        # 同在底部候选里：次数多优先，其次更靠下
        return (len(cluster), _cluster_mean_y(cluster))

    return max(pool, key=_score)


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(float(v) for v in values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * (float(pct) / 100.0)
    lo = int(rank)
    hi = min(lo + 1, len(ordered) - 1)
    frac = rank - lo
    return ordered[lo] * (1.0 - frac) + ordered[hi] * frac


def _region_from_cluster(
    cluster: list[_BandObservation],
    *,
    max_h_ratio: float,
    min_h_ratio: float,
) -> SubtitleRegion:
    """聚类 → 对白带锚点；高度用观测 h 的 P90 + 小 pad，只封顶不硬撑。"""
    y_center = statistics.median([obs.y_center for obs in cluster])
    heights = [float(obs.h_ratio) for obs in cluster]
    h_obs = _percentile(heights, 90.0)
    h_ratio = min(
        float(max_h_ratio),
        max(float(min_h_ratio), float(h_obs) * 1.15),
    )
    y_ratio = max(0.0, min(y_center - h_ratio * 0.52, 1.0 - h_ratio))
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


def pick_subtitle_region_from_grays(
    grays: list[np.ndarray],
    *,
    config: Config | None = None,
    search_band_top_ratio: float | None = None,
    log_tag: str = "",
) -> SubtitleRegion:
    """从已有灰度帧定对白字幕带（不再二次解码视频）。

    ``search_band_top_ratio`` 非空时，输入已是全帧底部搜索带裁切，
    返回的 y/h 仍换算成**全帧**归一化坐标。
    """
    cfg = config or Config()
    if not cfg.gold_story_ocr_region_detect:
        return fallback_subtitle_region(cfg)
    if not grays:
        return fallback_subtitle_region(cfg)

    search_ratio_cfg = float(cfg.gold_story_ocr_region_search_ratio)
    max_h_ratio = float(cfg.gold_story_ocr_region_max_h_ratio)
    min_h_ratio = float(cfg.gold_story_ocr_region_min_h_ratio)

    profiles: list[np.ndarray] = []
    kept: list[np.ndarray] = []
    frame_h = 0
    for gray in grays:
        if gray is None or getattr(gray, "ndim", 0) != 2 or gray.size == 0:
            continue
        profile = compute_edge_density_profile(gray)
        if profile.size == 0:
            continue
        peak = float(profile.max())
        if peak > 1e-6:
            profile = profile / peak
        profiles.append(profile)
        kept.append(gray)
        frame_h = int(profile.size)

    if not profiles or frame_h <= 0:
        return fallback_subtitle_region(cfg)

    stacked = np.stack(
        [p if p.size == frame_h else np.resize(p, frame_h) for p in profiles],
        axis=0,
    )
    agg = np.median(stacked, axis=0)

    band_top = search_band_top_ratio
    if band_top is not None:
        # 输入已是搜索带：整图可搜；min/max 高按全帧比例换算到本图像素
        search_ratio = max(0.15, min(1.0 - float(band_top), 0.55))
        search_y0 = 0
        full_h_equiv = frame_h / max(search_ratio, 1e-6)
        min_h = max(int(full_h_equiv * min_h_ratio), 8)
        max_h = max(
            min_h + 1,
            int(full_h_equiv * min(max_h_ratio, 0.14)),
        )
        min_h = min(min_h, frame_h - 1)
        max_h = min(max_h, frame_h)
    else:
        search_ratio = max(0.15, min(float(search_ratio_cfg), 0.55))
        search_y0 = int(frame_h * (1.0 - search_ratio))
        min_h = max(int(frame_h * min_h_ratio), 8)
        max_h = max(min_h + 1, int(frame_h * min(max_h_ratio, 0.14)))

    candidates = collect_sliding_window_candidates(
        agg,
        search_y0=search_y0,
        min_h=min_h,
        max_h=max_h,
        step=max(1, frame_h // 400),
        top_k=5,
    )
    if not candidates:
        logger.info(
            "subtitle region sliding-window miss tag=%s frames=%s → fallback",
            log_tag or "-",
            len(profiles),
        )
        return fallback_subtitle_region(cfg)

    best: tuple[int, int, float, float] | None = None
    for y0, y1, dens_score in candidates:
        ry0, ry1 = refine_band_by_profile(agg, y0, y1, keep_ratio=0.30)
        contrast = mean_band_contrast_over_frames(kept, ry0, ry1)
        final = float(dens_score) * (0.35 + 0.65 * float(contrast))
        if best is None or final > best[2]:
            best = (ry0, ry1, final, contrast)

    if best is None or best[2] < 0.015:
        return fallback_subtitle_region(cfg)

    y0, y1, score, contrast = best
    pad = max(int((y1 - y0) * 0.12), max(int(frame_h * 0.004), 2))
    y0 = max(0, y0 - pad)
    y1 = min(frame_h, y1 + pad)

    if band_top is not None:
        search_ratio = max(0.15, min(1.0 - float(band_top), 0.55))
        local_y = y0 / float(frame_h)
        local_h = (y1 - y0) / float(frame_h)
        y_ratio = float(band_top) + local_y * search_ratio
        h_ratio = local_h * search_ratio
    else:
        h_ratio = (y1 - y0) / float(frame_h)
        y_ratio = y0 / float(frame_h)

    conf = min(
        1.0,
        0.35 + 0.06 * len(profiles) + 0.25 * contrast + min(score, 0.25),
    )
    region = SubtitleRegion(
        y_ratio=y_ratio,
        h_ratio=h_ratio,
        method="edge_density_sliding+contrast",
        samples=len(profiles),
        confidence=conf,
    ).clamp(max_h_ratio=max_h_ratio)
    logger.info(
        "subtitle region tag=%s y=%.3f h=%.3f frames=%s dens=%.3f contrast=%.2f conf=%.2f",
        log_tag or "-",
        region.y_ratio,
        region.h_ratio,
        region.samples,
        score,
        contrast,
        region.confidence,
    )
    return region


def detect_subtitle_region_from_images(
    image_paths: list[Path],
    *,
    config: Config | None = None,
    search_band_top_ratio: float | None = None,
    max_samples: int = 10,
    log_tag: str = "",
) -> SubtitleRegion:
    """从已抽帧路径定带；均匀抽样，避免再跑一遍 ffmpeg。"""
    cfg = config or Config()
    if not image_paths:
        return fallback_subtitle_region(cfg)
    try:
        import cv2
    except ImportError:
        logger.warning("opencv missing, subtitle region fallback")
        return fallback_subtitle_region(cfg)

    paths = list(image_paths)
    cap = max(2, int(max_samples))
    if len(paths) > cap:
        last = len(paths) - 1
        picked: list[Path] = []
        seen: set[int] = set()
        for slot in range(cap):
            idx = round(slot * last / (cap - 1))
            if idx in seen:
                continue
            seen.add(idx)
            picked.append(paths[idx])
        paths = picked

    grays: list[np.ndarray] = []
    for path in paths:
        gray = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        if gray is not None:
            grays.append(gray)
    return pick_subtitle_region_from_grays(
        grays,
        config=cfg,
        search_band_top_ratio=search_band_top_ratio,
        log_tag=log_tag,
    )


def detect_subtitle_region(
    video_path: Path,
    *,
    workspace: Path,
    duration_sec: float | None = None,
    config: Config | None = None,
) -> SubtitleRegion:
    """兼容入口：临时抽多样本全帧再定带（烧录探测等）。

    OCR 主路径请用已抽搜索带帧 + ``detect_subtitle_region_from_images``，
    避免视频解码两遍。
    """
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
            0.12,
            0.22,
            0.32,
            0.42,
            0.52,
            0.62,
            0.72,
            0.82,
            0.90,
            0.96,
        )
    )
    frame_dir = workspace / "region_detect"
    frame_dir.mkdir(parents=True, exist_ok=True)

    try:
        import cv2
    except ImportError:
        logger.warning("opencv missing, subtitle region fallback")
        return fallback_subtitle_region(cfg)

    grays: list[np.ndarray] = []
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
            if gray is not None:
                grays.append(gray)
        except Exception as exc:
            logger.debug("subtitle region sample failed ts=%.2f: %s", ts, exc)

    return pick_subtitle_region_from_grays(
        grays,
        config=cfg,
        search_band_top_ratio=None,
        log_tag=video_path.stem,
    )


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
                config=cfg,
            )
            if roi_has_text_band(frame_path):
                hits += 1
        except Exception:
            continue
    return hits >= hits_required
