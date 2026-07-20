"""分镜画面概述规则与构建函数。"""

from __future__ import annotations

_VISUAL_BRIEF_RULE = (
    "各段含segment_index,text,visual_brief,visual_mode=static_motion；"
    "各段text按顺序拼接须与narration全文一致。"
    "visual_brief为该镜画面描述（80-150字）：写清视觉主旨、关键动作或对比关系、"
    "场景类型与情绪，帮助后续扩写文生图提示词；不写镜头焦距、光线方向、材质参数等细节。"
)


# ── JSON 样例 ─────────────────────────────────────────────────────

_VISUAL_BRIEF_JSON_EXAMPLE_FULL = """{
  "segments": [
    {"segment_index": 1, "visual_brief": "画面主旨与关键视觉（80-150字）", "visual_mode": "static_motion"},
    {"segment_index": 2, "visual_brief": "画面主旨", "visual_mode": "static_motion"}
  ]
}

注意：segments 须覆盖输入的每一段，segment_index 一一对应；不要修改各段 text。"""

_VISUAL_BRIEF_JSON_EXAMPLE_PARTIAL = """{
  "segments": [
    {"segment_index": 2, "visual_brief": "画面主旨与关键视觉（80-150字）", "visual_mode": "static_motion"}
  ]
}

注意：仅输出标记为【需生成】的 segment；【仅上下文】无需输出；不要修改各段 text。"""


# ── builders（常量须在上方）───────────────────────────────────────

from typing import Any

from app.utils.job_info import (
    CONTENT_STYLE_DAILY_STORY,
)

from app.services.script.prompt_common import (
    append_supplementary_to_user,
    json_output_clause,
    prompt_step,
    resolve_script_profile,
    supplementary_system_clause,
)
from app.services.script.voiceover_standard.styles import resolve_style_rules


_DAILY_CAST_RULE = (
    "【角色入画】本段画面人物必须且仅等于 dialogue 中的发言角色"
    "（speaker 去重后的集合）；未发言角色禁止以任何形式入画"
    "（旁观、路过、背景、另一房间等都不允许）。"
    "台词中提及某人姓名不等于其在该段发言；仅以 dialogue.speaker 为准。"
    "妈妈同样遵守：仅 speaker=\"妈妈\" 时才可入画；"
    "若该段无人发言，visual_brief 禁止出现昭昭/灿灿/妈妈等人像，只写场景。"
)

_DEFAULT_MOM_RULE = (
    "【角色约束】妈妈角色只在该段有妈妈台词（dialogue中speaker=\"妈妈\"）时才出现在画面中；"
    "若该段dialogue数组中没有speaker为妈妈的项，则visual_brief绝对禁止出现妈妈（包括不让妈妈旁观、路过、做背景动作、"
    "在厨房方向、在另一房间等任何形式）。特别注意：台词中提及「妈妈」字样（如\"妈妈说…\"）不等于妈妈在该段说话，"
    "妈妈未发言时不可出现在该段画面中。"
)


def _format_one_visual_brief_segment(
    seg: dict,
    *,
    prefix: str = "",
    include_dialogue: bool = False,
) -> str:
    idx = seg.get("segment_index")
    text = str(seg.get("text") or "")
    line = f"{prefix}segment {idx}: text={text!r}"
    if include_dialogue:
        speakers = sorted(
            {
                str(d.get("speaker") or "").strip()
                for d in (seg.get("dialogue") or [])
                if str(d.get("speaker") or "").strip()
            }
        )
        line += f"; speakers={speakers!r}"
    return line


def format_visual_brief_segments_for_prompt(
    segments: list[dict],
    *,
    include_dialogue: bool = False,
    segment_indices: list[int] | None = None,
) -> str:
    ordered = sorted(
        segments,
        key=lambda seg: int(seg.get("segment_index") or seg.get("index") or 0),
    )
    if segment_indices is None:
        return "\n".join(
            _format_one_visual_brief_segment(seg, include_dialogue=include_dialogue)
            for seg in ordered
        )

    wanted = {int(idx) for idx in segment_indices}
    max_idx = max(
        (int(seg.get("segment_index") or 0) for seg in ordered),
        default=0,
    )
    extra: set[int] = set()
    for idx in wanted:
        if idx - 1 >= 1:
            extra.add(idx - 1)
        if idx + 1 <= max_idx:
            extra.add(idx + 1)
    extra -= wanted
    shown = wanted | extra

    lines: list[str] = []
    for seg in ordered:
        idx = int(seg.get("segment_index") or 0)
        if idx not in shown:
            continue
        tag = "【仅上下文】" if idx in extra else "【需生成】"
        lines.append(
            _format_one_visual_brief_segment(
                seg,
                prefix=tag,
                include_dialogue=include_dialogue,
            )
        )
    return "\n".join(lines)


def build_visual_brief_prompts(
    script: dict[str, Any],
    *,
    feedback: str | None = None,
    supplementary_info: str | None = None,
    job: dict | None = None,
    orientation: str | None = None,
    content_style: str | None = None,
    segment_indices: list[int] | None = None,
) -> dict[str, str]:
    """第二步：基于已切分的 segments 与全文 narration 生成 visual_brief。

    segment_indices 非空时只要求 LLM 输出这些段（邻段作上下文）。
    """
    _profile_orientation, profile_style = resolve_script_profile(
        job,
        orientation=orientation,
        content_style=content_style,
    )
    segments = script.get("segments") or []
    narration = str(script.get("narration") or "").strip()
    visual_style = str(script.get("visual_style") or "").strip()
    title = str(script.get("title") or "").strip()
    cast_rule = (
        _DAILY_CAST_RULE
        if profile_style == CONTENT_STYLE_DAILY_STORY
        else _DEFAULT_MOM_RULE
    )
    partial = segment_indices is not None
    coverage = (
        "segments 仅需输出标记为【需生成】的分镜；【仅上下文】分段无需输出；"
        if partial
        else "segments 为分镜数组，须与输入逐段一一对应；"
    )
    seg_rule = (
        f"{coverage}"
        "各段含 segment_index, visual_brief, visual_mode=static_motion；"
        "不要输出或修改各段 text。"
        f"visual_brief 为该镜画面描述（80-150 字）：写清视觉主旨、关键动作或对比关系、"
        f"场景类型；情绪须对标台词语气强度（争吵时表情激烈如瞪眼皱眉张嘴、温和平静时表情放松）。"
        f"{cast_rule}"
        "须通读全文 narration，保证相邻分镜画面衔接自然、叙事节奏连贯，"
        "避免前后镜主体/场景毫无关联的跳跃；"
        "同时每镜 visual_brief 只表达本段 text 内容，禁止提前画后续段落情节。"
    )
    example = (
        _VISUAL_BRIEF_JSON_EXAMPLE_PARTIAL
        if partial
        else _VISUAL_BRIEF_JSON_EXAMPLE_FULL
    )
    system = (
        f"{resolve_style_rules(profile_style).role}输出 JSON，字段：segments。"
        f"{seg_rule}"
        f"{supplementary_system_clause(supplementary_info)}"
        f"{json_output_clause(example)}"
    )
    seg_lines = format_visual_brief_segments_for_prompt(
        segments,
        include_dialogue=(profile_style == CONTENT_STYLE_DAILY_STORY),
        segment_indices=segment_indices,
    )
    user = append_supplementary_to_user(
        (
            f"标题：{title}\n"
            f"全片 visual_style：{visual_style or '（待你输出）'}\n\n"
            f"【口播全文 narration】（供把握画面节奏与连贯性，勿改写）：\n{narration}\n\n"
            f"【各分镜口播 text】（已固定，须按标记生成 visual_brief）：\n"
            f"{seg_lines}"
        ),
        supplementary_info,
    )
    if feedback:
        user += f"\n\n上次不合格：{feedback}。请按要求重写。"
    return prompt_step("visual_brief", system, user)
