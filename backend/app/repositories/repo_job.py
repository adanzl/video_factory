from __future__ import annotations

import json
import sqlite3
from typing import Any

from app.utils.stage_names import normalize_stage
from app.utils.final_asset import parse_final_asset


def _row_to_dict(row: sqlite3.Row) -> dict:
    data = dict(row)
    if data.get("script_json"):
        data["script_json"] = json.loads(data["script_json"])
    if data.get("quality_report"):
        data["quality_report"] = json.loads(data["quality_report"])
    if data.get("tts_usage_json"):
        data["tts_usage_json"] = json.loads(data["tts_usage_json"])
    if data.get("info"):
        data["info"] = json.loads(data["info"])
    if data.get("final_path"):
        data["final_path"] = parse_final_asset(data["final_path"])
    if data.get("stage"):
        data["stage"] = normalize_stage(data["stage"])
    data["skip_publish"] = bool(data.get("skip_publish"))
    return data


def _normalize_list_row(row: sqlite3.Row) -> dict:
    data = dict(row)
    if data.get("final_path"):
        data["final_path"] = parse_final_asset(data["final_path"])
    return data


def create_job(
    conn: sqlite3.Connection,
    title: str,
    *,
    skip_publish: bool = True,
    stage: str = "script",
    status: str = "pending",
    pipeline: str = "standard",
    material_id: int | None = None,
    script_json: dict | None = None,
    info: dict | None = None,
) -> dict:
    script_payload = None
    if script_json is not None:
        script_payload = json.dumps(script_json, ensure_ascii=False)
    info_payload = None
    if info is not None:
        info_payload = json.dumps(info, ensure_ascii=False)
    cur = conn.execute(
        """
        INSERT INTO video_job (
            title, stage, status, skip_publish, pipeline, material_id, script_json, info
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            title,
            stage,
            status,
            int(skip_publish),
            pipeline,
            material_id,
            script_payload,
            info_payload,
        ),
    )
    job_id = cur.lastrowid
    return get_job(conn, job_id)


def list_jobs(
    conn: sqlite3.Connection,
    *,
    condition: dict | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    limit = max(1, min(limit, 200))
    offset = max(0, offset)

    conditions: list[str] = []
    params: list = []
    if condition:
        for col, val in condition.items():
            conditions.append(f"{col} = ?")
            params.append(val)

    where_clause = ""
    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)

    rows = conn.execute(
        f"""
        SELECT id, title, stage, status, pipeline, final_path, updated_at, error_message
        FROM video_job
        {where_clause}
        ORDER BY id DESC
        LIMIT ? OFFSET ?
        """,
        (*params, limit, offset),
    ).fetchall()
    return [_normalize_list_row(row) for row in rows]


def count_jobs(
    conn: sqlite3.Connection,
    *,
    condition: dict | None = None,
) -> int:
    conditions: list[str] = []
    params: list = []
    if condition:
        for col, val in condition.items():
            conditions.append(f"{col} = ?")
            params.append(val)

    where_clause = ""
    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)

    row = conn.execute(
        f"SELECT COUNT(*) AS cnt FROM video_job {where_clause}",
        params,
    ).fetchone()
    return row["cnt"] if row else 0


def get_job(conn: sqlite3.Connection, job_id: int) -> dict:
    row = conn.execute(
        "SELECT * FROM video_job WHERE id = ?",
        (job_id,),
    ).fetchone()
    if row is None:
        raise KeyError(f"job {job_id} not found")
    return _row_to_dict(row)


def update_job(conn: sqlite3.Connection, job_id: int, **fields: Any) -> dict:
    allowed = {
        "title",
        "stage",
        "status",
        "fail_stage",
        "retry_count",
        "skip_publish",
        "pipeline",
        "material_id",
        "script_json",
        "quality_report",
        "final_path",
        "cover_path",
        "intro_path",
        "base_path",
        "end_path",
        "audio_path",
        "subtitle_path",
        "tts_usage_json",
        "info",
        "error_message",
        "audio_version",
    }
    parts: list[str] = ["updated_at = datetime('now')"]
    values: list[Any] = []
    for key, value in fields.items():
        if key not in allowed:
            continue
        if key in {"script_json", "quality_report", "tts_usage_json", "info"} and value is not None:
            value = json.dumps(value, ensure_ascii=False)
        if key == "final_path" and isinstance(value, dict):
            value = json.dumps(value, ensure_ascii=False)
        if key == "skip_publish":
            value = int(bool(value))
        parts.append(f"{key} = ?")
        values.append(value)
    values.append(job_id)
    conn.execute(
        f"UPDATE video_job SET {', '.join(parts)} WHERE id = ?",
        values,
    )
    return get_job(conn, job_id)


def delete_job(conn: sqlite3.Connection, job_id: int) -> None:
    cur = conn.execute("DELETE FROM video_job WHERE id = ?", (job_id,))
    if cur.rowcount == 0:
        raise KeyError(f"job {job_id} not found")


def claim_next_pending(conn: sqlite3.Connection) -> dict | None:
    """原子领取下一条 pending → running。

    单条 UPDATE（子查询选 id）+ ``RETURNING``，避免 SELECT 后再
    UPDATE 的竞态；无 RETURNING 时回退为条件 UPDATE 重试。
    """
    try:
        cur = conn.execute(
            """
            UPDATE video_job
            SET status = 'running', updated_at = datetime('now')
            WHERE id = (
                SELECT id FROM video_job
                WHERE status = 'pending'
                ORDER BY id
                LIMIT 1
            )
            AND status = 'pending'
            RETURNING id
            """
        )
        row = cur.fetchone()
        if row is None:
            return None
        return get_job(conn, int(row["id"]))
    except sqlite3.OperationalError:
        # 旧 SQLite 无 RETURNING：条件 UPDATE + 重试
        pass

    for _ in range(8):
        row = conn.execute(
            """
            SELECT id FROM video_job
            WHERE status = 'pending'
            ORDER BY id
            LIMIT 1
            """
        ).fetchone()
        if row is None:
            return None
        job_id = int(row["id"])
        cur = conn.execute(
            """
            UPDATE video_job
            SET status = 'running', updated_at = datetime('now')
            WHERE id = ? AND status = 'pending'
            """,
            (job_id,),
        )
        if cur.rowcount == 1:
            return get_job(conn, job_id)
    return None
