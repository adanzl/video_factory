"""口播提示词字数预算测试。"""

from __future__ import annotations

import pytest

from app.services.script.image_prompt import build_image_prompts
from app.services.script.visual_brief import build_visual_brief_prompts
from app.services.script.voiceover_standard import (
    build_voiceover_standard_expand_prompts,
)
from app.services.script.compose import collect_prompts
from app.utils.media import (
    narration_accept_min_chars,
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

def test_build_image_prompts_door_single_leaf_rule():
    """文生图含门时须写明单扇门与门外景象，防止跨镜穿帮。"""
    for style in ("science_child", "life_experience", "history_mystery"):
        prompts = build_image_prompts(
            _minimal_image_script(),
            content_style=style,
            job={"pipeline": "standard", "content_style": style},
        )
        assert "一扇单开门" in prompts["system"]
        assert "一块完整门板" in prompts["system"]
        assert "门外是柔和的白色亮光" in prompts["system"]
        # 纯正面表述：图像模型会把否定词当生成指令
        assert "没有分成" not in prompts["system"]
        assert "双开门/对开门" not in prompts["system"]

def test_wrap_image_prompts_daily_assembles_from_visual_brief():
    from app.services.script.image_prompt import wrap_image_prompts

    segments = [
        {
            "segment_index": 1,
            "visual_brief": (
                "客厅地板上昭昭右手高举橡皮，瞪圆眼；灿灿左手前伸争辩。"
            ),
            "dialogue": [
                {"speaker": "昭昭", "text": "我的！"},
                {"speaker": "灿灿", "text": "还我！"},
            ],
            "shot_type": "特写",
        }
    ]
    wrap_image_prompts(segments, content_style="daily_story")
    prompt = segments[0]["image_prompt"]
    assert prompt.startswith("基于参考图调整人物动作")
    assert "保持参考图外貌" in prompt
    assert "儿童涂鸦蜡笔画风格" in prompt
    assert "绝不允许" not in prompt
    assert "禁用" not in prompt
    assert "平涂光照" in prompt
    assert "窗光从一侧斜照" not in prompt
    assert "与参考图同质" in prompt
    assert "中近景特写" in prompt
    assert "橡皮" in prompt
    assert "昭昭：7岁男孩" not in prompt

def test_wrap_image_prompts_passes_setting_for_sticky_cast():
    from app.services.script.image_prompt import wrap_image_prompts

    segments = [
        {
            "segment_index": 1,
            "visual_brief": (
                "客厅餐桌前，画面从左到右是昭昭、妈妈、灿灿。"
                "妈妈指碗，昭昭瞪眼，灿灿托腮旁听。"
            ),
            "dialogue": [
                {"speaker": "妈妈", "text": "青菜不能挑食"},
                {"speaker": "昭昭", "text": "那你碗边呢"},
            ],
            "shot_type": "特写",
        },
        {
            "segment_index": 2,
            "visual_brief": "灿灿摊手，昭昭叉腰，妈妈在场。",
            "dialogue": [
                {"speaker": "灿灿", "text": "那是放凉"},
                {"speaker": "昭昭", "text": "堆那么高？"},
            ],
            "shot_type": "中景",
        },
    ]
    wrap_image_prompts(
        segments,
        content_style="daily_story",
        setting="客厅餐桌前，妈妈正夹青菜给昭昭，自己碗边堆了一小堆菜叶。",
        segment_indices=[1],
    )
    assert segments[0]["speakers"] == ["昭昭", "灿灿", "妈妈"]
    assert "灿灿" in segments[0]["image_prompt"]
    assert "三人" in segments[0]["image_prompt"]

def test_assemble_daily_t2i_prompt_only_speakers():
    from app.services.script.image_prompt import assemble_daily_t2i_prompt

    prompt = assemble_daily_t2i_prompt(
        {
            "visual_brief": "厨房里灿灿叉腰瞪眼。",
            "dialogue": [{"speaker": "灿灿", "text": "不许动！"}],
            "shot_type": "中景",
        }
    )
    assert "灿灿：10岁女孩" in prompt
    assert "昭昭" not in prompt
    assert "妈妈" not in prompt
    assert "中景，人物全身" in prompt

def test_assemble_daily_t2i_prompt_door_and_hair_locks():
    """拼装层硬锁：门必须单扇、风吹头发必须连头皮，不依赖 LLM 照写。"""
    from app.services.script.image_prompt import assemble_daily_t2i_prompt

    prompt = assemble_daily_t2i_prompt(
        {
            "visual_brief": (
                "客厅门边，门半掩着，门缝被风吹得更开，风将灿灿的马尾吹起。"
                "画面左边是昭昭，右边是灿灿。"
            ),
            "dialogue": [
                {"speaker": "灿灿", "text": "你搭着门，门缝却越开越大"},
                {"speaker": "昭昭", "text": "风把头发吹乱了！"},
            ],
            "shot_type": "中景",
        }
    )
    assert "画面中的门是一扇单开门，一块完整门板" in prompt
    assert "门缝" not in prompt
    assert "门与门框的空隙" in prompt
    assert "发丝连着头皮" in prompt
    assert "风从门口吹向室内，头发顺风飘离门口" in prompt

def test_assemble_daily_t2i_prompt_skips_locks_when_absent():
    """无门/无风时拼装层不注入多余硬锁。"""
    from app.services.script.image_prompt import assemble_daily_t2i_prompt

    prompt = assemble_daily_t2i_prompt(
        {
            "visual_brief": "厨房里灿灿叉腰瞪眼。",
            "dialogue": [{"speaker": "灿灿", "text": "不许动！"}],
            "shot_type": "中景",
        }
    )
    assert "一扇单开门" not in prompt
    assert "发丝连着头皮" not in prompt

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
    assert "妈妈可入画" in prompts["system"] or "妈妈" in prompts["system"]
    assert "不要为了让妈妈入画而改写" in prompts["system"] or "不算在场" in prompts["system"]
    assert "dialogue=" in prompts["user"]
    assert "昭昭:" in prompts["user"]
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
                "shot_type": "特写",
            },
        ],
    }
    prompts = build_visual_brief_prompts(
        script,
        job={"pipeline": "chat", "content_style": "daily_story"},
    )
    assert "日常亲子对话短剧的分镜画面设计师" in prompts["system"]
    assert "小朋友讲科普" not in prompts["system"]
    assert "可入画" in prompts["system"]
    assert "台词写明" in prompts["system"] or "当场在场" in prompts["system"]
    assert "粘性" in prompts["system"] or "speakers" in prompts["system"]
    assert "三人同框" in prompts["system"] or "从左到右" in prompts["system"]
    assert "dialogue=" in prompts["user"]
    assert "visual_subjects" in prompts["system"]
    assert "object_states" in prompts["system"]
    assert "【开场】" in prompts["system"]
    assert "冲突峰值" in prompts["system"]
    assert "物品锁定" in prompts["system"] or "物品锁定" in prompts["user"]
    assert "粉色卫衣" in prompts["system"]
    assert "人物关系" in prompts["system"]
    assert "单扇门" in prompts["system"]
    assert "一扇单开门" in prompts["system"]
    assert "柔和的白色亮光" in prompts["system"]
    assert "门板边缘与门框之间露出一道空隙" in prompts["system"]
    assert "禁止写「门缝」" in prompts["system"]
    assert "站位" in prompts["system"]
    assert "画面左边是" in prompts["system"]
    assert "刚叠好" in prompts["system"]
    assert "台词点名" in prompts["system"] or "台词已出现" in prompts["system"]

def test_build_visual_brief_daily_wind_blows_speaker_hair():
    """风吹头发须落在台词对应的角色头上，正向表述且发丝连头皮。"""
    script = {
        "title": "关门关到门更开",
        "narration": "风把头发吹乱了！",
        "visual_style": "日常写实",
        "segments": [
            {
                "segment_index": 6,
                "text": "你搭着门，门缝却越开越大。风把头发吹乱了！",
                "dialogue": [
                    {"speaker": "灿灿", "text": "你搭着门，门缝却越开越大"},
                    {
                        "speaker": "昭昭",
                        "text": "风把头发吹乱了！我不敢使劲，你说轻点我就轻到底。",
                    },
                ],
                "shot_type": "中景",
            },
        ],
    }
    prompts = build_visual_brief_prompts(
        script,
        job={"pipeline": "chat", "content_style": "daily_story"},
    )
    assert "【风与头发】" in prompts["system"]
    assert "风只吹本镜在场角色的头发" in prompts["system"]
    assert "谁说头发被风吹乱，风就吹谁的头发" in prompts["system"]
    assert "台词未提头发时" in prompts["system"]
    assert "门外的风吹起昭昭的黑色短发" in prompts["system"]
    assert "背离门口" in prompts["system"]
    assert "发丝必须连着头皮" in prompts["system"]
    assert "马尾被吹起" in prompts["system"]
    assert "碎发乱飞" in prompts["system"]
    assert "单扇门" in prompts["system"]

def test_build_visual_brief_daily_includes_setting_anchor():
    from app.services.script.visual_brief import build_visual_brief_prompts

    script = {
        "title": "新橡皮归谁",
        "setting": "客厅，昭昭和灿灿同时抓住一块新橡皮。",
        "narration": "昭昭：我先拿到的！",
        "visual_style": "日常写实",
        "segments": [
            {
                "segment_index": 1,
                "text": "昭昭：我先拿到的！",
                "dialogue": [{"speaker": "昭昭", "text": "我先拿到的！"}],
            },
        ],
    }
    prompts = build_visual_brief_prompts(
        script,
        job={"pipeline": "chat", "content_style": "daily_story"},
    )
    assert "全片地点 setting：客厅" in prompts["user"]
    assert "地点锚点" in prompts["system"]
    assert "地点与 setting 一致" in prompts["system"]

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
    assert "≤10 秒" in system
    assert str(int(10 * 4.0)) in system  # max chars = 40
    assert "20" in system  # min chars floor
    assert "倾向 2 句" in system
    assert "优先每镜 2 句" in system
    assert "倾向每镜 2 句" in user
    assert "特写对白上限" in system
    assert "特写镜硬性不得超过 2 句" in user
    assert "彩铅" not in system
    assert "超短发" not in system
    assert "不要输出 visual_description" in system
    assert "转折用特写，不拆碎" in system
    assert "特写数量·硬性" in system
    assert "实际切出的镜数" in system
    assert "⌈N/2⌉" in system
    assert "半数进一" in system or "进一" in system
    assert "开场首镜" in system
    assert "禁止一句一镜" in user
    assert "特写数量·硬性" in user
    assert "不得丢句" in user
    assert "【标题】争酸奶" in user
    assert "【场景设定】厨房，傍晚" in user
    assert "昭昭：这瓶是我的！" in user
    # 上限口径：不得超过 max_chars
    assert "不得超过 40 字" in system

def test_validate_daily_script_scenes_closeup_max_two_lines():
    from app.services.daily_story.prompts import validate_daily_script_scenes

    ok = [
        {"scene_id": 1, "shot_type": "特写", "dialogue": [{}, {}]},
        {"scene_id": 2, "shot_type": "中景", "dialogue": [{}, {}, {}]},
        {"scene_id": 3, "shot_type": "特写", "dialogue": [{}, {}]},
    ]
    assert validate_daily_script_scenes(ok) == []

    bad = [
        {"scene_id": 8, "shot_type": "特写", "dialogue": [{}, {}, {}]},
        {"scene_id": 9, "shot_type": "特写", "dialogue": [{}, {}]},
    ]
    errs = validate_daily_script_scenes(bad)
    assert any("scene_id=8" in e and "3 句" in e for e in errs)

def test_enforce_daily_script_closeups_demotes_overfull():
    from app.services.daily_story.prompts import (
        enforce_daily_script_closeups,
        validate_daily_script_scenes,
    )

    scenes = [
        {"scene_id": 1, "shot_type": "特写", "dialogue": [{}, {}]},
        {"scene_id": 2, "shot_type": "中景", "dialogue": [{}, {}]},
        {"scene_id": 3, "shot_type": "中景", "dialogue": [{}, {}]},
        {
            "scene_id": 10,
            "shot_type": "特写",
            "dialogue": [
                {"speaker": "昭昭", "text": "a"},
                {"speaker": "灿灿", "text": "b"},
                {"speaker": "昭昭", "text": "c"},
            ],
        },
    ]
    notes = enforce_daily_script_closeups(scenes)
    assert any("demoted" in n and "scene_id=10" in n for n in notes)
    assert scenes[3]["shot_type"] == "中景"
    assert validate_daily_script_scenes(scenes) == []

def test_daily_script_closeup_bounds_and_enforce():
    from app.services.daily_story.prompts import (
        daily_script_closeup_bounds,
        enforce_daily_script_closeups,
        validate_daily_script_closeup_count,
    )

    assert daily_script_closeup_bounds(11) == (6, 6)  # ⌈11/2⌉
    assert daily_script_closeup_bounds(8) == (4, 4)
    assert daily_script_closeup_bounds(9) == (5, 5)
    assert daily_script_closeup_bounds(7) == (4, 4)

    scenes = [
        {"scene_id": 1, "shot_type": "特写", "dialogue": [{}, {}]},
        *[
            {"scene_id": i, "shot_type": "中景", "dialogue": [{}, {}]}
            for i in range(2, 11)
        ],
        {
            "scene_id": 11,
            "shot_type": "中景",
            "dialogue": [
                {"speaker": "妈妈", "text": "你俩在干什么？！"},
                {"speaker": "昭昭", "text": "完蛋了！"},
            ],
        },
    ]
    notes = enforce_daily_script_closeups(scenes)
    assert validate_daily_script_closeup_count(scenes) == []
    closeups = [s["scene_id"] for s in scenes if s.get("shot_type") == "特写"]
    assert len(closeups) == 6
    assert 1 in closeups
    assert 11 in closeups
    assert notes


def test_enforce_daily_script_closeups_demotes_over_half():
    from app.services.daily_story.prompts import (
        enforce_daily_script_closeups,
        validate_daily_script_closeup_count,
    )

    scenes = [
        {"scene_id": i, "shot_type": "特写", "dialogue": [{}, {}]}
        for i in range(1, 5)
    ]
    notes = enforce_daily_script_closeups(scenes)
    closeups = [s["scene_id"] for s in scenes if s.get("shot_type") == "特写"]
    assert len(closeups) == 2  # ⌈4/2⌉
    assert 1 in closeups
    assert any("over" in n for n in notes)
    assert validate_daily_script_closeup_count(scenes) == []

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
