"""H0b ASR：faster-whisper，读本地 WHISPER_MODEL_DIR。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.config import Config


def join_segment_texts(parts: list[str]) -> str:
    """Whisper 分段合并：每段一行，便于阅读与下游 LLM。"""
    lines: list[str] = []
    for raw in parts:
        line = str(raw or "").strip()
        if line:
            lines.append(line)
    return "\n".join(lines)


def transcribe_audio(
    audio_path: Path,
    config: Config,
    *,
    prompt: str | None = None,
) -> dict[str, Any]:
    model_path = config.whisper_model_dir / config.gold_story_whisper_model
    if not model_path.is_dir():
        raise RuntimeError(
            f"faster-whisper model not found: {model_path} "
            "(set WHISPER_MODEL_DIR and GOLD_STORY_WHISPER_MODEL)"
        )
    try:
        from faster_whisper import WhisperModel  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError("faster-whisper is not installed") from exc

    model = WhisperModel(
        str(model_path),
        device=config.gold_story_whisper_device,
        compute_type=config.gold_story_whisper_compute_type,
    )
    transcribe_kwargs: dict[str, Any] = {
        "language": "zh",
        "initial_prompt": prompt or None,
        "vad_filter": config.gold_story_whisper_vad_filter,
        "condition_on_previous_text": False,
        "hallucination_silence_threshold": 2.0,
        "repetition_penalty": 1.15,
        "no_repeat_ngram_size": 3,
        "compression_ratio_threshold": 2.2,
    }
    segments_iter, info = model.transcribe(str(audio_path), **transcribe_kwargs)
    segment_rows: list[dict[str, Any]] = []
    text_parts: list[str] = []
    for segment in segments_iter:
        segment_rows.append(
            {
                "start": segment.start,
                "end": segment.end,
                "text": segment.text,
            }
        )
        text_parts.append(segment.text)

    text = join_segment_texts(text_parts)
    if not text and config.gold_story_whisper_vad_filter:
        segments_iter, info = model.transcribe(
            str(audio_path),
            **{**transcribe_kwargs, "vad_filter": False},
        )
        segment_rows = []
        text_parts = []
        for segment in segments_iter:
            segment_rows.append(
                {
                    "start": segment.start,
                    "end": segment.end,
                    "text": segment.text,
                }
            )
            text_parts.append(segment.text)
        text = join_segment_texts(text_parts)
    if not text:
        raise RuntimeError("faster-whisper returned empty transcript")
    return {
        "text": text,
        "segments": segment_rows,
        "language": getattr(info, "language", None),
        "engine": "faster-whisper",
        "model": config.gold_story_whisper_model,
        "model_path": str(model_path),
        "device": config.gold_story_whisper_device,
    }
