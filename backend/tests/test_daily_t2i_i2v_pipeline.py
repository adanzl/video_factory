"""daily_story 文生图拼装 + 关键帧 motion + TTS 时间注入 链路校验。"""

from __future__ import annotations

from app.services.media.media_mgr import _inject_mouth_motion
from app.services.script.image_prompt import (
    assemble_daily_image_prompts,
    assemble_daily_t2i_prompt,
    build_image_prompts,
)
from app.services.segment.clip.video_agnes import _stabilize_motion_prompt
from app.utils.job_info import apply_keyframe_video_providers, is_keyframe_segment


def test_assemble_daily_t2i_prompt_structure():
    seg = {
        "segment_index": 1,
        "shot_type": "特写",
        "visual_brief": (
            "客厅沙发上，灿灿手指着皱衣服瞪圆眼张嘴；"
            "昭昭双手摊开耸肩撇嘴。茶几上有空水杯和蜡笔。"
        ),
        "dialogue": [
            {"speaker": "灿灿", "text": "你怎么又乱扔！"},
            {"speaker": "昭昭", "text": "我没有啊。"},
        ],
    }
    prompt = assemble_daily_t2i_prompt(seg)
    assert prompt.startswith("儿童情绪涂鸦风格")
    assert "灿灿：10岁女孩" in prompt
    assert "昭昭：7岁男孩" in prompt
    assert "昭昭比灿灿矮约半个头" in prompt
    assert "窗光从一侧斜照" in prompt
    assert "中近景特写" in prompt
    assert "蜡笔" in prompt


def test_build_image_prompts_daily_motion_modes_and_duration():
    segs = [
        {
            "segment_index": 1,
            "shot_type": "特写",
            "visual_brief": "客厅沙发上姐弟对峙，茶几有蜡笔。",
            "dialogue": [
                {"speaker": "灿灿", "text": "你怎么又乱扔！"},
                {"speaker": "昭昭", "text": "我没有啊。"},
            ],
            "duration_sec": 2.5,
        },
        {
            "segment_index": 2,
            "shot_type": "中景",
            "visual_brief": "客厅中景灿灿叉腰，沙发靠垫可见。",
            "dialogue": [{"speaker": "灿灿", "text": "哼！"}],
            "duration_sec": 1.2,
        },
    ]
    apply_keyframe_video_providers(segs)
    assert is_keyframe_segment(segs[0])
    assert not is_keyframe_segment(segs[1])
    assemble_daily_image_prompts(segs)
    script = {
        "title": "乱扔衣服",
        "visual_style": "儿童情绪涂鸦",
        "content_style": "daily_story",
        "segments": segs,
    }
    prompts = build_image_prompts(
        script,
        content_style="daily_story",
        job={"pipeline": "chat", "content_style": "daily_story"},
    )
    assert "仅为每段编写 motion_prompt" in prompts["user"]
    assert "不要输出 image_prompt" in prompts["user"]
    assert "motion_mode=keyframe" in prompts["user"]
    assert "motion_mode=ambient" in prompts["user"]
    assert "duration_sec=2.5" in prompts["user"]
    assert "禁止自编" in prompts["system"]
    assert "说话，同时" in prompts["system"]
    assert "image_prompt=" in prompts["user"]


def test_inject_mouth_motion_overwrites_llm_times_from_cues():
    seg = {
        "dialogue": [
            {"speaker": "灿灿", "text": "你怎么又乱扔！"},
            {"speaker": "昭昭", "text": "我没有啊。"},
        ],
    }
    mp = (
        "画面左边是灿灿，右边是昭昭。"
        "0.0-1.0秒灿灿说话，同时右手食指微微向下点动约2厘米后停止；"
        "1.0-2.0秒昭昭说话，同时肩膀轻轻耸起约3厘米后定格。"
        "两人说话后面部表情恢复与静图一致："
        "灿灿瞪圆眼睛嘴巴大张（惊讶质问状），不微笑；"
        "昭昭撇着嘴角耸肩（无辜状），表情不变。"
        "服装发型稳定，身高比例（昭昭比灿灿矮半个头）不变。"
        "镜头固定，不推近不拉远，画面只有人物和场景，无任何文字叠加。"
    )
    cues = [("你怎么又乱扔！", 1.4), ("我没有啊。", 1.1)]
    out = _inject_mouth_motion(mp, seg, cues)
    assert "0.0-1.4秒灿灿说话，同时" in out
    assert "1.4-2.5秒昭昭说话，同时" in out
    assert "0.0-1.0秒" not in out
    assert "1.0-2.0秒" not in out


def test_inject_mouth_motion_adds_times_when_missing():
    seg = {
        "dialogue": [
            {"speaker": "灿灿", "text": "你怎么又乱扔！"},
            {"speaker": "昭昭", "text": "我没有啊。"},
        ],
    }
    mp = (
        "画面左边是灿灿，右边是昭昭。"
        "灿灿说话，同时右手点动约2厘米后停止；"
        "昭昭说话，同时耸肩约3厘米后定格。"
        "镜头固定，不推近不拉远。"
    )
    cues = [("你怎么又乱扔！", 1.4), ("我没有啊。", 1.1)]
    out = _inject_mouth_motion(mp, seg, cues)
    assert "0.0-1.4秒灿灿说话，同时" in out
    assert "1.4-2.5秒昭昭说话，同时" in out


def test_inject_mouth_motion_noop_for_ambient():
    seg = {"dialogue": [{"speaker": "灿灿", "text": "哼！"}]}
    amb = "窗边纱帘被风轻轻掀起，人物姿势保持不变。"
    assert _inject_mouth_motion(amb, seg, [("哼！", 1.0)]) == amb


def test_stabilize_keeps_timeline_ranges():
    mp = (
        "画面左边是灿灿，右边是昭昭。"
        "0.0-1.4秒灿灿说话，同时右手食指微微向下点动约2厘米后停止；"
        "1.4-2.5秒昭昭说话，同时肩膀轻轻耸起约3厘米后定格。"
        "两人说话后面部表情恢复与静图一致："
        "灿灿瞪圆眼睛嘴巴大张（惊讶质问状），不微笑；"
        "昭昭撇着嘴角耸肩（无辜状），表情不变。"
        "服装发型稳定，身高比例（昭昭比灿灿矮半个头）不变。"
        "镜头固定，不推近不拉远，画面只有人物和场景，无任何文字叠加。"
    )
    out = _stabilize_motion_prompt(mp)
    assert "0.0-1.4秒灿灿说话，同时" in out
    assert "1.4-2.5秒昭昭说话，同时" in out
    assert "镜头固定" in out


def test_scrub_daily_visual_brief_strips_labels_and_outfit_props():
    from app.services.script.visual_brief import scrub_daily_visual_brief

    raw = (
        "客厅沙发上，灿灿刚叠好的一堆衣服（粉色卫衣、蓝色T恤等）堆在沙发左侧，"
        "其中一件蓝色T恤被揉得皱成一团。灿灿站在沙发前叉腰瞪眼。"
        "冲突道具：那件皱成一团的蓝色T恤清晰可见。"
    )
    cleaned = scrub_daily_visual_brief(raw)
    assert "冲突道具" not in cleaned
    assert "粉色卫衣" not in cleaned
    assert "蓝色T恤" not in cleaned
    assert "衣服" in cleaned
    assert "叉腰瞪眼" in cleaned
