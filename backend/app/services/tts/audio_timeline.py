"""TTS 口播时间轴：分镜时长探测、对齐全轨 narration、落盘 manifest。"""

from __future__ import annotations

import json
from pathlib import Path

from app.services.media.ffmpeg_utils import probe_duration

__all__ = [
    "align_segment_durations_to_narration",
    "audio_timeline_manifest_path",
    "extend_phrase_cues_to_duration",
    "probe_segment_clip_durations",
    "resolve_segment_timeline_durations",
    "save_audio_timeline_manifest",
    "segment_timeline_durations_from_db",
    "segment_tts_clip_path",
]


def segment_tts_clip_path(audio_dir: Path, segment_index: int) -> Path:
    """TTS 按分镜导出的 MP3（与 narration 拼接顺序一致）。"""
    return audio_dir / "clips" / f"{segment_index}.mp3"


def extend_phrase_cues_to_duration(
    cues: list[tuple[str, float]],
    target_sec: float,
    *,
    tail_tol: float = 0.02,
) -> list[tuple[str, float]]:
    """将句级字幕时长拉长到分镜口播总长（末尾留白跟音频）。"""
    if target_sec <= 0 or not cues:
        return cues
    total = sum(duration for _, duration in cues if duration > 0)
    if total <= 0:
        return cues
    gap = target_sec - total
    if gap <= tail_tol:
        return cues
    out = list(cues)
    text, duration = out[-1]
    out[-1] = (text, duration + gap)
    return out


def _scale_durations_to_audio(
    durations: list[float],
    audio_dur: float,
    *,
    tail_tol: float = 0.05,
) -> list[float]:
    total = sum(durations)
    if total <= 0:
        return durations
    drift = audio_dur - total
    if abs(drift) <= tail_tol:
        if abs(drift) > 0.001:
            scaled = list(durations)
            scaled[-1] += drift
            return scaled
        return durations
    scale = audio_dur / total
    return [d * scale for d in durations]


def probe_segment_clip_durations(
    audio_dir: Path,
    segments: list[dict],
) -> list[float]:
    """按 segment_index 顺序探测 audio/clips/{n}.mp3 时长。"""
    sorted_seg = sorted(segments, key=lambda s: int(s["segment_index"]))
    durations: list[float] = []
    for seg in sorted_seg:
        index = int(seg["segment_index"])
        clip = segment_tts_clip_path(audio_dir, index)
        if not clip.is_file():
            raise FileNotFoundError(f"TTS 分镜音频缺失: {clip}")
        dur = probe_duration(clip)
        if dur <= 0:
            raise ValueError(f"TTS 分镜音频时长无效: {clip}")
        durations.append(dur)
    return durations


def align_segment_durations_to_narration(
    segment_durations: list[float],
    narration_path: Path,
    *,
    tail_tol: float = 0.05,
) -> list[float]:
    """将分镜时长缩放到与 narration 整轨一致（concat / loudnorm 后的交付音轨）。"""
    audio_dur = probe_duration(narration_path)
    return _scale_durations_to_audio(segment_durations, audio_dur, tail_tol=tail_tol)


def resolve_segment_timeline_durations(
    *,
    audio_dir: Path,
    narration_path: Path,
    segments: list[dict],
    segment_durations: list[float] | None = None,
    tail_tol: float = 0.05,
) -> list[float]:
    """TTS 结束：分镜在 narration 时间轴上的时长。

    标准线：``segment_durations`` 省略时从 clips 探测。
    日常线：传入已含镜间 gap 的 ``segment_durations``，不再探测 clips。
    """
    if segment_durations is not None:
        if len(segment_durations) != len(segments):
            raise ValueError("segment_durations 与 segments 数量不一致")
        base = list(segment_durations)
    else:
        base = probe_segment_clip_durations(audio_dir, segments)
    return align_segment_durations_to_narration(
        base,
        narration_path,
        tail_tol=tail_tol,
    )


def segment_timeline_durations_from_db(segments: list[dict]) -> list[float]:
    """merge 用：只读 TTS 已写入的 duration_sec。"""
    sorted_seg = sorted(segments, key=lambda s: int(s["segment_index"]))
    durations: list[float] = []
    for seg in sorted_seg:
        raw = seg.get("duration_sec")
        if raw is None or float(raw) <= 0:
            index = seg["segment_index"]
            raise ValueError(f"segment {index} 缺少 duration_sec，请从 tts 阶段重跑")
        durations.append(float(raw))
    return durations


def audio_timeline_manifest_path(audio_dir: Path) -> Path:
    return audio_dir / "segment_timeline.json"


def save_audio_timeline_manifest(
    audio_dir: Path,
    segments: list[dict],
    timeline_durations: list[float],
    narration_path: Path,
    *,
    clip_probe_durations: list[float] | None = None,
) -> Path:
    """TTS 结束时落盘，记录分镜在 narration 上的时长（与 DB 一致）。"""
    sorted_seg = sorted(segments, key=lambda s: int(s["segment_index"]))
    if len(timeline_durations) != len(sorted_seg):
        raise ValueError("timeline_durations 与 segments 数量不一致")
    items: list[dict[str, float | int]] = []
    for i, seg in enumerate(sorted_seg):
        entry: dict[str, float | int] = {
            "segment_index": int(seg["segment_index"]),
            "duration_sec": round(float(timeline_durations[i]), 3),
        }
        if clip_probe_durations is not None and i < len(clip_probe_durations):
            entry["clip_probe_sec"] = round(float(clip_probe_durations[i]), 3)
        items.append(entry)
    manifest = {
        "narration_duration_sec": round(probe_duration(narration_path), 3),
        "segments": items,
    }
    path = audio_timeline_manifest_path(audio_dir)
    path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path
