"""阿里云百炼 CosyVoice TTS 客户端。"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

import gevent
import gevent.event
import gevent.pool
import websocket

from app.config import get_settings
from app.services.tts.breath_cue import build_phrase_breath_cues
from app.services.tts.instruct import resolve_instruction
from app.services.tts.phrase_timing import (
    build_segment_tts_text,
    normalize_word_timestamps,
)
from app.services.tts.segment_trim import apply_tts_segment_trim
from app.services.tts.tts_leadin import prepare_lead_in, strip_tts_lead_in
from app.services.media.ffmpeg_utils import build_srt_from_cues, concat_clips, probe_duration, run_ffmpeg
from app.services.tts.tts_mgr import (
    SubtitleCue,
    TTSClient,
    TTSResult,
    TTSUsageTask,
    tts_mgr,
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
    "cosyvoice-v3.5-flash-leo-60621bdce780434ab0734555e5196d7d": "cosyvoice-v3.5-flash",
    "cosyvoice-v3.5-flash-leo-f9d115bfdf2346edbeb9d21ecd4f9ce9": "cosyvoice-v3.5-flash",
}
DEFAULT_VOICE = "cosyvoice-v3.5-flash-leo-60621bdce780434ab0734555e5196d7d"  # cSpell: disable-line
DEFAULT_MODEL = "cosyvoice-v3-flash"

# cSpell: enable


@dataclass(frozen=True)
class _SynthesisResult:
    audio: bytes
    words: list[dict]
    usage: dict | None = None


@dataclass(frozen=True)
class _SegmentSynthResult:
    seg_index: int
    clip_path: Path
    subtitle_cues: list[SubtitleCue]
    segment_duration: float
    usage_task: TTSUsageTask | None


def _pick_usage(payload: dict) -> dict | None:
    usage = payload.get("usage")
    if isinstance(usage, dict) and usage:
        return usage
    return None


def _segment_timeout(text: str) -> float:
    return max(120.0, len(text) * 0.35 + 45.0)


def _audio_extension(fmt: str | None = None) -> str:
    settings = get_settings()
    ext = (fmt or settings.tts_audio_format or "mp3").strip().lower().lstrip(".")
    return f".{ext}"


def _run_tts_task(
    text: str,
    *,
    word_timestamps: bool = False,
    timeout: float = 120,
    rate: float | None = None,
    pitch: float | None = None,
    voice: str | None = None,
    audio_format: str | None = None,
) -> _SynthesisResult:
    settings = get_settings()
    api_key = settings.dashscope_api_key or settings.tts_api_key or ""
    if not api_key:
        raise ValueError("DASHSCOPE_API_KEY is required for TTS")
    if not text.strip():
        raise ValueError("TTS text is empty")

    voice = voice or settings.tts_voice
    model = VOICE_MODEL_MAP.get(voice) or settings.tts_model or DEFAULT_MODEL
    instruction = resolve_instruction(
        voice,
        explicit=settings.tts_instruction,
        preset=settings.tts_instruct_preset,
    )
    fmt = (audio_format or settings.tts_audio_format or "mp3").strip().lower()
    task_id = str(uuid.uuid4())
    audio_chunks: list[bytes] = []
    raw_words: list[dict] = []
    latest_usage: dict | None = None
    started = gevent.event.Event()
    finished = gevent.event.Event()
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
                        "format": fmt,
                        "sample_rate": 22050,
                        "volume": settings.tts_volume,
                        "rate": rate if rate is not None else settings.tts_speech_rate,
                        "pitch": pitch if pitch is not None else 1,
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
    gevent.spawn(ws_app.run_forever)

    if not started.wait(timeout=30):
        ws_app.close()
        raise TimeoutError("TTS task-started 超时")

    if not finished.wait(timeout=timeout):
        ws_app.close()
        raise TimeoutError(f"TTS 合成超时（>{timeout}s）")

    if error:
        raise error[0]
    audio = b"".join(audio_chunks)
    if not audio:
        raise RuntimeError("TTS 返回空音频")
    logger.info(
        "tts result: audio=%d bytes words=%d text_chars=%d voice=%s",
        len(audio), len(raw_words), len(text), voice,
    )
    return _SynthesisResult(audio=audio, words=raw_words, usage=latest_usage)


def _synthesize_segment(
    seg: dict,
    clips_dir: Path,
    *,
    effective_voice: str,
    effective_rate: float,
) -> _SegmentSynthResult:
    seg_index = seg["segment_index"]
    raw_text = (seg.get("text") or "").strip()
    phrases = tts_mgr.phrase_chunks_for_segment(seg)
    segment_text = build_segment_tts_text(phrases)
    tts_text, lead_in = prepare_lead_in(segment_text, voice=effective_voice)
    settings = get_settings()
    logger.info(
        "tts segment %s raw_text=%s phrases=%s text_chars=%s lead_in=%s transport=websocket segment_text=%s tts_text=%s",
        seg_index,
        raw_text,
        len(phrases),
        len(segment_text),
        lead_in or "-",
        segment_text,
        tts_text,
    )

    for attempt in (1, 2):
        try:
            result = _run_tts_task(
                tts_text,
                word_timestamps=True,
                timeout=_segment_timeout(tts_text),
                rate=effective_rate,
                voice=effective_voice,
                audio_format="wav",
            )
            break
        except TimeoutError:
            if attempt == 2:
                raise
            logger.warning("tts segment %s task-started 超时，重试第 %s 次", seg_index, attempt)
            time.sleep(3)
            continue

    # 先存 WAV，裁剪后再转 MP3（WAV 上 -ss 是样本级精确）
    wav_clip = clips_dir / f"{seg_index}.wav"
    wav_clip.write_bytes(result.audio)

    words = normalize_word_timestamps(result.words)
    if lead_in:
        words = strip_tts_lead_in(wav_clip, words, lead_in, rate=effective_rate)
    if settings.tts_trim_edges:
        if words:
            words = apply_tts_segment_trim(wav_clip, words)
        else:
            logger.warning(
                "tts segment %s: no word timestamps, skip edge trim",
                seg_index,
            )

    # WAV → MP3
    segment_clip = clips_dir / f"{seg_index}.mp3"
    run_ffmpeg([
        "ffmpeg", "-y", "-hide_banner",
        "-i", str(wav_clip),
        "-c:a", "libmp3lame", "-q:a", "2",
        str(segment_clip),
    ])
    wav_clip.unlink(missing_ok=True)

    segment_duration = probe_duration(segment_clip)
    breath_cues = build_phrase_breath_cues(
        phrases,
        words,
        segment_duration_sec=segment_duration,
    )
    phrase_durations = [cue.duration_sec for cue in breath_cues]
    if not words:
        logger.warning(
            "tts segment %s: no word timestamps, proportional subtitle timing",
            seg_index,
        )
    elif len(breath_cues) > 1:
        pauses_ms = [
            pause
            for pause in (cue.pause_after_ms for cue in breath_cues)
            if pause is not None
        ]
        if pauses_ms:
            logger.info(
                "tts segment %s breath_cue_pauses_ms count=%s sum=%s avg=%.0f",
                seg_index,
                len(pauses_ms),
                sum(pauses_ms),
                sum(pauses_ms) / len(pauses_ms),
            )

    subtitle_cues = [
        SubtitleCue(
            segment_index=seg_index,
            text=subtitle_text,
            duration_sec=duration,
        )
        for (_, subtitle_text), duration in zip(phrases, phrase_durations, strict=False)
    ]

    usage_task: TTSUsageTask | None = None
    usage_chars = None
    if result.usage:
        usage_task = TTSUsageTask(
            segment_index=seg_index,
            usage=result.usage,
        )
        usage_chars = result.usage.get("characters")
    logger.info(
        "tts segment %s done duration=%.2fs cues=%s billing_chars=%s",
        seg_index,
        segment_duration,
        len(phrases),
        usage_chars,
    )

    return _SegmentSynthResult(
        seg_index=seg_index,
        clip_path=segment_clip,
        subtitle_cues=subtitle_cues,
        segment_duration=segment_duration,
        usage_task=usage_task,
    )


def synthesize_utterance(
    text: str,
    output_path: Path,
    *,
    rate: float | None = None,
    pitch: float | None = None,
    voice: str | None = None,
) -> Path:
    """单句 MP3（片头喊声等）。"""
    settings = get_settings()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result = _run_tts_task(text, rate=rate, pitch=pitch, voice=voice, audio_format="wav")
    wav_path = output_path.with_suffix(".wav")
    wav_path.write_bytes(result.audio)
    if settings.tts_trim_edges:
        apply_tts_segment_trim(wav_path, normalize_word_timestamps(result.words))
    run_ffmpeg([
        "ffmpeg", "-y", "-hide_banner",
        "-i", str(wav_path),
        "-c:a", "libmp3lame", "-q:a", "2",
        str(output_path),
    ])
    wav_path.unlink(missing_ok=True)
    if result.usage:
        logger.info(
            "tts utterance done chars=%s bytes=%s",
            result.usage.get("characters"),
            len(result.audio),
        )
    return output_path


class AliTTSClient(TTSClient):
    """按分镜整段合成（每 segment 一次 TTS 请求），字幕仍用 phrase_chunks 断句。"""

    def synthesize(
        self,
        narration: str,
        segments: list[dict],
        output_dir: Path,
        *,
        voice: str | None = None,
        speech_rate: float | None = None,
    ) -> TTSResult:
        if not segments:
            raise ValueError("no segments to synthesize")

        settings = get_settings()
        output_dir.mkdir(parents=True, exist_ok=True)
        clips_dir = output_dir / "clips"
        clips_dir.mkdir(parents=True, exist_ok=True)

        effective_voice = voice or settings.tts_voice
        effective_rate = speech_rate if speech_rate is not None else settings.tts_speech_rate

        max_workers = min(len(segments), max(1, settings.tts_max_workers))

        logger.info(
            "tts start segments=%s voice=%s model=%s rate=%s max_workers=%s transport=websocket",
            len(segments),
            effective_voice,
            VOICE_MODEL_MAP.get(effective_voice) or settings.tts_model or DEFAULT_MODEL,
            effective_rate,
            max_workers,
        )

        def _run(seg: dict) -> _SegmentSynthResult:
            return _synthesize_segment(
                seg,
                clips_dir,
                effective_voice=effective_voice,
                effective_rate=effective_rate,
            )

        pool = gevent.pool.Pool(size=max_workers)
        greenlets = [pool.spawn(_run, seg) for seg in segments]
        gevent.joinall(greenlets, raise_error=True)
        segment_results: list[_SegmentSynthResult] = [g.value for g in greenlets]

        segment_results.sort(key=lambda item: item.seg_index)

        clip_paths = [item.clip_path for item in segment_results]
        subtitle_cues = [
            cue for item in segment_results for cue in item.subtitle_cues
        ]
        segment_durations = [item.segment_duration for item in segment_results]
        usage_tasks = [
            item.usage_task for item in segment_results if item.usage_task is not None
        ]

        audio_path = output_dir / f"narration{_audio_extension()}"
        concat_clips(clip_paths, audio_path)

        cues_path = tts_mgr.subtitle_cues_path_for(output_dir)
        tts_mgr.save_subtitle_cues(cues_path, subtitle_cues)

        subtitle_path = output_dir / "subtitles.srt"
        subtitle_path.write_text(build_srt_from_cues(subtitle_cues), encoding="utf-8")
        logger.info(
            "srt written cues=%s path=%s",
            len(subtitle_cues),
            subtitle_path,
        )

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
