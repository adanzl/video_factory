from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

import requests

from app.config import get_settings
from app.services.visual.image_mock import MockImageProvider
from app.services.visual.visual_mgr import ImageProvider

logger = logging.getLogger(__name__)

_SUBMIT_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text2image/image-synthesis"
_RETRYABLE = {429, 500, 502, 503, 504}


class WanImageProvider(ImageProvider):
    _submit_lock = threading.Lock()

    def __init__(self) -> None:
        settings = get_settings()
        self._api_key = settings.dashscope_api_key
        self._model = settings.wan_model
        self._default_size = settings.wan_image_size
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
                resp = requests.request(method, url, headers=h, json=json, timeout=60)
                if resp.status_code in _RETRYABLE:
                    wait = min(2 ** attempt * 2, 60)
                    logger.warning(
                        "dashscope %s %s, retry %s/%s in %ss",
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
                logger.warning("dashscope request error: %s, retry in %ss", exc, wait)
                time.sleep(wait)
        if last_exc:
            raise last_exc
        raise RuntimeError(f"dashscope request failed after {max_retries} retries: {url}")

    def generate(self, prompt: str, output_path: Path, *, size: str | None = None) -> Path:
        size = size or self._default_size
        if not self._api_key:
            return self._fallback.generate(prompt, output_path, size=size)
        self._throttle_submit()
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "X-DashScope-Async": "enable",
        }
        payload = {
            "model": self._model,
            "input": {"prompt": prompt},
            "parameters": {"size": size, "n": 1},
        }
        try:
            resp = self._request("POST", _SUBMIT_URL, headers=headers, json=payload)
            task_id = resp.json()["output"]["task_id"]
            for _ in range(90):
                status_resp = self._request(
                    "GET",
                    f"https://dashscope.aliyuncs.com/api/v1/tasks/{task_id}",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                )
                body = status_resp.json()
                state = body["output"]["task_status"]
                if state == "SUCCEEDED":
                    url = body["output"]["results"][0]["url"]
                    img = requests.get(url, timeout=60)
                    img.raise_for_status()
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    output_path.write_bytes(img.content)
                    return output_path
                if state in {"FAILED", "CANCELED"}:
                    out = body.get("output", {})
                    logger.error(
                        "wan task %s %s: %s - %s",
                        task_id,
                        state,
                        out.get("code"),
                        out.get("message"),
                    )
                    break
                time.sleep(2)
        except Exception as exc:
            logger.error("wan generate failed, fallback to mock: %s", exc)
        return self._fallback.generate(prompt, output_path, size=size)


