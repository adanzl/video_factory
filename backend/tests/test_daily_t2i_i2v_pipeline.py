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
    assert prompt.startswith("基于参考图调整人物动作")
    assert "保持参考图外貌" in prompt
    assert "儿童涂鸦蜡笔画风格" in prompt
    assert "绝不允许" not in prompt
    assert "禁用" not in prompt
    assert "非写实" not in prompt
    assert "横线笔记本纸" not in prompt
    assert "平涂光照" in prompt
    assert "窗光从一侧斜照" not in prompt
    assert "与参考图同质" in prompt
    assert "中近景特写" in prompt
    assert "全身可见" in prompt
    assert "画面左边是昭昭，右边是灿灿" in prompt
    assert "严格左" not in prompt
    # 有参考图时不再展开外貌长描述
    assert "昭昭：7岁男孩" not in prompt
    # 场景陈设句（茶几上空水杯和蜡笔）已归 S2/S5，不再留在 S4
    assert "空水杯" not in prompt
    # 嘴型锁定：首个说话人（灿灿）张嘴，其余闭嘴，防 i2v 说话人反转
    assert "灿灿嘴唇微张，正在开口说话" in prompt
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
    # 孩子文字身份由 S1 参考图句锁定；此处守护站位/动作主体仍在、妈妈未入场
    assert "画面左边是昭昭，右边是灿灿" in p1
    assert "昭昭端盘" in p1
    assert "灿灿扯袖子" in p1
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
    assert "昭昭嘴唇微张，正在开口说话" in prompt
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
    assert "画面右边是灿灿，比昭昭高一点" in enriched
    assert "对面" not in enriched
    assert "画面中有薯片" not in enriched

    prompt = assemble_daily_t2i_prompt(seg, setting=setting)
    assert "客厅，沙发、茶几清晰可见" in prompt
    assert "一个薯片袋在茶几上" in prompt
    assert prompt.count("薯片袋") == 1
    assert "对面" not in prompt


def test_assemble_dining_segment_no_prop_triple_repeat():
    """M2+C 餐桌镜：肉块/餐桌不得在 S4+S5 三遍复读（#70 分镜8 类问题）。"""
    from app.services.script.image_prompt import assemble_daily_t2i_prompt

    setting = "餐桌旁，灿灿面前一盘肉，昭昭碗里几根青菜"
    seg = {
        "segment_index": 8,
        "shot_type": "中近景特写",
        "speakers": ["昭昭", "灿灿"],
        "visual_subjects": [
            {"name": "昭昭", "posture": "站在餐桌旁", "action": "双手叉腰", "expression": "皱眉瞪眼"},
            {"name": "灿灿", "posture": "坐在餐桌旁", "action": "双手捏住肉块，用筷子夹起", "expression": "眯眼笑"},
        ],
        "object_states": [
            {"object": "肉", "count": "一块", "form": "被灿灿用筷子夹起，悬在盘子上方", "holder": "灿灿", "position": ""},
            {"object": "青菜", "count": "几根", "form": "盛在碗里", "holder": "昭昭", "position": ""},
            {"object": "餐桌", "count": "一张", "form": "桌上摆着菜盘和碗", "holder": "无", "position": "画面中央"},
        ],
        "scene_anchors": ["餐桌"],
        "visual_brief": (
            "餐桌旁，餐桌清晰可见，灿灿手中放着一块肉，被灿灿用筷子夹起，悬在盘子上方。"
            "画面左边是昭昭，双手叉腰，皱眉瞪眼。画面右边是灿灿，双手捏住肉块，眯眼笑。"
            "灿灿手中放着一块肉，被灿灿用筷子夹起，悬在盘子上方。"
        ),
        "dialogue": [{"speaker": "昭昭", "line": "你碗里肉这么多，凭什么不能给我夹一块！"}],
    }
    prompt = assemble_daily_t2i_prompt(
        seg, scene_anchor="餐桌旁，餐桌，菜盘", setting=setting,
    )
    assert prompt.count("被灿灿用筷子夹起，悬在盘子上方") <= 1
    assert prompt.count("餐桌旁") <= 2
    assert prompt.count("一张餐桌在画面中央") == 0
    assert "画面左边是昭昭" in prompt
    assert "画面右边灿灿面前的碗里是一块肉" in prompt
    assert "画面左边昭昭面前的碗里是几根青菜" in prompt
    assert "一块肉在灿灿手中" not in prompt
    assert "没有肉" not in prompt


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
    assert "客厅，长条沙发，茶几" in ip1
    # 特写镜 S2 按景别裁剪，只留地点（可带轻涂后缀）
    assert "客厅，场景浅色蜡笔轻涂" in ip6 or ip6.split("；")[1].startswith("客厅")
    assert "长条沙发" not in ip6.split("；")[1]
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
    """质检重写爱编尺子/背景沙发/第二张纸，锁定后只能留 setting 里的剪刀和纸；
    客厅场景锚点固定补入「长条沙发」（沙发锁定 1c1fd7b）。"""
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
    assert "长条沙发" in ip2
    assert "背景是沙发" not in ip2
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


def test_story_container_props_locked_without_name_list():
    """容器句抽出的冲突物要锁定；不靠把肉/菜写进道具名单。"""
    from app.services.script.visual_brief import (
        _LOCKABLE_PROPS,
        daily_locked_inventory,
        enrich_setting_with_dialogue_props,
        extract_story_prop_holdings,
        _prop_key,
    )

    assert _prop_key("一盘肉") == "肉"
    assert _prop_key("几根青菜") == "青菜"
    assert "肉" not in _LOCKABLE_PROPS
    assert "青菜" not in _LOCKABLE_PROPS

    setting = "餐桌旁，灿灿面前一盘肉，昭昭碗里几根青菜"
    segs = [
        {
            "segment_index": 1,
            "visual_brief": "餐桌旁。",
            "dialogue": [
                {"speaker": "昭昭", "line": "你碗里肉这么多，凭什么不能给我夹一块！"},
            ],
        }
    ]
    locked = daily_locked_inventory(segs, setting)
    assert "肉" in locked
    assert "青菜" in locked
    holdings = extract_story_prop_holdings(setting, segs[0]["dialogue"])
    assert ("灿灿", "肉") in holdings
    assert ("昭昭", "青菜") in holdings

    thin = enrich_setting_with_dialogue_props(
        "餐桌旁，灿灿和昭昭在吵架",
        [
            {"speaker": "昭昭", "line": "你碗里肉这么多，凭什么不能给我夹一块！"},
            {"speaker": "灿灿", "line": "你碗里那青菜不香吗？"},
        ],
        contract_object="肉",
    )
    assert "肉" in thin
    assert "青菜" in thin
    assert "灿灿面前有肉" in thin
    assert "昭昭面前有青菜" in thin


def test_bowl_container_lock_not_forced_into_hands():
    """桌上碗盘：肉在灿灿碗里，昭昭碗里没有肉；不要写成拿在手里。"""
    from app.services.script.image_prompt import assemble_daily_t2i_prompt
    from app.services.script.visual_brief import normalize_object_states

    setting = "餐桌旁，灿灿面前一盘肉，昭昭碗里几根青菜"
    segs = [
        {
            "segment_index": 1,
            "shot_type": "中近景特写",
            "speakers": ["昭昭", "灿灿"],
            "visual_subjects": [
                {
                    "name": "昭昭",
                    "posture": "坐在餐桌左边",
                    "action": "右手指着肉盘",
                    "expression": "瞪眼皱眉",
                },
                {
                    "name": "灿灿",
                    "posture": "坐在餐桌右边",
                    "action": "双手护住肉盘",
                    "expression": "撇嘴瞪眼",
                },
            ],
            "object_states": [
                {
                    "object": "肉",
                    "count": "一盘",
                    "form": "冒着热气",
                    "holder": "灿灿",
                    "position": "灿灿面前的餐桌上",
                },
                {
                    "object": "青菜",
                    "count": "几根",
                    "form": "堆在碗里",
                    "holder": "昭昭",
                    "position": "昭昭面前的餐桌上",
                },
            ],
            "scene_anchors": ["餐桌"],
            "dialogue": [
                {"speaker": "昭昭", "line": "你碗里肉这么多，凭什么不能给我夹一块！"},
            ],
        }
    ]
    normalize_object_states(segs, setting=setting)
    meat = next(s for s in segs[0]["object_states"] if s["object"] == "肉")
    veg = next(s for s in segs[0]["object_states"] if s["object"] == "青菜")
    assert meat["position"] == "灿灿碗里"
    assert veg["position"] == "昭昭碗里"
    assert "手中" not in meat["position"]
    prompt = assemble_daily_t2i_prompt(segs[0], setting=setting, scene_anchor="餐桌旁")
    assert "画面右边灿灿面前的碗里是一盘肉" in prompt
    assert "画面左边昭昭面前的碗里是几根青菜" in prompt
    assert "一盘肉在灿灿手中" not in prompt
    assert "青菜在昭昭手中" not in prompt
    assert "指着肉盘" not in prompt
    assert "没有肉" not in prompt


def test_handheld_snack_not_forced_into_bowl():
    """手里举着零食不得归一成「灿灿碗里」（job91 回归）。"""
    from app.services.script.image_prompt import (
        _render_object_states,
        assemble_daily_t2i_prompt,
    )
    from app.services.script.visual_brief import (
        bowl_container_owners,
        extract_story_prop_holdings,
        normalize_object_states,
    )

    setting = (
        "家中客厅，灿灿坐在沙发上，手里举着一包零食，"
        "昭昭站在他面前，气鼓鼓地伸手去够。"
    )
    dialogue = [
        {"speaker": "灿灿", "line": "沙发上这包零食归我，作业本归你，公平吧？"},
        {"speaker": "昭昭", "line": "凭什么你偷吃我的零食还定规矩？"},
    ]
    holdings = extract_story_prop_holdings(setting, dialogue)
    assert ("灿灿", "零食") in holdings
    assert bowl_container_owners(setting, dialogue) == {}

    segs = [
        {
            "segment_index": 1,
            "speakers": ["昭昭", "灿灿"],
            "shot_type": "特写",
            "dialogue": dialogue,
            "visual_subjects": [
                {
                    "name": "灿灿",
                    "posture": "坐在沙发上",
                    "action": "右手举起零食包",
                    "expression": "挑眉瞪眼",
                },
                {
                    "name": "昭昭",
                    "posture": "站在灿灿面前",
                    "action": "右手指向灿灿",
                    "expression": "皱眉瞪眼",
                },
            ],
            "object_states": [
                {
                    "object": "零食",
                    "count": "一包",
                    "form": "未开封，包装完整",
                    "holder": "灿灿",
                    "position": "灿灿手中",
                }
            ],
            "scene_anchors": ["沙发", "茶几"],
            "visual_brief": (
                "灿灿坐在沙发上，右手举起零食包，挑眉瞪眼。"
                "昭昭站在灿灿面前，右手指向灿灿，皱眉瞪眼。"
            ),
        }
    ]
    notes = normalize_object_states(segs, setting=setting)
    assert not any("碗里" in n for n in notes)
    snack = segs[0]["object_states"][0]
    assert snack["position"] == "灿灿手中"
    rendered = _render_object_states(
        segs[0]["object_states"], setting=setting, dialogue=dialogue
    )
    assert "碗里" not in rendered
    assert "一包零食在灿灿手中" in rendered
    prompt = assemble_daily_t2i_prompt(segs[0], setting=setting)
    assert "碗里" not in prompt
    assert "一包零食在灿灿手中" in prompt


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


_KEYFRAME_LLM_MOTION = (
    "画面左边是灿灿，右边是昭昭。"
    "灿灿说话，同时微微点头后停止；"
    "昭昭说话，同时双肩轻轻耸起后停止。"
    "服装发型稳定，身高比例（昭昭比灿灿矮半个头）不变。"
    "镜头固定，不推近不拉远，两人全程在画面内。"
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


def test_rewrite_shared_grip_to_ends_s4_two_people_hold_one_remote():
    """两人共持单件道具时，S4 的「握遥控器」改写为「握遥控器一端/另一端」。

    对应 job88 2-9 镜「左手握遥控器 + 右手握遥控器」被 T2I 画成两个遥控器的问题。
    """
    from app.services.script.image_prompt import (
        _rewrite_shared_grip_to_ends_s4,
        assemble_daily_t2i_prompt,
    )

    s4 = (
        "画面左边是昭昭，左手握遥控器，右手食指指向灿灿，皱眉瞪眼。"
        "画面右边是灿灿，右手握遥控器，左手叉腰，撇嘴瞪眼"
    )
    states = [
        {
            "object": "遥控器",
            "count": "一个",
            "form": "两端被两人各握一端",
            "holder": "昭昭与灿灿",
            "position": "昭昭与灿灿手中",
        }
    ]
    out = _rewrite_shared_grip_to_ends_s4(s4, states)
    assert "左手握遥控器一端" in out
    assert "右手握遥控器另一端" in out
    assert out.count("握遥控器一端") == 1
    assert out.count("握遥控器另一端") == 1
    # 完整拼装：S4 已改写，S5 数量一致，不得出现两个独立的「握遥控器」
    seg = {
        "segment_index": 2,
        "shot_type": "中近景",
        "speakers": ["昭昭", "灿灿"],
        "visual_brief": s4,
        "visual_subjects": [
            {
                "name": "昭昭",
                "posture": "坐在沙发上，身体前倾",
                "action": "左手握遥控器，右手食指指向灿灿",
                "expression": "皱眉瞪眼",
            },
            {
                "name": "灿灿",
                "posture": "坐在沙发上，身体后仰",
                "action": "右手握遥控器，左手叉腰",
                "expression": "撇嘴瞪眼",
            },
        ],
        "object_states": states,
        "scene_anchors": ["沙发"],
    }
    prompt = assemble_daily_t2i_prompt(seg, setting="客厅，沙发上", scene_anchor="客厅，沙发")
    assert "左手握遥控器一端" in prompt
    assert "右手握遥控器另一端" in prompt
    assert prompt.count("一个遥控器在昭昭与灿灿手中") == 1


def test_scene_anchor_appends_tv_when_dialogue_mentions_tv():
    """台词涉电视相关词时，场景锚点必须补「电视」。
    回归：分镜5「指向电视方向」因 scene_anchors 只有沙发而画面无电视。"""
    from app.services.script.image_prompt import _daily_scene_anchor

    out = _daily_scene_anchor(
        "客厅，沙发上",
        "画面左边是昭昭，右手食指指向电视方向，瞪眼。",
        ["沙发"],
        dialogue_blob="你倒是背个新闻给我听！今天新闻说，科学家发现新星星，你懂吗？",
    )
    assert "电视" in out
    assert out.startswith("客厅")


def test_scene_anchor_no_tv_without_trigger_words():
    """无电视相关词时，场景锚点不得凭空出现电视。"""
    from app.services.script.image_prompt import _daily_scene_anchor

    out = _daily_scene_anchor(
        "客厅，沙发上",
        "画面左边是昭昭，右手摊开，瞪眼。",
        ["沙发"],
        dialogue_blob="你把作业写完！",
    )
    assert "电视" not in out
    assert "长条沙发" in out
    assert re.search(r"(?<!长条)沙发", out) is None


def test_living_room_locks_long_sofa():
    """客厅 S2 沙发一律长条沙发；无沙发时也补入。"""
    from app.services.script.image_prompt import (
        _daily_scene_anchor,
        _lock_living_room_long_sofa,
        assemble_daily_t2i_prompt,
    )

    assert _lock_living_room_long_sofa("客厅，沙发，茶几") == "客厅，长条沙发，茶几"
    assert _lock_living_room_long_sofa("客厅，茶几") == "客厅，长条沙发，茶几"
    assert "长条沙发" in _daily_scene_anchor("客厅", "", ["茶几"])
    prompt = assemble_daily_t2i_prompt(
        {
            "segment_index": 2,
            "shot_type": "中景",
            "speakers": ["昭昭", "灿灿"],
            "visual_brief": "画面左边是昭昭，右边是灿灿。",
            "scene_anchors": ["沙发", "茶几"],
        },
        setting="客厅",
        scene_anchor="客厅，沙发，茶几",
    )
    assert "长条沙发" in prompt
    assert "分体" not in prompt


def test_assemble_daily_image_prompts_adds_tv_across_segments():
    """全片台词涉电视时，各镜 image_prompt 场景锚点带电视（特写只保留地点）。"""
    segs = []
    for idx in (1, 2, 5):
        segs.append(
            {
                "segment_index": idx,
                "shot_type": "中景" if idx != 1 else "特写",
                "speakers": ["昭昭", "灿灿"],
                "visual_brief": (
                    "画面左边是昭昭，左手握遥控器，右手食指指向电视方向，瞪眼。"
                    "画面右边是灿灿，右手握遥控器，左手摊开，瞪眼"
                ),
                "visual_subjects": [
                    {"name": "昭昭", "posture": "坐在沙发上", "action": "左手握遥控器，右手指向电视方向", "expression": "瞪眼"},
                    {"name": "灿灿", "posture": "坐在沙发上", "action": "右手握遥控器，左手摊开", "expression": "瞪眼"},
                ],
                "object_states": [
                    {
                        "object": "电视遥控器",
                        "count": "一个",
                        "form": "黑色长方形，两端被两人各握一端",
                        "holder": "昭昭与灿灿",
                        "position": "昭昭与灿灿手中",
                    }
                ],
                "scene_anchors": ["沙发"],
                "dialogue": [
                    {"speaker": "灿灿", "text": "遥控器给我，我要看动画片！"},
                    {"speaker": "昭昭", "text": "你天天霸占电视，不讲理！"},
                ],
            }
        )
    assemble_daily_image_prompts(segs, setting="客厅，沙发上")
    seg5 = next(s for s in segs if int(s["segment_index"]) == 5)
    s2_5 = seg5["image_prompt"].split("；")[1]
    assert "客厅，长条沙发，电视" in s2_5
    seg1 = next(s for s in segs if int(s["segment_index"]) == 1)
    # 特写只保留地点「客厅」，不强制带电视/长条沙发
    s2_1 = seg1["image_prompt"].split("；")[1].strip()
    assert s2_1.startswith("客厅")
    assert "电视" not in s2_1
    assert "长条沙发" not in s2_1


def test_scrub_hand_contradiction_s4_downgrades_two_hand():
    """持物角色写「双手抱头」时降级为另一只手，避免三手。"""
    from app.services.script.image_prompt import _scrub_hand_contradiction_s4

    s4 = (
        "画面左边是昭昭，左手握遥控器一端，右手挥动，瞪眼。"
        "画面右边是灿灿，右手握遥控器另一端，双手抱头，皱眉闭眼"
    )
    out = _scrub_hand_contradiction_s4(s4)
    assert "左手抱头" in out
    assert "双手抱头" not in out
    # 昭昭无持物双手动作，不应被改写
    assert "右手挥动" in out


def test_assemble_daily_image_prompts_fixes_grip_two_hand_conflict():
    """全片拼装时 seg9 式「右手握遥控器，双手抱头」被改写为另一只手。"""
    seg = {
        "segment_index": 9,
        "shot_type": "中景",
        "speakers": ["昭昭", "灿灿"],
        "visual_brief": (
            "昭昭坐在沙发上，身体前倾，左手握遥控器，右手挥动，瞪眼。"
            "灿灿坐在沙发上，低头，右手握遥控器，双手抱头，皱眉闭眼"
        ),
        "visual_subjects": [
            {"name": "昭昭", "posture": "坐在沙发上，身体前倾", "action": "左手握遥控器，右手挥动", "expression": "瞪眼"},
            {"name": "灿灿", "posture": "坐在沙发上，低头", "action": "右手握遥控器，双手抱头", "expression": "皱眉闭眼"},
        ],
        "object_states": [
            {
                "object": "遥控器",
                "count": "一个",
                "form": "两端被两人各握一端",
                "holder": "昭昭与灿灿",
                "position": "昭昭与灿灿手中",
            }
        ],
        "scene_anchors": ["沙发"],
        "dialogue": [
            {"speaker": "灿灿", "text": "我……我……"},
            {"speaker": "昭昭", "text": "别说了！"},
        ],
    }
    prompt = assemble_daily_image_prompts(
        [seg], setting="客厅，沙发上，灿灿和昭昭各执遥控器一端，互不相让"
    )[0]["image_prompt"]
    assert "双手抱头" not in prompt
    assert "左手抱头" in prompt
    assert "右手握遥控器另一端" in prompt
