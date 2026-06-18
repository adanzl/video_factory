"""阿里云百炼 CosyVoice TTS 客户端。"""

from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

import websocket

from app.config import get_settings
from app.services.tts.instruct import resolve_instruction
from app.services.tts.phrase_timing import (
    build_segment_tts_text,
    normalize_word_timestamps,
    phrase_durations_from_words,
)
from app.services.media.ffmpeg_utils import build_srt_from_cues, concat_clips, probe_duration
from app.services.tts.tts_mgr import (
    SubtitleCue,
    TTSClient,
    TTSResult,
    TTSUsageTask,
    phrase_chunks_for_segment,
    save_subtitle_cues,
    subtitle_cues_path_for,
)

logger = logging.getLogger(__name__)
# cSpell: disable
VOICE_MODEL_MAP = {
    "longwan_v2": "cosyvoice-v2",
    "longcheng_v2": "cosyvoice-v2",
    "longhua_v2": "cosyvoice-v2",
    "longshu_v2": "cosyvoice-v2",
    "loongbella_v2": "cosyvoice-v2",
    "longxiaochun_v2": "cosyvoice-v2",
    "longxiaoxia_v2": "cosyvoice-v2",
    "longwan_v3": "cosyvoice-v3-flash",
    "longyingjing_v3": "cosyvoice-v3-flash",
    "longanhuan_v3": "cosyvoice-v3-flash",
    "longanhuan": "cosyvoice-v3-flash",
    "longhuhu_v3": "cosyvoice-v3-flash",
    "longhuhu": "cosyvoice-v3-flash",
    "longniuniu_v3": "cosyvoice-v3-flash",
    "longniuniu": "cosyvoice-v3-flash",
    "longxian_v3": "cosyvoice-v3-flash",
    "longjielidou_v3": "cosyvoice-v3-flash",
}
DEFAULT_VOICE = "longhuhu_v3"
DEFAULT_MODEL = "cosyvoice-v3-flash"

# cSpell: enable


@dataclass(frozen=True)
class _SynthesisResult:
    audio: bytes
    words: list[dict]
    usage: dict | None = None


def _pick_usage(payload: dict) -> dict | None:
    usage = payload.get("usage")
    if isinstance(usage, dict) and usage:
        return usage
    return None


def _segment_timeout(text: str) -> float:
    return max(120.0, len(text) * 0.35 + 45.0)


def _run_tts_task(
    text: str,
    *,
    word_timestamps: bool = False,
    timeout: float = 120,
    rate: float | None = None,
    pitch: float | None = None,
) -> _SynthesisResult:
    settings = get_settings()
    api_key = settings.dashscope_api_key or settings.tts_api_key or ""
    if not api_key:
        raise ValueError("DASHSCOPE_API_KEY is required for TTS")
    if not text.strip():
        raise ValueError("TTS text is empty")

    voice = settings.tts_voice
    model = settings.tts_model or VOICE_MODEL_MAP.get(voice, DEFAULT_MODEL)
    instruction = resolve_instruction(
        voice,
        explicit=settings.tts_instruction,
        preset=settings.tts_instruct_preset,
    )
    task_id = str(uuid.uuid4())
    audio_chunks: list[bytes] = []
    raw_words: list[dict] = []
    latest_usage: dict | None = None
    started = threading.Event()
    finished = threading.Event()
    error: list[Exception] = []

    def on_open(ws) -> None:
        ws.send(
            json.dumps({
                "header": {
                    "action": "run-task",
                    "task_id": task_id,
                    "streaming": "duplex",
                },
                "payload": {
                    "task_group": "audio",
                    "task": "tts",
                    "function": "SpeechSynthesizer",
                    "model": model,
                    "parameters": {
                        "text_type": "PlainText",
                        "voice": voice,
                        "format": "mp3",
                        "sample_rate": 22050,
                        "volume": settings.tts_volume,
                        "rate": rate if rate is not None else settings.tts_speech_rate,
                        "pitch": pitch if pitch is not None else 1,
                        "enable_ssml": False,  # cSpell: disable-line
                        "word_timestamp_enabled": word_timestamps,
                        **({"instruction": instruction} if instruction else {}),
                    },
                    "input": {},
                },
            }))

    def on_message(ws, message) -> None:
        nonlocal latest_usage
        if isinstance(message, bytes):
            audio_chunks.append(message)
            return
        try:
            body = json.loads(message)
        except json.JSONDecodeError:
            return
        header = body.get("header", {})
        event = header.get("event")
        payload = body.get("payload", {})
        if event == "result-generated":
            output = payload.get("output", {})
            if output.get("type") == "sentence-end":
                usage = _pick_usage(payload)
                if usage is not None:
                    latest_usage = usage
                for word in output.get("sentence", {}).get("words") or []:
                    if word.get("text"):
                        raw_words.append(word)
        elif event == "task-started":
            started.set()
            ws.send(
                json.dumps(
                    {
                        "header": {
                            "action": "continue-task",
                            "task_id": task_id,
                            "streaming": "duplex",
                        },
                        "payload": {"input": {"text": text}},
                    }
                )
            )
            ws.send(
                json.dumps(
                    {
                        "header": {
                            "action": "finish-task",
                            "task_id": task_id,
                            "streaming": "duplex",
                        },
                        "payload": {"input": {}},
                    }
                )
            )
        elif event == "task-finished":
            usage = _pick_usage(payload)
            if usage is not None:
                latest_usage = usage
            finished.set()
            ws.close()
        elif event == "task-failed":
            msg = header.get("error_message", "TTS task failed")
            code = header.get("error_code", "")
            error.append(RuntimeError(f"{code}: {msg}" if code else msg))
            finished.set()
            ws.close()

    def on_error(_ws, err) -> None:
        error.append(err if isinstance(err, Exception) else RuntimeError(str(err)))
        finished.set()

    ws_app = websocket.WebSocketApp(
        settings.dashscope_ws_uri,
        header={
            "Authorization": f"bearer {api_key}",
            "X-DashScope-DataInspection": "enable",
        },
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
    )
    thread = threading.Thread(target=ws_app.run_forever, daemon=True)
    thread.start()

    if not started.wait(timeout=15):
        ws_app.close()
        raise TimeoutError("TTS task-started 超时")

    deadline = time.time() + timeout
    while not finished.is_set():
        if time.time() > deadline:
            ws_app.close()
            raise TimeoutError(f"TTS 合成超时（>{timeout}s）")
        time.sleep(0.05)

    if error:
        raise error[0]
    audio = b"".join(audio_chunks)
    if not audio:
        raise RuntimeError("TTS 返回空音频")
    return _SynthesisResult(audio=audio, words=raw_words, usage=latest_usage)


def synthesize_utterance(
    text: str,
    output_path: Path,
    *,
    rate: float | None = None,
    pitch: float | None = None,
) -> Path:
    """单句 MP3（片头喊声等）。"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result = _run_tts_task(text, rate=rate, pitch=pitch)
    output_path.write_bytes(result.audio)
    if result.usage:
        logger.info(
            "tts utterance done chars=%s bytes=%s",
            result.usage.get("characters"),
            len(result.audio),
        )
    return output_path


class AliTTSClient(TTSClient):
    """按分镜整段合成（每 segment 一次 WebSocket），字幕仍用 phrase_chunks 断句。"""

    def synthesize(self, narration: str, segments: list[dict], output_dir: Path) -> TTSResult:
        if not segments:
            raise ValueError("no segments to synthesize")

        settings = get_settings()
        output_dir.mkdir(parents=True, exist_ok=True)
        clips_dir = output_dir / "clips"
        clips_dir.mkdir(parents=True, exist_ok=True)

        clip_paths: list[Path] = []
        subtitle_cues: list[SubtitleCue] = []
        segment_durations: list[float] = []
        usage_tasks: list[TTSUsageTask] = []

        logger.info(
            "tts start segments=%s voice=%s model=%s",
            len(segments),
            settings.tts_voice,
            settings.tts_model or VOICE_MODEL_MAP.get(settings.tts_voice, DEFAULT_MODEL),
        )

        for seg in segments:
            seg_index = seg["segment_index"]
            phrases = phrase_chunks_for_segment(seg)
            segment_text = build_segment_tts_text(phrases)
            logger.info(
                "tts segment %s start phrases=%s text_chars=%s",
                seg_index,
                len(phrases),
                len(segment_text),
            )

            result = _run_tts_task(
                segment_text,
                word_timestamps=True,
                timeout=_segment_timeout(segment_text),
            )
            segment_mp3 = clips_dir / f"{seg_index}.mp3"
            segment_mp3.write_bytes(result.audio)

            segment_duration = probe_duration(segment_mp3)
            words = normalize_word_timestamps(result.words)
            phrase_durations = phrase_durations_from_words(
                phrases,
                words,
                segment_duration_sec=segment_duration,
            )
            if not words:
                logger.warning(
                    "tts segment %s: no word timestamps, proportional subtitle timing",
                    seg_index,
                )

            clip_paths.append(segment_mp3)
            for (_, subtitle_text), duration in zip(phrases, phrase_durations, strict=False):
                subtitle_cues.append(
                    SubtitleCue(
                        segment_index=seg_index,
                        text=subtitle_text,
                        duration_sec=duration,
                    )
                )
            segment_durations.append(segment_duration)

            usage_chars = None
            if result.usage:
                usage_tasks.append(
                    TTSUsageTask(
                        segment_index=seg_index,
                        usage=result.usage,
                    )
                )
                usage_chars = result.usage.get("characters")
            logger.info(
                "tts segment %s done duration=%.2fs cues=%s billing_chars=%s",
                seg_index,
                segment_duration,
                len(phrases),
                usage_chars,
            )

        audio_path = output_dir / "narration.mp3"
        concat_clips(clip_paths, audio_path)

        cues_path = subtitle_cues_path_for(output_dir)
        save_subtitle_cues(cues_path, subtitle_cues)

        subtitle_path = output_dir / "subtitles.srt"
        subtitle_path.write_text(build_srt_from_cues(subtitle_cues), encoding="utf-8")

        total_chars = sum(int(t.usage.get("characters") or 0) for t in usage_tasks)
        logger.info(
            "tts done duration=%.2fs cues=%s billing_chars=%s path=%s",
            sum(segment_durations),
            len(subtitle_cues),
            total_chars,
            audio_path,
        )

        return TTSResult(
            audio_path=audio_path,
            subtitle_path=subtitle_path,
            subtitle_cues_path=cues_path,
            duration_sec=sum(segment_durations),
            segment_durations=segment_durations,
            subtitle_cues=subtitle_cues,
            usage_tasks=usage_tasks,
        )
