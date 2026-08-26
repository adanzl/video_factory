"""H0b 烧录字幕 OCR：抽帧 → 去重 → ProcessPool 并行识别。"""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.config import Config
from . import merge as gs_merge
from .detect import (
    SubtitleRegion,
    detect_burned_subtitles,
    detect_subtitle_region,
    fallback_subtitle_region,
    probe_duration,
)
from app.utils.async_util import wait_futures_hub

logger = logging.getLogger(__name__)

_CJK_IN_LINE = re.compile(r"[\u4e00-\u9fff]")

_OCR_CONFIG_NAME = "rapidocr_gold_story.yaml"
_BACKEND_DIR = Path(__file__).resolve().parents[5]
_OCR_SUBPROCESS_TIMEOUT_SEC = 600.0

_worker_engine = None
_worker_config_path: str | None = None
_worker_model_root: str | None = None
_worker_min_box_height_ratio: float = 0.65
_worker_min_dialogue_box_px: float = 22.0
_worker_min_white_bg_ratio: float = 0.42


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
    min_box_height_ratio: float = 0.65,
    min_dialogue_box_px: float = 22.0,
    min_white_bg_ratio: float = 0.42,
) -> None:
    global _worker_engine, _worker_config_path, _worker_model_root
    global _worker_min_box_height_ratio, _worker_min_dialogue_box_px
    global _worker_min_white_bg_ratio
    _worker_config_path = config_path
    _worker_model_root = model_root_dir
    _worker_min_box_height_ratio = float(min_box_height_ratio)
    _worker_min_dialogue_box_px = float(min_dialogue_box_px)
    _worker_min_white_bg_ratio = float(min_white_bg_ratio)
    from rapidocr import RapidOCR

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
    white_threshold: int = 210,
) -> float:
    """检测 OCR 框周围是否有对白白底气泡（overlay 为描边字，白底占比低）。"""
    try:
        import cv2
    except ImportError:
        return 1.0

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


def _filter_dialogue_boxes(
    image: Any,
    txts: tuple[str, ...] | list[str],
    scores: tuple[float, ...] | list[float],
    boxes: Any,
    *,
    min_white_bg_ratio: float,
) -> tuple[list[str], list[float], list[Any]]:
    """只保留白底气泡风格的对白框，去掉描边 overlay / 解说层。"""
    if boxes is None:
        return list(txts), list(scores), []
    kept_txts: list[str] = []
    kept_scores: list[float] = []
    kept_boxes: list[Any] = []
    box_list = list(boxes)
    for idx, txt in enumerate(txts):
        if idx >= len(box_list):
            break
        if _box_white_bg_ratio(image, box_list[idx]) >= min_white_bg_ratio:
            kept_txts.append(str(txt))
            kept_scores.append(float(scores[idx] if idx < len(scores) else 0.0))
            kept_boxes.append(box_list[idx])
    return kept_txts, kept_scores, kept_boxes


def _read_crop_height(image_path: str) -> float:
    try:
        import cv2
    except ImportError:
        return 0.0
    image = cv2.imread(image_path)
    if image is None:
        return 0.0
    return float(image.shape[0])


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

    注：overlay 描边字在 compose 前已按白底气泡占比过滤。
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
    global _worker_engine
    if _worker_engine is None:
        if not _worker_config_path or not _worker_model_root:
            raise RuntimeError("OCR worker not initialized")
        _init_ocr_worker(_worker_config_path, _worker_model_root)

    timestamp_sec, image_path = args
    result = _worker_engine(str(image_path), use_cls=False)
    if result is None or not getattr(result, "txts", None):
        return {
            "timestamp_sec": timestamp_sec,
            "text": "",
            "confidence": 0.0,
            "lines": [],
        }

    try:
        import cv2
    except ImportError:
        cv2 = None  # type: ignore[assignment]

    crop_h = _read_crop_height(image_path)
    txts = list(result.txts)
    scores = list(result.scores or ())
    boxes = result.boxes
    if cv2 is not None:
        image = cv2.imread(str(image_path))
        if image is not None:
            txts, scores, boxes = _filter_dialogue_boxes(
                image,
                txts,
                scores,
                boxes,
                min_white_bg_ratio=_worker_min_white_bg_ratio,
            )
    if not txts:
        return {
            "timestamp_sec": timestamp_sec,
            "text": "",
            "confidence": 0.0,
            "lines": [],
        }

    text, confidence = compose_frame_text(
        txts,
        scores,
        boxes,
        crop_h=crop_h,
        min_height_ratio=_worker_min_box_height_ratio,
        min_dialogue_box_px=_worker_min_dialogue_box_px,
    )
    lines = [text] if text else []
    return {
        "timestamp_sec": timestamp_sec,
        "text": text,
        "confidence": confidence,
        "lines": lines,
    }


def build_ocr_engine(config: Config):
    """主进程探测用（非 ProcessPool worker）。"""
    from rapidocr import RapidOCR

    cfg_path = ocr_config_path(config)
    model_root = config.ocr_model_dir
    if not model_root.is_dir():
        raise RuntimeError(
            f"OCR model dir not found: {model_root} (set OCR_MODEL_DIR)"
        )
    return RapidOCR(
        config_path=str(cfg_path),
        params={"Global.model_root_dir": str(model_root)},
    )


def extract_subtitle_frames(
    video_path: Path,
    *,
    output_dir: Path,
    fps: float = 2.0,
    region: SubtitleRegion | None = None,
    crop_bottom_ratio: float = 0.10,
    config: Config | None = None,
) -> list[OcrFrame]:
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
    result = subprocess.run(cmd, capture_output=True, encoding="utf-8")
    if result.returncode != 0:
        stderr = (result.stderr or "").strip() or "unknown ffmpeg error"
        raise RuntimeError(f"ffmpeg extract frames failed: {stderr}")

    frames: list[OcrFrame] = []
    for idx, image_path in enumerate(sorted(output_dir.glob("frame_*.jpg")), start=1):
        ts = (idx - 1) / max(fps, 0.1)
        frames.append(OcrFrame(timestamp_sec=ts, image_path=image_path))
    return frames


_DHASH_SIZE = (9, 8)
_DHASH_THRESHOLD = 0


def _frame_dhash(image_path: Path) -> int | None:
    try:
        import cv2
    except ImportError:
        return None
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
    min_h_ratio = float(config.gold_story_ocr_min_box_height_ratio)
    min_box_px = float(config.gold_story_ocr_min_dialogue_box_px)
    min_white_bg = float(config.gold_story_ocr_min_white_bg_ratio)
    workers = max(1, int(config.gold_story_ocr_frame_workers))
    workers = min(workers, len(frames))

    tasks = [(frame.timestamp_sec, str(frame.image_path)) for frame in frames]
    initargs = (cfg_path, model_root, min_h_ratio, min_box_px, min_white_bg)
    if workers <= 1:
        _init_ocr_worker(*initargs)
        return [_ocr_single_frame(task) for task in tasks]

    rows: list[dict[str, Any]] = []
    with ProcessPoolExecutor(
        max_workers=workers,
        initializer=_init_ocr_worker,
        initargs=initargs,
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
    """单视频 OCR 逐字稿（当前进程内执行，供 subprocess worker 调用）。"""
    frame_dir = workspace / "ocr_frames" / source_id
    region_dir = workspace / "ocr_region" / source_id
    if duration_sec is None:
        duration_sec = probe_duration(video_path)

    region = detect_subtitle_region(
        video_path,
        workspace=region_dir,
        duration_sec=duration_sec,
        config=config,
    )
    frames = extract_subtitle_frames(
        video_path,
        output_dir=frame_dir,
        fps=float(config.gold_story_ocr_fps),
        region=region,
        crop_bottom_ratio=float(config.gold_story_ocr_crop_bottom_ratio),
        config=config,
    )
    ocr_rows = ocr_frames_parallel(frames, config)
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
            from app.utils.async_util import _on_gevent_hub, run_subprocess_safe

            if _on_gevent_hub():
                code, stdout, stderr = run_subprocess_safe(
                    cmd,
                    timeout=_OCR_SUBPROCESS_TIMEOUT_SEC,
                    cwd=str(_BACKEND_DIR),
                )
                if code != 0:
                    raise RuntimeError(
                        f"OCR subprocess failed code={code}: "
                        f"{(stderr or stdout or '').strip()}"
                    )
            else:
                proc = subprocess.run(
                    cmd,
                    capture_output=True,
                    encoding="utf-8",
                    cwd=str(_BACKEND_DIR),
                    timeout=_OCR_SUBPROCESS_TIMEOUT_SEC,
                    check=False,
                )
                if proc.returncode != 0:
                    raise RuntimeError(
                        f"OCR subprocess failed code={proc.returncode}: "
                        f"{(proc.stderr or proc.stdout or '').strip()}"
                    )
        except subprocess.TimeoutExpired as exc:
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
