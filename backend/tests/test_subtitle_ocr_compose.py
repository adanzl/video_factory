"""单帧 OCR 合成：小字号说明过滤 + 帧内去换行。"""

import numpy as np

from app.services.gold_story.transcript.ocr import compose_frame_text


def _box(y0: float, y1: float) -> np.ndarray:
    return np.array([[0.0, y0], [10.0, y0], [10.0, y1], [0.0, y1]])


def test_compose_drops_small_attribution_line():
    text, _ = compose_frame_text(
        ("这就完了得了呗", "素材来源：海洋"),
        (0.95, 0.99),
        [_box(0, 35), _box(0, 17)],
        crop_h=58.0,
    )
    assert text == "这就完了得了呗"
    assert "素材来源" not in text


def test_compose_skips_frame_with_only_small_font():
    text, conf = compose_frame_text(
        ("素材来源：海洋",),
        (0.99,),
        [_box(0, 21)],
        crop_h=58.0,
    )
    assert text == ""
    assert conf == 0.0


def test_compose_joins_multiline_dialogue_without_break():
    text, _ = compose_frame_text(
        ("你听不懂我说话我也听不懂", "你说话"),
        (0.9, 0.85),
        [_box(0, 33), _box(34, 66)],
        crop_h=58.0,
    )
    assert text == "你听不懂我说话我也听不懂你说话"
