"""Pytest：临时 SQLite + Flask app_context。"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from flask import Flask

from app.config import config


@pytest.fixture
def app_ctx(tmp_path) -> Iterator[Flask]:
    db_path = tmp_path / "test.db"
    config.sqlite_path = db_path
    from app.core import create_app
    from app.repositories.database import get_dbapi_connection
    from app.repositories.schema import apply_schema

    app = create_app()
    with app.app_context():
        conn = get_dbapi_connection()
        apply_schema(conn)
        conn.commit()
        yield app


@pytest.fixture
def noop_atomic(monkeypatch):
    from app.repositories import sql_exec as sql_exec_module

    original = sql_exec_module.atomic

    @contextmanager
    def _noop():
        yield

    monkeypatch.setattr(sql_exec_module, "atomic", _noop)
    monkeypatch.setattr(sql_exec_module, "commit", lambda: None)
    monkeypatch.setattr(sql_exec_module, "rollback", lambda: None)

    import sys

    for mod in sys.modules.values():
        if mod is not None and getattr(mod, "atomic", None) is original:
            monkeypatch.setattr(mod, "atomic", _noop, raising=False)
