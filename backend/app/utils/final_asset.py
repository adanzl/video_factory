"""成片 final_path 字段：JSON { path, duration, size, cost_time }。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

__all__ = ["build_final_asset", "parse_final_asset", "resolve_final_path_file"]


def parse_final_asset(raw: Any) -> dict | None:
    if raw is None:
        return None
    if isinstance(raw, dict):
        path = raw.get("path")
        if not path:
            return None
        return {
            "path": str(path),
            "duration": raw.get("duration"),
            "size": raw.get("size"),
            "cost_time": raw.get("cost_time"),
        }
    if not isinstance(raw, str) or not raw.strip():
        return None
    text = raw.strip()
    if text.startswith("{"):
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return {"path": text, "duration": None, "size": None, "cost_time": None}
        if isinstance(data, dict) and data.get("path"):
            return {
                "path": str(data["path"]),
                "duration": data.get("duration"),
                "size": data.get("size"),
                "cost_time": data.get("cost_time"),
            }
    return {"path": text, "duration": None, "size": None, "cost_time": None}


def resolve_final_path_file(value: Any) -> str | None:
    parsed = parse_final_asset(value)
    if not parsed:
        return None
    return parsed["path"]


def build_final_asset(
    path: Path,
    *,
    duration: float,
    size: int | None = None,
    cost_time: float | None = None,
) -> dict:
    file_size = size if size is not None else path.stat().st_size
    asset = {
        "path": str(path),
        "duration": round(float(duration), 3),
        "size": int(file_size),
    }
    if cost_time is not None:
        asset["cost_time"] = round(float(cost_time), 1)
    return asset
