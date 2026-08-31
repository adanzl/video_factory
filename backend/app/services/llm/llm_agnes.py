"""Agnes AI 客户端：公共 API 逻辑与 LLM（OpenAI 兼容 /v1/chat/completions）。"""
from __future__ import annotations
import json
import logging
import time
from dataclasses import dataclass
from collections.abc import Callable
from typing import Any
import requests
from app.config import Settings, get_settings
from app.exceptions import JobStageFailureError
logger = logging.getLogger(__name__)
_QUOTA_STATUS = frozenset({402, 403, 429})
_QUOTA_KEYWORDS = ('quota', 'limit', 'exceeded', 'insufficient', 'balance', 'credit', '余额', '限额', '超限', '额度', '不足', 'rate limit', 'too many')

class AgnesQuotaExceeded(RuntimeError, JobStageFailureError):
    """当前 Key 配额/限流耗尽，可切换备用 Key；整任务失败时不必打堆栈。"""


class AgnesI2VError(RuntimeError, JobStageFailureError):
    """图生视频 API 调用失败（重试耗尽、任务失败等），消息即原因。"""


class AgnesImageError(RuntimeError, JobStageFailureError):
    """文生图 API 调用失败（超时、重试耗尽等），消息即原因。"""


class AgnesContentPolicyError(RuntimeError, JobStageFailureError):
    """内容策略拦截（prompt 违规等），不必打堆栈。"""

@dataclass(frozen=True)
class AgnesApiKey:
    label: str
    value: str
    # 与 Key 绑定的 API 根路径（国际 / 国内站不同）
    base_url: str = ""


def agnes_api_keys(settings: Settings | None = None) -> list[AgnesApiKey]:
    """Key 链：付费 → 国际免费 → 国内免费；各自绑定 base_url。"""
    cfg = settings or get_settings()
    intl = (cfg.agnes_api_base_url or "").rstrip("/")
    cn = (getattr(cfg, "agnes_api_base_url_cn", None) or "").rstrip("/") or intl
    keys: list[AgnesApiKey] = []
    primary = cfg.agnes_api_key
    free = cfg.agnes_free_api_key
    cn_free = getattr(cfg, "agnes_cn_free_api_key", None)
    seen: set[str] = set()
    if primary:
        keys.append(AgnesApiKey("primary", primary, intl))
        seen.add(primary)
    if free and free not in seen:
        keys.append(AgnesApiKey("free", free, intl))
        seen.add(free)
    if cn_free and cn_free not in seen:
        keys.append(AgnesApiKey("cn_free", cn_free, cn))
    return keys


def agnes_key_base_url(api_key: AgnesApiKey, settings: Settings | None = None) -> str:
    """取 Key 绑定地址；缺省回落国际 base_url。"""
    if api_key.base_url:
        return api_key.base_url.rstrip("/")
    cfg = settings or get_settings()
    return (cfg.agnes_api_base_url or "").rstrip("/")


def agnes_auth_header(api_key: str, *, extra: dict[str, str] | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    if extra:
        headers.update(extra)
    return headers


def agnes_should_switch_key(
    exc: BaseException | None = None,
    *,
    status_code: int | None = None,
    body: dict | str | None = None,
    message: str | None = None,
) -> bool:
    """4xx/5xx/配额/限流/超时 → 换下一把 Key。提示词违规不换（上层重生）。"""
    if isinstance(exc, AgnesContentPolicyError):
        return False
    code = status_code
    if code is None and isinstance(exc, requests.HTTPError) and exc.response is not None:
        code = exc.response.status_code
        if body is None:
            try:
                body = exc.response.json()
            except Exception:
                body = (exc.response.text or "")[:500]
    msg = message or (str(exc) if exc else None)
    if is_agnes_content_policy(body=body, message=msg):
        return False
    if isinstance(exc, AgnesQuotaExceeded):
        return True
    if exc is not None and agnes_quota_exceeded_from_exception(exc):
        return True
    if is_agnes_quota_exceeded(status_code=code, body=body, message=msg):
        return True
    if code is not None and code >= 400:
        return True
    if isinstance(exc, (requests.Timeout, requests.ConnectionError)):
        return True
    if isinstance(exc, (AgnesI2VError, AgnesImageError)):
        return True
    text = str(exc or "")
    if "last_status=" in text:
        return True
    if "after" in text and "retries" in text:
        return True
    return False


_AGNES_COM_HOST = "apihub.agnes-ai.com"
_AGNES_CN_HOST = "apihub.agnes-ai.cn"
_AGNES_API_SUFFIXES = ("/chat/completions", "/images/generations", "/videos")


def agnes_alternate_host_url(url: str) -> str | None:
    """apihub 域名 .com ↔ .cn 互换；其它 URL 返回 None。"""
    if _AGNES_COM_HOST in url:
        return url.replace(_AGNES_COM_HOST, _AGNES_CN_HOST, 1)
    if _AGNES_CN_HOST in url:
        return url.replace(_AGNES_CN_HOST, _AGNES_COM_HOST, 1)
    return None


def agnes_is_apihub_url(url: str) -> bool:
    return _AGNES_COM_HOST in url or _AGNES_CN_HOST in url


def agnes_api_base_from_url(url: str) -> str | None:
    """从完整 API URL 提取 /v1 根路径。"""
    for suffix in _AGNES_API_SUFFIXES:
        if suffix in url:
            return url.rsplit(suffix, 1)[0]
    if "/v1" in url:
        idx = url.find("/v1")
        return url[: idx + 3]
    return None


def agnes_try_failover_host(
    url: str,
    tried: set[str],
    *,
    reason: str,
    tag: str = "",
) -> str | None:
    """503/超时等在 apihub .com/.cn 间切换一次（同 Key 内兜底）。"""
    if not agnes_is_apihub_url(url):
        return None
    alt = agnes_alternate_host_url(url)
    if not alt or alt in tried:
        return None
    prefix = f"{tag} " if tag else ""
    logger.warning(
        "%sagnes %s on %s, failover to alternate domain %s",
        prefix,
        reason,
        url,
        alt,
    )
    tried.add(alt)
    return alt


def agnes_apply_host_failover(
    url: str,
    tried: set[str],
    *,
    reason: str,
    tag: str = "",
    on_switch: Callable[[str], None] | None = None,
) -> str | None:
    """切换备用域名（仅当前请求生效，不持久化全局 base_url）；
    on_switch 可同步 provider 端点。"""
    alt = agnes_try_failover_host(url, tried, reason=reason, tag=tag)
    if not alt:
        return None
    if on_switch is not None:
        on_switch(alt)
    return alt


def _collect_error_text(*, status_code: int | None=None, body: dict | str | None=None, message: str | None=None) -> str:
    parts: list[str] = []
    if status_code is not None:
        parts.append(str(status_code))
    if message:
        parts.append(message)
    if isinstance(body, dict):
        err = body.get('error')
        if isinstance(err, dict):
            code = err.get('code')
            msg = err.get('message')
            if code is not None:
                parts.append(str(code))
            if msg is not None:
                parts.append(str(msg))
        elif err is not None:
            parts.append(str(err))
        parts.append(json.dumps(body, ensure_ascii=False))
    elif isinstance(body, str) and body.strip():
        parts.append(body)
    return ' '.join(parts).lower()

def is_agnes_quota_exceeded(*, status_code: int | None=None, body: dict | str | None=None, message: str | None=None) -> bool:
    if status_code in _QUOTA_STATUS:
        return True
    text = _collect_error_text(status_code=status_code, body=body, message=message)
    return any((keyword in text for keyword in _QUOTA_KEYWORDS))

def agnes_quota_exceeded_from_exception(exc: BaseException) -> bool:
    if isinstance(exc, AgnesQuotaExceeded):
        return True
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        body: dict | str | None = None
        try:
            body = exc.response.json()
        except Exception:
            body = exc.response.text[:500]
        return is_agnes_quota_exceeded(status_code=exc.response.status_code, body=body, message=str(exc))
    return is_agnes_quota_exceeded(message=str(exc))

def raise_if_agnes_quota(*, status_code: int | None=None, body: dict | str | None=None, message: str | None=None) -> None:
    if is_agnes_quota_exceeded(status_code=status_code, body=body, message=message):
        detail = _collect_error_text(status_code=status_code, body=body, message=message)
        raise AgnesQuotaExceeded(detail or 'agnes quota or rate limit exceeded')


def is_agnes_content_policy(
    *,
    body: dict | str | None = None,
    message: str | None = None,
) -> bool:
    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict) and err.get("code") == "content_policy_violation":
            return True
    text = _collect_error_text(body=body, message=message)
    return "content_policy_violation" in text


def raise_if_agnes_content_policy(
    *,
    status_code: int | None = None,
    body: dict | str | None = None,
    message: str | None = None,
) -> None:
    if not is_agnes_content_policy(body=body, message=message):
        return
    if status_code is not None:
        raise AgnesContentPolicyError(f"agnes api {status_code}: {body}")
    if message:
        raise AgnesContentPolicyError(message)
    raise AgnesContentPolicyError(f"agnes content_policy_violation: {body}")


# 含 Cloudflare 源站错误 52x（如 520 unknown error）
_RETRYABLE = frozenset({500, 502, 503, 504, 520, 521, 522, 523, 524, 525, 526, 527})

def _build_chat_payload(*, model: str, system: str, user: str, max_tokens: int) -> dict[str, Any]:
    return {'model': model, 'messages': [{'role': 'system', 'content': system}, {'role': 'user', 'content': user}], 'max_tokens': max_tokens, 'response_format': {'type': 'json_object'}}

def _post_chat(*, api_key: AgnesApiKey, base_url: str, payload: dict[str, Any], max_retries: int, connect_timeout: float, read_timeout: float) -> requests.Response:
    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = agnes_auth_header(api_key.value)
    timeout = (connect_timeout, read_timeout)
    last_exc: Exception | None = None
    host_failover_tried: set[str] = {url}
    for attempt in range(max_retries):
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
            if resp.status_code == 503:
                alt = agnes_apply_host_failover(
                    url,
                    host_failover_tried,
                    reason='503',
                    tag='llm',
                )
                if alt:
                    url = alt
                    continue
            if resp.status_code in _RETRYABLE:
                wait = min(2 ** attempt * 2, 60)
                logger.warning('agnes llm %s %s, retry %s/%s in %ss', resp.status_code, url, attempt + 1, max_retries, wait)
                time.sleep(wait)
                continue
            if not resp.ok:
                body: dict | str | None = None
                try:
                    body = resp.json()
                except Exception:
                    body = resp.text[:500]
                raise_if_agnes_content_policy(status_code=resp.status_code, body=body)
                raise_if_agnes_quota(status_code=resp.status_code, body=body)
            resp.raise_for_status()
            return resp
        except AgnesContentPolicyError:
            raise
        except AgnesQuotaExceeded:
            raise
        except requests.RequestException as exc:
            last_exc = exc
            if agnes_quota_exceeded_from_exception(exc):
                raise AgnesQuotaExceeded(str(exc)) from exc
            if isinstance(exc, requests.Timeout):
                alt = agnes_apply_host_failover(
                    url,
                    host_failover_tried,
                    reason='timeout',
                    tag='llm',
                )
                if alt:
                    url = alt
                    continue
            wait = min(2 ** attempt * 2, 60)
            logger.warning('agnes llm request error: %s, retry in %ss', exc, wait)
            time.sleep(wait)
    if last_exc:
        raise last_exc
    raise RuntimeError(f'agnes llm request failed after {max_retries} retries: {url}')

def _chat_with_key_fallback(*, system: str, user: str, max_tokens: int | None=None) -> tuple[str, str | None]:
    settings = get_settings()
    keys = agnes_api_keys(settings)
    if not keys:
        raise RuntimeError(
            'AGNES_API_KEY / AGNES_FREE_API_KEY / AGNES_CN_FREE_API_KEY 未配置，无法使用 Agnes LLM'
        )
    limit = settings.agnes_llm_max_tokens if max_tokens is None else max_tokens
    payload = _build_chat_payload(model=settings.agnes_llm_model, system=system, user=user, max_tokens=limit)
    last_exc: Exception | None = None
    for idx, api_key in enumerate(keys):
        base = agnes_key_base_url(api_key, settings)
        try:
            resp = _post_chat(
                api_key=api_key,
                base_url=base,
                payload=payload,
                max_retries=settings.agnes_http_max_retries,
                connect_timeout=settings.agnes_http_connect_timeout_sec,
                read_timeout=settings.agnes_http_submit_read_timeout_sec,
            )
            choice = resp.json()['choices'][0]
            finish = choice.get('finish_reason')
            content = choice.get('message', {}).get('content') or ''
            if finish == 'length':
                logger.warning('Agnes LLM response truncated (finish_reason=length), max_tokens=%d model=%s', limit, settings.agnes_llm_model)
            return (content, finish)
        except AgnesContentPolicyError:
            raise
        except Exception as exc:
            last_exc = exc
            if idx < len(keys) - 1 and agnes_should_switch_key(exc):
                logger.warning(
                    'agnes llm %s key failed (%s), switching to backup',
                    api_key.label,
                    type(exc).__name__,
                )
                continue
            raise
    if last_exc:
        raise last_exc
    raise RuntimeError('agnes llm chat failed without exception')
_agnes_client_cls: type | None = None

def _agnes_client_class() -> type:
    """延迟继承 DeepSeekClient，避免 import 时触发循环依赖。"""
    global _agnes_client_cls
    if _agnes_client_cls is not None:
        return _agnes_client_cls
    from app.services.llm.llm_deepseek import DeepSeekClient

    class AgnesClient(DeepSeekClient):
        """复用 DeepSeekClient 业务逻辑，HTTP 走 Agnes chat/completions。"""

        def _chat(self, system: str, user: str, *, max_tokens: int | None=None) -> tuple[str, str | None]:
            return _chat_with_key_fallback(system=system, user=user, max_tokens=max_tokens)
    _agnes_client_cls = AgnesClient
    return AgnesClient

def __getattr__(name: str):
    if name == 'AgnesClient':
        return _agnes_client_class()
    raise AttributeError(f'module {__name__!r} has no attribute {name!r}')
