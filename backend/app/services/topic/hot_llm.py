"""热搜流水线共用 LLM 调用。"""

from __future__ import annotations

import json
from typing import Any

from app.config import get_settings


def extract_items_array(raw: Any, *, field: str = "items") -> list[dict[str, Any]]:
    """兼容 LLM 返回 {items: [...]} 或直接返回 [...]。"""
    if isinstance(raw, list):
        rows = raw
    elif isinstance(raw, dict):
        rows = raw.get(field)
        if rows is None and field == "items":
            for key in ("results", "data", "topics"):
                candidate = raw.get(key)
                if isinstance(candidate, list):
                    rows = candidate
                    break
    else:
        rows = None
    if not isinstance(rows, list):
        raise ValueError(f"LLM response missing {field} array")
    return [row for row in rows if isinstance(row, dict)]


def chat_json(system: str, user: str, *, max_tokens: int = 4096) -> Any:
    settings = get_settings()
    if settings.mock_mode:
        raise RuntimeError("mock_mode 下不应调用 chat_json")

    import requests

    resp = requests.post(
        f"{settings.deepseek_base_url.rstrip('/')}/chat/completions",
        headers={
            "Authorization": f"Bearer {settings.deepseek_api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": settings.deepseek_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "response_format": {"type": "json_object"},
            "max_tokens": max_tokens,
        },
        timeout=180,
    )
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"]
    return json.loads(content)
