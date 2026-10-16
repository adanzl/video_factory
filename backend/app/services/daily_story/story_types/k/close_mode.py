"""K 类收场模式：K-A 劝失败僵持 vs K-B 旁观后孩子自行收场。"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

K_A_PARENT_FAIL_STALEMATE = "K_A_PARENT_FAIL_STALEMATE"
K_B_CHILD_SELF_RESOLVE = "K_B_CHILD_SELF_RESOLVE"
K_UNKNOWN = "K_UNKNOWN"
# K-B 负向守卫命中：拍链/收束预设让家长成为孩子的攻击/迁怒目标。
# 这是「解析结论」而非可落盘的收场模式（不进 K_CLOSE_MODES）：落盘语义仍沿旧口径
# （normalize 归 K_UNKNOWN），避免存量稿因新常量被当成已解析而跳过守卫。
K_B_DISQUALIFIED = "K_B_DISQUALIFIED"

K_CLOSE_MODES = frozenset(
    {
        K_A_PARENT_FAIL_STALEMATE,
        K_B_CHILD_SELF_RESOLVE,
        K_UNKNOWN,
    }
)

# beat / closing 因果（抽象 intent，非道具词表）
RE_BEAT_CHILD_SELF = re.compile(
    r"自行收场|自行恢复|自行发起|自己发起|自行.*和|恢复互动|"
    r"搭话|邀约|一起出|一起走去|再问|探头|勾肩|抹脸答应"
)
RE_BEAT_PARENT_PASSIVE = re.compile(
    r"旁观|不掺和|不评理|不参与|挡回|立规|不介入|规矩挡|拒绝评理|"
    r"挡回去|不接"
)
RE_BEAT_PARENT_FAIL = re.compile(
    r"劝失败|管不了|劝不动|劝不了|拦不住|制止失败|越劝越"
)
RE_BEAT_STALE = re.compile(r"僵持|不和好|冷战|仍不对付|不对付")
# 孩子自行停战（抽象冲突终止事件类型，非单篇道具/动作）
RE_BEAT_CHILD_STOP = re.compile(
    r"停手|收手|罢手|放手|停战|停下|不打了|不闹了|收场|收势"
)
# 停战后再恢复互动/关系缓和；单有"停手"只算暂停，须与之组合才判 K-B
RE_BEAT_CHILD_RESUME = re.compile(
    r"笑|一起|一块|和好|恢复互动|搭话|邀约|勾肩|继续玩|出门|问吃|抹脸"
)
RE_CLOSE_PASSIVE = re.compile(r"不掺和|旁观|不评理|不参与")
RE_CLOSE_FAIL_STALE = re.compile(
    r"劝失败|管不了|僵持|不和好|劝不动|劝不了"
)

# K-B 负向守卫（抽象：目标角色 × 动作/情绪类别，不绑单篇道具/角色名）。
# K-B 的不变量是「家长非介入 + 孩子自行收场」：家长不能是冲突的攻击/迁怒对象，
# 收束也不能预设「家长被孩子弄伤/狼狈」这一必须落地的事件。
_KB_PARENT_ROLE_CUES = re.compile(r"爸爸|妈妈|父亲|母亲|家长|爹|娘")
_KB_TARGET_AGGRESSION_ACT = re.compile(
    r"攻击|袭击|殴打|揍|踢|掐|砸|泼|撕|拽|推倒|推搡|猛推|打人|"
    r"伤害|弄伤|摔倒|弄倒|欺负|欺压|强迫|威逼"
)
# 告状/评理/求助：孩子把家长当诉求对象，不是攻击目标（家长是「第三方」）。
_KB_APPEAL_ACT = re.compile(r"告状|评理|求助|求评|喊.*评|投诉|诉苦|撒娇|求援")
_KB_TARGET_VENT_EMOTION = re.compile(
    r"迁怒|撒气|发泄|出气|冲家长|冲爸爸|冲妈妈|怪罪|责怪|埋怨|怨恨"
)
_KB_PARENT_HARM_STATE = re.compile(
    r"狼狈|受伤|被推|被打|被砸|吃痛|倒地|趔趄|鼻青|挂彩|惨状|吃亏"
)
_KB_CHILD_FORCE_ACT = re.compile(r"推|打|砸|攻击|动手|揍|踢|拽|泼")


def _beat_text(beat: Any, *keys: str) -> str:
    if not isinstance(beat, dict):
        return ""
    return " ".join(str(beat.get(k) or "") for k in keys)


def k_b_disqualification_reason(
    *,
    beat_chain: list[Any] | None,
    closing_intent: str = "",
) -> str:
    """K-B 不合格的结构化原因；合格返回空串。

    判据全部是抽象类别：说话方是不是孩子、目标（addressee/intent 提到的角色）
    是不是家长、动作是不是攻击类、情绪是不是迁怒类，以及收束是否把
    「家长受孩子动作伤害」当成必须落地的事件。命中即返回原因，不做静默改判。
    """
    for beat in beat_chain or []:
        speaker = _beat_text(beat, "speaker")
        if not speaker or _KB_PARENT_ROLE_CUES.search(speaker):
            continue
        addressee = _beat_text(beat, "addressee")
        intent = _beat_text(beat, "intent")
        targets_parent = bool(
            _KB_PARENT_ROLE_CUES.search(addressee)
            or (not addressee and _KB_PARENT_ROLE_CUES.search(intent))
        )
        if not targets_parent:
            continue
        beat_no = str(
            (beat.get("beat") if isinstance(beat, dict) else "") or "?"
        )
        if _KB_TARGET_VENT_EMOTION.search(intent):
            return f"beat {beat_no} 孩子对家长的迁怒/发泄目标：{intent}"
        if _KB_APPEAL_ACT.search(intent):
            continue
        if _KB_TARGET_AGGRESSION_ACT.search(intent):
            return f"beat {beat_no} 孩子对家长的攻击目标：{intent}"
    closing = str(closing_intent or "")
    if (
        _KB_PARENT_ROLE_CUES.search(closing)
        and _KB_PARENT_HARM_STATE.search(closing)
        and _KB_CHILD_FORCE_ACT.search(closing)
    ):
        return f"closing 预设家长受孩子动作伤害：{closing.strip()[:24]}"
    return ""


def _k_b_or_disqualified(
    *,
    beat_chain: list[Any] | None,
    closing_intent: str,
) -> str:
    reason = k_b_disqualification_reason(
        beat_chain=beat_chain, closing_intent=closing_intent
    )
    if reason:
        logger.info("K-B disqualified by negative guard: %s", reason)
        return K_B_DISQUALIFIED
    return K_B_CHILD_SELF_RESOLVE

# K-B 正文硬卡（只看对白，不看 punchline）
_KB_PARENT_PASSIVE_CUES = (
    r"不评理|不参与|不掺和|规矩|不能哭|别找我|挡回|不介入|"
    r"不接|别评|不管你们|吃饭|吃自己的"
)
# 高精度预筛：命中即判为家长非介入（保留为独立常量，供打分/审计复用）
RE_KB_PARENT_PASSIVE = re.compile(_KB_PARENT_PASSIVE_CUES)
# K-B 家长「非介入」抽象行为不变量（词表只做高精度预筛，行为立场才是判据）。
# 覆盖立场：WITHDRAW 退出冲突/交还孩子自理、BYSTANDER 旁观看戏、
# BLOCK 挡回制止继续、REFUSE_JUDGE 拒绝裁判、DISTRACT 转移注意。
RE_KB_PARENT_NON_INTERVENTION = re.compile(
    _KB_PARENT_PASSIVE_CUES
    + "|"
    # WITHDRAW：退出冲突，交给孩子自己处理
    + r"你们(?:俩|两个)?自己(?:玩|说|解决|看着办|闹|商量|处理|来)|"
    + r"我(?:不喊|不管|不问|不看|不插手|先走|走开|回屋|做饭)|"
    + r"别问我|"
    # BYSTANDER：旁观/看戏/看热闹
    + r"旁观|看戏|吃瓜|看热闹|看你们(?:打|闹|玩)|我(?:就|只)看|当没看见|"
    # BLOCK：挡回/制止继续
    + r"别(?:推|打|闹|吵|抢)|不(?:许|能)(?:推|打|抢)|住手|停下|松手"
)
RE_KB_PARENT_MEDIATE = re.compile(
    r"别闹了|快分开|评评理|谁对谁错|都错了|听妈妈的|我生气了|"
    r"和好吧|快和好|你们去|一起去玩|一块玩"
)
# 旁观挡回时勿怂恿姐弟继续打（抽象动词，非单篇）
RE_KB_PARENT_INCITE = re.compile(
    r"接着打|继续打|你俩.{0,6}打|再打(?:下去|呗|啊|吧)|去打吧|"
    r"打吧|别停|看你们打|越打越|打热闹|接着闹"
)
RE_KB_DEFIANCE_FILLER = re.compile(
    r"不服输|不认输|还没完|你试试|试试看|偏不让|偏不|谁怕谁|"
    r"没完就没完|你胡说|你得意|我不让"
)
RE_KB_LINE_FRAGMENT = re.compile(
    r"[\.…]+(?:了呢|了吧|了啊)[\.…]*|"
    r"(?<=[啊呀吧呢])[\.…]{2,}(?:了呢|了吧)?[\.…]*"
)
RE_KB_CHILD_RESOLVE = re.compile(
    r"要不要|还玩|走[啊吧]|去不去|吃不吃|再来一局|行了|"
    r"算了|还打吗|要，等|出门|玩不玩|还玩不|一起走吧|咱们走|一起吃|一起去|"
    r"还生气|饿不饿"
)
RE_KB_CHILD_ACCEPT = re.compile(
    r"玩！|玩啊|行啊|好啊|要[！。?]|走起|一起[走去吧]|等我|换鞋|走[。！]|"
    r"来啊|来吧"
)
RE_KB_CHILD_REJECT = re.compile(r"不要|我拒绝|谁稀罕|不理你|才不")
RE_KB_COLD_TAIL = re.compile(r"不理|谁稀罕|谁怕谁|不认输|不让你|没完就没完")
RE_KB_STALE_LOOP = re.compile(
    r"谁怕谁|不让步|服不服|僵着|僵吧|没完|我也不让|你服不服|偏不让|瞪吧|"
    r"不服呀|怎么样"
)

KID_SPEAKERS = frozenset({"昭昭", "灿灿"})

RE_H_RITUAL = re.compile(
    r"拉手|(?<!不)和好|对不起|原谅|说好了|齐声|抱抱|都错"
)

# K-B：家长对白勿替观众解说；closing_intent 可写「对爸爸说」，成稿宜自言自语
RE_KB_PARENT_AUDIENCE_NARRATION = re.compile(
    r"你看(他|她|它|俩|两|他们|孩子|他俩|两个)|"
    r"自己就好了|自己弄好了"
)
RE_KB_PARENT_EXPLICIT_ADDRESSEE = re.compile(
    r"跟(跟)?(孩|孩子)?(他)?爸(说|讲)|跟你爸|跟孩子爸|咱俩"
)

# punchline 常见未落正文动作（抽象，非单篇道具）
RE_KB_PUNCHLINE_UNGROUNDED = re.compile(r"勾肩搭背|拉钩一百年")


def normalize_k_close_mode(value: str | None) -> str:
    raw = str(value or "").strip()
    if raw in K_CLOSE_MODES:
        return raw
    return K_UNKNOWN


def closing_intent_from_story(story: dict[str, Any]) -> str:
    if not isinstance(story, dict):
        return ""
    direct = str(story.get("closing_intent") or "").strip()
    if direct:
        return direct
    sc = story.get("scene_contract")
    if isinstance(sc, dict):
        return str(sc.get("closing_intent") or "").strip()
    return ""


def k_b_passive_mutter_from_closing(closing_intent: str) -> str:
    """K-B 家长末句：自言自语点题，关键词来自 closing_intent。"""
    ci = str(closing_intent or "").strip()
    if re.search(r"不掺和|不介入|不参与", ci):
        lead = "不掺和就对了"
    elif re.search(r"不评理|挡回|旁观", ci):
        lead = "不评理就对了"
    else:
        lead = "不掺和就对了"
    return f"{lead}……嗯，让他们自己弄去吧。"


K_MODE_SOURCE_STORED = "stored"
K_MODE_SOURCE_LEGACY_EMPTY = "legacy_empty"
K_MODE_SOURCE_EXPLICIT_UNKNOWN = "explicit_unknown"
K_MODE_SOURCE_ABSENT = "absent"
# 历史稿从未落盘该字段：沿用旧兜底，不因"字段缺失"阻断。
K_MODE_SOURCE_LEGACY = frozenset({K_MODE_SOURCE_LEGACY_EMPTY, K_MODE_SOURCE_ABSENT})


def _read_k_close_mode(
    story: dict[str, Any],
) -> tuple[str, str]:
    """读稿上 k_close_mode，并区分来源：(mode, source)。

    ``legacy_empty``/``absent`` 表示历史字段缺失（旧稿兼容，勿当"判不出"）；
    ``explicit_unknown`` 才是解析器跑过但落 K_UNKNOWN 的显式状态。
    """
    if not isinstance(story, dict):
        return K_UNKNOWN, K_MODE_SOURCE_ABSENT
    raw = str(story.get("k_close_mode") or "").strip()
    if raw:
        return (
            normalize_k_close_mode(raw),
            K_MODE_SOURCE_EXPLICIT_UNKNOWN
            if normalize_k_close_mode(raw) == K_UNKNOWN
            else K_MODE_SOURCE_STORED,
        )
    sc = story.get("scene_contract")
    if isinstance(sc, dict):
        nested = str(sc.get("k_close_mode") or "").strip()
        if nested:
            return (
                normalize_k_close_mode(nested),
                K_MODE_SOURCE_EXPLICIT_UNKNOWN
                if normalize_k_close_mode(nested) == K_UNKNOWN
                else K_MODE_SOURCE_STORED,
            )
    if "k_close_mode" in story or (
        isinstance(sc, dict) and "k_close_mode" in sc
    ):
        return K_UNKNOWN, K_MODE_SOURCE_LEGACY_EMPTY
    return K_UNKNOWN, K_MODE_SOURCE_ABSENT


def k_close_mode_from_story(story: dict[str, Any]) -> str:
    """读稿上已落盘的 k_close_mode；缺省为 K_UNKNOWN（勿当 K-A）。"""
    return _read_k_close_mode(story)[0]


def k_close_mode_is_explicit_unknown(story: dict[str, Any]) -> bool:
    """是否"解析器跑过并显式判为 K_UNKNOWN"（历史空值不算）。

    新稿显式 K_UNKNOWN 属未定轨非法状态，不得空转放行；历史空值走旧兜底。
    """
    mode, source = _read_k_close_mode(story)
    return mode == K_UNKNOWN and source == K_MODE_SOURCE_EXPLICIT_UNKNOWN


def _beat_intents(beat_chain: list[Any]) -> list[str]:
    out: list[str] = []
    for item in beat_chain or []:
        if isinstance(item, dict):
            out.append(str(item.get("intent") or "").strip())
        elif item is not None:
            out.append(str(item).strip())
    return [x for x in out if x]


def resolve_k_close_mode(
    *,
    beat_chain: list[Any] | None,
    closing_intent: str = "",
    mechanism_text: str = "",
) -> str:
    """生成前由 beat_chain/closing 判定；判不出则 K_UNKNOWN。"""
    intents = _beat_intents(beat_chain or [])
    beats_blob = " ".join(intents)
    closing = str(closing_intent or "").strip()
    mech = str(mechanism_text or "").strip()
    blob = " ".join(x for x in (beats_blob, closing, mech) if x)

    last3 = " ".join(intents[-3:])
    child_self_last = bool(RE_BEAT_CHILD_SELF.search(last3))
    child_self_any = bool(RE_BEAT_CHILD_SELF.search(beats_blob))
    parent_passive = bool(RE_BEAT_PARENT_PASSIVE.search(blob)) or bool(
        RE_CLOSE_PASSIVE.search(closing)
    )
    parent_fail = bool(RE_BEAT_PARENT_FAIL.search(blob)) or bool(
        RE_CLOSE_FAIL_STALE.search(closing)
    )
    stale_end = bool(RE_BEAT_STALE.search(last3 + closing))
    # 组合规则：自行停战 + 末段恢复互动。单有"停手"只算暂停，不判 K-B。
    child_stop_last = bool(RE_BEAT_CHILD_STOP.search(last3 + closing))
    child_resume = bool(RE_BEAT_CHILD_RESUME.search(last3 + closing))
    child_self_resolved = (child_stop_last and child_resume) or child_self_last

    if child_self_resolved and parent_passive and not stale_end:
        return _k_b_or_disqualified(
            beat_chain=beat_chain, closing_intent=closing_intent
        )
    if parent_fail and stale_end and not child_self_resolved:
        return K_A_PARENT_FAIL_STALEMATE
    if child_self_any and parent_passive:
        if not parent_fail or child_self_resolved:
            return _k_b_or_disqualified(
                beat_chain=beat_chain, closing_intent=closing_intent
            )
    if parent_fail and not child_self_any:
        return K_A_PARENT_FAIL_STALEMATE
    if parent_passive and child_self_any and not stale_end:
        return _k_b_or_disqualified(
            beat_chain=beat_chain, closing_intent=closing_intent
        )
    return K_UNKNOWN


def stamp_k_close_mode_on_payload(
    payload: dict[str, Any],
    *,
    beat_chain: list[Any] | None = None,
    closing_intent: str = "",
    mechanism_text: str = "",
    force: bool = False,
) -> tuple[str, bool]:
    """写入 payload 与 scene_contract.k_close_mode；已有且非 force 则不覆盖。"""
    out = dict(payload)
    prev = normalize_k_close_mode(str(out.get("k_close_mode") or ""))
    sc_raw = out.get("scene_contract")
    sc = dict(sc_raw) if isinstance(sc_raw, dict) else {}
    prev_sc = normalize_k_close_mode(str(sc.get("k_close_mode") or ""))
    if not force and prev != K_UNKNOWN:
        return prev, False
    if not force and prev_sc != K_UNKNOWN:
        out["k_close_mode"] = prev_sc
        if prev_sc != prev:
            out["scene_contract"] = {**sc, "k_close_mode": prev_sc}
        payload.clear()
        payload.update(out)
        return prev_sc, prev_sc != prev

    closing = str(
        closing_intent or out.get("closing_intent") or sc.get("closing_intent") or ""
    )
    chain = beat_chain
    if chain is None:
        chain = sc.get("beat_chain") if isinstance(sc.get("beat_chain"), list) else []
    mode = resolve_k_close_mode(
        beat_chain=chain,
        closing_intent=closing,
        mechanism_text=mechanism_text
        or str(sc.get("mechanism") or out.get("mechanism") or ""),
    )
    out["k_close_mode"] = mode
    sc["k_close_mode"] = mode
    out["scene_contract"] = sc
    payload.clear()
    payload.update(out)
    return mode, True


def attach_k_close_mode_to_chat(
    chat: dict[str, Any],
    *,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    out = dict(chat)
    mode = K_UNKNOWN
    if isinstance(payload, dict):
        mode = normalize_k_close_mode(str(payload.get("k_close_mode") or ""))
        sc = payload.get("scene_contract")
        if mode == K_UNKNOWN and isinstance(sc, dict):
            mode = normalize_k_close_mode(str(sc.get("k_close_mode") or ""))
    if mode == K_UNKNOWN:
        mode = k_close_mode_from_story(out)
    out["k_close_mode"] = mode
    return out
