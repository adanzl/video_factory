"""funny_signal 观众反应测试。"""

from __future__ import annotations

from app.repositories import repo_gold_story
from app.services.daily_story.gold_story.funny_signal import (
    AudienceFunnyMetrics,
    comment_laugh_ratio,
    compute_funny_signal,
    cute_not_funny_flag,
    danmaku_laugh_ratio,
    passes_funny_gate,
    passes_funny_gate_from_payload,
)


def test_danmaku_laugh_ratio_counts_strong_words():
    texts = ["笑死我了", "前方高能", "哈哈哈哈哈哈"]
    total, ratio = danmaku_laugh_ratio(texts)
    assert total == 3
    assert ratio > 0.3


def test_comment_laugh_ratio():
    replies = ["哈哈哈太好笑了", "前排", "笑死这小孩"]
    assert comment_laugh_ratio(replies) == 0.6667


def test_compute_funny_signal_formula():
    signal = compute_funny_signal(
        dm_laugh_ratio=0.4,
        comment_laugh=0.2,
        view_reply_norm=0.5,
    )
    assert signal == round(0.5 * 0.4 + 0.3 * 0.2 + 0.2 * 0.5, 4)


def test_cute_not_funny_flag():
    assert cute_not_funny_flag(["好可爱啊啊啊"], ["心化了"]) is True
    assert cute_not_funny_flag(["笑死我了"], ["哈哈哈"]) is False


def test_passes_funny_gate_l2_rejects_low_signal():
    metrics = AudienceFunnyMetrics(
        danmaku_total=100,
        danmaku_laugh_score=10.0,
        danmaku_laugh_ratio=0.1,
        comment_laugh_ratio=0.05,
        view_reply_ratio_norm=0.2,
        funny_signal=0.15,
        cute_not_funny=False,
        danmaku_fetch_ok=True,
    )
    ok, reason = passes_funny_gate(metrics, level="l2")
    assert ok is False
    assert "low_funny_signal" in reason


def test_passes_funny_gate_from_payload():
    ok, _ = passes_funny_gate_from_payload(
        {
            "funny_signal": 0.55,
            "comment_laugh_ratio": 0.3,
            "danmaku_total": 80,
            "danmaku_fetch_ok": True,
            "cute_not_funny": False,
        },
        level="l2",
    )
    assert ok is True


def test_passes_funny_gate_rejects_no_danmaku_laugh():
    metrics = AudienceFunnyMetrics(
        danmaku_total=100,
        danmaku_laugh_score=1.0,
        danmaku_laugh_ratio=0.01,
        comment_laugh_ratio=0.3,
        view_reply_ratio_norm=0.5,
        funny_signal=0.5,
        cute_not_funny=False,
        danmaku_fetch_ok=True,
    )
    ok, reason = passes_funny_gate(metrics, level="l1")
    assert ok is False
    assert "no_danmaku_laugh" in reason


def test_compute_auto_score_uses_funny_signal():
    score = repo_gold_story.compute_auto_score(
        funny_signal=0.8,
        extract_confidence=0.7,
        structure_confidence=0.7,
        dialogue_confidence=0.7,
    )
    assert score == round(0.45 * 0.8 + 0.20 * 0.7 + 0.20 * 0.7 + 0.15 * 0.7, 4)
