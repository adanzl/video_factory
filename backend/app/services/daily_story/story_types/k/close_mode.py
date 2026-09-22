"""K 类收场模式：K-A 劝失败僵持 vs K-B 旁观后孩子自行收场。"""

from __future__ import annotations

import re
from typing import Any

K_A_PARENT_FAIL_STALEMATE = "K_A_PARENT_FAIL_STALEMATE"
K_B_CHILD_SELF_RESOLVE = "K_B_CHILD_SELF_RESOLVE"
K_UNKNOWN = "K_UNKNOWN"

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
RE_CLOSE_PASSIVE = re.compile(r"不掺和|旁观|不评理|不参与")
RE_CLOSE_FAIL_STALE = re.compile(
    r"劝失败|管不了|僵持|不和好|劝不动|劝不了"
)

# K-B 正文硬卡（只看对白，不看 punchline）
RE_KB_PARENT_PASSIVE = re.compile(
    r"不评理|不参与|不掺和|规矩|不能哭|别找我|挡回|不介入|"
    r"不接|别评|不管你们|吃饭|吃自己的"
)
RE_KB_PARENT_MEDIATE = re.compile(
    r"别闹了|快分开|评评理|谁对谁错|都错了|听妈妈的|我生气了|"
    r"和好吧|快和好|你们去|一起去玩|一块玩"
)
RE_KB_CHILD_RESOLVE = re.compile(
    r"要不要|还玩|走[啊吧]|去不去|吃不吃|再来一局|行了|"
    r"算了|还打吗|要，等|勾肩|出门|玩不玩|还玩不|一起走吧|咱们走"
)
RE_KB_CHILD_ACCEPT = re.compile(
    r"玩！|玩啊|行啊|好啊|要[！。?]|走起|一起[走去吧]|等我|换鞋|走[。！]"
)
RE_KB_CHILD_REJECT = re.compile(r"不要|我拒绝|谁稀罕|不理你|才不")
RE_KB_COLD_TAIL = re.compile(r"不理|谁稀罕|谁怕谁|不认输|不让你|没完就没完")

KID_SPEAKERS = frozenset({"昭昭", "灿灿"})

RE_H_RITUAL = re.compile(
    r"拉手|(?<!不)和好|对不起|原谅|说好了|齐声|抱抱|都错"
)


def normalize_k_close_mode(value: str | None) -> str:
    raw = str(value or "").strip()
    if raw in K_CLOSE_MODES:
        return raw
    return K_UNKNOWN


def k_close_mode_from_story(story: dict[str, Any]) -> str:
    """读稿上已落盘的 k_close_mode；缺省为 K_UNKNOWN（勿当 K-A）。"""
    if not isinstance(story, dict):
        return K_UNKNOWN
    direct = normalize_k_close_mode(str(story.get("k_close_mode") or ""))
    if direct != K_UNKNOWN:
        return direct
    sc = story.get("scene_contract")
    if isinstance(sc, dict):
        nested = normalize_k_close_mode(str(sc.get("k_close_mode") or ""))
        if nested != K_UNKNOWN:
            return nested
    return K_UNKNOWN


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

    if child_self_last and parent_passive and not stale_end:
        return K_B_CHILD_SELF_RESOLVE
    if parent_fail and stale_end and not child_self_last:
        return K_A_PARENT_FAIL_STALEMATE
    if child_self_any and parent_passive:
        if not parent_fail or child_self_last:
            return K_B_CHILD_SELF_RESOLVE
    if parent_fail and not child_self_any:
        return K_A_PARENT_FAIL_STALEMATE
    if parent_passive and child_self_any and not stale_end:
        return K_B_CHILD_SELF_RESOLVE
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
