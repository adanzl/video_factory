from __future__ import annotations

import sqlite3


def delete_segments(conn: sqlite3.Connection, job_id: int) -> None:
    conn.execute("DELETE FROM video_segment WHERE job_id = ?", (job_id,))


def insert_segments(
    conn: sqlite3.Connection,
    job_id: int,
    segments: list[dict],
) -> None:
    delete_segments(conn, job_id)
    for seg in segments:
        conn.execute(
            """
            INSERT INTO video_segment (
                job_id, segment_index, text, image_prompt, motion_prompt, visual_mode, duration_sec, sd15_prompt_en, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending')
            """,
            (
                job_id,
                seg["segment_index"],
                seg["text"],
                seg.get("image_prompt"),
                seg.get("motion_prompt"),
                seg.get("visual_mode", "static_motion"),
                seg.get("duration_sec"),
                seg.get("sd15_prompt_en"),
            ),
        )


def list_segments(conn: sqlite3.Connection, job_id: int) -> list[dict]:
    rows = conn.execute(
        """
        SELECT id, segment_index, text, image_prompt, motion_prompt, visual_mode,
               image_path, clip_path, duration_sec, sd15_prompt_en, status
        FROM video_segment
        WHERE job_id = ?
        ORDER BY segment_index
        """,
        (job_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def update_segment(
    conn: sqlite3.Connection,
    segment_id: int,
    **fields: object,
) -> None:
    allowed = {
        "image_path",
        "clip_path",
        "duration_sec",
        "status",
        "image_prompt",
        "motion_prompt",
        "visual_mode",
        "sd15_prompt_en",
    }
    parts: list[str] = []
    values: list[object] = []
    for key, value in fields.items():
        if key not in allowed:
            continue
        parts.append(f"{key} = ?")
        values.append(value)
    if not parts:
        return
    values.append(segment_id)
    conn.execute(
        f"UPDATE video_segment SET {', '.join(parts)} WHERE id = ?",
        values,
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
