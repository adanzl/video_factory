"""基底视频画面时间表解析与口播对齐提示词。"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from typing import Any

# 实测 TTS rate≈1.15 时中文口播约 4.5–5 字/秒，留余量避免拖镜
TIMELINE_TTS_CHARS_PER_SEC = 5.0

_TIMELINE_ITEM_KEYS = ("balls", "segments", "items", "entries", "scenes", "shots")


@dataclass(frozen=True)
class TimelineSlot:
    index: int
    start_sec: float
    end_sec: float
    duration_sec: float
    scene: str
    max_chars: int


@dataclass(frozen=True)
class VideoTimeline:
    duration_sec: float | None
    slots: tuple[TimelineSlot, ...]
    raw: str


def _coerce_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None
    return None


def _coerce_int(value: object) -> int | None:
    num = _coerce_float(value)
    if num is None:
        return None
    rounded = int(num)
    return rounded if rounded > 0 else None


def _slot_scene_label(item: dict[str, Any], *, fallback_index: int) -> str:
    label = item.get("label") or item.get("scene") or item.get("title")
    if isinstance(label, str) and label.strip():
        return label.strip()

    parts: list[str] = []
    year = item.get("year")
    if year is not None:
        parts.append(f"{year}年")
    country = item.get("country") or item.get("host")
    if isinstance(country, str) and country.strip():
        parts.append(country.strip())
    ball_name = item.get("ball_name") or item.get("name")
    if isinstance(ball_name, str) and ball_name.strip():
        parts.append(ball_name.strip())
    description = item.get("description") or item.get("topic")
    if isinstance(description, str) and description.strip():
        parts.append(description.strip())

    if parts:
        return " ".join(parts)
    return f"第{fallback_index}段画面"


def _slot_duration(item: dict[str, Any]) -> float | None:
    duration = _coerce_float(item.get("duration_sec"))
    if duration is not None and duration > 0:
        return duration
    start = _coerce_float(item.get("start_sec"))
    end = _coerce_float(item.get("end_sec"))
    if start is not None and end is not None and end > start:
        return end - start
    return None


def _timeline_items(data: dict[str, Any]) -> list[dict[str, Any]] | None:
    for key in _TIMELINE_ITEM_KEYS:
        raw = data.get(key)
        if isinstance(raw, list) and raw:
            items = [item for item in raw if isinstance(item, dict)]
            if items:
                return items
    return None


def _max_chars_for_duration(duration_sec: float) -> int:
    return max(8, int(math.floor(duration_sec * TIMELINE_TTS_CHARS_PER_SEC)))


def parse_video_timeline(raw: str | None) -> VideoTimeline | None:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None

    items = _timeline_items(data)
    if not items:
        return None

    duration_sec = _coerce_float(data.get("duration_sec"))
    slots: list[TimelineSlot] = []
    for idx, item in enumerate(items, start=1):
        start = _coerce_float(item.get("start_sec"))
        end = _coerce_float(item.get("end_sec"))
        duration = _slot_duration(item)
        if duration is None or duration <= 0:
            continue
        if start is None and end is not None:
            start = end - duration
        if end is None and start is not None:
            end = start + duration
        if start is None:
            if slots:
                start = slots[-1].end_sec
            else:
                start = 0.0
        if end is None:
            end = start + duration

        slot_index = _coerce_int(item.get("index")) or idx
        scene = _slot_scene_label(item, fallback_index=slot_index)
        slots.append(
            TimelineSlot(
                index=slot_index,
                start_sec=start,
                end_sec=end,
                duration_sec=duration,
                scene=scene,
                max_chars=_max_chars_for_duration(duration),
            )
        )

    if not slots:
        return None
    return VideoTimeline(duration_sec=duration_sec, slots=tuple(slots), raw=text)


def _format_sec(value: float) -> str:
    if value == int(value):
        return str(int(value))
    return f"{value:.1f}"


def timeline_table_for_prompt(timeline: VideoTimeline) -> str:
    lines = [
        "序号 | 起止(秒) | 时长 | 画面内容 | 本段字数上限",
        "--- | --- | --- | --- | ---",
    ]
    for slot in timeline.slots:
        lines.append(
            f"{slot.index} | {_format_sec(slot.start_sec)}-{_format_sec(slot.end_sec)} | "
            f"{_format_sec(slot.duration_sec)}s | {slot.scene} | {slot.max_chars}"
        )
    return "\n".join(lines)


def timeline_system_clause(timeline: VideoTimeline) -> str:
    count = len(timeline.slots)
    total_max = sum(slot.max_chars for slot in timeline.slots)
    return (
        f"用户提供了基底视频画面时间表（共{count}段），口播须与画面逐段严格对齐。"
        f"segments 必须恰好 {count} 条，segment_index 从 1 到 {count}，与时间表顺序一一对应；"
        "第 i 段 text 只讲第 i 段画面，禁止提前讲后续画面、禁止滞后讲上一段、禁止合并多段。"
        "禁止开场钩子、悬念反问（如「你知道吗」）、全片总起、结尾长篇回顾或清单式连读多届/多段。"
        "narration 第一句必须从第 1 段画面内容直接讲起（视频 0 秒即进入该段主题）。"
        f"每段 text 字数不得超过对应 max_chars（全片合计约 {total_max} 字），宁可短勿超；"
        "各段 text 按顺序拼接须与 narration 完全一致。"
        "有补充信息时不得与时间表矛盾；时间表优先决定分段与讲什么。"
    )


def append_timeline_to_user(user: str, timeline: VideoTimeline) -> str:
    return (
        f"{user}\n\n"
        "基底视频画面时间表（segments 须与此表逐段对齐；JSON 为权威来源）：\n"
        f"{timeline_table_for_prompt(timeline)}\n\n"
        "时间表 JSON：\n"
        f"{timeline.raw}"
    )


def narration_range_for_timeline(timeline: VideoTimeline) -> tuple[int, int]:
    total = sum(slot.max_chars for slot in timeline.slots)
    margin = max(30, int(total * 0.08))
    lo = max(100, total - margin)
    hi = total + max(20, int(margin * 0.5))
    return lo, hi


def validate_timeline_script(script: dict[str, Any], timeline: VideoTimeline) -> str | None:
    segments = script.get("segments") or []
    expected = len(timeline.slots)
    if len(segments) != expected:
        return (
            f"segments 数量须等于时间表条目数 {expected}，当前 {len(segments)}；"
            "请按时间表逐段输出，每段一条 segment，禁止合并或拆分。"
        )

    over_limit: list[str] = []
    for seg, slot in zip(segments, timeline.slots, strict=False):
        seg_index = seg.get("segment_index")
        if seg_index != slot.index:
            return (
                f"segment_index 须与时间表一致：第 {slot.index} 段应为 segment_index={slot.index}，"
                f"当前为 {seg_index!r}。"
            )
        text = str(seg.get("text") or "")
        chars = len(re.sub(r"\s+", "", text))
        if chars > slot.max_chars:
            over_limit.append(
                f"第{slot.index}段({slot.scene}) {chars}字>{slot.max_chars}字"
            )

    if over_limit:
        return (
            "以下段落超长，请压缩 wording 后重写："
            + "；".join(over_limit)
            + f"。按约 {TIMELINE_TTS_CHARS_PER_SEC} 字/秒控字数。"
        )
    return None
