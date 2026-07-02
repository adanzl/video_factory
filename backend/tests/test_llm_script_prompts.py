"""口播提示词字数预算测试。"""

from __future__ import annotations

from app.services.script.prompts import (
    _narration_word_range,
    _storyboard_length_budget,
    build_segment_shrink_prompts,
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


def test_storyboard_length_budget_life_28s_per_segment_cap():
    target = narration_target_for_minutes(6.0)
    assert target == 1646
    budget = _storyboard_length_budget(
        narration_target=target,
        segment_target_sec=28.0,
        content_style=CONTENT_STYLE_LIFE_EXPERIENCE,
    )
    assert "140" in budget
    assert "须至少" in budget
    assert "输出前硬性自检" in budget


def test_build_storyboard_prompts_includes_length_budget():
    prompts = build_storyboard_prompts(
        "测试标题",
        narration_target_words=1318,
        segment_target_sec=16.0,
        job={"pipeline": "standard", "content_style": CONTENT_STYLE_LIFE_EXPERIENCE},
    )
    assert "【单段上限·优先】" in prompts["user"]
    assert "字数预算" in prompts["user"]
    assert "95%" in prompts["user"] or "95％" in prompts["user"]
    assert "输出前硬性自检" in prompts["user"]
    assert "禁止把多句堆进同一段" in prompts["system"] or "禁止把多句堆进同一段" in prompts["user"]
    assert str(narration_accept_min_chars(1318)) in prompts["user"]


def test_storyboard_compact_output_default_standard():
    from app.utils.media import default_narration_target_words

    target = default_narration_target_words()
    assert storyboard_compact_output(target, 16.0) is True


def test_build_storyboard_life_experience_bans_memoir_style():
    prompts = build_storyboard_prompts(
        "瓦斯来了湿毛巾捂嘴对吗",
        narration_target_words=800,
        segment_target_sec=16.0,
        job={"pipeline": "standard", "info": {"content_style": "life_experience"}},
    )
    assert "禁止伪亲历体" in prompts["system"]
    assert "我当" in prompts["system"]
    assert "误区+原因+正确做法" in prompts["user"]


def test_build_storyboard_science_child_uses_four_part_structure_and_self_check():
    prompts = build_storyboard_prompts(
        "光刻胶是什么",
        narration_target_words=800,
        segment_target_sec=10.0,
        job={"pipeline": "standard", "content_style": "science_child"},
    )
    assert "【结构规范】" in prompts["system"]
    assert "开场钩子" in prompts["system"]
    assert "机制拆解" in prompts["system"]
    assert "输出前须自检" in prompts["system"]
    assert "感叹+科普点+比喻/拟声" in prompts["user"]
    assert "【单段上限·优先】" in prompts["user"]


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


def test_segment_shrink_prompts_preserve_voice():
    script = {
        "segments": [
            {"segment_index": 1, "text": "哇，空调居然这么神奇！" + "x" * 80},
        ]
    }
    prompts = build_segment_shrink_prompts(
        script,
        segment_indices=[1],
        cap=75,
        segment_target_sec=15.0,
    )
    assert "文风" in prompts["system"]
    assert "口吻" in prompts["system"]
    assert "保持原文风" in prompts["user"]
