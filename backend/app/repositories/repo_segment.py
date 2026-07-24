from __future__ import annotations

import json

from app.repositories import sql_exec as sql


def _serialize_info(value: object | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False) if value else None
    return None


def _parse_info(raw: object | None) -> dict | None:
    if raw is None:
        return None
    if isinstance(raw, dict):
        return dict(raw) if raw else None
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    if not text:
        return None
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None
    return dict(parsed) if isinstance(parsed, dict) and parsed else None


def delete_segments(job_id: int) -> None:
    sql.execute("DELETE FROM video_segment WHERE job_id = ?", (job_id,))
    sql.commit()


def insert_segments(
    job_id: int,
    segments: list[dict],
) -> None:
    existing_by_index = {
        int(row["segment_index"]): row for row in list_segments(job_id)
    }
    delete_segments(job_id)
    for seg in segments:
        index = int(seg["segment_index"])
        prev = existing_by_index.get(index)
        image_path = seg.get("image_path")
        if image_path is None and prev is not None:
            image_path = prev.get("image_path")
        clip_path = seg.get("clip_path")
        if clip_path is None and prev is not None:
            clip_path = prev.get("clip_path")
        duration_sec = seg.get("duration_sec")
        if prev is not None and prev.get("duration_sec") is not None:
            duration_sec = prev.get("duration_sec")
        status = seg.get("status")
        if not status and prev is not None:
            status = prev.get("status")
        if not status:
            status = "pending"
        version = int(prev["version"]) if prev is not None else 0
        if "info" in seg:
            info_raw = _serialize_info(seg.get("info"))
        elif prev is not None:
            info_raw = _serialize_info(prev.get("info"))
        else:
            info_raw = None
        sql.execute(
            """
            INSERT INTO video_segment (
                job_id, segment_index, text, image_prompt, motion_prompt, visual_mode,
                duration_sec, sd15_prompt_en, image_path, clip_path, status, dialogue,
                info, version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job_id,
                index,
                seg["text"],
                seg.get("image_prompt"),
                seg.get("motion_prompt"),
                seg.get("visual_mode", "static_motion"),
                duration_sec,
                seg.get("sd15_prompt_en"),
                image_path,
                clip_path,
                status,
                json.dumps(seg["dialogue"], ensure_ascii=False) if seg.get("dialogue") else None,
                info_raw,
                version,
            ),
        )
    sql.commit()


def list_segments(job_id: int) -> list[dict]:
    rows = sql.fetchall(
        """
        SELECT id, segment_index, text, image_prompt, motion_prompt, visual_mode,
               image_path, clip_path, duration_sec, sd15_prompt_en, status, dialogue,
               info, version
        FROM video_segment
        WHERE job_id = ?
        ORDER BY segment_index
        """,
        (job_id,),
    )
    sql.commit()
    result = []
    for row in rows:
        d = dict(row)
        raw = d.pop("dialogue", None)
        if raw:
            try:
                d["dialogue"] = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                d["dialogue"] = None
        info = _parse_info(d.pop("info", None))
        if info is not None:
            d["info"] = info
        result.append(d)
    return result


def get_segment_info(segment_id: int) -> str | None:
    row = sql.fetchone(
        "SELECT info FROM video_segment WHERE id = ?",
        (segment_id,),
    )
    sql.commit()
    return row["info"] if row else None


def update_segment(
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
        "info",
        "version",
    }
    parts: list[str] = []
    values: list[object] = []
    for key, value in fields.items():
        if key not in allowed:
            continue
        if key == "dialogue" and value is not None and not isinstance(value, str):
            value = json.dumps(value, ensure_ascii=False)
        if key == "info":
            value = _serialize_info(value)
        parts.append(f"{key} = ?")
        values.append(value)
    if not parts:
        return
    values.append(segment_id)
    sql.execute(
        f"UPDATE video_segment SET {', '.join(parts)} WHERE id = ?",
        values,
    )
    sql.commit()


def increase_version(segment_id: int) -> None:
    sql.execute(
        "UPDATE video_segment SET version = version + 1 WHERE id = ?",
        (segment_id,),
    )
    sql.commit()


def clear_segment_durations(job_id: int) -> None:
    sql.execute(
        "UPDATE video_segment SET duration_sec = NULL WHERE job_id = ?",
        (job_id,),
    )
    sql.commit()


def clear_segment_clips(
    job_id: int,
    segment_indices: list[int] | None = None,
) -> None:
    if segment_indices:
        placeholders = ",".join("?" for _ in segment_indices)
        sql.execute(
            f"""
            UPDATE video_segment
            SET clip_path = NULL
            WHERE job_id = ? AND segment_index IN ({placeholders})
            """,
            (job_id, *segment_indices),
        )
    else:
        sql.execute(
            "UPDATE video_segment SET clip_path = NULL WHERE job_id = ?",
            (job_id,),
        )
    sql.commit()


def clear_segment_clips_only(
    job_id: int,
    segment_indices: list[int],
) -> None:
    placeholders = ",".join("?" for _ in segment_indices)
    sql.execute(
        f"""
        UPDATE video_segment
        SET clip_path = NULL, status = 'pending'
        WHERE job_id = ? AND segment_index IN ({placeholders})
        """,
        (job_id, *segment_indices),
    )
    sql.commit()


def clear_segment_media(
    job_id: int,
    segment_indices: list[int] | None,
) -> None:
    if segment_indices:
        placeholders = ",".join("?" for _ in segment_indices)
        sql.execute(
            f"""
            UPDATE video_segment
            SET image_path = NULL, clip_path = NULL, status = 'pending'
            WHERE job_id = ? AND segment_index IN ({placeholders})
            """,
            (job_id, *segment_indices),
        )
    else:
        sql.execute(
            """
            UPDATE video_segment
            SET image_path = NULL, clip_path = NULL, status = 'pending'
            WHERE job_id = ?
            """,
            (job_id,),
        )
    sql.commit()
