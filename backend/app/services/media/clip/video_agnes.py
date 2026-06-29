"""Agnes AI 文生视频 ClipProvider（agnes-video-v2.0）。"""

from __future__ import annotations

import logging
import math
import threading
import time
from pathlib import Path
from urllib.parse import urlencode

import requests

from app.config import get_settings
from app.services.media.clip.mgr import ClipProvider, clip_mgr
from app.services.media.clip.render import fit_video_duration, video_to_clip_timed_overlays
from app.services.media.ffmpeg_utils import ffmpeg_cmd_start, probe_duration, run_ffmpeg
from app.services.visual.agnes_api import (
    AgnesApiKey,
    AgnesQuotaExceeded,
    agnes_api_keys,
    agnes_auth_header,
    agnes_quota_exceeded_from_exception,
    raise_if_agnes_quota,
)

logger = logging.getLogger(__name__)

_RETRYABLE = {500, 502, 503, 504}


def _backoff_seconds(
    attempt: int,
    *,
    is_timeout: bool = False,
) -> float:
    if is_timeout:
        return min(45.0 + attempt * 30.0, 180.0)
    return min(2**attempt * 2, 60.0)
_DEFAULT_MOTION_PROMPT = (
    "镜头固定或极轻微缓慢推进，主体清晰稳定，画面平滑无抖动，科普讲解风格"
)
_MAX_FRAMES = 441
_MIN_FRAMES = 81


def _pick_num_frames(target_sec: float, frame_rate: int) -> int:
    need = max(_MIN_FRAMES, int(math.ceil(target_sec * frame_rate)))
    return min(_MAX_FRAMES, 8 * math.ceil((need - 1) / 8) + 1)


def _merge_t2v_prompt(image_prompt: str | None, motion_prompt: str | None) -> str:
    """按 [场景]+[动效/运镜]+[风格] 结构合成一段连贯的 t2v prompt。"""
    parts = [p for p in [image_prompt, motion_prompt] if p and p.strip()]
    return "，".join(parts) if parts else _DEFAULT_MOTION_PROMPT


def _agnes_api_root(base_url: str) -> str:
    cleaned = base_url.rstrip("/")
    if cleaned.endswith("/v1"):
        return cleaned[:-3]
    return cleaned.rsplit("/", 1)[0]


class AgnesClipProvider(ClipProvider):
    _submit_lock = threading.Lock()
    _last_submit_at = 0.0

    def __init__(self) -> None:
        settings = get_settings()
        base = settings.agnes_api_base_url.rstrip("/")
        self._create_url = f"{base}/videos"
        self._poll_root = _agnes_api_root(base)
        self._model = settings.agnes_video_model
        self._video_width = settings.agnes_video_width
        self._video_height = settings.agnes_video_height
        self._frame_rate = settings.agnes_video_frame_rate
        self._submit_interval = settings.agnes_submit_interval_sec
        self._http_max_retries = settings.agnes_http_max_retries
        self._connect_timeout = settings.agnes_http_connect_timeout_sec
        self._submit_read_timeout = settings.agnes_http_submit_read_timeout_sec
        self._poll_read_timeout = settings.agnes_http_poll_read_timeout_sec
        self._download_timeout = settings.agnes_video_download_timeout_sec
        self._task_max_retries = settings.agnes_video_task_max_retries
        self._submit_max_retries = settings.agnes_video_submit_max_retries
        self._poll_max_attempts = settings.agnes_video_poll_max_attempts
        self._poll_interval_sec = settings.agnes_video_poll_interval_sec

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
        timeout: float | tuple[float, float] | None = None,
        label: str = "request",
    ) -> requests.Response:
        retries = max_retries if max_retries is not None else self._http_max_retries
        if label == "submit" and max_retries is None:
            retries = self._submit_max_retries
        h = headers or {}
        if timeout is None:
            read_timeout = (
                self._submit_read_timeout
                if label == "submit"
                else self._poll_read_timeout
            )
            req_timeout = (self._connect_timeout, read_timeout)
        else:
            req_timeout = timeout
        last_exc: Exception | None = None
        for attempt in range(retries):
            try:
                resp = requests.request(
                    method, url, headers=h, json=json, timeout=req_timeout
                )
                if resp.status_code in _RETRYABLE:
                    wait = _backoff_seconds(attempt)
                    logger.warning(
                        "agnes %s %s %s, retry %s/%s in %ss",
                        label,
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
            except requests.Timeout as exc:
                last_exc = exc
                wait = _backoff_seconds(attempt, is_timeout=True)
                hint = ""
                if label == "submit":
                    hint = "（异步 API 提交应秒级返回 video_id）"
                logger.warning(
                    "agnes %s %s %s read timeout%s: %s, retry %s/%s in %ss",
                    label,
                    method,
                    url,
                    hint,
                    exc,
                    attempt + 1,
                    retries,
                    wait,
                )
                time.sleep(wait)
            except requests.RequestException as exc:
                last_exc = exc
                if agnes_quota_exceeded_from_exception(exc):
                    raise AgnesQuotaExceeded(str(exc)) from exc
                wait = _backoff_seconds(attempt)
                if isinstance(exc, requests.HTTPError) and exc.response is not None:
                    try:
                        body = exc.response.text[:500]
                    except Exception:
                        body = "<unreadable>"
                    logger.warning(
                        "agnes %s %s %s error: %s body=%s, retry %s/%s in %ss",
                        label,
                        method,
                        url,
                        exc,
                        body,
                        attempt + 1,
                        retries,
                        wait,
                    )
                else:
                    logger.warning(
                        "agnes %s %s %s error: %s, retry %s/%s in %ss",
                        label,
                        method,
                        url,
                        exc,
                        attempt + 1,
                        retries,
                        wait,
                    )
                time.sleep(wait)
        if last_exc:
            raise last_exc
        raise RuntimeError(f"agnes request failed after {retries} retries: {url}")

    def _extract_video_url(self, body: dict) -> str | None:
        for key in ("remixed_from_video_id", "video_url", "url"):
            value = body.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        output = body.get("output")
        if isinstance(output, dict):
            for key in ("video_url", "url"):
                value = output.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        return None

    def _generate_raw_with_key(
        self,
        api_key: AgnesApiKey,
        prompt: str,
        output_path: Path,
        *,
        width: int,
        height: int,
        num_frames: int,
    ) -> Path:
        headers = agnes_auth_header(api_key.value, extra={"Connection": "close"})
        payload = {
            "model": self._model,
            "prompt": prompt,
            "width": width,
            "height": height,
            "size": f"{width}x{height}",
            "num_frames": num_frames,
            "frame_rate": self._frame_rate,
        }
        logger.info(
            "agnes t2v submit (%s key): model=%s frames=%s fps=%s size=%sx%s prompt_chars=%s",
            api_key.label,
            self._model,
            num_frames,
            self._frame_rate,
            width,
            height,
            len(prompt),
        )
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
            except AgnesQuotaExceeded:
                raise
            except RuntimeError as exc:
                last_exc = exc
                msg = str(exc)
                if agnes_quota_exceeded_from_exception(exc):
                    raise AgnesQuotaExceeded(msg) from exc
                if attempt >= max_attempts - 1 or not any(
                    token in msg.lower()
                    for token in (
                        "failed",
                        "timeout",
                        "429",
                        "rate limit",
                        "too many",
                    )
                ):
                    raise
                wait = 10 * (attempt + 1)
                logger.warning(
                    "agnes t2v attempt %s/%s failed, retry in %ss: %s",
                    attempt + 1,
                    max_attempts,
                    wait,
                    msg[:200],
                )
                time.sleep(wait)
        if last_exc:
            raise last_exc
        raise RuntimeError("agnes t2v failed without exception")

    def _generate_raw(
        self,
        prompt: str,
        output_path: Path,
        *,
        width: int,
        height: int,
        num_frames: int,
    ) -> Path:
        keys = agnes_api_keys()
        if not keys:
            raise RuntimeError("AGNES_FREE_API_KEY / AGNES_API_KEY 未配置，无法调用 Agnes 文生视频")

        last_exc: Exception | None = None
        for idx, key in enumerate(keys):
            try:
                return self._generate_raw_with_key(
                    key,
                    prompt,
                    output_path,
                    width=width,
                    height=height,
                    num_frames=num_frames,
                )
            except AgnesQuotaExceeded as exc:
                last_exc = exc
                if idx < len(keys) - 1:
                    logger.warning(
                        "agnes %s key quota/rate limit exceeded, switching to backup",
                        key.label,
                    )
                    continue
                raise
            except RuntimeError as exc:
                if agnes_quota_exceeded_from_exception(exc) and idx < len(keys) - 1:
                    logger.warning(
                        "agnes %s key quota/rate limit exceeded, switching to backup",
                        key.label,
                    )
                    last_exc = exc
                    continue
                raise

        if last_exc:
            raise last_exc
        raise RuntimeError("agnes t2v failed without exception")

    def _submit_task(self, *, headers: dict, payload: dict) -> tuple[str | None, str | None, str, dict]:
        """异步提交：仅创建任务，立即返回 video_id / task_id。"""
        resp = self._request(
            "POST", self._create_url, headers=headers, json=payload, label="submit"
        )
        body = resp.json()
        if body.get("error"):
            err = body["error"]
            raise_if_agnes_quota(body=body, message=str(err))
            if isinstance(err, dict):
                raise RuntimeError(
                    f"agnes t2v submit error: {err.get('code')} - {err.get('message')}"
                )
            raise RuntimeError(f"agnes t2v submit error: {err}")

        video_id = body.get("video_id")
        if isinstance(video_id, str):
            video_id = video_id.strip() or None
        else:
            video_id = None
        task_id = body.get("task_id") or body.get("id")
        if isinstance(task_id, str):
            task_id = task_id.strip() or None
        else:
            task_id = None
        if not video_id and not task_id:
            raise RuntimeError(f"agnes t2v submit missing task id: {body}")

        state = str(body.get("status") or "queued")
        logger.info(
            "agnes t2v task queued (async): video_id=%s task_id=%s status=%s",
            video_id or "-",
            task_id or "-",
            state,
        )
        return video_id, task_id, state, body

    def _download_video(self, poll: dict, output_path: Path, task_label: str) -> Path:
        video_url = self._extract_video_url(poll)
        if not video_url:
            raise RuntimeError(f"agnes t2v task {task_label} completed but missing video url")
        video = requests.get(
            video_url,
            timeout=(self._connect_timeout, self._download_timeout),
        )
        video.raise_for_status()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(video.content)
        return output_path

    def _poll_task(
        self,
        *,
        headers: dict,
        video_id: str | None,
        task_id: str | None,
        output_path: Path,
    ) -> Path:
        """轮询异步任务，直到 completed / failed 或超时。"""
        task_label = video_id or task_id or "unknown"
        state = "queued"
        for poll_idx in range(self._poll_max_attempts):
            time.sleep(self._poll_interval_sec)
            if video_id:
                query = urlencode({"video_id": video_id})
                # cSpell: disable-next-line
                poll_url = f"{self._poll_root}/agnesapi?{query}"
            elif task_id:
                poll_url = f"{self._create_url}/{task_id}"
            else:
                raise RuntimeError("agnes poll missing both video_id and task_id")
            poll_resp = self._request(
                "GET",
                poll_url,
                headers={**headers, "Connection": "close"},
                label="poll",
            )
            poll = poll_resp.json()
            if poll.get("error"):
                err = poll["error"]
                raise_if_agnes_quota(body=poll, message=str(err))
                if isinstance(err, dict):
                    raise RuntimeError(
                        f"agnes t2v poll error: {err.get('code')} - {err.get('message')}"
                    )
                raise RuntimeError(f"agnes t2v poll error: {err}")

            state = str(poll.get("status") or "unknown")
            if poll_idx % 6 == 0 and state not in {"completed", "failed"}:
                logger.info(
                    "agnes t2v task %s polling... state=%s (~%ss)",
                    task_label,
                    state,
                    int((poll_idx + 1) * self._poll_interval_sec),
                )
            if state == "completed":
                return self._download_video(poll, output_path, task_label)
            if state == "failed":
                err = poll.get("error")
                detail = err if isinstance(err, str) else repr(err)
                raise RuntimeError(f"agnes t2v task {task_label} failed: {detail}")

        raise RuntimeError(f"agnes t2v task {task_label} timeout, last state={state}")

    def _submit_and_poll(
        self,
        *,
        headers: dict,
        payload: dict,
        output_path: Path,
    ) -> Path:
        video_id, task_id, state, body = self._submit_task(headers=headers, payload=payload)
        if state == "completed":
            return self._download_video(
                body,
                output_path,
                video_id or task_id or "unknown",
            )
        return self._poll_task(
            headers=headers,
            video_id=video_id,
            task_id=task_id,
            output_path=output_path,
        )

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
    ) -> Path:
        _ = motion_preset
        _ = image_path
        t0 = time.time()
        total_duration, overlay_windows, overlay_paths = clip_mgr.prepare_subtitle_overlays(
            subtitle_cues=subtitle_cues,
            work_dir=work_dir,
            segment_index=segment_index,
            width=width,
            height=height,
        )
        if total_duration <= 0:
            raise ValueError(f"segment {segment_index} has zero duration")

        clip_width = width or get_settings().video_width
        clip_height = height or get_settings().video_height
        prompt = _merge_t2v_prompt(image_prompt, motion_prompt)
        logger.info("segment %s: total_duration=%.2fs n_cues=%s", segment_index, total_duration, len(subtitle_cues))
        num_frames = _pick_num_frames(total_duration, self._frame_rate)
        raw_path = work_dir / f"{segment_index}.agnes_raw.mp4"
        fitted_path = work_dir / f"{segment_index}.agnes_fit.mp4"

        logger.info(
            "clip %s: submitting agnes t2v (frames=%s, fps=%s, dur_target=%.1fs, prompt=%s...)",
            segment_index,
            num_frames,
            self._frame_rate,
            total_duration,
            prompt[:80],
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._generate_raw(
                prompt,
                raw_path,
                width=self._video_width,
                height=self._video_height,
                num_frames=num_frames,
            )
            logger.info("clip %s: raw done, fitting to %.1fs", segment_index, total_duration)
            raw_dur = probe_duration(raw_path)
            if raw_dur > 0 and total_duration > raw_dur * 1.15:
                loop = math.ceil(total_duration / raw_dur) - 1
                looped = work_dir / f"{segment_index}.agnes_loop.mp4"
                run_ffmpeg([
                    *ffmpeg_cmd_start(hwaccel=False),
                    "-stream_loop", str(loop),
                    "-i", str(raw_path),
                    "-c", "copy",
                    "-y", str(looped),
                ])
                raw_path = looped
            fit_video_duration(
                raw_path,
                fitted_path,
                total_duration,
                width=clip_width,
                height=clip_height,
            )
            logger.info("clip %s: overlaying %s subtitles", segment_index, len(overlay_windows))
            if overlay_windows:
                video_to_clip_timed_overlays(
                    fitted_path,
                    overlay_windows,
                    output_path,
                    total_duration,
                    width=clip_width,
                    height=clip_height,
                )
            else:
                fitted_path.replace(output_path)
        finally:
            clip_mgr.cleanup_overlay_paths(overlay_paths)
            raw_path.unlink(missing_ok=True)
            if fitted_path.exists() and fitted_path != output_path:
                fitted_path.unlink(missing_ok=True)
        elapsed = time.time() - t0
        logger.info("clip %s: done in %.1fs", segment_index, elapsed)
        return output_path
