from __future__ import annotations

import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv

load_dotenv(BACKEND_DIR.parent / ".env")

# 规范运行目录：统一切换到 backend 根目录，使相对路径解析一致
os.chdir(BACKEND_DIR)

from gevent import monkey

# 不 patch thread，使用真正的操作系统线程，避免与 asyncio 事件循环冲突
# subprocess=True 保留子进程能力；queue=False 避免与标准库队列行为冲突
monkey.patch_all(subprocess=True, thread=False, queue=False)

from flask import Flask, jsonify, make_response, request

from app.api import register_api
from app.config import config
from app.core.log_config import setup_server_logging

app_logger, gevent_access_logger = setup_server_logging(
    log_dir=config.log_dir,
    is_production=config.is_production,
)
log = app_logger

IS_PRODUCTION = config.is_production


def create_app() -> Flask:
    app = Flask(__name__)

    @app.after_request
    def add_cors_headers(response):
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
        return response

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


app = create_app()


def null_application(environ, start_response):
    if environ.get("PATH_INFO") == "/health":
        start_response("200 OK", [("Content-Type", "application/json")])
        yield b'{"status":"ok"}'
        return
    start_response("404 NOT FOUND", [("Content-Type", "text/plain")])
    yield b"NOT FOUND"


if __name__ == "__main__":
    PORT = config.port
    HOST = config.host

    # 只在开发环境禁用浏览器缓存
    if not IS_PRODUCTION:

        @app.after_request
        def disable_cache(resp):
            resp = make_response(resp)
            resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            resp.headers["Pragma"] = "no-cache"
            resp.headers["Expires"] = "0"
            return resp

    try:
        from gevent.pywsgi import WSGIServer
        from geventwebsocket.handler import WebSocketHandler
        from werkzeug.middleware.dispatcher import DispatcherMiddleware
        from werkzeug.middleware.shared_data import SharedDataMiddleware

        static_dir = BACKEND_DIR / "static"
        if static_dir.is_dir():
            static_app = SharedDataMiddleware(null_application, {"/": str(static_dir)})
            application = DispatcherMiddleware(app, {"/video_factory/web": static_app})
        else:
            application = app

        http_server = WSGIServer(
            (HOST, PORT),
            application,
            log=gevent_access_logger,
            error_log=log,
            handler_class=WebSocketHandler,
        )
        env_info = "production" if IS_PRODUCTION else "development"
        log.info("Server started on http://%s:%s (using gevent, env=%s)", HOST, PORT, env_info)
        http_server.serve_forever()
    except ImportError as exc:
        log.error("Gevent 相关模块导入失败: %s", exc)
        log.error("请运行: pip install gevent gevent-websocket")
        log.info("尝试使用 Flask 开发服务器...")
        app.run(host=HOST, port=PORT, debug=not IS_PRODUCTION)
    except Exception as exc:
        log.error("启动服务器失败: %s", exc)
        log.info("尝试使用 Flask 开发服务器...")
        app.run(host=HOST, port=PORT, debug=not IS_PRODUCTION)
