from __future__ import annotations
import time
from flask import Flask, jsonify, request
from flask_cors import CORS
from app.api import register_api
from app.config import config
from app.core.log_config import setup_server_logging
from app.repositories.database import get_app, get_dbapi_connection, init_database
from worker.recovery import recover_stuck_daily_stories, recover_stuck_jobs
app_logger, gevent_access_logger = setup_server_logging(log_dir=config.log_dir, is_production=config.is_production)
log = app_logger

def _recover_stuck_jobs() -> None:
    try:
        count = recover_stuck_jobs()
        if count:
            log.warning('startup recovery: %d job(s) were stuck and have been reset to pending', count)
    except Exception:
        log.exception('startup recovery failed, jobs may still be stuck')

def _recover_stuck_daily_stories() -> None:
    try:
        count = recover_stuck_daily_stories()
        if count:
            log.warning('startup recovery: %d daily story/stories were stuck and have been re-queued', count)
    except Exception:
        log.exception('startup recovery failed, daily stories may still be stuck')

def create_app() -> Flask:
    app = Flask(__name__)
    init_database(app)
    if config.mock_mode:
        log.warning('[CONFIG] MOCK_MODE=true：将使用假文案/假图/假音，勿用于生产成片')
    else:
        missing = config.missing_provider_keys()
        if missing:
            log.error('[CONFIG] MOCK_MODE=false 但缺少 Key：%s（相关调用将失败，不会静默 mock）', '；'.join(missing))
    cors_origins = config.get_cors_origins()
    if cors_origins == ['*']:
        log.warning("[CORS] CORS_ORIGINS 设置为 '*'；前端 withCredentials 将无法与 '*' 同时使用，建议配置具体 origins（如：http://localhost:5174）")
        CORS(app, supports_credentials=False, resources={'/*': {'origins': '*'}})
    else:
        log.info('[CORS] 配置允许的 origins: %s，启用 credentials 支持', cors_origins)
        CORS(app, supports_credentials=True, resources={'/*': {'origins': cors_origins}})

    @app.before_request
    def _record_options_start_time():
        if request.method == 'OPTIONS':
            request._start_time = time.time()

    @app.route('/')
    def main_page():
        return '<p>Video Factory API</p>'

    @app.route('/health', methods=['GET', 'OPTIONS'])
    def health():
        if request.method == 'OPTIONS':
            return ('', 204)
        return jsonify({'status': 'ok'})
    register_api(app)
    with app.app_context():
        _recover_stuck_jobs()
        _recover_stuck_daily_stories()
    return app
__all__ = ['app_logger', 'create_app', 'gevent_access_logger', 'get_app', 'log']
