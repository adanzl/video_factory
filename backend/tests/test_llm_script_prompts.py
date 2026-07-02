"""口播提示词字数预算测试。"""

from __future__ import annotations

from app.services.script.board import (
    _narration_word_range,
    build_narration_prompts,
    build_segment_shrink_prompts,
    build_visual_brief_prompts,
)
from app.utils.job_info import CONTENT_STYLE_LIFE_EXPERIENCE
from app.utils.media import (
    min_narration_chars_for_target,
    narration_accept_max_chars,
    narration_accept_min_chars,
    narration_target_for_minutes,
)


def test_narration_word_range_aligns_min_with_validation():
    target = 1318
    lo, hi = _narration_word_range(target)
    assert lo == narration_accept_min_chars(target)
    assert hi == target + max(50, int(target * 0.1))


def test_build_narration_prompts_focuses_on_total_length():
    target = 1318
    prompts = build_narration_prompts(
        "测试标题",
        narration_target_words=target,
        job={"pipeline": "standard", "content_style": CONTENT_STYLE_LIFE_EXPERIENCE},
    )
    hard_min = narration_accept_min_chars(target)
    assert str(hard_min) in prompts["user"]
    assert "不要输出 segments" in prompts["system"]
    assert "禁止输出 segments" in prompts["system"] or "不要输出 segments" in prompts["user"]
    assert "字数预算" in prompts["user"]
    assert "95%" in prompts["user"] or "95％" in prompts["user"]


def test_build_narration_prompts_includes_anti_repetition_rule():
    prompts = build_narration_prompts(
        "地震预警的秘密",
        narration_target_words=800,
        job={"pipeline": "standard", "content_style": "science_child"},
    )
    assert "禁止复读" in prompts["system"]


def test_build_narration_prompts_life_experience_bans_memoir_style():
    prompts = build_narration_prompts(
        "瓦斯来了湿毛巾捂嘴对吗",
        narration_target_words=800,
        job={"pipeline": "standard", "info": {"content_style": "life_experience"}},
    )
    assert "禁止伪亲历体" in prompts["system"]
    assert "我当" in prompts["system"]
    assert "误区+原因+正确做法" in prompts["user"]


def test_build_narration_prompts_science_child_structure():
    prompts = build_narration_prompts(
        "光刻胶是什么",
        narration_target_words=800,
        job={"pipeline": "standard", "content_style": "science_child"},
    )
    assert "【结构规范】" in prompts["system"]
    assert "开场钩子" in prompts["system"]
    assert "感叹+科普点+比喻/拟声" in prompts["user"]


def test_build_narration_prompts_emphasizes_narration_max():
    target = narration_target_for_minutes(6.0)
    accept_max = narration_accept_max_chars(target)
    prompts = build_narration_prompts(
        "地震预警只有几十秒",
        narration_target_words=target,
        job={"pipeline": "standard", "content_style": "science_child"},
    )
    assert "【首要任务】" in prompts["user"] or "硬区间" in prompts["user"]
    assert str(accept_max) in prompts["user"]
    assert "独立的小知识点" not in prompts["system"]


def test_build_visual_brief_prompts_includes_full_narration():
    script = {
        "title": "测试标题",
        "narration": "全文口播内容在这里。",
        "visual_style": "测试画风",
        "segments": [
            {"segment_index": 1, "text": "全文口播内容在这里。", "visual_mode": "static_motion"},
        ],
    }
    prompts = build_visual_brief_prompts(
        script,
        job={"pipeline": "standard", "content_style": "science_child"},
    )
    assert "【口播全文 narration】" in prompts["user"]
    assert script["narration"] in prompts["user"]
    assert "画面衔接自然" in prompts["system"] or "连贯" in prompts["system"]
    assert "不要输出或修改各段 text" in prompts["system"]


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
    assert "segment_index" in prompts["system"]
    assert "不要输出 narration" in prompts["system"]
