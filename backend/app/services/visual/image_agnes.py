"""Agnes AI 文生图 ImageProvider（OpenAI-compatible /v1/images/generations）。"""

from __future__ import annotations

import base64
import logging
import threading
import time
from pathlib import Path

import requests

from app.config import get_settings
from app.services.visual.image_mock import MockImageProvider
from app.services.visual.visual_mgr import ImageProvider

logger = logging.getLogger(__name__)

_RETRYABLE = {429, 500, 502, 503, 504}


def _to_agnes_size(size: str) -> str:
    """项目内 720*1280 → Agnes API 720x1280。"""
    return size.strip().lower().replace("*", "x")


class AgnesImageProvider(ImageProvider):
    _submit_lock = threading.Lock()

    def __init__(self) -> None:
        settings = get_settings()
        self._api_key = settings.agnes_api_key
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
        headers: dict | None = None,
        json: dict | None = None,
        max_retries: int | None = None,
        timeout: int = 120,
    ) -> requests.Response:
        retries = max_retries if max_retries is not None else self._http_max_retries
        h = headers or {}
        last_exc: Exception | None = None
        for attempt in range(retries):
            try:
                resp = requests.request(method,
                                        url,
                                        headers=h,
                                        json=json,
                                        timeout=timeout)
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
                resp.raise_for_status()
                return resp
            except requests.RequestException as exc:
                last_exc = exc
                wait = min(2**attempt * 2, 60)
                logger.warning("agnes request error: %s, retry in %ss", exc,
                               wait)
                time.sleep(wait)
        if last_exc:
            raise last_exc
        raise RuntimeError(
            f"agnes request failed after {retries} retries: {url}")

    @staticmethod
    def _extract_image(body: dict) -> tuple[str | None, bytes | None]:
        if body.get("error"):
            err = body["error"]
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

    def generate(self,
                 prompt: str,
                 output_path: Path,
                 *,
                 size: str | None = None) -> Path:
        size = size or self._default_size
        agnes_size = _to_agnes_size(size)
        if not self._api_key:
            return self._fallback.generate(prompt, output_path, size=size)
        self._throttle_submit()
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self._model,
            "prompt": prompt,
            "size": agnes_size,
            "extra_body": {
                "response_format": "url"
            },
        }
        logger.info(
            "agnes request: %s, prompt_chars=%s, %s",
            self.describe_params(size=size),
            len(prompt),
            prompt,
        )
        try:
            resp = self._request(
                "POST",
                self._generation_url,
                headers=headers,
                json=payload,
            )
            image_url, image_bytes = self._extract_image(resp.json())
            output_path.parent.mkdir(parents=True, exist_ok=True)
            if image_bytes is not None:
                output_path.write_bytes(image_bytes)
                return output_path
            if not image_url:
                raise RuntimeError(
                    "agnes response missing image url or b64_json")
            img = requests.get(image_url, timeout=120)
            img.raise_for_status()
            output_path.write_bytes(img.content)
            return output_path
        except Exception as exc:
            logger.error("agnes generate failed: %s", exc)
            if get_settings().mock_mode:
                return self._fallback.generate(prompt, output_path, size=size)
            raise
