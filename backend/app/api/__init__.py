from __future__ import annotations

from flask import Flask


def register_api(app: Flask) -> None:
    from app.api.errors import register_error_handlers
    from app.api.api_jobs import bp as jobs_bp
    from app.api.api_clips import bp as clips_bp
    from app.api.api_materials import bp as materials_bp
    from app.api.api_media import bp as media_bp
    from app.api.api_topic import bp as topic_bp

    register_error_handlers(app)
    app.register_blueprint(jobs_bp)
    app.register_blueprint(clips_bp)
    app.register_blueprint(materials_bp)
    app.register_blueprint(media_bp)
    app.register_blueprint(topic_bp)
