from __future__ import annotations

import sqlite3

_TITLE_DDL = """
CREATE TABLE IF NOT EXISTS title (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL UNIQUE,
    track TEXT,
    template TEXT,
    hook TEXT,
    score INTEGER,
    score_detail TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    job_id INTEGER,
    source TEXT NOT NULL DEFAULT 'manual',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (job_id) REFERENCES video_job(id)
);

CREATE INDEX IF NOT EXISTS idx_title_status ON title(status);
"""


_MATERIAL_DDL = """
CREATE TABLE IF NOT EXISTS video_material (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    file_path TEXT NOT NULL,
    duration_sec REAL,
    width INTEGER,
    height INTEGER,
    size_bytes INTEGER,
    thumbnail_path TEXT,
    note TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_video_material_status ON video_material(status);
"""


def apply_material_schema(conn: sqlite3.Connection) -> None:
    """创建视频素材库表，并为 video_job 增加 pipeline / material_id（幂等）。"""
    conn.executescript(_MATERIAL_DDL)
    _ensure_column(conn, "video_job", "pipeline", "TEXT NOT NULL DEFAULT 'standard'")
    _ensure_column(conn, "video_job", "material_id", "INTEGER")
    _ensure_column(conn, "video_material", "job_id", "INTEGER")
    _ensure_column(conn, "video_job", "base_path", "TEXT")
    _ensure_journal_mode_delete(conn)


def _ensure_journal_mode_delete(conn: sqlite3.Connection) -> None:
    row = conn.execute("PRAGMA journal_mode").fetchone()
    if row and str(row[0]).upper() == "DELETE":
        return
    conn.execute("PRAGMA journal_mode=DELETE")


def apply_title_schema(conn: sqlite3.Connection) -> None:
    """创建选题库 title 表（幂等，可单独对已有库执行）。"""
    conn.executescript(_TITLE_DDL)


def apply_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(_MATERIAL_DDL)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS video_job (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            stage TEXT NOT NULL DEFAULT 'title',
            status TEXT NOT NULL DEFAULT 'pending',
            pipeline TEXT NOT NULL DEFAULT 'standard',
            material_id INTEGER,
            fail_stage TEXT,
            retry_count INTEGER NOT NULL DEFAULT 0,
            skip_publish INTEGER NOT NULL DEFAULT 1,
            script_json TEXT,
            quality_report TEXT,
            final_path TEXT,
            cover_path TEXT,
            intro_path TEXT,
            audio_path TEXT,
            subtitle_path TEXT,
            tts_usage_json TEXT,
            error_message TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS video_segment (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER NOT NULL,
            segment_index INTEGER NOT NULL,
            text TEXT NOT NULL,
            image_prompt TEXT,
            visual_mode TEXT NOT NULL DEFAULT 'static_motion',
            image_path TEXT,
            clip_path TEXT,
            duration_sec REAL,
            status TEXT NOT NULL DEFAULT 'pending',
            FOREIGN KEY (job_id) REFERENCES video_job(id) ON DELETE CASCADE,
            UNIQUE(job_id, segment_index)
        );

        CREATE TABLE IF NOT EXISTS job_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER NOT NULL,
            stage TEXT NOT NULL,
            level TEXT NOT NULL DEFAULT 'info',
            message TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (job_id) REFERENCES video_job(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_video_job_status ON video_job(status);
        CREATE INDEX IF NOT EXISTS idx_video_segment_job ON video_segment(job_id);
        CREATE INDEX IF NOT EXISTS idx_job_log_job ON job_log(job_id);
        """
    )
    apply_title_schema(conn)
    apply_material_schema(conn)
    conn.execute(
        "UPDATE video_job SET stage = 'segment' WHERE stage = 'ffmpeg'"
    )
    conn.execute(
        "UPDATE video_job SET fail_stage = 'segment' WHERE fail_stage = 'ffmpeg'"
    )
    conn.execute(
        "UPDATE video_job SET stage = 'segment' WHERE stage = 'image'"
    )
    conn.execute(
        "UPDATE video_job SET fail_stage = 'segment' WHERE fail_stage = 'image'"
    )
    conn.execute(
        "UPDATE video_job SET stage = 'segment' WHERE stage = 'quality'"
    )
    _ensure_column(conn, "video_job", "tts_usage_json", "TEXT")
    _ensure_column(conn, "video_job", "info", "TEXT")
    _ensure_column(conn, "video_segment", "motion_prompt", "TEXT")
    _ensure_column(conn, "video_segment", "sd15_prompt_en", "TEXT")


def _ensure_column(
    conn: sqlite3.Connection,
    table: str,
    column: str,
    ddl: str,
) -> None:
    columns = {
        row[1] for row in conn.execute(f"PRAGMA table_info({table})")
    }
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
