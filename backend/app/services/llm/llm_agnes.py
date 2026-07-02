"""Agnes AI LLM 客户端（OpenAI 兼容 /v1/chat/completions）。"""

from __future__ import annotations

import logging
import time
from typing import Any

import requests

from app.config import get_settings
from app.services.visual.agnes_api import (
    AgnesApiKey,
    AgnesQuotaExceeded,
    agnes_api_keys,
    agnes_auth_header,
    agnes_quota_exceeded_from_exception,
    raise_if_agnes_quota,
)

logger = logging.getLogger(__name__)

_RETRYABLE = frozenset({500, 502, 503, 504})


def _build_chat_payload(
    *,
    model: str,
    system: str,
    user: str,
    max_tokens: int,
) -> dict[str, Any]:
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
    }


def _post_chat(
    *,
    api_key: AgnesApiKey,
    base_url: str,
    payload: dict[str, Any],
    max_retries: int,
    connect_timeout: float,
    read_timeout: float,
) -> requests.Response:
    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = agnes_auth_header(api_key.value)
    timeout = (connect_timeout, read_timeout)
    last_exc: Exception | None = None
    for attempt in range(max_retries):
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
            if resp.status_code in _RETRYABLE:
                wait = min(2**attempt * 2, 60)
                logger.warning(
                    "agnes llm %s %s, retry %s/%s in %ss",
                    resp.status_code,
                    url,
                    attempt + 1,
                    max_retries,
                    wait,
                )
                time.sleep(wait)
                continue
            if not resp.ok:
                body: dict | str | None = None
                try:
                    body = resp.json()
                except Exception:
                    body = resp.text[:500]
                raise_if_agnes_quota(status_code=resp.status_code, body=body)
            resp.raise_for_status()
            return resp
        except AgnesQuotaExceeded:
            raise
        except requests.RequestException as exc:
            last_exc = exc
            if agnes_quota_exceeded_from_exception(exc):
                raise AgnesQuotaExceeded(str(exc)) from exc
            wait = min(2**attempt * 2, 60)
            logger.warning("agnes llm request error: %s, retry in %ss", exc, wait)
            time.sleep(wait)
    if last_exc:
        raise last_exc
    raise RuntimeError(f"agnes llm request failed after {max_retries} retries: {url}")


def _chat_with_key_fallback(
    *,
    system: str,
    user: str,
    max_tokens: int | None = None,
) -> tuple[str, str | None]:
    settings = get_settings()
    keys = agnes_api_keys(settings)
    if not keys:
        raise RuntimeError("AGNES_FREE_API_KEY / AGNES_API_KEY 未配置，无法使用 Agnes LLM")
    limit = settings.agnes_llm_max_tokens if max_tokens is None else max_tokens
    payload = _build_chat_payload(
        model=settings.agnes_llm_model,
        system=system,
        user=user,
        max_tokens=limit,
    )
    last_exc: Exception | None = None
    for idx, api_key in enumerate(keys):
        try:
            resp = _post_chat(
                api_key=api_key,
                base_url=settings.agnes_api_base_url,
                payload=payload,
                max_retries=settings.agnes_http_max_retries,
                connect_timeout=settings.agnes_http_connect_timeout_sec,
                read_timeout=settings.agnes_http_submit_read_timeout_sec,
            )
            choice = resp.json()["choices"][0]
            finish = choice.get("finish_reason")
            content = choice.get("message", {}).get("content") or ""
            if finish == "length":
                logger.warning(
                    "Agnes LLM response truncated (finish_reason=length), "
                    "max_tokens=%d model=%s",
                    limit,
                    settings.agnes_llm_model,
                )
            return content, finish
        except AgnesQuotaExceeded as exc:
            last_exc = exc
            if idx < len(keys) - 1:
                logger.warning(
                    "agnes llm %s key quota/rate limit exceeded, switching to backup",
                    api_key.label,
                )
                continue
            raise
        except Exception as exc:
            if agnes_quota_exceeded_from_exception(exc) and idx < len(keys) - 1:
                logger.warning(
                    "agnes llm %s key quota/rate limit exceeded, switching to backup",
                    api_key.label,
                )
                last_exc = exc
                continue
            raise
    if last_exc:
        raise last_exc
    raise RuntimeError("agnes llm chat failed without exception")


_agnes_client_cls: type | None = None


def _agnes_client_class() -> type:
    """延迟继承 DeepSeekClient，避免 import 时触发循环依赖。"""
    global _agnes_client_cls
    if _agnes_client_cls is not None:
        return _agnes_client_cls
    from app.services.llm.llm_deepseek import DeepSeekClient

    class AgnesClient(DeepSeekClient):
        """复用 DeepSeekClient 业务逻辑，HTTP 走 Agnes chat/completions。"""

        def _chat(
            self,
            system: str,
            user: str,
            *,
            max_tokens: int | None = None,
        ) -> tuple[str, str | None]:
            return _chat_with_key_fallback(system=system, user=user, max_tokens=max_tokens)

    _agnes_client_cls = AgnesClient
    return AgnesClient


def __getattr__(name: str):
    if name == "AgnesClient":
        return _agnes_client_class()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
