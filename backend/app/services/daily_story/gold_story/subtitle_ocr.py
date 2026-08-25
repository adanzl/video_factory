"""H0b 烧录字幕 OCR：抽帧 → 去重 → ProcessPool 并行识别。"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
from concurrent.futures import Future, ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.config import Config
from app.services.daily_story.gold_story import transcript_merge as gs_merge

_CJK_IN_LINE = re.compile(r"[\u4e00-\u9fff]")
from app.services.daily_story.gold_story.subtitle_detect import detect_burned_subtitles
from app.utils.async_util import wait_futures_hub

logger = logging.getLogger(__name__)

_SPEAKER_LINE_RE = re.compile(r"^([^：:]{1,8})[：:]\s*(.+)$")
_OVERLAY_LINE_RES = (
    re.compile(r"近日"),
    re.compile(r"素材来源"),
    re.compile(r"应来自"),
    re.compile(r"网邮|内发极来"),
    re.compile(r"令人哭笑不得"),
    re.compile(r"一招制"),
    re.compile(r"舌头授"),
    re.compile(r"^[+＋]\s"),
)
_SINGLE_CHAR_RE = re.compile(r"^[A-Za-z0-9]$")
_OCR_CONFIG_NAME = "rapidocr_gold_story.yaml"

_worker_engine = None
_worker_config_path: str | None = None
_worker_model_root: str | None = None


@dataclass(frozen=True, slots=True)
class OcrFrame:
    timestamp_sec: float
    image_path: Path


def ocr_config_path(config: Config | None = None) -> Path:
    _ = config
    return Path(__file__).with_name(_OCR_CONFIG_NAME)


def _ffmpeg() -> str:
    path = shutil.which("ffmpeg")
    if not path:
        raise RuntimeError("ffmpeg is required but was not found on PATH")
    return path


def _init_ocr_worker(config_path: str, model_root_dir: str) -> None:
    global _worker_engine, _worker_config_path, _worker_model_root
    _worker_config_path = config_path
    _worker_model_root = model_root_dir
    from rapidocr import RapidOCR

    _worker_engine = RapidOCR(
        config_path=config_path,
        params={"Global.model_root_dir": model_root_dir},
    )


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

    parts: list[str] = []
    scores: list[float] = []
    for txt, score in zip(result.txts, result.scores or ()):
        line = str(txt or "").strip()
        if not line:
            continue
        parts.append(line)
        scores.append(float(score or 0.0))

    text = " ".join(parts).strip()
    confidence = sum(scores) / len(scores) if scores else 0.0
    return {
        "timestamp_sec": timestamp_sec,
        "text": text,
        "confidence": confidence,
        "lines": parts,
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
    crop_bottom_ratio: float = 0.20,
) -> list[OcrFrame]:
    output_dir.mkdir(parents=True, exist_ok=True)
    for old in output_dir.glob("frame_*.jpg"):
        old.unlink(missing_ok=True)

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


def dedupe_frames(frames: list[OcrFrame]) -> list[OcrFrame]:
    """相邻帧保留代表帧，降低 OCR 次数。"""
    if not frames:
        return []
    kept: list[OcrFrame] = [frames[0]]
    step = max(len(frames) // 80, 1)
    for idx in range(1, len(frames)):
        if idx % step != 0 and idx != len(frames) - 1:
            continue
        kept.append(frames[idx])
    return kept


def _is_overlay_line(text: str) -> bool:
    line = str(text or "").strip()
    if not line:
        return True
    if _SINGLE_CHAR_RE.match(line):
        return True
    if len(line) <= 2 and not _CJK_IN_LINE.search(line):
        return True
    if len(line) > 36 and "：" not in line and ":" not in line:
        return True
    return any(pat.search(line) for pat in _OVERLAY_LINE_RES)


def _clean_ocr_fragment(text: str) -> str:
    line = str(text or "").strip()
    for prefix in ("连环追问", "素材来源", "近日"):
        if line.startswith(prefix):
            line = line[len(prefix) :].strip()
    return line.strip()


def _parse_speaker_line(text: str) -> tuple[str | None, str]:
    match = _SPEAKER_LINE_RE.match(str(text or "").strip())
    if not match:
        return None, str(text or "").strip()
    speaker = match.group(1).strip()
    body = match.group(2).strip()
    return speaker, body


def merge_ocr_rows(rows: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]], float]:
    """按时间合并 OCR 行，去重相邻相同字幕。"""
    ordered = sorted(rows, key=lambda r: float(r.get("timestamp_sec") or 0.0))
    merged_lines: list[dict[str, Any]] = []
    plain_parts: list[str] = []
    confidences: list[float] = []

    for row in ordered:
        text = _clean_ocr_fragment(str(row.get("text") or "").strip())
        if not text or _is_overlay_line(text):
            continue
        conf = float(row.get("confidence") or 0.0)
        if merged_lines and gs_merge.texts_similar(
            merged_lines[-1].get("text") or "",
            text,
        ):
            merged_lines[-1]["end_sec"] = float(row.get("timestamp_sec") or 0.0)
            merged_lines[-1]["confidence"] = max(
                float(merged_lines[-1].get("confidence") or 0.0),
                conf,
            )
            continue

        speaker, body = _parse_speaker_line(text)
        line_text = f"{speaker}：{body}" if speaker else text
        merged_lines.append(
            {
                "timestamp_sec": float(row.get("timestamp_sec") or 0.0),
                "end_sec": float(row.get("timestamp_sec") or 0.0),
                "speaker": speaker,
                "text": line_text,
                "confidence": conf,
            }
        )
        plain_parts.append(body if speaker else text)
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
    if workers <= 1:
        _init_ocr_worker(cfg_path, model_root)
        return [_ocr_single_frame(task) for task in tasks]

    rows: list[dict[str, Any]] = []
    with ProcessPoolExecutor(
        max_workers=workers,
        initializer=_init_ocr_worker,
        initargs=(cfg_path, model_root),
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
    """单视频 OCR 逐字稿。"""
    frame_dir = workspace / "ocr_frames" / source_id
    frames = extract_subtitle_frames(
        video_path,
        output_dir=frame_dir,
        fps=float(config.gold_story_ocr_fps),
    )
    sample_frames = dedupe_frames(frames)
    ocr_rows = ocr_frames_parallel(sample_frames, config)
    text, line_rows, avg_conf = merge_ocr_rows(ocr_rows)

    if duration_sec is None:
        from app.services.daily_story.gold_story.subtitle_detect import _probe_duration

        duration_sec = _probe_duration(video_path)

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
        "frame_count": len(sample_frames),
        "ocr_frame_dir": str(frame_dir),
    }


def should_try_ocr(video_path: Path, *, config: Config, workspace: Path) -> bool:
    if not config.gold_story_ocr_enabled:
        return False
    try:
        build_ocr_engine(config)
    except Exception as exc:
        logger.warning("OCR unavailable: %s", exc)
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
