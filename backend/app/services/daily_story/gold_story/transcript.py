"""H0b 逐字稿：yt-dlp 下载 + faster-whisper 转写（平台无关 ASR）。"""

from __future__ import annotations

import logging
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import Config
from app.services.daily_story.gold_story.download import (
    MediaRef,
    download_media,
    extract_audio_wav,
    normalize_bv,
    parse_media_ref,
    write_metadata,
)
from app.services.daily_story.gold_story import whisper as gs_whisper
from app.services.daily_story.gold_story import subtitle_ocr as gs_subtitle_ocr
from app.services.daily_story.gold_story import transcript_merge as gs_transcript_merge

logger = logging.getLogger(__name__)

__all__ = [
    "batch_bilibili",
    "batch_transcribe",
    "doctor",
    "format_dialogue_transcript",
    "format_transcript_display",
    "normalize_bv",
    "read_source_list",
    "repaired_transcript_path",
    "save_repaired_transcript",
    "transcribe_bilibili",
    "transcribe_media",
]


def repaired_transcript_path(config: Config, source_id: str) -> Path:
    return config.gold_story_transcript_dir / f"{source_id}.repaired.txt"


def format_dialogue_transcript(lines: list[dict[str, Any]]) -> str:
    """说话人标注逐字稿：每行 `角色：台词`。"""
    out: list[str] = []
    for row in lines:
        speaker = str(row.get("speaker") or "未知").strip() or "未知"
        text = str(row.get("text") or "").strip()
        if text:
            out.append(f"{speaker}：{text}")
    return "\n".join(out)


def save_repaired_transcript(path: Path, lines: list[dict[str, Any]]) -> str:
    text = format_dialogue_transcript(lines)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text + "\n", encoding="utf-8")
    return text


def format_transcript_display(text: str) -> str:
    """逐字稿展示：已有换行保留；否则按句读/逗号断行。"""
    raw = str(text or "").strip()
    if not raw:
        return ""
    if "\n" in raw:
        return raw
    for pattern in (r"(?<=[。！？!?；;])", r"(?<=[，,])"):
        parts = re.split(pattern, raw)
        lines = [part.strip() for part in parts if part.strip()]
        if len(lines) > 1:
            return "\n".join(lines)
    return raw


def read_source_list(path: Path) -> list[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    out: list[str] = []
    for line in lines:
        text = line.strip()
        if not text or text.startswith("#"):
            continue
        out.append(text)
    if not out:
        raise ValueError(f"no sources in {path}")
    return out


def _transcript_path(config: Config, ref: MediaRef) -> Path:
    return config.gold_story_transcript_dir / f"{ref.source_id}.txt"


def _resolve_transcription(
    *,
    video_path: Path,
    audio_path: Path,
    ref: MediaRef,
    cfg: Config,
    workspace: Path,
    prompt: str | None,
    title: str = "",
    duration_sec: float | None = None,
) -> dict[str, Any]:
    """OCR 优先（烧录字幕，子进程隔离）→ 必要时 Whisper ASR 兜底。"""
    candidates: list[dict[str, Any]] = []
    ocr_result: dict[str, Any] | None = None
    asr_result: dict[str, Any] | None = None
    skip_asr = False

    if gs_subtitle_ocr.should_try_ocr(video_path, config=cfg, workspace=workspace):
        try:
            ocr_result = gs_subtitle_ocr.transcribe_video_ocr_subprocess(
                video_path,
                config=cfg,
                workspace=workspace,
                source_id=ref.source_id,
                title=title,
                duration_sec=duration_sec,
            )
            if str(ocr_result.get("text") or "").strip():
                candidates.append(ocr_result)
                skip_asr = gs_subtitle_ocr.should_skip_asr_after_ocr(ocr_result, cfg)
                if skip_asr:
                    logger.info(
                        "gold_story skip ASR bvid=%s ocr_quality=%.2f",
                        ref.source_id,
                        float(ocr_result.get("quality_score") or 0.0),
                    )
        except Exception as exc:
            logger.warning(
                "gold_story OCR failed bvid=%s: %s",
                ref.source_id,
                exc,
            )

    if not skip_asr:
        try:
            asr_result = gs_whisper.transcribe_audio(audio_path, cfg, prompt=prompt)
            if str(asr_result.get("text") or "").strip():
                asr_row = {
                    **asr_result,
                    "source": "asr",
                    "avg_confidence": None,
                    "quality_score": gs_transcript_merge.score_transcript_text(
                        str(asr_result.get("text") or ""),
                        title=title,
                        duration_sec=float(duration_sec or 0.0),
                    ),
                }
                candidates.append(asr_row)
        except Exception as exc:
            if not candidates:
                raise
            logger.warning(
                "gold_story ASR failed after OCR bvid=%s: %s",
                ref.source_id,
                exc,
            )

    if not candidates:
        raise RuntimeError("both OCR and ASR returned empty transcript")

    picked = gs_transcript_merge.pick_transcript_candidate(
        candidates,
        title=title,
        duration_sec=float(duration_sec or 0.0),
        min_quality=float(cfg.gold_story_ocr_quality_min),
    )
    engine = str(picked.get("engine") or picked.get("source") or "unknown")
    model = str(picked.get("model") or "")
    return {
        "text": str(picked.get("text") or ""),
        "segments": picked.get("segments") or [],
        "engine": engine,
        "model": model,
        "language": picked.get("language"),
        "source": picked.get("source"),
        "quality_score": picked.get("quality_score"),
        "quality_warn": picked.get("quality_warn"),
        "avg_confidence": picked.get("avg_confidence"),
        "ocr_attempted": ocr_result is not None,
        "asr_attempted": asr_result is not None,
        "asr_skipped": skip_asr,
        "candidates": [
            {
                "source": row.get("source"),
                "quality_score": row.get("quality_score"),
                "chars": len(str(row.get("text") or "")),
            }
            for row in candidates
        ],
    }


def transcribe_media(
    source: str,
    *,
    platform: str = "bili",
    output: Path | None = None,
    config: Config | None = None,
    skip_existing: bool = True,
    prompt: str | None = None,
) -> dict[str, Any]:
    """下载 + 转写单条，输出 `{source_id}.txt`。"""
    cfg = config or Config()
    ref = parse_media_ref(source, platform=platform)
    out_path = output or _transcript_path(cfg, ref)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if skip_existing and out_path.exists() and out_path.stat().st_size > 0:
        return {
            "source": ref.source,
            "source_id": ref.source_id,
            "action": "skip",
            "transcript_path": str(out_path),
        }

    workspace = cfg.gold_story_media_workspace
    audio_dir = workspace / "audio"
    metadata_dir = workspace / "metadata"

    downloaded = download_media(ref, cfg)
    duration_sec = float(downloaded.metadata.get("duration") or 0.0)
    audio_path = extract_audio_wav(
        downloaded.video_path,
        audio_dir=audio_dir,
        stem=ref.source_id,
    )
    transcription = _resolve_transcription(
        video_path=downloaded.video_path,
        audio_path=audio_path,
        ref=ref,
        cfg=cfg,
        workspace=workspace,
        prompt=prompt,
        title=str(downloaded.metadata.get("title") or ""),
        duration_sec=duration_sec,
    )
    out_path.write_text(transcription["text"] + "\n", encoding="utf-8")

    meta_path = write_metadata(
        ref=ref,
        metadata_dir=metadata_dir,
        payload={
            "source": ref.source,
            "source_id": ref.source_id,
            "url": ref.url,
            "download": downloaded.metadata,
            "audio_path": str(audio_path),
            "video_path": str(downloaded.video_path),
            "engine": transcription["engine"],
            "model": transcription["model"],
            "language": transcription.get("language"),
            "transcript_backend": transcription.get("source"),
            "transcript_quality_score": transcription.get("quality_score"),
            "transcript_path": str(out_path),
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
    )
    return {
        "source": ref.source,
        "source_id": ref.source_id,
        "action": "ok",
        "transcript_path": str(out_path),
        "metadata_path": str(meta_path),
        "engine": transcription["engine"],
        "model": transcription["model"],
        "transcript_backend": transcription.get("source"),
        "quality_score": transcription.get("quality_score"),
    }


def batch_transcribe(
    sources: list[str],
    *,
    platform: str = "bili",
    config: Config | None = None,
    skip_existing: bool = True,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for raw in sources:
        try:
            row = transcribe_media(
                raw,
                platform=platform,
                config=config,
                skip_existing=skip_existing,
            )
        except Exception as exc:
            try:
                ref = parse_media_ref(raw, platform=platform)
                source_id = ref.source_id
                source = ref.source
            except ValueError:
                source_id = None
                source = platform
            results.append(
                {
                    "source": source,
                    "source_id": source_id,
                    "source_input": raw,
                    "action": "error",
                    "error": str(exc),
                }
            )
            continue
        results.append(row)
    return results


def transcribe_bilibili(
    source: str,
    *,
    output: Path | None = None,
    config: Config | None = None,
    skip_existing: bool = True,
) -> dict[str, Any]:
    return transcribe_media(
        source,
        platform="bili",
        output=output,
        config=config,
        skip_existing=skip_existing,
    )


def batch_bilibili(
    sources: list[str],
    *,
    config: Config | None = None,
    skip_existing: bool = True,
) -> list[dict[str, Any]]:
    return batch_transcribe(
        sources,
        platform="bili",
        config=config,
        skip_existing=skip_existing,
    )


def doctor(config: Config | None = None) -> dict[str, Any]:
    cfg = config or Config()
    model_path = cfg.whisper_model_dir / cfg.gold_story_whisper_model
    yt_dlp_ok = False
    faster_whisper_ok = False
    rapidocr_ok = False
    onnxruntime_ok = False
    cv2_ok = False
    ocr_models_ok = False
    try:
        import yt_dlp  # noqa: F401

        yt_dlp_ok = True
    except ImportError:
        pass
    try:
        import faster_whisper  # noqa: F401

        faster_whisper_ok = True
    except ImportError:
        pass
    try:
        from rapidocr import RapidOCR  # noqa: F401

        rapidocr_ok = True
    except ImportError:
        pass
    try:
        import onnxruntime  # noqa: F401

        onnxruntime_ok = True
    except ImportError:
        pass
    try:
        import cv2  # noqa: F401

        cv2_ok = True
    except ImportError:
        pass

    ocr_dir = cfg.ocr_model_dir
    if ocr_dir.is_dir():
        ocr_models_ok = (
            (ocr_dir / "ch_PP-OCRv4_det_mobile.onnx").is_file()
            and (ocr_dir / "ch_PP-OCRv4_rec_mobile.onnx").is_file()
        )

    return {
        "ffmpeg": shutil.which("ffmpeg"),
        "yt_dlp": yt_dlp_ok,
        "faster_whisper": faster_whisper_ok,
        "rapidocr": rapidocr_ok,
        "onnxruntime": onnxruntime_ok,
        "opencv": cv2_ok,
        "ocr_model_dir": str(ocr_dir),
        "ocr_models_ready": ocr_models_ok,
        "gold_story_ocr_enabled": cfg.gold_story_ocr_enabled,
        "gold_story_ocr_frame_workers": cfg.gold_story_ocr_frame_workers,
        "whisper_model_dir": str(cfg.whisper_model_dir),
        "whisper_model": cfg.gold_story_whisper_model,
        "whisper_model_path": str(model_path),
        "whisper_model_exists": model_path.is_dir(),
        "transcript_dir": str(cfg.gold_story_transcript_dir),
        "media_workspace": str(cfg.gold_story_media_workspace),
        "bili_cookie": str(cfg.bili_cookie_path),
        "bili_cookie_exists": cfg.bili_cookie_path.exists(),
        "douyin_cookie": str(cfg.douyin_cookie_path or ""),
        "douyin_cookie_exists": bool(
            cfg.douyin_cookie_path and cfg.douyin_cookie_path.exists()
        ),
        "platforms_ready": {
            "bili": bool(cfg.bili_cookie_path.exists()),
            "douyin": bool(cfg.douyin_cookie_path and cfg.douyin_cookie_path.exists()),
        },
    }
