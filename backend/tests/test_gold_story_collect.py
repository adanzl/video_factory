"""金故事 H0/H1 采集测试。"""

from __future__ import annotations

from app.services.daily_story.gold_story.collect import (
    engagement_norm,
    passes_h1_filter,
)


def test_engagement_norm():
    assert engagement_norm(500_000, 500) == 1.0
    assert engagement_norm(0, 0) == 0.0


def test_h1_passes_with_high_view():
    ok, reason = passes_h1_filter(
        title="姐弟吵架名场面",
        view_count=200_000,
        reply_count=10,
    )
    assert ok is True
    assert reason == "ok"


def test_h1_rejects_exclude_title():
    ok, reason = passes_h1_filter(
        title="萌娃英语启蒙教程",
        view_count=500_000,
        reply_count=100,
    )
    assert ok is False
    assert reason == "exclude_title"


def test_h1_rejects_low_engagement():
    ok, reason = passes_h1_filter(
        title="姐弟日常",
        view_count=1000,
        reply_count=2,
    )
    assert ok is False
    assert reason == "low_engagement"
