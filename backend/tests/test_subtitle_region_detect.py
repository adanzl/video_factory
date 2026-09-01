"""字幕带 ROI 检测测试。"""

import statistics

import numpy as np

from app.services.daily_story.gold_story.transcript.detect import (
    SubtitleRegion,
    _BandObservation,
    _cluster_observations,
    _region_from_cluster,
    _select_fixed_dialogue_cluster,
    band_edge_side_contrast_score,
    compute_edge_density_profile,
    list_subtitle_bands_from_gray,
    sliding_window_subtitle_band,
)


def _synthetic_dual_band_frame() -> np.ndarray:
    """底部两条水平文字带：上方说明层 + 下方对白层。"""
    h, w = 720, 1280
    gray = np.full((h, w), 24, dtype=np.uint8)
    upper_y0, upper_y1 = int(h * 0.78), int(h * 0.83)
    lower_y0, lower_y1 = int(h * 0.91), int(h * 0.95)
    for y in range(upper_y0, upper_y1):
        gray[y, 120:1160] = 180 + (y % 5) * 8
    for y in range(lower_y0, lower_y1):
        gray[y, 220:1060] = 190 + (y % 4) * 7
    return gray


def test_sliding_window_finds_bottom_subtitle_band():
    """边缘密度投影 + 滑动窗口应圈住底部字幕带。"""
    h, w = 720, 1280
    gray = np.full((h, w), 20, dtype=np.uint8)
    # 底部字幕：横向高对比条纹
    y0, y1 = int(h * 0.90), int(h * 0.95)
    for y in range(y0, y1):
        gray[y, 100:1180] = 200 if (y % 2 == 0) else 40
    profile = compute_edge_density_profile(gray)
    hit = sliding_window_subtitle_band(
        profile,
        search_y0=int(h * 0.65),
        min_h=int(h * 0.02),
        max_h=int(h * 0.12),
        step=2,
    )
    assert hit is not None
    by0, by1, _ = hit
    center = 0.5 * (by0 + by1) / h
    assert center >= 0.85


def test_band_contrast_prefers_sharp_text_over_gradient():
    """字幕字/底高对比分应明显高于地板渐变边缘。"""
    h, w = 240, 640
    text = np.full((h, w), 30, dtype=np.uint8)
    text[100:140, 80:560] = 30
    # 白字：每隔几列画竖笔，两侧差大
    for x in range(100, 540, 12):
        text[105:135, x : x + 4] = 230

    grad = np.zeros((h, w), dtype=np.uint8)
    for y in range(h):
        grad[y, :] = int(40 + 160 * y / max(h - 1, 1))

    text_score = band_edge_side_contrast_score(text, 100, 140)
    grad_score = band_edge_side_contrast_score(grad, 100, 140)
    assert text_score > grad_score
    assert text_score >= 0.35


def test_select_fixed_dialogue_cluster_prefers_recurring_lower_band():
    observations: list[_BandObservation] = []
    for _ in range(2):
        observations.append(_BandObservation(y_ratio=0.78, h_ratio=0.05))
    for _ in range(6):
        observations.append(_BandObservation(y_ratio=0.90, h_ratio=0.06))

    clusters = _cluster_observations(observations, y_center_tol=0.025)
    picked = _select_fixed_dialogue_cluster(
        clusters,
        sample_frames=8,
        max_h_ratio=0.10,
    )
    assert picked is not None
    assert len(picked) == 6
    assert statistics.mean(obs.y_center for obs in picked) > 0.88


def test_region_from_cluster_tracks_observed_height():
    """动态带宽：观测 h 的 P90 *1.15，不再 *2.5 / 0.16 硬撑。"""
    cluster = [_BandObservation(y_ratio=0.88, h_ratio=0.05) for _ in range(5)]
    region = _region_from_cluster(cluster, max_h_ratio=0.22, min_h_ratio=0.025)
    assert region.h_ratio <= 0.05 * 1.15 + 1e-6
    assert region.h_ratio >= 0.05
    assert region.y_ratio + region.h_ratio <= 1.0


def test_select_cluster_prefers_bottom_prior():
    """常驻顶部台标次数更多时，仍应选底部对白带。"""
    top = [_BandObservation(y_ratio=0.10, h_ratio=0.04) for _ in range(10)]
    bottom = [_BandObservation(y_ratio=0.90, h_ratio=0.05) for _ in range(4)]
    clusters = _cluster_observations(top + bottom, y_center_tol=0.025)
    picked = _select_fixed_dialogue_cluster(
        clusters,
        sample_frames=12,
        max_h_ratio=0.22,
        min_y_center=0.84,
    )
    assert picked is not None
    assert statistics.mean(obs.y_center for obs in picked) >= 0.84


def test_list_subtitle_bands_returns_empty_on_blank():
    gray = np.full((480, 640), 20, dtype=np.uint8)
    assert list_subtitle_bands_from_gray(gray) == []


def test_pick_region_from_search_band_grays_maps_to_fullframe():
    """搜索带裁切帧定带后，y/h 须换算回全帧坐标。"""
    from app.services.daily_story.gold_story.transcript.detect import (
        pick_subtitle_region_from_grays,
    )

    full_h, w = 720, 1280
    search_ratio = 0.5
    band_top = 1.0 - search_ratio
    search_h = int(full_h * search_ratio)
    # 全帧字幕约在 0.90–0.95 → 搜索带内约 0.80–0.90
    local_y0 = int(search_h * 0.80)
    local_y1 = int(search_h * 0.90)
    gray = np.full((search_h, w), 20, dtype=np.uint8)
    for y in range(local_y0, local_y1):
        gray[y, 100:1180] = 200 if (y % 2 == 0) else 40

    region = pick_subtitle_region_from_grays(
        [gray, gray, gray],
        search_band_top_ratio=band_top,
        log_tag="test",
    )
    assert region.method.startswith("edge_density")
    center = region.y_ratio + 0.5 * region.h_ratio
    assert center >= 0.85
    assert region.y_ratio >= band_top - 1e-6


def test_region_crop_vf_must_pass_max_h_for_detect_samples():
    """detect 抽样切图须传 config max_h，否则默认 0.12 压扁 ROI。"""
    region = SubtitleRegion(y_ratio=0.8, h_ratio=0.2)
    assert region.crop_vf_expr(max_h_ratio=0.20) == "crop=iw:ih*0.2:0:ih*0.8"
    assert "0.12" in region.crop_vf_expr()


def test_ensure_ocr_readable_region_expands_thin_band():
    from app.services.daily_story.gold_story.transcript.detect import (
        ensure_ocr_readable_region,
    )

    thin = SubtitleRegion(y_ratio=0.687, h_ratio=0.040, method="test")
    expanded = ensure_ocr_readable_region(
        thin,
        min_h_ratio=0.07,
        max_h_ratio=0.22,
    )
    assert expanded.h_ratio >= 0.07 - 1e-6
    assert expanded.y_ratio < thin.y_ratio
    assert expanded.y_ratio + expanded.h_ratio <= 1.0 + 1e-6
