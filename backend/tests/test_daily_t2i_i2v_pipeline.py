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
    assert prompt.startswith("儿童情绪涂鸦风")
    assert "灿灿：10岁女孩" in prompt
    assert "昭昭：7岁男孩" in prompt
    assert "昭昭比灿灿矮约半个头" in prompt
    assert "窗光从一侧斜照" in prompt
    assert "中近景特写" in prompt
    assert "全身可见" in prompt
    assert "灿灿头发通体纯黑" in prompt
    assert "画面左边是昭昭，右边是灿灿" in prompt
    assert "严格左" not in prompt
    # 场景陈设句（茶几上空水杯和蜡笔）已归 S2/S5，不再留在 S4
    assert "空水杯" not in prompt
    # 槽位顺序：S1→S2→S4 场景动作在前，S3 外貌在后（对齐成功三人稿）
    assert prompt.index("客厅沙发") < prompt.index("昭昭：7岁男孩")
    # 嘴型锁定：首个说话人（灿灿）张嘴，其余闭嘴，防 i2v 说话人反转
    assert "灿灿正在开口说话" in prompt
    assert "昭昭嘴巴自然闭合" in prompt


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

    policy_dirty = (
        clean
        + "出图被内容策略拦截（content_policy_violation），请改写本段 visual_brief。"
    )
    assert strip_verify_regen_leak(policy_dirty) == clean


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
    assert "中景，全身可见" in prompt
    assert "严格左" not in prompt
    assert "画面左边是昭昭，右边是灿灿" in prompt
    assert prompt.count("画面左边是昭昭，右边是灿灿") == 1


def test_assemble_daily_lr_brief_not_force_mom_mid():
    """vb 写左昭右灿时，即使 speakers 含妈妈也不强插三人构图。"""
    from app.services.script.image_prompt import _daily_layout_speakers

    seg = {
        "shot_type": "特写",
        "speakers": ["昭昭", "灿灿", "妈妈"],
        "visual_brief": (
            "客厅茶几旁；画面左边是昭昭，右边是灿灿；"
            "昭昭端盘瞪眼；灿灿扯袖子瞥向厨房门口。"
        ),
        "dialogue": [
            {"speaker": "昭昭", "text": "奶油滴桌布了！"},
            {"speaker": "灿灿", "text": "快擦，千万别让妈看见。"},
        ],
    }
    assert _daily_layout_speakers(seg, seg["visual_brief"]) == ["昭昭", "灿灿"]
    prompt = assemble_daily_t2i_prompt(seg)
    assert "三人特写" not in prompt
    assert "从左到右是昭昭、妈妈、灿灿" not in prompt
    assert "妈妈：" not in prompt
    assert "画面左边是昭昭，右边是灿灿" in prompt


def test_assemble_daily_e_sticky_mom_not_dropped_by_lr_brief():
    """E 类妈妈在场：vb 只写左右姐弟时仍须三人构图，不能挤掉妈妈。"""
    from app.services.script.image_prompt import _daily_layout_speakers

    seg = {
        "shot_type": "特写",
        "speakers": ["昭昭", "灿灿", "妈妈"],
        "visual_brief": (
            "洗手间水槽边，画面左边是昭昭，右边是灿灿；"
            "昭昭指向水槽，灿灿摊手。"
        ),
        "dialogue": [
            {"speaker": "昭昭", "text": "那是下水道沫，手上还滴水呢。"},
            {"speaker": "灿灿", "text": "赶时间，冲得急。"},
        ],
    }
    assert _daily_layout_speakers(seg, seg["visual_brief"]) == [
        "昭昭",
        "妈妈",
        "灿灿",
    ]
    prompt = assemble_daily_t2i_prompt(seg)
    assert "三人同框" in prompt
    assert "中景三人同框，全身可见" in prompt
    assert "从左到右是昭昭、妈妈、灿灿" not in prompt


def test_assemble_daily_ma_coming_keeps_empty_doorway():
    """「妈出来了」但未入画：盯门口改空门口，并硬锁恰好两人。"""
    seg = {
        "shot_type": "中景",
        "speakers": ["昭昭", "灿灿"],
        "visual_brief": (
            "客厅茶几旁，两人半蹲；画面左边是昭昭，右边是灿灿；"
            "昭昭捂嘴惊恐；灿灿举拖鞋，眼睛瞟向厨房门口，身体僵住。"
        ),
        "dialogue": [
            {"speaker": "昭昭", "text": "完了完了！"},
            {"speaker": "灿灿", "text": "糟了，妈出来了，快蹲下！"},
        ],
    }
    prompt = assemble_daily_t2i_prompt(seg)
    assert "妈妈：" not in prompt
    assert "瞟向厨房门口" not in prompt
    assert "空无无人" not in prompt


def test_assemble_daily_hide_ma_keeps_two_person_cast():
    """「别让妈看见」离场后，拼装应为两人，不含妈妈外貌/三人句。"""
    segs = [
        {
            "segment_index": 1,
            "shot_type": "特写",
            "visual_brief": (
                "客厅茶几旁；画面左边是昭昭，右边是灿灿；"
                "昭昭端盘；灿灿扯袖子。"
            ),
            "dialogue": [
                {"speaker": "昭昭", "text": "奶油滴桌布了！"},
                {"speaker": "灿灿", "text": "快擦，千万别让妈看见。"},
            ],
        },
        {
            "segment_index": 2,
            "shot_type": "中景",
            "visual_brief": (
                "客厅里；画面从左到右是昭昭、妈妈、灿灿；"
                "妈妈叉腰指茶几。"
            ),
            "dialogue": [
                {"speaker": "妈妈", "text": "你俩拿的什么！"},
                {"speaker": "昭昭", "text": "被发现了！"},
            ],
        },
    ]
    assemble_daily_image_prompts(
        segs, setting="客厅，昭昭和灿灿刚打开冰箱，妈妈在厨房。"
    )
    p1 = segs[0]["image_prompt"]
    assert "妈妈：" not in p1
    assert "三人同框" not in p1
    assert "三人特写" not in p1
    assert "画面主体为" not in p1
    assert "灿灿：" in p1
    p2 = segs[1]["image_prompt"]
    assert "妈妈：" in p2
    assert "三人同框" in p2


def test_scrub_daily_visual_brief_drops_duplicate_pose():
    from app.services.script.visual_brief import scrub_daily_visual_brief

    raw = (
        "卫生间门口，地面有拖把痕迹；画面左边是昭昭，右边是灿灿；"
        "昭昭右手比划吃冰棍，左手叉腰，瞪眼；灿灿右手比划数字十，左手叉腰，仰头；"
        "昭昭双手叉腰，点头瞪眼。"
    )
    out = scrub_daily_visual_brief(raw)
    assert out.count("昭昭右手比划吃冰棍") == 1
    assert "昭昭双手叉腰" not in out
    assert "灿灿右手比划数字十" in out


def test_scrub_daily_visual_brief_strips_mouth_and_fixes_hands():
    from app.services.script.image_prompt import assemble_daily_t2i_prompt
    from app.services.script.visual_brief import scrub_daily_visual_brief

    raw = (
        "客厅沙发上，茶几上摊开一袋薯片；画面从左到右是昭昭、妈妈、灿灿；"
        "昭昭双手叉腰，身体前倾，瞪圆眼睛，嘴巴大张，右手指着薯片袋，语气得意；"
        "妈妈耸肩；灿灿双手抱胸撇嘴。"
    )
    out = scrub_daily_visual_brief(raw)
    assert "嘴巴大张" not in out
    assert "语气得意" not in out
    assert "双手叉腰" not in out
    assert "叉腰" not in out
    assert "左手自然下垂" in out
    assert "右手指着薯片袋" in out
    assert "身体前倾" not in out

    prompt = assemble_daily_t2i_prompt(
        {
            "shot_type": "中景",
            "visual_brief": raw,
            "dialogue": [
                {"speaker": "昭昭", "text": "那这半袋都空了？"},
                {"speaker": "妈妈", "text": "我就尝了一片。"},
            ],
        }
    )
    assert "嘴巴大张" not in prompt
    assert "嘴巴大张" not in prompt
    assert prompt.count("正在开口说话") == 1
    assert "昭昭正在开口说话" in prompt
    assert "双手叉腰" not in prompt
    assert "叉腰" not in prompt
    assert "左手自然下垂" in prompt


def test_scrub_daily_visual_brief_rewrites_door_gap():
    """「门缝」诱发双开门中缝，统一改写为门与门框的空隙。"""
    from app.services.script.visual_brief import scrub_daily_visual_brief

    raw = "客厅门边，门半掩着，门缝被风吹得更开。"
    out = scrub_daily_visual_brief(raw)
    assert "门缝" not in out
    assert "门与门框的空隙" in out


def test_scrub_daily_visual_brief_normalizes_default_table_set():
    from app.services.script.visual_brief import scrub_daily_visual_brief

    # 纯默认陈设句保持归一（幂等）
    out = scrub_daily_visual_brief(
        "客厅沙发上，妈妈举着薯片袋；画面左边是昭昭，右边是灿灿；"
        "茶几上放着遥控器和空水杯。"
    )
    assert "茶几上放着遥控器和空水杯" in out
    # 非默认道具（月饼/蛋糕）一律保留，不再靠词表删（回归：job45 蛋糕被删）
    cake = scrub_daily_visual_brief(
        "客厅茶几上放着一块圆形蛋糕，灿灿手拿餐刀正准备切；"
        "画面左边是昭昭，右边是灿灿。"
    )
    assert "蛋糕" in cake
    moon = scrub_daily_visual_brief(
        "客厅茶几上放着一个月饼盒；画面左边是昭昭，右边是灿灿。"
    )
    assert "月饼" in moon
    # 专家边界：茶/量词不被误删，杂物保留，纯默认归一，子集补齐
    tea = scrub_daily_visual_brief(
        "客厅茶几上放着茶和空水杯；画面左边是昭昭，右边是灿灿。"
    )
    assert "茶" in tea and "空水杯" in tea
    plain_tea = scrub_daily_visual_brief(
        "客厅茶几上放着茶；画面左边是昭昭，右边是灿灿。"
    )
    assert "茶" in plain_tea
    one_cup = scrub_daily_visual_brief(
        "客厅茶几上放着一个空水杯；画面左边是昭昭，右边是灿灿。"
    )
    assert "一个空水杯" in one_cup
    default_full = scrub_daily_visual_brief(
        "客厅茶几上摆着空水杯、遥控器；画面左边是昭昭，右边是灿灿。"
    )
    assert "茶几上放着遥控器和空水杯" in default_full
    # 冲突物摊开也保留
    keep = scrub_daily_visual_brief(
        "客厅沙发上；茶几上摊开一袋薯片；画面左边是昭昭，右边是灿灿。"
    )
    assert "茶几上摊开一袋薯片" in keep


def test_scrub_daily_visual_brief_resolves_prop_ground_conflict():
    """冲突道具已摔落在地，陈设句仍写「茶几上立着」→ 归一为落地状态。"""
    from app.services.script.visual_brief import scrub_daily_visual_brief

    raw = (
        "客厅，茶几上立着摔裂的相框，旁边是扫帚和簸箕；"
        "画面左边是昭昭，右边是灿灿；昭昭双手摊开，表情懊恼，相框摔在地上；"
        "灿灿蹲下，双手伸向相框，手指悬空未接触，表情紧张。"
    )
    out = scrub_daily_visual_brief(raw)
    assert "茶几上立着摔裂的相框" not in out
    assert "相框掉在地上" in out


def test_scrub_daily_visual_brief_resolves_prop_slip_conflict():
    """相框滑落镜：陈设句不得再写「茶几上立着」。"""
    from app.services.script.visual_brief import scrub_daily_visual_brief

    raw = (
        "客厅，茶几上立着摔裂的相框，旁边是扫帚和簸箕；"
        "画面左边是昭昭，右边是灿灿；昭昭双手张开向前扑，相框从手中滑落，表情惊慌；"
        "灿灿双手向前伸出试图接住，身体前倾，表情焦急。"
    )
    out = scrub_daily_visual_brief(raw)
    assert "茶几上立着摔裂的相框" not in out
    assert "相框掉在地上" in out


def test_scrub_daily_visual_brief_resolves_prop_fragment_conflict():
    """相框已成碎片，陈设句归一为碎片散落在地上。"""
    from app.services.script.visual_brief import scrub_daily_visual_brief

    raw = (
        "客厅，茶几上立着摔裂的相框，旁边是扫帚和簸箕；"
        "画面左边是昭昭，右边是灿灿；昭昭右脚踩在相框碎片上，双手扶住沙发，表情疼痛。"
    )
    out = scrub_daily_visual_brief(raw)
    assert "茶几上立着摔裂的相框" not in out
    assert "地上散落着摔裂的相框碎片" in out


def test_scrub_daily_visual_brief_resolves_prop_hand_conflict():
    """相框已被妈妈拿起，桌上陈设句去掉该物，只留手里。"""
    from app.services.script.visual_brief import scrub_daily_visual_brief

    raw = (
        "客厅，茶几上立着摔裂的相框，旁边是扫帚和簸箕；"
        "画面左边是昭昭，右边是灿灿，妈妈站在中间；"
        "妈妈右手拿着相框，左手叉腰，皱着眉。"
    )
    out = scrub_daily_visual_brief(raw)
    assert "茶几上立着摔裂的相框" not in out
    assert "拿着相框" in out
    assert "旁边是扫帚和簸箕" in out


def test_scrub_strips_held_prop_from_table_keeps_other_items():
    """同镜已握着某物时，桌上并列项只去掉该物，不靠剪刀/水壶词表。"""
    from app.services.script.visual_brief import scrub_daily_visual_brief

    scissors = scrub_daily_visual_brief(
        "客厅，桌上摊着剪坏的纸和剪刀；画面左边是昭昭，右边是灿灿；"
        "灿灿右手握着剪刀（手指包裹剪刀柄），左手按在纸上。"
    )
    assert "桌上摊着剪坏的纸" in scissors
    assert "纸和剪刀" not in scissors
    assert "握着剪刀" in scissors

    kettle = scrub_daily_visual_brief(
        "阳台，桌上放着托盘和水壶；昭昭右手握着一把蓝色塑料浇花水壶。"
    )
    assert "桌上放着托盘" in kettle
    assert "托盘和水壶" not in kettle
    assert "握着一把蓝色塑料浇花水壶" in kettle

    table_only = scrub_daily_visual_brief(
        "客厅，桌上摊着一把剪刀，纸边歪歪扭扭；画面左边是昭昭，右边是灿灿；"
        "昭昭双手自然下垂，看着纸边。"
    )
    assert "桌上摊着一把剪刀" in table_only

    beside = scrub_daily_visual_brief(
        "客厅，画面左边是昭昭，右边是灿灿。"
        "纸旁放着一把剪刀，剪刀由灿灿右手握着，刀刃张开，她左手自然下垂。"
        "昭昭眼睛盯着剪刀，双手空着摊开耸肩。"
    )
    assert "纸旁放着" not in beside
    assert "握着" in beside
    assert "剪刀" in beside
    assert "盯着剪刀" not in beside
    assert "看向灿灿" in beside
    assert beside.count("剪刀") == 1


def test_scrub_daily_visual_brief_keeps_one_active_hand():
    """指+叉腰会诱发第三只手，scrub 只留一个主动手。"""
    from app.services.script.visual_brief import scrub_daily_visual_brief

    out = scrub_daily_visual_brief(
        "画面左边是昭昭，右边是灿灿。"
        "灿灿左手指着纸边，右手叉腰，身体前倾，正在说话。"
        "昭昭双手摊开耸肩。"
    )
    assert "右手自然下垂" in out
    assert "左手指着纸边" in out
    assert "叉腰" not in out
    assert "身体前倾" not in out


def test_scrub_daily_visual_brief_fixes_relative_lr_conflict():
    """质检重写「站在她右侧」不得和「左边是昭昭」并存。"""
    from app.services.script.visual_brief import scrub_daily_visual_brief

    out = scrub_daily_visual_brief(
        "画面左边是昭昭，右边是灿灿。灿灿右手握着那把剪刀。"
        "昭昭站在她右侧，双手摊开耸肩。"
    )
    assert "昭昭站在画面左边" in out
    assert "站在她右侧" not in out


def test_scrub_daily_visual_brief_rewrites_vague_opposite_to_anchor():
    """「对面/旁边」改正面锚点，不用否定表述。"""
    from app.services.script.visual_brief import scrub_daily_visual_brief

    mom = scrub_daily_visual_brief(
        "昭昭站在茶几旁，双手背在身后。灿灿站在昭昭右边，双手下垂。"
        "妈妈站在对面，单手叉腰，皱眉瞪眼。"
    )
    assert "妈妈站在茶几前" in mom
    assert "对面" not in mom

    squat = scrub_daily_visual_brief(
        "画面左边是昭昭，右边是灿灿。昭昭蹲在灿灿对面，双手叉腰。"
    )
    assert "昭昭蹲在画面左边" in squat
    assert "对面" not in squat


def test_enrich_thin_daily_visual_brief_three_person_chips():
    """薄 vb 加厚：场景开场 + 妈妈居中 + 左右孩锚点；S5 去重薯片/薯片袋。"""
    from app.services.script.image_prompt import assemble_daily_t2i_prompt
    from app.services.script.visual_brief import enrich_thin_daily_visual_brief

    setting = (
        "客厅，茶几上摆着一袋打开的薯片和半杯水，"
        "昭昭和灿灿刚偷吃被妈妈发现，正手忙脚乱藏薯片"
    )
    seg = {
        "segment_index": 12,
        "shot_type": "特写",
        "visual_brief": (
            "昭昭站在茶几旁，双手背在身后，瞪大眼睛。"
            "灿灿站在昭昭右边，双手下垂，撇嘴。"
            "妈妈站在对面，单手叉腰，皱眉瞪眼。画面中有薯片"
        ),
        "speakers": ["昭昭", "灿灿", "妈妈"],
        "visual_subjects": [
            {"name": "昭昭", "posture": "站在茶几旁", "action": "双手背在身后", "expression": "瞪大眼睛"},
            {"name": "灿灿", "posture": "站在昭昭右边", "action": "双手下垂", "expression": "撇嘴"},
            {"name": "妈妈", "posture": "站在对面", "action": "单手叉腰", "expression": "皱眉瞪眼"},
        ],
        "object_states": [
            {"object": "薯片袋", "count": "一个", "form": "袋口敞开，薯片散出", "holder": "无", "position": "茶几上"},
            {"object": "薯片", "count": "一袋", "form": "袋口敞开，部分散落", "holder": "无", "position": "茶几上"},
        ],
        "scene_anchors": ["沙发", "茶几"],
    }
    enriched = enrich_thin_daily_visual_brief(seg, setting=setting)
    assert "客厅" in enriched
    assert "沙发" in enriched and "茶几" in enriched
    assert "妈妈站在茶几前" in enriched
    assert "画面左边是昭昭" in enriched
    assert "画面右边是灿灿" in enriched
    assert "对面" not in enriched
    assert "画面中有薯片" not in enriched

    prompt = assemble_daily_t2i_prompt(seg, setting=setting)
    assert "客厅，沙发、茶几清晰可见" in prompt
    assert "一个薯片袋在茶几上" in prompt
    assert prompt.count("薯片袋") == 1
    assert "对面" not in prompt


def test_restore_held_prop_owners_keeps_original_holder():
    """质检重写把剪刀改到昭昭手里时，拨回灿灿。"""
    from app.services.script.visual_brief import restore_held_prop_owners

    old = "画面左边是昭昭，右边是灿灿。灿灿右手握着那把剪刀。"
    new = "画面左边是昭昭，右边是灿灿。昭昭右手握着剪刀，灿灿左手叉腰。"
    out = restore_held_prop_owners(new, old)
    assert "灿灿右手握着剪刀" in out
    assert "昭昭右手握着剪刀" not in out


def test_assemble_daily_image_prompts_drops_table_scissors_when_held():
    """拼装后的 image_prompt 不得同时写桌上剪刀和手里握着剪刀。"""
    from app.services.script.image_prompt import assemble_daily_image_prompts

    segs = [
        {
            "segment_index": 1,
            "shot_type": "中景",
            "visual_brief": (
                "客厅，桌上摊着剪坏的纸和剪刀；画面左边是昭昭，右边是灿灿；"
                "灿灿右手握着剪刀（手指包裹剪刀柄），左手叉腰。"
            ),
            "dialogue": [
                {"speaker": "灿灿", "line": "我压着线顺着推，你看仔细啊。"},
            ],
        }
    ]
    assemble_daily_image_prompts(
        segs,
        setting="客厅，桌上摊着一张刚剪坏的纸。",
    )
    vb = segs[0]["visual_brief"]
    assert "桌上摊着剪坏的纸" in vb
    assert "纸和剪刀" not in vb
    assert "握着剪刀" in vb
    ip = segs[0]["image_prompt"]
    assert "握着剪刀" in ip
    assert not re.search(r"桌上[^。；]*剪刀", ip)


def test_scrub_daily_visual_brief_keeps_prop_when_no_position_conflict():
    """道具仍在原位时不改写；「蛋糕刀/薯片袋」同前缀别物不得误判为位移。"""
    from app.services.script.visual_brief import scrub_daily_visual_brief

    cake = scrub_daily_visual_brief(
        "客厅茶几上放着一块圆形蛋糕；画面左边是昭昭，右边是灿灿；"
        "灿灿右手握着塑料蛋糕刀正准备切。"
    )
    assert "茶几上放着一块圆形蛋糕" in cake
    chips = scrub_daily_visual_brief(
        "客厅沙发上；茶几上摊开一袋薯片；画面左边是昭昭，右边是灿灿；"
        "昭昭指着薯片袋，撇着嘴。"
    )
    assert "茶几上摊开一袋薯片" in chips
    pointing = scrub_daily_visual_brief(
        "客厅，茶几上立着摔裂的相框，旁边是扫帚和簸箕；"
        "画面左边是昭昭，右边是灿灿；昭昭右手食指指向茶几上的相框，瞪圆眼睛。"
    )
    assert "茶几上立着摔裂的相框" in pointing


def test_assemble_daily_image_prompts_injects_fixed_furniture_when_missing():
    """分镜1 建立的固定陈设（沙发/茶几）由 S2 场景锚点统一补回。"""
    from app.services.script.image_prompt import assemble_daily_image_prompts

    segs = [
        {
            "segment_index": 1,
            "shot_type": "中景",
            "visual_brief": (
                "客厅，茶几上立着摔裂的相框，旁边是扫帚和簸箕；"
                "画面左边是昭昭，右边是灿灿；"
                "昭昭身后的沙发上有一团揉皱的衣服；昭昭右手食指指向茶几上的相框。"
            ),
            "dialogue": [{"speaker": "昭昭", "text": "姐，我把相框碰裂了！"}],
        },
        {
            "segment_index": 6,
            "shot_type": "特写",
            "visual_brief": (
                "客厅，摔裂的相框掉在地上；画面左边是昭昭，右边是灿灿；"
                "昭昭双手摊开，表情懊恼。"
            ),
            "dialogue": [{"speaker": "昭昭", "text": "哎呀！手滑——！"}],
        },
    ]
    assemble_daily_image_prompts(segs, setting="客厅。")
    ip1 = segs[0]["image_prompt"]
    ip6 = segs[1]["image_prompt"]
    # S2 场景锚点：地点+硬锚点（分镜1 沙发/茶几）
    assert "客厅，沙发，茶几" in ip1
    # 特写镜 S2 按景别裁剪，只留地点
    assert "客厅；" in ip6
    assert "茶几上立着摔裂的相框" not in ip6
    # 幂等：重复拼装不会二次注入
    ip6_before = ip6
    assemble_daily_image_prompts(segs, setting="客厅。")
    assert segs[1]["image_prompt"] == ip6_before


def test_normalize_daily_visual_brief_sequence_injects_fixed_furniture():
    """visual_brief 归一同样补回分镜1 的固定陈设，供前端画面描述一致。"""
    from app.services.script.visual_brief import normalize_daily_visual_brief_sequence

    segs = [
        {
            "segment_index": 1,
            "visual_brief": (
                "客厅，茶几上立着摔裂的相框，旁边是扫帚和簸箕；"
                "昭昭身后的沙发上有一团揉皱的衣服。"
            ),
        },
        {
            "segment_index": 6,
            "visual_brief": (
                "客厅，摔裂的相框掉在地上；"
                "画面左边是昭昭，右边是灿灿；昭昭双手摊开，表情懊恼。"
            ),
        },
    ]
    normalize_daily_visual_brief_sequence(segs)
    vb6 = segs[1]["visual_brief"]
    assert "沙发" in vb6
    assert "茶几" in vb6
    assert "扫帚" in vb6
    assert "簸箕" in vb6


def test_scrub_daily_visual_brief_layers_furniture_when_prop_on_ground():
    """道具已落地时，「沙发和茶几之间」改写为家具台面整洁+地面分层写法。"""
    from app.services.script.visual_brief import scrub_daily_visual_brief

    raw = (
        "客厅，沙发和茶几之间，摔裂的相框和碎片散落在地上，旁边是扫帚和簸箕；"
        "画面左边是昭昭，右边是灿灿；妈妈站在中间；昭昭双手摊开，表情委屈。"
    )
    out = scrub_daily_visual_brief(raw)
    assert "沙发和茶几之间" not in out
    assert "沙发、茶几上没有任何物品，表面整洁" in out
    assert "散落在地上" in out


def test_scrub_daily_visual_brief_keeps_between_for_people_or_no_ground_state():
    """人物站位或道具仍在原位时，「之间」不动，避免误改写。"""
    from app.services.script.visual_brief import scrub_daily_visual_brief

    people = scrub_daily_visual_brief(
        "客厅，沙发和茶几之间，妈妈站在中间；画面左边是昭昭，右边是灿灿。"
    )
    assert "沙发和茶几之间" in people
    fell = scrub_daily_visual_brief(
        "客厅，相框掉在沙发和茶几之间；画面左边是昭昭，右边是灿灿。"
    )
    assert "掉在沙发和茶几之间" in fell
    assert "没有任何物品" not in fell


def test_normalize_daily_visual_brief_sequence_blocks_prop_state_regression():
    """冲突道具落地后，后续镜不得再写回家具台面（跨镜状态保护）。"""
    from app.services.script.visual_brief import normalize_daily_visual_brief_sequence

    segs = [
        {"segment_index": 1, "visual_brief": "客厅，茶几上立着摔裂的相框，旁边是扫帚和簸箕；昭昭指着相框。"},
        {"segment_index": 5, "visual_brief": "客厅，摔裂的相框掉在地上；昭昭双手张开向前扑。"},
        {"segment_index": 12, "visual_brief": "客厅，茶几上立着摔裂的相框，昭昭正把相框往沙发垫下塞，灿灿在门口望风。"},
    ]
    normalize_daily_visual_brief_sequence(segs)
    vb1, vb5, vb12 = (s["visual_brief"] for s in segs)
    assert "茶几上立着" in vb1  # 分镜1 原位保留
    assert "掉在地上" in vb5
    assert "茶几上立着" not in vb12  # 落地后回归被改回
    assert "掉在地上" in vb12


def test_assemble_daily_image_prompts_blocks_prop_state_regression():
    """出图质检兜底重写路径同样受跨镜状态保护。"""
    from app.services.script.image_prompt import assemble_daily_image_prompts

    segs = [
        {
            "segment_index": 1,
            "shot_type": "中景",
            "visual_brief": "客厅，茶几上立着摔裂的相框，旁边是扫帚和簸箕；画面左边是昭昭，右边是灿灿。",
            "dialogue": [
                {"speaker": "昭昭", "text": "姐，我把相框碰裂了！"},
                {"speaker": "灿灿", "text": "妈回来会骂的！"},
            ],
        },
        {
            "segment_index": 5,
            "shot_type": "中景",
            "visual_brief": "客厅，摔裂的相框掉在地上；画面左边是昭昭，右边是灿灿。",
            "dialogue": [
                {"speaker": "昭昭", "text": "哎呀！相框滑了！"},
                {"speaker": "灿灿", "text": "快接住它！"},
            ],
        },
        {
            "segment_index": 12,
            "shot_type": "中景",
            "visual_brief": "客厅，茶几上立着摔裂的相框，昭昭正把相框往沙发垫下塞，灿灿在门口望风；画面左边是昭昭，右边是灿灿。",
            "dialogue": [
                {"speaker": "昭昭", "text": "被发现了！"},
                {"speaker": "灿灿", "text": "这下死定了……"},
            ],
        },
    ]
    assemble_daily_image_prompts(segs, setting="客厅。")
    ip12 = segs[2]["image_prompt"]
    assert "茶几上立着" not in ip12
    assert "掉在地上" in ip12


def test_assemble_daily_image_prompts_locks_inventory_from_setting():
    """质检重写爱编尺子/沙发/第二张纸，锁定后只能留 setting 里的剪刀和纸。"""
    from app.services.script.image_prompt import assemble_daily_image_prompts

    setting = (
        "客厅，灿灿正指着昭昭剪得歪歪扭扭的纸边，教他剪刀要拿正、沿直线剪；"
        "桌上还摊着一张昭昭刚剪坏的纸。"
    )
    segs = [
        {
            "segment_index": 1,
            "shot_type": "中近景特写",
            "visual_brief": (
                "客厅，桌上摊着一张刚剪坏的纸和一把剪刀，纸边歪歪扭扭呈锯齿状；"
                "画面左边是昭昭，右边是灿灿；桌上还放着遥控器和空水杯。"
            ),
            "dialogue": [
                {"speaker": "灿灿", "line": "客厅桌上你剪的纸边都歪成锯齿了，得顺着线走"},
                {"speaker": "昭昭", "line": "那你剪一条给我看"},
            ],
        },
        {
            "segment_index": 2,
            "shot_type": "中景",
            "visual_brief": (
                "客厅，灿灿右手握着一把儿童安全剪刀，左手压在白纸上；"
                "两张剪坏的纸被灿灿拿在手中；背景是沙发和茶几；"
                "桌上还放着一把尺子和一支铅笔。"
            ),
            "dialogue": [
                {"speaker": "灿灿", "line": "我压着线顺着推，你看仔细啊。"},
                {"speaker": "昭昭", "line": "你这条边怎么往外弯了你听着呀？"},
            ],
        },
    ]
    assemble_daily_image_prompts(segs, setting=setting)
    ip2 = segs[2 - 1]["image_prompt"]
    assert "剪刀" in ip2
    assert "纸" in ip2
    assert "儿童安全剪刀" not in ip2
    assert "尺子" not in ip2
    assert "铅笔" not in ip2
    assert "沙发" not in ip2
    assert "茶几" not in ip2
    assert "两张" not in ip2


def test_clutter_prop_not_locked_from_dialogue_metaphor():
    """台词说「拿尺子比」不是把尺子锁进画面。"""
    from app.services.script.visual_brief import (
        daily_locked_inventory,
        strip_unlocked_inventory,
    )

    segs = [
        {
            "segment_index": 1,
            "visual_brief": "客厅，桌上摊着一张剪坏的纸和一把剪刀。",
            "dialogue": [
                {"speaker": "昭昭", "line": "你拿尺子比着，边都扭成麻花了啊。"},
            ],
        }
    ]
    locked = daily_locked_inventory(
        segs,
        "客厅，教他剪刀要拿正；桌上摊着一张刚剪坏的纸。",
    )
    assert "剪刀" in locked
    assert "纸" in locked
    assert "尺子" not in locked
    out = strip_unlocked_inventory("桌上还放着一把尺子和半张纸。", locked)
    assert "尺子" not in out


def test_strip_unlocked_inventory_remote_job79_dirty_brief():
    """远程 job79 质检重写原文：尺子/沙发/第二张纸必须剥掉，剪刀要补回。"""
    from app.services.script.visual_brief import (
        daily_locked_inventory,
        strip_unlocked_inventory,
    )

    setting = (
        "客厅，灿灿正指着昭昭剪得歪歪扭扭的纸边，教他剪刀要拿正、沿直线剪；"
        "桌上还摊着一张昭昭刚剪坏的纸。"
    )
    segs = [
        {
            "segment_index": 1,
            "visual_brief": (
                "客厅，桌上摊着一张刚剪坏的纸和一把剪刀，纸边歪歪扭扭呈锯齿状；"
                "桌上还放着遥控器和空水杯。"
            ),
            "dialogue": [
                {"speaker": "灿灿", "line": "你剪的纸边都歪成锯齿了"},
                {"speaker": "昭昭", "line": "那你剪一条给我看"},
            ],
        }
    ]
    locked = daily_locked_inventory(segs, setting)
    dirty4 = (
        "儿童情绪涂鸦风格，橡皮擦拭痕迹。客厅桌上摊着一张剪坏的纸和一把剪刀；"
        "桌上还放着一把尺子和半张被剪坏的纸；昭昭手指悬空未接触剪刀。"
    )
    out4 = strip_unlocked_inventory(dirty4, locked)
    assert "尺子" not in out4
    assert "橡皮擦拭" in out4
    assert "剪刀" in out4
    dirty7 = (
        "客厅桌上，一张被剪成波浪形的纸摊开，纸边歪扭如锯齿；"
        "桌上还摊着另一张剪坏的纸，边缘破损。"
    )
    out7 = strip_unlocked_inventory(dirty7, locked)
    assert "另一张" not in out7
    assert "剪刀" in out7


def test_locked_inventory_keeps_shot1_furniture():
    """分镜1 已有的沙发/茶几仍锁定，不能当杂物删掉。"""
    from app.services.script.visual_brief import (
        daily_locked_inventory,
        strip_unlocked_inventory,
    )

    segs = [
        {
            "segment_index": 1,
            "visual_brief": (
                "客厅，茶几上立着摔裂的相框，旁边是扫帚和簸箕；"
                "昭昭身后的沙发上有一团揉皱的衣服。"
            ),
            "dialogue": [{"speaker": "昭昭", "line": "姐，我把相框碰裂了！"}],
        },
        {
            "segment_index": 2,
            "visual_brief": "客厅，沙发和茶几还在，相框掉在地上。",
            "dialogue": [{"speaker": "灿灿", "line": "快捡起来"}],
        },
    ]
    locked = daily_locked_inventory(segs, "客厅，茶几上摔裂的相框。")
    assert "相框" in locked
    assert "沙发" in locked
    assert "茶几" in locked
    out = strip_unlocked_inventory(segs[1]["visual_brief"], locked)
    assert "沙发" in out
    assert "茶几" in out
    assert "相框" in out


def test_assemble_daily_t2i_floor_shoe_lace_lock():
    """地垫系带：灿灿粉鞋在垫上、昭昭蓝白鞋在脚上，硬锁两只鞋。"""
    setting = "客厅地垫上，灿灿脱下的粉红运动鞋鞋带散开摆着，昭昭蹲在鞋边准备系带"
    seg = {
        "segment_index": 1,
        "shot_type": "中景",
        "visual_brief": (
            "昭昭蹲着，双手伸向鞋带，抬头看向灿灿；"
            "灿灿站着，右手食指指向地面上的鞋，皱眉瞪眼，说话。"
        ),
        "dialogue": [
            {"speaker": "灿灿", "line": "昭昭，地垫上这双鞋鞋带又散了，你来帮我系。"},
            {"speaker": "昭昭", "line": "好嘞，我这就蹲下来系。"},
        ],
    }
    prompt = assemble_daily_t2i_prompt(seg, setting=setting)
    assert "双脚均已穿好一双蓝白运动鞋" in prompt
    assert "两侧同色蓝白运动鞋" not in prompt
    assert "赤脚仅穿白袜子" in prompt
    assert "仅有一双粉红运动鞋共两只" in prompt
    # 三句重复锁定已去重，只保留 mat 从句里的单句鞋数描述
    assert "全画面地垫上仅此一双粉红运动鞋共两只" not in prompt
    assert "双手并拢拢住地垫上一双粉鞋的鞋带结" in prompt
    assert "鞋帮贴地" in prompt
    assert "粉鞋全部在地垫上" in prompt
    assert "穿进" not in prompt
    assert "灿灿赤脚仅穿白袜子" in prompt
    assert prompt.count("鞋带散开") == 1


def test_assemble_daily_t2i_floor_shoe_seg1_no_hand_conflict():
    """分镜1：brief 里「双手伸向鞋带/指向鞋」须剥掉，避免与硬锁打架诱发套鞋。"""
    setting = "客厅地垫上，灿灿脱下的粉红运动鞋鞋带散开摆着，昭昭蹲在鞋边准备系带"
    seg = {
        "segment_index": 1,
        "shot_type": "特写",
        "visual_brief": (
            "昭昭蹲在鞋边准备系带。画面左边是昭昭，右边是灿灿。"
            "昭昭蹲着，双手伸向鞋带，抬头看向灿灿；"
            "灿灿站着，右手食指指向地面上的鞋，左手自然下垂，皱眉瞪眼，说话。"
            "客厅地垫是浅灰色圆形编织地垫。"
        ),
        "dialogue": [
            {"speaker": "灿灿", "line": "昭昭，地垫上这双鞋鞋带又散了，你来帮我系。"},
            {"speaker": "昭昭", "line": "好嘞，我这就蹲下来系。"},
        ],
    }
    prompt = assemble_daily_t2i_prompt(seg, setting=setting)
    assert "双手伸向鞋带" not in prompt
    assert "指向地面上的鞋" not in prompt
    assert "指向地垫上的鞋带" not in prompt
    assert "蹲在鞋边准备系带" not in prompt
    assert "双手并拢拢住地垫上一双粉鞋的鞋带结" in prompt
    assert "灿灿刚脱下的同一双" in prompt


def test_assemble_daily_t2i_floor_shoe_scrubs_chuanjin():
    """brief 里「穿进鞋眼」须改成「穿过鞋眼」，避免 T2I 画成往脚上套鞋。"""
    setting = "客厅地垫上，灿灿脱下的粉红运动鞋鞋带散开摆着，昭昭蹲在鞋边准备系带"
    seg = {
        "segment_index": 3,
        "shot_type": "中景",
        "visual_brief": "昭昭将右鞋带穿进左边鞋眼，灿灿右手食指指着鞋带。",
        "dialogue": [
            {"speaker": "灿灿", "text": "哎，你干嘛把左带子弄到右边去"},
            {"speaker": "昭昭", "text": "你说系一起嘛"},
        ],
    }
    prompt = assemble_daily_t2i_prompt(seg, setting=setting)
    assert "穿过左边鞋眼" in prompt
    assert "穿进" not in prompt


def test_assemble_daily_t2i_floor_shoe_dead_knot_state():
    """后续镜鞋带系死结时，硬锁须写贴底/死结，禁止仍写鞋带散开并排。"""
    setting = "客厅地垫上，灿灿脱下的粉红运动鞋鞋带散开摆着，昭昭蹲在鞋边准备系带"
    seg = {
        "segment_index": 6,
        "shot_type": "中景",
        "visual_brief": (
            "客厅地垫上，一双运动鞋的鞋带被系成死结，两只鞋底紧紧贴在一起；"
            "昭昭蹲在鞋边，双手握着鞋带用力向上提。"
        ),
        "dialogue": [{"speaker": "灿灿", "line": "我才一提，两只鞋哗啦全翻过去了！"}],
    }
    prompt = assemble_daily_t2i_prompt(seg, setting=setting)
    assert "鞋带系成死结" in prompt
    assert "鞋底紧紧贴在一起" in prompt
    assert "鞋带散开" not in prompt
    assert "并排平放" not in prompt


def test_assemble_daily_t2i_floor_shoe_seg6_cancan_lift():
    """分镜6：灿灿拎死结鞋、昭昭叉腰旁观；禁止误判为昭昭系带或鞋平放垫上。"""
    setting = "客厅地垫上，灿灿脱下的粉红运动鞋鞋带散开摆着，昭昭蹲在鞋边准备系带"
    seg = {
        "segment_index": 6,
        "shot_type": "中景",
        "visual_brief": (
            "客厅地垫上，画面左边是昭昭，右边是灿灿。灿灿蹲在地垫上，"
            "双手拎起两只系在一起的粉红运动鞋，鞋底紧紧贴在一起，鞋带勒出深深的印痕，"
            "她皱着眉、撇着嘴，费力地拎着鞋带。昭昭蹲在灿灿对面，双手叉腰，"
            "仰头看着灿灿，咧嘴得意地笑，眼睛眯成缝。地垫上散落着散开的鞋带。"
        ),
        "dialogue": [
            {"speaker": "灿灿", "line": "两只鞋底都贴一块儿了，我拎都拎不起来。"},
            {"speaker": "昭昭", "line": "大功告成，像手铐一样严实，你提起来试试。"},
        ],
        "speakers": ["昭昭", "灿灿"],
    }
    prompt = assemble_daily_t2i_prompt(seg, setting=setting)
    assert "被拎离地面" in prompt
    assert "双手拎着系成死结串在一起" in prompt
    assert "昭昭蹲在画面左边，双手叉腰" in prompt
    assert "无人拿在手中" not in prompt
    assert "鞋带散开" not in prompt
    assert "散开的鞋带" not in prompt
    assert "双手并拢拢住" not in prompt
    assert "双手拎起" not in prompt
    assert "带。" not in prompt
    assert "全画面仅有两只粉红运动鞋" in prompt
    assert "粉鞋全部在灿灿双手中" in prompt
    assert "重申" not in prompt
    assert "得意地笑" in prompt
    assert "咧嘴" not in prompt


def test_assemble_daily_t2i_floor_shoe_seg7_cancan_flip():
    """分镜7：灿灿拎鞋翻个儿、昭昭摊手惊讶；禁止鞋带松散或昭昭叉腰/捏鞋带。"""
    setting = "客厅地垫上，灿灿脱下的粉红运动鞋鞋带散开摆着，昭昭蹲在鞋边准备系带"
    seg = {
        "segment_index": 7,
        "shot_type": "中近景特写",
        "visual_brief": (
            "接上一镜，灿灿弯腰用右手提起两只串在一起的鞋，鞋子翻了个个儿，"
            "鞋带松散摇晃。昭昭蹲在一旁，抬头看着鞋子，双手摊开，表情惊讶。"
            "场景定稿：客厅地垫上，两只粉红运动鞋被拎起，鞋带缠绕；"
            "背景是沙发和茶几，茶几上放着遥控器和空水杯"
        ),
        "dialogue": [
            {"speaker": "灿灿", "line": "我才一提，两只鞋哗啦全翻过去了！"},
            {"speaker": "昭昭", "line": "多稳当，我绑得连蚂蚁都钻不过去。"},
        ],
        "speakers": ["昭昭", "灿灿"],
    }
    prompt = assemble_daily_t2i_prompt(seg, setting=setting)
    assert "鞋子翻了个个儿" in prompt
    assert "双手摊开，表情惊讶" in prompt
    assert "鞋带松散" not in prompt
    assert "鞋带散开" not in prompt
    assert "双手叉腰" not in prompt
    assert "双手并拢拢住" not in prompt
    assert "无人拿在手中" not in prompt
    assert "用右手提起" not in prompt


def test_assemble_daily_t2i_floor_shoe_seg9_aftermath():
    """分镜9：系带失败旁观镜，昭昭垂手沮丧、灿灿叉腰叹气，禁止捏鞋带。"""
    setting = "客厅地垫上，灿灿脱下的粉红运动鞋鞋带散开摆着，昭昭蹲在鞋边准备系带"
    seg = {
        "segment_index": 9,
        "shot_type": "中近景特写",
        "visual_brief": (
            "接上一镜，昭昭蹲着，双手垂在身侧，低头看着地上的鞋，表情沮丧。"
            "灿灿站在旁边，双手叉腰，低头看着鞋，叹了口气。"
            "场景定稿：客厅地垫上，两只粉红运动鞋并排放在地上，鞋带散乱；"
            "背景是沙发和茶几，茶几上放着遥控器和空水杯"
        ),
        "dialogue": [{"speaker": "灿灿", "line": "行吧，这鞋带是彻底白系了。"}],
        "speakers": ["昭昭", "灿灿"],
    }
    prompt = assemble_daily_t2i_prompt(seg, setting=setting)
    assert "双手垂在身侧" in prompt
    assert "表情沮丧" in prompt
    assert "灿灿双手叉腰" in prompt
    assert "鞋带纠缠散乱" in prompt
    assert "双手并拢拢住" not in prompt
    assert "双手自然下垂" not in prompt
    assert "鞋带散开；" not in prompt
    assert "地垫中央仅有一双粉红运动鞋共两只" in prompt
    assert "左右并排平放接触地垫" in prompt
    assert "重申" not in prompt


def test_assemble_daily_t2i_floor_shoe_seg1_not_untie_compact():
    """分镜1：昭昭系带开场，勿因「昭昭蹲在鞋」误走灿灿抠死结短 prompt。"""
    setting = "客厅地垫上，灿灿脱下的粉红运动鞋鞋带散开摆着，昭昭蹲在鞋边准备系带"
    seg = {
        "segment_index": 1,
        "shot_type": "特写",
        "visual_brief": (
            "客厅地垫上，灿灿脱下的粉红运动鞋鞋带散开摆着，昭昭蹲在鞋边准备系带。"
            "画面左边是昭昭，右边是灿灿。"
            "昭昭蹲着，双手伸向鞋带，抬头看向灿灿；"
            "灿灿站着，右手食指指向地面上的鞋，左手自然下垂，皱眉瞪眼，说话。"
        ),
        "dialogue": [
            {"speaker": "灿灿", "text": "昭昭，地垫上这双鞋鞋带又散了，你来帮我系。"},
            {"speaker": "昭昭", "text": "好嘞，我这就蹲下来系。"},
        ],
    }
    prompt = assemble_daily_t2i_prompt(seg, setting=setting)
    assert "鞋带缠成死结" not in prompt
    assert "鞋带散开" in prompt
    assert "双手并拢拢住地垫上一双粉鞋的鞋带结" in prompt
    assert "灿灿双手自然下垂" in prompt
    assert "双手掌心向上摊开" not in prompt


def test_assemble_daily_t2i_floor_shoe_seg8_cancan_untie():
    """分镜8：灿灿抠死结、昭昭摊手旁观；brief 反写左右时仍左昭右灿；走短 prompt。"""
    setting = "客厅地垫上，灿灿脱下的粉红运动鞋鞋带散开摆着，昭昭蹲在鞋边准备系带"
    seg = {
        "segment_index": 8,
        "shot_type": "中景",
        "visual_brief": (
            "客厅地垫上，两只粉红运动鞋鞋带系成死结、鞋底相对贴在一起；"
            "画面左边是灿灿，右边是昭昭；灿灿蹲在鞋旁，双手手指正用力抠鞋带死结，"
            "眉头紧皱、撇嘴；昭昭站在旁边，双手摊开耸肩，歪头皱眉，一脸不解地看向灿灿。"
        ),
        "dialogue": [
            {"speaker": "灿灿", "text": "别夸了，我蹲地上，上手抠都解不开这死结。"},
            {"speaker": "昭昭", "text": "可你刚才明明说鞋带系一起，怎么现在又上手来解了？"},
        ],
        "speakers": ["昭昭", "灿灿"],
    }
    prompt = assemble_daily_t2i_prompt(seg, setting=setting)
    assert "画面左侧蓝T恤深蓝短裤短发男孩昭昭" in prompt
    assert "双手掌心向上摊开" in prompt
    assert "双手用力抠地垫中央一双粉红运动鞋的鞋带死结" in prompt
    assert "灿灿双手自然下垂" not in prompt
    assert "昭昭蹲在地垫旁看着地垫上的粉鞋" not in prompt
    assert "严格左蓝T恤深蓝短裤短发男孩昭昭、右粉卫衣蓝裤黑马尾女孩灿灿" in prompt
    assert "全画面仅有昭昭、灿灿两位儿童" in prompt
    assert "禁止第三" not in prompt
    assert len(prompt) < 550


def test_assemble_daily_t2i_floor_shoe_seg9_corrupted_vb_dialogue_aftermath():
    """分镜9：visual_brief 被质检 LLM 改坏时，台词「彻底白系」仍走沮丧旁观硬锁。"""
    setting = "客厅地垫上，灿灿脱下的粉红运动鞋鞋带散开摆着，昭昭蹲在鞋边准备系带"
    seg = {
        "segment_index": 9,
        "shot_type": "中近景特写",
        "visual_brief": (
            "客厅地垫上，画面左边是昭昭，右边是灿灿；灿灿蹲在地上，"
            "双手各捏住一只鞋的鞋带末端，用力向外拉扯；昭昭双手摊开耸肩。"
        ),
        "dialogue": [{"speaker": "灿灿", "line": "行吧，这鞋带是彻底白系了。"}],
        "speakers": ["昭昭", "灿灿"],
    }
    prompt = assemble_daily_t2i_prompt(seg, setting=setting)
    assert "各捏住一只鞋的鞋带" not in prompt
    assert "向外拉扯" not in prompt
    assert "双手垂在身侧" in prompt
    assert "灿灿双手叉腰" in prompt
    assert "鞋带纠缠散乱" in prompt
    assert "左右并排平放接触地垫" in prompt


def test_render_object_states_dedup_same_object():
    from app.services.script.image_prompt import _render_object_states

    rendered = _render_object_states(
        [
            {"object": "薯片", "count": "一个", "position": "茶几上", "form": "袋口敞开，薯片散出"},
            {"object": "薯片", "count": "一袋", "position": "茶几上", "form": "袋口敞开，部分散落"},
        ]
    )
    assert rendered.count("薯片") == 1
    assert "部分散落" in rendered


def test_body_part_object_states_do_not_render_detached_hand():
    """伤势误写入 object_states 时，不得生成「手中放着一只手」。"""
    from app.services.script.image_prompt import assemble_daily_t2i_prompt
    from app.services.script.visual_brief import (
        normalize_object_states,
        render_visual_subjects,
    )

    subjects = [
        {
            "name": "昭昭",
            "posture": "站在门口",
            "action": "左手抬起捂住右手",
            "expression": "低头皱眉",
        },
        {
            "name": "灿灿",
            "posture": "站在昭昭对面",
            "action": "右手叉腰",
            "expression": "瞪眼",
        },
    ]
    seg = {
        "segment_index": 1,
        "shot_type": "中近景特写",
        "speakers": ["昭昭", "灿灿"],
        "visual_subjects": subjects,
        "visual_brief": render_visual_subjects(subjects),
        "object_states": [
            {
                "object": "一只手",
                "count": "",
                "form": "红肿",
                "holder": "昭昭",
                "position": "昭昭手中",
            }
        ],
        "scene_anchors": ["门"],
        "dialogue": [
            {"speaker": "灿灿", "text": "昭昭，你手咋了？"},
            {"speaker": "昭昭", "text": "没……没有。"},
        ],
    }
    notes = normalize_object_states([seg])
    assert any("身体部位" in n for n in notes)
    assert not seg["object_states"]

    prompt = assemble_daily_t2i_prompt(
        seg,
        setting="家门口，昭昭手上有伤，灿灿叉腰瞪他。",
        scene_anchor="家门口",
    )
    assert "手中放着一只手" not in prompt
    assert "一只手在昭昭手中" not in prompt
    assert "左手抬起捂住右手" in prompt
    assert "红肿" in prompt


def test_promote_hand_injury_from_setting_without_object_states():
    from app.services.script.image_prompt import assemble_daily_image_prompts

    seg = {
        "segment_index": 1,
        "shot_type": "中近景特写",
        "speakers": ["昭昭", "灿灿"],
        "visual_subjects": [
            {
                "name": "昭昭",
                "posture": "站在门口",
                "action": "左手抬起捂住右手",
                "expression": "低头皱眉",
            },
            {
                "name": "灿灿",
                "posture": "站在昭昭对面",
                "action": "右手叉腰",
                "expression": "瞪眼",
            },
        ],
        "dialogue": [
            {"speaker": "灿灿", "text": "昭昭，你手咋了？"},
            {"speaker": "昭昭", "text": "没……没有。"},
        ],
    }
    assemble_daily_image_prompts(
        [seg],
        setting="家门口，昭昭手上有伤，灿灿叉腰瞪他。",
    )
    assert "红肿" in seg["image_prompt"]
    assert "手中放着一只手" not in seg["image_prompt"]


def test_hand_injury_bandaged_after_medicine_segment():
    from app.services.script.image_prompt import assemble_daily_image_prompts

    segments = [
        {
            "segment_index": 10,
            "shot_type": "中景",
            "speakers": ["昭昭", "灿灿"],
            "visual_subjects": [
                {
                    "name": "昭昭",
                    "posture": "站在门口",
                    "action": "双手握拳放在身前",
                    "expression": "认真",
                },
                {
                    "name": "灿灿",
                    "posture": "站在昭昭对面",
                    "action": "右手叉腰",
                    "expression": "撇嘴",
                },
            ],
            "text": "哼，小屁孩，还管我？认真的。",
        },
        {
            "segment_index": 11,
            "shot_type": "中景",
            "speakers": ["昭昭", "灿灿"],
            "visual_subjects": [
                {
                    "name": "昭昭",
                    "posture": "站在灿灿面前",
                    "action": "向前迈步",
                    "expression": "低头",
                },
                {
                    "name": "灿灿",
                    "posture": "站在昭昭面前",
                    "action": "右手招了招",
                    "expression": "放松",
                },
            ],
            "text": "行了行了，过来，我给你擦擦药。嗯。",
        },
        {
            "segment_index": 12,
            "shot_type": "中景",
            "speakers": ["昭昭", "灿灿"],
            "visual_subjects": [
                {
                    "name": "昭昭",
                    "posture": "站在灿灿旁",
                    "action": "抬头看向灿灿",
                    "expression": "眯眼笑",
                },
                {
                    "name": "灿灿",
                    "posture": "站在昭昭旁",
                    "action": "右手拍了拍昭昭肩膀",
                    "expression": "微笑",
                },
            ],
            "text": "以后谁欺负你，我还得给你撑腰呢！那说好了！",
        },
    ]
    assemble_daily_image_prompts(
        segments,
        setting="家门口，昭昭手上有伤，灿灿叉腰瞪他。",
    )
    assert "红肿" in segments[0]["image_prompt"]
    assert "纱布" in segments[1]["image_prompt"]
    assert "红肿" not in segments[1]["image_prompt"]
    assert "纱布" in segments[2]["image_prompt"]
    assert "红肿" not in segments[2]["image_prompt"]


def test_assemble_daily_t2i_no_duplicate_lr_in_prompt():
    """visual_brief 已有左右时，构图段不再重复「画面左边…」。"""
    seg = {
        "shot_type": "中景",
        "visual_brief": (
            "卫生间门口，地面有拖把痕迹；画面左边是昭昭，右边是灿灿；"
            "昭昭右手比划吃冰棍，左手叉腰，瞪眼；灿灿右手比划数字十，左手叉腰，仰头；"
            "昭昭双手叉腰，点头瞪眼。"
        ),
        "dialogue": [
            {"speaker": "昭昭", "text": "一天十根。"},
            {"speaker": "灿灿", "text": "你吃了十二根。"},
        ],
    }
    prompt = assemble_daily_t2i_prompt(seg)
    assert prompt.count("画面左边是昭昭，右边是灿灿") == 1
    assert "昭昭双手叉腰，点头瞪眼" not in prompt
    assert "中景，全身可见" in prompt
    assert "严格左蓝T恤" not in prompt


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
    assert "0.0-1.4秒左侧女孩开口说话，口型自然开合，说完即闭嘴，同时" in out
    assert "1.4-2.5秒右侧男孩开口说话，口型自然开合，说完即闭嘴，同时" in out
    assert "此时右侧男孩嘴巴闭合不动" in out
    assert "此时左侧女孩嘴巴闭合不动" in out
    assert "0.0-1.0秒" not in out
    assert "1.0-2.0秒" not in out
    assert "画面左边灿灿" not in out
    assert "两人说话后面部表情" not in out
    assert "说话时只动嘴唇和下巴" in out


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
    assert "0.0-1.4秒左侧女孩开口说话，口型自然开合，说完即闭嘴，同时" in out
    assert "1.4-2.5秒右侧男孩开口说话，口型自然开合，说完即闭嘴，同时" in out
    assert "此时右侧男孩嘴巴闭合不动" in out


def test_inject_mouth_motion_three_person_stand():
    """三人站位写入左侧/中间/右侧身份，口型后校验才能抽到窗口。"""
    seg = {
        "dialogue": [
            {"speaker": "昭昭", "text": "哪里不一样？"},
            {"speaker": "灿灿", "text": "当然不算。"},
        ],
    }
    mp = (
        "画面左边是昭昭，中间是妈妈，右边是灿灿。"
        "昭昭说话，同时双手向上摊开约5厘米后停止；"
        "灿灿说话，同时右手食指轻轻点动两下后定格。"
        "服装发型稳定，身高比例（灿灿比昭昭高半个头，妈妈最高）不变。"
        "镜头固定，不推近不拉远。"
    )
    out = _inject_mouth_motion(mp, seg, [("哪里不一样？", 5.3), ("当然不算。", 3.4)])
    assert "0.0-5.3秒左侧男孩开口说话，口型自然开合，说完即闭嘴，同时" in out
    assert "5.3-8.7秒右侧女孩开口说话，口型自然开合，说完即闭嘴，同时" in out
    assert "中间妈妈嘴巴闭合不动" in out
    assert "昭昭开口说话" not in out


def test_inject_mouth_motion_mom_in_middle_after_lr():
    """LLM 写成「左右 + 妈妈在中间」时，闭嘴锁也要落到中间人。"""
    seg = {
        "dialogue": [
            {"speaker": "昭昭", "text": "那泡泡呢？"},
            {"speaker": "灿灿", "text": "水一冲就没了。"},
        ],
    }
    mp = (
        "画面左边是昭昭，右边是灿灿，妈妈在中间。"
        "昭昭说话，同时双手摊开后停止；"
        "灿灿说话，同时轻轻耸肩后定格。"
        "服装发型稳定。镜头固定，不推近不拉远。"
    )
    out = _inject_mouth_motion(
        mp, seg, [("那泡泡呢？", 5.2), ("水一冲就没了。", 4.6)]
    )
    assert "中间妈妈嘴巴闭合不动" in out
    assert "0.0-5.2秒左侧男孩开口说话" in out
    assert "5.2-9.8秒右侧女孩开口说话" in out


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
    assert "0.0-4.0秒右侧女孩开口说话，口型自然开合，说完即闭嘴，同时" in out
    assert "4.0-7.4秒左侧男孩开口说话，口型自然开合，说完即闭嘴，同时" in out
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
    assert "左侧女孩开口说话，口型自然开合" in out
    assert "后定格" in out
    assert "两人说话后面部表情" not in out
    assert "说话时只动嘴唇和下巴" in out
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
    assert "0.0-2.5秒左侧女孩开口说话，口型自然开合，说完即闭嘴，同时" in out
    assert "2.5-6.5秒右侧男孩开口说话，口型自然开合，说完即闭嘴，同时" in out
    assert "6.5-8.3秒左侧女孩开口说话，口型自然开合，说完即闭嘴，同时" in out
    assert out.count("右侧男孩嘴巴闭合不动") == 2
    assert "左侧女孩嘴巴闭合不动" in out
    assert out.index("0.0-2.5秒左侧女孩") < out.index("2.5-6.5秒右侧男孩")
    assert out.count("开口说话，口型自然开合") == 3
    assert "两人说话后面部表情恢复与静图一致" not in out
    assert "说话时只动嘴唇和下巴" in out
    assert "服装发型稳定" in out
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
    assert "0.0-3.0秒左侧女孩开口说话，口型自然开合，说完即闭嘴，同时" in out
    assert "3.0-6.1秒右侧男孩开口说话，口型自然开合，说完即闭嘴，同时" in out
    assert out.index("0.0-3.0秒左侧女孩") < out.index("3.0-6.1秒右侧男孩")
    assert out.index("3.0-6.1秒右侧男孩") < out.index("说话时只动嘴唇和下巴")
    assert "两人说话后面部表情" not in out
    assert "服装发型稳定" in out


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
    "灿灿说话，同时微微点头后停止；"
    "昭昭说话，同时双肩轻轻耸起后停止。"
    "服装发型稳定，身高比例（昭昭比灿灿矮半个头）不变。"
    "镜头固定，不推近不拉远，两人全程在画面内，画面干净无字幕无文字。"
)
_FORBIDDEN_INJECTED = re.compile(
    r"粉色卫衣的黑马尾女孩|蓝色短袖T恤的短发男孩|嘴巴闭合不张嘴"
)
_SPEAK_WINDOW_RE = re.compile(
    r"[\d.]+-[\d.]+秒(?:左侧|右侧)(?:男孩|女孩|妈妈)"
    r"开口说话，口型自然开合，说完即闭嘴，同时"
)


def test_keyframe_motion_llm_draft_contract():
    """LLM 底稿：站位、按句说话、统一后停止、不自编秒数与 inject 字段。"""
    base = _KEYFRAME_LLM_MOTION
    assert "画面左边是灿灿，右边是昭昭" in base
    assert base.count("说话，同时") == 2
    assert "后定格" not in base
    assert "张嘴说话" not in base
    head = base.split("服装发型稳定", 1)[0]
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

    assert out.count("开口说话，口型自然开合") == 2
    assert out.count("嘴巴闭合不动") == 2
    assert _SPEAK_WINDOW_RE.search(out)
    assert "0.0-3.0秒左侧女孩开口说话" in out
    assert "3.0-6.1秒右侧男孩开口说话" in out
    assert _FORBIDDEN_INJECTED.search(out) is None
    # 收束表情段会锁回闭嘴脸，注入后须被替换为嘴唇锁定句
    assert "两人说话后面部表情恢复与静图一致" not in out
    assert "说话时只动嘴唇和下巴" in out
    # 末句动作由 inject 改为定格
    assert "双肩轻轻耸起后定格" in out
    assert "微微点头后停止" in out
    assert "服装发型稳定" in out
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
    assert "左侧女孩开口说话，口型自然开合" in mp
    assert "右侧男孩开口说话，口型自然开合" in mp


def test_inject_mouth_motion_strips_orphan_and_normalizes_face_mark():
    """重生成后 LLM 多写无时间动作、收束写成「灿灿说话后…」时仍正确注入。"""
    seg = {
        "dialogue": [
            {"speaker": "灿灿", "text": "这道题你写错了，等于九十四"},
            {"speaker": "昭昭", "text": "可你自己刚才也算九十四"},
        ],
    }
    mp = (
        "画面左边是灿灿，右边是昭昭。"
        "灿灿说话，同时右手食指向下点动约2厘米后停止；"
        "昭昭说话，同时身体轻微后仰约1厘米后停止；"
        "昭昭保持双手摊开耸肩姿势，肩膀微微耸起约3厘米后停止。"
        "灿灿说话后面部表情恢复与静图一致："
        "灿灿瞪圆眼睛嘴巴大张（质问状），不微笑；"
        "昭昭皱着眉头撇嘴（不服状），表情不变。"
        "服装发型稳定，身高比例（昭昭比灿灿矮半个头）不变。"
        "镜头固定，不推近不拉远，画面只有人物和场景，无任何文字叠加。"
    )
    cues = [
        ("这道题你写错了，等于九十四", 3.4289),
        ("可你自己刚才也算九十四", 2.8154),
    ]
    out = _inject_mouth_motion(mp, seg, cues)
    assert "0.0-3.4秒左侧女孩开口说话，口型自然开合，说完即闭嘴，同时" in out
    assert "3.4-6.2秒右侧男孩开口说话，口型自然开合，说完即闭嘴，同时" in out
    assert "昭昭保持双手摊开耸肩姿势" not in out
    assert "灿灿说话后面部表情" not in out
    assert "两人说话后面部表情恢复与静图一致：" not in out
    assert "说话时只动嘴唇和下巴" in out
    assert out.count("开口说话，口型自然开合") == 2
    assert "服装发型稳定" in out


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
