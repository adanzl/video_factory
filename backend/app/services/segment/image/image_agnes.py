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
# 有备用 Key 时，5xx 同 Key 只打 1 次，失败立刻切
_FAILOVER_HTTP_RETRIES = 1
# 同一文生图提示词的质检重试次数；耗尽后由上层重生提示词再开一轮
_VERIFY_MAX_ATTEMPTS = 3
_ITEM_LINE_RE = re.compile(r"^项\s*(\d+)\s*[:：]\s*(.*)$")
_YES_HEAD_RE = re.compile(r"^[「【\[]?是([，,。．\s的」】\]]|$)")
_NO_HEAD_RE = re.compile(r"^[「【\[]?(否|不是)([，,。．\s」】\]]|$)")


class AgnesImageVerifyFailed(RuntimeError):
    """同提示词质检重试耗尽；最后一版图片仍在 output_path。"""

    def __init__(
        self,
        message: str,
        *,
        output_path: Path,
        prompt: str,
    ) -> None:
        super().__init__(message)
        self.output_path = output_path
        self.prompt = prompt


class _AgnesImageKeyFailover(RuntimeError):
    """生图：配额/限流或持续 5xx，应切备用 Key。"""


def _should_switch_image_key(exc: BaseException) -> bool:
    """生图切备用 Key：配额/限流，或同 Key 重试耗尽后的 5xx。"""
    if isinstance(exc, (_AgnesImageKeyFailover, AgnesQuotaExceeded)):
        return True
    if agnes_quota_exceeded_from_exception(exc):
        return True
    text = str(exc)
    return any(f"last_status={code}" in text for code in _RETRYABLE)


def _agnes_image_gen_keys(settings=None) -> list[AgnesApiKey]:
    """生图 Key 顺序：与全局一致（收费优先，失败再切 free）。"""
    return agnes_api_keys(settings)


def _to_agnes_size(size: str) -> str:
    """项目内 720*1280 → Agnes API 720x1280。"""
    return size.strip().lower().replace("*", "x")


def _resp_body_summary(resp: requests.Response, *, limit: int = 500) -> str:
    """截断响应体，便于日志排查（不含密钥）。"""
    try:
        body = resp.json()
        text = str(body)
    except Exception:
        text = (resp.text or "").strip() or "<empty>"
    text = " ".join(text.split())
    if len(text) > limit:
        return text[:limit] + "…"
    return text


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
        log_tag: str = "",
    ) -> requests.Response:
        retries = max_retries if max_retries is not None else self._http_max_retries
        timeout = get_settings().agnes_image_timeout_sec if timeout is None else timeout
        headers = agnes_auth_header(api_key)
        tag = f"{log_tag} " if log_tag else ""
        last_exc: Exception | None = None
        last_status: int | None = None
        last_body: str | None = None
        for attempt in range(retries):
            t0 = time.monotonic()
            try:
                resp = requests.request(
                    method,
                    url,
                    headers=headers,
                    json=json,
                    timeout=timeout,
                )
                elapsed = time.monotonic() - t0
                last_status = resp.status_code
                last_body = _resp_body_summary(resp)
                if resp.status_code in _RETRYABLE:
                    if attempt + 1 >= retries:
                        # 最后一次仍 5xx：不再 sleep，交给上层切 Key / 失败
                        logger.warning(
                            "%sagnes %s %s in %.1fs, body=%s, giving up after %s/%s",
                            tag,
                            resp.status_code,
                            url,
                            elapsed,
                            last_body,
                            attempt + 1,
                            retries,
                        )
                        break
                    wait = min(2**attempt * 2, 60)
                    logger.warning(
                        "%sagnes %s %s in %.1fs, body=%s, retry %s/%s in %ss",
                        tag,
                        resp.status_code,
                        url,
                        elapsed,
                        last_body,
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
                        "%sagnes api %s %s in %.1fs: %s",
                        tag,
                        resp.status_code,
                        url,
                        elapsed,
                        body,
                    )
                    raise RuntimeError(f"agnes api {resp.status_code}: {body}")
                logger.info(
                    "%sagnes http %s %s ok in %.1fs, bytes=%s",
                    tag,
                    resp.status_code,
                    url,
                    elapsed,
                    len(resp.content or b""),
                )
                return resp
            except RuntimeError:
                raise
            except AgnesQuotaExceeded:
                raise
            except requests.RequestException as exc:
                elapsed = time.monotonic() - t0
                last_exc = exc
                if agnes_quota_exceeded_from_exception(exc):
                    raise AgnesQuotaExceeded(str(exc)) from exc
                wait = min(2**attempt * 2, 60)
                logger.warning(
                    "%sagnes request error in %.1fs: %s, retry %s/%s in %ss",
                    tag,
                    elapsed,
                    exc,
                    attempt + 1,
                    retries,
                    wait,
                )
                time.sleep(wait)
        detail_parts = [f"after {retries} retries", f"url={url}"]
        if last_status is not None:
            detail_parts.append(f"last_status={last_status}")
        if last_body:
            detail_parts.append(f"last_body={last_body}")
        if last_exc:
            detail_parts.append(f"last_exc={last_exc}")
        detail = f"agnes request failed ({'; '.join(detail_parts)})"
        if last_status in _RETRYABLE:
            raise _AgnesImageKeyFailover(detail)
        raise RuntimeError(detail)

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
        max_retries: int | None = None,
    ) -> Path:
        agnes_size = _to_agnes_size(size)
        log_tag = f"[out={output_path.name}]"
        t0 = time.monotonic()
        self._acquire_submit_slot()
        try:
            extra_body: dict = {"response_format": "url"}
            ref_names: list[str] = []
            if ref_images:
                ref_b64_list: list[str] = []
                for ref_path in ref_images:
                    if ref_path.exists():
                        ref_b64 = base64.b64encode(ref_path.read_bytes()).decode("ascii")
                        ref_b64_list.append(ref_b64)
                        ref_names.append(ref_path.name)
                        logger.info(
                            "%s agnes ref_image: %s, size=%s bytes",
                            log_tag,
                            ref_path.name,
                            ref_path.stat().st_size,
                        )
                    else:
                        logger.warning(
                            "%s agnes ref_image not found: %s", log_tag, ref_path
                        )
                if ref_b64_list:
                    extra_body["ref_images"] = ref_b64_list
            payload = {
                "model": self._model,
                "prompt": prompt,
                "size": agnes_size,
                "extra_body": extra_body,
            }
            logger.info(
                "%s agnes request (%s key): %s, refs=%s, prompt_chars=%s, %s",
                log_tag,
                api_key.label,
                self.describe_params(size=size),
                ref_names or None,
                len(prompt),
                prompt,
            )
            resp = self._request(
                "POST",
                self._generation_url,
                api_key=api_key.value,
                json=payload,
                max_retries=max_retries,
                log_tag=log_tag,
            )
            image_url, image_bytes = self._extract_image(resp.json())
            output_path.parent.mkdir(parents=True, exist_ok=True)
            if image_bytes is not None:
                output_path.write_bytes(image_bytes)
                logger.info(
                    "%s agnes saved b64 image (%s key) in %.1fs, bytes=%s path=%s",
                    log_tag,
                    api_key.label,
                    time.monotonic() - t0,
                    len(image_bytes),
                    output_path,
                )
                return output_path
            if not image_url:
                raise RuntimeError("agnes response missing image url or b64_json")
            logger.info(
                "%s agnes downloading image url (%s key): %s",
                log_tag,
                api_key.label,
                image_url[:120],
            )
            img = requests.get(image_url, timeout=get_settings().agnes_image_timeout_sec)
            img.raise_for_status()
            output_path.write_bytes(img.content)
            sidecar = output_path.with_name(output_path.name + ".agnes_source_url")
            sidecar.write_text(image_url.strip(), encoding="utf-8")
            logger.info(
                "%s agnes saved url image (%s key) in %.1fs, bytes=%s path=%s",
                log_tag,
                api_key.label,
                time.monotonic() - t0,
                len(img.content),
                output_path,
            )
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
        log_tag = f"[out={output_path.name}]"
        keys = _agnes_image_gen_keys()
        if not keys:
            if get_settings().mock_mode:
                return self._fallback.generate(prompt, output_path, size=size)
            raise RuntimeError(
                "Agnes API Key 未配置（AGNES_API_KEY / AGNES_FREE_API_KEY）；"
                "非 MOCK_MODE 下拒绝静默出占位图"
            )

        exhausted: set[str] = set()
        result: Path | None = None
        last_exc: Exception | None = None
        last_key: AgnesApiKey | None = None

        for attempt in range(_VERIFY_MAX_ATTEMPTS):
            usable = [k for k in keys if k.value not in exhausted]
            if not usable:
                break

            # 校验失败重试时轮询换 key；本轮若撞配额/5xx 则同 attempt 内换下一个
            start = attempt % len(usable)
            generated = False
            for offset in range(len(usable)):
                key = usable[(start + offset) % len(usable)]
                last_key = key
                # 还有其它未耗尽 Key 时：5xx 首次失败即切，不在同 Key 上磨
                has_backup = any(
                    k.value != key.value and k.value not in exhausted for k in keys
                )
                key_retries = (
                    min(_FAILOVER_HTTP_RETRIES, self._http_max_retries)
                    if has_backup
                    else None
                )
                try:
                    result = self._generate_with_key(
                        key,
                        prompt,
                        output_path,
                        size=size,
                        ref_images=ref_images,
                        max_retries=key_retries,
                    )
                    generated = True
                    break
                except Exception as exc:
                    if _should_switch_image_key(exc):
                        exhausted.add(key.value)
                        last_exc = exc
                        nxt = next(
                            (k for k in keys if k.value not in exhausted),
                            None,
                        )
                        if nxt is not None:
                            logger.warning(
                                "%s agnes %s key quota/rate/5xx exhausted, "
                                "switching to backup (%s)",
                                log_tag,
                                key.label,
                                nxt.label,
                            )
                            continue
                        raise
                    logger.error(
                        "%s agnes generate failed (%s key): %s",
                        log_tag,
                        key.label,
                        exc,
                    )
                    if get_settings().mock_mode:
                        return self._fallback.generate(
                            prompt, output_path, size=size
                        )
                    raise

            if not generated:
                break
            if result is None or not result.exists():
                return result

            verified = self._verify_image(
                prompt,
                result,
                expected_speakers=expected_speakers,
                content_style=content_style,
            )
            key_label = last_key.label if last_key else "?"
            if verified:
                logger.info(
                    "%s agnes generate ok (%s key, verify_attempt=%s/%s)",
                    log_tag,
                    key_label,
                    attempt + 1,
                    _VERIFY_MAX_ATTEMPTS,
                )
                return result
            more = attempt + 1 < _VERIFY_MAX_ATTEMPTS
            next_usable = [k for k in keys if k.value not in exhausted]
            next_label = ""
            if more and next_usable:
                next_key = next_usable[(attempt + 1) % len(next_usable)]
                next_label = f", next_key={next_key.label}"
            logger.warning(
                "%s agnes image verify FAILED (%s key, attempt=%s/%s, "
                "prompt_chars=%s, speakers=%s)%s",
                log_tag,
                key_label,
                attempt + 1,
                _VERIFY_MAX_ATTEMPTS,
                len(prompt),
                expected_speakers,
                f", regenerating…{next_label}" if more else ", raise for prompt re_gen",
            )

        if result is not None and result.exists():
            raise AgnesImageVerifyFailed(
                f"agnes image verify failed after {_VERIFY_MAX_ATTEMPTS} attempts",
                output_path=result,
                prompt=prompt,
            )
        if last_exc:
            raise last_exc
        raise RuntimeError("agnes generate failed without exception")

    # ── image-text match verification ────────────────────────────────

    _VERIFY_SYSTEM_PROMPT = (
        "你是图像质检员。只根据用户列出的检查项逐项判断，每项单独一行回答。"
        "回答格式必须为「项N: 是」或「项N: 否」"
        "（昭昭短发项无该角色可答「项N: 无昭昭」；"
        "灿灿发型项无该角色可答「项N: 无灿灿」；"
        "妈妈成年项无该角色可答「项N: 无妈妈」）。"
        "不要解释、不要编号列表外的文字、不要复述提示词。"
        "项「场景」：只看主场景/主体是否明显跑偏；"
        "画风套话、参考图指令前缀、次要细节差异一律算通过（答是）。"
        "项「胳膊」：每人可见胳膊是否最多 2 条；正常答「是」，多肢答「否」。"
        "项「人数」：只计画面主体人物，不超过 3 个即通过；"
        "昭昭与灿灿可同时出场，即使本段未发言；"
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
        """归一化为 yes / no / na_zhao / na_can / na_mom / unknown。

        先判「不是/否」，避免「不是」命中「是」。
        """
        text = (body or "").strip().strip("。．.")
        if "无昭昭" in text:
            return "na_zhao"
        if "无灿灿" in text:
            return "na_can"
        if "无妈妈" in text:
            return "na_mom"
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
                    "角色昭昭是否为男孩超短发"
                    "（耳上短发、双耳与后颈清晰可见，圆寸/学生头感；"
                    "若为女童波波头、齐肩短发、厚刘海遮额或任何马尾则答「否」）？"
                    "回答「是」或「否」；图中无昭昭时回答「无昭昭」",
                )
            )
        if content_style == CONTENT_STYLE_DAILY_STORY and "灿灿" in speakers:
            items.append(
                (
                    "can_hair",
                    "角色灿灿是否为单侧高马尾"
                    "（仅一根马尾，非双马尾/麻花辫/披肩长发）？"
                    "回答「是」或「否」；图中无灿灿时回答「无灿灿」",
                )
            )
        if content_style == CONTENT_STYLE_DAILY_STORY and "妈妈" in speakers:
            items.append(
                (
                    "mom_adult",
                    "角色妈妈是否为成年女性"
                    "（成人脸与体型、黑长发、米色上衣牛仔裤；"
                    "若画成小孩脸/童装/与姐弟同龄感则答「否」）？"
                    "回答「是」或「否」；图中无妈妈时回答「无妈妈」",
                )
            )
        items.append(
            (
                "extra_arms",
                "画面中每人可见胳膊/手臂是否最多 2 条？"
                "正常答「是」；有任何人超过 2 条答「否」",
            )
        )
        if speakers or content_style == CONTENT_STYLE_DAILY_STORY:
            items.append(
                (
                    "cast_count",
                    "画面主体人物数量是否不超过 3 个？"
                    "昭昭与灿灿可同时出场，即使本段未发言也算通过；"
                    "超过 3 个主体人物答「否」；"
                    "背景照片墙/镜子虚影/玩具人脸/远处剪影不算。"
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

        各项极性统一：答「是」为通过侧；答「否」为失败
        （zhao_hair「无昭昭」、can_hair「无灿灿」、mom_adult「无妈妈」放行）。
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
            if cid == "can_hair" and verdict == "na_can":
                continue
            if cid == "mom_adult" and verdict == "na_mom":
                continue
            if verdict == "no" and cid in {
                "scene",
                "zhao_hair",
                "can_hair",
                "mom_adult",
                "extra_arms",
                "cast_count",
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

            log_tag = f"[out={image_path.name}]"
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
                        ok = AgnesImageProvider._evaluate_verify_response(
                            content, check_ids
                        )
                        logger.info(
                            "%s agnes verify (%s key): ok=%s checks=%s reply=%s",
                            log_tag,
                            api_key.label,
                            ok,
                            check_ids,
                            " ".join(content.split())[:200],
                        )
                        return ok
                    logger.warning(
                        "%s agnes verify_image http %s (%s key), body=%s",
                        log_tag,
                        resp.status_code,
                        api_key.label,
                        _resp_body_summary(resp),
                    )
                except Exception as exc:
                    logger.warning(
                        "%s agnes verify_image call failed (%s key): %s",
                        log_tag,
                        api_key.label,
                        exc,
                    )
            logger.warning("%s agnes verify skipped (all keys failed)", log_tag)
            return True
        except Exception as exc:
            logger.warning(
                "agnes verify_image error [out=%s]: %s", image_path.name, exc
            )
            return True
