"""Agnes AI API 公共逻辑：免费/付费 API Key 与配额超限检测。"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

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
