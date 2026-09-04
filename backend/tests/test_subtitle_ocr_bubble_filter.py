"""多数派字色过滤（白底只是特征）。"""

import numpy as np

from app.services.gold_story.transcript.ocr import (
    _box_ink_color_key,
    _box_white_bg_ratio,
    _preprocess_subtitle_crop,
    filter_hits_by_majority_color,
    filter_repeat_watermark_hits,
    infer_majority_ink_color,
)


def _box(y0: float, y1: float, x1: float = 200.0) -> np.ndarray:
    return np.array([[0.0, y0], [x1, y0], [x1, y1], [0.0, y1]])


def _bubble_patch(h: int = 36, w: int = 220) -> np.ndarray:
    import cv2

    img = np.full((h, w, 3), 40, dtype=np.uint8)
    cv2.rectangle(img, (4, 4), (w - 5, h - 5), (235, 232, 236), thickness=-1)
    cv2.putText(
        img,
        "woai",
        (16, h - 12),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        (30, 28, 32),
        1,
        cv2.LINE_AA,
    )
    return img


def _stroke_patch(h: int = 36, w: int = 220) -> np.ndarray:
    import cv2

    img = np.full((h, w, 3), 40, dtype=np.uint8)
    cv2.putText(
        img,
        "hello",
        (8, h - 12),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        (245, 245, 245),
        2,
        cv2.LINE_AA,
    )
    return img


def test_white_bg_is_feature_not_gate():
    bubble = _bubble_patch()
    stroke = _stroke_patch()
    assert _box_white_bg_ratio(bubble, _box(4, 32)) > _box_white_bg_ratio(
        stroke, _box(4, 32)
    )


def test_infer_majority_ink_by_char_weight():
    hits = [
        {"text": "北京", "color_key": "yellow"},
        {"text": "你这样说我还觉得你很讨厌呢", "color_key": "white"},
    ]
    assert infer_majority_ink_color(hits) == "white"


def test_filter_keeps_majority_color_only():
    hits = [
        {"text": "北京", "color_key": "yellow", "score": 0.9},
        {"text": "你比我还讨厌", "color_key": "white", "score": 0.95},
    ]
    kept = filter_hits_by_majority_color(hits, color_key="white")
    assert [h["text"] for h in kept] == ["你比我还讨厌"]


def test_filter_repeat_watermark():
    hits = [
        {"text": "你比我还讨厌", "color_key": "white"},
        {"text": "联系删除", "color_key": "white"},
        {"text": "联系删除", "color_key": "white"},
        {"text": "联系删除", "color_key": "white"},
    ]
    kept = filter_repeat_watermark_hits(hits)
    assert [h["text"] for h in kept] == ["你比我还讨厌"]


def test_filter_up_watermark_without_repeat():
    hits = [
        {"text": "你为什么不能背上来啊", "color_key": "white"},
        {"text": "陶泥小猴子", "color_key": "white"},
        {"text": "陶泥小猴子Do", "color_key": "white"},
    ]
    kept = filter_repeat_watermark_hits(hits)
    assert [h["text"] for h in kept] == ["你为什么不能背上来啊"]


def test_preprocess_upscales_thin_crop():
    import cv2

    thin = np.full((40, 320, 3), 40, dtype=np.uint8)
    cv2.putText(
        thin,
        "test",
        (8, 28),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        (245, 245, 245),
        2,
        cv2.LINE_AA,
    )
    out = _preprocess_subtitle_crop(thin, min_height_px=72)
    assert out.shape[0] >= 72
    assert out.shape[1] >= thin.shape[1]
    canvas = np.full((96, 320, 3), 40, dtype=np.uint8)
    canvas[0:36, :] = _stroke_patch(h=36, w=320)
    canvas[54:90, :] = _bubble_patch(h=36, w=320)
    txts = ("哼", "我爱学习你爱吗别抢遥控器了呀呀")
    scores = (0.95, 0.98)
    boxes = [_box(4, 32), _box(58, 86)]
    hits = [
        {
            "text": str(txts[i]),
            "score": float(scores[i]),
            "white_bg": _box_white_bg_ratio(canvas, boxes[i]),
            "color_key": _box_ink_color_key(canvas, boxes[i]),
        }
        for i in range(len(txts))
    ]
    key = infer_majority_ink_color(hits)
    kept = filter_hits_by_majority_color(hits, color_key=key)
    kept_txts = [str(h["text"]) for h in kept]
    assert len(kept_txts) >= 1
