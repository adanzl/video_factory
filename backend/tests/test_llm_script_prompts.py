"""口播提示词字数预算测试。"""

from __future__ import annotations

from app.services.script.image_prompt import build_image_prompts
from app.services.script.visual_brief import build_visual_brief_prompts
from app.services.script.voiceover_standard import (
    build_voiceover_standard_prompts,
    build_voiceover_standard_shrink_prompts,
)
from app.services.script.compose import collect_prompts
from app.utils.job_info import CONTENT_STYLE_LIFE_EXPERIENCE
from app.utils.media import (
    min_narration_chars_for_target,
    narration_accept_max_chars,
    narration_accept_min_chars,
    narration_target_for_minutes,
    narration_word_range,
)


def test_narration_word_range_aligns_min_with_validation():
    target = 1318
    lo, hi = narration_word_range(target)
    assert lo == narration_accept_min_chars(target)
    assert hi == target + max(50, int(target * 0.1))


def test_build_image_prompts_discourages_generic_motion():
    script = {
        "title": "测试标题",
        "visual_style": "3D卡通科普",
        "segments": [
            {
                "segment_index": 1,
                "text": "第一段口播。",
                "visual_brief": "展示地震波传播示意。（结构示意图）",
                "visual_mode": "static_motion",
            },
        ],
    }
    prompts = build_image_prompts(
        script,
        job={"pipeline": "standard", "content_style": "science_child"},
    )
    assert "禁止套话" in prompts["user"]
    assert "各段互不重复" in prompts["user"]
    assert "炉口青烟缓缓上升" in prompts["system"]
    assert "卡通科普插画风" in prompts["system"]
    assert "明快蓝橙主色调" in prompts["system"]


def test_build_voiceover_standard_prompts_science_child_skips_visual_style():
    """A1 不再注入 visual_style；画风由后端硬编码写入后续步骤。"""
    prompts = build_voiceover_standard_prompts(
        "地震预警只有几十秒",
        narration_target_words=800,
        job={"pipeline": "standard", "content_style": "science_child"},
    )
    assert "卡通科普插画风" not in prompts["system"]
    assert "明快蓝橙主色调" not in prompts["system"]
    assert "你是给小朋友讲科普的视频编剧" in prompts["system"]
    assert "visual_style 由后端写入" in prompts["system"]


def test_build_voiceover_standard_prompts_history_mystery_role():
    prompts = build_voiceover_standard_prompts(
        "雍正暴毙之谜",
        narration_target_words=800,
        job={"pipeline": "standard", "info": {"content_style": "history_mystery"}},
    )
    assert "电影级写实历史再现" not in prompts["system"]
    assert "你是B站历史悬案视频的编剧" in prompts["system"]
    assert "事实+转折+反问" in prompts["user"]


def test_build_voiceover_standard_prompts_tech_science_not_child_voice():
    prompts = build_voiceover_standard_prompts(
        "光刻机为什么贵",
        narration_target_words=800,
        job={"pipeline": "standard", "content_style": "tech_science"},
    )
    assert "小朋友" not in prompts["system"]
    assert "你是B站科技/产业科普的内容编剧" in prompts["system"]
    assert "现象+机制+结论" in prompts["user"]
    assert "禁止儿童感叹词" in prompts["system"]
    assert "你看" not in prompts["system"]


def test_build_voiceover_standard_prompts_supplementary_no_timeline():
    prompts = build_voiceover_standard_prompts(
        "测试标题",
        narration_target_words=800,
        supplementary_info="补充：强调因果关系",
        job={"pipeline": "standard", "content_style": "science_child"},
    )
    assert "时间表" not in prompts["system"]
    assert "以科学事实为准" in prompts["system"]
    assert "补充：强调因果关系" in prompts["user"]


def test_build_image_prompts_history_mystery_forbids_cartoon():
    script = {
        "title": "测试",
        "visual_style": "电影级写实历史再现，低饱和古风",
        "segments": [
            {
                "segment_index": 1,
                "text": "口播",
                "visual_brief": "宫廷内景。（历史场景再现）",
            },
        ],
    }
    prompts = build_image_prompts(
        script,
        job={"pipeline": "standard", "info": {"content_style": "history_mystery"}},
    )
    assert "禁止卡通/绘本/扁平插画风" in prompts["system"]
    assert "你是历史悬案视频文生图" in prompts["system"]


def test_build_voiceover_standard_prompts_focuses_on_total_length():
    target = 1318
    prompts = build_voiceover_standard_prompts(
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


def test_build_voiceover_standard_prompts_includes_anti_repetition_rule():
    prompts = build_voiceover_standard_prompts(
        "地震预警的秘密",
        narration_target_words=800,
        job={"pipeline": "standard", "content_style": "science_child"},
    )
    assert "禁止复读" in prompts["system"]


def test_build_voiceover_standard_prompts_life_experience_bans_memoir_style():
    prompts = build_voiceover_standard_prompts(
        "瓦斯来了湿毛巾捂嘴对吗",
        narration_target_words=800,
        job={"pipeline": "standard", "info": {"content_style": "life_experience"}},
    )
    assert "禁止伪亲历体" in prompts["system"]
    assert "我当" in prompts["system"]
    assert "误区+原因+正确做法" in prompts["user"]


def test_build_voiceover_standard_prompts_science_child_structure():
    prompts = build_voiceover_standard_prompts(
        "光刻胶是什么",
        narration_target_words=800,
        job={"pipeline": "standard", "content_style": "science_child"},
    )
    assert "【结构规范】" in prompts["system"]
    assert "开场钩子" in prompts["system"]
    assert "感叹+科普点+比喻/拟声" in prompts["user"]


def test_build_voiceover_standard_prompts_emphasizes_narration_max():
    target = narration_target_for_minutes(6.0)
    accept_max = narration_accept_max_chars(target)
    prompts = build_voiceover_standard_prompts(
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


def test_voiceover_standard_shrink_prompts_preserve_voice():
    script = {
        "segments": [
            {"segment_index": 1, "text": "哇，空调居然这么神奇！" + "x" * 80},
        ]
    }
    prompts = build_voiceover_standard_shrink_prompts(
        script,
        segment_indices=[1],
        cap=75,
        segment_target_sec=15.0,
    )
    assert "segment_index" in prompts["system"]
    assert "不要输出 narration" in prompts["system"]


def test_collect_prompts_accepts_speech_chars_per_sec():
    job = {"pipeline": "standard", "info": {}}
    prompts = collect_prompts(
        job,
        "测试标题",
        speech_chars_per_sec=4.1,
        preview_followups=True,
    )
    steps = [item["step"] for item in prompts]
    assert steps == ["narration", "visual_brief", "image_prompts", "title_optimize"]
    assert all(item["step"] != "video_description" for item in prompts)


def test_collect_prompts_preview_includes_title_optimize_when_skipped_at_runtime():
    job = {"pipeline": "standard", "info": {}}
    prompts = collect_prompts(
        job,
        "测试标题",
        skip_title_optimize=True,
        preview_followups=True,
    )
    assert "title_optimize" in [item["step"] for item in prompts]


def test_collect_prompts_omits_title_optimize_when_skipped_without_preview():
    job = {"pipeline": "standard", "info": {}}
    script = {
        "title": "测试标题",
        "narration": "x" * 200,
        "segments": [{"segment_index": 1, "text": "x" * 50, "visual_brief": "画面"}],
    }
    prompts = collect_prompts(
        job,
        "测试标题",
        script=script,
        skip_title_optimize=True,
    )
    assert "title_optimize" not in [item["step"] for item in prompts]


def test_collect_prompts_includes_followup_steps_when_script_ready():
    job = {"pipeline": "standard", "info": {}}
    script = {
        "title": "测试标题",
        "narration": "x" * 200,
        "segments": [{"segment_index": 1, "text": "x" * 50, "visual_brief": "画面"}],
    }
    prompts = collect_prompts(job, "测试标题", script=script)
    steps = [item["step"] for item in prompts]
    assert steps == ["narration", "visual_brief", "image_prompts", "title_optimize"]
