"""日常故事角色入画（发言 ∪ 台词在场）校验。"""

from __future__ import annotations

from app.quality.image_prompt import check_image_prompt
from app.services.daily_story.speaker import (
    allowed_cast_from_dialogue,
    annotate_sticky_stage_speakers,
    collect_speaker_leak_issues,
    leaked_speaker_names_in_text,
    mom_should_stay_offscreen,
    present_cast_from_dialogue,
    scrub_leaked_speaker_names,
    speakers_from_dialogue,
)
from app.services.script.image_prompt import build_image_prompts


def test_speakers_and_leak_detection():
    allowed = speakers_from_dialogue(
        [{"speaker": "昭昭", "text": "a"}, {"speaker": "灿灿", "text": "b"}]
    )
    assert allowed == {"昭昭", "灿灿"}
    assert leaked_speaker_names_in_text("妈妈站在中间，昭昭举手。", allowed) == [
        "妈妈",
    ]
    assert leaked_speaker_names_in_text("昭昭与灿灿对峙。", allowed) == []


def test_present_cast_allows_mom_without_speaking():
    dialogue = [
        {"speaker": "昭昭", "text": "客厅挂钟都九点了，妈妈还躺着刷手机。"},
        {"speaker": "灿灿", "text": "对啊，她手机屏幕亮着，自己也不睡觉。"},
    ]
    assert speakers_from_dialogue(dialogue) == {"昭昭", "灿灿"}
    assert present_cast_from_dialogue(dialogue) == {"妈妈"}
    assert allowed_cast_from_dialogue(dialogue) == {"昭昭", "灿灿", "妈妈"}


def test_present_cast_addressing_mom():
    dialogue = [{"speaker": "昭昭", "text": "妈，你手机屏幕还亮着"}]
    assert "妈妈" in allowed_cast_from_dialogue(dialogue)


def test_sticky_stage_keeps_mom_after_she_appears():
    from app.services.daily_story.speaker import annotate_sticky_stage_speakers

    segments = [
        {
            "segment_index": 1,
            "dialogue": [
                {"speaker": "妈妈", "text": "青菜不能挑食"},
                {"speaker": "昭昭", "text": "那你碗边呢"},
            ],
        },
        {
            "segment_index": 2,
            "dialogue": [
                {"speaker": "灿灿", "text": "那是放凉"},
                {"speaker": "昭昭", "text": "堆那么高？"},
            ],
        },
    ]
    annotate_sticky_stage_speakers(
        segments,
        setting="客厅餐桌前，妈妈正夹青菜给昭昭，自己碗边堆了一小堆菜叶。",
    )
    assert segments[0]["speakers"] == ["昭昭", "灿灿", "妈妈"]
    assert segments[1]["speakers"] == ["昭昭", "灿灿", "妈妈"]


def test_sticky_stage_mom_not_forced_before_entrance():
    from app.services.daily_story.speaker import annotate_sticky_stage_speakers

    segments = [
        {
            "segment_index": 1,
            "dialogue": [
                {"speaker": "昭昭", "text": "这橡皮我的"},
                {"speaker": "灿灿", "text": "我先拿到的"},
            ],
        },
        {
            "segment_index": 2,
            "dialogue": [{"speaker": "妈妈", "text": "你俩过来"}],
        },
    ]
    annotate_sticky_stage_speakers(
        segments,
        setting="客厅，昭昭和灿灿同时抓住一块新橡皮。",
    )
    assert segments[0]["speakers"] == ["昭昭", "灿灿"]
    assert segments[1]["speakers"] == ["昭昭", "灿灿", "妈妈"]


def test_sticky_stage_opening_mom_expands_without_setting():
    """无 setting 重跑拼装时，开场妈妈发言 + 全文三人 → 开场起三人。"""
    from app.services.daily_story.speaker import annotate_sticky_stage_speakers

    segments = [
        {
            "segment_index": 1,
            "dialogue": [
                {"speaker": "妈妈", "text": "青菜不能挑食"},
                {"speaker": "昭昭", "text": "那你碗边呢"},
            ],
        },
        {
            "segment_index": 2,
            "dialogue": [
                {"speaker": "灿灿", "text": "那是放凉"},
                {"speaker": "昭昭", "text": "堆那么高？"},
            ],
        },
    ]
    annotate_sticky_stage_speakers(segments, setting=None)
    assert segments[0]["speakers"] == ["昭昭", "灿灿", "妈妈"]
    assert segments[1]["speakers"] == ["昭昭", "灿灿", "妈妈"]


def test_sticky_stage_hiding_from_mom_breaks_mom_sticky():
    from app.services.daily_story.speaker import annotate_sticky_stage_speakers

    segments = [
        {
            "segment_index": 1,
            "dialogue": [
                {"speaker": "妈妈", "text": "我去阳台收衣服。"},
                {"speaker": "昭昭", "text": "知道了。"},
            ],
        },
        {
            "segment_index": 2,
            "dialogue": [
                {"speaker": "灿灿", "text": "快躲着妈妈，把零食先塞沙发缝里。"},
                {"speaker": "昭昭", "text": "你快挡住门口。"},
            ],
        },
        {
            "segment_index": 3,
            "dialogue": [{"speaker": "妈妈", "text": "你们俩在藏什么？"}],
        },
    ]
    annotate_sticky_stage_speakers(segments, setting="客厅，妈妈刚从门口经过。")
    assert segments[0]["speakers"] == ["昭昭", "灿灿", "妈妈"]
    assert segments[1]["speakers"] == ["昭昭", "灿灿"]
    assert segments[2]["speakers"] == ["昭昭", "灿灿", "妈妈"]


def test_setting_mom_in_other_room_does_not_grant_onstage_cast():
    from app.services.daily_story.speaker import annotate_sticky_stage_speakers

    segments = [
        {
            "segment_index": 1,
            "dialogue": [
                {"speaker": "昭昭", "text": "姐姐，别告诉妈妈。"},
                {"speaker": "灿灿", "text": "你快拿桶。"},
            ],
            "speakers": ["昭昭", "灿灿", "妈妈"],
        },
        {
            "segment_index": 2,
            "dialogue": [{"speaker": "灿灿", "text": "听，妈妈脚步声！"}],
            "speakers": ["昭昭", "灿灿", "妈妈"],
        },
        {
            "segment_index": 3,
            "dialogue": [{"speaker": "妈妈", "text": "你俩，过来！"}],
            "speakers": ["昭昭", "灿灿", "妈妈"],
        },
    ]
    annotate_sticky_stage_speakers(
        segments,
        setting="客厅，地上有碎片，昭昭和灿灿蹲在旁边，妈妈在厨房。",
    )
    assert segments[0]["speakers"] == ["昭昭", "灿灿"]
    assert segments[1]["speakers"] == ["昭昭", "灿灿"]
    assert segments[2]["speakers"] == ["昭昭", "灿灿", "妈妈"]


def test_assemble_layout_does_not_leak_cancan_when_cast_two():
    """vb 写了三人站位但 cast 只有两人时，构图不得带入灿灿。"""
    from app.services.script.image_prompt import assemble_daily_t2i_prompt

    prompt = assemble_daily_t2i_prompt(
        {
            "visual_brief": (
                "客厅餐桌前，画面从左到右是昭昭、妈妈、灿灿。"
                "妈妈指碗，昭昭瞪眼。"
            ),
            "shot_type": "特写",
            "speakers": ["昭昭", "妈妈"],
            "dialogue": [
                {"speaker": "妈妈", "text": "青菜不能挑食"},
                {"speaker": "昭昭", "text": "那你碗边呢"},
            ],
        }
    )
    assert "灿灿" not in prompt
    assert "妈妈" in prompt
    assert "昭昭" in prompt


def test_hearsay_and_where_do_not_allow_mom():
    assert "妈妈" not in allowed_cast_from_dialogue(
        [{"speaker": "昭昭", "text": "妈妈说过别乱跑。"}]
    )
    assert "妈妈" not in allowed_cast_from_dialogue(
        [{"speaker": "昭昭", "text": "妈妈呢？"}]
    )


def test_hide_from_mom_marks_her_offscreen():
    dialogue = [{"speaker": "昭昭", "text": "快点把玩具塞进去，别告诉妈妈。"}]
    assert "妈妈" not in allowed_cast_from_dialogue(dialogue)
    assert mom_should_stay_offscreen(dialogue) is True


def test_hide_from_ma_short_form_marks_her_offscreen():
    """口语「妈」须与「妈妈」同等离场，避免 sticky 误塞三人。"""
    for text in (
        "快擦，千万别让妈看见，用袖子擦。",
        "小声点，吃完把盘子藏好别让妈发现。",
        "别让妈知道。",
    ):
        dialogue = [{"speaker": "灿灿", "text": text}]
        assert "妈妈" not in allowed_cast_from_dialogue(dialogue), text
        assert mom_should_stay_offscreen(dialogue) is True, text


def test_sticky_drops_mom_when_hide_from_ma():
    """前镜妈妈已粘性在场时，本镜「别让妈看见」须打断粘性。"""
    segments = [
        {
            "segment_index": 3,
            "dialogue": [
                {"speaker": "妈妈", "text": "你们小声点。"},
                {"speaker": "昭昭", "text": "知道了。"},
            ],
        },
        {
            "segment_index": 4,
            "dialogue": [
                {"speaker": "昭昭", "text": "奶油滴桌布了！"},
                {"speaker": "灿灿", "text": "快擦，千万别让妈看见。"},
            ],
        },
    ]
    annotate_sticky_stage_speakers(segments, setting="客厅，妈妈刚走过。")
    assert "妈妈" in segments[0]["speakers"]
    assert segments[1]["speakers"] == ["昭昭", "灿灿"]


def test_footsteps_only_do_not_grant_mom_onstage():
    dialogue = [{"speaker": "灿灿", "text": "听，妈妈脚步声！"}]
    assert "妈妈" not in allowed_cast_from_dialogue(dialogue)
    assert mom_should_stay_offscreen(dialogue) is True


def test_scrub_keeps_mom_when_present_in_dialogue():
    dialogue = [
        {"speaker": "昭昭", "text": "妈妈还躺着刷手机。"},
        {"speaker": "灿灿", "text": "她自己也不睡觉。"},
    ]
    allowed = allowed_cast_from_dialogue(dialogue)
    text = (
        "客厅沙发上妈妈躺着刷手机。画面左边是昭昭，右边是灿灿。"
        "昭昭左手指向挂钟。灿灿右手指着妈妈手机。"
    )
    assert scrub_leaked_speaker_names(text, allowed) == text


def test_scrub_leaked_speaker_names_drops_mom_clause():
    text = "昭昭举手比石头。妈妈站在两人中间手臂微张。灿灿双手叉腰。"
    cleaned = scrub_leaked_speaker_names(text, {"昭昭", "灿灿"})
    assert "妈妈" not in cleaned
    assert "昭昭" in cleaned
    assert "灿灿" in cleaned


def test_check_image_prompt_rejects_speaker_leak():
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
    assert report.details["reason"] == "daily speaker leak in image_prompt"


def test_check_image_prompt_allows_present_mom():
    script = {
        "content_style": "daily_story",
        "segments": [
            {
                "segment_index": 1,
                "dialogue": [
                    {
                        "speaker": "昭昭",
                        "text": "客厅挂钟都九点了，妈妈还躺着刷手机。",
                    },
                    {
                        "speaker": "灿灿",
                        "text": "对啊，她手机屏幕亮着，自己也不睡觉。",
                    },
                ],
                "image_prompt": (
                    "客厅沙发上妈妈躺着刷手机，昭昭指向挂钟，灿灿指着手机。"
                    + "x" * 80
                ),
            }
        ],
    }
    report = check_image_prompt(script, content_style="daily_story")
    assert report.details.get("reason") != "daily speaker leak in image_prompt"


def test_check_image_prompt_rejects_hidden_mom_even_if_speakers_polluted():
    script = {
        "content_style": "daily_story",
        "segments": [
            {
                "segment_index": 2,
                "speakers": ["昭昭", "灿灿", "妈妈"],
                "dialogue": [
                    {
                        "speaker": "灿灿",
                        "text": "快躲着妈妈，别让她看见我们在藏零食。",
                    },
                    {"speaker": "昭昭", "text": "你挡住门口。"},
                ],
                "image_prompt": (
                    "客厅里昭昭蹲在沙发边，灿灿回头张望；"
                    "妈妈站在两人面前盯着他们。"
                    + "x" * 80
                ),
            }
        ],
    }
    report = check_image_prompt(script, content_style="daily_story")
    assert report.level == "major"
    assert report.details["reason"] == "daily speaker leak in image_prompt"


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


def test_collect_issues_ignores_wrap_prefix_speaker_names():
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
    issues = collect_speaker_leak_issues(segments, check_visual_brief=False)
    assert issues == []


def test_assemble_injects_mom_look_when_present():
    from app.services.script.image_prompt import assemble_daily_t2i_prompt

    prompt = assemble_daily_t2i_prompt(
        {
            "visual_brief": "客厅沙发上妈妈躺着刷手机，昭昭指向挂钟。",
            "shot_type": "特写",
            "dialogue": [
                {
                    "speaker": "昭昭",
                    "text": "妈妈还躺着刷手机。",
                }
            ],
        }
    )
    assert "妈妈" in prompt
    assert "米色上衣" in prompt


def test_assemble_three_person_layout_from_speakers():
    from app.services.script.image_prompt import assemble_daily_t2i_prompt

    prompt = assemble_daily_t2i_prompt(
        {
            "visual_brief": (
                "客厅餐桌前，画面从左到右是昭昭、妈妈、灿灿。"
                "昭昭叉腰质问，妈妈低头夹菜，灿灿摊手帮腔。"
            ),
            "shot_type": "中景",
            "speakers": ["昭昭", "灿灿", "妈妈"],
            "dialogue": [
                {"speaker": "灿灿", "text": "那是放凉"},
                {"speaker": "昭昭", "text": "堆那么高？"},
            ],
        }
    )
    assert "从左到右是昭昭、妈妈、灿灿" in prompt
    assert "三人同框" in prompt
    assert "米色上衣" in prompt
    assert "妈妈最高" in prompt
