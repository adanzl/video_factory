"""视频素材库 + 素材流水线字段迁移（已有数据库单独执行）。

用法:
    cd backend
    python -m scripts.migrate_material

注意:
    执行前请先停止 API / worker，避免 database is locked。

变更:
    - 新建 video_material 表
    - video_job 增加 pipeline、material_id 列
    - video_material 增加 job_id 列
    - journal_mode 从 WAL 切回 DELETE（若当前为 WAL）
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import get_settings
from app.repositories.connection import connection
from app.repositories.schema import apply_material_schema

_LOCK_HINT = (
    "database is locked：请先停止正在访问数据库的进程（Flask API、worker 等），"
    "再重新执行 migrate_material。"
)


def main() -> None:
    settings = get_settings()
    try:
        with connection() as conn:
            apply_material_schema(conn)
    except sqlite3.OperationalError as exc:
        if "locked" in str(exc).lower():
            raise SystemExit(_LOCK_HINT) from exc
        raise
    print(f"material schema ready: {settings.sqlite_path}")


if __name__ == "__main__":
    main()
