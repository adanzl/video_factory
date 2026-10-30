"""多数派字色过滤（白底只是特征）。"""

import numpy as np
import pytest

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


def test_materialize_preserves_multicolor_dialogue_and_repeated_short_subtitles():
    from app.services.gold_story.transcript.ocr import materialize_ocr_rows, merge_ocr_rows
    rows = [{"timestamp_sec": i, "hits": [{"text": text, "color_key": color,
             "score": 0.98, "box_h": 36.0}]} for i, (text, color) in enumerate([
                 ("轮到你了吗", "yellow"), ("轮到你了吗", "yellow"),
                 ("还没有", "white"), ("还没有", "white"),
                 ("那我再等一会", "yellow"), ("联系删除", "white"),
             ])]
    result = materialize_ocr_rows(rows, color_key="yellow", min_height_ratio=0.65,
                                  min_dialogue_box_px=22)
    text, _, _ = merge_ocr_rows(result)
    assert text.splitlines() == ["轮到你了吗", "还没有", "那我再等一会"]


def test_repeated_dialogue_is_not_a_watermark():
    hits = [{"text": "知道了", "color_key": "white"}] * 8
    assert filter_repeat_watermark_hits(hits) == hits


@pytest.mark.parametrize("quality", [0.2, 0.9])
def test_ocr_preserves_search_band_even_when_quality_looks_high(monkeypatch, tmp_path, quality):
    from app.config import Config
    from app.services.gold_story.transcript import ocr
    import cv2
    import numpy as np
    cfg = Config()
    cfg.gold_story_ocr_region_detect = True
    cfg.gold_story_ocr_region_search_ratio = 0.5
    original = np.full((540, 960, 3), 180, dtype=np.uint8)
    path = tmp_path / "frame.png"
    cv2.imwrite(str(path), original)
    frames = [ocr.OcrFrame(0, path)]
    calls = []
    def extract(*a, **kw):
        calls.append(kw)
        return frames
    def recognize(frames, config):
        # 窄裁切即使产生高质量分，也不能先破坏送入识别器的字形。
        assert np.array_equal(cv2.imread(str(frames[0].image_path)), original)
        return [{"timestamp_sec": 0, "hits": [{"text": "完整对白", "score": .99,
                "color_key": "white", "box_h": 100}]}]
    monkeypatch.setattr(ocr, "extract_subtitle_frames", extract)
    monkeypatch.setattr(ocr, "ocr_frames_parallel", recognize)
    monkeypatch.setattr(ocr.gs_merge, "score_transcript_text", lambda *a, **kw: quality)
    result = ocr.transcribe_video_ocr(tmp_path / "video.mp4", config=cfg, workspace=tmp_path,
                                    source_id="example", duration_sec=30)
    assert len(calls) == 1
    assert calls[0]["crop_bottom_ratio"] == .5
    assert result["text"] == "完整对白"
    assert result["quality_score"] == quality
    assert result["subtitle_region"]["y_ratio"] == .5
    assert result["subtitle_region"]["h_ratio"] == .5
