"""DeepSeek Chat Completions 请求体（OpenAI 兼容 HTTP）。"""

from __future__ import annotations

from typing import Any


def build_deepseek_chat_payload(
    *,
    model: str,
    system: str,
    user: str,
    max_tokens: int,
    thinking_enabled: bool,
    json_mode: bool = True,
) -> dict[str, Any]:
    """构建 chat/completions JSON；V4 默认 thinking=enabled，结构化输出须显式关闭。"""
    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": max_tokens,
        "thinking": {"type": "enabled" if thinking_enabled else "disabled"},
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    return payload
