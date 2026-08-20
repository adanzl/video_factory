from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import requests

from app.services.llm.llm_agnes import (
    AgnesApiKey,
    AgnesContentPolicyError,
    AgnesQuotaExceeded,
    agnes_alternate_host_url,
    agnes_api_keys,
    agnes_quota_exceeded_from_exception,
    is_agnes_content_policy,
    is_agnes_quota_exceeded,
    raise_if_agnes_content_policy,
    raise_if_agnes_quota,
)


def test_agnes_alternate_host_url() -> None:
    com = "https://apihub.agnes-ai.com/v1/images/generations"
    cn = "https://apihub.agnes-ai.cn/v1/images/generations"
    assert agnes_alternate_host_url(com) == cn
    assert agnes_alternate_host_url(cn) == com
    assert agnes_alternate_host_url("https://example.com/v1") is None
    assert agnes_alternate_host_url(
        "https://apihub.agnes-ai.com/v1/chat/completions"
    ) == "https://apihub.agnes-ai.cn/v1/chat/completions"
    assert agnes_alternate_host_url(
        "https://apihub.agnes-ai.cn/v1/videos"
    ) == "https://apihub.agnes-ai.com/v1/videos"


def test_agnes_api_base_from_url() -> None:
    from app.services.llm.llm_agnes import agnes_api_base_from_url

    assert agnes_api_base_from_url(
        "https://apihub.agnes-ai.com/v1/chat/completions"
    ) == "https://apihub.agnes-ai.com/v1"
    assert agnes_api_base_from_url(
        "https://apihub.agnes-ai.cn/v1/videos"
    ) == "https://apihub.agnes-ai.cn/v1"


def test_agnes_api_keys_primary_first_then_free() -> None:
    settings = SimpleNamespace(
        agnes_api_key="main-key",
        agnes_free_api_key="free-key",
    )
    keys = agnes_api_keys(settings)
    assert keys == [
        AgnesApiKey("primary", "main-key"),
        AgnesApiKey("free", "free-key"),
    ]


def test_agnes_api_keys_free_only() -> None:
    settings = SimpleNamespace(
        agnes_api_key=None,
        agnes_free_api_key="free-key",
    )
    keys = agnes_api_keys(settings)
    assert keys == [AgnesApiKey("free", "free-key")]


def test_agnes_api_keys_dedup_same_value() -> None:
    settings = SimpleNamespace(
        agnes_api_key="same-key",
        agnes_free_api_key="same-key",
    )
    keys = agnes_api_keys(settings)
    assert keys == [AgnesApiKey("primary", "same-key")]


def test_is_agnes_quota_exceeded_status_and_keywords() -> None:
    assert is_agnes_quota_exceeded(status_code=429)
    assert is_agnes_quota_exceeded(status_code=402)
    assert is_agnes_quota_exceeded(message="daily quota exceeded")
    assert is_agnes_quota_exceeded(body={"error": {"code": "insufficient_balance", "message": "余额不足"}})
    assert not is_agnes_quota_exceeded(status_code=500, message="internal server error")


def test_raise_if_agnes_quota_raises() -> None:
    with pytest.raises(AgnesQuotaExceeded):
        raise_if_agnes_quota(status_code=429)


def test_is_agnes_content_policy() -> None:
    body = {
        "error": {
            "message": "Unable to generate this content.",
            "type": "invalid_request_error",
            "param": "prompt",
            "code": "content_policy_violation",
        }
    }
    assert is_agnes_content_policy(body=body)
    assert not is_agnes_content_policy(body={"error": {"code": "invalid_prompt"}})


def test_raise_if_agnes_content_policy_raises() -> None:
    body = {"error": {"code": "content_policy_violation", "message": "blocked"}}
    with pytest.raises(AgnesContentPolicyError, match="content_policy_violation"):
        raise_if_agnes_content_policy(status_code=400, body=body)


def test_agnes_quota_exceeded_from_http_error() -> None:
    response = MagicMock()
    response.status_code = 403
    response.json.return_value = {"error": {"message": "quota exceeded"}}
    exc = requests.HTTPError(response=response)
    assert agnes_quota_exceeded_from_exception(exc)
