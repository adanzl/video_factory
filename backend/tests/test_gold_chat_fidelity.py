"""gold_chat 金稿保真 checklist。"""

from __future__ import annotations

from app.services.daily_story.gold_story.gold_chat_fidelity import (
    fidelity_chain,
    format_fidelity_block,
)


def test_m5_h_chain_has_mutual_destruction_and_escalation():
    chain = fidelity_chain(structure_type="H", mechanism="M5")
    blob = "\n".join(chain)
    assert "双向互毁" in blob
    assert "M5 加码" in blob
    assert "谁先动手" in blob


def test_fidelity_block_includes_beats_and_bans():
    block = format_fidelity_block(
        structure_type="H",
        mechanism="M5",
        beat=["互毁扭打", "妈妈劝和"],
        closing_intent="齐声不打了",
        story_raw="双胞胎画画互毁",
    )
    assert "金稿保真 checklist" in block
    assert "互毁扭打" in block
    assert "齐声不打了" in block
    assert "禁止 Invent" in block
    assert "彩虹" in block
