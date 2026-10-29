"""首页总览：库内计数，不打外部签到和机器采样。"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone

from app.repositories import sql_exec as sql
from app.services.home.overview import (
    _fmt_bytes,
    _parse_size_token,
    build_overview,
    project_share_percent,
)


def test_fmt_bytes_and_swap_token():
    assert _fmt_bytes(2 * 1024 ** 3) == "2.0 GiB"
    assert _fmt_bytes(812 * 1024 ** 3) == "812 GiB"
    assert _fmt_bytes(int(1.8 * 1024 ** 4)) == "1.8 TiB"
    assert _parse_size_token("2048.00M") == 2048 * 1024 ** 2


def test_project_share_percent():
    assert project_share_percent(100, 40) == 40
    assert project_share_percent(10, 0) == 0
    assert project_share_percent(0, 10) == 0


def test_overview_counts(app_ctx, monkeypatch):
    import app.services.home.overview as overview

    monkeypatch.setattr(
        overview,
        "machine_meters",
        lambda: [
            {"key": "cpu", "value": "1%", "percent": 1, "note": "cpu"},
            {"key": "memory", "value": "1 / 2 GiB", "percent": 50, "note": "swap"},
            {"key": "disk", "value": "1 / 2 GiB", "percent": 40, "note": "/tmp"},
        ],
    )
    monkeypatch.setattr(
        overview,
        "_checkin_module",
        lambda: {"key": "checkin", "stats": [{"key": "disabled", "value": 0}], "lines": []},
    )

    now = datetime.now(timezone.utc)
    created = now.strftime("%Y-%m-%d %H:%M:%S")
    published = json.dumps(
        {"publish_result": {"status": "success", "at": now.isoformat()}}
    )
    old = json.dumps(
        {
            "publish_result": {
                "status": "success",
                "at": (now - timedelta(days=2)).isoformat(),
            }
        }
    )
    sql.execute(
        """
        INSERT INTO video_job (title, status, stage, fail_stage)
        VALUES ('草莓', 'failed', 'tts', 'tts')
        """
    )
    sql.execute(
        """
        INSERT INTO video_job (title, status, stage)
        VALUES ('遥控器', 'pending', 'segment')
        """
    )
    sql.execute(
        """
        INSERT INTO video_job (title, status, stage)
        VALUES ('在跑', 'running', 'merge')
        """
    )
    sql.execute(
        """
        INSERT INTO video_job (title, status, stage, publish, info)
        VALUES ('今天发出', 'done', 'publish', 1, ?)
        """,
        (published,),
    )
    sql.execute(
        """
        INSERT INTO video_job (title, status, stage, publish, info)
        VALUES ('前天发出', 'done', 'publish', 1, ?)
        """,
        (old,),
    )
    sql.execute(
        """
        INSERT INTO daily_story (theme, story_json, story_type, created_at)
        VALUES ('洗碗', '{}', 'C', ?)
        """,
        (created,),
    )
    sql.execute(
        """
        INSERT INTO title (title, status, score)
        VALUES ('热水', 'queued', 86)
        """
    )
    sql.execute(
        """
        INSERT INTO material_video (name, file_path, status)
        VALUES ('厨房俯拍', 'a.mp4', 'analyze_failed')
        """
    )
    sql.execute(
        """
        INSERT INTO gold_story (
            source, source_id, url, mechanism, structure_type,
            auto_score, content_hash, payload_json, title
        ) VALUES (
            'bili', 'BV1', 'https://example.com/1', 'm', 'A',
            1, 'hash-1', ?, '作业写到半夜'
        )
        """,
        (json.dumps({"gold_chat_last_error": "转换中断"}),),
    )
    sql.commit()

    data = build_overview()
    jobs = next(item for item in data["modules"] if item["key"] == "jobs")
    stats = {item["key"]: item["value"] for item in jobs["stats"]}
    assert stats["failed"] == 1
    assert stats["pending"] == 1
    assert stats["queued"] == 0
    assert stats["running"] == 1
    assert "label" not in jobs["stats"][1]
    assert jobs["lines"][0]["code"] == "failed"
    assert jobs["lines"][0]["stage"] == "tts"
    assert jobs["lines"][0]["to"].startswith("/jobs?id=")
    pending_line = next(item for item in jobs["lines"] if item["title"] == "遥控器")
    assert pending_line["code"] == "pending"
    assert pending_line["stage"] == "segment"
    assert "tone" not in pending_line

    progress = {item["key"]: item["value"] for item in data["progress"]}
    assert progress["stories_today"] == 1
    assert progress["running"] == 1
    assert progress["published_today"] == 1
    assert "stories_cost" not in progress

    alert_codes = {(item["module"], item["code"]) for item in data["alerts"]}
    assert ("jobs", "failed") in alert_codes
    assert ("video", "analyze_failed") in alert_codes
    assert ("gold_chat", "convert_failed") in alert_codes
    assert ("jobs", "pending") not in alert_codes
    failed_alert = next(item for item in data["alerts"] if item["code"] == "failed")
    assert failed_alert["id"] == int(failed_alert["to"].rsplit("=", 1)[-1])
    assert all(isinstance(item.get("id"), int) for item in data["alerts"])
    assert data["host"]
    _assert_no_label_chinese(data)


_CONTENT_KEYS = {"title", "host", "note"}
_CJK = re.compile(r"[\u4e00-\u9fff]")


def _assert_no_label_chinese(value: object, key: str = "") -> None:
    """标题、主机名、机器备注是数据，其余字段不应带展示用汉字。"""
    if isinstance(value, dict):
        for item_key, item in value.items():
            _assert_no_label_chinese(item, str(item_key))
        return
    if isinstance(value, list):
        for item in value:
            _assert_no_label_chinese(item, key)
        return
    if isinstance(value, str) and key not in _CONTENT_KEYS:
        assert _CJK.search(value) is None, f"{key}={value}"
