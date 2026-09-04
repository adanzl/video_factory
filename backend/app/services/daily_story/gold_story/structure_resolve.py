"""金故事结构类型纠偏：M2+C 误判武力压制→M8+J；正经胡说→M6+N；
目标错位→M13+O。"""

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
_RE_SOLEMN_NONSENSE = re.compile(
    r"一本正经|正经胡说|荒诞逻辑|无厘头|童趣逻辑|跳跃逻辑|"
    r"哭笑不得|愣住.*放弃|被童言|胡说"
)
_RE_NO_BOOMERANG_NOTE = re.compile(r"未形成回旋镖|没有回旋镖|非回旋镖|无回旋镖")
_RE_I_SOUL_QUESTION = re.compile(
    r"灵魂拷问|一招制敌|价值高地|质问.*双标|双标.*质问|"
    r"为你好.*不让我|不让我.*为你好|语塞|无言以对|哑口无言"
)
_RE_I_QUESTION_CHAIN = re.compile(
    r"(你那是|那你怎么|你才|你自己).{0,20}(吗？|呢？|！)"
)
# 目标错位：死磕赛过程，奖品/资源溜走后点题（非双规则互戳）
_RE_GOAL_TUNNEL_GAME = re.compile(
    r"剪刀石头布|猜拳|赢的.*(?:才)?能?吃|赢了.*吃|吹蜡烛|抢吃"
)
_RE_GOAL_TUNNEL_PROCESS = re.compile(
    r"光顾着赢|顾着赢|一心只想赢|专注出拳|多次获胜|又赢|我赢了"
)
_RE_GOAL_TUNNEL_PRIZE = re.compile(
    r"菜都没了|菜.*没了|只剩|吃光|见底|空盘子|资源.*溜|目标.*没|"
    r"白赢|赢了.*没"
)


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


def suggests_m11_i_soul_question(blob: str) -> bool:
    """灵魂拷问：质问链+语塞/一招制敌，无公平争夺。"""
    text = str(blob or "")
    if suggests_c_fairness_boomerang(text):
        return False
    if _RE_DOMINATION.search(text):
        return False
    has_soul = bool(_RE_I_SOUL_QUESTION.search(text))
    question_hits = len(_RE_I_QUESTION_CHAIN.findall(text))
    if has_soul and question_hits >= 2:
        return True
    if has_soul and not suggests_c_fairness_boomerang(text):
        return True
    return False


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


def suggests_m6_n_solemn_nonsense(blob: str) -> bool:
    text = str(blob or "")
    if not _RE_SOLEMN_NONSENSE.search(text):
        return False
    if suggests_c_fairness_boomerang(text):
        return False
    if suggests_m8_j_domination(text):
        return False
    return True


def suggests_m13_o_goal_tunnel(blob: str) -> bool:
    """目标错位：死磕赛过程，奖品溜走后点题；非双规则回旋镖。"""
    text = str(blob or "")
    if suggests_c_fairness_boomerang(text):
        return False
    if suggests_m8_j_domination(text):
        return False
    if suggests_m6_n_solemn_nonsense(text):
        return False
    has_game = bool(_RE_GOAL_TUNNEL_GAME.search(text))
    has_process = bool(_RE_GOAL_TUNNEL_PROCESS.search(text))
    has_prize = bool(_RE_GOAL_TUNNEL_PRIZE.search(text))
    if has_prize and has_process:
        return True
    if has_prize and has_game and re.search(r"光顾着|顾着赢|白赢|赢了.*没", text):
        return True
    return False


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


def should_reclassify_m2_c_to_m11_i(
    *,
    mechanism: str,
    structure_type: str,
    blob: str,
) -> bool:
    """M2+C 但实际是灵魂拷问质问链 → M11+I。"""
    mech = str(mechanism or "").strip().upper()
    st = str(structure_type or "").strip().upper()
    if mech != "M2" or st != "C":
        return False
    if not suggests_m11_i_soul_question(blob):
        return False
    if suggests_c_fairness_boomerang(blob):
        return False
    return True


def should_reclassify_to_m6_n(
    *,
    mechanism: str,
    structure_type: str,
    blob: str,
) -> bool:
    """误标 C/A/E 的正经胡说 → M6+N。"""
    mech = str(mechanism or "").strip().upper()
    st = str(structure_type or "").strip().upper()
    if mech == "M6" and st == "N":
        return False
    if not suggests_m6_n_solemn_nonsense(blob):
        return False
    if mech == "M6" and st in {"A", "E", "C"}:
        return True
    if mech == "M2" and st == "C":
        return True
    if st == "C" and _RE_NO_BOOMERANG_NOTE.search(blob):
        return True
    return False


def should_reclassify_m2_c_to_m13_o(
    *,
    mechanism: str,
    structure_type: str,
    blob: str,
) -> bool:
    """M2+C 但实际是顾赛不顾奖/目标错位 → M13+O。"""
    mech = str(mechanism or "").strip().upper()
    st = str(structure_type or "").strip().upper()
    if mech == "M13" and st == "O":
        return False
    if not suggests_m13_o_goal_tunnel(blob):
        return False
    if suggests_c_fairness_boomerang(blob):
        return False
    if mech == "M2" and st == "C":
        return True
    if st == "C" and _RE_NO_BOOMERANG_NOTE.search(blob):
        return True
    return False


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


def _apply_reclass(
    out: dict[str, Any],
    *,
    target_mech: str,
    target_st: str,
    note_extra: str,
    note_tag: str,
) -> list[str]:
    notes = [
        f"mechanism:{out.get('mechanism')}→{target_mech}"
        f"+structure:{out.get('structure_type')}→{target_st}({note_tag})"
    ]
    out["mechanism"] = target_mech
    out["structure_type"] = target_st
    note = str(out.get("structure_mapping_note") or "").strip()
    out["structure_mapping_note"] = (
        f"{note}；{note_extra}".strip("；") if note else note_extra
    )
    return notes


def resolve_h3_structure(
    h3: dict[str, Any],
    *,
    story_raw: str = "",
) -> tuple[dict[str, Any], list[str]]:
    """H3 后处理：武力压制误标 M2+C → M8+J；正经胡说误标 → M6+N；
    目标错位误标 → M13+O。"""
    notes: list[str] = []
    out = dict(h3)
    blob = classification_blob(
        story_raw=story_raw,
        beat=out.get("beat") if isinstance(out.get("beat"), list) else [],
        conflict_core=str(out.get("conflict_core") or ""),
        mapping_note=str(out.get("structure_mapping_note") or ""),
    )
    if should_reclassify_m2_c_to_m8_j(
        mechanism=str(out.get("mechanism") or ""),
        structure_type=str(out.get("structure_type") or ""),
        blob=blob,
    ):
        notes.extend(
            _apply_reclass(
                out,
                target_mech="M8",
                target_st="J",
                note_extra="武力压制单方定规+认输收场，非 C 双规则回旋镖",
                note_tag="domination-not-fairness",
            )
        )
        return out, notes

    if should_reclassify_m2_c_to_m11_i(
        mechanism=str(out.get("mechanism") or ""),
        structure_type=str(out.get("structure_type") or ""),
        blob=blob,
    ):
        notes.extend(
            _apply_reclass(
                out,
                target_mech="M11",
                target_st="I",
                note_extra="灵魂拷问质问链+语塞/一招制敌，非 C 公平争夺",
                note_tag="soul-question-not-fairness",
            )
        )
        return out, notes

    if should_reclassify_to_m6_n(
        mechanism=str(out.get("mechanism") or ""),
        structure_type=str(out.get("structure_type") or ""),
        blob=blob,
    ):
        notes.extend(
            _apply_reclass(
                out,
                target_mech="M6",
                target_st="N",
                note_extra="正经胡说荒诞自洽+愣住，非 C/A/E 标准收束",
                note_tag="solemn-nonsense",
            )
        )
        return out, notes

    if should_reclassify_m2_c_to_m13_o(
        mechanism=str(out.get("mechanism") or ""),
        structure_type=str(out.get("structure_type") or ""),
        blob=blob,
    ):
        notes.extend(
            _apply_reclass(
                out,
                target_mech="M13",
                target_st="O",
                note_extra="顾赛不顾奖：赢过程输目标，非 C 双规则回旋镖",
                note_tag="goal-tunnel-not-fairness",
            )
        )
        return out, notes

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

    target_mech = ""
    target_st = ""
    extra = ""
    if should_reclassify_m2_c_to_m8_j(
        mechanism=mechanism,
        structure_type=current,
        blob=blob,
    ):
        target_mech, target_st = "M8", "J"
        extra = "武力压制单方定规+认输收场，非 C 双规则回旋镖"
    elif should_reclassify_m2_c_to_m11_i(
        mechanism=mechanism,
        structure_type=current,
        blob=blob,
    ):
        target_mech, target_st = "M11", "I"
        extra = "灵魂拷问质问链+语塞/一招制敌，非 C 公平争夺"
    elif should_reclassify_to_m6_n(
        mechanism=mechanism,
        structure_type=current,
        blob=blob,
    ):
        target_mech, target_st = "M6", "N"
        extra = "正经胡说荒诞自洽+愣住，非 C/A/E 标准收束"
    elif should_reclassify_m2_c_to_m13_o(
        mechanism=mechanism,
        structure_type=current,
        blob=blob,
    ):
        target_mech, target_st = "M13", "O"
        extra = "顾赛不顾奖：赢过程输目标，非 C 双规则回旋镖"

    if not target_mech:
        out["payload"] = payload
        return out, notes

    if target_st not in allowed_structure_types(target_mech):
        out["payload"] = payload
        return out, notes

    normalize_structure_type(target_st)
    out["mechanism"] = target_mech
    out["structure_type"] = target_st
    notes.append(f"mechanism:{mechanism}→{target_mech}+structure:{current}→{target_st}")

    note = str(payload.get("structure_mapping_note") or "").strip()
    if extra not in note:
        payload["structure_mapping_note"] = (
            f"{note}；{extra}".strip("；") if note else extra
        )

    _sync_scene_contract_story_type(payload, target_st, notes)
    out["payload"] = payload
    return out, notes
