from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

import requests

from app.config import get_settings
from app.services.segment.image.image_mock import MockImageProvider
from app.services.segment.image.image_mgr import ImageProvider

logger = logging.getLogger(__name__)

_ASYNC_SUBMIT_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text2image/image-synthesis"
_SYNC_GENERATION_URL = (
    "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
)
_RETRYABLE = {429, 500, 502, 503, 504}

_SYNC_MODELS = frozenset({"wan2.6-t2i", "wan2.5-t2i-preview", "wan2.2-t2i-plus", "wan2.2-t2i-flash"})


class WanImageProvider(ImageProvider):
    _submit_lock = threading.Lock()

    def __init__(self) -> None:
        settings = get_settings()
        self._api_key = settings.dashscope_api_key
        self._model = settings.wan_model
        self._default_size = settings.wan_image_size
        self._submit_interval = settings.image_submit_interval_sec
        self._prompt_extend = settings.wan_prompt_extend
        self._fallback = MockImageProvider()
        self._last_submit_at = 0.0
        self._use_sync = self._model in _SYNC_MODELS
        self._http_max_retries = settings.dashscope_http_max_retries
        self._poll_max_attempts = settings.wan_t2i_poll_max_attempts

    def describe_params(self, *, size: str | None = None) -> str:
        size = size or self._default_size
        mode = "sync" if self._use_sync else "async"
        return (
            f"provider=wan_t2i, model={self._model}, mode={mode}, size={size}, "
            f"prompt_extend={self._prompt_extend}"
        )

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
        timeout: int = 60,
    ) -> requests.Response:
        retries = max_retries if max_retries is not None else self._http_max_retries
        h = headers or {}
        last_exc: Exception | None = None
        for attempt in range(retries):
            try:
                resp = requests.request(method, url, headers=h, json=json, timeout=timeout)
                if resp.status_code in _RETRYABLE:
                    wait = min(2 ** attempt * 2, 60)
                    logger.warning(
                        "dashscope %s %s, retry %s/%s in %ss",
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
                wait = min(2 ** attempt * 2, 60)
                logger.warning("dashscope request error: %s, retry in %ss", exc, wait)
                time.sleep(wait)
        if last_exc:
            raise last_exc
        raise RuntimeError(f"dashscope request failed after {retries} retries: {url}")

    def _generate_sync(self, prompt: str, output_path: Path, *, size: str) -> Path:
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
                "n": 1,
            },
        }
        resp = self._request("POST", _SYNC_GENERATION_URL, headers=headers, json=payload, timeout=120)
        body = resp.json()
        if body.get("code"):
            raise RuntimeError(f"wan sync api error: {body.get('code')} - {body.get('message')}")
        choices = body.get("output", {}).get("choices") or []
        if not choices:
            raise RuntimeError("wan sync response missing choices")
        content = choices[0].get("message", {}).get("content") or []
        image_url = None
        for item in content:
            if isinstance(item, dict) and item.get("image"):
                image_url = item["image"]
                break
        if not image_url:
            raise RuntimeError("wan sync response missing image url")
        img = requests.get(image_url, timeout=60)
        img.raise_for_status()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(img.content)
        return output_path

    def _generate_async(self, prompt: str, output_path: Path, *, size: str) -> Path:
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
        resp = self._request("POST", _ASYNC_SUBMIT_URL, headers=headers, json=payload)
        task_id = resp.json()["output"]["task_id"]
        for _ in range(self._poll_max_attempts):
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
        raise RuntimeError(f"wan async task {task_id} {state}")

    def generate(self, prompt: str, output_path: Path, *, size: str | None = None, ref_images: list[Path] | None = None) -> Path:
        size = size or self._default_size
        if not self._api_key:
            return self._fallback.generate(prompt, output_path, size=size)
        self._throttle_submit()
        logger.info(
            "wan request: %s, prompt_chars=%s",
            self.describe_params(size=size),
            len(prompt),
        )
        try:
            if self._use_sync:
                return self._generate_sync(prompt, output_path, size=size)
            return self._generate_async(prompt, output_path, size=size)
        except Exception as exc:
            logger.error("wan generate failed: %s", exc)
            if get_settings().mock_mode:
                return self._fallback.generate(prompt, output_path, size=size)
            raise
