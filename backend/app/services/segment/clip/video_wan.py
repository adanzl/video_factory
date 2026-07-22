"""通义万相图生视频 ClipProvider（wanx2.1-i2v 系列）。"""  # cSpell: disable-line

from __future__ import annotations

import base64
import logging
import math
import mimetypes
import time
from pathlib import Path

from gevent.lock import Semaphore
import requests

from app.config import get_settings
from app.services.segment.clip.clip_mgr import ClipProvider, clip_mgr
from app.services.segment.clip.clip_render import fit_video_duration
from app.services.media.ffmpeg_utils import ffmpeg_cmd_start, probe_duration, run_ffmpeg
from app.utils.job_cancel import job_cancel

logger = logging.getLogger(__name__)

_SUBMIT_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/video-generation/video-synthesis"
_RETRYABLE = {429, 500, 502, 503, 504}
_DEFAULT_MOTION_PROMPT = "画面元素轻微自然晃动，镜头极缓推进"
_STABILITY_HINT = "画面稳定，无快速运镜"


def _stabilize_motion_prompt(prompt: str) -> str:
    text = prompt.strip()
    if not text:
        return _DEFAULT_MOTION_PROMPT
    if _STABILITY_HINT in text:
        return text
    if any(word in text for word in ("稳定", "平滑", "无抖动", "极缓", "缓慢")):
        return text
    return f"{text}，{_STABILITY_HINT}"


class WanClipProvider(ClipProvider):
    _submit_lock = Semaphore(value=1)

    def __init__(self) -> None:
        settings = get_settings()
        self._api_key = settings.dashscope_api_key
        self._model = settings.wan_i2v_model
        self._resolution = settings.wan_i2v_resolution
        self._prompt_extend = settings.wan_i2v_prompt_extend
        self._submit_interval = settings.clip_submit_interval_sec
        self._http_max_retries = settings.dashscope_http_max_retries
        self._task_max_retries = settings.wan_i2v_task_max_retries
        self._poll_max_attempts = settings.wan_i2v_poll_max_attempts
        self._active_job_id: int | None = None

    def _raise_if_job_cancelled(self) -> None:
        if self._active_job_id is not None:
            job_cancel.raise_if_cancelled(self._active_job_id)

    def _throttle_submit(self) -> None:
        self._raise_if_job_cancelled()
        with self._submit_lock:
            elapsed = time.monotonic() - self._last_submit_at
            if elapsed < self._submit_interval:
                time.sleep(self._submit_interval - elapsed)
                self._raise_if_job_cancelled()
            self._last_submit_at = time.monotonic()

    _last_submit_at = 0.0

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
                resp = requests.request(method, url, headers=h, json=json, timeout=timeout)
                if resp.status_code in _RETRYABLE:
                    wait = min(2**attempt * 2, 60)
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
                wait = min(2**attempt * 2, 60)
                logger.warning("dashscope request error: %s, retry in %ss", exc, wait)
                time.sleep(wait)
        if last_exc:
            raise last_exc
        raise RuntimeError(f"dashscope request failed after {retries} retries: {url}")

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
        last_exc: Exception | None = None
        max_attempts = max(1, self._task_max_retries)
        for attempt in range(max_attempts):
            try:
                return self._submit_and_poll(
                    headers=headers,
                    payload=payload,
                    output_path=output_path,
                )
            except RuntimeError as exc:
                last_exc = exc
                msg = str(exc)
                if attempt >= max_attempts - 1 or "FAILED" not in msg and "timeout" not in msg.lower():
                    raise
                wait = 10 * (attempt + 1)
                logger.warning(
                    "wan i2v attempt %s/%s failed, retry in %ss: %s",
                    attempt + 1,
                    max_attempts,
                    wait,
                    msg[:200],
                )
                time.sleep(wait)
        if last_exc:
            raise last_exc
        raise RuntimeError("wan i2v failed without exception")

    def _submit_and_poll(
        self,
        *,
        headers: dict,
        payload: dict,
        output_path: Path,
    ) -> Path:
        resp = self._request("POST", _SUBMIT_URL, headers=headers, json=payload)
        body = resp.json()
        if body.get("code"):
            raise RuntimeError(f"wan i2v submit error: {body.get('code')} - {body.get('message')}")
        task_id = body["output"]["task_id"]

        state = "PENDING"
        for poll_idx in range(self._poll_max_attempts):
            self._raise_if_job_cancelled()
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
            if poll_idx % 10 == 0 and state in {"PENDING", "RUNNING", "UNKNOWN"}:
                logger.info(
                    "wan i2v task %s polling... state=%s (~%ss)",
                    task_id,
                    state,
                    poll_idx * 3,
                )
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
        image_prompt: str | None = None,
        width: int | None = None,
        height: int | None = None,
        job_id: int | None = None,
    ) -> Path:
        _ = motion_preset
        _ = image_prompt
        self._active_job_id = job_id
        t0 = time.time()
        try:
            total_duration = clip_mgr.cue_total_duration(subtitle_cues)
            if total_duration <= 0:
                raise ValueError(f"segment {segment_index} has zero duration")

            prompt = _stabilize_motion_prompt(motion_prompt or "")
            api_duration = self._pick_api_duration(total_duration)
            raw_path = work_dir / f"{segment_index}.wan_raw.mp4"

            logger.info("clip %s: submitting i2v (duration=%s, motion=%s...)", segment_index, api_duration, prompt[:60])
            output_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                self._generate_raw(
                    image_path,
                    prompt,
                    raw_path,
                    duration=api_duration,
                )
                self._raise_if_job_cancelled()
                logger.info("clip %s: raw done, fitting to %.1fs", segment_index, total_duration)
                raw_dur = probe_duration(raw_path)
                if raw_dur > 0 and total_duration > raw_dur * 1.15:
                    loop = math.ceil(total_duration / raw_dur) - 1
                    looped = work_dir / f"{segment_index}.wan_loop.mp4"
                    run_ffmpeg([
                        *ffmpeg_cmd_start(hwaccel=False),
                        "-stream_loop", str(loop),
                        "-i", str(raw_path),
                        "-c", "copy",
                        "-y", str(looped),
                    ])
                    raw_path = looped
                # 字幕改在 merge 阶段 ASS 烧录
                fit_video_duration(
                    raw_path,
                    output_path,
                    total_duration,
                    width=width,
                    height=height,
                )
            finally:
                raw_path.unlink(missing_ok=True)
            elapsed = time.time() - t0
            logger.info("clip %s: done in %.1fs", segment_index, elapsed)
            return output_path
        finally:
            self._active_job_id = None
