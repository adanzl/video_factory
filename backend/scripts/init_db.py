from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.repositories.connection import connection
from app.repositories.schema import apply_schema


def main() -> None:
    with connection() as conn:
        apply_schema(conn)
    print("Database initialized.")


if __name__ == "__main__":
    main()
