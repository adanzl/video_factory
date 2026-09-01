"""J 类正文本地修稿：灿灿中段否决同构复读 + 末句镇住。

只做类型级句尾去重/换尾，禁止按 theme 造句。
"""

from __future__ import annotations

import re

from app.services.daily_story.dialogue_text import DAILY_STORY_LINE_CHARS_MAX
from app.services.daily_story.story_types import parse_story_type_code
from app.services.daily_story.story_types.j.validate import RE_HOLD

_RE_J_HOLD = re.compile(r"我说了算")
_RE_J_STUBBORN = re.compile(r"我说不行|不行就不行")

# 与 quality._LIMP_SOFT_CLOSE_MARKERS 对齐：末句命中且无破功痕迹 → 结构 -20
_J_LIMP_LAST: tuple[str, ...] = (
    "哼",
    "算了",
    "好吧",
    "好了好了",
    "行吧",
    "随你",
    "我不管",
    "不管了",
    "随便你",
    "那行",
    "行行行",
    "吃吧",
    "你赢",
    "给你",
)

_J_HOLD_FALLBACK = "听我的，我说了算！"

# 中段否决句尾轮换池（抽象权威压住，不含主题物件）
_J_MID_VETO_TAILS: tuple[str, ...] = (
    "想都别想呀。",
    "哭也没用呀。",
    "反正我不准就不准。",
    "现在收买没用。",
)

# 句内权威尾巴 → 保留前半理由时的替换尾
_J_TAIL_REWRITES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"，?出门我说了算[吧呀啊！。…]*$"), "，今天不准出门。"),
    (re.compile(r"，?这个家我说了算[吧呀啊！。…]*$"), "，反正我不准就不准。"),
    (re.compile(r"，?我说不行就不行[啊！。…]*$"), "，想都别想呀。"),
    (re.compile(r"，?我说不行[啊！。…]*$"), "，想都别想呀。"),
    (re.compile(r"，?我说了算[吧呀啊！。…]*$"), "，想都别想呀。"),
)


def _is_j(story: dict) -> bool:
    punch = str(story.get("punchline_explain") or "")
    code = parse_story_type_code(
        story_type=str(story.get("story_type") or "") or None,
        punchline=punch,
    )
    return code == "J"


def _cancan_indices(dialogue: list[dict]) -> list[int]:
    out: list[int] = []
    for i, item in enumerate(dialogue):
        if not isinstance(item, dict):
            continue
        if str(item.get("speaker") or "").strip() == "灿灿":
            out.append(i)
    return out


def _rewrite_j_veto_tail(line: str, alt: str) -> str | None:
    text = str(line or "").strip()
    if not text:
        return None
    for pat, repl in _J_TAIL_REWRITES:
        if pat.search(text):
            new_line = pat.sub(repl, text, count=1)
            if new_line != text:
                return new_line
    if _RE_J_HOLD.search(text):
        prefix = _RE_J_HOLD.split(text, maxsplit=1)[0].rstrip("，, ")
        if len(prefix) >= 4:
            return f"{prefix}，{alt.lstrip('，')}"
    if _RE_J_STUBBORN.search(text):
        prefix = _RE_J_STUBBORN.split(text, maxsplit=1)[0].rstrip("，, ")
        if len(prefix) >= 4:
            return f"{prefix}，{alt.lstrip('，')}"
    return None


def _ensure_hold_line(line: str) -> str:
    text = str(line or "").strip()
    if RE_HOLD.search(text):
        return text[:DAILY_STORY_LINE_CHARS_MAX]
    core = text.rstrip("！。？…!")
    if not core:
        return _J_HOLD_FALLBACK
    merged = f"{core}，我说了算！"
    return merged[:DAILY_STORY_LINE_CHARS_MAX]


def _patch_j_closing_hold(dialogue: list) -> list[str]:
    """末句昭昭软收（哼/算了…）时，把灿灿镇住落到末句，避免无破功软收 -20。"""
    rows = [x for x in dialogue if isinstance(x, dict) and str(x.get("line") or "").strip()]
    if len(rows) < 2:
        return []
    last = rows[-1]
    prev = rows[-2]
    last_sp = str(last.get("speaker") or "").strip()
    last_ln = str(last.get("line") or "").strip()
    prev_sp = str(prev.get("speaker") or "").strip()
    prev_ln = str(prev.get("line") or "").strip()
    limp = any(m in last_ln for m in _J_LIMP_LAST)

    if last_sp == "灿灿" and RE_HOLD.search(last_ln):
        return []
    if not limp and last_sp == "灿灿":
        last["line"] = _ensure_hold_line(last_ln)
        return ["J末句补镇住"]

    notes: list[str] = []
    if last_sp == "昭昭" and limp and prev_sp == "灿灿":
        hold_line = _ensure_hold_line(prev_ln)
        last["speaker"] = "灿灿"
        last["line"] = hold_line
        prev["speaker"] = "昭昭"
        prev["line"] = last_ln
        notes.append("J末句镇住：软收与压住对调")
        # 对调后若出现昭昭连说（…昭昭认输 + 昭昭软收），并掉前一句认输
        if len(rows) >= 3:
            ante = rows[-3]
            if str(ante.get("speaker") or "").strip() == "昭昭":
                try:
                    dialogue.remove(ante)
                    notes.append("J末句镇住：并掉连说认输")
                except ValueError:
                    pass
        return notes

    if last_sp == "昭昭" and limp:
        last["speaker"] = "灿灿"
        last["line"] = _J_HOLD_FALLBACK
        notes.append("J末句镇住：软收改灿灿压住")
        return notes

    if last_sp != "灿灿" and not RE_HOLD.search(
        "".join(str(r.get("line") or "") for r in rows[-4:])
    ):
        last["speaker"] = "灿灿"
        last["line"] = _J_HOLD_FALLBACK
        notes.append("J末句镇住：补压住收场")
    return notes


def patch_j_body(story: dict) -> list[str]:
    """灿灿中段「我说了算/我说不行」同构复读 → 句尾轮换，末句保留镇住词。"""
    if not _is_j(story):
        return []
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 8:
        return []

    cancan = _cancan_indices(dialogue)
    notes: list[str] = []
    if len(cancan) >= 2:
        hold_seen = 0
        stubborn_seen = 0
        tail_idx = 0
        last_cancan = cancan[-1]

        for idx in cancan:
            item = dialogue[idx]
            if not isinstance(item, dict):
                continue
            line = str(item.get("line") or "").strip()
            if not line:
                continue

            has_hold = bool(_RE_J_HOLD.search(line))
            has_stubborn = bool(_RE_J_STUBBORN.search(line))
            is_closing = idx == last_cancan

            need_rewrite = False
            if has_hold:
                hold_seen += 1
                if hold_seen > 1 and not is_closing:
                    need_rewrite = True
            if has_stubborn:
                stubborn_seen += 1
                if stubborn_seen > 1 and not is_closing:
                    need_rewrite = True

            if not need_rewrite:
                continue

            alt = _J_MID_VETO_TAILS[tail_idx % len(_J_MID_VETO_TAILS)]
            tail_idx += 1
            new_line = _rewrite_j_veto_tail(line, alt)
            if not new_line or new_line == line:
                continue
            item["line"] = new_line
            notes.append(f"J去否决复读[{idx + 1}]")

    notes.extend(_patch_j_closing_hold(dialogue))
    return notes
