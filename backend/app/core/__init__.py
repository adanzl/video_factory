from __future__ import annotations

import time

from flask import Flask, jsonify, request
from flask_cors import CORS

from app.api import register_api
from app.config import config
from app.core.log_config import setup_server_logging

app_logger, gevent_access_logger = setup_server_logging(
    log_dir=config.log_dir,
    is_production=config.is_production,
)
log = app_logger


def create_app() -> Flask:
    app = Flask(__name__)

    cors_origins = config.get_cors_origins()
    if cors_origins == ["*"]:
        log.warning(
            "[CORS] CORS_ORIGINS 设置为 '*'；前端 withCredentials 将无法与 '*' 同时使用，"
            "建议配置具体 origins（如：http://localhost:5174）"
        )
        CORS(app, supports_credentials=False, resources={r"/*": {"origins": "*"}})
    else:
        log.info("[CORS] 配置允许的 origins: %s，启用 credentials 支持", cors_origins)
        CORS(app, supports_credentials=True, resources={r"/*": {"origins": cors_origins}})

    @app.before_request
    def _record_options_start_time():
        if request.method == "OPTIONS":
            request._start_time = time.time()

    @app.route("/")
    def main_page():
        return "<p>Video Factory API</p>"

    @app.route("/health", methods=["GET", "OPTIONS"])
    def health():
        if request.method == "OPTIONS":
            return "", 204
        return jsonify({"status": "ok"})

    register_api(app)
    return app
