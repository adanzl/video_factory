"""Agnes AI 文生图 ImageProvider（OpenAI-compatible /v1/images/generations）。"""

from __future__ import annotations

import base64
import logging
import threading
import time
from pathlib import Path

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
from app.services.visual.image_mock import MockImageProvider
from app.services.visual.visual_mgr import ImageProvider

logger = logging.getLogger(__name__)

_RETRYABLE = {500, 502, 503, 504}


def _to_agnes_size(size: str) -> str:
    """项目内 720*1280 → Agnes API 720x1280。"""
    return size.strip().lower().replace("*", "x")


class AgnesImageProvider(ImageProvider):
    _submit_lock = threading.Lock()

    def __init__(self) -> None:
        settings = get_settings()
        base = settings.agnes_api_base_url.rstrip("/")
        self._generation_url = f"{base}/images/generations"
        self._model = settings.agnes_image_model
        self._default_size = settings.agnes_image_size
        self._submit_interval = settings.image_submit_interval_sec
        self._fallback = MockImageProvider()
        self._last_submit_at = 0.0
        self._http_max_retries = settings.agnes_http_max_retries

    def describe_params(self, *, size: str | None = None) -> str:
        size = size or self._default_size
        return f"provider=agnes_t2i, model={self._model}, size={size}"

    def _throttle_submit(self) -> None:
        with self._submit_lock:
            elapsed = time.monotonic() - self._last_submit_at
            if elapsed < self._submit_interval:
                time.sleep(self._submit_interval - elapsed)
            self._last_submit_at = time.monotonic()

    def _request(
        self,
        method: str,
        url: str,
        *,
        api_key: str,
        json: dict | None = None,
        max_retries: int | None = None,
        timeout: int = 120,
    ) -> requests.Response:
        retries = max_retries if max_retries is not None else self._http_max_retries
        headers = agnes_auth_header(api_key)
        last_exc: Exception | None = None
        for attempt in range(retries):
            try:
                resp = requests.request(
                    method,
                    url,
                    headers=headers,
                    json=json,
                    timeout=timeout,
                )
                if resp.status_code in _RETRYABLE:
                    wait = min(2**attempt * 2, 60)
                    logger.warning(
                        "agnes %s %s, retry %s/%s in %ss",
                        resp.status_code,
                        url,
                        attempt + 1,
                        retries,
                        wait,
                    )
                    time.sleep(wait)
                    continue
                if resp.status_code == 429:
                    body: dict | str | None = None
                    try:
                        body = resp.json()
                    except Exception:
                        body = resp.text[:500]
                    raise_if_agnes_quota(status_code=resp.status_code, body=body)
                if not resp.ok:
                    body = None
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
                logger.warning("agnes request error: %s, retry in %ss", exc, wait)
                time.sleep(wait)
        if last_exc:
            raise last_exc
        raise RuntimeError(f"agnes request failed after {retries} retries: {url}")

    @staticmethod
    def _extract_image(body: dict) -> tuple[str | None, bytes | None]:
        if body.get("error"):
            err = body["error"]
            raise_if_agnes_quota(body=body if isinstance(body, dict) else None, message=str(err))
            if isinstance(err, dict):
                raise RuntimeError(
                    f"agnes api error: {err.get('code')} - {err.get('message')}"
                )
            raise RuntimeError(f"agnes api error: {err}")
        data = body.get("data") or []
        if not data:
            return None, None
        item = data[0] if isinstance(data[0], dict) else {}
        url = item.get("url")
        b64 = item.get("b64_json")
        if isinstance(url, str) and url.strip():
            return url.strip(), None
        if isinstance(b64, str) and b64.strip():
            return None, base64.b64decode(b64)
        return None, None

    def _generate_with_key(
        self,
        api_key: AgnesApiKey,
        prompt: str,
        output_path: Path,
        *,
        size: str,
    ) -> Path:
        agnes_size = _to_agnes_size(size)
        self._throttle_submit()
        payload = {
            "model": self._model,
            "prompt": prompt,
            "size": agnes_size,
            "extra_body": {
                "response_format": "url"
            },
        }
        logger.info(
            "agnes request (%s key): %s, prompt_chars=%s, %s",
            api_key.label,
            self.describe_params(size=size),
            len(prompt),
            prompt,
        )
        resp = self._request(
            "POST",
            self._generation_url,
            api_key=api_key.value,
            json=payload,
        )
        image_url, image_bytes = self._extract_image(resp.json())
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if image_bytes is not None:
            output_path.write_bytes(image_bytes)
            return output_path
        if not image_url:
            raise RuntimeError("agnes response missing image url or b64_json")
        img = requests.get(image_url, timeout=120)
        img.raise_for_status()
        output_path.write_bytes(img.content)
        sidecar = output_path.with_name(output_path.name + ".agnes_source_url")
        sidecar.write_text(image_url.strip(), encoding="utf-8")
        return output_path

    def generate(
        self,
        prompt: str,
        output_path: Path,
        *,
        size: str | None = None,
    ) -> Path:
        size = size or self._default_size
        keys = agnes_api_keys()
        if not keys:
            return self._fallback.generate(prompt, output_path, size=size)

        last_exc: Exception | None = None
        for idx, key in enumerate(keys):
            try:
                return self._generate_with_key(key, prompt, output_path, size=size)
            except AgnesQuotaExceeded as exc:
                last_exc = exc
                if idx < len(keys) - 1:
                    logger.warning(
                        "agnes %s key quota/rate limit exceeded, switching to backup",
                        key.label,
                    )
                    continue
                raise
            except Exception as exc:
                if agnes_quota_exceeded_from_exception(exc) and idx < len(keys) - 1:
                    logger.warning(
                        "agnes %s key quota/rate limit exceeded, switching to backup",
                        key.label,
                    )
                    last_exc = exc
                    continue
                logger.error("agnes generate failed (%s key): %s", key.label, exc)
                if get_settings().mock_mode:
                    return self._fallback.generate(prompt, output_path, size=size)
                raise

        if last_exc:
            raise last_exc
        raise RuntimeError("agnes generate failed without exception")
