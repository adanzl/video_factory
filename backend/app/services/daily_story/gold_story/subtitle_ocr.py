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
from app.services.daily_story.gold_story import transcript_merge as gs_merge
from app.services.daily_story.gold_story.subtitle_detect import (
    SubtitleRegion,
    detect_burned_subtitles,
    detect_subtitle_region,
    fallback_subtitle_region,
    probe_duration,
)
from app.utils.async_util import wait_futures_hub

logger = logging.getLogger(__name__)

_CJK_IN_LINE = re.compile(r"[\u4e00-\u9fff]")

_SPEAKER_LINE_RE = re.compile(r"^([^：:]{1,8})[：:]\s*(.+)$")
_PURE_OVERLAY_FRAGMENT_RES = (
    re.compile(r"素材来源"),
    re.compile(r"应来自"),
    re.compile(r"网邮|内发极来"),
    re.compile(r"令人哭笑不得"),
    re.compile(r"^一双儿女"),
    re.compile(r"^舌头[授授摇捋]"),
    re.compile(r"^姐姐一招制"),
    re.compile(r"^[+＋]\s"),
)
_GARBAGE_FRAGMENT_RES = (
    re.compile(r"^[A-Za-z0-9]$"),
    re.compile(r"^D\s*\d*$"),
    re.compile(r"^[A-Za-z0-9\s]{1,3}$"),
)
_TRAILING_NOISE_RES = (
    re.compile(r"[品口]+$"),
    re.compile(r"\s+[你尚]?说[王注尚]+$"),
    re.compile(r"\s+素材来源.*$"),
)
_SINGLE_CHAR_RE = re.compile(r"^[A-Za-z0-9]$")
_OCR_CONFIG_NAME = "rapidocr_gold_story.yaml"
_BACKEND_DIR = Path(__file__).resolve().parents[4]
_OCR_SUBPROCESS_TIMEOUT_SEC = 600.0

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
    region: SubtitleRegion | None = None,
    crop_bottom_ratio: float = 0.10,
) -> list[OcrFrame]:
    output_dir.mkdir(parents=True, exist_ok=True)
    for old in output_dir.glob("frame_*.jpg"):
        old.unlink(missing_ok=True)

    if region is not None:
        vf = f"fps={fps},{region.crop_vf_expr()}"
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
_DHASH_THRESHOLD = 5


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


def _sanitize_dialogue_fragment(text: str) -> str:
    line = str(text or "").strip()
    for prefix in ("连环追问", "近日"):
        if line.startswith(prefix):
            line = line[len(prefix) :].strip()
    for pat in _TRAILING_NOISE_RES:
        line = pat.sub("", line).strip()
    return line.strip()


def _is_pure_overlay_fragment(text: str) -> bool:
    line = str(text or "").strip()
    if not line:
        return True
    return any(pat.search(line) for pat in _PURE_OVERLAY_FRAGMENT_RES)


def _is_garbage_fragment(text: str) -> bool:
    line = str(text or "").strip()
    if not line:
        return True
    if _SINGLE_CHAR_RE.match(line):
        return True
    if any(pat.match(line) for pat in _GARBAGE_FRAGMENT_RES):
        return True
    if len(line) <= 2 and not _CJK_IN_LINE.search(line):
        return True
    cjk_count = len(_CJK_IN_LINE.findall(line))
    if len(line) <= 4 and cjk_count == 0:
        return True
    return False


def _is_overlay_line(text: str) -> bool:
    """兼容诊断脚本：整行是否应视为纯解说/垃圾。"""
    line = _sanitize_dialogue_fragment(str(text or "").strip())
    if not line:
        return True
    return _is_pure_overlay_fragment(line) or _is_garbage_fragment(line)


def _expand_row_fragments(row: dict[str, Any]) -> list[dict[str, Any]]:
    ts = float(row.get("timestamp_sec") or 0.0)
    conf = float(row.get("confidence") or 0.0)
    raw_lines = row.get("lines") or []
    if not raw_lines:
        text = str(row.get("text") or "").strip()
        if text:
            raw_lines = [text]
    out: list[dict[str, Any]] = []
    for raw in raw_lines:
        frag = _sanitize_dialogue_fragment(str(raw or "").strip())
        if not frag or _is_garbage_fragment(frag) or _is_pure_overlay_fragment(frag):
            continue
        out.append(
            {
                "timestamp_sec": ts,
                "text": frag,
                "confidence": conf,
            }
        )
    return out


def _clean_ocr_fragment(text: str) -> str:
    return _sanitize_dialogue_fragment(text)


def _parse_speaker_line(text: str) -> tuple[str | None, str]:
    match = _SPEAKER_LINE_RE.match(str(text or "").strip())
    if not match:
        return None, str(text or "").strip()
    speaker = match.group(1).strip()
    body = match.group(2).strip()
    return speaker, body


def merge_ocr_rows(rows: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]], float]:
    """按时间合并 OCR 片段，去重相邻相同字幕。"""
    fragments: list[dict[str, Any]] = []
    for row in rows:
        fragments.extend(_expand_row_fragments(row))
    ordered = sorted(fragments, key=lambda r: float(r.get("timestamp_sec") or 0.0))
    merged_lines: list[dict[str, Any]] = []
    plain_parts: list[str] = []
    confidences: list[float] = []

    for row in ordered:
        text = str(row.get("text") or "").strip()
        if not text:
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
    )
    sample_frames = dedupe_frames(
        frames,
        max_frames=int(config.gold_story_ocr_max_frames),
    )
    ocr_rows = ocr_frames_parallel(sample_frames, config)
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
        "frame_count": len(sample_frames),
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
    module = "app.services.daily_story.gold_story.subtitle_ocr"
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
