"""video_job.info JSON 字段解析与合并。"""

from __future__ import annotations

import json
from typing import Any

ORIENTATION_AUTO = "auto"
ORIENTATION_PORTRAIT = "portrait"
ORIENTATION_LANDSCAPE = "landscape"

_VALID_ORIENTATIONS = frozenset(
    {ORIENTATION_AUTO, ORIENTATION_PORTRAIT, ORIENTATION_LANDSCAPE}
)


def parse_job_info(raw: str | dict | None) -> dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return dict(raw)
    if not isinstance(raw, str):
        return {}
    text = raw.strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return dict(parsed) if isinstance(parsed, dict) else {}


def normalize_orientation(value: str | None) -> str | None:
    """将 orientation 规范为 auto / portrait / landscape。"""
    if value is None:
        return None
    normalized = value.strip().lower()
    if not normalized or normalized in {"auto", "自动", "default"}:
        return ORIENTATION_AUTO
    if normalized in {ORIENTATION_PORTRAIT, "竖屏", "vertical", "9:16", "9x16"}:
        return ORIENTATION_PORTRAIT
    if normalized in {ORIENTATION_LANDSCAPE, "横屏", "horizontal", "16:9", "16x9"}:
        return ORIENTATION_LANDSCAPE
    return None


def orientation_from_dimensions(width: int, height: int) -> str:
    if width > height:
        return ORIENTATION_LANDSCAPE
    return ORIENTATION_PORTRAIT


def orientation_for_resolve(job: dict) -> str | None:
    """读取 job.info.orientation，供片头尺寸解析（auto 返回 None）。"""
    raw = parse_job_info(job.get("info")).get("orientation")
    if not isinstance(raw, str):
        return None
    normalized = normalize_orientation(raw)
    if normalized in {ORIENTATION_PORTRAIT, ORIENTATION_LANDSCAPE}:
        return normalized
    return None


def default_orientation_for_pipeline(pipeline: str | None) -> str:
    if (pipeline or "standard").strip() == "material":
        return ORIENTATION_AUTO
    return ORIENTATION_PORTRAIT


def merge_job_info(existing: str | dict | None, **updates: Any) -> dict[str, Any]:
    merged = parse_job_info(existing)
    for key, value in updates.items():
        if value is None:
            merged.pop(key, None)
        else:
            merged[key] = value
    return merged
