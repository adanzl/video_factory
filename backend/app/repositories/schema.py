from __future__ import annotations

import sqlite3


def apply_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS video_job (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            stage TEXT NOT NULL DEFAULT 'title',
            status TEXT NOT NULL DEFAULT 'pending',
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
