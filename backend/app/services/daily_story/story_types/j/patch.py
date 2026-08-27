"""J 类正文本地修稿：灿灿中段否决同构复读。

只做类型级句尾去重/换尾，禁止按 theme 造句。
"""

from __future__ import annotations

import re

from app.services.daily_story.story_types import parse_story_type_code

_RE_J_HOLD = re.compile(r"我说了算")
_RE_J_STUBBORN = re.compile(r"我说不行|不行就不行")

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


def patch_j_body(story: dict) -> list[str]:
    """灿灿中段「我说了算/我说不行」同构复读 → 句尾轮换，末句保留镇住词。"""
    if not _is_j(story):
        return []
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 8:
        return []

    cancan = _cancan_indices(dialogue)
    if len(cancan) < 2:
        return []

    notes: list[str] = []
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

    return notes
