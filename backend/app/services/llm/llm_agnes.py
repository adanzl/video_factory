"""Agnes AI LLM 客户端（OpenAI 兼容 /v1/chat/completions）。"""

from __future__ import annotations

import logging
import time
from typing import Any

import requests

from app.config import get_settings
from app.services.llm.llm_deepseek import DeepSeekClient
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


class AgnesClient(DeepSeekClient):
    """复用 DeepSeekClient 业务逻辑，仅替换 HTTP 传输层。"""

    def __init__(self) -> None:
        self._requests = requests
        settings = get_settings()
        self._api_keys = agnes_api_keys(settings)
        if not self._api_keys:
            raise RuntimeError("AGNES_FREE_API_KEY / AGNES_API_KEY 未配置，无法使用 Agnes LLM")
        self._base_url = settings.agnes_api_base_url.rstrip("/")
        self._model = settings.agnes_llm_model
        self._max_tokens_default = settings.agnes_llm_max_tokens
        self._http_max_retries = settings.agnes_http_max_retries
        self._connect_timeout = settings.agnes_http_connect_timeout_sec
        self._read_timeout = settings.agnes_http_submit_read_timeout_sec

    def _build_chat_payload(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int,
    ) -> dict[str, Any]:
        return {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }

    def _post_chat(self, api_key: AgnesApiKey, payload: dict[str, Any]) -> requests.Response:
        url = f"{self._base_url}/chat/completions"
        headers = agnes_auth_header(api_key.value)
        timeout = (self._connect_timeout, self._read_timeout)
        last_exc: Exception | None = None
        for attempt in range(self._http_max_retries):
            try:
                resp = self._requests.post(url, headers=headers, json=payload, timeout=timeout)
                if resp.status_code in _RETRYABLE:
                    wait = min(2**attempt * 2, 60)
                    logger.warning(
                        "agnes llm %s %s, retry %s/%s in %ss",
                        resp.status_code,
                        url,
                        attempt + 1,
                        self._http_max_retries,
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
        raise RuntimeError(f"agnes llm request failed after {self._http_max_retries} retries: {url}")

    def _chat(self, system: str, user: str, *, max_tokens: int | None = None) -> tuple[str, str | None]:
        limit = self._max_tokens_default if max_tokens is None else max_tokens
        payload = self._build_chat_payload(system=system, user=user, max_tokens=limit)
        last_exc: Exception | None = None
        for idx, api_key in enumerate(self._api_keys):
            try:
                resp = self._post_chat(api_key, payload)
                choice = resp.json()["choices"][0]
                finish = choice.get("finish_reason")
                content = choice.get("message", {}).get("content") or ""
                if finish == "length":
                    logger.warning(
                        "Agnes LLM response truncated (finish_reason=length), "
                        "max_tokens=%d model=%s",
                        limit,
                        self._model,
                    )
                return content, finish
            except AgnesQuotaExceeded as exc:
                last_exc = exc
                if idx < len(self._api_keys) - 1:
                    logger.warning(
                        "agnes llm %s key quota/rate limit exceeded, switching to backup",
                        api_key.label,
                    )
                    continue
                raise
            except Exception as exc:
                if agnes_quota_exceeded_from_exception(exc) and idx < len(self._api_keys) - 1:
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
