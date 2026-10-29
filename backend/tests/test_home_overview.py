"""首页总览：库内计数，不打外部签到和机器采样。"""

from __future__ import annotations

import json
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
        lambda: {"key": "checkin", "stats": [{"label": "状态", "value": "未启用"}], "lines": []},
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
    stats = {item["label"]: item["value"] for item in jobs["stats"]}
    assert stats["失败"] == 1
    assert stats["停住"] == 1
    assert stats["进行中"] == 1
    assert jobs["lines"][0]["note"] == "配音失败"
    assert jobs["lines"][0]["to"].startswith("/jobs?id=")

    progress = {item["label"]: item["value"] for item in data["progress"]}
    assert progress["今日生成"] == "1 篇"
    assert progress["正在跑"] == "1 个"
    assert progress["今日发布"] == "1 条"
    assert "今日花费" not in progress

    notes = [item["note"] for item in data["alerts"]]
    assert "配音失败" in notes
    assert "分析失败" in notes
    assert "转换失败" in notes
    assert "停在分镜" in notes
    assert data["host"]
