"""对白白底气泡 vs overlay 描边字过滤。"""

import numpy as np

from app.services.daily_story.gold_story.subtitle_ocr import (
    _box_white_bg_ratio,
    _filter_dialogue_boxes,
)


def _box(y0: float, y1: float, x1: float = 200.0) -> np.ndarray:
    return np.array([[0.0, y0], [x1, y0], [x1, y1], [0.0, y1]])


def _bubble_patch(h: int = 36, w: int = 220) -> np.ndarray:
    """白底黑字气泡。"""
    import cv2

    img = np.full((h, w, 3), 40, dtype=np.uint8)
    cv2.rectangle(img, (4, 4), (w - 5, h - 5), (235, 232, 236), thickness=-1)
    cv2.putText(
        img,
        "我爱学习",
        (16, h - 12),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        (30, 28, 32),
        1,
        cv2.LINE_AA,
    )
    return img


def _stroke_patch(h: int = 36, w: int = 220) -> np.ndarray:
    """描边 overlay（无白底）。"""
    import cv2

    img = np.full((h, w, 3), 40, dtype=np.uint8)
    cv2.putText(
        img,
        "姐姐一招制敌呀",
        (8, h - 12),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        (245, 245, 245),
        2,
        cv2.LINE_AA,
    )
    return img


def test_white_bg_ratio_distinguishes_bubble_and_stroke():
    bubble = _bubble_patch()
    stroke = _stroke_patch()
    bubble_ratio = _box_white_bg_ratio(bubble, _box(4, 32))
    stroke_ratio = _box_white_bg_ratio(stroke, _box(4, 32))
    assert bubble_ratio >= 0.42
    assert stroke_ratio < 0.42
    assert bubble_ratio - stroke_ratio >= 0.15


def test_filter_dialogue_boxes_drops_overlay():
    canvas = np.full((96, 320, 3), 40, dtype=np.uint8)
    canvas[0:36, :] = _stroke_patch(h=36, w=320)
    canvas[54:90, :] = _bubble_patch(h=36, w=320)

    txts = ("姐姐一招制敌呀", "你们就")
    scores = (0.95, 0.98)
    boxes = [_box(4, 32), _box(58, 86)]
    kept_txts, _, _ = _filter_dialogue_boxes(
        canvas,
        txts,
        scores,
        boxes,
        min_white_bg_ratio=0.42,
    )
    assert kept_txts == ["你们就"]
