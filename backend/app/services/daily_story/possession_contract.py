"""C 类整件物·阶段化占有契约（closed-loop P0，2026-08-21）。

opening 严（intent/reach），body 活（contact→control→complete）。
全层只读本模块常量；禁止在 line/validate/patch 各写一套判据。
"""

from __future__ import annotations

import re

CONTRACT_VERSION = "possession_stage_v1"

OPENING_STAGES = ("intent", "reach")
BODY_STAGES = ("contact", "control", "complete")

# 整件物末四拍：哪条作数→回收初始规则→回旋镖→嘴硬（L15–L18）
FINAL_FOUR_ROLES = ("which_rule", "reclaim", "boomerang", "stubborn")
FINAL_FOUR_SPEAKER_SLOTS = ("opp", "maker", "opp", "maker")

# preview 熔断兜底；不进 prompt few-shot（P0-6）
BREAKER_OPENING_PAIR = (
    "姐姐和弟弟同时朝沙发上的抱枕伸手，两人的手都还离抱枕有一段距离。",
    "姐弟俩一起伸手去抢那个抱枕，抱枕仍留在沙发上一动不动。",
)

_POSSESS_COMPLETE_OPENING_RE = re.compile(
    r"我(?:先|就|都|已经|早就)?(?:拿到|攥住|攥着|攥手里|握着|抢到|抓住|拿到手|到手|抱住了|抱在怀里|抱进怀里)",
)


def whole_item_anchor(text: str) -> bool:
    from app.services.daily_story.story_types.c.validate import _RE_WHOLE_ITEM_ANCHOR

    return bool(_RE_WHOLE_ITEM_ANCHOR.search(text or ""))


def append_whole_item_opening_prevalidate_errors(
    normalized: list[dict],
    *,
    setting: str = "",
    conflict_core: str = "",
    errors: list[str],
) -> None:
    """P0-2：opening 前 2 句判据句检测 + 同时伸手 setting 禁占有完成态。"""
    anchor = f"{setting}{conflict_core}"
    if not whole_item_anchor(anchor):
        return
    lines = [str(d.get("line") or "") for d in normalized[:2]]
    if not lines:
        return

    from app.services.daily_story.story_types.c.validate import _criterion_drift_error
    from app.services.daily_story.story_types.c.opening import _opening_setting_holder

    drift = _criterion_drift_error(lines, phase="opening")
    if drift:
        errors.append(f"opening P0-2 {drift}")
        return

    if _opening_setting_holder(setting) is not None:
        return

    for i, ln in enumerate(lines):
        if _POSSESS_COMPLETE_OPENING_RE.search(ln):
            errors.append(
                f"opening[{i}] C类整件物开场须 intent/reach（未接触竞争），"
                "禁占有完成态（我先拿到/我抱住了等）——与「同时伸手」setting 矛盾"
            )
            break


def align_whole_item_final_four_speakers(
    dialogue: list,
    *,
    maker: str,
    opp: str,
) -> list[str]:
    """末四拍 speaker 按 L15–L18 槽位对齐：对方→立规人→对方→立规人。"""
    notes: list[str] = []
    if len(dialogue) < 4:
        return notes
    role_labels = ("哪条作数", "回收规则", "回旋镖", "嘴硬")
    expected = [opp, maker, opp, maker]
    for i, exp_sp in enumerate(expected):
        item = dialogue[-4 + i]
        if not isinstance(item, dict):
            continue
        cur = str(item.get("speaker") or "").strip()
        if cur != exp_sp:
            item["speaker"] = exp_sp
            notes.append(f"整件物末四拍·{role_labels[i]}→{exp_sp}")
    return notes
