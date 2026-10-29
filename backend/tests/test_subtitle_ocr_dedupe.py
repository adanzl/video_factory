"""OCR 抽帧去重测试。"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from app.services.gold_story.transcript.ocr import OcrFrame, dedupe_frames


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
    # 完整转写默认不能按80帧上限静默丢掉中间字幕。
    assert len(dedupe_frames(frames)) == 120


def test_ocr_batches_process_all_frames_once(tmp_path, monkeypatch):
    from app.config import Config
    from app.services.gold_story.transcript import ocr
    from concurrent.futures import Future

    cfg = Config()
    cfg.gold_story_ocr_max_frames = 3
    cfg.gold_story_ocr_frame_workers = 2
    submitted = []
    batches = []
    class Pool:
        def __init__(self, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def submit(self, fn, task):
            submitted.append(task)
            future = Future()
            future.set_result({"timestamp_sec": task[0], "hits": []})
            return future
    def wait(futures):
        batches.append(len(futures))
        return futures
    monkeypatch.setattr(ocr, "ProcessPoolExecutor", Pool)
    monkeypatch.setattr(ocr, "wait_futures_hub", wait)
    frames = [OcrFrame(timestamp_sec=float(i), image_path=tmp_path / f"{i}.png") for i in range(8)]
    rows = ocr.ocr_frames_parallel(frames, cfg)
    assert batches == [3, 3, 2]
    assert len(rows) == len(submitted) == 8
    assert [r["timestamp_sec"] for r in rows] == list(range(8))


def test_ocr_rejects_incomplete_batch(tmp_path, monkeypatch):
    from app.config import Config
    from app.services.gold_story.transcript import ocr
    import pytest
    class Pool:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def submit(self, *args): return None
    cfg = Config()
    cfg.gold_story_ocr_frame_workers = 2
    monkeypatch.setattr(ocr, "ProcessPoolExecutor", Pool)
    monkeypatch.setattr(ocr, "wait_futures_hub", lambda *_a: [])
    frames = [OcrFrame(timestamp_sec=float(i), image_path=tmp_path / f"{i}.png") for i in range(2)]
    with pytest.raises(RuntimeError, match="incomplete"):
        ocr.ocr_frames_parallel(frames, cfg)
