"""OCR 抽帧去重测试。"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from app.services.daily_story.gold_story.transcript.ocr import OcrFrame, dedupe_frames


def _write_frame(path: Path, seed: int) -> None:
    rng = np.random.default_rng(seed)
    gray = rng.integers(0, 256, size=(48, 320), dtype=np.uint8)
    cv2.imwrite(str(path), gray)


def test_dedupe_merges_identical_subtitle_frames(tmp_path: Path):
    frames: list[OcrFrame] = []
    for idx in range(10):
        path = tmp_path / f"frame_{idx:03d}.jpg"
        _write_frame(path, 42)
        frames.append(OcrFrame(timestamp_sec=float(idx), image_path=path))

    kept = dedupe_frames(frames, max_frames=80)
    assert len(kept) == 2
    assert kept[0].timestamp_sec == 0.0
    assert kept[-1].timestamp_sec == 9.0


def test_dedupe_keeps_text_change_frames(tmp_path: Path):
    frames: list[OcrFrame] = []
    seeds = [1, 1, 1, 2, 2, 3, 3]
    for idx, seed in enumerate(seeds):
        path = tmp_path / f"frame_{idx:03d}.jpg"
        _write_frame(path, seed)
        frames.append(OcrFrame(timestamp_sec=float(idx), image_path=path))

    kept = dedupe_frames(frames, max_frames=80)
    assert [frame.timestamp_sec for frame in kept] == [0.0, 3.0, 5.0, 6.0]


def test_dedupe_subsamples_when_over_max_frames(tmp_path: Path):
    frames: list[OcrFrame] = []
    for idx in range(120):
        path = tmp_path / f"frame_{idx:03d}.jpg"
        _write_frame(path, idx)
        frames.append(OcrFrame(timestamp_sec=float(idx), image_path=path))

    kept = dedupe_frames(frames, max_frames=80)
    assert len(kept) == 80
    assert kept[0].timestamp_sec == 0.0
    assert kept[-1].timestamp_sec == 119.0
