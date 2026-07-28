"""C 类正文硬卡（收束形态、防写成 A 式末四拍）。"""

from __future__ import annotations

import re

from app.services.daily_story.story_types import parse_story_type_code
from app.services.daily_story.story_types.quality import (
    RE_BOOMERANG_RULE,
    RE_REVELATION_PROP,
    RE_SOFT_LAST,
    RE_SURRENDER,
    RE_TWIST_SEGUE,
)

# A 类末四拍标志性组合（C 稿勿全套照搬）
RE_A_WHERE_DIFF = re.compile(r"哪里不一样|都是听|大人也要听小孩|大人要听小孩")
RE_A_CITE_CLOSE = re.compile(
    r"(?:你刚才(?:明明|自己)?说|你自己(?:刚才)?说|你不是说|你刚说|你说的)",
)
# 末句须收完整（24 字/句限制下尤忌写到一半）
RE_C_LINE_END_OK = re.compile(
    r"(?:[。！？…]|哼|行吧|随便|好吧|算了|认了|你赢|我先|你先|算了算)",
)


def _line_incomplete(line: str) -> bool:
    s = line.strip()
    if not s:
        return True
    if s[-1] in "'\"‘’「」":
        return True
    if s.count("'") % 2 == 1 or s.count('"') % 2 == 1:
        return True
    if s.count("「") != s.count("」"):
        return True
    if RE_C_LINE_END_OK.search(s[-4:]):
        return False
    if RE_SOFT_LAST.search(s) or RE_SURRENDER.search(s[-8:]):
        return False
    if s[-1] in "呀嘛啊呢吧了哼":
        return False
    return not bool(re.search(r"[。！？…]$", s))


def _dialogue_lines(story: dict) -> tuple[list[str], list[str]]:
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return [], []
    lines: list[str] = []
    speakers: list[str] = []
    for item in dialogue:
        if not isinstance(item, dict):
            continue
        sp = str(item.get("speaker") or "").strip()
        ln = str(item.get("line") or "").strip()
        if not ln:
            continue
        speakers.append(sp)
        lines.append(ln)
    return lines, speakers


def _closing_ok(tail4: str, tail3: str) -> bool:
    if RE_BOOMERANG_RULE.search(tail4) or RE_BOOMERANG_RULE.search(tail3):
        return True
    if RE_REVELATION_PROP.search(tail4) and (
        RE_TWIST_SEGUE.search(tail3) or RE_BOOMERANG_RULE.search(tail4)
    ):
        return True
    return False


def append_c_body_errors(story: dict, errors: list[str]) -> None:
    punch = str(story.get("punchline_explain") or "")
    if parse_story_type_code(punchline=punch) != "C":
        return

    lines, speakers = _dialogue_lines(story)
    n = len(lines)
    if n < 8:
        errors.append("C类正文过短，不足以完成公平执念收束（至少约 8 句对白）")
        return

    tail4 = "".join(lines[-4:])
    tail3 = "".join(lines[-3:])
    last = lines[-1]
    last_sp = speakers[-1] if speakers else ""

    if last_sp == "妈妈":
        errors.append("C类末句须姐弟一方嘴硬收场，禁止妈妈收束")
        return

    if RE_A_WHERE_DIFF.search(tail4) and (
        "那不一样" in tail4 or RE_A_CITE_CLOSE.search(tail4)
    ):
        errors.append(
            "C类收束勿写成 A 式末四拍（引话+那不一样+哪里不一样）；"
            "应走回旋镖或实物反转",
        )
        return

    for ln in lines[-3:-1]:
        if _line_incomplete(ln):
            errors.append(
                "C类收束对白须写完整（每句≤24字且以。！？或哼/行吧等收束，"
                "禁止停在引号或未说完）",
            )
            return

    if not _closing_ok(tail4, tail3):
        errors.append(
            "C类末段须有回旋镖（用对方刚立的规则反问）"
            "或实物真相反转收束",
        )
        return

    if _line_incomplete(last) and not (
        RE_SOFT_LAST.search(last) or RE_SURRENDER.search(last)
    ):
        errors.append(
            "C类末句须写完整或嘴硬软收（哼/行吧/给你/算了等）",
        )
        return

    if not (
        RE_SOFT_LAST.search(last)
        or RE_SURRENDER.search(last)
    ):
        errors.append(
            "C类末句须被戳穿方嘴硬软收（哼/行吧/给你/算了等），"
            "禁止赢家总结或继续立规矩",
        )
        return

    if len(speakers) >= 2 and speakers[-1] == speakers[-2]:
        errors.append("C类收束末两句须换人，禁止同人连说")