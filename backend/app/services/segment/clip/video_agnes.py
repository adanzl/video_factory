"""Agnes AI 图生视频 ClipProvider（agnes-video-v2.0，Data URI 输入）。"""

from __future__ import annotations

import base64
import logging
import math
import mimetypes
import re
import time
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urlencode

from gevent.lock import Semaphore
import requests

from app.config import get_settings
from app.services.segment.clip.clip_mgr import ClipProvider, clip_mgr
from app.services.segment.clip.clip_render import fit_video_duration, video_to_clip_timed_overlays
from app.services.media.ffmpeg_utils import ffmpeg_cmd_start, probe_duration, run_ffmpeg
from app.services.llm.llm_agnes import (
    AgnesApiKey,
    AgnesQuotaExceeded,
    agnes_api_keys,
    agnes_auth_header,
    agnes_quota_exceeded_from_exception,
    raise_if_agnes_quota,
)

logger = logging.getLogger(__name__)

_RETRYABLE_HTTP = frozenset({500, 502, 503, 504})
_TASK_RETRY_TOKENS = ("failed", "timeout", "429", "rate limit", "too many")
_TERMINAL_POLL_STATES = frozenset({"completed", "failed"})
_I2V_MODE = "ti2vid"
_DEFAULT_MOTION_PROMPT = (
    "画面元素轻微自然晃动，镜头固定不推近不拉远，面部表情与静图一致"
)
_STABILITY_HINT = "画面稳定，无快速运镜"
_FACE_LOCK_HINT = "面部表情与静图一致，不微笑不大笑，五官服装发型保持不变"
_CAMERA_LOCK_HINT = "镜头固定，不推近不拉远，不放大构图"
_DEFAULT_NEGATIVE_PROMPT = (
    "微笑, 大笑, 露齿笑, 开心, 嬉笑, 表情突变, 换脸, 脸部变形, "
    "扭曲, 多手指, 文字水印, "
    "快速推进, 大幅推进, 强烈变焦, 画面放大, 裁切脸部, zoom in, dolly in"
)
# 提交前去掉旧稿里的推近用语，避免 I2V 猛 zoom（勿误伤「不推近」）
_CAMERA_ZOOM_RE = re.compile(
    r"镜头(?:极缓|缓慢|轻轻|轻微|大幅|强烈)?(?:推近|推进|拉远|变焦)"
    r"|(?:极缓|缓慢|轻轻|轻微|大幅|强烈)(?:推近|推进|拉远)"
    r"|放大构图|放大画面"
    r"|slow\s*zoom(?:\s*in)?|zoom\s*in|dolly\s*in",
    re.IGNORECASE,
)
# Agnes 720p 各比例上限均为 409 帧（1080p 仅 169 帧，更长分镜靠 loop + fit 补齐）
_MAX_FRAMES = 409
_MIN_FRAMES = 81
# Agnes API 默认 1152×768 ≈ 884K 像素（720P 级别），超出会 400
_API_TARGET_PIXELS = 921_600  # 1280×720


def _resolve_api_dimensions(target_w: int, target_h: int) -> tuple[int, int]:
    """将目标画布尺寸缩放到 Agnes API 支持的 ~720P 总像素范围内，保持比例。"""
    scale = min(1.0, math.sqrt(_API_TARGET_PIXELS / (target_w * target_h)))
    api_w = int(target_w * scale) // 2 * 2  # 保证偶数
    api_h = int(target_h * scale) // 2 * 2
    return max(api_w, 2), max(api_h, 2)


def _backoff_seconds(attempt: int, *, is_timeout: bool = False) -> float:
    if is_timeout:
        return min(45.0 + attempt * 30.0, 180.0)
    return min(2**attempt * 2, 60.0)


def _stabilize_motion_prompt(prompt: str) -> str:
    """补齐 I2V 稳定性与面部锁定，并压掉推近/变焦（易裁脸）。"""
    text = prompt.strip() or _DEFAULT_MOTION_PROMPT
    text = _CAMERA_ZOOM_RE.sub("", text)
    text = re.sub(r"[，,]{2,}", "，", text).strip("，, ").strip()
    if not text:
        text = _DEFAULT_MOTION_PROMPT
    parts = [text]
    if _STABILITY_HINT not in text and not any(
        word in text for word in ("稳定", "平滑", "无抖动", "镜头固定")
    ):
        parts.append(_STABILITY_HINT)
    if not any(
        word in text
        for word in ("面部", "表情", "静图一致", "不微笑", "五官", "脸")
    ):
        parts.append(_FACE_LOCK_HINT)
    if not any(
        word in text for word in ("镜头固定", "不推近", "不拉远", "不放大")
    ):
        parts.append(_CAMERA_LOCK_HINT)
    return "，".join(parts) if len(parts) > 1 else text


def _pick_num_frames(target_sec: float, frame_rate: int) -> int:
    need = max(_MIN_FRAMES, int(math.ceil(target_sec * frame_rate)))
    return min(_MAX_FRAMES, 8 * math.ceil((need - 1) / 8) + 1)


def _encode_image_data_uri(path: Path) -> str:
    """本地分镜图 → Data URI Base64（与 agnes-image-2.1-flash 文档一致）。"""
    mime, _ = mimetypes.guess_type(str(path))
    mime = mime or "image/png"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _read_agnes_source_url(image_path: Path) -> str | None:
    """文生图若由 Agnes 返回 CDN URL，侧车文件可直接供图生视频引用。"""
    sidecar = image_path.with_name(image_path.name + ".agnes_source_url")
    if not sidecar.is_file():
        return None
    url = sidecar.read_text(encoding="utf-8").strip()
    if url.startswith(("http://", "https://")):
        return url
    return None


def _resolve_i2v_image(image_path: Path) -> str:
    source_url = _read_agnes_source_url(image_path)
    if source_url:
        logger.info("agnes i2v image: using Agnes CDN URL from sidecar (%s)", source_url[:80])
        return source_url
    logger.info(
        "agnes i2v image: using Data URI (%s, %s bytes)",
        image_path.name,
        image_path.stat().st_size,
    )
    return _encode_image_data_uri(image_path)


def _format_image_ref_for_log(image_ref: str) -> str:
    if image_ref.startswith("http"):
        return image_ref[:96]
    return f"data-uri({len(image_ref)} chars)"


def _strip_optional_str(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _response_body(resp: requests.Response) -> dict | str | None:
    try:
        return resp.json()
    except Exception:
        return resp.text[:500]


def _raise_i2v_api_error(phase: str, err: object, *, body: dict | None = None) -> None:
    raise_if_agnes_quota(body=body, message=str(err))
    if isinstance(err, dict):
        raise RuntimeError(
            f"agnes i2v {phase} error: {err.get('code')} - {err.get('message')}"
        )
    raise RuntimeError(f"agnes i2v {phase} error: {err}")


def _is_retriable_task_error(message: str) -> bool:
    lowered = message.lower()
    return any(token in lowered for token in _TASK_RETRY_TOKENS)


def _agnes_api_root(base_url: str) -> str:
    cleaned = base_url.rstrip("/")
    if cleaned.endswith("/v1"):
        return cleaned[:-3]
    return cleaned.rsplit("/", 1)[0]


def _loop_video_to_duration(
    raw_path: Path,
    *,
    work_dir: Path,
    segment_index: int,
    total_duration: float,
) -> Path:
    raw_dur = probe_duration(raw_path)
    if raw_dur <= 0 or total_duration <= raw_dur * 1.15:
        return raw_path
    loop = math.ceil(total_duration / raw_dur) - 1
    looped = work_dir / f"{segment_index}.agnes_loop.mp4"
    run_ffmpeg([
        *ffmpeg_cmd_start(hwaccel=False),
        "-stream_loop",
        str(loop),
        "-i",
        str(raw_path),
        "-c",
        "copy",
        "-y",
        str(looped),
    ])
    return looped


class AgnesClipProvider(ClipProvider):
    _submit_lock = Semaphore(value=1)
    _last_submit_at = 0.0

    def __init__(self) -> None:
        settings = get_settings()
        base = settings.agnes_api_base_url.rstrip("/")
        self._create_url = f"{base}/videos"
        self._poll_root = _agnes_api_root(base)
        self._model = settings.agnes_video_model
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
        retries = self._submit_max_retries if label == "submit" and max_retries is None else (
            max_retries if max_retries is not None else self._http_max_retries
        )
        read_timeout = self._submit_read_timeout if label == "submit" else self._poll_read_timeout
        req_timeout = timeout if timeout is not None else (self._connect_timeout, read_timeout)
        last_exc: Exception | None = None

        for attempt in range(retries):
            try:
                resp = requests.request(
                    method, url, headers=headers or {}, json=json, timeout=req_timeout
                )
                if resp.status_code in _RETRYABLE_HTTP:
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
                if resp.status_code == 429 or not resp.ok:
                    raise_if_agnes_quota(
                        status_code=resp.status_code,
                        body=_response_body(resp),
                    )
                resp.raise_for_status()
                return resp
            except AgnesQuotaExceeded:
                raise
            except requests.Timeout as exc:
                last_exc = exc
                wait = _backoff_seconds(attempt, is_timeout=True)
                hint = "（异步 API 提交应秒级返回 video_id）" if label == "submit" else ""
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
                detail = ""
                if isinstance(exc, requests.HTTPError) and exc.response is not None:
                    try:
                        detail = f" body={exc.response.text[:500]}"
                    except Exception:
                        detail = " body=<unreadable>"
                logger.warning(
                    "agnes %s %s %s error: %s%s, retry %s/%s in %ss",
                    label,
                    method,
                    url,
                    exc,
                    detail,
                    attempt + 1,
                    retries,
                    wait,
                )
                time.sleep(wait)

        if last_exc:
            raise last_exc
        raise RuntimeError(f"agnes request failed after {retries} retries: {url}")

    @staticmethod
    def _extract_video_url(body: dict) -> str | None:
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

    def _build_i2v_payload(
        self, *, prompt: str, image_ref: str, num_frames: int,
        width: int | None = None, height: int | None = None,
    ) -> dict:
        payload: dict = {
            "model": self._model,
            "prompt": prompt,
            "image": image_ref,
            "mode": _I2V_MODE,
            "num_frames": num_frames,
            "frame_rate": self._frame_rate,
            "negative_prompt": _DEFAULT_NEGATIVE_PROMPT,
        }
        if width is not None:
            payload["width"] = width
        if height is not None:
            payload["height"] = height
        return payload

    def _with_api_key_fallback(self, operation: Callable[[AgnesApiKey], Path]) -> Path:
        keys = agnes_api_keys()
        if not keys:
            raise RuntimeError("AGNES_FREE_API_KEY / AGNES_API_KEY 未配置，无法调用 Agnes 图生视频")

        last_exc: Exception | None = None
        for idx, key in enumerate(keys):
            try:
                return operation(key)
            except AgnesQuotaExceeded as exc:
                last_exc = exc
            except RuntimeError as exc:
                if not agnes_quota_exceeded_from_exception(exc):
                    raise
                last_exc = exc

            if idx >= len(keys) - 1:
                assert last_exc is not None
                raise last_exc
            logger.warning(
                "agnes %s key quota/rate limit exceeded, switching to backup",
                key.label,
            )

        raise RuntimeError("agnes i2v failed without exception")

    def _generate_raw_with_key(
        self,
        api_key: AgnesApiKey,
        image_path: Path,
        prompt: str,
        output_path: Path,
        *,
        num_frames: int,
        width: int | None = None,
        height: int | None = None,
    ) -> Path:
        image_ref = _resolve_i2v_image(image_path)
        headers = agnes_auth_header(api_key.value, extra={"Connection": "close"})
        payload = self._build_i2v_payload(
            prompt=prompt,
            image_ref=image_ref,
            num_frames=num_frames,
            width=width,
            height=height,
        )
        logger.info(
            "agnes i2v submit (%s key): model=%s frames=%s fps=%s size=%sx%s image=%s prompt_chars=%s",
            api_key.label,
            self._model,
            num_frames,
            self._frame_rate,
            width or "-",
            height or "-",
            _format_image_ref_for_log(image_ref),
            len(prompt),
        )

        self._throttle_submit()
        max_attempts = max(1, self._task_max_retries)
        last_exc: Exception | None = None
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
                if attempt >= max_attempts - 1 or not _is_retriable_task_error(msg):
                    raise
                wait = 10 * (attempt + 1)
                logger.warning(
                    "agnes i2v attempt %s/%s failed, retry in %ss: %s",
                    attempt + 1,
                    max_attempts,
                    wait,
                    msg[:200],
                )
                time.sleep(wait)

        if last_exc:
            raise last_exc
        raise RuntimeError("agnes i2v failed without exception")

    def _generate_raw(
        self,
        image_path: Path,
        prompt: str,
        output_path: Path,
        *,
        num_frames: int,
        width: int | None = None,
        height: int | None = None,
    ) -> Path:
        return self._with_api_key_fallback(
            lambda key: self._generate_raw_with_key(
                key,
                image_path,
                prompt,
                output_path,
                num_frames=num_frames,
                width=width,
                height=height,
            )
        )

    def _submit_task(
        self,
        *,
        headers: dict,
        payload: dict,
    ) -> tuple[str | None, str | None, str, dict]:
        resp = self._request(
            "POST", self._create_url, headers=headers, json=payload, label="submit"
        )
        body = resp.json()
        if body.get("error"):
            _raise_i2v_api_error("submit", body["error"], body=body)

        video_id = _strip_optional_str(body.get("video_id"))
        task_id = _strip_optional_str(body.get("task_id") or body.get("id"))
        if not video_id and not task_id:
            raise RuntimeError(f"agnes i2v submit missing task id: {body}")

        state = str(body.get("status") or "queued")
        logger.info(
            "agnes i2v task queued (async): video_id=%s task_id=%s status=%s",
            video_id or "-",
            task_id or "-",
            state,
        )
        return video_id, task_id, state, body

    def _poll_url(self, video_id: str | None, task_id: str | None) -> str:
        if video_id:
            # cSpell: disable-next-line
            return f"{self._poll_root}/agnesapi?{urlencode({'video_id': video_id})}"
        if task_id:
            return f"{self._create_url}/{task_id}"
        raise RuntimeError("agnes poll missing both video_id and task_id")

    def _download_video(self, poll: dict, output_path: Path, task_label: str) -> Path:
        video_url = self._extract_video_url(poll)
        if not video_url:
            raise RuntimeError(f"agnes i2v task {task_label} completed but missing video url")
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
        task_label = video_id or task_id or "unknown"
        state = "queued"
        for poll_idx in range(self._poll_max_attempts):
            time.sleep(self._poll_interval_sec)
            poll_resp = self._request(
                "GET",
                self._poll_url(video_id, task_id),
                headers={**headers, "Connection": "close"},
                label="poll",
            )
            poll = poll_resp.json()
            if poll.get("error"):
                _raise_i2v_api_error("poll", poll["error"], body=poll)

            state = str(poll.get("status") or "unknown")
            if poll_idx % 6 == 0 and state not in _TERMINAL_POLL_STATES:
                logger.info(
                    "agnes i2v task %s polling... state=%s (~%ss)",
                    task_label,
                    state,
                    int((poll_idx + 1) * self._poll_interval_sec),
                )
            if state == "completed":
                return self._download_video(poll, output_path, task_label)
            if state == "failed":
                err = poll.get("error")
                detail = err if isinstance(err, str) else repr(err)
                raise RuntimeError(f"agnes i2v task {task_label} failed: {detail}")

        raise RuntimeError(f"agnes i2v task {task_label} timeout, last state={state}")

    def _submit_and_poll(
        self,
        *,
        headers: dict,
        payload: dict,
        output_path: Path,
    ) -> Path:
        video_id, task_id, state, body = self._submit_task(headers=headers, payload=payload)
        task_label = video_id or task_id or "unknown"
        if state == "completed":
            return self._download_video(body, output_path, task_label)
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
        _ = image_prompt
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
        api_w, api_h = _resolve_api_dimensions(clip_width, clip_height)
        prompt = _stabilize_motion_prompt(motion_prompt or "")
        num_frames = _pick_num_frames(total_duration, self._frame_rate)
        raw_path = work_dir / f"{segment_index}.agnes_raw.mp4"
        fitted_path = work_dir / f"{segment_index}.agnes_fit.mp4"

        logger.info(
            "segment %s: total_duration=%.2fs n_cues=%s; submitting agnes i2v "
            "(frames=%s, fps=%s, motion=%s...)",
            segment_index,
            total_duration,
            len(subtitle_cues),
            num_frames,
            self._frame_rate,
            prompt[:80],
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._generate_raw(
                image_path, prompt, raw_path,
                num_frames=num_frames,
                width=api_w, height=api_h,
            )
            logger.info("clip %s: raw done, fitting to %.1fs", segment_index, total_duration)
            raw_path = _loop_video_to_duration(
                raw_path,
                work_dir=work_dir,
                segment_index=segment_index,
                total_duration=total_duration,
            )
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

        logger.info("clip %s: done in %.1fs", segment_index, time.time() - t0)
        return output_path
