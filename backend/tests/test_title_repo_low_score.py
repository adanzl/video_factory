import sqlite3

from app.repositories import repo_title


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE title (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            category TEXT,
            template TEXT,
            hook TEXT,
            score INTEGER,
            score_detail TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            job_id INTEGER,
            source TEXT DEFAULT 'manual',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        )
        """
    )
    return conn


def test_list_ids_below_score_excludes_enqueued_and_null():
    conn = _conn()
    conn.executemany(
        "INSERT INTO title (title, score, status) VALUES (?, ?, ?)",
        [
            ("低分", 60, "rejected"),
            ("边界", 75, "queued"),
            ("高分", 80, "queued"),
            ("未打分", None, "pending"),
            ("已入队低分", 50, "enqueued"),
        ],
    )
    ids = repo_title.list_ids_below_score(conn, 75)
    assert ids == [1]
