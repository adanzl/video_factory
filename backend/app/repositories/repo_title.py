from __future__ import annotations

import json
from typing import Any

from app.repositories import sql_exec as sql


def _row_to_dict(row: dict) -> dict:
    data = dict(row)
    if data.get("score_detail"):
        data["score_detail"] = json.loads(data["score_detail"])
    return data


def count_titles(
    *,
    status: str | None = None,
) -> int:
    if status:
        row = sql.fetchone(
            "SELECT COUNT(*) AS cnt FROM title WHERE status = ?",
            (status,),
        )
    else:
        row = sql.fetchone(
            "SELECT COUNT(*) AS cnt FROM title",
        )
    sql.commit()
    return row["cnt"] if row else 0


def list_titles(
    *,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    if status:
        rows = sql.fetchall(
            """
            SELECT id, title, category, template, hook, score, score_detail,
                   status, job_id, source, keyword, created_at, updated_at
            FROM title
            WHERE status = ?
            ORDER BY id DESC
            LIMIT ? OFFSET ?
            """,
            (status, limit, offset),
        )
    else:
        rows = sql.fetchall(
            """
            SELECT id, title, category, template, hook, score, score_detail,
                   status, job_id, source, keyword, created_at, updated_at
            FROM title
            ORDER BY id DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        )
    sql.commit()
    return [_row_to_dict(row) for row in rows]


def get_title(title_id: int) -> dict:
    row = sql.fetchone("SELECT * FROM title WHERE id = ?", (title_id,))
    sql.commit()
    if row is None:
        raise KeyError(f"title {title_id} not found")
    return _row_to_dict(row)


def find_by_titles(titles: list[str]) -> set[str]:
    if not titles:
        return set()
    placeholders = ",".join("?" for _ in titles)
    rows = sql.fetchall(
        f"SELECT title FROM title WHERE title IN ({placeholders})",
        titles,
    )
    sql.commit()
    return {row["title"] for row in rows}


def list_all_keywords() -> list[str]:
    rows = sql.fetchall("SELECT keyword FROM title WHERE keyword IS NOT NULL")
    sql.commit()
    return [str(row["keyword"]) for row in rows if row.get("keyword")]


def insert_title(
    *,
    title: str,
    category: str | None = None,
    template: str | None = None,
    hook: str | None = None,
    source: str = "manual",
    keyword: str | None = None,
) -> dict | None:
    cur = sql.execute(
        """
        INSERT OR IGNORE INTO title (title, category, template, hook, source, keyword)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (title, category, template, hook, source, keyword),
    )
    if cur.rowcount == 0:
        sql.commit()
        return None
    title_id = int(cur.lastrowid)
    sql.commit()
    return get_title(title_id)


def update_title(title_id: int, **fields: Any) -> dict:
    allowed = {
        "title",
        "category",
        "template",
        "hook",
        "score",
        "score_detail",
        "status",
        "job_id",
        "source",
        "keyword",
    }
    parts: list[str] = ["updated_at = datetime('now')"]
    values: list[Any] = []
    for key, value in fields.items():
        if key not in allowed:
            continue
        if key == "score_detail" and value is not None:
            value = json.dumps(value, ensure_ascii=False)
        parts.append(f"{key} = ?")
        values.append(value)
    values.append(title_id)
    sql.execute(
        f"UPDATE title SET {', '.join(parts)} WHERE id = ?",
        values,
    )
    sql.commit()
    return get_title(title_id)


def delete_titles(title_ids: list[int]) -> int:
    if not title_ids:
        return 0
    placeholders = ",".join("?" for _ in title_ids)
    cur = sql.execute(
        f"DELETE FROM title WHERE id IN ({placeholders})",
        title_ids,
    )
    sql.commit()
    return cur.rowcount


def list_by_ids(title_ids: list[int]) -> list[dict]:
    if not title_ids:
        return []
    placeholders = ",".join("?" for _ in title_ids)
    rows = sql.fetchall(
        f"SELECT * FROM title WHERE id IN ({placeholders})",
        title_ids,
    )
    sql.commit()
    return [_row_to_dict(row) for row in rows]


def list_pending_score(*, limit: int = 200) -> list[dict]:
    rows = sql.fetchall(
        """
        SELECT * FROM title
        WHERE status = 'pending' OR score IS NULL
        ORDER BY id
        LIMIT ?
        """,
        (max(1, min(limit, 500)),),
    )
    sql.commit()
    return [_row_to_dict(row) for row in rows]


def list_ids_below_score(
    max_score: int,
    *,
    exclude_enqueued: bool = True,
) -> list[int]:
    if exclude_enqueued:
        rows = sql.fetchall(
            """
            SELECT id FROM title
            WHERE score IS NOT NULL AND score < ? AND status != 'enqueued'
            ORDER BY id
            """,
            (max_score,),
        )
    else:
        rows = sql.fetchall(
            """
            SELECT id FROM title
            WHERE score IS NOT NULL AND score < ?
            ORDER BY id
            """,
            (max_score,),
        )
    sql.commit()
    return [row["id"] for row in rows]


def list_queued(*, limit: int = 200) -> list[dict]:
    rows = sql.fetchall(
        """
        SELECT * FROM title
        WHERE status = 'queued'
        ORDER BY score DESC, id
        LIMIT ?
        """,
        (max(1, min(limit, 500)),),
    )
    sql.commit()
    return [_row_to_dict(row) for row in rows]
