"""阿里云百炼 CosyVoice TTS 客户端。"""

from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from pathlib import Path

import websocket

from app.config import get_settings
from app.services.media.ffmpeg_utils import build_srt_from_cues, concat_clips, probe_duration
from app.services.tts.tts_mgr import (
    SubtitleCue,
    TTSClient,
    TTSResult,
    save_subtitle_cues,
    sentences_for_segment,
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
}
DEFAULT_VOICE = "longwan_v3"
DEFAULT_MODEL = "cosyvoice-v3-flash"

# cSpell: enable


def _synthesize_utterance(
    text: str,
    *,
    timeout: float = 120,
    rate: float | None = None,
    pitch: float | None = None,
) -> bytes:
    """整句一次性 WebSocket 合成，返回 MP3 字节。"""
    settings = get_settings()
    api_key = settings.tts_api_key or settings.dashscope_api_key or ""
    if not api_key:
        raise ValueError("TTS_API_KEY or DASHSCOPE_API_KEY is required")
    if not text.strip():
        raise ValueError("TTS text is empty")

    voice = settings.tts_voice
    model = settings.tts_model or VOICE_MODEL_MAP.get(voice, DEFAULT_MODEL)
    task_id = str(uuid.uuid4())
    audio_chunks: list[bytes] = []
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
                    },
                    "input": {},
                },
            }))

    def on_message(ws, message) -> None:
        if isinstance(message, bytes):
            audio_chunks.append(message)
            return
        try:
            body = json.loads(message)
        except json.JSONDecodeError:
            return
        header = body.get("header", {})
        event = header.get("event")
        if event == "task-started":
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
    return audio


def synthesize_utterance(
    text: str,
    output_path: Path,
    *,
    rate: float | None = None,
    pitch: float | None = None,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(_synthesize_utterance(text, rate=rate, pitch=pitch))
    return output_path


class AliTTSClient(TTSClient):
    """按句末标点断句逐句合成，再合并音轨与字幕。"""

    def synthesize(self, narration: str, segments: list[dict], output_dir: Path) -> TTSResult:
        if not segments:
            raise ValueError("no segments to synthesize")

        output_dir.mkdir(parents=True, exist_ok=True)
        clips_dir = output_dir / "clips"
        clips_dir.mkdir(parents=True, exist_ok=True)

        clip_paths: list[Path] = []
        subtitle_cues: list[SubtitleCue] = []
        segment_durations: list[float] = []

        for seg in segments:
            seg_index = seg["segment_index"]
            sentences = sentences_for_segment(seg)
            seg_duration = 0.0
            logger.info("tts ali segment %s, %s sentences", seg_index, len(sentences))

            for sent_index, sentence in enumerate(sentences):
                logger.info(
                    "tts ali segment %s sentence %s, %s chars",
                    seg_index,
                    sent_index,
                    len(sentence),
                )
                clip_path = clips_dir / f"{seg_index}_{sent_index}.mp3"
                clip_path.write_bytes(_synthesize_utterance(sentence))
                duration = probe_duration(clip_path)
                clip_paths.append(clip_path)
                subtitle_cues.append(
                    SubtitleCue(
                        segment_index=seg_index,
                        text=sentence,
                        duration_sec=duration,
                    )
                )
                seg_duration += duration
            segment_durations.append(seg_duration)

        audio_path = output_dir / "narration.mp3"
        concat_clips(clip_paths, audio_path)

        cues_path = subtitle_cues_path_for(output_dir)
        save_subtitle_cues(cues_path, subtitle_cues)

        subtitle_path = output_dir / "subtitles.srt"
        subtitle_path.write_text(build_srt_from_cues(subtitle_cues), encoding="utf-8")

        return TTSResult(
            audio_path=audio_path,
            subtitle_path=subtitle_path,
            subtitle_cues_path=cues_path,
            duration_sec=sum(segment_durations),
            segment_durations=segment_durations,
            subtitle_cues=subtitle_cues,
        )
