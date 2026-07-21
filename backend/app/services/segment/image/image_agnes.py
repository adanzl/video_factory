"""Agnes AI 文生图 ImageProvider（OpenAI-compatible /v1/images/generations）。"""

from __future__ import annotations

import base64
import io
import logging
import re
import time
from pathlib import Path

from gevent.lock import Semaphore
from PIL import Image as PILImage

import requests

from app.config import get_settings
from app.services.llm.llm_agnes import (
    AgnesApiKey,
    AgnesQuotaExceeded,
    agnes_api_keys,
    agnes_auth_header,
    agnes_quota_exceeded_from_exception,
    raise_if_agnes_quota,
)
from app.services.segment.image.image_mock import MockImageProvider
from app.services.segment.image.image_mgr import ImageProvider
from app.utils.job_info import CONTENT_STYLE_DAILY_STORY

logger = logging.getLogger(__name__)

_RETRYABLE = frozenset({500, 502, 503, 504})
_VERIFY_MAX_ATTEMPTS = 3
_ITEM_LINE_RE = re.compile(r"^项\s*(\d+)\s*[:：]\s*(.*)$")
_YES_HEAD_RE = re.compile(r"^[「【\[]?是([，,。．\s的」】\]]|$)")
_NO_HEAD_RE = re.compile(r"^[「【\[]?(否|不是)([，,。．\s」】\]]|$)")


def _to_agnes_size(size: str) -> str:
    """项目内 720*1280 → Agnes API 720x1280。"""
    return size.strip().lower().replace("*", "x")


class AgnesImageProvider(ImageProvider):
    """Agnes 文生图：IMAGE_MAX_WORKERS 路并发 + IMAGE_SUBMIT_INTERVAL_SEC 错峰发起。"""

    _concurrency_lock = Semaphore(value=1)
    _schedule_lock = Semaphore(value=1)
    _inflight: Semaphore | None = None
    _max_concurrent: int = 1
    _stagger_sec: float = 20.0
    _next_submit_at: float = 0.0

    def __init__(self) -> None:
        settings = get_settings()
        base = settings.agnes_api_base_url.rstrip("/")
        self._generation_url = f"{base}/images/generations"
        self._model = settings.agnes_image_model
        self._default_size = settings.agnes_image_size
        self._fallback = MockImageProvider()
        self._http_max_retries = settings.agnes_http_max_retries
        self._ensure_concurrency()

    @classmethod
    def _ensure_concurrency(cls) -> None:
        settings = get_settings()
        max_concurrent = max(1, settings.image_max_workers)
        stagger_sec = max(0.0, settings.image_submit_interval_sec)
        with cls._concurrency_lock:
            if (
                cls._inflight is None
                or cls._max_concurrent != max_concurrent
                or cls._stagger_sec != stagger_sec
            ):
                cls._max_concurrent = max_concurrent
                cls._stagger_sec = stagger_sec
                cls._inflight = Semaphore(max_concurrent)
                cls._next_submit_at = 0.0

    def describe_params(self, *, size: str | None = None) -> str:
        size = size or self._default_size
        return (
            f"provider=agnes_t2i, model={self._model}, size={size}, "
            f"workers={self._max_concurrent}, stagger={self._stagger_sec}s"
        )

    def _acquire_submit_slot(self) -> None:
        self._ensure_concurrency()
        assert self._inflight is not None
        self._inflight.acquire()
        try:
            with self._schedule_lock:
                now = time.monotonic()
                wait = max(0.0, self._next_submit_at - now)
                self._next_submit_at = max(now, self._next_submit_at) + self._stagger_sec
            if wait:
                time.sleep(wait)
        except Exception:
            self._inflight.release()
            raise

    def _release_submit_slot(self) -> None:
        if self._inflight is not None:
            self._inflight.release()

    def _request(
        self,
        method: str,
        url: str,
        *,
        api_key: str,
        json: dict | None = None,
        max_retries: int | None = None,
        timeout: int | None = None,
    ) -> requests.Response:
        retries = max_retries if max_retries is not None else self._http_max_retries
        timeout = get_settings().agnes_image_timeout_sec if timeout is None else timeout
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
                    logger.warning(
                        "agnes api %s %s: %s",
                        resp.status_code,
                        url,
                        body,
                    )
                    raise RuntimeError(f"agnes api {resp.status_code}: {body}")
                return resp
            except RuntimeError:
                raise
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
            raise RuntimeError(f"agnes request failed after {retries} retries: {url}: {last_exc}")
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
        ref_images: list[Path] | None = None,
    ) -> Path:
        agnes_size = _to_agnes_size(size)
        self._acquire_submit_slot()
        try:
            extra_body: dict = {"response_format": "url"}
            if ref_images:
                ref_b64_list: list[str] = []
                for ref_path in ref_images:
                    if ref_path.exists():
                        ref_b64 = base64.b64encode(ref_path.read_bytes()).decode("ascii")
                        ref_b64_list.append(ref_b64)
                        logger.info(
                            "agnes ref_image: %s, size=%s bytes",
                            ref_path.name,
                            ref_path.stat().st_size,
                        )
                    else:
                        logger.warning("agnes ref_image not found: %s", ref_path)
                if ref_b64_list:
                    extra_body["ref_images"] = ref_b64_list
            payload = {
                "model": self._model,
                "prompt": prompt,
                "size": agnes_size,
                "extra_body": extra_body,
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
            img = requests.get(image_url, timeout=get_settings().agnes_image_timeout_sec)
            img.raise_for_status()
            output_path.write_bytes(img.content)
            sidecar = output_path.with_name(output_path.name + ".agnes_source_url")
            sidecar.write_text(image_url.strip(), encoding="utf-8")
            return output_path
        finally:
            self._release_submit_slot()

    def generate(
        self,
        prompt: str,
        output_path: Path,
        *,
        size: str | None = None,
        ref_images: list[Path] | None = None,
        expected_speakers: list[str] | None = None,
        content_style: str | None = None,
    ) -> Path:
        size = size or self._default_size
        keys = agnes_api_keys()
        if not keys:
            if get_settings().mock_mode:
                return self._fallback.generate(prompt, output_path, size=size)
            raise RuntimeError(
                "Agnes API Key 未配置（AGNES_API_KEY / AGNES_FREE_API_KEY）；"
                "非 MOCK_MODE 下拒绝静默出占位图"
            )

        last_exc: Exception | None = None
        for idx, key in enumerate(keys):
            try:
                result: Path | None = None
                for attempt in range(_VERIFY_MAX_ATTEMPTS):
                    result = self._generate_with_key(
                        key, prompt, output_path, size=size, ref_images=ref_images
                    )
                    if result is None or not result.exists():
                        return result
                    verified = self._verify_image(
                        prompt,
                        result,
                        expected_speakers=expected_speakers,
                        content_style=content_style,
                    )
                    if verified:
                        return result
                    logger.warning(
                        "agnes image verify FAILED (%s key, attempt=%s/%s, "
                        "prompt_chars=%s)%s",
                        key.label,
                        attempt + 1,
                        _VERIFY_MAX_ATTEMPTS,
                        len(prompt),
                        ", regenerating…" if attempt + 1 < _VERIFY_MAX_ATTEMPTS else ", keep last",
                    )
                return result
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

    # ── image-text match verification ────────────────────────────────

    _VERIFY_SYSTEM_PROMPT = (
        "你是图像质检员。只根据用户列出的检查项逐项判断，每项单独一行回答。"
        "回答格式必须为「项N: 是」或「项N: 否」"
        "（昭昭短发项在无该角色时可答「项N: 无昭昭」）。"
        "不要解释、不要编号列表外的文字、不要复述提示词。"
        "项「场景」：只看主场景/主体是否明显跑偏；"
        "画风套话、参考图指令前缀、次要细节差异一律算通过（答是）。"
        "项「胳膊」：每人可见胳膊是否最多 2 条；正常答「是」，多肢答「否」。"
        "项「人数」：只计画面主体人物，须与给定发言角色数一致；"
        "背景照片墙/镜子虚影/玩具人脸/远处剪影一律不算。"
    )

    @staticmethod
    def _strip_prompt_for_verify(prompt: str) -> str:
        """去掉 daily wrap 硬编码前缀，只留给 VL 核心场景句。"""
        body = (prompt or "").strip()
        marker = "孩子气的构图。"
        if "基于参考图调整人物动作" in body and marker in body:
            idx = body.find(marker)
            if idx >= 0:
                stripped = body[idx + len(marker) :].strip()
                if stripped:
                    return stripped
        return body

    @staticmethod
    def _parse_item_answer(body: str) -> str:
        """归一化为 yes / no / na_zhao / unknown。先判「不是/否」，避免「不是」命中「是」。"""
        text = (body or "").strip().strip("。．.")
        if "无昭昭" in text:
            return "na_zhao"
        if _NO_HEAD_RE.match(text):
            return "no"
        if _YES_HEAD_RE.match(text):
            return "yes"
        # 兜底：整段里出现独立否/是（仍避开「不是」误伤后的纯「是」扫描）
        if re.search(r"(^|[，,、\s])否([，,。．\s]|$)", text):
            return "no"
        if re.search(r"(^|[，,、\s])是([，,。．\s的]|$)", text) and "不是" not in text:
            return "yes"
        return "unknown"

    @staticmethod
    def _build_verify_checklist(
        *,
        prompt: str,
        expected_speakers: list[str] | None,
        content_style: str | None,
    ) -> tuple[list[tuple[str, str]], str]:
        """返回 ([(check_id, question_without_index), ...], user_prompt)."""
        speakers = [str(s).strip() for s in (expected_speakers or []) if str(s).strip()]
        scene_prompt = AgnesImageProvider._strip_prompt_for_verify(prompt)

        items: list[tuple[str, str]] = [
            (
                "scene",
                "画面主场景/主体是否与提示词核心场景一致？"
                "仅当主体或场景明显跑偏时答「否」；"
                "画风套话、参考图前缀、次要细节差异答「是」。"
                "回答「是」或「否」",
            ),
        ]
        if content_style == CONTENT_STYLE_DAILY_STORY and "昭昭" in speakers:
            items.append(
                (
                    "zhao_hair",
                    "角色昭昭是否为短发男生头"
                    "（发长约耳垂以上、无马尾/双马尾/麻花辫/丸子头）？"
                    "回答「是」或「否」；图中无昭昭时回答「无昭昭」",
                )
            )
        items.append(
            (
                "extra_arms",
                "画面中每人可见胳膊/手臂是否最多 2 条？"
                "正常答「是」；有任何人超过 2 条答「否」",
            )
        )
        expected_count = len(speakers)
        if expected_count > 0:
            speakers_str = "/".join(speakers)
            items.append(
                (
                    "cast_count",
                    f"画面主体人物数量是否恰好为 {expected_count} 个"
                    f"（须与该段发言角色一致：{speakers_str}；"
                    f"背景照片墙/镜子虚影/玩具人脸/远处剪影不算）？"
                    f"回答「是」或「否」",
                )
            )
        if (
            content_style == CONTENT_STYLE_DAILY_STORY
            and "昭昭" in speakers
            and "灿灿" in speakers
        ):
            items.append(
                (
                    "height_order",
                    "昭昭是否明显比灿灿矮约半个头"
                    "（不得同高或弟弟更高；勿因服装颜色偏差而判否）？"
                    "回答「是」或「否」",
                )
            )

        lines = [
            f"【核心场景】\n{scene_prompt}\n",
            f"请检查以下 {len(items)} 项，每项一行：",
        ]
        for i, (_cid, q) in enumerate(items, start=1):
            lines.append(f"项{i}: {q}")
        lines.append("不要输出任何其他内容。")
        return items, "\n".join(lines)

    @staticmethod
    def _evaluate_verify_response(content: str, check_ids: list[str]) -> bool:
        """按检查项判定；解析失败的项视为通过（避免误杀）。

        各项极性统一：答「是」为通过侧；答「否」为失败（zhao_hair 的「无昭昭」放行）。
        """
        answers: dict[int, str] = {}
        for raw in content.split("\n"):
            line = raw.strip()
            if not line:
                continue
            m = _ITEM_LINE_RE.match(line)
            if not m:
                continue
            idx = int(m.group(1))
            answers[idx] = AgnesImageProvider._parse_item_answer(m.group(2))

        for i, cid in enumerate(check_ids, start=1):
            verdict = answers.get(i, "unknown")
            if verdict == "unknown":
                continue
            if cid == "zhao_hair" and verdict == "na_zhao":
                continue
            if verdict == "no" and cid in {
                "scene",
                "zhao_hair",
                "extra_arms",
                "cast_count",
                "height_order",
            }:
                return False
        return True

    @staticmethod
    def _verify_image(
        prompt: str,
        image_path: Path,
        *,
        expected_speakers: list[str] | None = None,
        content_style: str | None = None,
    ) -> bool:
        """使用 Agnes 多模态判断图片是否匹配提示词且符合内容规则。

        返回 True=通过, False=不通过（触发生成重试）。
        优先使用 .agnes_source_url 侧车 CDN URL，无侧车时回退 base64。
        """
        if not image_path.exists():
            return True

        try:
            settings = get_settings()

            image_url: str | None = None
            sidecar = image_path.with_name(image_path.name + ".agnes_source_url")
            if sidecar.is_file():
                url = sidecar.read_text(encoding="utf-8").strip()
                if url.startswith(("http://", "https://")):
                    image_url = url

            if image_url is None:
                img = PILImage.open(image_path)
                max_dim = 1024
                if max(img.size) > max_dim:
                    ratio = max_dim / max(img.size)
                    new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
                    img = img.resize(new_size, PILImage.LANCZOS)
                buf = io.BytesIO()
                img.convert("RGB").save(buf, format="JPEG", quality=85)
                b64 = base64.b64encode(buf.getvalue()).decode("ascii")
                image_url = f"data:image/jpeg;base64,{b64}"

            items, user = AgnesImageProvider._build_verify_checklist(
                prompt=prompt,
                expected_speakers=expected_speakers,
                content_style=content_style,
            )
            check_ids = [cid for cid, _ in items]

            keys = agnes_api_keys(settings)
            if not keys:
                return True

            for api_key in keys:
                try:
                    headers = agnes_auth_header(api_key.value)
                    url = f"{settings.agnes_api_base_url.rstrip('/')}/chat/completions"
                    payload = {
                        "model": settings.agnes_vl_model,
                        "messages": [
                            {
                                "role": "system",
                                "content": AgnesImageProvider._VERIFY_SYSTEM_PROMPT,
                            },
                            {
                                "role": "user",
                                "content": [
                                    {"type": "text", "text": user},
                                    {
                                        "type": "image_url",
                                        "image_url": {"url": image_url},
                                    },
                                ],
                            },
                        ],
                        "max_tokens": 256,
                    }
                    resp = requests.post(url, headers=headers, json=payload, timeout=60)
                    if resp.ok:
                        content = (
                            resp.json()
                            .get("choices", [{}])[0]
                            .get("message", {})
                            .get("content", "")
                            .strip()
                        )
                        return AgnesImageProvider._evaluate_verify_response(
                            content, check_ids
                        )
                except Exception:
                    logger.warning(
                        "agnes verify_image call failed (%s key), skipping verify",
                        api_key.label,
                    )
            return True
        except Exception as exc:
            logger.warning("agnes verify_image error: %s", exc)
            return True
