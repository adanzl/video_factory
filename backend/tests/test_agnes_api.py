from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import requests

from app.services.visual.agnes_api import (
    AgnesApiKey,
    AgnesQuotaExceeded,
    agnes_api_keys,
    agnes_quota_exceeded_from_exception,
    is_agnes_quota_exceeded,
    raise_if_agnes_quota,
)


def test_agnes_api_keys_free_first_then_primary() -> None:
    settings = SimpleNamespace(
        agnes_api_key="main-key",
        agnes_free_api_key="free-key",
    )
    keys = agnes_api_keys(settings)
    assert keys == [
        AgnesApiKey("free", "free-key"),
        AgnesApiKey("primary", "main-key"),
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
    assert keys == [AgnesApiKey("free", "same-key")]


def test_is_agnes_quota_exceeded_status_and_keywords() -> None:
    assert is_agnes_quota_exceeded(status_code=429)
    assert is_agnes_quota_exceeded(status_code=402)
    assert is_agnes_quota_exceeded(message="daily quota exceeded")
    assert is_agnes_quota_exceeded(body={"error": {"code": "insufficient_balance", "message": "余额不足"}})
    assert not is_agnes_quota_exceeded(status_code=500, message="internal server error")


def test_raise_if_agnes_quota_raises() -> None:
    with pytest.raises(AgnesQuotaExceeded):
        raise_if_agnes_quota(status_code=429)


def test_agnes_quota_exceeded_from_http_error() -> None:
    response = MagicMock()
    response.status_code = 403
    response.json.return_value = {"error": {"message": "quota exceeded"}}
    exc = requests.HTTPError(response=response)
    assert agnes_quota_exceeded_from_exception(exc)
