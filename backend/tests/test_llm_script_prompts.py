"""口播提示词字数预算测试。"""

from __future__ import annotations

import pytest

from app.services.script.image_prompt import build_image_prompts
from app.services.script.visual_brief import build_visual_brief_prompts
from app.services.script.voiceover_standard import (
    build_voiceover_standard_expand_prompts,
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


def _minimal_image_script() -> dict:
    return {
        "title": "测试",
        "visual_style": "画风",
        "segments": [
            {
                "segment_index": 1,
                "text": "口播",
                "visual_brief": "画面",
            },
        ],
    }


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
    assert "禁止写人物或任何有生命主体的动作" in prompts["user"]
    assert "禁止写人物或任何有生命主体的动作" in prompts["system"]
    assert "炉口青烟缓缓上升" in prompts["system"]
    assert "不修改、不替换 visual_style" in prompts["system"]
    assert "非绘本水彩" in prompts["system"]
    assert "明快蓝橙主色调" not in prompts["system"]
    assert "3D卡通科普" in prompts["user"]


def test_build_image_prompts_life_keeps_no_spoil_ahead():
    prompts = build_image_prompts(
        _minimal_image_script(),
        content_style="life_experience",
        job={"pipeline": "standard", "content_style": "life_experience"},
    )
    assert "禁提前画后续段落" in prompts["system"]
    assert "禁可读大段文字/水印/品牌Logo" in prompts["system"]


def test_build_image_prompts_sd15_keeps_style_body():
    """SD15 附加英文规则，不替换风格正文。"""
    prompts = build_image_prompts(
        _minimal_image_script(),
        content_style="science_child",
        include_sd15_prompt=True,
        job={"pipeline": "standard", "content_style": "science_child"},
    )
    assert "非绘本水彩" in prompts["system"]
    assert "不修改、不替换 visual_style" in prompts["system"]
    assert "sd15_prompt_en" in prompts["system"]
    assert "实际 SD1.5 出图以 sd15_prompt_en 为准" in prompts["system"]


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


def test_build_image_prompts_role_matches_content_style():
    script = _minimal_image_script()
    expected = {
        "history_mystery": "历史悬案视频文生图",
        "science_child": "童趣科普视频文生图",
        "tech_science": "科技/产业科普视频文生图",
        "life_experience": "生活避坑/经验类视频文生图",
        "daily_story": "儿童日常故事视频文生图",
    }
    for style, role_snip in expected.items():
        prompts = build_image_prompts(
            script,
            content_style=style,
            job={"pipeline": "standard", "content_style": style},
        )
        assert role_snip in prompts["system"]
        assert "你是科普视频文生图" not in prompts["system"]


def test_build_image_prompts_orientation_label_unified():
    """各风格横竖屏只差 orientation 标签，文案格式统一。"""
    script = _minimal_image_script()
    for style, marker in [
        ("science_child", "非绘本水彩"),
        ("tech_science", "不修改、不替换 visual_style"),
        ("life_experience", "禁可读大段文字/水印/品牌Logo"),
        ("history_mystery", "禁止卡通/绘本/扁平插画风"),
        ("daily_story", "出图前系统硬编码"),
    ]:
        portrait = build_image_prompts(
            script,
            orientation="portrait",
            content_style=style,
            job={"pipeline": "standard", "content_style": style},
        )
        landscape = build_image_prompts(
            script,
            orientation="landscape",
            content_style=style,
            job={"pipeline": "standard", "content_style": style},
        )
        assert marker in portrait["system"]
        assert "适配9:16竖屏构图" in portrait["system"]
        assert "适配16:9横屏构图" in landscape["system"]
        assert "适配9:16竖屏构图" not in landscape["system"]
        assert "适配16:9横屏构图" not in portrait["system"]
        # 画风细节不在 system 硬编码，由 user 的 visual_style 提供
        assert "明快蓝橙主色调" not in portrait["system"]
        assert "电影级写实科技视觉" not in portrait["system"]


def test_wrap_image_prompts_daily_hardcodes_style():
    from app.services.script.image_prompt import wrap_image_prompts

    segments = [{"image_prompt": "客厅里对峙。"}]
    wrap_image_prompts(segments, content_style="daily_story")
    prompt = segments[0]["image_prompt"]
    assert prompt.startswith("基于参考图调整人物动作")
    assert "昭昭" in prompt
    assert "儿童情绪涂鸦风格" in prompt
    assert prompt.endswith("客厅里对峙。")


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
    assert "全片 visual_style：测试画风" in prompts["user"]
    assert "请为每一段生成 visual_brief" in prompts["user"]
    assert "须按标记生成" not in prompts["user"]
    assert "画面衔接自然" in prompts["system"] or "连贯" in prompts["system"]
    assert "不要输出或修改各段 text" in prompts["system"]
    assert "焦距" in prompts["system"]
    assert "妈妈" not in prompts["system"]
    assert "勿夸张表演" in prompts["system"]


def test_build_visual_brief_prompts_omits_empty_visual_style():
    script = {
        "title": "测试标题",
        "narration": "一句口播。",
        "segments": [
            {"segment_index": 1, "text": "一句口播。"},
        ],
    }
    prompts = build_visual_brief_prompts(
        script,
        job={"pipeline": "standard", "content_style": "science_child"},
    )
    assert "visual_style" not in prompts["user"]
    assert "待你输出" not in prompts["user"]


def test_build_visual_brief_prompts_partial_segments_only():
    script = {
        "title": "测试标题",
        "narration": "第一段。第二段。第三段。",
        "visual_style": "测试画风",
        "segments": [
            {"segment_index": 1, "text": "第一段。"},
            {"segment_index": 2, "text": "第二段。"},
            {"segment_index": 3, "text": "第三段。"},
        ],
    }
    prompts = build_visual_brief_prompts(
        script,
        job={"pipeline": "standard", "content_style": "science_child"},
        segment_indices=[2],
    )
    assert "【需生成】segment 2:" in prompts["user"]
    assert "【仅上下文】segment 1:" in prompts["user"]
    assert "【仅上下文】segment 3:" in prompts["user"]
    assert "仅【需生成】段输出 visual_brief" in prompts["user"]
    assert "仅需输出标记为【需生成】" in prompts["system"]
    assert "须与输入逐段一一对应" not in prompts["system"]


def test_build_visual_brief_prompts_life_without_dialogue_skips_mom():
    script = {
        "title": "测试标题",
        "narration": "带娃出门先看好书包。",
        "visual_style": "生活写实",
        "segments": [
            {"segment_index": 1, "text": "带娃出门先看好书包。"},
        ],
    }
    prompts = build_visual_brief_prompts(
        script,
        job={"pipeline": "chat", "content_style": "life_experience"},
    )
    assert "妈妈" not in prompts["system"]
    assert "speakers=" not in prompts["user"]
    assert "勿夸张表演" in prompts["system"]


def test_build_visual_brief_prompts_dialogue_keeps_mom_rule():
    script = {
        "title": "测试标题",
        "narration": "妈妈说过别乱跑。",
        "visual_style": "生活写实",
        "segments": [
            {
                "segment_index": 1,
                "text": "妈妈说过别乱跑。",
                "dialogue": [{"speaker": "昭昭", "text": "妈妈说过别乱跑。"}],
            },
        ],
    }
    prompts = build_visual_brief_prompts(
        script,
        job={"pipeline": "chat", "content_style": "life_experience"},
        supplementary_info="补充：厨房场景",
    )
    assert "妈妈角色" in prompts["system"]
    assert "speakers=" in prompts["user"]
    assert "融入画面描述" in prompts["system"]
    assert "融入口播内容" not in prompts["system"]
    assert "融入画面描述" in prompts["user"]


def test_build_visual_brief_prompts_daily_story_role_and_cast():
    script = {
        "title": "测试标题",
        "narration": "昭昭：妈妈呢？",
        "visual_style": "日常写实",
        "segments": [
            {
                "segment_index": 1,
                "text": "昭昭：妈妈呢？",
                "dialogue": [{"speaker": "昭昭", "text": "妈妈呢？"}],
            },
        ],
    }
    prompts = build_visual_brief_prompts(
        script,
        job={"pipeline": "chat", "content_style": "daily_story"},
    )
    assert "日常亲子对话短剧的分镜画面设计师" in prompts["system"]
    assert "小朋友讲科普" not in prompts["system"]
    assert "本段画面人物必须" in prompts["system"]
    assert "speakers=" in prompts["user"]
    assert "80-150" in prompts["system"]


def test_build_daily_script_prompts_uses_cps_setting_and_no_appearance():
    from app.services.daily_story.prompts import build_daily_script_prompts

    story = {
        "scene_title": "争酸奶",
        "setting": "厨房，傍晚",
        "dialogue": [
            {"speaker": "昭昭", "line": "这瓶是我的！"},
            {"speaker": "灿灿", "line": "我先看到的。"},
        ],
    }
    system, user = build_daily_script_prompts(story, chars_per_sec=4.0)
    assert "语速 4 字/秒" in system
    assert "18.0" not in system
    assert "≤18 秒" in system
    assert str(int(18 * 4.0)) in system  # max chars = 72
    assert "彩铅" not in system
    assert "超短发" not in system
    assert "不要输出 visual_description" in system
    assert "情绪单独成镜" in system
    assert "特写" in user
    assert "【标题】争酸奶" in user
    assert "【场景设定】厨房，傍晚" in user
    assert "昭昭：这瓶是我的！" in user
    # 规则 2/3 合并后字数上限只强调一次主口径
    assert system.count("≤72 字") == 1


def test_build_visual_brief_prompts_includes_shot_type():
    script = {
        "title": "测试",
        "narration": "hi",
        "visual_style": "日常",
        "segments": [
            {
                "segment_index": 1,
                "text": "hi",
                "shot_type": "中景",
                "dialogue": [{"speaker": "昭昭", "text": "hi"}],
            },
        ],
    }
    prompts = build_visual_brief_prompts(
        script,
        job={"pipeline": "chat", "content_style": "daily_story"},
    )
    assert "shot_type='中景'" in prompts["user"]


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


def test_voiceover_standard_expand_narration_only_injects_style():
    script = {
        "title": "测试",
        "narration": "短稿" * 20,
        "word_count": 40,
    }
    prompts = build_voiceover_standard_expand_prompts(
        script,
        min_chars=200,
        mode="narration_only",
        max_chars=280,
        job={"content_style": "tech_science"},
    )
    assert "narration口吻" in prompts["system"]
    assert "勿超过 280 字" in prompts["system"]
    assert "不要输出 segments" in prompts["system"]


def test_voiceover_standard_expand_rejects_storyboard_mode():
    with pytest.raises(ValueError, match="unsupported expand mode"):
        build_voiceover_standard_expand_prompts(
            {"narration": "x"},
            min_chars=100,
            mode="storyboard",
        )


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
