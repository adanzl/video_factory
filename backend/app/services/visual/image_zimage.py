from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

import requests

from app.config import get_settings
from app.services.visual.image_mock import MockImageProvider

logger = logging.getLogger(__name__)

_GENERATION_URL = (
    "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
)
_RETRYABLE = {429, 500, 502, 503, 504}


class ZImageProvider:
    _submit_lock = threading.Lock()

    def __init__(self) -> None:
        settings = get_settings()
        self._api_key = settings.dashscope_api_key
        self._model = settings.z_image_model
        self._default_size = settings.z_image_size
        self._prompt_extend = settings.z_image_prompt_extend
        self._submit_interval = settings.image_submit_interval_sec
        self._fallback = MockImageProvider()
        self._last_submit_at = 0.0

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
        max_retries: int = 6,
    ) -> requests.Response:
        h = headers or {}
        last_exc: Exception | None = None
        for attempt in range(max_retries):
            try:
                resp = requests.request(method, url, headers=h, json=json, timeout=120)
                if resp.status_code in _RETRYABLE:
                    wait = min(2 ** attempt * 2, 60)
                    logger.warning(
                        "dashscope z-image %s %s, retry %s/%s in %ss",
                        resp.status_code,
                        url,
                        attempt + 1,
                        max_retries,
                        wait,
                    )
                    time.sleep(wait)
                    continue
                resp.raise_for_status()
                return resp
            except requests.RequestException as exc:
                last_exc = exc
                wait = min(2 ** attempt * 2, 60)
                logger.warning("dashscope z-image request error: %s, retry in %ss", exc, wait)
                time.sleep(wait)
        if last_exc:
            raise last_exc
        raise RuntimeError(f"dashscope z-image request failed after {max_retries} retries: {url}")

    def _extract_image_url(self, body: dict) -> str | None:
        if body.get("code"):
            logger.error("z-image api error: %s - %s", body.get("code"), body.get("message"))
            return None
        choices = body.get("output", {}).get("choices") or []
        if not choices:
            return None
        content = choices[0].get("message", {}).get("content") or []
        for item in content:
            if isinstance(item, dict) and item.get("image"):
                return item["image"]
        return None

    def generate(self, prompt: str, output_path: Path, *, size: str | None = None) -> Path:
        size = size or self._default_size
        if not self._api_key:
            return self._fallback.generate(prompt, output_path, size=size)
        self._throttle_submit()
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self._model,
            "input": {
                "messages": [
                    {
                        "role": "user",
                        "content": [{"text": prompt}],
                    }
                ]
            },
            "parameters": {
                "size": size,
                "prompt_extend": self._prompt_extend,
            },
        }
        try:
            resp = self._request("POST", _GENERATION_URL, headers=headers, json=payload)
            image_url = self._extract_image_url(resp.json())
            if not image_url:
                raise RuntimeError("z-image response missing image url")
            img = requests.get(image_url, timeout=60)
            img.raise_for_status()
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(img.content)
            return output_path
        except Exception as exc:
            logger.error("z-image generate failed, fallback to mock: %s", exc)
        return self._fallback.generate(prompt, output_path, size=size)
