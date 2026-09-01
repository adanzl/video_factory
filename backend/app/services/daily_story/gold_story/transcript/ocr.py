"""H0b 烧录字幕 OCR：一遍抽搜索带 → 同批定带裁切 → ProcessPool 识别。"""

from __future__ import annotations

import json
import logging
import re
import shutil
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from app.config import Config
from . import merge as gs_merge
from .detect import (
    SubtitleRegion,
    detect_burned_subtitles,
    detect_subtitle_region_from_images,
    ensure_ocr_readable_region,
    fallback_subtitle_region,
    probe_duration,
)
from app.utils.async_util import run_subprocess_cmd, wait_futures_hub

logger = logging.getLogger(__name__)

_OCR_CONFIG_NAME = "rapidocr_gold_story.yaml"
_BACKEND_DIR = Path(__file__).resolve().parents[5]
_OCR_SUBPROCESS_TIMEOUT_SEC = 600.0

_worker_engine = None
_worker_config_path: str | None = None
_worker_model_root: str | None = None
_worker_preprocess_min_h: int = 72


@dataclass(frozen=True, slots=True)
class OcrFrame:
    timestamp_sec: float
    image_path: Path


def ocr_config_path(config: Config | None = None) -> Path:
    _ = config
    return Path(__file__).with_name(_OCR_CONFIG_NAME)


def ocr_models_ready(config: Config) -> bool:
    model_dir = config.ocr_model_dir
    if not model_dir.is_dir():
        return False
    return (
        (model_dir / "ch_PP-OCRv4_det_mobile.onnx").is_file()
        and (model_dir / "ch_PP-OCRv4_rec_mobile.onnx").is_file()
    )


def _ffmpeg() -> str:
    path = shutil.which("ffmpeg")
    if not path:
        raise RuntimeError("ffmpeg is required but was not found on PATH")
    return path


def _init_ocr_worker(
    config_path: str,
    model_root_dir: str,
    preprocess_min_h: int = 72,
) -> None:
    global _worker_engine, _worker_config_path, _worker_model_root, _worker_preprocess_min_h
    _worker_config_path = config_path
    _worker_model_root = model_root_dir
    _worker_preprocess_min_h = max(int(preprocess_min_h), 32)
    from rapidocr import RapidOCR  # type: ignore[import-not-found,unused-ignore]

    _worker_engine = RapidOCR(
        config_path=config_path,
        params={"Global.model_root_dir": model_root_dir},
    )


def _box_height(box: Any) -> float:
    ys = [float(point[1]) for point in box]
    return max(ys) - min(ys)


def _box_white_bg_ratio(
    image: Any,
    box: Any,
    *,
    pad: int = 4,
    white_threshold: int = 140,
) -> float:
    """框周亮底占比（特征，不作业务门控）。"""
    xs = [int(point[0]) for point in box]
    ys = [int(point[1]) for point in box]
    x0, x1 = max(0, min(xs)), min(image.shape[1] - 1, max(xs))
    y0, y1 = max(0, min(ys)), min(image.shape[0] - 1, max(ys))
    cy0 = max(0, y0 - pad)
    cy1 = min(image.shape[0], y1 + 1 + pad)
    cx0 = max(0, x0 - pad)
    cx1 = min(image.shape[1], x1 + 1 + pad)
    patch = image[cy0:cy1, cx0:cx1]
    if patch.size == 0:
        return 0.0
    gray = cv2.cvtColor(patch, cv2.COLOR_BGR2GRAY)
    return float((gray > white_threshold).mean())


def _box_ink_color_key(image: Any, box: Any) -> str:
    """粗粒度字色：white / yellow / black / other（笔画亮部主色）。"""
    xs = [int(point[0]) for point in box]
    ys = [int(point[1]) for point in box]
    x0, x1 = max(0, min(xs)), min(image.shape[1] - 1, max(xs))
    y0, y1 = max(0, min(ys)), min(image.shape[0] - 1, max(ys))
    if x1 <= x0 or y1 <= y0:
        return "other"
    patch = image[y0 : y1 + 1, x0 : x1 + 1]
    if patch.size == 0:
        return "other"
    gray = cv2.cvtColor(patch, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV)
    # 亮笔画（白/黄描边字）；若整体偏暗则看暗笔画（黑字）
    bright_thr = float(np.percentile(gray, 80))
    bright = gray >= max(bright_thr, 140)
    if float(bright.mean()) >= 0.03:
        h = hsv[:, :, 0][bright]
        s = hsv[:, :, 1][bright]
        v = hsv[:, :, 2][bright]
    else:
        dark = gray <= min(float(np.percentile(gray, 25)), 90)
        if float(dark.mean()) < 0.03:
            return "other"
        h = hsv[:, :, 0][dark]
        s = hsv[:, :, 1][dark]
        v = hsv[:, :, 2][dark]
        if float(np.median(v)) <= 90:
            return "black"
        return "other"

    med_h = float(np.median(h))
    med_s = float(np.median(s))
    med_v = float(np.median(v))
    if med_v < 90:
        return "black"
    if med_s >= 50 and 12 <= med_h <= 45:
        return "yellow"
    if med_v >= 150 and med_s <= 90:
        return "white"
    return "other"


def infer_majority_ink_color(
    hits: list[dict[str, Any]],
) -> str:
    """全片字数加权，多数派字色 = 对白颜色。"""
    weights: dict[str, int] = {}
    for hit in hits:
        text = str(hit.get("text") or "").strip()
        if not text:
            continue
        key = str(hit.get("color_key") or "other")
        weights[key] = weights.get(key, 0) + max(len(text), 1)
    if not weights:
        return "white"
    return max(weights.items(), key=lambda kv: kv[1])[0]


def filter_hits_by_majority_color(
    hits: list[dict[str, Any]],
    *,
    color_key: str,
) -> list[dict[str, Any]]:
    return [
        hit
        for hit in hits
        if str(hit.get("color_key") or "other") == str(color_key)
    ]


_WATERMARK_RE = re.compile(
    r"(联系删除|如有侵权|侵权|来源[:：]|糖小果|陶泥|小猴子|bilibili)",
    re.IGNORECASE,
)


def _preprocess_subtitle_crop(
    image: Any,
    *,
    min_height_px: int = 72,
) -> Any:
    """薄裁切 + 描边字：放大并轻度锐化，提升 mobile OCR 可读性。"""
    if image is None or getattr(image, "size", 0) == 0:
        return image
    h, w = image.shape[:2]
    out = image
    target = max(int(min_height_px), 1)
    if h < target:
        scale = target / max(h, 1)
        new_w = max(int(w * scale), w)
        new_h = max(int(h * scale), target)
        out = cv2.resize(out, (new_w, new_h), interpolation=cv2.INTER_CUBIC)
    blurred = cv2.GaussianBlur(out, (0, 0), 1.0)
    return cv2.addWeighted(out, 1.35, blurred, -0.35, 0)


def filter_repeat_watermark_hits(
    hits: list[dict[str, Any]],
    *,
    min_repeat: int = 4,
) -> list[dict[str, Any]]:
    """同色后的二次过滤：短且反复出现的水印/来源字当噪点删。"""
    from collections import Counter

    counts = Counter(
        str(h.get("text") or "").strip()
        for h in hits
        if str(h.get("text") or "").strip()
    )
    out: list[dict[str, Any]] = []
    for hit in hits:
        text = str(hit.get("text") or "").strip()
        if not text:
            continue
        if _WATERMARK_RE.search(text):
            continue
        if len(text) <= 8 and counts[text] >= max(2, int(min_repeat) - 2):
            continue
        if len(text) <= 6 and counts[text] >= int(min_repeat):
            continue
        out.append(hit)
    return out


def infer_video_subtitle_fill_style(
    hits: list[dict[str, Any]],
    *,
    bubble_min: float = 0.42,
) -> str:
    """兼容旧名：由多数派字色映射粗风格（调试用）。"""
    key = infer_majority_ink_color(hits)
    if key == "black":
        # 黑字多见于白底气泡
        lit = sum(
            max(len(str(h.get("text") or "")), 1)
            for h in hits
            if str(h.get("color_key")) == "black"
            and float(h.get("white_bg") or 0) >= float(bubble_min)
        )
        return "bubble" if lit > 0 else "stroke"
    return "stroke"


def compose_frame_text(
    txts: tuple[str, ...] | list[str],
    scores: tuple[float, ...] | list[float],
    boxes: Any,
    *,
    crop_h: float = 0.0,
    min_height_ratio: float = 0.65,
    min_dialogue_box_px: float = 22.0,
) -> tuple[str, float]:
    """单帧多行 OCR：去掉小字号说明，拼成一行（无换行）。

    注：颜色筛选在片级 materialize_ocr_rows 完成后再 compose。
    """
    _ = crop_h
    box_list = list(boxes) if boxes is not None else []
    items: list[tuple[str, float, float]] = []
    for idx, txt in enumerate(txts):
        line = str(txt or "").strip()
        if not line:
            continue
        score = float(scores[idx] if idx < len(scores) else 0.0)
        box_h = _box_height(box_list[idx]) if idx < len(box_list) else 0.0
        items.append((line, score, box_h))

    if not items:
        return "", 0.0

    if len(items) == 1:
        line, score, box_h = items[0]
        if box_h > 0 and box_h < min_dialogue_box_px:
            return "", 0.0
        return line, score

    heights = [box_h for _, _, box_h in items if box_h > 0]
    frame_max_h = max(heights) if heights else 0.0
    threshold = frame_max_h * min_height_ratio if frame_max_h > 0 else 0.0

    kept: list[tuple[str, float]] = []
    for line, score, box_h in items:
        if threshold > 0 and box_h > 0 and box_h < threshold:
            continue
        kept.append((line, score))

    if not kept:
        return "", 0.0

    text = "".join(line for line, _ in kept)
    confidence = sum(score for _, score in kept) / len(kept)
    return text, confidence


def _ocr_single_frame(args: tuple[float, str]) -> dict[str, Any]:
    """单帧 OCR：只产出候选 hit（含 white_bg），不做片级颜色过滤。"""
    global _worker_engine
    if _worker_engine is None:
        if not _worker_config_path or not _worker_model_root:
            raise RuntimeError("OCR worker not initialized")
        _init_ocr_worker(_worker_config_path, _worker_model_root)

    timestamp_sec, image_path = args
    image = cv2.imread(str(image_path))
    if image is not None:
        proc = _preprocess_subtitle_crop(
            image,
            min_height_px=_worker_preprocess_min_h,
        )
        cv2.imwrite(str(image_path), proc)

    result = _worker_engine(str(image_path), use_cls=False)  # type: ignore[operator]
    empty = {
        "timestamp_sec": timestamp_sec,
        "hits": [],
        "text": "",
        "confidence": 0.0,
        "lines": [],
    }
    txts = getattr(result, "txts", None)
    if result is None or not txts:
        return empty

    image = cv2.imread(str(image_path))

    txt_list = list(txts)
    scores = list(getattr(result, "scores", None) or ())
    boxes_raw = getattr(result, "boxes", None)
    boxes = list(boxes_raw) if boxes_raw is not None else []
    hits: list[dict[str, Any]] = []
    for idx, txt in enumerate(txt_list):
        text = str(txt or "").strip()
        if not text:
            continue
        box = boxes[idx] if idx < len(boxes) else None
        white_bg = 0.0
        box_h = 0.0
        color_key = "other"
        if box is not None:
            box_h = _box_height(box)
            if image is not None:
                white_bg = _box_white_bg_ratio(image, box)
                color_key = _box_ink_color_key(image, box)
        hits.append(
            {
                "text": text,
                "score": float(scores[idx] if idx < len(scores) else 0.0),
                "white_bg": float(white_bg),
                "color_key": color_key,
                "box_h": float(box_h),
            }
        )
    return {
        "timestamp_sec": timestamp_sec,
        "hits": hits,
        "text": "",
        "confidence": 0.0,
        "lines": [],
    }


def materialize_ocr_rows(
    raw_rows: list[dict[str, Any]],
    *,
    color_key: str,
    min_height_ratio: float,
    min_dialogue_box_px: float,
) -> list[dict[str, Any]]:
    """片级多数派字色 + 水印二次过滤后，压成 merge 可用行。"""
    all_colored: list[dict[str, Any]] = []
    for row in raw_rows:
        all_colored.extend(
            filter_hits_by_majority_color(
                list(row.get("hits") or []),
                color_key=color_key,
            )
        )
    allowed_texts = {
        str(h.get("text") or "").strip()
        for h in filter_repeat_watermark_hits(all_colored)
        if str(h.get("text") or "").strip()
    }

    out: list[dict[str, Any]] = []
    for row in raw_rows:
        hits = [
            hit
            for hit in filter_hits_by_majority_color(
                list(row.get("hits") or []),
                color_key=color_key,
            )
            if str(hit.get("text") or "").strip() in allowed_texts
        ]
        if not hits:
            out.append(
                {
                    "timestamp_sec": row.get("timestamp_sec"),
                    "text": "",
                    "confidence": 0.0,
                    "lines": [],
                }
            )
            continue
        txt_list = [str(h["text"]) for h in hits]
        scores = [float(h["score"]) for h in hits]
        boxes = [
            [
                [0.0, 0.0],
                [10.0, 0.0],
                [10.0, float(h["box_h"])],
                [0.0, float(h["box_h"])],
            ]
            for h in hits
        ]
        text, confidence = compose_frame_text(
            txt_list,
            scores,
            boxes,
            min_height_ratio=min_height_ratio,
            min_dialogue_box_px=min_dialogue_box_px,
        )
        out.append(
            {
                "timestamp_sec": row.get("timestamp_sec"),
                "text": text,
                "confidence": confidence,
                "lines": [text] if text else [],
                "hits": hits,
            }
        )
    return out


def extract_subtitle_frames(
    video_path: Path,
    *,
    output_dir: Path,
    fps: float = 2.0,
    region: SubtitleRegion | None = None,
    crop_bottom_ratio: float = 0.10,
    config: Config | None = None,
) -> list[OcrFrame]:
    """ffmpeg 抽帧一次。OCR 主路径传底部搜索带 ratio，不定最终字幕带。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    for old in output_dir.glob("frame_*.jpg"):
        old.unlink(missing_ok=True)

    cfg = config or Config()
    if region is not None:
        max_h = float(cfg.gold_story_ocr_region_max_h_ratio)
        vf = f"fps={fps},{region.crop_vf_expr(max_h_ratio=max_h)}"
    else:
        crop_y = 1.0 - crop_bottom_ratio
        vf = f"fps={fps},crop=iw:ih*{crop_bottom_ratio}:0:ih*{crop_y}"
    pattern = output_dir / "frame_%06d.jpg"
    cmd = [
        _ffmpeg(),
        "-y",
        "-i",
        str(video_path),
        "-vf",
        vf,
        str(pattern),
    ]
    run_subprocess_cmd(cmd, check=True)

    frames: list[OcrFrame] = []
    for idx, image_path in enumerate(sorted(output_dir.glob("frame_*.jpg")), start=1):
        ts = (idx - 1) / max(fps, 0.1)
        frames.append(OcrFrame(timestamp_sec=ts, image_path=image_path))
    return frames


def crop_search_band_frames_to_region(
    frames: list[OcrFrame],
    region: SubtitleRegion,
    *,
    search_band_top_ratio: float,
    config: Config | None = None,
) -> list[OcrFrame]:
    """将搜索带帧就地裁成定带结果（不再二次 ffmpeg）。"""
    if not frames:
        return []
    cfg = config or Config()

    band_top = max(0.0, min(float(search_band_top_ratio), 0.98))
    search_ratio = max(1.0 - band_top, 0.05)
    ocr_floor = float(cfg.gold_story_ocr_region_ocr_floor_h_ratio)
    clamped = ensure_ocr_readable_region(
        region,
        min_h_ratio=ocr_floor,
        max_h_ratio=float(cfg.gold_story_ocr_region_max_h_ratio),
    )
    local_y = (float(clamped.y_ratio) - band_top) / search_ratio
    local_h = float(clamped.h_ratio) / search_ratio
    local_y = max(0.0, min(local_y, 0.98))
    local_min_h = max(ocr_floor / search_ratio, 0.04)
    local_h = max(local_min_h, min(local_h, 1.0 - local_y))

    kept: list[OcrFrame] = []
    for frame in frames:
        img = cv2.imread(str(frame.image_path))
        if img is None:
            continue
        h = int(img.shape[0])
        y0 = int(round(h * local_y))
        y1 = int(round(h * (local_y + local_h)))
        y0 = max(0, min(y0, h - 1))
        y1 = max(y0 + 1, min(y1, h))
        crop = img[y0:y1, :]
        if crop.size == 0:
            continue
        cv2.imwrite(str(frame.image_path), crop)
        kept.append(frame)
    return kept


_DHASH_SIZE = (9, 8)
_DHASH_THRESHOLD = 0


def _frame_dhash(image_path: Path) -> int | None:
    gray = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
    if gray is None:
        return None
    small = cv2.resize(gray, _DHASH_SIZE, interpolation=cv2.INTER_AREA)
    diff = small[:, 1:] > small[:, :-1]
    value = 0
    for bit in diff.flatten():
        value = (value << 1) | int(bit)
    return value


def _hamming_distance(a: int, b: int) -> int:
    return int((a ^ b).bit_count())


def _subsample_uniform(frames: list[OcrFrame], max_frames: int) -> list[OcrFrame]:
    if len(frames) <= max_frames:
        return frames
    cap = max(2, int(max_frames))
    last_idx = len(frames) - 1
    picked: list[OcrFrame] = []
    seen: set[int] = set()
    for slot in range(cap):
        idx = round(slot * last_idx / (cap - 1))
        if idx in seen:
            continue
        seen.add(idx)
        picked.append(frames[idx])
    return picked


def dedupe_frames(
    frames: list[OcrFrame],
    *,
    max_frames: int = 80,
) -> list[OcrFrame]:
    """字幕静止时合并相邻帧；超长片再均匀抽样至上限。"""
    if not frames:
        return []
    if len(frames) == 1:
        return frames

    cap = max(2, int(max_frames))
    kept: list[OcrFrame] = [frames[0]]
    last_hash = _frame_dhash(frames[0].image_path)
    use_hash = last_hash is not None

    for frame in frames[1:-1]:
        if not use_hash:
            kept.append(frame)
            continue
        current = _frame_dhash(frame.image_path)
        if current is None:
            kept.append(frame)
            last_hash = None
            use_hash = False
            continue
        if last_hash is None or _hamming_distance(last_hash, current) > _DHASH_THRESHOLD:
            kept.append(frame)
            last_hash = current

    if frames[-1] is not kept[-1]:
        kept.append(frames[-1])

    return _subsample_uniform(kept, cap)


def _iter_row_texts(row: dict[str, Any]) -> list[str]:
    """每帧一行（帧内多行 OCR 已在 compose_frame_text 合并）。"""
    text = str(row.get("text") or "").strip()
    return [text] if text else []


def merge_ocr_rows(rows: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]], float]:
    """OCR 原样输出，仅去掉相邻重复行。"""
    merged_lines: list[dict[str, Any]] = []
    plain_parts: list[str] = []
    confidences: list[float] = []

    for row in sorted(rows, key=lambda r: float(r.get("timestamp_sec") or 0.0)):
        ts = float(row.get("timestamp_sec") or 0.0)
        conf = float(row.get("confidence") or 0.0)
        for text in _iter_row_texts(row):
            if merged_lines and gs_merge.texts_similar(
                merged_lines[-1].get("text") or "",
                text,
            ):
                merged_lines[-1]["end_sec"] = ts
                merged_lines[-1]["confidence"] = max(
                    float(merged_lines[-1].get("confidence") or 0.0),
                    conf,
                )
                continue
            merged_lines.append(
                {
                    "timestamp_sec": ts,
                    "end_sec": ts,
                    "speaker": None,
                    "text": text,
                    "confidence": conf,
                }
            )
            plain_parts.append(text)
            confidences.append(conf)

    plain = "\n".join(plain_parts).strip()
    avg_conf = sum(confidences) / len(confidences) if confidences else 0.0
    return plain, merged_lines, avg_conf


def ocr_frames_parallel(
    frames: list[OcrFrame],
    config: Config,
) -> list[dict[str, Any]]:
    if not frames:
        return []

    cfg_path = str(ocr_config_path(config))
    model_root = str(config.ocr_model_dir)
    workers = max(1, int(config.gold_story_ocr_frame_workers))
    workers = min(workers, len(frames))

    tasks = [(frame.timestamp_sec, str(frame.image_path)) for frame in frames]
    init_args = (
        cfg_path,
        model_root,
        int(config.gold_story_ocr_preprocess_min_height_px),
    )
    if workers <= 1:
        _init_ocr_worker(*init_args)
        return [_ocr_single_frame(task) for task in tasks]

    rows: list[dict[str, Any]] = []
    with ProcessPoolExecutor(
        max_workers=workers,
        initializer=_init_ocr_worker,
        initargs=init_args,
    ) as pool:
        futures = [pool.submit(_ocr_single_frame, task) for task in tasks]
        for future in wait_futures_hub(futures):
            rows.append(future.result())
    return rows


def transcribe_video_ocr(
    video_path: Path,
    *,
    config: Config,
    workspace: Path,
    source_id: str,
    title: str = "",
    duration_sec: float | None = None,
) -> dict[str, Any]:
    """单视频 OCR 逐字稿（视频只解码一遍）。

    流程：
    1) ffmpeg 抽底部搜索带帧（一次）
    2) 同批帧定字幕带 → 就地裁切
    3) OCR → 多数派字色过滤 → merge
    """
    frame_dir = workspace / "ocr_frames" / source_id
    if duration_sec is None:
        duration_sec = probe_duration(video_path)

    search_ratio = float(config.gold_story_ocr_region_search_ratio)
    search_ratio = max(0.15, min(search_ratio, 0.55))
    search_band_top = 1.0 - search_ratio

    # 1) 一遍抽帧：底部搜索带（比最终字幕带宽，留给定带）
    frames = extract_subtitle_frames(
        video_path,
        output_dir=frame_dir,
        fps=float(config.gold_story_ocr_fps),
        region=None,
        crop_bottom_ratio=search_ratio,
        config=config,
    )
    if config.gold_story_ocr_region_detect and frames:
        region = detect_subtitle_region_from_images(
            [f.image_path for f in frames],
            config=config,
            search_band_top_ratio=search_band_top,
            max_samples=10,
            log_tag=source_id,
        )
    else:
        region = fallback_subtitle_region(config)
    region = ensure_ocr_readable_region(
        region,
        min_h_ratio=float(config.gold_story_ocr_region_ocr_floor_h_ratio),
        max_h_ratio=float(config.gold_story_ocr_region_max_h_ratio),
    )
    if frames:
        frames = crop_search_band_frames_to_region(
            frames,
            region,
            search_band_top_ratio=search_band_top,
            config=config,
        )

    # 1.5) 去重相邻静止帧，再按上限均匀抽样
    max_frames = int(config.gold_story_ocr_max_frames)
    frames = dedupe_frames(frames, max_frames=max_frames)

    # 2) 全片 OCR 候选（先不过滤）
    raw_rows = ocr_frames_parallel(frames, config)
    all_hits: list[dict[str, Any]] = []
    for row in raw_rows:
        all_hits.extend(list(row.get("hits") or []))

    # 3) 多数派字色 + 水印二次过滤
    color_key = infer_majority_ink_color(all_hits)
    ocr_rows = materialize_ocr_rows(
        raw_rows,
        color_key=color_key,
        min_height_ratio=float(config.gold_story_ocr_min_box_height_ratio),
        min_dialogue_box_px=float(config.gold_story_ocr_min_dialogue_box_px),
    )
    text, line_rows, avg_conf = merge_ocr_rows(ocr_rows)

    quality = gs_merge.score_transcript_text(
        text,
        title=title,
        duration_sec=float(duration_sec or 0.0),
        avg_confidence=avg_conf,
    )
    return {
        "text": text,
        "lines": line_rows,
        "segments": line_rows,
        "engine": "rapidocr",
        "model": "PP-OCRv4_mobile",
        "source": "ocr",
        "avg_confidence": avg_conf,
        "quality_score": quality,
        "frame_count": len(frames),
        "ocr_frame_dir": str(frame_dir),
        "subtitle_color_key": color_key,
        "subtitle_fill_style": infer_video_subtitle_fill_style(all_hits),
        "subtitle_region": {
            "y_ratio": region.y_ratio,
            "h_ratio": region.h_ratio,
            "method": region.method,
            "samples": region.samples,
            "confidence": region.confidence,
        },
    }


def should_skip_asr_after_ocr(ocr_result: dict[str, Any], config: Config) -> bool:
    text = str(ocr_result.get("text") or "").strip()
    if not text:
        return False
    quality = float(ocr_result.get("quality_score") or 0.0)
    return quality >= float(config.gold_story_ocr_skip_asr_min)


def _run_ocr_worker(input_path: Path, output_path: Path) -> None:
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    cfg = Config()
    if payload.get("ocr_model_dir"):
        cfg.ocr_model_dir = Path(str(payload["ocr_model_dir"]))
    if payload.get("gold_story_ocr_fps") is not None:
        cfg.gold_story_ocr_fps = float(payload["gold_story_ocr_fps"])
    if payload.get("gold_story_ocr_frame_workers") is not None:
        cfg.gold_story_ocr_frame_workers = int(payload["gold_story_ocr_frame_workers"])

    result = transcribe_video_ocr(
        Path(str(payload["video_path"])),
        config=cfg,
        workspace=Path(str(payload["workspace"])),
        source_id=str(payload["source_id"]),
        title=str(payload.get("title") or ""),
        duration_sec=payload.get("duration_sec"),
    )
    output_path.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")


def transcribe_video_ocr_subprocess(
    video_path: Path,
    *,
    config: Config,
    workspace: Path,
    source_id: str,
    title: str = "",
    duration_sec: float | None = None,
) -> dict[str, Any]:
    """子进程隔离 OCR，避免与 Whisper/GPU 同进程 segfault。"""
    if not ocr_models_ready(config):
        raise RuntimeError(
            f"OCR model dir not ready: {config.ocr_model_dir} (set OCR_MODEL_DIR)"
        )

    payload = {
        "video_path": str(video_path),
        "workspace": str(workspace),
        "source_id": source_id,
        "title": title,
        "duration_sec": duration_sec,
        "ocr_model_dir": str(config.ocr_model_dir),
        "gold_story_ocr_fps": config.gold_story_ocr_fps,
        "gold_story_ocr_frame_workers": config.gold_story_ocr_frame_workers,
    }
    module = "app.services.daily_story.gold_story.transcript.ocr"
    with tempfile.TemporaryDirectory(prefix="gold_story_ocr_") as tmp:
        input_path = Path(tmp) / "input.json"
        output_path = Path(tmp) / "output.json"
        input_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        cmd = [
            sys.executable,
            "-m",
            module,
            "--worker",
            str(input_path),
            str(output_path),
        ]
        logger.info(
            "gold_story OCR subprocess bvid=%s workers=%s",
            source_id,
            config.gold_story_ocr_frame_workers,
        )
        try:
            run_subprocess_cmd(
                cmd,
                timeout=_OCR_SUBPROCESS_TIMEOUT_SEC,
                cwd=str(_BACKEND_DIR),
                check=True,
            )
        except TimeoutError as exc:
            raise TimeoutError(
                f"OCR subprocess timed out after {_OCR_SUBPROCESS_TIMEOUT_SEC}s"
            ) from exc

        if not output_path.is_file():
            raise RuntimeError("OCR subprocess produced no output")
        data = json.loads(output_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise RuntimeError("OCR subprocess returned invalid payload")
        return data


def should_try_ocr(video_path: Path, *, config: Config, workspace: Path) -> bool:
    if not config.gold_story_ocr_enabled:
        return False
    if not ocr_models_ready(config):
        logger.warning("OCR models not ready under %s", config.ocr_model_dir)
        return False
    try:
        return detect_burned_subtitles(
            video_path,
            workspace=workspace / "ocr_detect",
            config=config,
        )
    except Exception as exc:
        logger.warning("subtitle detect failed, skip OCR: %s", exc)
        return False


def _cli_worker() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="gold_story OCR subprocess worker")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("input_json")
    parser.add_argument("output_json")
    args = parser.parse_args()
    if not args.worker:
        parser.error("missing --worker")
    _run_ocr_worker(Path(args.input_json), Path(args.output_json))
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli_worker())
