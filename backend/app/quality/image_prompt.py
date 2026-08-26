"""script 阶段：文生图提示词质检与长度阈值。"""

from __future__ import annotations

import re

from app.quality.models import QualityReport

MIN_IMAGE_PROMPT_CHARS = 50
IMAGE_PROMPT_PASS_CHARS = 150
IMAGE_PROMPT_TARGET_CHARS = 300
MIN_IMAGE_PROMPT_CHARS_SD15 = 20
IMAGE_PROMPT_TARGET_CHARS_SD15 = 60
MIN_SD15_PROMPT_EN_WORDS = 8
TARGET_SD15_PROMPT_EN_WORDS = 12

__all__ = [
    "IMAGE_PROMPT_PASS_CHARS",
    "IMAGE_PROMPT_TARGET_CHARS",
    "MIN_IMAGE_PROMPT_CHARS",
    "MIN_SD15_PROMPT_EN_WORDS",
    "TARGET_SD15_PROMPT_EN_WORDS",
    "check_image_prompt",
    "audit_image_prompt_slots",
    "register_opposite_pair",
    "collect_motion_prompt_issues",
    "format_image_prompt_retry_warning",
    "generic_motion_prompt_issue",
    "image_prompt_min_chars",
    "image_prompt_pass_chars",
    "image_prompt_target_chars",
    "sd15_prompt_en_ok",
    "sd15_prompt_en_word_count",
    "skip_image_prompt_check",
]

_GENERIC_MOTION_FILLER_RE = re.compile(
    r"^(?:镜头固定[，,、]?)?主体稳定[，,、]?画面平滑[。．.]?$|"
    r"^镜头固定(?:或极?[轻缓]?慢?(?:推进|拉远|平移))?[，,、]?主体(?:清晰)?稳定[，,、]?画面平滑[。．.]?$"
)

# 检测 motion_prompt 中描述人物/主体主动作的模式
# 身体部位 + 动作，或角色名词 + 动作
_CHAR_ACTION_RE = re.compile(
    r"(?:手指|手掌|手臂|脚|脚趾|腿|头部|眼睛|嘴巴|肩膀|手腕|"
    r"小偷|人物|角色|少女|少年|老人|孩子|男子|女子|小孩|"
    r"凶手|受害者|侦探|士兵|将军|皇帝|刺客|猎人|骑士)"
    r".{0,6}"
    r"(?:弯曲|伸直|转身|奔跑|抓握|拿起|放下|抬起|挥动|踢|"
    r"走|跑|跳|站|坐|躺|爬|蹲|跪|闪躲|攻击|"
    r"睁开|闭上|张开|握紧|捏|指|踩|踢)"
)

# 检测 motion_prompt 中使用抽象视觉特效词而非具体物体微动的模式
_ABSTRACT_VFX_RE = re.compile(
    r"(?:光效|光晕|图标|UI元素|ui元素|特效|粒子|能量|光圈|光环|"
    r"脉动|辉光|光束扫射|光束扫过|光柱扫过|光柱扫射|呼吸感)"
)

# ── L1 结构审核（槽位拼装后、出图前） ──
_MOUTH_OPEN_WORDS = ("龇牙", "咧嘴", "张嘴", "张口", "大笑", "露齿", "吐舌")
_MOUTH_CLOSED_MARK = "嘴巴自然闭合"

# 对立谓词对：同一条提示词同时命中两个即矛盾（major）。
# L2 审出新矛盾后可 register_opposite_pair() 自动沉淀。
_OPPOSITE_PHRASE_PAIRS: list[tuple[str, str]] = [
    ("没有任何物品", "放着"),
    ("空无一物", "放着"),
    ("赤脚", "穿着运动鞋"),
    ("翘起", "贴地"),
    ("扯起", "贴地"),
]


def register_opposite_pair(a: str, b: str) -> None:
    """L2 审出新矛盾时把 (名词, 谓词对) 沉淀回表，供后续 L1 复用。"""
    pair = (a, b)
    if pair not in _OPPOSITE_PHRASE_PAIRS:
        _OPPOSITE_PHRASE_PAIRS.append(pair)


def _redundant_ngrams(prompt: str, n: int = 6, threshold: int = 3) -> list[str]:
    text = prompt or ""
    counts: dict[str, int] = {}
    for i in range(len(text) - n + 1):
        gram = text[i : i + n]
        if len(set(gram)) == 1:
            continue
        if any(ch in gram for ch in "，。；;、："):
            continue
        counts[gram] = counts.get(gram, 0) + 1
    return sorted(g for g, c in counts.items() if c >= threshold)


def audit_image_prompt_slots(prompt: object) -> list[dict]:
    """L1 结构审核：口型冲突 / 对立谓词 / n-gram 冗余。

    返回 issue 列表，每项 {level, kind, ...}；level 为 minor / major。
    """
    if not isinstance(prompt, str) or not prompt.strip():
        return [{"level": "major", "kind": "empty", "detail": "image_prompt empty"}]
    text = prompt
    issues: list[dict] = []
    if _MOUTH_CLOSED_MARK in text:
        for w in _MOUTH_OPEN_WORDS:
            if w in text:
                issues.append({"level": "major", "kind": "mouth_conflict", "word": w})
                break
    for a, b in _OPPOSITE_PHRASE_PAIRS:
        if a in text and b in text:
            issues.append({"level": "major", "kind": "opposite", "pair": [a, b]})
    for g in _redundant_ngrams(text):
        issues.append({"level": "minor", "kind": "redundancy", "gram": g})
    return issues


def image_prompt_min_chars(*, sd15_mode: bool = False) -> int:
    return MIN_IMAGE_PROMPT_CHARS_SD15 if sd15_mode else MIN_IMAGE_PROMPT_CHARS


def image_prompt_target_chars(*, sd15_mode: bool = False) -> int:
    return IMAGE_PROMPT_TARGET_CHARS_SD15 if sd15_mode else IMAGE_PROMPT_TARGET_CHARS


def image_prompt_pass_chars(*, sd15_mode: bool = False) -> int:
    return IMAGE_PROMPT_TARGET_CHARS_SD15 if sd15_mode else IMAGE_PROMPT_PASS_CHARS


def sd15_prompt_en_word_count(value: object) -> int:
    if not isinstance(value, str):
        return 0
    text = value.strip()
    if not text:
        return 0
    return len(text.split())


def sd15_prompt_en_ok(value: object) -> bool:
    return sd15_prompt_en_word_count(value) >= MIN_SD15_PROMPT_EN_WORDS


def generic_motion_prompt_issue(
    prompt: object,
    *,
    allow_character_action: bool = False,
) -> str | None:
    """检测 motion_prompt 是否为无信息套话或包含人物主动作。"""
    if not isinstance(prompt, str):
        return "motion_prompt missing"
    text = prompt.strip()
    if not text:
        return "motion_prompt empty"
    if _GENERIC_MOTION_FILLER_RE.match(text):
        return "套话填空，须描述画面内具体微动"
    stability = ("镜头固定", "主体稳定", "画面平滑")
    if all(word in text for word in stability) and len(text) <= 28:
        return "套话填空，须描述画面内具体微动"
    if not allow_character_action and _CHAR_ACTION_RE.search(text):
        return "禁止描述人物或主体的主动作，只写环境元素微动（如烟雾、光影、水流、尘埃等）"
    if _ABSTRACT_VFX_RE.search(text):
        return "禁止使用抽象视觉特效词（光效/光晕/图标/UI元素/粒子/能量等），须写画面中真实可见物体的物理微动"
    return None


def collect_motion_prompt_issues(segments: list[dict]) -> list[str]:
    """汇总各段 motion_prompt 套话与雷同问题。"""
    from app.utils.job_info import is_keyframe_segment

    issues: list[str] = []
    by_motion: dict[str, list[object]] = {}
    for seg in segments:
        idx = seg.get("segment_index")
        motion = str(seg.get("motion_prompt") or "").strip()
        issue = generic_motion_prompt_issue(
            motion,
            allow_character_action=is_keyframe_segment(seg),
        )
        if issue:
            issues.append(f"segment {idx}: {issue}")
        if motion:
            by_motion.setdefault(motion, []).append(idx)
    for motion, indices in by_motion.items():
        if len(indices) >= 3:
            joined = ",".join(str(i) for i in indices)
            issues.append(f"segments [{joined}] motion_prompt 完全相同，须按画面差异化")
    return issues


def _image_prompt_threshold_label(*, sd15_mode: bool = False) -> str:
    min_chars = image_prompt_min_chars(sd15_mode=sd15_mode)
    pass_chars = image_prompt_pass_chars(sd15_mode=sd15_mode)
    target_chars = image_prompt_target_chars(sd15_mode=sd15_mode)
    label = f"image_prompt>={min_chars}chars(pass{pass_chars},target{target_chars})"
    if sd15_mode:
        label += (
            f" sd15_prompt_en>={MIN_SD15_PROMPT_EN_WORDS}words"
            f"(target{TARGET_SD15_PROMPT_EN_WORDS})"
        )
    return label


def _format_image_prompt_retry_segments(segments: list[dict]) -> str:
    parts: list[str] = []
    for item in segments:
        idx = item.get("segment_index")
        metrics: list[str] = []
        if "chars" in item:
            metrics.append(f"{item['chars']}chars")
        if "words" in item:
            metrics.append(f"{item['words']}words")
        if metrics:
            parts.append(f"#{idx}({','.join(metrics)})")
        else:
            parts.append(f"#{idx}")
    return ", ".join(parts)


def format_image_prompt_retry_warning(
    *,
    attempt: int,
    reason: str,
    segments: list[dict],
    sd15_mode: bool = False,
) -> str:
    return (
        f"[SCRIPT] image_prompt retry attempt={attempt} reason={reason} "
        f"threshold={_image_prompt_threshold_label(sd15_mode=sd15_mode)} "
        f"segments=[{_format_image_prompt_retry_segments(segments)}]"
    )


def check_image_prompt(
    script: dict,
    *,
    sd15_mode: bool | None = None,
    segment_indices: list[int] | None = None,
    content_style: str | None = None,
) -> QualityReport:
    """各段 image_prompt 长度；SD15 模式另校验 sd15_prompt_en；daily 校验角色入画。"""
    if sd15_mode is None:
        sd15_mode = bool(script.get("include_sd15_prompt"))
    min_chars = image_prompt_min_chars(sd15_mode=sd15_mode)
    pass_chars = image_prompt_pass_chars(sd15_mode=sd15_mode)
    target_chars = image_prompt_target_chars(sd15_mode=sd15_mode)
    segments = script.get("segments") or []
    if segment_indices is not None:
        wanted = {int(idx) for idx in segment_indices}
        segments = [
            seg
            for seg in segments
            if int(seg.get("segment_index", -1)) in wanted
        ]
    if not segments:
        return QualityReport(
            level="major",
            step="image_prompts",
            fail_stage="script",
            details={"reason": "no segments"},
        )

    style = content_style or script.get("content_style")
    if style == "daily_story":
        from app.services.daily_story.speaker import (
            annotate_sticky_stage_speakers,
            collect_speaker_leak_segments,
        )

        annotate_sticky_stage_speakers(
            script.get("segments") or [],
            setting=str(script.get("setting") or "").strip() or None,
        )
        speaker_rows = collect_speaker_leak_segments(
            segments,
            check_visual_brief=False,
            check_image_prompt=True,
        )
        if speaker_rows:
            return QualityReport(
                level="major",
                step="image_prompts",
                fail_stage="script",
                details={
                    "reason": "daily speaker leak in image_prompt",
                    "issues": [
                        f"segment {r['segment_index']}: {r['field']} 含未授权角色 "
                        f"{r['leaks']} (cast={r['speakers'] or '[]'})"
                        for r in speaker_rows
                    ],
                    "segments": speaker_rows,
                },
            )

    too_short: list[dict] = []
    slightly_short: list[dict] = []
    missing_sd15: list[dict] = []
    bad_sd15: list[dict] = []
    weak_sd15: list[dict] = []
    for seg in segments:
        idx = seg.get("segment_index")
        prompt_len = len(str(seg.get("image_prompt") or ""))
        if prompt_len < min_chars:
            too_short.append(
                {
                    "segment_index": idx,
                    "chars": prompt_len,
                    "min_chars": min_chars,
                }
            )
        elif prompt_len < pass_chars:
            slightly_short.append(
                {
                    "segment_index": idx,
                    "chars": prompt_len,
                    "pass_chars": pass_chars,
                    "target_chars": target_chars,
                }
            )
        if sd15_mode:
            words = sd15_prompt_en_word_count(seg.get("sd15_prompt_en"))
            if words == 0:
                missing_sd15.append({"segment_index": idx, "words": 0})
            elif words < MIN_SD15_PROMPT_EN_WORDS:
                bad_sd15.append({"segment_index": idx, "words": words})
            elif words < TARGET_SD15_PROMPT_EN_WORDS:
                weak_sd15.append({"segment_index": idx, "words": words})

    if bad_sd15:
        return QualityReport(
            level="major",
            step="image_prompts",
            fail_stage="script",
            details={
                "reason": "sd15_prompt_en too short",
                "segments": bad_sd15,
            },
        )
    if too_short:
        return QualityReport(
            level="major",
            step="image_prompts",
            fail_stage="script",
            details={"reason": "image_prompt too short", "segments": too_short},
        )
    if missing_sd15:
        return QualityReport(
            level="minor",
            step="image_prompts",
            details={
                "reason": "sd15_prompt_en missing, fallback at image gen",
                "segments": missing_sd15,
            },
        )
    if weak_sd15:
        return QualityReport(
            level="minor",
            step="image_prompts",
            details={
                "reason": "sd15_prompt_en slightly short",
                "segments": weak_sd15,
                "target_words": TARGET_SD15_PROMPT_EN_WORDS,
            },
        )
    if slightly_short:
        return QualityReport(
            level="minor",
            step="image_prompts",
            details={
                "reason": "image_prompt slightly short",
                "segments": slightly_short,
            },
        )
    # L1 结构审核：口型冲突 / 对立谓词 / n-gram 冗余
    l1_major: list[dict] = []
    l1_minor: list[dict] = []
    for seg in segments:
        idx = seg.get("segment_index")
        for issue in audit_image_prompt_slots(seg.get("image_prompt")):
            row = {"segment_index": idx, **issue}
            (l1_major if issue["level"] == "major" else l1_minor).append(row)
    if l1_major:
        return QualityReport(
            level="major",
            step="image_prompts",
            fail_stage="script",
            details={
                "reason": "L1 image_prompt conflict",
                "issues": l1_major,
            },
        )
    if l1_minor:
        return QualityReport(
            level="minor",
            step="image_prompts",
            details={
                "reason": "L1 image_prompt redundancy",
                "issues": l1_minor,
            },
        )
    return QualityReport(
        level="pass",
        step="image_prompts",
        details={"segment_count": len(segments)},
    )


def skip_image_prompt_check() -> QualityReport:
    """未勾选生成文生图提示词时，跳过相关质检。"""
    return QualityReport(
        level="pass",
        step="image_prompts",
        details={"reason": "skipped", "generate_image_prompts": False},
    )
