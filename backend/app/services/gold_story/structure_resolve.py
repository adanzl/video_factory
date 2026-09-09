"""金故事结构类型纠偏：M2+C 误判武力压制→M8+J；正经胡说→M6+N；
目标错位→M13+O；整蛊互整→M14+P；无双规则硬套 M2+C → 降置信拒收。"""

from __future__ import annotations

import copy
import re
from typing import Any, cast

from app.services.gold_story.types import (
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
# 整蛊互整：道具下料 + 回敬 + 认怂（抽象，禁绑单篇芥末词）
_RE_P_OFFER = re.compile(r"尝尝|试试这个|给你选|挑战|这卷|这口|抹|加料|整蛊")
_RE_P_RETALIATE = re.compile(r"再试试|也给你|轮到你|回敬|特意给你|专门给你")
_RE_P_SURRENDER = re.compile(r"认输|不了不了|不敢再|我怂|服了|不试了")
_RE_P_PRANK_NOTE = re.compile(r"整蛊|互整|以牙还牙|挑战.*认输|回敬")
# 硬套 M2+C 的自述/题材信号（抽象，不绑单篇词表）
_RE_FORCED_M2C_NOTE = re.compile(
    r"无回旋镖|没有回旋镖|未形成回旋镖|非回旋镖|"
    r"理性共识|温馨感动|偏C但弱|变体|"
    r"双重规则.*无回旋镖|无回旋镖.*双重"
)
_RE_WARM_NO_CONFLICT = re.compile(
    r"甜蜜|感动|扑进.*怀|破涕为笑|亲了又亲|我爱你.*我爱你|"
    r"小甜心|眼眶湿润"
)
_RE_ADULT_OR_COUPLE = re.compile(
    r"二胎|再生一个|夫妻|闺蜜.*怀|抢男人|导演|片场|电动车|雅迪"
)
_RE_INFANT_LOVE = re.compile(r"三岁|宝宝|婴语|人类幼崽")


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


def suggests_m14_p_prank_reciprocal(blob: str) -> bool:
    """整蛊互整：道具下料 + 回敬加码 + 认怂；非公平回旋镖、非武力一锤。"""
    text = str(blob or "")
    if suggests_c_fairness_boomerang(text):
        return False
    if suggests_m8_j_domination(text):
        return False
    if suggests_m13_o_goal_tunnel(text):
        return False
    has_offer = bool(_RE_P_OFFER.search(text) or _RE_P_PRANK_NOTE.search(text))
    has_retaliate = bool(_RE_P_RETALIATE.search(text))
    has_surrender = bool(_RE_P_SURRENDER.search(text))
    if has_offer and has_retaliate and has_surrender:
        return True
    if has_offer and has_retaliate and _RE_P_PRANK_NOTE.search(text):
        return True
    return False


def should_reclassify_to_m14_p(
    *,
    mechanism: str,
    structure_type: str,
    blob: str,
) -> bool:
    """误标 C/F 的道具整蛊互整 → M14+P。"""
    mech = str(mechanism or "").strip().upper()
    st = str(structure_type or "").strip().upper()
    if mech == "M14" and st == "P":
        return False
    if not suggests_m14_p_prank_reciprocal(blob):
        return False
    if suggests_c_fairness_boomerang(blob):
        return False
    if mech == "M2" and st == "C":
        return True
    if mech == "M3" and st == "F":
        return True
    if st == "C" and _RE_P_PRANK_NOTE.search(blob):
        return True
    return False


def should_demote_forced_m2_c(
    *,
    mechanism: str,
    structure_type: str,
    blob: str,
) -> bool:
    """无双规则回旋镖却硬标 M2+C（温馨/婴语/夫妻共识等）→ 降置信拒收。"""
    mech = str(mechanism or "").strip().upper()
    st = str(structure_type or "").strip().upper()
    if mech != "M2" or st != "C":
        return False
    text = str(blob or "")
    # 自述无回旋镖/理性共识：优先于「公平」词刷屏
    if _RE_FORCED_M2C_NOTE.search(text):
        return True
    if suggests_c_fairness_boomerang(blob):
        return False
    if _RE_WARM_NO_CONFLICT.search(text) and _RE_NO_BOOMERANG_NOTE.search(text):
        return True
    if _RE_INFANT_LOVE.search(text) and _RE_WARM_NO_CONFLICT.search(text):
        return True
    if _RE_ADULT_OR_COUPLE.search(text):
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
    目标错位误标 → M13+O；整蛊互整误标 → M14+P；
    无双规则硬套 M2+C → 降 structure_confidence。"""
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

    if should_reclassify_to_m14_p(
        mechanism=str(out.get("mechanism") or ""),
        structure_type=str(out.get("structure_type") or ""),
        blob=blob,
    ):
        notes.extend(
            _apply_reclass(
                out,
                target_mech="M14",
                target_st="P",
                note_extra="道具整蛊互整回敬认怂，非 C 双规则/非 F 纯口头威胁",
                note_tag="prank-reciprocal",
            )
        )
        return out, notes

    if should_demote_forced_m2_c(
        mechanism=str(out.get("mechanism") or ""),
        structure_type=str(out.get("structure_type") or ""),
        blob=blob,
    ):
        conf = float(out.get("structure_confidence") or 0.0)
        out["structure_confidence"] = min(conf, 0.35)
        note = str(out.get("structure_mapping_note") or "").strip()
        extra = "缺双规则同场回旋镖，禁止硬套 M2+C"
        out["structure_mapping_note"] = (
            f"{note}；{extra}".strip("；") if note else extra
        )
        notes.append("demote:forced-m2c-no-fairness-boomerang")
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
    elif should_reclassify_to_m14_p(
        mechanism=mechanism,
        structure_type=current,
        blob=blob,
    ):
        target_mech, target_st = "M14", "P"
        extra = "道具整蛊互整回敬认怂，非 C 双规则/非 F 纯口头威胁"

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
