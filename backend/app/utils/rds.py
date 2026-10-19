"""Redis 访问封装（参照 MyTodo 的 `core/db/rds_mgr.py`）。

本模块提供一组轻量函数用于读写 Redis 的字符串 / Hash / 列表，并统一处理两件
在 gevent 进程里容易踩的事：

1. **每个 OS 线程持有独立的 Redis 客户端**（见 `_current_client`）。
   gevent 下 socket 绑定创建它的线程，跨线程复用连接会抛
   "Cannot switch to a different thread" 并污染连接池；而连接池的锁在
   `patch_all(thread=False)` 下是**真实锁**，hub 的 greenlet 一旦等在其上，
   整个进程会永久冻结。按线程隔离后各方只竞争自己的锁，不存在跨线程等待。
2. **单次操作带超时**（`_safe`）。注意 gevent 的 Timeout 只能中断 gevent 自己
   管理的等待；若阻塞在真实锁上它不会触发。所以超时是兜底，不跨线程共享才是
   根本手段。

连接信息取 `REDIS_URL`（优先）或 `REDIS_HOST/REDIS_PORT/REDIS_DB/REDIS_PASSWORD`。
**未配置**时降级为本地 JSON 文件（`RDS_LOCAL_FILE`，默认 `data/rds_local.json`），
便于本地开发；**已配置但连不上**则抛 `RedisUnavailable`，由调用方决定如何降级，
不静默改数据。
"""

from __future__ import annotations

import json
import logging
import os
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator, TypeVar

from app.config import ROOT_DIR
from app.utils.async_util import hub_safe_lock

logger = logging.getLogger(__name__)

_T = TypeVar("_T")

# gevent 的 Timeout 继承 BaseException，`except Exception` 接不住，必须单独列出来
try:
    from gevent.timeout import Timeout as _GeventTimeout

    _TIMEOUT_TYPES: tuple[type[BaseException], ...] = (_GeventTimeout,)
except ImportError:  # pragma: no cover - gevent 是运行依赖
    _TIMEOUT_TYPES = ()

_KEY_PREFIX_ENV = "RDS_KEY_PREFIX"
_DEFAULT_KEY_PREFIX = "video_factory:"
_OP_TIMEOUT_SEC = 3.0
_SOCKET_TIMEOUT_SEC = 5
_DEFAULT_LOCAL_FILE = ROOT_DIR / "data" / "rds_local.json"


class RedisUnavailable(RuntimeError):
    """Redis 已配置但当前不可用（连不上 / 超时 / 操作失败）。"""


# ---------------------------------------------------------------- 连接信息
def _redis_url() -> str:
    return (os.getenv("REDIS_URL") or "").strip()


def _redis_host() -> str:
    return (os.getenv("REDIS_HOST") or "").strip()


def is_configured() -> bool:
    """是否配置了 Redis；未配置时走本地 JSON 兜底。"""
    return bool(_redis_url() or _redis_host())


def key_prefix() -> str:
    """键前缀，默认 `video_factory:`，可用 `RDS_KEY_PREFIX` 覆盖。"""
    raw = os.getenv(_KEY_PREFIX_ENV)
    return _DEFAULT_KEY_PREFIX if raw is None else raw.strip()


def prefixed(key: str) -> str:
    """给业务键加上项目前缀，避免与同实例的其它项目撞键。"""
    return f"{key_prefix()}{key}"


def _create_client() -> Any:
    try:
        import redis
    except ImportError as exc:  # pragma: no cover - requirements 已含 redis
        raise RedisUnavailable("未安装 redis 库") from exc

    url = _redis_url()
    if url:
        return redis.Redis.from_url(
            url,
            socket_connect_timeout=_SOCKET_TIMEOUT_SEC,
            socket_timeout=_SOCKET_TIMEOUT_SEC,
        )
    return redis.Redis(
        host=_redis_host() or "localhost",
        port=int(os.getenv("REDIS_PORT", "6379")),
        db=int(os.getenv("REDIS_DB", "0")),
        password=os.getenv("REDIS_PASSWORD") or None,
        socket_connect_timeout=_SOCKET_TIMEOUT_SEC,
        socket_timeout=_SOCKET_TIMEOUT_SEC,
    )


# 每线程一份客户端（含独立连接池与锁），理由见模块文档。
_thread_local = threading.local()
_client_generation = 0


def _current_client() -> Any:
    if not is_configured():
        raise RedisUnavailable("未配置 REDIS_URL / REDIS_HOST")
    client = getattr(_thread_local, "client", None)
    if client is None or getattr(_thread_local, "gen", -1) != _client_generation:
        client = _create_client()
        _thread_local.client = client
        _thread_local.gen = _client_generation
    return client


def reset_clients() -> None:
    """丢弃各线程的旧客户端（重连或测试替换连接信息后调用）。"""
    global _client_generation
    _client_generation += 1


def ping() -> bool:
    """探活；未配置或连不上返回 False，不抛异常。"""
    if not is_configured():
        return False
    try:
        _safe(lambda: _current_client().ping())
        return True
    except RedisUnavailable:
        return False


# ---------------------------------------------------------------- 本地兜底
def _local_file() -> Path:
    raw = os.getenv("RDS_LOCAL_FILE")
    return Path(raw) if raw else _DEFAULT_LOCAL_FILE


class _LocalStore:
    """未配置 Redis 时用单个 JSON 文件模拟字符串 / Hash / 列表。

    只服务本地开发，不做并发优化：临界区里没有任何会让出 greenlet 的调用
    （文件读写不被 gevent 打补丁），锁用 `hub_safe_lock`（gevent 锁）而非
    `threading.Lock`，与进程里其它模块的约定一致。
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = hub_safe_lock()
        self._data: dict[str, dict[str, Any]] = {"strings": {}, "hashes": {}, "lists": {}}
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            loaded = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("本地兜底文件读取失败 %s: %s", self._path, exc)
            return
        if isinstance(loaded, dict):
            for bucket in self._data:
                value = loaded.get(bucket)
                if isinstance(value, dict):
                    self._data[bucket] = value

    def _persist(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        tmp.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self._path)

    def get(self, key: str) -> bytes | None:
        with self._lock:
            value = self._data["strings"].get(key)
            return None if value is None else str(value).encode("utf-8")

    def set(self, key: str, value: Any) -> bool:
        with self._lock:
            self._data["strings"][key] = _to_str(value)
            self._persist()
            return True

    def delete(self, key: str) -> int:
        with self._lock:
            removed = 0
            for bucket in self._data.values():
                if bucket.pop(key, None) is not None:
                    removed = 1
            if removed:
                self._persist()
            return removed

    def exists(self, key: str) -> int:
        with self._lock:
            return int(any(key in bucket for bucket in self._data.values()))

    def hset(self, key: str, field: str, value: Any) -> int:
        with self._lock:
            bucket = self._data["hashes"].setdefault(key, {})
            is_new = field not in bucket
            bucket[field] = _to_str(value)
            self._persist()
            return int(is_new)

    def hget(self, key: str, field: str) -> bytes | None:
        with self._lock:
            value = self._data["hashes"].get(key, {}).get(field)
            return None if value is None else str(value).encode("utf-8")

    def hgetall(self, key: str) -> dict[str, str]:
        with self._lock:
            bucket = self._data["hashes"].get(key, {})
            return {str(k): _to_str(v) for k, v in bucket.items()}

    def hdel(self, key: str, field: str) -> int:
        with self._lock:
            bucket = self._data["hashes"].get(key)
            if not bucket or field not in bucket:
                return 0
            bucket.pop(field)
            self._persist()
            return 1

    def lrange(self, key: str, start: int, end: int) -> list[str]:
        with self._lock:
            items = [str(item) for item in self._data["lists"].get(key, [])]
        if not items:
            return []
        n = len(items)
        start = max(n + start, 0) if start < 0 else start
        end = n + end if end < 0 else min(end, n - 1)
        return items[start : end + 1] if start <= end else []

    def lpush(self, key: str, value: Any) -> int:
        with self._lock:
            items = self._data["lists"].setdefault(key, [])
            items.insert(0, _to_str(value))
            self._persist()
            return len(items)

    def rpush(self, key: str, value: Any) -> int:
        with self._lock:
            items = self._data["lists"].setdefault(key, [])
            items.append(_to_str(value))
            self._persist()
            return len(items)

    def llen(self, key: str) -> int:
        with self._lock:
            return len(self._data["lists"].get(key, []))


_local_store: _LocalStore | None = None
_local_lock = hub_safe_lock()


def _local() -> _LocalStore:
    global _local_store
    if _local_store is None:
        with _local_lock:
            if _local_store is None:
                _local_store = _LocalStore(_local_file())
                logger.info("[RDS] 未配置 Redis，使用本地兜底文件 %s", _local_file())
    return _local_store


def _to_str(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return "" if value is None else str(value)


# ---------------------------------------------------------------- 通用执行
@contextmanager
def _timeout(seconds: float) -> Iterator[None]:
    try:
        from gevent import Timeout
    except ImportError:  # pragma: no cover - gevent 是运行依赖
        yield
        return
    with Timeout(seconds):
        yield


def _safe(operation: Callable[[], _T], *, timeout: float = _OP_TIMEOUT_SEC) -> _T:
    """执行一次 Redis 操作，把驱动异常与超时统一成 `RedisUnavailable`。"""
    try:
        import redis
    except ImportError as exc:  # pragma: no cover
        raise RedisUnavailable("未安装 redis 库") from exc

    try:
        with _timeout(timeout):
            return operation()
    except redis.RedisError as exc:
        raise RedisUnavailable(f"Redis 操作失败: {exc}") from exc
    except _TIMEOUT_TYPES as exc:
        # Timeout 继承 BaseException：这里必须显式列出，否则会穿透调用方
        raise RedisUnavailable(f"Redis 操作超时（{timeout}s）") from exc


# ---------------------------------------------------------------- 字符串
def get(key: str) -> bytes | None:
    if not is_configured():
        return _local().get(key)
    client = _current_client()
    return _safe(lambda: client.get(key))


def get_str(key: str) -> str:
    """取字符串值，不存在返回空串。"""
    value = get(key)
    return "" if value is None else _to_str(value)


def set(key: str, value: Any) -> bool:
    if not is_configured():
        return _local().set(key, value)
    client = _current_client()
    return bool(_safe(lambda: client.set(key, value)))


def setex(key: str, ttl_seconds: int, value: Any) -> bool:
    if not is_configured():
        return _local().set(key, value)
    client = _current_client()
    return bool(_safe(lambda: client.setex(key, ttl_seconds, value)))


def delete(key: str) -> int:
    if not is_configured():
        return _local().delete(key)
    client = _current_client()
    return int(_safe(lambda: client.delete(key)))


def exists(key: str) -> int:
    if not is_configured():
        return _local().exists(key)
    client = _current_client()
    return int(_safe(lambda: client.exists(key)))


# ---------------------------------------------------------------- Hash
def hset(key: str, field: str, value: Any) -> int:
    if not is_configured():
        return _local().hset(key, field, value)
    client = _current_client()
    return int(_safe(lambda: client.hset(key, field, value)))


def hget(key: str, field: str) -> bytes | None:
    if not is_configured():
        return _local().hget(key, field)
    client = _current_client()
    return _safe(lambda: client.hget(key, field))


def hgetall(key: str) -> dict[str, str]:
    if not is_configured():
        return _local().hgetall(key)
    client = _current_client()
    raw = _safe(lambda: client.hgetall(key)) or {}
    return {_to_str(k): _to_str(v) for k, v in raw.items()}


def hdel(key: str, field: str) -> int:
    if not is_configured():
        return _local().hdel(key, field)
    client = _current_client()
    return int(_safe(lambda: client.hdel(key, field)))


# ---------------------------------------------------------------- 列表
def lrange(key: str, start: int, end: int) -> list[str]:
    if not is_configured():
        return _local().lrange(key, start, end)
    client = _current_client()
    raw = _safe(lambda: client.lrange(key, start, end)) or []
    return [_to_str(item) for item in raw]


def lpush(key: str, value: Any) -> int:
    if not is_configured():
        return _local().lpush(key, value)
    client = _current_client()
    return int(_safe(lambda: client.lpush(key, value)))


def rpush(key: str, value: Any) -> int:
    if not is_configured():
        return _local().rpush(key, value)
    client = _current_client()
    return int(_safe(lambda: client.rpush(key, value)))


def llen(key: str) -> int:
    if not is_configured():
        return _local().llen(key)
    client = _current_client()
    return int(_safe(lambda: client.llen(key)))
