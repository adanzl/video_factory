"""金故事结构类型纠偏：M2+C 误判为武力压制时应落 M8+J。"""

from __future__ import annotations

import copy
import re
from typing import Any, cast

from app.services.daily_story.gold_story.types import (
    allowed_structure_types,
    normalize_structure_type,
)

_RE_C_BOOMERANG = re.compile(
    r"你刚说|你不是说|那不一样|哪里不一样|你定的|规矩是你|"
    r"回旋镖.*原话|引用.*原话|堵截"
)
_RE_C_DUAL_FAIR = re.compile(
    r"(公平|凭什么|归谁|谁先|应该给我).{0,40}(公平|凭什么|归谁|谁先|应该给我)",
    re.DOTALL,
)
_RE_DOMINATION = re.compile(
    r"打|拳|肘击|踢|按倒|锁住|扭打|ko|压制|镇住|一锤|最强形态|"
    r"草莓熊|互毁|互打",
    re.IGNORECASE,
)
_RE_SURRENDER = re.compile(r"我输了|认输|不敢再|怂|服软|败下阵来?|当场")
_RE_WINNER_RULE = re.compile(r"谁赢了?谁说了算|谁赢谁|赢了说了算|胜者为王")
_RE_DEFERRED_GRUDGE = re.compile(r"等我长大|以后再|再跟你算账|忍气吞声|来日再")


def classification_blob(
    *,
    story_raw: str = "",
    beat: list[Any] | None = None,
    conflict_core: str = "",
    mapping_note: str = "",
    closing_intent: str = "",
    dialogue_seed: list[Any] | None = None,
) -> str:
    parts = [
        str(story_raw or ""),
        str(conflict_core or ""),
        str(mapping_note or ""),
        str(closing_intent or ""),
    ]
    for item in beat or []:
        parts.append(str(item))
    for row in dialogue_seed or []:
        if isinstance(row, dict):
            parts.append(str(row.get("intent") or row.get("beat") or ""))
    return "\n".join(parts)


def suggests_c_fairness_boomerang(blob: str) -> bool:
    text = str(blob or "")
    if _RE_C_BOOMERANG.search(text):
        return True
    if _RE_C_DUAL_FAIR.search(text):
        return True
    fair_hits = len(re.findall(r"公平|凭什么|归谁|你先|我先|应该给我", text))
    return fair_hits >= 3 and not _RE_DOMINATION.search(text)


def suggests_m8_j_domination(blob: str) -> bool:
    text = str(blob or "")
    if not _RE_DOMINATION.search(text):
        return False
    if _RE_C_BOOMERANG.search(text):
        return False
    has_outcome = bool(
        _RE_SURRENDER.search(text)
        or _RE_WINNER_RULE.search(text)
        or _RE_DEFERRED_GRUDGE.search(text)
    )
    if not has_outcome:
        return False
    if _RE_DEFERRED_GRUDGE.search(text):
        return True
    if _RE_WINNER_RULE.search(text):
        return True
    return bool(_RE_SURRENDER.search(text))


def should_reclassify_m2_c_to_m8_j(
    *,
    mechanism: str,
    structure_type: str,
    blob: str,
) -> bool:
    mech = str(mechanism or "").strip().upper()
    st = str(structure_type or "").strip().upper()
    if mech != "M2" or st != "C":
        return False
    if not suggests_m8_j_domination(blob):
        return False
    if suggests_c_fairness_boomerang(blob):
        return False
    return True


def _sync_scene_contract_story_type(
    payload: dict[str, Any],
    target: str,
    notes: list[str],
) -> None:
    sc = payload.get("scene_contract")
    if not isinstance(sc, dict):
        return
    sc = copy.deepcopy(sc)
    sc_type = str(sc.get("story_type") or "").strip().upper()
    if sc_type and sc_type != target:
        sc["story_type"] = target
        notes.append(f"scene_contract.story_type:{sc_type}→{target}")
    payload["scene_contract"] = sc


def resolve_h3_structure(
    h3: dict[str, Any],
    *,
    story_raw: str = "",
) -> tuple[dict[str, Any], list[str]]:
    """H3 后处理：武力压制误标 M2+C → M8+J。"""
    notes: list[str] = []
    out = dict(h3)
    blob = classification_blob(
        story_raw=story_raw,
        beat=out.get("beat") if isinstance(out.get("beat"), list) else [],
        conflict_core=str(out.get("conflict_core") or ""),
        mapping_note=str(out.get("structure_mapping_note") or ""),
    )
    if not should_reclassify_m2_c_to_m8_j(
        mechanism=str(out.get("mechanism") or ""),
        structure_type=str(out.get("structure_type") or ""),
        blob=blob,
    ):
        return out, notes

    out["mechanism"] = "M8"
    out["structure_type"] = "J"
    notes.append("mechanism:M2→M8+structure:C→J(domination-not-fairness)")
    note = str(out.get("structure_mapping_note") or "").strip()
    extra = "武力压制单方定规+认输收场，非 C 双规则回旋镖"
    out["structure_mapping_note"] = f"{note}；{extra}".strip("；") if note else extra
    return out, notes


def resolve_structure_row(row: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """已入库金稿纠偏 mechanism/structure_type（含 payload.scene_contract）。"""
    notes: list[str] = []
    out = dict(row)
    payload = cast(dict[str, Any], out.get("payload") or {})
    payload = copy.deepcopy(payload)

    blob = classification_blob(
        story_raw=str(payload.get("story_raw") or ""),
        beat=payload.get("beat") if isinstance(payload.get("beat"), list) else [],
        conflict_core=str(out.get("conflict_core") or ""),
        mapping_note=str(payload.get("structure_mapping_note") or ""),
        closing_intent=str(payload.get("closing_intent") or ""),
        dialogue_seed=payload.get("dialogue_seed")
        if isinstance(payload.get("dialogue_seed"), list)
        else None,
    )
    mechanism = str(out.get("mechanism") or "").strip().upper()
    current = str(out.get("structure_type") or "").strip().upper()
    if not should_reclassify_m2_c_to_m8_j(
        mechanism=mechanism,
        structure_type=current,
        blob=blob,
    ):
        out["payload"] = payload
        return out, notes

    target_mech = "M8"
    target_st = "J"
    if target_st not in allowed_structure_types(target_mech):
        out["payload"] = payload
        return out, notes

    normalize_structure_type(target_st)
    out["mechanism"] = target_mech
    out["structure_type"] = target_st
    notes.append(f"mechanism:{mechanism}→{target_mech}+structure:{current}→{target_st}")

    note = str(payload.get("structure_mapping_note") or "").strip()
    extra = "武力压制单方定规+认输收场，非 C 双规则回旋镖"
    if extra not in note:
        payload["structure_mapping_note"] = f"{note}；{extra}".strip("；") if note else extra

    _sync_scene_contract_story_type(payload, target_st, notes)
    out["payload"] = payload
    return out, notes
