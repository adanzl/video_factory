"""OpenCode Go：OpenAI 兼容 chat/completions，业务复用 DeepSeekClient。"""
from __future__ import annotations

import hashlib
import logging
from typing import Any

from app.config import get_settings
from app.services.llm.llm_deepseek import DeepSeekClient, _build_deepseek_chat_payload

logger = logging.getLogger(__name__)

_opencode_client_cls: type | None = None


def _session_id_for_chat(system: str, user: str) -> str:
    """同 prompt 重试复用 session，利于 OpenCode 路由与缓存。"""
    digest = hashlib.sha256(f"{system}\0{user}".encode()).hexdigest()[:32]
    return f"vf-{digest}"


def _opencode_client_class() -> type:
    global _opencode_client_cls
    if _opencode_client_cls is not None:
        return _opencode_client_cls

    class OpenCodeGoClient(DeepSeekClient):
        """复用 DeepSeekClient 业务逻辑，HTTP 走 OpenCode Go zen 网关。"""

        def __init__(self) -> None:
            super().__init__()
            settings = get_settings()
            key = settings.opencode_go_api_key
            if not key:
                raise RuntimeError(
                    "OPENCODE_GO_API_KEY 未配置，无法使用 LLM_PROVIDER=opencode_go"
                )
            self._api_key = key
            self._base_url = settings.opencode_go_base_url.rstrip("/")
            self._user_agent = settings.opencode_go_user_agent

        def _chat(
            self,
            system: str,
            user: str,
            *,
            max_tokens: int | None = None,
            json_mode: bool = True,
            thinking_enabled: bool | None = None,
            temperature: float | None = None,
            model: str | None = None,
        ) -> tuple[str, str | None]:
            settings = get_settings()
            limit = settings.deepseek_max_tokens if max_tokens is None else max_tokens
            use_thinking = (
                settings.deepseek_thinking_enabled
                if thinking_enabled is None
                else thinking_enabled
            )
            use_model = model or self._model
            headers = {
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
                "User-Agent": self._user_agent,
                "x-opencode-session": _session_id_for_chat(system, user),
            }
            resp = self._requests.post(
                f"{self._base_url}/chat/completions",
                headers=headers,
                json=_build_deepseek_chat_payload(
                    model=use_model,
                    system=system,
                    user=user,
                    max_tokens=limit,
                    thinking_enabled=use_thinking,
                    json_mode=json_mode,
                    temperature=temperature,
                ),
                timeout=300,
            )
            resp.raise_for_status()
            choice = resp.json()["choices"][0]
            finish = choice.get("finish_reason")
            content = choice.get("message", {}).get("content") or ""
            if finish == "length":
                logger.warning(
                    "OpenCode Go LLM truncated (finish_reason=length), "
                    "max_tokens=%d model=%s",
                    limit,
                    use_model,
                )
            return content, finish

    _opencode_client_cls = OpenCodeGoClient
    return OpenCodeGoClient


def __getattr__(name: str) -> Any:
    if name == "OpenCodeGoClient":
        return _opencode_client_class()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
