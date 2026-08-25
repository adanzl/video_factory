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


def test_near_duplicate_catches_reprint_wording():
    from app.repositories.repo_gold_story import is_near_duplicate_story

    original = (
        "东北一辆车里，姐姐突然灵魂拷问：“我爱学习，你爱吗？”"
        "弟弟语塞。姐姐说：“都是一个爸爸妈妈生的，凭什么我爱学习你不爱？”"
        "弟弟嘟囔：“你听不懂我说话，我也听不懂你说话，这就完了呗。”"
        "姐姐回击：“我是听不懂你说话，大舌叽叽的。”弟弟彻底败下阵来。"
    )
    reprint = (
        "行驶的车里弟弟嘴硬说和姐姐相同。姐姐反问：“我就是爱学习，你爱吗？”"
        "又说都是一个爸爸妈妈生出来的。弟弟只能嘟囔："
        "“你听不懂我说话，我也听不懂你说话，这就完了得了呗。”"
        "姐姐不依不饶：“我是听不懂你说话，大舌唧叽的。”弟弟彻底败下阵来。"
    )
    other = (
        "客厅里两人为抢遥控器吵起来，妈妈让谁先放手谁先选。"
        "弟弟先放手却被姐姐反悔，最后妈妈把遥控器收回去了。"
    )
    assert is_near_duplicate_story(original, reprint) is True
    assert is_near_duplicate_story(original, other) is False


def test_insert_skips_similar_reprint(app_ctx):
    from app.repositories import repo_gold_story

    original = (
        "东北一辆车里，姐姐突然灵魂拷问：“我爱学习，你爱吗？”"
        "弟弟语塞。姐姐说：“都是一个爸爸妈妈生的，凭什么我爱学习你不爱？”"
        "弟弟嘟囔：“你听不懂我说话，我也听不懂你说话，这就完了呗。”"
        "姐姐回击：“我是听不懂你说话，大舌叽叽的。”弟弟彻底败下阵来。"
    )
    reprint = (
        "行驶的车里弟弟嘴硬说和姐姐相同。姐姐反问：“我就是爱学习，你爱吗？”"
        "又说都是一个爸爸妈妈生出来的。弟弟只能嘟囔："
        "“你听不懂我说话，我也听不懂你说话，这就完了得了呗。”"
        "姐姐不依不饶：“我是听不懂你说话，大舌唧叽的。”弟弟彻底败下阵来。"
    )
    first = repo_gold_story.insert_or_skip(
        source="bili",
        source_id="BV1ORIGTEST01",
        url="https://www.bilibili.com/video/BV1ORIGTEST01",
        mechanism="M11",
        structure_type="I",
        story_raw=original,
        payload={"story_raw": original, "beat": ["a", "b", "c", "d"]},
        title="原片灵魂拷问",
        auto_score=0.8,
        status="active",
    )
    assert first.get("action") == "insert"
    second = repo_gold_story.insert_or_skip(
        source="bili",
        source_id="BV1REPRINT001",
        url="https://www.bilibili.com/video/BV1REPRINT001",
        mechanism="M11",
        structure_type="I",
        story_raw=reprint,
        payload={"story_raw": reprint, "beat": ["a", "b", "c", "d"]},
        title="转载灵魂拷问",
        auto_score=0.8,
        status="active",
    )
    assert second.get("action") == "skip"
    assert second.get("reason") == "duplicate_similar_story"
    assert int(second.get("id")) == int(first["id"])
