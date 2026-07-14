from __future__ import annotations

import json
import sqlite3


def delete_segments(conn: sqlite3.Connection, job_id: int) -> None:
    conn.execute("DELETE FROM video_segment WHERE job_id = ?", (job_id,))



def insert_segments(
    conn: sqlite3.Connection,
    job_id: int,
    segments: list[dict],
) -> None:
    existing_by_index = {
        int(row["segment_index"]): row for row in list_segments(conn, job_id)
    }
    delete_segments(conn, job_id)
    for seg in segments:
        index = int(seg["segment_index"])
        prev = existing_by_index.get(index)
        image_path = seg.get("image_path")
        if image_path is None and prev is not None:
            image_path = prev.get("image_path")
        clip_path = seg.get("clip_path")
        if clip_path is None and prev is not None:
            clip_path = prev.get("clip_path")
        status = seg.get("status")
        if not status and prev is not None:
            status = prev.get("status")
        if not status:
            status = "pending"
        version = 0
        conn.execute(
            """
            INSERT INTO video_segment (
                job_id, segment_index, text, image_prompt, motion_prompt, visual_mode,
                duration_sec, sd15_prompt_en, image_path, clip_path, status, dialogue, version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job_id,
                index,
                seg["text"],
                seg.get("image_prompt"),
                seg.get("motion_prompt"),
                seg.get("visual_mode", "static_motion"),
                seg.get("duration_sec"),
                seg.get("sd15_prompt_en"),
                image_path,
                clip_path,
                status,
                json.dumps(seg["dialogue"], ensure_ascii=False) if seg.get("dialogue") else None,
                version,
            ),
        )


def list_segments(conn: sqlite3.Connection, job_id: int) -> list[dict]:
    rows = conn.execute(
        """
        SELECT id, segment_index, text, image_prompt, motion_prompt, visual_mode,
               image_path, clip_path, duration_sec, sd15_prompt_en, status, dialogue, version
        FROM video_segment
        WHERE job_id = ?
        ORDER BY segment_index
        """,
        (job_id,),
    ).fetchall()
    result = []
    for row in rows:
        d = dict(row)
        raw = d.pop("dialogue", None)
        if raw:
            try:
                d["dialogue"] = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                d["dialogue"] = None
        result.append(d)
    return result


def update_segment(
    conn: sqlite3.Connection,
    segment_id: int,
    **fields: object,
) -> None:
    allowed = {
        "text",
        "image_path",
        "clip_path",
        "duration_sec",
        "status",
        "image_prompt",
        "motion_prompt",
        "visual_mode",
        "sd15_prompt_en",
        "dialogue",
        "version",
    }
    parts: list[str] = []
    values: list[object] = []
    for key, value in fields.items():
        if key not in allowed:
            continue
        if key == "dialogue" and value is not None and not isinstance(value, str):
            value = json.dumps(value, ensure_ascii=False)
        parts.append(f"{key} = ?")
        values.append(value)
    if not parts:
        return
    values.append(segment_id)
    conn.execute(
        f"UPDATE video_segment SET {', '.join(parts)} WHERE id = ?",
        values,
    )


def increase_version(
    conn: sqlite3.Connection,
    segment_id: int,
) -> None:
    conn.execute(
        "UPDATE video_segment SET version = version + 1 WHERE id = ?",
        (segment_id,),
    )


def clear_segment_durations(conn: sqlite3.Connection, job_id: int) -> None:
    conn.execute(
        "UPDATE video_segment SET duration_sec = NULL WHERE job_id = ?",
        (job_id,),
    )


def clear_segment_clips(
    conn: sqlite3.Connection,
    job_id: int,
    segment_indices: list[int] | None = None,
) -> None:
    if segment_indices:
        placeholders = ",".join("?" for _ in segment_indices)
        conn.execute(
            f"""
            UPDATE video_segment
            SET clip_path = NULL
            WHERE job_id = ? AND segment_index IN ({placeholders})
            """,
            (job_id, *segment_indices),
        )
        return
    conn.execute(
        "UPDATE video_segment SET clip_path = NULL WHERE job_id = ?",
        (job_id,),
    )


def clear_segment_clips_only(
    conn: sqlite3.Connection,
    job_id: int,
    segment_indices: list[int],
) -> None:
    placeholders = ",".join("?" for _ in segment_indices)
    conn.execute(
        f"""
        UPDATE video_segment
        SET clip_path = NULL, status = 'pending'
        WHERE job_id = ? AND segment_index IN ({placeholders})
        """,
        (job_id, *segment_indices),
    )


def clear_segment_media(
    conn: sqlite3.Connection,
    job_id: int,
    segment_indices: list[int] | None,
) -> None:
    if segment_indices:
        placeholders = ",".join("?" for _ in segment_indices)
        conn.execute(
            f"""
            UPDATE video_segment
            SET image_path = NULL, clip_path = NULL, status = 'pending'
            WHERE job_id = ? AND segment_index IN ({placeholders})
            """,
            (job_id, *segment_indices),
        )
        return
    conn.execute(
        """
        UPDATE video_segment
        SET image_path = NULL, clip_path = NULL, status = 'pending'
        WHERE job_id = ?
        """,
        (job_id,),
    )
