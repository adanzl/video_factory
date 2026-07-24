"""初始化 SQLite schema（新环境跑一次）。

用法:
  cd backend
  python -m scripts.db_init
"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core import create_app
from app.repositories.database import get_dbapi_connection
from app.repositories.schema import apply_schema


def main() -> None:
    app = create_app()
    with app.app_context():
        conn = get_dbapi_connection()
        try:
            apply_schema(conn)
            conn.commit()
        finally:
            conn.close()
    print("Database initialized.")


if __name__ == "__main__":
    main()
