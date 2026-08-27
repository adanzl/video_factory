"""Agnes AI 文生图 ImageProvider（OpenAI-compatible /v1/images/generations）。"""

from __future__ import annotations

import base64
import io
import logging
import re
import time
from pathlib import Path

from gevent.lock import Semaphore
from gevent import sleep as gevent_sleep
from gevent import spawn as gevent_spawn
from gevent.event import AsyncResult
from PIL import Image as PILImage

import requests

from app.config import get_settings
from app.services.daily_story.speaker import DAILY_STORY_SPEAKER_NAMES
from app.utils.job_cancel import job_cancel
from app.services.llm.llm_agnes import (
    AgnesApiKey,
    AgnesContentPolicyError,
    AgnesImageError,
    AgnesQuotaExceeded,
    agnes_api_keys,
    agnes_apply_host_failover,
    agnes_auth_header,
    agnes_key_base_url,
    agnes_quota_exceeded_from_exception,
    agnes_should_switch_key,
    raise_if_agnes_content_policy,
    raise_if_agnes_quota,
)
from app.services.segment.image.image_mock import MockImageProvider
from app.services.segment.image.image_mgr import ImageProvider
from app.utils.job_info import CONTENT_STYLE_DAILY_STORY

logger = logging.getLogger(__name__)

# 含 Cloudflare 源站错误 52x（如 520 unknown error）
_RETRYABLE = frozenset({500, 502, 503, 504, 520, 521, 522, 523, 524, 525, 526, 527})
# 有备用 Key 时，5xx 同 Key 只打 1 次，失败立刻切
_FAILOVER_HTTP_RETRIES = 1
# 同一文生图提示词的质检重试次数；耗尽后由上层重生提示词再开一轮
_VERIFY_MAX_ATTEMPTS = 5
# 验证接口超时/网络失败时的重试次数（不重生图，只重试验证）
_VERIFY_RETRY_COUNT = 2
_VERIFY_RETRY_DELAY = 10
_ITEM_LINE_RE = re.compile(r"^项\s*(\d+)\s*[:：]\s*(.*)$")
_YES_HEAD_RE = re.compile(r"^[「【\[]?是([，,。．\s的」】\]]|$)")
_NO_HEAD_RE = re.compile(r"^[「【\[]?(否|不是)([，,。．\s」】\]]|$)")
_HTML_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)

# 日常故事固定角色顺序；姐弟未发言也可同框
_DAILY_SIBLINGS = ("昭昭", "灿灿")
_DAILY_SPEAKER_ORDER = DAILY_STORY_SPEAKER_NAMES
# 供质检项引用的角色外观速写
_DAILY_LOOK = {
    "昭昭": "蓝色短袖T恤的短发男孩（昭昭）",
    "灿灿": "粉色卫衣的黑马尾女孩（灿灿）",
    "妈妈": "米色上衣的黑长发成年女性（妈妈）",
}
_DAILY_ARM_IDS = {"昭昭": "zhao_arms", "灿灿": "can_arms", "妈妈": "mom_arms"}
_ARM_COUNT_IDS = frozenset({"zhao_arms", "can_arms", "mom_arms", "extra_arms"})
_MAX_ARMS_PER_PERSON = 2
_DAILY_LEG_IDS = {"昭昭": "zhao_legs", "灿灿": "can_legs", "妈妈": "mom_legs"}
_LEG_COUNT_IDS = frozenset({"zhao_legs", "can_legs", "mom_legs", "extra_legs"})
_MAX_LEGS_PER_PERSON = 2

# ── 多手硬卡（裁剪放大数手）────────────────────────────────
# 主校验整图数手对低分辨率下的多手会漏（图9 双手抱头+第三只手握遥控器）。
# 硬卡把角色所在半幅裁剪 ×2 放大后再数手+多手确认，两问任一命中即失败。
_HARDFAIL_ARM_SYSTEM_PROMPT = (
    "你是图像质检员。只根据用户列出的检查项逐项判断，每项单独一行回答。"
    "回答格式必须为「项N: 是」或「项N: 否」，数字项只回答阿拉伯数字。"
    "不要解释、不要编号列表外的文字。"
)
_HARDFAIL_ARM_Q1 = (
    "项1: 只看{look}本人。该角色身上凡是末端呈人手形态的肢端都算一条手臂"
    "（起点是肩膀、腋下、腰侧、胸口或身前都要数，明显多出来的第3只手必须计入）。"
    "手里握着东西的手也要算进去——手和握着的东西是两回事。"
    "不要用「人只有两只胳膊」的常识改口。只回答阿拉伯数字"
)
_HARDFAIL_ARM_Q2 = (
    "项2: {look}本人是否出现了多于正常两只手的情况？"
    "（数清楚她/他身上所有的手，包括握着东西的手、"
    "从腰侧/背后/胸前伸出的手）是则回答「是」，否则回答「否」。"
)
# daily 固定布局：昭昭左、灿灿右、妈妈中
_HARDFAIL_ZONE = {"昭昭": "left", "灿灿": "right", "妈妈": "center"}
_HARDFAIL_ZOOM = 2


def _arm_count_question(look: str) -> str:
    """手臂条数问法：要数字。是/否和「人只有两臂」先验都会漏三臂。"""
    return (
        f"只看{look}本人。"
        "该角色身上凡是末端呈人手形态的肢端都算一条手臂"
        "（起点是肩膀、腋下、腰侧、胸口或身前都要数，"
        "明显多出来的第3只手必须计入）。"
        "手里握着东西的手也要算进去——手和握着的东西是两回事；"
        "剪柄、纸边不算。"
        "不要用「人只有两只胳膊」的常识改口。"
        "只回答阿拉伯数字"
    )


def _leg_count_question(look: str) -> str:
    """腿条数问法：要数字。是/否和「人只有两腿」先验都会漏三腿。"""
    return (
        f"只看{look}本人。"
        "该角色身上凡是末端呈人脚或鞋子形态的肢端都算一条腿"
        "（起点是髋、臀、膝盖或桌下都要数，"
        "明显多出来的第3条腿必须计入）。"
        "桌腿、椅腿、裤褶不算。"
        "不要用「人只有两条腿」的常识改口。"
        "只回答阿拉伯数字"
    )
# 拼装器写入 image_prompt 的首个说话人张嘴标记（须与 image_prompt.py 一致）
_MOUTH_FIRST_SPEAKER_RE = re.compile(
    r"(昭昭|灿灿|妈妈)(?:嘴唇微张，|(?:嘴巴明显张开|微微张嘴|嘴巴微张)?)正在开口说话"
)
_PROP_HOLDER_RE = re.compile(
    r"(?P<hand>右手|左手)?"
    r"(?:握着|握住|握|拿着|持着|持|举着|端着|托着|托住|提着|接过|递出|抓住|抓着|拿起|紧握)"
    r"(?P<prop>[^，。；、]{1,8})"
)


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


class _AgnesImageKeyFailover(AgnesImageError):
    """生图：配额/限流或持续 5xx，应切备用 Key。"""


def _should_switch_image_key(exc: BaseException) -> bool:
    """生图切备用 Key：4xx/5xx/配额/限流；提示词违规不换。"""
    if isinstance(exc, AgnesContentPolicyError):
        return False
    if isinstance(exc, _AgnesImageKeyFailover):
        return True
    return agnes_should_switch_key(exc)


def _agnes_image_gen_keys(settings=None) -> list[AgnesApiKey]:
    """生图 Key 顺序：与全局一致（收费优先，失败再切 free）。"""
    return agnes_api_keys(settings)


def _maybe_failover_generation_host(
    provider: AgnesImageProvider,
    url: str,
    host_failover_tried: set[str],
    *,
    reason: str,
    tag: str,
) -> str | None:
    """images/generations 在 .com/.cn 间切换一次；已试过的域名不再切。"""
    if "/images/generations" not in url:
        return None
    return agnes_apply_host_failover(
        url,
        host_failover_tried,
        reason=reason,
        tag=tag,
        on_switch=lambda alt: setattr(provider, "_generation_url", alt),
    )


def _to_agnes_size(size: str) -> str:
    """项目内 720*1280 → Agnes API 720x1280；档位 2K 保留大小写。"""
    text = size.strip()
    if re.fullmatch(r"[1-4][Kk]", text):
        return text.upper()
    return text.lower().replace("*", "x")


def _guess_agnes_ratio(size: str) -> str:
    """按请求尺寸推断宽高比；横屏 16:9，竖屏 9:16。"""
    text = size.strip().lower().replace("*", "x")
    if "x" in text:
        try:
            w, h = text.split("x", 1)[:2]
            width = int(float(w))
            height = int(float(h))
            return "16:9" if width > height else "9:16"
        except (ValueError, TypeError):
            pass
    return "16:9"


def _resp_body_summary(resp: requests.Response, *, limit: int = 500) -> str:
    """截断响应体，便于日志排查（不含密钥）。HTML 错误页只保留 title。"""
    try:
        body = resp.json()
        text = str(body)
    except Exception:
        raw = (resp.text or "").strip() or "<empty>"
        head = raw[:300].lower()
        if head.startswith("<!doctype") or "<html" in head:
            m = _HTML_TITLE_RE.search(raw)
            title = " ".join(m.group(1).split()) if m else ""
            text = f"<html: {title}>" if title else f"<html status={resp.status_code}>"
        else:
            text = raw
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
        self._active_job_id: int | None = None
        self._ensure_concurrency()

    def _raise_if_job_cancelled(self) -> None:
        if self._active_job_id is not None:
            job_cancel.raise_if_cancelled(self._active_job_id)

    def _run_blocking_cancellable(self, fn):
        """在子 greenlet 跑阻塞 HTTP，主 greenlet 轮询中止。"""
        result = AsyncResult()

        def _worker() -> None:
            try:
                result.set(fn())
            except Exception as exc:
                result.set_exception(exc)

        gevent_spawn(_worker)
        while not result.ready():
            self._raise_if_job_cancelled()
            gevent_sleep(0.3)
        return result.get()

    def _sleep_cancellable(self, seconds: float) -> None:
        if seconds <= 0:
            return
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            self._raise_if_job_cancelled()
            gevent_sleep(min(0.3, max(0.0, deadline - time.monotonic())))

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
            f"workers={self._max_concurrent}, stagger={self._stagger_sec}s, "
            f"api={self._generation_url}"
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
                self._sleep_cancellable(wait)
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
        host_failover_tried = {url}
        for attempt in range(retries):
            self._raise_if_job_cancelled()
            t0 = time.monotonic()
            try:
                resp = self._run_blocking_cancellable(
                    lambda: requests.request(
                        method,
                        url,
                        headers=headers,
                        json=json,
                        timeout=timeout,
                    )
                )
                elapsed = time.monotonic() - t0
                last_status = resp.status_code
                last_body = _resp_body_summary(resp)
                if resp.status_code == 503:
                    alt_url = _maybe_failover_generation_host(
                        self,
                        url,
                        host_failover_tried,
                        reason="503",
                        tag=tag,
                    )
                    if alt_url:
                        url = alt_url
                        continue
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
                    self._sleep_cancellable(wait)
                    continue
                if resp.status_code == 429:
                    body: dict | str | None = None
                    try:
                        body = resp.json()
                    except Exception:
                        body = _resp_body_summary(resp)
                    raise_if_agnes_quota(status_code=resp.status_code, body=body)
                if not resp.ok:
                    body = None
                    try:
                        body = resp.json()
                    except Exception:
                        body = _resp_body_summary(resp)
                    raise_if_agnes_quota(status_code=resp.status_code, body=body)
                    raise_if_agnes_content_policy(
                        status_code=resp.status_code, body=body
                    )
                    logger.warning(
                        "%sagnes api %s %s in %.1fs: %s",
                        tag,
                        resp.status_code,
                        url,
                        elapsed,
                        body,
                    )
                    raise AgnesImageError(f"agnes api {resp.status_code}: {body}")
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
                if isinstance(exc, requests.Timeout):
                    alt_url = _maybe_failover_generation_host(
                        self,
                        url,
                        host_failover_tried,
                        reason="timeout",
                        tag=tag,
                    )
                    if alt_url:
                        url = alt_url
                        continue
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
                self._sleep_cancellable(wait)
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
        raise AgnesImageError(detail)

    @staticmethod
    def _extract_image(body: dict) -> tuple[str | None, bytes | None]:
        if body.get("error"):
            err = body["error"]
            raise_if_agnes_quota(body=body if isinstance(body, dict) else None, message=str(err))
            raise_if_agnes_content_policy(
                body=body if isinstance(body, dict) else None,
                message=str(err),
            )
            if isinstance(err, dict):
                raise AgnesImageError(
                    f"agnes api error: {err.get('code')} - {err.get('message')}"
                )
            raise AgnesImageError(f"agnes api error: {err}")
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
        ref_images: list[Path | str] | None = None,
        max_retries: int | None = None,
    ) -> Path:
        settings = get_settings()
        cfg_size = settings.agnes_image_size.strip()
        if re.fullmatch(r"[1-4][Kk]", cfg_size):
            agnes_size = cfg_size.upper()
            ratio = settings.agnes_image_ratio.strip() or _guess_agnes_ratio(size)
        else:
            agnes_size = _to_agnes_size(size)
            ratio = ""
        log_tag = f"[out={output_path.name}]"
        t0 = time.monotonic()
        self._acquire_submit_slot()
        try:
            extra_body: dict = {"response_format": "url"}
            ref_names: list[str] = []
            if ref_images:
                # URL / 本地 base64 一律进 ref_images（角色参考）；勿用 image（那是 i2i 底图）
                ref_payload: list[str] = []
                for ref in ref_images:
                    if isinstance(ref, str) and ref.startswith(("http://", "https://")):
                        ref_payload.append(ref)
                        ref_names.append(ref)
                        logger.info("%s agnes ref_image url: %s", log_tag, ref)
                        continue
                    ref_path = Path(ref)
                    if ref_path.exists():
                        ref_b64 = base64.b64encode(
                            ref_path.read_bytes()
                        ).decode("ascii")
                        ref_payload.append(ref_b64)
                        ref_names.append(ref_path.name)
                        logger.info(
                            "%s agnes ref_image: %s, size=%s bytes",
                            log_tag,
                            ref_path.name,
                            ref_path.stat().st_size,
                        )
                    else:
                        logger.warning(
                            "%s agnes ref_image not found: %s",
                            log_tag,
                            ref_path,
                        )
                if ref_payload:
                    extra_body["ref_images"] = ref_payload
            payload = {
                "model": self._model,
                "prompt": prompt,
                "size": agnes_size,
                "extra_body": extra_body,
            }
            if ratio:
                payload["ratio"] = ratio
            logger.info(
                "%s agnes request (%s key): %s, refs=%s, prompt_chars=%s, %s",
                log_tag,
                api_key.label,
                self.describe_params(size=size),
                ref_names or None,
                len(prompt),
                prompt,
            )
            gen_url = f"{agnes_key_base_url(api_key)}/images/generations"
            resp = self._request(
                "POST",
                gen_url,
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
                raise AgnesImageError("agnes response missing image url or b64_json")
            logger.info(
                "%s agnes downloading image url (%s key): %s",
                log_tag,
                api_key.label,
                image_url[:120],
            )
            img = self._run_blocking_cancellable(
                lambda: requests.get(
                    image_url, timeout=get_settings().agnes_image_timeout_sec
                )
            )
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
        ref_images: list[Path | str] | None = None,
        expected_speakers: list[str] | None = None,
        content_style: str | None = None,
    ) -> Path:
        size = size or self._default_size
        log_tag = f"[out={output_path.name}]"
        # chat 有参考图时再钉发色：涂鸦高饱和易把灿灿马尾画成彩色。
        # 无条件前置——LLM 已把硬锁写进提示词末尾时，句末权重最低等于没锁。
        # 锁必须纯正面表述：图像模型把否定词当生成指令，
        # "禁止蓝粉黄绿霓虹条纹或彩色挑染"会诱发全图彩虹化（实测连妈妈黑发都中招）
        if (
            ref_images
            and content_style == CONTENT_STYLE_DAILY_STORY
            and expected_speakers
            and "灿灿" in expected_speakers
        ):
            prompt = "严格保留参考图发色：灿灿头发通体纯黑，头顶到马尾同一黑色。" + prompt
        keys = _agnes_image_gen_keys()
        if not keys:
            if get_settings().mock_mode:
                return self._fallback.generate(prompt, output_path, size=size)
            raise RuntimeError(
                "Agnes API Key 未配置（AGNES_API_KEY / AGNES_FREE_API_KEY / "
                "AGNES_CN_FREE_API_KEY）；非 MOCK_MODE 下拒绝静默出占位图"
            )

        exhausted: set[str] = set()
        result: Path | None = None
        last_exc: Exception | None = None
        last_key: AgnesApiKey | None = None
        # 质检失败不换 Key：沿用上一把成功出图的 key
        sticky_key: AgnesApiKey | None = None

        for attempt in range(_VERIFY_MAX_ATTEMPTS):
            self._raise_if_job_cancelled()
            usable = [k for k in keys if k.value not in exhausted]
            if not usable:
                break

            if sticky_key and sticky_key.value not in exhausted:
                ordered = [sticky_key] + [
                    k for k in usable if k.value != sticky_key.value
                ]
            else:
                ordered = usable

            generated = False
            for key in ordered:
                last_key = key
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
                    sticky_key = key
                    generated = True
                    break
                except AgnesContentPolicyError:
                    raise
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
                                "%s agnes %s key failed (%s), "
                                "switching to backup (%s)",
                                log_tag,
                                key.label,
                                type(exc).__name__,
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

            if not get_settings().agnes_image_verify:
                logger.info(
                    "%s agnes generate ok (%s key, verify disabled)",
                    log_tag,
                    last_key.label if last_key else "?",
                )
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
            logger.warning(
                "%s agnes image verify FAILED (%s key, attempt=%s/%s, "
                "prompt_chars=%s, speakers=%s)%s",
                log_tag,
                key_label,
                attempt + 1,
                _VERIFY_MAX_ATTEMPTS,
                len(prompt),
                expected_speakers,
                ", regenerating with same key…" if more else ", raise for prompt re_gen",
            )

        if result is not None and result.exists():
            raise AgnesImageVerifyFailed(
                f"agnes image verify failed after {_VERIFY_MAX_ATTEMPTS} attempts",
                output_path=result,
                prompt=prompt,
            )
        if last_exc:
            raise last_exc
        raise AgnesImageError("agnes generate failed without exception")

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
        "项「手臂」：只报该角色末端呈人手形态的肢端条数，只答阿拉伯数字；"
        "起点是肩膀/腋下/腰侧/胸口/身前都要数，多出来的第3只手必须计入；"
        "手里握着东西的手也要算进去——手和握着的东西是两回事；"
        "剪柄、纸边不算；不要用「人只有两臂」改口；不要用是/否。"
        "项「腿」：只报该角色末端呈人脚或鞋子形态的肢端条数，只答阿拉伯数字；"
        "起点是髋/臀/膝盖/桌下都要数，多出来的第3条腿必须计入；"
        "桌腿、椅腿、裤褶不算；不要用「人只有两腿」改口；不要用是/否。"
        "项「嘴型」：只看该项写明角色本人是否张着嘴，微张即算张（答是）；"
        "完全闭合才答「否」；其他人物的嘴型与本项无关。"
        "项「人数」：数清晰完整的主体人头，只回答阿拉伯数字；"
        "不判断是谁；两个相同服装/双胞胎/额外漂浮人头各算一人；"
        "背景照片墙/镜子虚影/玩具人脸/远处剪影一律不算。"
        "项「粉卫衣」：穿粉色卫衣的女孩是否恰好 1 个；多了（含漂浮头）答否。"
        "项「单扇门」：门是否只有一个门扇（单开门）；"
        "左右各一扇的双开门/对开门答「否」。"
        "项「无飘发」：画面里是否没有不连在任何人头上的独立马尾/发束/一绺头发"
        "（含从门缝/门外飘入的）；有则答「否」，没有答「是」。"
        "项「风向」：风吹头发时，发丝是否顺着风背离门口飘（不朝门口方向）；"
        "朝门口方向飘答「否」。"
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

    _CN_COUNT = {
        "零": 0,
        "一": 1,
        "二": 2,
        "两": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
        "十": 10,
    }

    @staticmethod
    def _parse_person_count(body: str) -> int | None:
        """解析人数项答案为整数；是/否等非数字返回 None。"""
        text = (body or "").strip().strip("。．.")
        if not text:
            return None
        m = re.search(r"(\d+)\s*个?", text)
        if m:
            return int(m.group(1))
        m = re.search(r"([零一二两三四五六七八九十])\s*个?", text)
        if m:
            return AgnesImageProvider._CN_COUNT.get(m.group(1))
        return None

    @staticmethod
    def _allowed_cast_for_verify(
        *,
        speakers: list[str],
        content_style: str | None,
    ) -> list[str]:
        """本段允许出镜角色（有序）→ cast_count 上限 = len(结果)。

        - 以 expected_speakers（发言 ∪ 台词写明在场）为底
        - daily_story：始终可带昭昭/灿灿（未发言也可同框）
        - 妈妈：传入的 speakers 已含「妈妈」时保留（含未发言但台词写明在场）
        """
        allowed: set[str] = {s for s in speakers if s}
        if content_style == CONTENT_STYLE_DAILY_STORY:
            allowed.update(_DAILY_SIBLINGS)
        ordered = [name for name in _DAILY_SPEAKER_ORDER if name in allowed]
        for name in speakers:
            if name and name not in ordered:
                ordered.append(name)
        return ordered

    @staticmethod
    def _build_verify_checklist(
        *,
        prompt: str,
        expected_speakers: list[str] | None,
        content_style: str | None,
    ) -> tuple[list[tuple[str, str]], str, int | None]:
        """返回 ([(check_id, question), ...], user_prompt, cast_max)。"""
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
                    "图中短发男孩即昭昭。"
                    "其发型是否为男孩超短发"
                    "（耳上短发、双耳与后颈清晰可见，圆寸/学生头感；"
                    "若为女童波波头、齐肩短发、厚刘海遮额或任何马尾则答「否」）？"
                    "回答「是」或「否」；"
                    "仅当画面完全没有短发男孩时才答「无昭昭」",
                )
            )
        if content_style == CONTENT_STYLE_DAILY_STORY and "灿灿" in speakers:
            items.append(
                (
                    "can_hair",
                    "图中扎马尾的女孩即灿灿。"
                    "其发型与发色是否同时满足："
                    "①单侧高马尾（仅一根，非双马尾/麻花辫/披肩长发）；"
                    "②头发通体黑色或深黑棕，从头顶到马尾同一深色；"
                    "若马尾、刘海或发丝出现蓝/粉/黄/绿等霓虹条纹、彩虹挑染、"
                    "彩色高光块，即使发根偏黑也答「否」。"
                    "回答「是」或「否」；"
                    "仅当画面完全没有扎马尾女孩时才答「无灿灿」",
                )
            )
            items.append(
                (
                    "can_one",
                    "画面中穿粉色卫衣的女孩是否恰好 1 个？"
                    "出现两个及以上粉卫衣女孩、或额外漂浮的女孩头/脸答「否」。"
                    "回答「是」或「否」",
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
        # 左右站位：提示词写了「左边是A，右边是B」时校验，防 T2I 对调导致后续嘴型全反
        lr = re.search(
            r"画面左边是\s*(昭昭|灿灿|妈妈)\s*[，,；;]?\s*右边是\s*(昭昭|灿灿|妈妈)",
            scene_prompt,
        )
        if content_style == CONTENT_STYLE_DAILY_STORY and lr:
            left, right = lr.group(1), lr.group(2)
            items.append(
                (
                    "lr_pos",
                    f"画面左边是否为{_DAILY_LOOK.get(left, left)}、"
                    f"右边是否为{_DAILY_LOOK.get(right, right)}？"
                    "若左右人物对调答「否」。"
                    "回答「是」或「否」",
                )
            )
        # 嘴型：首个说话人必须张嘴；完全闭合（闭嘴）硬失败。
        mouth = _MOUTH_FIRST_SPEAKER_RE.search(scene_prompt)
        if content_style == CONTENT_STYLE_DAILY_STORY and mouth:
            first = mouth.group(1)
            items.append(
                (
                    "mouth_first",
                    f"{_DAILY_LOOK.get(first, first)}是否张着嘴"
                    "（微张/张开做说话状都算「是」）？"
                    "只看该角色本人，其他人张嘴与否不影响本项；"
                    "该角色嘴巴完全闭合才答「否」。"
                    "回答「是」或「否」",
                )
            )
        # 道具归属：提示词写「XX手持道具」时只拦「不见了 / 别人拿着」。
        # 涂鸦风经常把小物件画到持物人身前桌上，不当硬失败。
        prop_match = None
        for clause in re.split(r"[；;。]", scene_prompt):
            m = _PROP_HOLDER_RE.search(clause)
            if not m:
                continue
            roles = re.findall(r"昭昭|灿灿|妈妈", clause[: m.start()])
            if roles:
                prop_match = (roles[-1], m.group("hand") or "手中", m.group("prop"))
                break
        if content_style == CONTENT_STYLE_DAILY_STORY and prop_match:
            holder, hand, prop = prop_match
            others = [
                name
                for name in ("昭昭", "灿灿", "妈妈")
                if name in speakers and name != holder
            ]
            look = _DAILY_LOOK.get(holder, holder)
            question = (
                f"画面中是否能看到{prop}？"
                f"在{look}的{hand}里、碰到该手，或就在其身前桌面上，都算「是」。"
                f"仅当完全看不到{prop}，或明显在其他人手里时答「否」。"
            )
            if others:
                question += (
                    "其他人指"
                    + "、".join(_DAILY_LOOK.get(name, name) for name in others)
                    + "。"
                )
            question += "回答「是」或「否」"
            items.append(("prop_holder", question))
        # 承托物/关键道具在场：提示词写了托盘等就必须可见，防止道具凭空消失
        if "托盘" in scene_prompt:
            items.append(
                (
                    "prop_present",
                    "画面中场景里的托盘是否清晰可见？"
                    "若托盘缺失、被完全遮挡或画成其他物体答「否」。"
                    "回答「是」或「否」",
                )
            )
        # 单扇门：提示词写门时校验，防 T2I 画成双开门/对开门
        if "门" in scene_prompt:
            items.append(
                (
                    "door_single",
                    "画面中的门是否只有一个门扇（单扇门/单开门）？"
                    "若为双开门/对开门（左右各一个门扇）答「否」。"
                    "回答「是」或「否」",
                )
            )
        # 无独立飘发：提示词写风吹头发时校验，防独立马尾/发丝从门外飘入
        if any(w in scene_prompt for w in ("风", "吹")) and any(
            w in scene_prompt for w in ("头发", "马尾")
        ):
            items.append(
                (
                    "no_float_hair",
                    "画面中是否没有不连在任何人头上的独立马尾/发束/一绺头发"
                    "（尤其从门口/门缝飘入的）？没有答「是」，有则答「否」。"
                    "回答「是」或「否」",
                )
            )
        # 风向：门+风吹头发时，发丝须背离门口（顺风），防逆风朝门飘
        if (
            "门" in scene_prompt
            and any(w in scene_prompt for w in ("风", "吹"))
            and any(w in scene_prompt for w in ("头发", "马尾"))
        ):
            items.append(
                (
                    "hair_wind_dir",
                    "画面中头发被风吹起时，发丝是否顺着风背离门口方向飘动"
                    "（不朝门口方向）？若发丝朝门口方向飘答「否」。"
                    "回答「是」或「否」",
                )
            )
        allowed = AgnesImageProvider._allowed_cast_for_verify(
            speakers=speakers,
            content_style=content_style,
        )
        # 手臂/腿条数：是/否不可靠（三臂/三腿仍答「是」）。按人报数字。
        if content_style == CONTENT_STYLE_DAILY_STORY:
            for name in _DAILY_SPEAKER_ORDER:
                if name in allowed and name in _DAILY_ARM_IDS:
                    items.append(
                        (
                            _DAILY_ARM_IDS[name],
                            _arm_count_question(_DAILY_LOOK[name]),
                        )
                    )
            for name in _DAILY_SPEAKER_ORDER:
                if name in allowed and name in _DAILY_LEG_IDS:
                    items.append(
                        (
                            _DAILY_LEG_IDS[name],
                            _leg_count_question(_DAILY_LOOK[name]),
                        )
                    )
        else:
            items.append(
                (
                    "extra_arms",
                    "画面中手臂最多的那个人，末端呈人手形态的肢端一共几条？"
                    "起点是肩膀/腋下/腰侧/胸口/身前都要数；剪柄纸边不算。"
                    "不要用「人只有两臂」改口。只回答阿拉伯数字",
                )
            )
            items.append(
                (
                    "extra_legs",
                    "画面中腿最多的那个人，末端呈人脚或鞋子形态的肢端一共几条？"
                    "起点是髋/臀/膝盖/桌下都要数；桌腿椅腿裤褶不算。"
                    "不要用「人只有两腿」改口。只回答阿拉伯数字",
                )
            )
        cast_max: int | None = None
        if allowed:
            cast_max = len(allowed)
            # 要数字而非是/否：VL 对「是否不超过 N」常把双胞胎/漂浮头漏算。
            items.append(
                (
                    "cast_count",
                    f"画面清晰完整的主体人头一共几个？"
                    f"（上限参考 {cast_max}，但须如实报数）"
                    "只数人头，不判断是谁；"
                    "两个相同粉卫衣女孩/双胞胎外形/额外漂浮人头各算一人；"
                    "背景照片墙/镜子虚影/玩具人脸/远处剪影不算。"
                    "只回答阿拉伯数字，例如「3」",
                )
            )

        lines = [
            f"【核心场景】\n{scene_prompt}\n",
            f"请检查以下 {len(items)} 项，每项一行：",
        ]
        for i, (_cid, q) in enumerate(items, start=1):
            lines.append(f"项{i}: {q}")
        lines.append("不要输出任何其他内容。")
        return items, "\n".join(lines), cast_max

    @staticmethod
    def _extract_item_lines(text: str) -> str:
        """从正文或思考链中抽出「项N: …」行。"""
        lines = [
            ln.strip()
            for ln in (text or "").splitlines()
            if _ITEM_LINE_RE.match(ln.strip())
        ]
        return "\n".join(lines)

    @staticmethod
    def _vl_message_text(msg: dict) -> str:
        """取出可用于质检解析的文本。

        Agnes VL 常把短答案放进 reasoning_content，content 为空；
        嘴型质检已处理，出图质检须同样回退，否则全项 unknown。
        """
        content = (msg.get("content") or "").strip()
        extracted = AgnesImageProvider._extract_item_lines(content)
        if extracted:
            return extracted
        reasoning = (msg.get("reasoning_content") or "").strip()
        extracted = AgnesImageProvider._extract_item_lines(reasoning)
        if extracted:
            return extracted
        return content or reasoning

    @staticmethod
    def _evaluate_verify_response(
        content: str,
        check_ids: list[str],
        *,
        cast_max: int | None = None,
    ) -> bool:
        """按检查项判定。

        单项解析失败仍跳过（避免误杀）；但若整段一个有效项都没有，
        视为质检失效，返回 False 触发重生（避免全 unknown 放行）。
        cast_count 须报数字，并由 cast_max 卡上限（是/否已不可靠）。
        手臂/腿条数须报数字，超过 2 失败。
        其余项：答「是」通过；答「否」失败
        （zhao_hair「无昭昭」、can_hair「无灿灿」、mom_adult「无妈妈」放行）。
        """
        raw_answers: dict[int, str] = {}
        for raw in content.split("\n"):
            line = raw.strip()
            if not line:
                continue
            m = _ITEM_LINE_RE.match(line)
            if not m:
                continue
            raw_answers[int(m.group(1))] = m.group(2)

        parsed_any = False
        for i, cid in enumerate(check_ids, start=1):
            raw = raw_answers.get(i)
            if raw is None:
                continue
            if cid == "cast_count":
                n = AgnesImageProvider._parse_person_count(raw)
                if n is None:
                    # 人数项必须给出数字；是/否或空答视为质检失败
                    return False
                parsed_any = True
                if cast_max is not None and n > cast_max:
                    return False
                continue
            if cid in _ARM_COUNT_IDS:
                n = AgnesImageProvider._parse_person_count(raw)
                if n is None:
                    return False
                parsed_any = True
                if n > _MAX_ARMS_PER_PERSON:
                    return False
                continue
            if cid in _LEG_COUNT_IDS:
                n = AgnesImageProvider._parse_person_count(raw)
                if n is None:
                    return False
                parsed_any = True
                if n > _MAX_LEGS_PER_PERSON:
                    return False
                continue
            verdict = AgnesImageProvider._parse_item_answer(raw)
            if verdict == "unknown":
                continue
            parsed_any = True
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
                "can_one",
                "mom_adult",
                "lr_pos",
                "mouth_first",
                "prop_holder",
                "prop_present",
                "door_single",
                "no_float_hair",
                "hair_wind_dir",
            }:
                return False
        return parsed_any

    @staticmethod
    def _format_verify_reply(content: str, check_ids: list[str]) -> str:
        """解析回复，生成「scene=yes cast_count=4 …」格式的简短日志。"""
        raw_answers: dict[int, str] = {}
        for raw in content.split("\n"):
            line = raw.strip()
            if not line:
                continue
            m = _ITEM_LINE_RE.match(line)
            if not m:
                continue
            raw_answers[int(m.group(1))] = m.group(2)
        parts: list[str] = []
        for i, cid in enumerate(check_ids, start=1):
            raw = raw_answers.get(i)
            if raw is None:
                parts.append(f"{cid}=unknown")
                continue
            if cid == "cast_count" or cid in _ARM_COUNT_IDS or cid in _LEG_COUNT_IDS:
                n = AgnesImageProvider._parse_person_count(raw)
                parts.append(f"{cid}={n if n is not None else 'unknown'}")
                continue
            parts.append(f"{cid}={AgnesImageProvider._parse_item_answer(raw)}")
        return " ".join(parts)

    def _verify_image(
        self,
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

            items, user, cast_max = AgnesImageProvider._build_verify_checklist(
                prompt=prompt,
                expected_speakers=expected_speakers,
                content_style=content_style,
            )
            check_ids = [cid for cid, _ in items]

            keys = agnes_api_keys(settings)
            if not keys:
                return True

            log_tag = f"[out={image_path.name}]"
            for retry in range(_VERIFY_RETRY_COUNT + 1):
                self._raise_if_job_cancelled()
                for api_key in keys:
                    try:
                        headers = agnes_auth_header(api_key.value)
                        verify_url = (
                            f"{agnes_key_base_url(api_key, settings)}/chat/completions"
                        )
                        url = verify_url
                        host_failover_tried: set[str] = {verify_url}
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
                            # agnes VL 强制思考且关不掉，预算须容纳思考链，
                            # 否则正文为空 → 全项 unknown → 质检形同虚设
                            "max_tokens": 16384,
                        }

                        def _post_verify() -> requests.Response:
                            nonlocal url, verify_url
                            resp = requests.post(
                                url, headers=headers, json=payload, timeout=300
                            )
                            if resp.status_code == 503:
                                alt = agnes_apply_host_failover(
                                    url,
                                    host_failover_tried,
                                    reason="503",
                                    tag=f"{log_tag} verify",
                                )
                                if alt:
                                    verify_url = alt
                                    url = alt
                                    resp = requests.post(
                                        url, headers=headers, json=payload, timeout=300
                                    )
                            return resp

                        resp = self._run_blocking_cancellable(_post_verify)
                        if resp.status_code == 503:
                            continue
                        if resp.ok:
                            msg = (
                                resp.json()
                                .get("choices", [{}])[0]
                                .get("message", {})
                                or {}
                            )
                            content = AgnesImageProvider._vl_message_text(msg)
                            ok = AgnesImageProvider._evaluate_verify_response(
                                content, check_ids, cast_max=cast_max
                            )
                            logger.info(
                                "%s agnes verify (%s key, retry=%s/%s): ok=%s %s",
                                log_tag,
                                api_key.label,
                                retry,
                                _VERIFY_RETRY_COUNT,
                                ok,
                                AgnesImageProvider._format_verify_reply(content, check_ids),
                            )
                            if ok and content_style == CONTENT_STYLE_DAILY_STORY:
                                ok = self._verify_hardfail_limbs(
                                    image_path,
                                    expected_speakers=expected_speakers,
                                    content_style=content_style,
                                )
                            return ok
                        logger.warning(
                            "%s agnes verify_image http %s (%s key, retry=%s/%s), body=%s",
                            log_tag,
                            resp.status_code,
                            api_key.label,
                            retry,
                            _VERIFY_RETRY_COUNT,
                            _resp_body_summary(resp),
                        )
                    except requests.Timeout as exc:
                        alt = agnes_apply_host_failover(
                            verify_url,
                            host_failover_tried,
                            reason="timeout",
                            tag=f"{log_tag} verify",
                        )
                        if alt:
                            verify_url = alt
                            continue
                        logger.warning(
                            "%s agnes verify_image timeout (%s key, retry=%s/%s): %s",
                            log_tag,
                            api_key.label,
                            retry,
                            _VERIFY_RETRY_COUNT,
                            exc,
                        )
                    except Exception as exc:
                        logger.warning(
                            "%s agnes verify_image call failed (%s key, retry=%s/%s): %s",
                            log_tag,
                            api_key.label,
                            retry,
                            _VERIFY_RETRY_COUNT,
                            exc,
                        )
                if retry < _VERIFY_RETRY_COUNT:
                    logger.info(
                        "%s agnes verify retrying in %ss (retry=%s/%s)",
                        log_tag,
                        _VERIFY_RETRY_DELAY,
                        retry + 1,
                        _VERIFY_RETRY_COUNT,
                    )
                    self._sleep_cancellable(_VERIFY_RETRY_DELAY)
            logger.warning(
                "%s agnes verify exhausted (all keys failed after %s retries)",
                log_tag,
                _VERIFY_RETRY_COUNT + 1,
            )
            return False
        except Exception as exc:
            logger.warning(
                "agnes verify_image error [out=%s]: %s", image_path.name, exc
            )
            return True

    # ── 多手硬卡：裁剪放大数手 ────────────────────────────────

    @staticmethod
    def _crop_zone_data_url(
        image_path: Path,
        zone: str,
        *,
        zoom: int = _HARDFAIL_ZOOM,
    ) -> str:
        """把角色所在区域裁剪出来并放大，返回 base64 data URL。

        daily 固定布局：昭昭在左半幅、灿灿在右半幅、妈妈在中间半幅。
        整图 VL 对低分辨率多手会漏（三手相叠/握着东西被忽略），
        裁剪放大后手部轮廓更清晰，VL 才能数出来。
        """
        img = PILImage.open(image_path)
        w, h = img.size
        if zone == "left":
            box = (0, 0, w // 2, h)
        elif zone == "right":
            box = (w // 2, 0, w, h)
        else:  # center
            box = (w // 4, 0, w * 3 // 4, h)
        crop = img.crop(box)
        crop = crop.resize(
            (crop.size[0] * zoom, crop.size[1] * zoom), PILImage.LANCZOS
        )
        max_dim = 1024
        if max(crop.size) > max_dim:
            ratio = max_dim / max(crop.size)
            crop = crop.resize(
                (int(crop.size[0] * ratio), int(crop.size[1] * ratio)),
                PILImage.LANCZOS,
            )
        buf = io.BytesIO()
        crop.convert("RGB").save(buf, format="JPEG", quality=92)
        return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")

    def _verify_hardfail_limbs(
        self,
        image_path: Path,
        *,
        expected_speakers: list[str] | None,
        content_style: str | None,
    ) -> bool:
        """多手硬卡：对出镜角色裁剪放大后数手，任何角色 >2 手即失败。

        返回 False 触发整图重生成。网络/解析失败跳过该角色（不误杀），
        仅当 VL 明确给出「>2 手」或「多手=是」时才判失败。
        """
        if content_style != CONTENT_STYLE_DAILY_STORY:
            return True
        if not image_path.exists():
            return True
        settings = get_settings()
        keys = agnes_api_keys(settings)
        if not keys:
            return True
        speakers = [str(s).strip() for s in (expected_speakers or []) if str(s).strip()]
        allowed = AgnesImageProvider._allowed_cast_for_verify(
            speakers=speakers,
            content_style=content_style,
        )
        roles = [name for name in allowed if name in _HARDFAIL_ZONE]
        if not roles:
            return True

        log_tag = f"[out={image_path.name}]"
        for name in roles:
            zone = _HARDFAIL_ZONE[name]
            try:
                data_url = AgnesImageProvider._crop_zone_data_url(image_path, zone)
            except Exception as exc:
                logger.warning(
                    "%s agnes hardfail crop %s error: %s", log_tag, name, exc
                )
                continue
            look = _DAILY_LOOK.get(name, name)
            question = (
                _HARDFAIL_ARM_Q1.format(look=look)
                + "\n"
                + _HARDFAIL_ARM_Q2.format(look=look)
            )
            answer = self._ask_hardfail_vl(settings, keys, data_url, question, log_tag)
            if answer is None:
                continue
            count, extra = AgnesImageProvider._parse_hardfail_arm_answer(answer)
            hit = (count is not None and count > _MAX_ARMS_PER_PERSON) or (
                extra is True
            )
            logger.info(
                "%s agnes hardfail limbs %s: count=%s extra=%s hit=%s",
                log_tag,
                name,
                count,
                extra,
                hit,
            )
            if hit:
                return False
        return True

    def _ask_hardfail_vl(
        self,
        settings,
        keys: list,
        data_url: str,
        question: str,
        log_tag: str,
    ) -> str | None:
        """裁剪图数手 VL 调用；网络失败返回 None（跳过该角色）。"""
        for api_key in keys:
            try:
                headers = agnes_auth_header(api_key.value)
                url = f"{agnes_key_base_url(api_key, settings)}/chat/completions"
                payload = {
                    "model": settings.agnes_vl_model,
                    "messages": [
                        {
                            "role": "system",
                            "content": _HARDFAIL_ARM_SYSTEM_PROMPT,
                        },
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": question},
                                {"type": "image_url", "image_url": {"url": data_url}},
                            ],
                        },
                    ],
                    "max_tokens": 16384,
                }

                def _post() -> requests.Response:
                    return requests.post(
                        url, headers=headers, json=payload, timeout=300
                    )

                resp = self._run_blocking_cancellable(_post)
                if resp.ok:
                    msg = (
                        resp.json()
                        .get("choices", [{}])[0]
                        .get("message", {})
                        or {}
                    )
                    return AgnesImageProvider._vl_message_text(msg)
                logger.warning(
                    "%s agnes hardfail http %s (%s key): %s",
                    log_tag,
                    resp.status_code,
                    api_key.label,
                    _resp_body_summary(resp),
                )
            except Exception as exc:
                logger.warning(
                    "%s agnes hardfail call failed (%s key): %s",
                    log_tag,
                    api_key.label,
                    exc,
                )
        return None

    @staticmethod
    def _parse_hardfail_arm_answer(body: str) -> tuple[int | None, bool | None]:
        """解析硬卡两问回答，返回 (count, extra)。

        项1 数字为手臂条数；项2 是/否为多手确认。
        解析失败返回 None，调用方跳过（不误杀）。
        """
        count: int | None = None
        extra: bool | None = None
        for raw in (body or "").split("\n"):
            line = raw.strip()
            m = _ITEM_LINE_RE.match(line)
            if not m:
                continue
            num = int(m.group(1))
            text = m.group(2)
            if num == 1:
                count = AgnesImageProvider._parse_person_count(text)
            elif num == 2:
                verdict = AgnesImageProvider._parse_item_answer(text)
                if verdict == "yes":
                    extra = True
                elif verdict == "no":
                    extra = False
        return count, extra
