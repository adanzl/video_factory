"""SQLAlchemy Session 上的短事务执行（替代裸 sqlite3 + with connection）。"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Iterator, Mapping, Sequence

from app.repositories.db_obj import db

_in_atomic: ContextVar[bool] = ContextVar("_in_atomic", default=False)
_db_write_lock: object | None = None


def _get_db_write_lock():
    """gevent 同线程多 greenlet 共享 SQLAlchemy session，写库须串行。"""
    global _db_write_lock
    if _db_write_lock is None:
        try:
            from gevent.lock import Semaphore

            _db_write_lock = Semaphore(1)
        except ImportError:
            import threading

            _db_write_lock = threading.Lock()
    return _db_write_lock


class _DriverResult:
    """兼容 repo 对 rowcount / lastrowid / mappings 的用法。"""

    def __init__(self, cursor: sqlite3.Cursor) -> None:
        self._cursor = cursor

    @property
    def rowcount(self) -> int:
        return self._cursor.rowcount

    @property
    def lastrowid(self) -> int | None:
        return self._cursor.lastrowid

    def mappings(self) -> "_MappingRows":
        rows = self._cursor.fetchall()
        return _MappingRows(rows)


class _MappingRows:
    def __init__(self, rows: list[sqlite3.Row]) -> None:
        self._rows = rows

    def first(self) -> dict | None:
        if not self._rows:
            return None
        return dict(self._rows[0])

    def all(self) -> list[dict]:
        return [dict(row) for row in self._rows]


def _params_tuple(params: Sequence[Any] | Mapping[str, Any] | None) -> tuple[Any, ...]:
    if params is None:
        return ()
    if isinstance(params, Mapping):
        raise TypeError("named parameters not supported; use positional ? placeholders")
    return tuple(params)


def execute(
    sql: str,
    params: Sequence[Any] | Mapping[str, Any] | None = None,
) -> _DriverResult:
    raw = db.session.connection().connection.dbapi_connection
    assert isinstance(raw, sqlite3.Connection)
    cur = raw.execute(sql, _params_tuple(params))
    return _DriverResult(cur)


def fetchone(sql: str, params: Sequence[Any] | Mapping[str, Any] | None = None) -> dict | None:
    return execute(sql, params).mappings().first()


def fetchall(sql: str, params: Sequence[Any] | Mapping[str, Any] | None = None) -> list[dict]:
    return execute(sql, params).mappings().all()


def commit() -> None:
    if _in_atomic.get():
        return
    db.session.commit()


def rollback() -> None:
    db.session.rollback()


@contextmanager
def atomic() -> Iterator[None]:
    token = _in_atomic.set(True)
    try:
        with db.session.begin():
            yield
    except Exception:
        rollback()
        raise
    finally:
        _in_atomic.reset(token)


@contextmanager
def locked_atomic() -> Iterator[None]:
    """串行 + 短事务：出图 batch 多 greenlet 写分镜时用。"""
    lock = _get_db_write_lock()
    lock.acquire()
    try:
        with atomic():
            yield
    finally:
        lock.release()


def get_dbapi_connection() -> sqlite3.Connection:
    raw = db.engine.raw_connection()
    conn = raw.driver_connection
    if not isinstance(conn, sqlite3.Connection):
        raise TypeError("expected sqlite3 connection from engine")
    return conn
