"""通义万相图生视频 ClipProvider（wanx2.1-i2v 系列）。"""  # cSpell: disable-line

from __future__ import annotations

import base64
import logging
import mimetypes
import threading
import time
from pathlib import Path

import requests

from app.config import get_settings
from app.services.media.clip.mgr import ClipProvider, cleanup_overlay_paths, prepare_subtitle_overlays
from app.services.media.clip.render import fit_video_duration, video_to_clip_timed_overlays

logger = logging.getLogger(__name__)

_SUBMIT_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/video-generation/video-synthesis"
_RETRYABLE = {429, 500, 502, 503, 504}
_DEFAULT_MOTION_PROMPT = "轻微镜头运动，画面自然流畅，科普讲解风格"


class WanClipProvider(ClipProvider):
    _submit_lock = threading.Lock()

    def __init__(self) -> None:
        settings = get_settings()
        self._api_key = settings.dashscope_api_key
        self._model = settings.wan_i2v_model
        self._resolution = settings.wan_i2v_resolution
        self._prompt_extend = settings.wan_i2v_prompt_extend
        self._submit_interval = settings.clip_submit_interval_sec

    def _throttle_submit(self) -> None:
        with self._submit_lock:
            elapsed = time.monotonic() - self._last_submit_at
            if elapsed < self._submit_interval:
                time.sleep(self._submit_interval - elapsed)
            self._last_submit_at = time.monotonic()

    _last_submit_at = 0.0

    def _request(
        self,
        method: str,
        url: str,
        *,
        headers: dict | None = None,
        json: dict | None = None,
        max_retries: int = 6,
        timeout: int = 120,
    ) -> requests.Response:
        h = headers or {}
        last_exc: Exception | None = None
        for attempt in range(max_retries):
            try:
                resp = requests.request(method, url, headers=h, json=json, timeout=timeout)
                if resp.status_code in _RETRYABLE:
                    wait = min(2**attempt * 2, 60)
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
                wait = min(2**attempt * 2, 60)
                logger.warning("dashscope request error: %s, retry in %ss", exc, wait)
                time.sleep(wait)
        if last_exc:
            raise last_exc
        raise RuntimeError(f"dashscope request failed after {max_retries} retries: {url}")

    @staticmethod
    def _encode_image(path: Path) -> str:
        mime, _ = mimetypes.guess_type(str(path))
        mime = mime or "image/png"
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        return f"data:{mime};base64,{encoded}"

    @staticmethod
    def _pick_api_duration(target_sec: float) -> int:
        if target_sec <= 3:
            return 3
        if target_sec <= 4:
            return 4
        return 5

    def _generate_raw(
        self,
        image_path: Path,
        prompt: str,
        output_path: Path,
        *,
        duration: int,
    ) -> Path:
        if not self._api_key:
            raise RuntimeError("DASHSCOPE_API_KEY 未配置，无法调用万相图生视频")

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "X-DashScope-Async": "enable",
        }
        payload = {
            "model": self._model,
            "input": {
                "img_url": self._encode_image(image_path),
                "prompt": prompt,
            },
            "parameters": {
                "resolution": self._resolution,
                "duration": duration,
                "prompt_extend": self._prompt_extend,
            },
        }
        self._throttle_submit()
        resp = self._request("POST", _SUBMIT_URL, headers=headers, json=payload)
        body = resp.json()
        if body.get("code"):
            raise RuntimeError(f"wan i2v submit error: {body.get('code')} - {body.get('message')}")
        task_id = body["output"]["task_id"]

        state = "PENDING"
        for _ in range(120):
            status_resp = self._request(
                "GET",
                f"https://dashscope.aliyuncs.com/api/v1/tasks/{task_id}",
                headers={"Authorization": f"Bearer {self._api_key}"},
            )
            poll = status_resp.json()
            if poll.get("code"):
                raise RuntimeError(f"wan i2v poll error: {poll.get('code')} - {poll.get('message')}")
            output = poll.get("output", {})
            state = output.get("task_status", "UNKNOWN")
            if state == "SUCCEEDED":
                video_url = output.get("video_url")
                if not video_url:
                    raise RuntimeError(f"wan i2v task {task_id} succeeded but missing video_url")
                video = requests.get(video_url, timeout=120)
                video.raise_for_status()
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(video.content)
                return output_path
            if state in {"FAILED", "CANCELED"}:
                raise RuntimeError(
                    f"wan i2v task {task_id} {state}: "
                    f"{output.get('code')} - {output.get('message')}"
                )
            time.sleep(3)
        raise RuntimeError(f"wan i2v task {task_id} timeout, last state={state}")

    def build_segment_clip(
        self,
        *,
        image_path: Path,
        subtitle_cues: list[tuple[str, float]],
        output_path: Path,
        motion_preset: str,
        work_dir: Path,
        segment_index: int,
        motion_prompt: str | None = None,
    ) -> Path:
        _ = motion_preset
        t0 = time.time()
        total_duration, overlay_windows, overlay_paths = prepare_subtitle_overlays(
            subtitle_cues=subtitle_cues,
            work_dir=work_dir,
            segment_index=segment_index,
        )
        if total_duration <= 0:
            raise ValueError(f"segment {segment_index} has zero duration")

        prompt = (motion_prompt or "").strip() or _DEFAULT_MOTION_PROMPT
        api_duration = self._pick_api_duration(total_duration)
        raw_path = work_dir / f"{segment_index}.wan_raw.mp4"
        fitted_path = work_dir / f"{segment_index}.wan_fit.mp4"

        logger.info("clip %s: submitting i2v (duration=%s, motion=%s...)", segment_index, api_duration, prompt[:60])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._generate_raw(
                image_path,
                prompt,
                raw_path,
                duration=api_duration,
            )
            logger.info("clip %s: raw done, fitting to %.1fs", segment_index, total_duration)
            fit_video_duration(raw_path, fitted_path, total_duration)
            logger.info("clip %s: overlaying %s subtitles", segment_index, len(overlay_windows))
            if overlay_windows:
                video_to_clip_timed_overlays(
                    fitted_path,
                    overlay_windows,
                    output_path,
                    total_duration,
                )
            else:
                fitted_path.replace(output_path)
        finally:
            cleanup_overlay_paths(overlay_paths)
            raw_path.unlink(missing_ok=True)
            if fitted_path.exists() and fitted_path != output_path:
                fitted_path.unlink(missing_ok=True)
        elapsed = time.time() - t0
        logger.info("clip %s: done in %.1fs", segment_index, elapsed)
        return output_path
