from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING

from sqlalchemy import event
from sqlalchemy.engine import Engine

from app.config import get_settings
from app.repositories.db_obj import db

if TYPE_CHECKING:
    from flask import Flask

_app: Flask | None = None


def init_database(app: Flask) -> None:
    global _app
    _app = app
    settings = get_settings()
    settings.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    uri = f"sqlite:///{settings.sqlite_path.resolve()}"
    app.config["SQLALCHEMY_DATABASE_URI"] = uri
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "connect_args": {"check_same_thread": False},
    }
    db.init_app(app)

    @event.listens_for(Engine, "connect")
    def _sqlite_pragmas(dbapi_conn: object, _record: object) -> None:
        if not isinstance(dbapi_conn, sqlite3.Connection):
            return
        dbapi_conn.row_factory = sqlite3.Row
        dbapi_conn.execute("PRAGMA busy_timeout=30000")
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    @app.teardown_appcontext
    def _teardown_db(_exc: BaseException | None) -> None:
        db.session.remove()


def get_app() -> Flask:
    if _app is None:
        raise RuntimeError("database not initialized; call init_database(create_app()) first")
    return _app


def get_dbapi_connection() -> sqlite3.Connection:
    from app.repositories.sql_exec import get_dbapi_connection as _raw

    return _raw()
