from __future__ import annotations

import sqlite3

_TITLE_DDL = """
CREATE TABLE IF NOT EXISTS title (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL UNIQUE,
    category TEXT,
    template TEXT,
    hook TEXT,
    score INTEGER,
    score_detail TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    job_id INTEGER,
    source TEXT NOT NULL DEFAULT 'manual',
    keyword TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (job_id) REFERENCES video_job(id)
);

CREATE INDEX IF NOT EXISTS idx_title_status ON title(status);
"""

_MATERIAL_VIDEO_DDL = """
CREATE TABLE IF NOT EXISTS material_video (
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

CREATE INDEX IF NOT EXISTS idx_material_video_status ON material_video(status);
"""

_MATERIAL_AUDIO_DDL = """
CREATE TABLE IF NOT EXISTS material_audio (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    file_path TEXT NOT NULL,
    duration_sec REAL,
    size_bytes INTEGER,
    note TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_material_audio_status ON material_audio(status);
"""


def _rename_table_if_exists(conn: sqlite3.Connection, old: str, new: str) -> None:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (old,)
    ).fetchone()
    if row is not None:
        conn.execute(f"ALTER TABLE {old} RENAME TO {new}")


def apply_material_video_schema(conn: sqlite3.Connection) -> None:
    """创建视频素材库表，并为 video_job 增加 pipeline / material_id（幂等）。"""
    _rename_table_if_exists(conn, "video_material", "material_video")
    conn.executescript(_MATERIAL_VIDEO_DDL)
    _ensure_column(conn, "video_job", "pipeline", "TEXT NOT NULL DEFAULT 'standard'")
    _ensure_column(conn, "video_job", "material_id", "INTEGER")
    _ensure_column(conn, "material_video", "job_id", "INTEGER")
    _ensure_column(conn, "video_job", "base_path", "TEXT")
    _ensure_column(conn, "video_job", "end_path", "TEXT")
    _ensure_journal_mode_delete(conn)


def apply_material_audio_schema(conn: sqlite3.Connection) -> None:
    """创建音频素材表（幂等）。"""
    _rename_table_if_exists(conn, "audio_material", "material_audio")
    conn.executescript(_MATERIAL_AUDIO_DDL)
    _ensure_journal_mode_delete(conn)


def _ensure_journal_mode_delete(conn: sqlite3.Connection) -> None:
    row = conn.execute("PRAGMA journal_mode").fetchone()
    if row and str(row[0]).upper() == "DELETE":
        return
    conn.execute("PRAGMA journal_mode=DELETE")


def apply_title_schema(conn: sqlite3.Connection) -> None:
    """创建选题库 title 表（幂等，可单独对已有库执行）。"""
    conn.executescript(_TITLE_DDL)
    _ensure_column(conn, "title", "keyword", "TEXT")

def apply_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(_MATERIAL_VIDEO_DDL)
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
            version INTEGER NOT NULL DEFAULT 0,
            skip_publish INTEGER NOT NULL DEFAULT 1,
            publish INTEGER NOT NULL DEFAULT 0,
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
    apply_material_video_schema(conn)
    apply_material_audio_schema(conn)
    apply_daily_story_schema(conn)
    apply_gold_story_schema(conn)
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
    _ensure_column(conn, "video_segment", "dialogue", "TEXT")
    _ensure_column(conn, "video_segment", "info", "TEXT")
    _ensure_column(conn, "video_segment", "version", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(conn, "video_job", "audio_version", "INTEGER NOT NULL DEFAULT 0")
    _rename_column_if_exists(conn, "video_job", "retry_count", "version")
    _ensure_column(conn, "video_job", "version", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(conn, "video_job", "publish", "INTEGER NOT NULL DEFAULT 0")


def _rename_column_if_exists(
    conn: sqlite3.Connection,
    table: str,
    old: str,
    new: str,
) -> None:
    columns = {
        row[1] for row in conn.execute(f"PRAGMA table_info({table})")
    }
    if old in columns and new not in columns:
        conn.execute(f"ALTER TABLE {table} RENAME COLUMN {old} TO {new}")


_DAILY_STORY_DDL = """
CREATE TABLE IF NOT EXISTS daily_story (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    theme TEXT NOT NULL,
    story_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_daily_story_status ON daily_story(status);
"""


def extract_story_type_from_punchline(punchline: str | None) -> str | None:
    """从笑点解析提取 A–G（与 story_types 逻辑对齐，供迁移回填，避免循环依赖）。"""
    import re

    t = (punchline or "").strip()
    if not t:
        return None
    code_class = "[ABCDEG]"
    m = re.search(rf"矛盾类型\s*({code_class})", t, re.IGNORECASE)
    if m:
        return m.group(1).upper()
    m = re.match(rf"^({code_class})\s*类?\s*([^，,。：:]+)", t)
    if m:
        return m.group(1).upper()
    m = re.match(rf"^({code_class})\s+\S+", t)
    if m:
        return m.group(1).upper()
    for k in ("A", "B", "C", "D", "E", "G"):
        if f"{k}类" in t or f"{k}：" in t:
            return k
    return None


def _backfill_daily_story_type(conn: sqlite3.Connection) -> None:
    import json

    rows = conn.execute(
        """
        SELECT id, story_json
        FROM daily_story
        WHERE story_type IS NULL OR TRIM(story_type) = ''
        """,
    ).fetchall()
    for row in rows:
        story_id = int(row[0])
        raw = row[1] or ""
        try:
            story = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            continue
        if not isinstance(story, dict):
            continue
        code = extract_story_type_from_punchline(
            str(story.get("punchline_explain") or ""),
        )
        if not code:
            continue
        conn.execute(
            "UPDATE daily_story SET story_type = ? WHERE id = ?",
            (code, story_id),
        )


def apply_daily_story_schema(conn: sqlite3.Connection) -> None:
    """创建日常故事表（幂等）。"""
    conn.executescript(_DAILY_STORY_DDL)
    _ensure_column(conn, "daily_story", "job_id", "INTEGER")
    _ensure_column(conn, "daily_story", "story_type", "TEXT")
    _ensure_column(conn, "daily_story", "key", "TEXT")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_daily_story_job ON daily_story(job_id)"
    )
    _backfill_daily_story_type(conn)
    _backfill_daily_story_key(conn)
    _ensure_journal_mode_delete(conn)


def _backfill_daily_story_key(conn: sqlite3.Connection) -> None:
    """旧行：若列空且 story_json 有 key，回填到列。"""
    import json

    rows = conn.execute(
        """
        SELECT id, story_json
        FROM daily_story
        WHERE key IS NULL OR TRIM(key) = ''
        """,
    ).fetchall()
    for row in rows:
        story_id = int(row[0])
        raw = row[1] or ""
        try:
            story = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            continue
        if not isinstance(story, dict):
            continue
        k = str(story.get("key") or "").strip()
        if not k:
            continue
        conn.execute(
            "UPDATE daily_story SET key = ? WHERE id = ?",
            (k, story_id),
        )


_GOLD_STORY_DDL = """
CREATE TABLE IF NOT EXISTS gold_story (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    source_id TEXT NOT NULL,
    url TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    mechanism TEXT NOT NULL,
    structure_type TEXT NOT NULL,
    theme_family TEXT,
    title TEXT,
    conflict_core TEXT,
    auto_score REAL NOT NULL,
    engagement_score REAL,
    content_hash TEXT NOT NULL,
    times_used INTEGER NOT NULL DEFAULT 0,
    avg_humor_delta REAL,
    copy_hits INTEGER NOT NULL DEFAULT 0,
    transcript_backend TEXT,
    transcript_path TEXT,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    last_used_at TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_gold_story_source
    ON gold_story(source, source_id);
CREATE INDEX IF NOT EXISTS idx_gold_story_pick
    ON gold_story(status, structure_type, mechanism);
CREATE INDEX IF NOT EXISTS idx_gold_story_score
    ON gold_story(status, auto_score DESC);

CREATE TABLE IF NOT EXISTS gold_story_inject_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    gold_story_id INTEGER NOT NULL,
    daily_story_id INTEGER,
    job_id INTEGER,
    theme TEXT,
    story_type TEXT,
    humor_score INTEGER,
    baseline_humor INTEGER,
    humor_delta REAL,
    copy_hit INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (gold_story_id) REFERENCES gold_story(id)
);

CREATE INDEX IF NOT EXISTS idx_gs_inject_story
    ON gold_story_inject_log(gold_story_id, created_at);
"""


def apply_gold_story_schema(conn: sqlite3.Connection) -> None:
    """金故事库表（幂等）。"""
    conn.executescript(_GOLD_STORY_DDL)
    _ensure_journal_mode_delete(conn)


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
