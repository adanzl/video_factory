from __future__ import annotations

from flask import Flask

from app.api.errors import register_error_handlers
from app.api.api_jobs import bp as jobs_bp
from app.api.api_media import bp as media_bp
from app.api.api_topic import bp as topic_bp


def register_api(app: Flask) -> None:
    register_error_handlers(app)
    app.register_blueprint(jobs_bp)
    app.register_blueprint(media_bp)
    app.register_blueprint(topic_bp)
