"""口播提示词字数预算测试。"""

from __future__ import annotations

from app.services.llm.llm_script_prompts import (
    _narration_word_range,
    _storyboard_length_budget,
    build_storyboard_prompts,
)
from app.utils.job_info import CONTENT_STYLE_LIFE_EXPERIENCE
from app.utils.media import (
    min_narration_chars_for_target,
    narration_accept_min_chars,
    narration_target_for_minutes,
    storyboard_compact_output,
)


def test_narration_word_range_aligns_min_with_validation():
    target = 1318
    lo, hi = _narration_word_range(target)
    assert lo == narration_accept_min_chars(target)
    assert hi == target + max(50, int(target * 0.1))


def test_storyboard_length_budget_requires_enough_segments():
    target = 1318
    budget = _storyboard_length_budget(
        narration_target=target,
        segment_target_sec=16.0,
        content_style=CONTENT_STYLE_LIFE_EXPERIENCE,
    )
    hard_min = narration_accept_min_chars(target)
    assert str(hard_min) in budget
    assert "segments" in budget
    assert "字数预算" in budget


def test_storyboard_length_budget_life_28s_needs_many_segments():
    target = narration_target_for_minutes(6.0)
    assert target == 1646
    budget = _storyboard_length_budget(
        narration_target=target,
        segment_target_sec=28.0,
        content_style=CONTENT_STYLE_LIFE_EXPERIENCE,
    )
    assert "12 个 segments" in budget
    assert "140" in budget
    assert "禁止用 3～5 个长段" in budget


def test_build_storyboard_prompts_includes_length_budget():
    prompts = build_storyboard_prompts(
        "测试标题",
        narration_target_words=1318,
        segment_target_sec=16.0,
        job={"pipeline": "standard", "content_style": CONTENT_STYLE_LIFE_EXPERIENCE},
    )
    assert "字数预算" in prompts["user"]
    assert "1120" in prompts["user"] or str(narration_accept_min_chars(1318)) in prompts["user"]


def test_storyboard_compact_output_for_landscape_life_preset():
    target = narration_target_for_minutes(6.0)
    assert storyboard_compact_output(target, 28.0) is True


def test_build_storyboard_prompts_compact_omits_narration_field():
    prompts = build_storyboard_prompts(
        "测试标题",
        narration_target_words=1646,
        segment_target_sec=28.0,
        compact_output=True,
    )
    assert "不要输出 narration" in prompts["system"]
    assert "narration, word_count, visual_style" not in prompts["system"]
    assert "JSON 输出样例" in prompts["system"]
    assert "segment_index" in prompts["system"]
