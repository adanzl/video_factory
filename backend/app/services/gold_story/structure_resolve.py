"""金故事结构类型纠偏：M2+C 误判武力压制→M8+J；正经胡说→M6+N；
目标错位→M13+O；整蛊互整→M14+P；耍赖翻车→M15+Q；暖收误标 M7+D→M4+G；
无双规则硬套 M2+C / 假 M14+P → 降置信拒收；
M4+G 无真情 pivot 时旁路 closing_mode=authority_punchline。"""

from __future__ import annotations

import copy
import re
from typing import Any, cast

from app.services.gold_story.types import (
    allowed_structure_types,
    normalize_structure_type,
)

# M4+G 收束旁路：权威点题（非真情 pivot/暖收），不改 structure_type 字母
CLOSING_MODE_AUTHORITY_PUNCHLINE = "authority_punchline"

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
# 整蛊互整：道具下料 + 对等回敬 + 认怂（抽象，禁绑单篇芥末词）
# 裸「回敬」不得单独充当 offer/retaliate（会把「回敬洗碗」亲子反将误标 P）
_RE_P_OFFER = re.compile(
    r"尝尝|试试这个|给你选|挑战|这卷|这口|抹|加料|整蛊|"
    r"递.*饼|推到.*面前"
)
_RE_P_RETALIATE = re.compile(
    r"再试试|也给你|轮到你|特意给你|专门给你|也尝尝|给你加料"
)
_RE_P_SURRENDER = re.compile(r"认输|不了不了|不敢再|我怂|服了|不试了")
_RE_P_PRANK_NOTE = re.compile(r"整蛊|互整|以牙还牙|挑战.*认输")
# 成人惩罚/家务反将：负向（无互整链时禁止当 P；可作 Q 反噬信号）
_RE_P_ADULT_REVERSE = re.compile(
    r"洗碗|刷碗|洗盘子|罚站|写作业|没收|罚洗|去做家务"
)
# 耍赖翻车：约定后耍赖/借口 → 被拆穿 → 反噬（与 E/P 对仗）
_RE_Q_CHEAT = re.compile(
    r"耍赖|重抽|再抽|逞强|借口|推给|胃小|太少|不认|嘴硬"
)
_RE_Q_EXPOSE = re.compile(
    r"看穿|拆穿|揭穿|心思|你昨天|偷吃|别装|露馅|明明"
)
_RE_Q_BACKFIRE = re.compile(
    r"洗碗|刷碗|洗盘子|加活|罚|活该|自己收拾|你去|翻车"
)
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
# M7/D 误标暖收：有暖心收束、无字面破规回旋镖
_RE_WARM_CLOSE = re.compile(
    r"暖心|暖收|会心一笑|愣住.*笑|笑出声|感动|"
    r"符合G|G型结构|嘴硬心软"
)
_RE_D_CLOSE = re.compile(
    r"叮嘱.*破|破规|原话回旋|你刚说|你不是说|规矩是你|歪读执行.*破"
)
# 权威点题旁路：立规→反将→认怂让渡→权威秩序点题（抽象槽位，禁绑单篇词）
_RE_AUTH_RULE = re.compile(r"谁先|立规|约好|规定|规矩|定规")
_RE_AUTH_REVERSE = re.compile(
    r"不罚|没发火|反而|反把|那今晚|那你负责|你负责|今晚你|"
    r"递.*给|把.*给.*哄|反将"
)
_RE_AUTH_CEDE = re.compile(
    r"立刻.*(给|塞|让)|你玩你玩|我哄|认怂|塞给|让出|主动让"
)
_RE_AUTH_PUNCH = re.compile(
    r"记住|宣布|点破|并列|第[一二三]|这个家|这个班|听清楚|我说了算|"
    r"家庭排名|秩序"
)
# 真 G 关系修复证据（有则勿打权威点题旁路）
_RE_TRUE_G_PIVOT = re.compile(
    r"护|撑腰|拼命|动你|心疼|认真的|我怕|重要|舍不得|在乎|"
    r"你去哪|一个人走|陪你|真心"
)
_RE_TRUE_G_SOFT = re.compile(
    r"擦|药|说好了|行了|过来|撑腰|识相|饶|原谅|一起走|一起去|拉手"
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


def p_structure_evidence_blob(
    *,
    story_raw: str = "",
    beat: list[Any] | None = None,
    conflict_core: str = "",
    closing_intent: str = "",
    dialogue_seed: list[Any] | None = None,
) -> str:
    """P 纠偏证据：不含 mapping_note，防「整蛊回敬」自证循环。"""
    return classification_blob(
        story_raw=story_raw,
        beat=beat,
        conflict_core=conflict_core,
        mapping_note="",
        closing_intent=closing_intent,
        dialogue_seed=dialogue_seed,
    )


def suggests_m14_p_prank_reciprocal(blob: str) -> bool:
    """整蛊互整：道具下料 + 对等回敬 + 认怂；非公平回旋镖、非武力一锤。

    须三拍齐备；禁止用「回敬/整蛊」备注词单独充当 offer。
    """
    text = str(blob or "")
    if suggests_c_fairness_boomerang(text):
        return False
    if suggests_m8_j_domination(text):
        return False
    if suggests_m13_o_goal_tunnel(text):
        return False
    has_offer = bool(_RE_P_OFFER.search(text))
    has_retaliate = bool(_RE_P_RETALIATE.search(text))
    has_surrender = bool(_RE_P_SURRENDER.search(text))
    return bool(has_offer and has_retaliate and has_surrender)


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


def should_demote_forced_m14_p(
    *,
    mechanism: str,
    structure_type: str,
    blob: str,
) -> bool:
    """已标 M14+P 但干净证据无互整认怂链 → 降置信（禁亲子洗碗反将硬套）。

    若已可纠到 M15+Q，优先走 reclass，不 demote。
    """
    mech = str(mechanism or "").strip().upper()
    st = str(structure_type or "").strip().upper()
    if mech != "M14" or st != "P":
        return False
    if suggests_m15_q_cheat_expose(blob):
        return False
    return not suggests_m14_p_prank_reciprocal(blob)


def suggests_m15_q_cheat_expose(blob: str) -> bool:
    """耍赖翻车：耍赖/借口加码 + 被拆穿 + 反噬；非 P 互整、非 C 回旋镖。"""
    text = str(blob or "")
    if suggests_m14_p_prank_reciprocal(text):
        return False
    if suggests_c_fairness_boomerang(text):
        return False
    if suggests_m8_j_domination(text):
        return False
    has_cheat = bool(_RE_Q_CHEAT.search(text))
    has_expose = bool(_RE_Q_EXPOSE.search(text))
    has_backfire = bool(_RE_Q_BACKFIRE.search(text))
    return bool(has_cheat and has_expose and has_backfire)


def should_reclassify_to_m15_q(
    *,
    mechanism: str,
    structure_type: str,
    blob: str,
) -> bool:
    """误标 P/C/E 的耍赖翻车 → M15+Q。"""
    mech = str(mechanism or "").strip().upper()
    st = str(structure_type or "").strip().upper()
    if mech == "M15" and st == "Q":
        return False
    if not suggests_m15_q_cheat_expose(blob):
        return False
    if mech == "M14" and st == "P":
        return True
    if mech == "M2" and st == "C":
        return True
    if st in {"P", "C", "E"}:
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


def suggests_m4_g_warm_close(blob: str) -> bool:
    """暖心收束：愣住/暖收/符合G；非 D 字面破规回旋镖。"""
    text = str(blob or "")
    if not _RE_WARM_CLOSE.search(text):
        return False
    if _RE_D_CLOSE.search(text):
        return False
    return True


def suggests_true_g_relational_close(blob: str) -> bool:
    """源稿已有真情 pivot + 暖收信号 → 走标准 G，勿旁路。"""
    text = str(blob or "")
    return bool(_RE_TRUE_G_PIVOT.search(text) and _RE_TRUE_G_SOFT.search(text))


def suggests_authority_punchline_close(blob: str) -> bool:
    """立规→反将→认怂让渡→权威点题（无真情 pivot/暖收）。"""
    text = str(blob or "")
    if suggests_true_g_relational_close(text):
        return False
    return bool(
        _RE_AUTH_RULE.search(text)
        and _RE_AUTH_REVERSE.search(text)
        and _RE_AUTH_CEDE.search(text)
        and _RE_AUTH_PUNCH.search(text)
    )


def stamp_m4_g_closing_mode(
    row: dict[str, Any],
    payload: dict[str, Any],
    blob: str,
) -> list[str]:
    """M4+G 无关系修复证据且命中权威点题链时，打 closing_mode 旁路。

    不改 mechanism/structure_type；真 G 清掉误标旁路。
    """
    notes: list[str] = []
    mech = str(row.get("mechanism") or "").strip().upper()
    st = str(row.get("structure_type") or "").strip().upper()
    prev = str(payload.get("closing_mode") or "").strip()
    if mech != "M4" or st != "G":
        if prev == CLOSING_MODE_AUTHORITY_PUNCHLINE:
            payload["closing_mode"] = None
            notes.append("closing_mode:clear(not-m4-g)")
        return notes
    if suggests_true_g_relational_close(blob):
        if prev == CLOSING_MODE_AUTHORITY_PUNCHLINE:
            payload["closing_mode"] = None
            notes.append("closing_mode:clear(true-g)")
        return notes
    if suggests_authority_punchline_close(blob):
        if prev != CLOSING_MODE_AUTHORITY_PUNCHLINE:
            payload["closing_mode"] = CLOSING_MODE_AUTHORITY_PUNCHLINE
            notes.append("closing_mode:authority_punchline")
        return notes
    if prev == CLOSING_MODE_AUTHORITY_PUNCHLINE:
        payload["closing_mode"] = None
        notes.append("closing_mode:clear(no-authority-chain)")
    return notes


def should_reclassify_m7_d_to_m4_g(
    *,
    mechanism: str,
    structure_type: str,
    blob: str,
) -> bool:
    """立规后暖收误标 M7+D → M4+G。"""
    mech = str(mechanism or "").strip().upper()
    st = str(structure_type or "").strip().upper()
    if mech != "M7" or st != "D":
        return False
    return suggests_m4_g_warm_close(blob)


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
    暖收误标 M7+D → M4+G；无双规则硬套 M2+C / 假 M14+P → 降 structure_confidence。"""
    notes: list[str] = []
    out = dict(h3)
    beat = out.get("beat") if isinstance(out.get("beat"), list) else []
    blob = classification_blob(
        story_raw=story_raw,
        beat=beat,
        conflict_core=str(out.get("conflict_core") or ""),
        mapping_note=str(out.get("structure_mapping_note") or ""),
    )
    # P 判定禁用 mapping_note，防「整蛊回敬」自证
    blob_p = p_structure_evidence_blob(
        story_raw=story_raw,
        beat=beat,
        conflict_core=str(out.get("conflict_core") or ""),
        closing_intent=str(out.get("closing_intent") or ""),
    )
    if should_reclassify_m7_d_to_m4_g(
        mechanism=str(out.get("mechanism") or ""),
        structure_type=str(out.get("structure_type") or ""),
        blob=blob,
    ):
        notes.extend(
            _apply_reclass(
                out,
                target_mech="M4",
                target_st="G",
                note_extra="立规后暖心收束，非 D 字面破规回旋镖",
                note_tag="warm-close-not-literal",
            )
        )
        return out, notes

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
        blob=blob_p,
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

    if should_reclassify_to_m15_q(
        mechanism=str(out.get("mechanism") or ""),
        structure_type=str(out.get("structure_type") or ""),
        blob=blob_p,
    ):
        notes.extend(
            _apply_reclass(
                out,
                target_mech="M15",
                target_st="Q",
                note_extra="耍赖/借口被拆穿后反噬，非 P 互整认怂、非 E 妈妈破功",
                note_tag="cheat-expose-backfire",
            )
        )
        return out, notes

    if should_demote_forced_m14_p(
        mechanism=str(out.get("mechanism") or ""),
        structure_type=str(out.get("structure_type") or ""),
        blob=blob_p,
    ):
        conf = float(out.get("structure_confidence") or 0.0)
        out["structure_confidence"] = min(conf, 0.35)
        note = str(out.get("structure_mapping_note") or "").strip()
        extra = (
            "adult_reverse_not_prank；缺道具互整认怂链，禁止硬套 M14+P"
            if _RE_P_ADULT_REVERSE.search(blob_p)
            else "no_retaliate_chain；缺道具互整认怂链，禁止硬套 M14+P"
        )
        if "adult_reverse_not_prank" not in note and "no_retaliate_chain" not in note:
            out["structure_mapping_note"] = (
                f"{note}；{extra}".strip("；") if note else extra
            )
        notes.append("demote:forced-m14p-not-prank")
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
    blob_p = p_structure_evidence_blob(
        story_raw=str(payload.get("story_raw") or ""),
        beat=payload.get("beat") if isinstance(payload.get("beat"), list) else [],
        conflict_core=str(out.get("conflict_core") or ""),
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
    if should_reclassify_m7_d_to_m4_g(
        mechanism=mechanism,
        structure_type=current,
        blob=blob,
    ):
        target_mech, target_st = "M4", "G"
        extra = "立规后暖心收束，非 D 字面破规回旋镖"
    elif should_reclassify_m2_c_to_m8_j(
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
        blob=blob_p,
    ):
        target_mech, target_st = "M14", "P"
        extra = "道具整蛊互整回敬认怂，非 C 双规则/非 F 纯口头威胁"
    elif should_reclassify_to_m15_q(
        mechanism=mechanism,
        structure_type=current,
        blob=blob_p,
    ):
        target_mech, target_st = "M15", "Q"
        extra = "耍赖/借口被拆穿后反噬，非 P 互整认怂、非 E 妈妈破功"

    if not target_mech:
        if should_demote_forced_m14_p(
            mechanism=mechanism,
            structure_type=current,
            blob=blob_p,
        ):
            conf = float(payload.get("structure_confidence") or out.get("structure_confidence") or 0.0)
            payload["structure_confidence"] = min(conf, 0.35)
            note = str(payload.get("structure_mapping_note") or "").strip()
            demote_extra = (
                "adult_reverse_not_prank；缺道具互整认怂链，禁止硬套 M14+P"
                if _RE_P_ADULT_REVERSE.search(blob_p)
                else "no_retaliate_chain；缺道具互整认怂链，禁止硬套 M14+P"
            )
            if (
                "adult_reverse_not_prank" not in note
                and "no_retaliate_chain" not in note
            ):
                payload["structure_mapping_note"] = (
                    f"{note}；{demote_extra}".strip("；") if note else demote_extra
                )
            notes.append("demote:forced-m14p-not-prank")
        notes.extend(stamp_m4_g_closing_mode(out, payload, blob))
        out["payload"] = payload
        return out, notes

    if target_st not in allowed_structure_types(target_mech):
        notes.extend(stamp_m4_g_closing_mode(out, payload, blob))
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
    # 纠偏后再用新 mechanism/structure 打旁路
    notes.extend(stamp_m4_g_closing_mode(out, payload, blob))
    out["payload"] = payload
    return out, notes


def sync_h3_from_scene_contract(
    h3: dict[str, Any],
    scene_contract: dict[str, Any] | None,
    *,
    story_raw: str = "",
) -> tuple[dict[str, Any], list[str]]:
    """H3a 标了结构字母时回写 H3 列，避免表头与契约分叉（如列 D、契约 G）。"""
    notes: list[str] = []
    out = dict(h3)
    sc = scene_contract if isinstance(scene_contract, dict) else {}
    sc_st = str(sc.get("story_type") or "").strip().upper()
    h3_st = str(out.get("structure_type") or "").strip().upper()
    if not sc_st or sc_st == h3_st:
        return out, notes

    blob = classification_blob(
        story_raw=story_raw,
        beat=out.get("beat") if isinstance(out.get("beat"), list) else [],
        conflict_core=str(out.get("conflict_core") or ""),
        mapping_note=str(out.get("structure_mapping_note") or ""),
        closing_intent=str(sc.get("closing_intent") or ""),
    )
    # 已知分叉：契约 G / 列 D（暖收）→ 跟契约走
    if sc_st == "G" and h3_st == "D" and (
        suggests_m4_g_warm_close(blob)
        or should_reclassify_m7_d_to_m4_g(
            mechanism=str(out.get("mechanism") or ""),
            structure_type=h3_st,
            blob=blob,
        )
        or _RE_WARM_CLOSE.search(blob)
    ):
        notes.extend(
            _apply_reclass(
                out,
                target_mech="M4",
                target_st="G",
                note_extra="H3a.story_type=G 回写列（原误标 D）",
                note_tag="sync-scene-g",
            )
        )
        return out, notes

    return out, notes
