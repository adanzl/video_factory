"""分镜切割：由口播全文按单镜时长切 segments。"""

from __future__ import annotations

import re
from typing import Any

from app.utils.media import DEFAULT_SPEECH_CHARS_PER_SEC, split_narration_to_segments

__all__ = ["apply_segments_from_voiceover"]


def apply_segments_from_voiceover(
    data: dict[str, Any],
    *,
    segment_target_sec: float,
    chars_per_sec: float | None = None,
) -> dict[str, Any]:
    """将 narration 按单镜时长切分为 segments，并回写 word_count。"""
    narration = str(data.get("narration") or "").strip()
    if not narration:
        raise ValueError("LLM narration response missing narration")
    rate = chars_per_sec or DEFAULT_SPEECH_CHARS_PER_SEC
    data["segments"] = split_narration_to_segments(
        narration,
        segment_target_sec,
        chars_per_sec=rate,
    )
    if not data["segments"]:
        raise ValueError("narration split produced no segments")
    data["word_count"] = len(re.sub(r"\s+", "", str(data.get("narration") or "")))
    return data
