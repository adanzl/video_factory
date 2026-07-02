"""选题库 title 表初始化（已有数据库单独执行）。

用法:
    cd backend
    python -m scripts.migrate_title
"""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import get_settings
from app.repositories.connection import connection
from app.repositories.schema import apply_title_schema


def main() -> None:
    settings = get_settings()
    with connection() as conn:
        apply_title_schema(conn)
    print(f"title table ready: {settings.sqlite_path}")


if __name__ == "__main__":
    main()
