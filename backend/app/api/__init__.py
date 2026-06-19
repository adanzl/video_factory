from __future__ import annotations

from flask import Flask

from app.api.errors import register_error_handlers
from app.api.api_jobs import bp as jobs_bp


def register_api(app: Flask) -> None:
    register_error_handlers(app)
    app.register_blueprint(jobs_bp)
