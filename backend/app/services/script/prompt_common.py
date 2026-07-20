"""提示词构建共用辅助函数。"""

from __future__ import annotations

import re

from app.utils.job_info import (
    CONTENT_STYLE_DAILY_STORY,
    CONTENT_STYLE_LIFE_EXPERIENCE,
    CONTENT_STYLE_SCIENCE_CHILD,
    ORIENTATION_LANDSCAPE,
    ORIENTATION_PORTRAIT,
    content_style_from_job,
    orientation_for_resolve,
)
from app.utils.media import (
    NARRATION_WRITING_TARGET_RATIO,
    narration_accept_max_chars,
    narration_word_range,
    narration_writing_plan,
    narration_writing_target_chars,
)
from app.services.script.board_timeline import (
    VideoTimeline,
    parse_video_timeline,
)


def json_output_clause(example: str) -> str:
    return (
        "请仅输出合法 JSON 对象（不要 markdown 代码块，不要解释文字）。"
        "JSON 输出样例（字段名须一致，内容为示意）：\n"
        f"{example}\n"
    )


def resolve_script_profile(
    job: dict | None,
    *,
    orientation: str | None = None,
    content_style: str | None = None,
) -> tuple[str, str]:
    resolved_orientation = orientation or (
        orientation_for_resolve(job) if job else None
    ) or ORIENTATION_PORTRAIT
    resolved_style = content_style
    if not resolved_style and job:
        # 兼容测试/调用方把 content_style 放在 job 根上
        raw_root = job.get("content_style")
        if isinstance(raw_root, str) and raw_root.strip():
            from app.utils.job_info import normalize_content_style

            resolved_style = normalize_content_style(raw_root) or None
        if not resolved_style:
            resolved_style = content_style_from_job(job)
    if not resolved_style:
        resolved_style = CONTENT_STYLE_SCIENCE_CHILD
    # chat pipeline 默认横屏；非 daily_story 时使用生活经验风格
    if job and job.get("pipeline") == "chat":
        if not orientation:
            resolved_orientation = ORIENTATION_LANDSCAPE
        if not content_style and resolved_style != CONTENT_STYLE_DAILY_STORY:
            resolved_style = CONTENT_STYLE_LIFE_EXPERIENCE
    return resolved_orientation, resolved_style


def writing_target_clause(narration_target: int) -> str:
    writing_target = narration_writing_target_chars(narration_target)
    lo, hi = narration_word_range(narration_target)
    pct = int(NARRATION_WRITING_TARGET_RATIO * 100)
    return (
        f"写作目标约 {writing_target} 字（总目标 {narration_target} 字的 {pct}%），"
        f"验收硬区间 {lo}-{hi} 字：低于下限可补细节，超过上限须删繁就简，超标与不足均作废"
    )


def storyboard_length_budget(
    *,
    narration_target: int,
    content_style: str,
) -> str:
    """无单镜时长约束时的字数预算（segment_target_sec=0）。"""
    from app.services.script.voiceover_standard.styles import resolve_style_rules

    plan = narration_writing_plan(narration_target, 0)
    hard_min = plan["hard_min"]
    writing_target = plan["writing_target"]
    hard_max = narration_accept_max_chars(narration_target)
    per_min = plan["per_seg_min"]
    seg_count_min = plan["seg_count_min"]
    pct = int(NARRATION_WRITING_TARGET_RATIO * 100)
    layers = resolve_style_rules(content_style).layer_style
    self_check = (
        "【输出前硬性自检，任一项不满足须当场重写后再输出 JSON】"
        f"①segments 数量 ≥ {seg_count_min}；"
        "②逐段统计 text 字数，任一超过单段上限须拆段；"
        f"③各段 text 字数之和在 {hard_min}-{hard_max} 字之间（目标约 {writing_target} 字，"
        f"超过 {hard_max} 字须删内容后重写）；"
        "④word_count 等于 narration 实际字数；"
        "⑤narration 与 segments 按序拼接完全一致；"
        "⑥口播无伪亲历/第一人称从业叙事。"
    )
    return (
        f"【字数预算】总目标 {narration_target} 字；"
        f"写作目标约 {writing_target} 字（总目标 {narration_target} 字的 {pct}%）；"
        f"验收区间 {hard_min}-{hard_max} 字（超出即不合格）。\n"
        f"每段至少 {per_min} 字，段数由口播内容逻辑决定；"
        f"各段 text 字数之和须在 {hard_min}-{hard_max} 字之间。\n"
        f"每段用「{layers}」三层写法，每层一句短话，禁止整段一句带过。\n"
        "【生成顺序】先按预算写满各段 segments，再拼接 narration，最后核对 word_count。\n"
        f"{self_check}"
    )


def append_supplementary_to_user(user: str, supplementary_info: str | None) -> str:
    extra = (supplementary_info or "").strip()
    if not extra:
        return user
    return (
        f"{user}\n\n"
        "用户补充信息（须合理融入口播与分镜，勿编造与补充信息矛盾的内容；"
        "若与科普常识冲突，以科学事实为准）：\n"
        f"{extra}"
    )


def supplementary_system_clause(
    supplementary_info: str | None,
    *,
    bind_timeline: bool = False,
) -> str:
    extra = (supplementary_info or "").strip()
    if not extra:
        return ""
    if bind_timeline:
        return (
            "用户会提供补充信息：须融入口播内容与表达风格，"
            "但不得与画面时间表冲突；若冲突以时间表为准。"
        )
    return (
        "用户会提供补充信息：须合理融入口播内容与表达风格，"
        "勿编造与补充信息矛盾的内容；若与科普常识冲突，以科学事实为准。"
    )


def resolve_video_timeline(
    video_timeline: str | None,
    *,
    script: dict | None = None,
    chars_per_sec: float | None = None,
) -> VideoTimeline | None:
    raw = (video_timeline or "").strip()
    if not raw and script:
        saved = script.get("video_timeline")
        if isinstance(saved, str) and saved.strip():
            raw = saved.strip()
    return parse_video_timeline(raw, chars_per_sec=chars_per_sec) if raw else None


def title_rule(title: str, max_title: int) -> tuple[str, str]:
    cleaned = re.sub(r"\s+", "", title.strip())
    if len(cleaned) <= max_title:
        return (
            f"title 必须与原标题完全一致：{cleaned}，不要改写、精简或替换。",
            f"原标题：{title}\n请输出 title（与原标题一致）、完整口播",
        )
    return (
        f"title 为精简视频标题，保留原标题核心意思，不含空格换行，字数不超过 {max_title}。",
        f"原标题：{title}\n请输出精简 title（≤{max_title}字）、完整口播",
    )


def prompt_step(step: str, system: str, user: str) -> dict[str, str]:
    return {
        "step": step,
        "label": {
                "storyboard": "口播分镜",
                "narration": "口播文案",
                "visual_brief": "分镜画面概述",
                "image_prompts": "文生图提示词",
                "material_script": "口播文案",
                "title_optimize": "标题优化",
                "video_description": "视频介绍",
            }.get(step, step),
        "system": system,
        "user": user,
    }
