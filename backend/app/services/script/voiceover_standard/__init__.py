"""标准管线自由口播：提示词构建。"""

from __future__ import annotations

import json
import re
from typing import Any

from app.config import get_settings
from app.utils.media import (
    NARRATION_WRITING_TARGET_RATIO,
    default_narration_target_words,
    effective_segment_narration_sec,
    narration_accept_max_chars,
    narration_accept_min_chars,
    narration_word_range,
    narration_writing_target_chars,
)

from app.services.script.prompt_common import (
    append_supplementary_to_user,
    json_output_clause,
    prompt_step,
    resolve_script_profile,
    supplementary_system_clause,
    title_rule,
)
from app.services.script.voiceover_standard.styles import resolve_style_rules
from app.services.script.voiceover_standard.styles.common import (
    ANTI_MEMOIR,
    MATERIAL_SCRIPT_JSON_EXAMPLE,
    NARRATION_ONLY_JSON_EXAMPLE,
    NO_JSON,
)

__all__ = [
    "build_voiceover_standard_prompts",
    "build_voiceover_standard_expand_prompts",
    "build_voiceover_standard_shrink_prompts",
]


def _narration_char_count(text: str) -> int:
    return len(re.sub(r"\s+", "", text or ""))


def build_voiceover_standard_prompts(
    title: str,
    *,
    feedback: str | None = None,
    max_title_length: int | None = None,
    narration_target_words: int | None = None,
    supplementary_info: str | None = None,
    job: dict | None = None,
    orientation: str | None = None,
    content_style: str | None = None,
) -> dict[str, str]:
    """第一步：只生成口播全文（不含 segments，visual_style 已由后端硬编码）。"""
    settings = get_settings()
    _profile_orientation, profile_style = resolve_script_profile(
        job,
        orientation=orientation,
        content_style=content_style,
    )
    style = resolve_style_rules(profile_style)
    max_title = settings.max_title_length if max_title_length is None else max_title_length
    narration_word_target = (
        narration_target_words
        if narration_target_words is not None
        else default_narration_target_words(settings)
    )
    narration_word_min, narration_word_max = narration_word_range(narration_word_target)
    title_rule_text, title_user_prefix = title_rule(title, max_title)
    layers = style.layer_style
    length_rule = (
        f"口播总目标 {narration_word_target} 字；"
        f"验收硬区间 {narration_word_min}-{narration_word_max} 字（不含空格换行），"
        f"超标与不足均不合格；"
        f"【口播写法】全文连贯书写，按「{layers}」思路展开，用句号/问号/感叹号自然断句；"
        "不要输出 segments，后端会按单镜时长自动切分。"
        "word_count 必须等于 narration 实际字数（不含空格换行），禁止虚报。"
    )
    hard_min = narration_accept_min_chars(narration_word_target)
    writing_target = narration_writing_target_chars(narration_word_target)
    hard_max = narration_accept_max_chars(narration_word_target)
    pct = int(NARRATION_WRITING_TARGET_RATIO * 100)
    execution_headline = (
        f"【首要任务】口播总字数须落在 {hard_min}-{hard_max} 字硬区间内（写作目标约 {writing_target} 字），"
        f"超过 {hard_max} 字整稿作废，优先删例子/删并列知识点。"
        f"全文用连贯口播书写，按「{layers}」思路展开，用句号自然断句；"
        "不要输出 segments 字段，分镜由后端按单镜时长自动切分。"
        "输出前统计 narration 字数并核对 word_count。"
    )
    length_budget = (
        f"【字数预算】总目标 {narration_word_target} 字；"
        f"写作目标约 {writing_target} 字（总目标 {narration_word_target} 字的 {pct}%）；"
        f"验收区间 {hard_min}-{hard_max} 字（超出或不足均不合格）。\n"
        f"全文用「{layers}」写法连贯展开，不足可补细节，超标须删繁就简。\n"
        "【生成顺序】只写 narration 与 word_count，不要写 segments。\n"
        "【输出前硬性自检】①narration 字数在验收区间内；"
        "②word_count 等于 narration 实际字数；"
        "③口播无伪亲历/第一人称从业叙事。"
    )
    system = (
        f"{style.role}输出 JSON，字段：title, narration, word_count。"
        "口播总字数未落在验收硬区间内则整稿无效；禁止输出 segments 字段。"
        f"{title_rule_text}"
        f"{length_rule}"
        f"narration口吻：{style.voice}"
        f"{ANTI_MEMOIR}"
        f"{style.anti_rep}"
        f"{NO_JSON}"
        f"{style.structure}"
        "结构完整有开头结尾。"
        "禁止口播开头空泛自我介绍或冗长人设铺垫。"
        "本步只写口播，不写分镜与 image_prompt；visual_style 由后端写入，无需生成。"
        f"{supplementary_system_clause(supplementary_info)}"
        f"{json_output_clause(NARRATION_ONLY_JSON_EXAMPLE)}"
    )
    user = append_supplementary_to_user(
        (
            f"{execution_headline}\n\n"
            f"{length_budget}\n\n"
            f"{title_user_prefix}与完整口播 narration。"
        ),
        supplementary_info,
    )
    if feedback:
        user += f"\n\n上次不合格：{feedback}。请按要求重写。"
    return prompt_step("narration", system, user)


def build_voiceover_standard_expand_prompts(
    script: dict[str, Any],
    *,
    min_chars: int,
    mode: str = "narration_only",
    max_chars: int | None = None,
    job: dict | None = None,
    content_style: str | None = None,
) -> dict[str, str]:
    """初稿字数不足时专用扩写。

    mode:
      - narration_only：标准主路径（只扩 narration）
      - material：素材管线（按段扩 text，再拼 narration）
    """
    current = _narration_char_count(str(script.get("narration") or ""))
    deficit = max(1, min_chars - current)
    upper = (
        f"扩写后也勿超过 {max_chars} 字（硬上限）；够用即可，禁止注水。"
        if max_chars is not None and max_chars > min_chars
        else ""
    )
    if mode == "narration_only":
        _, profile_style = resolve_script_profile(job, content_style=content_style)
        style = resolve_style_rules(profile_style)
        system = (
            "你是口播扩写编辑。用户在初稿字数不足，须在保持主题与结构的前提下扩写。"
            "输出 JSON，字段：title, narration, word_count。"
            f"扩写后 narration 须至少 {min_chars} 字（不含空格换行），"
            f"当前仅 {current} 字，还差约 {deficit} 字。"
            f"{upper}"
            "规则：只扩写 narration，补具体细节、案例、步骤或结论，禁止删减已有核心信息；"
            "不要输出 segments；word_count 等于 narration 实际字数。"
            f"narration口吻：{style.voice}"
            f"{style.anti_rep}"
            f"{ANTI_MEMOIR}"
            f"{NO_JSON}"
            f"{json_output_clause(NARRATION_ONLY_JSON_EXAMPLE)}"
        )
        draft = {
            "title": script.get("title"),
            "narration": script.get("narration"),
            "word_count": script.get("word_count"),
        }
        user = (
            "当前稿件（字数不足，请扩写 narration）：\n"
            f"{json.dumps(draft, ensure_ascii=False, indent=2)}"
        )
        return prompt_step("narration_expand", system, user)

    if mode != "material":
        raise ValueError(f"unsupported expand mode: {mode!r}")

    system = (
        "你是口播扩写编辑。用户在初稿字数不足，须在保持主题与分镜结构的前提下扩写。"
        "输出 JSON，字段与输入一致（title, narration, word_count, segments）。"
        f"扩写后 narration 须至少 {min_chars} 字（不含空格换行），"
        f"当前仅 {current} 字，还差约 {deficit} 字。"
        f"{upper}"
        "规则：segments 段数与 segment_index 不得减少、不得合并；"
        "每段 text 只能扩写（补具体细节、案例、步骤或结论），禁止删减已有核心信息；"
        "narration 为各段 text 按顺序原样拼接；word_count 等于 narration 实际字数。"
        f"{ANTI_MEMOIR}"
        f"{json_output_clause(MATERIAL_SCRIPT_JSON_EXAMPLE)}"
    )
    draft = {
        "title": script.get("title"),
        "narration": script.get("narration"),
        "word_count": script.get("word_count"),
        "segments": script.get("segments"),
    }
    user = (
        "当前稿件（字数不足，请扩写）：\n"
        f"{json.dumps(draft, ensure_ascii=False)}\n\n"
        f"请扩写至至少 {min_chars} 字后输出完整 JSON。"
    )
    return prompt_step("expand_material", system, user)


def build_voiceover_standard_shrink_prompts(
    script: dict[str, Any],
    *,
    segment_indices: list[int],
    cap: int,
    segment_target_sec: float,
    job: dict | None = None,
    content_style: str | None = None,
) -> dict[str, str]:
    """略超限分镜专用缩字（只改 text，保留 visual_brief 等字段）。"""
    _, profile_style = resolve_script_profile(job, content_style=content_style)
    voice_rule = resolve_style_rules(profile_style).voice
    by_idx = {
        int(seg["segment_index"]): seg
        for seg in script.get("segments") or []
        if seg.get("segment_index") is not None
    }
    targets: list[dict[str, Any]] = []
    for idx in segment_indices:
        seg = by_idx.get(idx)
        if not seg:
            continue
        text = str(seg.get("text") or "")
        targets.append(
            {
                "segment_index": idx,
                "text": text,
                "chars": _narration_char_count(text),
                "max_chars": cap,
            }
        )
    narration_sec = effective_segment_narration_sec(segment_target_sec)
    sec = int(narration_sec) if narration_sec == int(narration_sec) else narration_sec
    system = (
        "你是口播缩字编辑。指定分镜口播略超单镜时长上限，只做删字瘦身，禁止改写文风。"
        '输出 JSON：{"segments": [{"segment_index": 序号, "text": "缩短后的口播"}, ...]}。'
        f"每段 text 不得超过 {cap} 字（不含空格换行）。"
        "【文风·最高优先级】必须完整保留原句的语气、节奏、人称与修辞习惯；"
        "禁止把口语改成书面语、禁止换成另一种叙述风格。"
        f"当前口吻要求：{voice_rule}"
        "只允许删重复比喻、次要形容词和冗余连接词；禁止改变科学事实与核心信息；"
        "禁止增删 segment_index；不要输出 narration、visual_brief 等其他字段。"
        f"{ANTI_MEMOIR}"
        f"{NO_JSON}"
    )
    user = (
        f"单镜口播上限 {sec}s（每段 text 最多 {cap} 字）。"
        "在完全保持原文风与口吻的前提下缩短以下分镜 text，并输出 JSON：\n"
        f"{json.dumps(targets, ensure_ascii=False)}"
    )
    return prompt_step("segment_shrink", system, user)
