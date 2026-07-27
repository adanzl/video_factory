"""D 类好笑维硬伤与修订 hint。"""

from __future__ import annotations

import re

from app.services.daily_story.story_types.quality import RE_BOOMERANG_RULE

RE_LITERAL = re.compile(r"照做|按你说的|你不是说|字面|按规矩|你让我")
RE_MESS = re.compile(r"掉了|滑|洒|乱|坏|打不开|饿着|够不着|弄翻|摔")
RE_FIX = re.compile(r"我来|我捡|我弄|只好|只能|没办法|我得|只好碰")
_A_STYLE = re.compile(r"那不一样.*哪里不一样|哪里不一样.*都是听")

HUMOR_ISSUE_CAPS: tuple[tuple[str, int], ...] = (
    ("偏A式末四拍", 6),
    ("缺字面执行", 7),
    ("缺后果场面", 6),
    ("缺叮嘱方破规", 7),
    ("回旋镖过早", 5),
)


def collect_humor_issues(
    lines: list[str],
    speakers: list[str] | None,
) -> list[str]:
    _ = speakers
    cons: list[str] = []
    n = len(lines)
    if n < 6:
        return cons

    body = lines[:-4] if n > 4 else lines[:-2]
    tail4 = lines[-4:] if n >= 4 else lines
    body_text = "".join(body)
    tail_text = "".join(tail4)

    if _A_STYLE.search(tail_text) or (
        "哪里不一样" in tail_text and "那不一样" in tail_text
    ):
        cons.append("偏A式末四拍")

    if not RE_LITERAL.search(body_text):
        cons.append("缺字面执行")

    if RE_LITERAL.search(body_text) and not RE_MESS.search(body_text):
        cons.append("缺后果场面")

    if RE_BOOMERANG_RULE.search(tail_text) and not RE_FIX.search(tail_text):
        cons.append("缺叮嘱方破规")

    if RE_BOOMERANG_RULE.search(body_text) and not RE_BOOMERANG_RULE.search(
        tail_text,
    ):
        cons.append("回旋镖过早")

    return cons


def humor_revision_hint(issue: str) -> str | None:
    if "字面" in issue or "D" in issue or "回旋镖" in issue or "后果" in issue:
        return (
            f"【好笑·D】{issue}。"
            "中段写清「按叮嘱字面做」→可见搞砸→叮嘱方被迫破规补救→"
            "末段用原话回旋镖，勿A式哪里不一样。"
        )
    return None
