"""金故事 H5–H7 注入块测试。"""

from __future__ import annotations

from unittest.mock import patch

from app.services.daily_story.gold_story.inject import (
    build_gold_story_block,
    pick_for_injection,
    resolve_gold_story_block,
)
from app.services.daily_story.prompts import build_daily_story_prompts


_SAMPLE = {
    "id": 1,
    "mechanism": "M2",
    "structure_type": "C",
    "conflict_core": "独占不让吃，被质问后歪理自洽",
    "payload": {
        "beat": ["独占不让", "被质问", "歪理自洽"],
        "scene_contract": {
            "source_type": "field",
            "location": "餐桌",
            "object": "果汁",
            "characters": ["昭昭", "灿灿"],
            "conflict": "争果汁",
            "mom_lines_max": 0,
            "beat_chain": [
                {"speaker": "灿灿", "intent": "宣布占有"},
                {"speaker": "昭昭", "intent": "质疑"},
                {"speaker": "灿灿", "intent": "歪理"},
                {"speaker": "昭昭", "intent": "收束"},
            ],
        },
        "dialogue_seed": [
            {"speaker": "灿灿", "intent": "宣布占有"},
            {"speaker": "昭昭", "intent": "质疑"},
        ],
        "closing_intent": "嘴硬收束",
        "banned_literals": ["妹妹", "哥哥"],
    },
}


def test_build_gold_story_block_shape():
    block = build_gold_story_block(_SAMPLE)
    assert "【金故事·对话方向·禁照抄站外原文】" in block
    assert "M2" in block
    assert "1. 独占不让" in block
    assert "灿灿：宣布占有" in block
    assert "scene_contract" in block
    assert "禁词：妹妹、哥哥" in block
    assert "story_raw" not in block.lower()


def test_resolve_disabled_by_default():
    block, row = resolve_gold_story_block(theme="抢遥控器", story_type="C")
    assert block == ""
    assert row is None


def test_resolve_when_enabled():
    cfg = type("Cfg", (), {"gold_story_enabled": True})()
    with patch(
        "app.services.daily_story.gold_story.inject.pick_for_injection",
        return_value=_SAMPLE,
    ):
        block, row = resolve_gold_story_block(
            theme="抢遥控器",
            story_type="C",
            config=cfg,
        )
    assert row is _SAMPLE
    assert "冲突核：独占不让吃" in block


def test_pick_skips_excluded_mechanism():
    rows = [
        {**_SAMPLE, "mechanism": "M2"},
        {**_SAMPLE, "id": 2, "mechanism": "M4"},
    ]
    with patch("app.repositories.repo_gold_story.pick", return_value=rows):
        with patch(
            "app.services.daily_story.gold_story.inject.recent_injected_mechanisms",
            return_value={"M2"},
        ):
            picked = pick_for_injection(theme="结盟", story_type="C")
    assert picked is not None
    assert picked["mechanism"] == "M4"


def test_build_daily_story_prompts_no_block_when_disabled():
    _sys, user = build_daily_story_prompts(
        "抢遥控器",
        story_type="C",
        length_mode="draft",
    )
    assert "【金故事·对话方向" not in user


def test_build_daily_story_prompts_injects_when_enabled():
    with patch(
        "app.services.daily_story.prompts._resolve_gold_story_user_block",
        return_value=(build_gold_story_block(_SAMPLE), _SAMPLE),
    ):
        _sys, user = build_daily_story_prompts(
            "抢遥控器",
            story_type="C",
            length_mode="draft",
        )
    assert user.startswith("【金故事·对话方向")
