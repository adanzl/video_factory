"""Agnes AI 客户端：公共 API 逻辑与 LLM（OpenAI 兼容 /v1/chat/completions）。"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Any

import requests

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

_QUOTA_STATUS = frozenset({402, 403, 429})
_QUOTA_KEYWORDS = (
    "quota",
    "limit",
    "exceeded",
    "insufficient",
    "balance",
    "credit",
    "余额",
    "限额",
    "超限",
    "额度",
    "不足",
    "rate limit",
    "too many",
)


class AgnesQuotaExceeded(RuntimeError):
    """当前 Key 配额/限流耗尽，可切换备用 Key。"""


@dataclass(frozen=True)
class AgnesApiKey:
    label: str
    value: str


def agnes_api_keys(settings: Settings | None = None) -> list[AgnesApiKey]:
    """返回 Agnes Key 列表：优先 AGNES_FREE_API_KEY，限流后切换 AGNES_API_KEY。"""
    cfg = settings or get_settings()
    keys: list[AgnesApiKey] = []
    free = cfg.agnes_free_api_key
    if free:
        keys.append(AgnesApiKey("free", free))
    primary = cfg.agnes_api_key
    if primary and primary != free:
        keys.append(AgnesApiKey("primary", primary))
    return keys


def agnes_auth_header(api_key: str, *, extra: dict[str, str] | None = None) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if extra:
        headers.update(extra)
    return headers


def _collect_error_text(
    *,
    status_code: int | None = None,
    body: dict | str | None = None,
    message: str | None = None,
) -> str:
    parts: list[str] = []
    if status_code is not None:
        parts.append(str(status_code))
    if message:
        parts.append(message)
    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict):
            code = err.get("code")
            msg = err.get("message")
            if code is not None:
                parts.append(str(code))
            if msg is not None:
                parts.append(str(msg))
        elif err is not None:
            parts.append(str(err))
        parts.append(json.dumps(body, ensure_ascii=False))
    elif isinstance(body, str) and body.strip():
        parts.append(body)
    return " ".join(parts).lower()


def is_agnes_quota_exceeded(
    *,
    status_code: int | None = None,
    body: dict | str | None = None,
    message: str | None = None,
) -> bool:
    if status_code in _QUOTA_STATUS:
        return True
    text = _collect_error_text(status_code=status_code, body=body, message=message)
    return any(keyword in text for keyword in _QUOTA_KEYWORDS)


def agnes_quota_exceeded_from_exception(exc: BaseException) -> bool:
    if isinstance(exc, AgnesQuotaExceeded):
        return True
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        body: dict | str | None = None
        try:
            body = exc.response.json()
        except Exception:
            body = exc.response.text[:500]
        return is_agnes_quota_exceeded(
            status_code=exc.response.status_code,
            body=body,
            message=str(exc),
        )
    return is_agnes_quota_exceeded(message=str(exc))


def raise_if_agnes_quota(
    *,
    status_code: int | None = None,
    body: dict | str | None = None,
    message: str | None = None,
) -> None:
    if is_agnes_quota_exceeded(status_code=status_code, body=body, message=message):
        detail = _collect_error_text(status_code=status_code, body=body, message=message)
        raise AgnesQuotaExceeded(detail or "agnes quota or rate limit exceeded")


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
