"""素材时间轴口播：提示词构建。"""

from __future__ import annotations

from app.config import get_settings
from app.utils.job_info import CONTENT_STYLE_SCIENCE_CHILD, script_params_from_info
from app.utils.media import DEFAULT_SPEECH_CHARS_PER_SEC, narration_word_range
from app.services.script.board_timeline import (
    append_material_timeline_to_user,
    material_timeline_system_clause,
    narration_range_for_timeline,
)
from app.services.script.prompt_common import (
    append_supplementary_to_user,
    json_output_clause,
    prompt_step,
    resolve_video_timeline,
    storyboard_length_budget,
    supplementary_system_clause,
    title_rule,
    writing_target_clause,
)
from app.services.script.voiceover_standard.styles.science_child import VOICE as SCIENCE_CHILD_VOICE
from app.services.script.voiceover_standard.styles.common import (
    ANTI_MEMOIR,
    MATERIAL_LENGTH_RULE,
    MATERIAL_NO_JSON,
    MATERIAL_SCRIPT_JSON_EXAMPLE,
)

__all__ = ["build_voiceover_material_prompts", "resolve_need_opening"]


def resolve_need_opening(
    job: dict | None = None,
    script: dict | None = None,
) -> bool:
    """从 script_json / info.script 解析是否需要开场钩子。"""
    if isinstance(script, dict) and isinstance(script.get("need_opening"), bool):
        return script["need_opening"]
    if not job:
        return False
    params = script_params_from_info(job.get("info"))
    if isinstance(params.get("need_opening"), bool):
        return params["need_opening"]
    legacy = job.get("script")
    if isinstance(legacy, dict) and isinstance(legacy.get("need_opening"), bool):
        return legacy["need_opening"]
    return False


def build_voiceover_material_prompts(
    title: str,
    *,
    feedback: str | None = None,
    max_title_length: int | None = None,
    narration_target_words: int | None = None,
    supplementary_info: str | None = None,
    video_timeline: str | None = None,
    script: dict | None = None,
    chars_per_sec: float | None = None,
    need_opening: bool | None = None,
    job: dict | None = None,
) -> dict[str, str]:
    settings = get_settings()
    max_title = settings.max_title_length if max_title_length is None else max_title_length
    timeline = resolve_video_timeline(video_timeline, script=script, chars_per_sec=chars_per_sec)
    opening = (
        bool(need_opening)
        if need_opening is not None
        else resolve_need_opening(job, script)
    )
    if timeline:
        narration_word_min, narration_word_max = narration_range_for_timeline(timeline)
        narration_word_target = (narration_word_min + narration_word_max) // 2
    else:
        narration_word_target = (
            narration_target_words if narration_target_words is not None else 800
        )
        narration_word_min, narration_word_max = narration_word_range(narration_word_target)
    title_rule_text, title_user_prefix = title_rule(title, max_title)
    if timeline:
        segment_rule = (
            f"segments 必须恰好 {len(timeline.slots)} 条，与画面时间表逐段一一对应；"
            "每项含 segment_index 与 text，第 i 段只讲第 i 段对象/画面；"
            "口吻保持童趣。"
        )
        if opening:
            opening_rule = (
                "开头用一句惊讶感叹或反常识直接吸引观众，如「哇，快看天上！」；"
                "迅速接入时间表第 1 段对象内容。"
            )
        else:
            opening_rule = (
                "禁止开场钩子、悬念反问、自我介绍、全片总起或结尾清单式连读多段；"
                "narration 第一句必须从时间表第 1 段对象内容直接讲起。"
            )
        length_rule = (
            f"全片 narration 验收区间 {narration_word_min}-{narration_word_max} 字；"
            "每段按时间表字数范围与三层写法写满（见下）。"
        )
    else:
        segment_rule = (
            "segments 为分句数组，每项含 segment_index 与 text；"
            "各段 text 按顺序拼接须与 narration 完全一致，口吻同样保持童趣；"
            "按自然断句切分，无需 visual 字段。"
        )
        opening_rule = (
            "开头用一句惊讶感叹或反常识吸引观众，迅速进入主题。"
            if opening
            else "禁止开头自我介绍；第一句直接进入主题。"
        )
        length_rule = (
            f"narration 总目标 {narration_word_target} 字；{writing_target_clause(narration_word_target)}；"
            f"验收区间 {narration_word_min}-{narration_word_max} 字（不含空格换行）；"
            f"低于 {narration_word_min} 字或高于 {narration_word_max} 字视为不合格；"
            f"{MATERIAL_LENGTH_RULE}"
        )
    system = (
        "你是给小朋友讲科普的视频口播编剧。视频画面已由用户上传的基底视频提供，无需描述画面。"
        "输出 JSON，字段：title, narration, segments。"
        f"{title_rule_text}"
        f"{length_rule}"
        f"{SCIENCE_CHILD_VOICE}"
        f"{ANTI_MEMOIR}"
        f"{MATERIAL_NO_JSON}"
        f"{opening_rule}"
        f"{segment_rule}"
        f"{material_timeline_system_clause(timeline) if timeline else ''}"
        f"{supplementary_system_clause(supplementary_info, bind_timeline=bool(timeline))}"
        f"{json_output_clause(MATERIAL_SCRIPT_JSON_EXAMPLE)}"
    )
    user_parts = [
        f"{title_user_prefix} narration 与分句 segments。",
    ]
    if not timeline:
        user_parts.append(
            storyboard_length_budget(
                narration_target=narration_word_target,
                content_style=CONTENT_STYLE_SCIENCE_CHILD,
            )
        )
    user = append_supplementary_to_user("\n\n".join(user_parts), supplementary_info)
    if timeline:
        cps = chars_per_sec if chars_per_sec is not None else DEFAULT_SPEECH_CHARS_PER_SEC
        user = append_material_timeline_to_user(user, timeline, chars_per_sec=cps)
    if feedback:
        user += f"\n\n上次不合格：{feedback}。请按要求重写。"
    return prompt_step("material_script", system, user)
