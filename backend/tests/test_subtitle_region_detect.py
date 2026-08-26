"""字幕带 ROI 检测测试。"""

import statistics

import numpy as np

from app.services.daily_story.gold_story.transcript.detect import (
    SubtitleRegion,
    _BandObservation,
    _cluster_observations,
    _region_from_cluster,
    _select_fixed_dialogue_cluster,
    list_subtitle_bands_from_gray,
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


def test_list_subtitle_bands_finds_dual_layers():
    bands = list_subtitle_bands_from_gray(_synthetic_dual_band_frame())
    assert len(bands) >= 2
    centers = sorted(obs.y_center for obs in bands)
    assert centers[-1] - centers[0] >= 0.05


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


def test_region_from_cluster_caps_height_to_two_lines():
    cluster = [_BandObservation(y_ratio=0.88, h_ratio=0.05) for _ in range(5)]
    region = _region_from_cluster(cluster, max_h_ratio=0.18, min_h_ratio=0.025)
    assert region.h_ratio <= 0.18
    assert region.y_ratio <= 0.88
    assert region.y_ratio + region.h_ratio <= 1.0


def test_list_subtitle_bands_returns_empty_on_blank():
    gray = np.full((480, 640), 20, dtype=np.uint8)
    assert list_subtitle_bands_from_gray(gray) == []


def test_region_crop_vf_must_pass_max_h_for_detect_samples():
    """detect 抽样切图须传 config max_h，否则默认 0.12 压扁 ROI。"""
    region = SubtitleRegion(y_ratio=0.8, h_ratio=0.2)
    assert region.crop_vf_expr(max_h_ratio=0.20) == "crop=iw:ih*0.2:0:ih*0.8"
    assert "0.12" in region.crop_vf_expr()
