"""CLI 日志：控制台 + 文件。"""

from __future__ import annotations

import logging
import sys
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_DATE_FORMAT = "%H:%M:%S"
_CONFIGURED = False


def _formatter() -> logging.Formatter:
    return logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)


def _rotating_file_handler(log_file: Path, *, retention_days: int) -> TimedRotatingFileHandler:
    """按自然日切割；retention_days 含当天，共保留最近 N 天。"""
    handler = TimedRotatingFileHandler(
        log_file,
        when="midnight",
        interval=1,
        backupCount=max(0, retention_days - 1),
        encoding="utf-8",
    )
    handler.suffix = "%Y-%m-%d"
    handler.setFormatter(_formatter())
    return handler


def setup_logging(*, log_dir: Path, retention_days: int = 3) -> Path:
    """初始化根 logger：stderr + log_dir/worker.log（按天滚动）。"""
    global _CONFIGURED
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "worker.log"

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    logging.getLogger("websocket").setLevel(logging.WARNING)

    if _CONFIGURED:
        return log_file

    console = logging.StreamHandler(sys.stderr)
    console.setFormatter(_formatter())
    root.addHandler(console)

    file_handler = _rotating_file_handler(log_file, retention_days=retention_days)
    root.addHandler(file_handler)

    _CONFIGURED = True
    return log_file


def attach_job_log(media_dir: Path, job_id: int) -> Path:
    """追加 job 专属 run.log（与 worker.log 并行写入）。"""
    job_dir = media_dir / str(job_id)
    job_dir.mkdir(parents=True, exist_ok=True)
    log_file = job_dir / "run.log"

    root = logging.getLogger()
    for handler in root.handlers:
        if isinstance(handler, logging.FileHandler) and handler.baseFilename == str(log_file):
            return log_file

    handler = logging.FileHandler(log_file, encoding="utf-8", mode="a")
    handler.setFormatter(_formatter())
    root.addHandler(handler)
    return log_file
