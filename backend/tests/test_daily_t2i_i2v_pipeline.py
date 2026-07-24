"""daily_story 文生图拼装 + 关键帧 motion + TTS 时间注入 链路校验。"""

from __future__ import annotations

import re

from app.services.media.media_mgr import (
    _inject_mouth_motion,
    inject_speaking_times_into_motion_prompts,
)
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
    # 对白先发言者在左（灿灿），勿固定昭昭在左
    assert "粉卫衣马尾女孩灿灿" in prompt
    assert "蓝T恤短发男孩昭昭" in prompt
    assert "禁止左右对调" in prompt
    assert "画面左边是灿灿，右边是昭昭" in prompt
    assert "占左半" in prompt and "占右半" in prompt
    assert "蜡笔" in prompt


def test_strip_verify_regen_leak():
    from app.services.script.image_prompt import strip_verify_regen_leak

    clean = "客厅沙发旁，灿灿指着脏衣篮。"
    dirty = (
        clean
        + "出图质检连续未通过（发型/人数/肢体/场景/妈妈是否成年等），"
        + "请改写本段 image_prompt：换姿势与构图。"
    )
    assert strip_verify_regen_leak(dirty) == clean
    assert strip_verify_regen_leak(clean) == clean


def test_assemble_daily_layout_from_visual_brief():
    """visual_brief 明示左右时，构图跟 brief，不对白序。"""
    seg = {
        "shot_type": "中景",
        "visual_brief": (
            "客厅沙发上，画面左边是昭昭，右边是灿灿；"
            "昭昭摊手耸肩，灿灿叉腰瞪眼。"
        ),
        "dialogue": [
            {"speaker": "灿灿", "text": "你怎么又乱扔！"},
            {"speaker": "昭昭", "text": "我没有啊。"},
        ],
    }
    prompt = assemble_daily_t2i_prompt(seg)
    assert "蓝T恤短发男孩昭昭" in prompt
    assert "粉卫衣马尾女孩灿灿" in prompt
    assert "禁止左右对调" in prompt
    assert "画面左边是昭昭，右边是灿灿" in prompt


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
    assert "0.0-1.4秒左侧女孩张嘴说话，同时" in out
    assert "1.4-2.5秒右侧男孩张嘴说话，同时" in out
    assert "此时右侧男孩闭嘴" in out
    assert "此时左侧女孩闭嘴" in out
    assert "0.0-1.0秒" not in out
    assert "1.0-2.0秒" not in out
    assert "画面左边灿灿" not in out


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
    assert "0.0-1.4秒左侧女孩张嘴说话，同时" in out
    assert "1.4-2.5秒右侧男孩张嘴说话，同时" in out
    assert "此时右侧男孩闭嘴" in out


def test_inject_mouth_motion_zeros_min_start():
    """前导无 speaker 把起点推高时，最小值归零再全体平移。"""
    seg = {
        "dialogue": [
            {"speaker": "", "text": "（静音）"},
            {"speaker": "灿灿", "text": "你怎么又乱扔！"},
            {"speaker": "昭昭", "text": "我没有啊。"},
        ],
    }
    mp = (
        "画面左边是昭昭，右边是灿灿。"
        "昭昭说话，同时右手食指向前戳动约3厘米后收回；"
        "灿灿说话，同时双手在胸前轻轻摆动约2次后停止。"
    )
    cues = [("（静音）", 3.3), ("你怎么又乱扔！", 4.0), ("我没有啊。", 3.4)]
    out = _inject_mouth_motion(mp, seg, cues)
    # 按站位+身份标注，对白序仍跟 dialogue
    assert "0.0-4.0秒右侧女孩张嘴说话，同时" in out
    assert "4.0-7.4秒左侧男孩张嘴说话，同时" in out
    assert "3.3-" not in out
    assert "7.3-" not in out


def test_inject_mouth_motion_noop_for_ambient():
    seg = {"dialogue": [{"speaker": "灿灿", "text": "哼！"}]}
    amb = "窗边纱帘被风轻轻掀起，人物姿势保持不变。"
    assert _inject_mouth_motion(amb, seg, [("哼！", 1.0)]) == amb


def test_inject_mouth_motion_without_face_mark_tail():
    """无「两人说话后面部表情」时仍可注入，尾部锁定句保留。"""
    seg = {
        "dialogue": [
            {"speaker": "灿灿", "text": "a"},
            {"speaker": "昭昭", "text": "b"},
        ],
    }
    mp = (
        "画面左边是灿灿，右边是昭昭。"
        "灿灿说话，同时右手点动约2厘米后停止；"
        "昭昭说话，同时耸肩约3厘米后停止。"
        "镜头固定，不推近不拉远，画面只有人物和场景，无任何文字叠加。"
    )
    out = _inject_mouth_motion(mp, seg, [("a", 1.0), ("b", 1.5)])
    assert "左侧女孩张嘴说话" in out
    assert "后定格" in out
    assert "两人说话后面部表情" not in out
    assert "镜头固定" in out


def test_inject_mouth_motion_three_lines_same_speaker_twice():
    """三句对白（灿灿→昭昭→灿灿）须写出三段时间，不能漏首句。"""
    seg = {
        "dialogue": [
            {"speaker": "灿灿", "text": "对，意思是别碰。"},
            {"speaker": "昭昭", "text": "那你现在弄乱了，要负责吗？"},
            {"speaker": "灿灿", "text": "我哪里弄乱了？"},
        ],
    }
    # LLM 漏了首句，且顺序写成昭昭→灿灿
    mp = (
        "画面左边是灿灿，右边是昭昭。"
        "2.5-6.5秒昭昭说话，同时双手摊开的手指微微向内抖动约1厘米后停止；"
        "6.5-8.3秒灿灿说话，同时右手食指轻轻向前点动约1厘米后定格。"
        "两人说话后面部表情恢复与静图一致："
        "灿灿瞪圆眼睛嘴巴大张（愤怒状），不微笑；"
        "昭昭眯着眼睛嘴角上翘（无辜状），表情不变。"
        "服装发型稳定，身高比例（昭昭比灿灿矮半个头）不变。"
        "镜头固定，不推近不拉远，画面只有人物和场景，无任何文字叠加。"
    )
    cues = [
        ("对，意思是别碰。", 2.5),
        ("那你现在弄乱了，要负责吗？", 4.0),
        ("我哪里弄乱了？", 1.8),
    ]
    out = _inject_mouth_motion(mp, seg, cues)
    assert "0.0-2.5秒左侧女孩张嘴说话，同时" in out
    assert "2.5-6.5秒右侧男孩张嘴说话，同时" in out
    assert "6.5-8.3秒左侧女孩张嘴说话，同时" in out
    assert out.count("右侧男孩闭嘴") == 2
    assert "左侧女孩闭嘴" in out
    assert out.index("0.0-2.5秒左侧女孩") < out.index("2.5-6.5秒右侧男孩")
    assert out.count("张嘴说话，同时") == 3
    assert "两人说话后面部表情恢复与静图一致" in out
    first = out.split("；")[0]
    assert "后定格" not in first


def test_inject_mouth_motion_face_mark_between_lines():
    """收束句被插在说话句中间时，仍按对白序重建，不丢第二句。"""
    seg = {
        "dialogue": [
            {"speaker": "灿灿", "text": "我刚叠好的衣服怎么皱成一团了？"},
            {"speaker": "昭昭", "text": "我就碰了一下，没弄皱！"},
        ],
    }
    mp = (
        "画面左边是灿灿，右边是昭昭。"
        "0.0-3.0秒灿灿说话，同时右手食指向前点动约2厘米后停止。"
        "两人说话后面部表情恢复与静图一致：昭昭撇着嘴角耸肩（无辜状），表情不变；"
        "3.0-6.1秒昭昭说话，同时双手摊开微微向上抬起约2厘米后定格；"
        "两人说话后面部表情恢复与静图一致：昭昭撇着嘴角耸肩（无辜状），表情不变；"
        "灿灿瞪圆眼睛嘴巴大张（惊讶质问状），不微笑。"
        "服装发型稳定，身高比例（昭昭比灿灿矮半个头）不变。"
        "镜头固定，不推近不拉远，画面只有人物和场景，无任何文字叠加。"
    )
    cues = [
        ("我刚叠好的衣服怎么皱成一团了？", 3.0),
        ("我就碰了一下，没弄皱！", 3.1),
    ]
    out = _inject_mouth_motion(mp, seg, cues)
    assert "0.0-3.0秒左侧女孩张嘴说话，同时" in out
    assert "3.0-6.1秒右侧男孩张嘴说话，同时" in out
    assert out.index("0.0-3.0秒左侧女孩") < out.index("3.0-6.1秒右侧男孩")
    assert out.index("3.0-6.1秒右侧男孩") < out.index("两人说话后面部表情")
    assert out.count("两人说话后面部表情") == 1


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


_KEYFRAME_LLM_MOTION = (
    "画面左边是灿灿，右边是昭昭。"
    "灿灿说话，同时右手食指指向衣服团微微颤抖约2厘米后停止；"
    "昭昭说话，同时双手摊开向上微抖一下后停止。"
    "两人说话后面部表情恢复与静图一致："
    "灿灿瞪圆眼睛嘴巴大张（愤怒质问状），不微笑；"
    "昭昭撇着嘴角耸肩（委屈不服状），表情不变。"
    "服装发型稳定，身高比例（昭昭比灿灿矮半个头）不变。"
    "镜头固定，不推近不拉远，画面只有人物和场景，无任何文字叠加。"
)
_FORBIDDEN_INJECTED = re.compile(
    r"粉色卫衣的马尾女孩|蓝色短袖T恤的短发男孩|嘴巴闭合不张嘴"
)
_SPEAK_WINDOW_RE = re.compile(
    r"[\d.]+-[\d.]+秒(?:左侧|右侧)(?:男孩|女孩|妈妈)张嘴说话，同时"
)


def test_keyframe_motion_llm_draft_contract():
    """LLM 底稿：站位、按句说话、统一后停止、不自编秒数与 inject 字段。"""
    base = _KEYFRAME_LLM_MOTION
    assert "画面左边是灿灿，右边是昭昭" in base
    assert base.count("说话，同时") == 2
    assert "后定格" not in base
    assert "张嘴说话" not in base
    head = base.split("两人说话后面部表情", 1)[0]
    assert not re.search(r"[\d.]+-[\d.]+秒", head)
    assert _FORBIDDEN_INJECTED.search(base) is None


def test_keyframe_motion_after_inject_contract():
    """TTS 注入后：左右侧身份、张嘴/闭嘴、末句定格、无长外貌锚点。"""
    dialogue = [
        {"speaker": "灿灿", "text": "我刚叠好的衣服怎么皱成一团了？"},
        {"speaker": "昭昭", "text": "我就碰了一下，没弄皱！"},
    ]
    cues = [("我刚叠好的衣服怎么皱成一团了？", 3.05), ("我就碰了一下，没弄皱！", 3.02)]
    out = _inject_mouth_motion(_KEYFRAME_LLM_MOTION, {"dialogue": dialogue}, cues)

    assert out.count("张嘴说话，同时") == 2
    assert out.count("闭嘴") == 2
    assert _SPEAK_WINDOW_RE.search(out)
    assert "0.0-3.0秒左侧女孩张嘴说话" in out
    assert "3.0-6.1秒右侧男孩张嘴说话" in out
    assert _FORBIDDEN_INJECTED.search(out) is None
    assert "两人说话后面部表情恢复与静图一致" in out
    assert "愤怒质问状" in out
    assert "委屈不服状" in out
    # 末句动作由 inject 改为定格
    assert "双手摊开向上微抖一下后定格" in out
    assert "微微颤抖约2厘米后停止" in out
    assert "镜头固定，不推近不拉远" in out


def test_inject_speaking_times_into_motion_prompts_updates_segment():
    """与 worker clip 前同一入口：segments 原地写入 motion_prompt。"""
    dialogue = [
        {"speaker": "灿灿", "text": "a"},
        {"speaker": "昭昭", "text": "b"},
    ]
    segments = [
        {
            "segment_index": 1,
            "dialogue": dialogue,
            "motion_prompt": _KEYFRAME_LLM_MOTION,
        },
    ]
    from app.services.tts.tts_mgr import SubtitleCue

    cues = [
        SubtitleCue(segment_index=1, text="a", duration_sec=1.0),
        SubtitleCue(segment_index=1, text="b", duration_sec=1.5),
    ]
    n = inject_speaking_times_into_motion_prompts(segments, cues)
    assert n == 1
    mp = segments[0]["motion_prompt"]
    assert "左侧女孩张嘴说话" in mp
    assert "右侧男孩张嘴说话" in mp


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
