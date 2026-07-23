"""日常故事角色入画校验。"""

from __future__ import annotations

from app.quality.image_prompt import check_image_prompt
from app.services.daily_story.cast import (
    cast_leaks_in_text,
    collect_daily_cast_issues,
    scrub_cast_leaks,
    speakers_from_dialogue,
)
from app.services.script.image_prompt import build_image_prompts


def test_speakers_and_leak_detection():
    allowed = speakers_from_dialogue(
        [{"speaker": "昭昭", "text": "a"}, {"speaker": "灿灿", "text": "b"}]
    )
    assert allowed == {"昭昭", "灿灿"}
    assert cast_leaks_in_text("妈妈站在中间，昭昭举手。", allowed) == ["妈妈"]
    assert cast_leaks_in_text("昭昭与灿灿对峙。", allowed) == []


def test_scrub_cast_leaks_drops_mom_clause():
    text = "昭昭举手比石头。妈妈站在两人中间手臂微张。灿灿双手叉腰。"
    cleaned = scrub_cast_leaks(text, {"昭昭", "灿灿"})
    assert "妈妈" not in cleaned
    assert "昭昭" in cleaned
    assert "灿灿" in cleaned


def test_check_image_prompt_rejects_cast_leak():
    script = {
        "content_style": "daily_story",
        "segments": [
            {
                "segment_index": 7,
                "dialogue": [
                    {"speaker": "昭昭", "text": "a"},
                    {"speaker": "灿灿", "text": "b"},
                ],
                "image_prompt": (
                    "客厅里昭昭举手，灿灿叉腰；妈妈站中间手臂微张，面露无奈。"
                    + "x" * 80
                ),
            }
        ],
    }
    report = check_image_prompt(script, content_style="daily_story")
    assert report.level == "major"
    assert report.details["reason"] == "daily cast leak in image_prompt"


def test_build_daily_image_prompts_is_slimmer():
    script = {
        "title": "谁先洗澡",
        "visual_style": "儿童情绪涂鸦风格",
        "segments": [
            {
                "segment_index": 1,
                "text": "台词",
                "visual_brief": "昭昭举手",
                "image_prompt": "儿童情绪涂鸦风格。昭昭举手。",
                "dialogue": [{"speaker": "昭昭", "text": "台词"}],
            }
        ],
    }
    prompts = build_image_prompts(
        script,
        content_style="daily_story",
        job={"pipeline": "chat", "content_style": "daily_story"},
    )
    system = prompts["system"]
    assert "世界地图" not in system
    assert "丹炉" not in system
    assert "纱帘" in system or "窗边" in system
    assert "规则拼装" in system
    assert "禁止改写" in system
    assert "不要输出 image_prompt" in prompts["user"]
    assert "motion_mode=ambient" in prompts["user"]
    assert "image_prompt=" in prompts["user"]
    assert len(system) < 3800


def test_build_image_prompts_daily_includes_setting():
    from app.services.script.image_prompt import build_image_prompts

    script = {
        "title": "新橡皮归谁",
        "setting": "客厅，昭昭和灿灿同时抓住一块新橡皮。",
        "visual_style": "儿童情绪涂鸦",
        "content_style": "daily_story",
        "segments": [
            {
                "segment_index": 1,
                "text": "我先拿到的！",
                "visual_brief": "客厅里姐弟抢橡皮",
                "image_prompt": "已拼装提示词",
                "dialogue": [{"speaker": "昭昭", "text": "我先拿到的！"}],
            }
        ],
    }
    prompts = build_image_prompts(
        script,
        content_style="daily_story",
        job={"pipeline": "chat", "content_style": "daily_story"},
    )
    assert "全片地点 setting：客厅" in prompts["user"]
    assert "规则拼装" in prompts["system"]
    assert "motion_prompt" in prompts["system"]


def test_build_image_prompts_daily_keyframe_marks_motion_mode():
    from app.services.script.image_prompt import build_image_prompts
    from app.utils.job_info import apply_keyframe_video_providers

    script = {
        "title": "新橡皮归谁",
        "visual_style": "儿童情绪涂鸦",
        "content_style": "daily_story",
        "segments": [
            {
                "segment_index": 1,
                "text": "开场抢",
                "visual_brief": "举手抢橡皮",
                "shot_type": "特写",
                "dialogue": [{"speaker": "昭昭", "text": "我先拿到的！"}],
            },
            {
                "segment_index": 2,
                "text": "普通镜",
                "visual_brief": "中景对峙",
                "dialogue": [{"speaker": "昭昭", "text": "普通镜"}],
            },
            {
                "segment_index": 3,
                "text": "停！",
                "visual_brief": "妈妈举手停，昭昭侧头",
                "shot_type": "特写",
                "dialogue": [{"speaker": "妈妈", "text": "停！"}],
            },
        ],
    }
    apply_keyframe_video_providers(script["segments"])
    prompts = build_image_prompts(
        script,
        content_style="daily_story",
        job={"pipeline": "chat", "content_style": "daily_story"},
    )
    assert "segment 1:" in prompts["user"] and "motion_mode=keyframe" in prompts["user"]
    assert "segment 2:" in prompts["user"]
    assert "motion_mode=ambient" in prompts["user"]
    assert "motion_mode=keyframe" in prompts["user"]
    assert "keyframe" in prompts["user"] or "锁住面部表情" in prompts["user"]
    assert "禁止自编" in prompts["system"] or "TTS" in prompts["system"]
    assert "说话，同时" in prompts["system"]
    assert "不微笑" in prompts["system"]
    assert "点动约2厘米" in prompts["system"] or "食指" in prompts["system"]
    assert "与静图一致" in prompts["system"]
    assert "镜头固定" in prompts["system"] or "不推近" in prompts["system"]
    assert "规则拼装" in prompts["system"]
    assert len(prompts["system"]) < 4200


def test_collect_issues_ignores_wrap_prefix_cast_names():
    segments = [
        {
            "segment_index": 1,
            "dialogue": [{"speaker": "妈妈", "text": "行了"}],
            "image_prompt": (
                "基于参考图调整人物动作，保留昭昭：7岁男孩；灿灿：10岁女孩的基本外貌特征。"
                "儿童情绪涂鸦风格，彩铅和蜡笔混合笔触，用力不均的线条，"
                "主观夸张变形，高饱和色彩，涂色出界，"
                "橡皮擦拭痕迹，手工感，孩子气的构图。"
                "客厅里妈妈双手前伸示意停止，面色严肃。"
            ),
        }
    ]
    issues = collect_daily_cast_issues(segments, check_visual_brief=False)
    assert issues == []
