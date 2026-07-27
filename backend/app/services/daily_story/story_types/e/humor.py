"""E 类好笑维硬伤与修订 hint。"""

from __future__ import annotations

import re

RE_MOM_RULE = re.compile(r"应该|必须|规矩|听我的|我说|不行|不能")
RE_KID_ASK = re.compile(r"为什么|凭什么|那你|你也|上次|妈妈你也")
RE_LOOP = re.compile(r"你自己说|你刚才|那你也是|你也这样")
RE_MOM_SOFT = re.compile(r"唉|行了|好吧|随便|说不通|行行行")
_A_STYLE = re.compile(r"那不一样.*哪里不一样")

HUMOR_ISSUE_CAPS: tuple[tuple[str, int], ...] = (
    ("偏A式末四拍", 6),
    ("缺妈妈立论", 6),
    ("缺追问闭环", 7),
    ("末句非妈妈破功", 7),
    ("妈妈说教过长", 5),
)


def collect_humor_issues(
    lines: list[str],
    speakers: list[str] | None,
) -> list[str]:
    cons: list[str] = []
    n = len(lines)
    if n < 6:
        return cons

    tail4 = lines[-4:] if n >= 4 else lines
    tail_text = "".join(tail4)
    body = lines[:-4] if n > 4 else lines[:-2]
    body_text = "".join(body)

    if _A_STYLE.search(tail_text):
        cons.append("偏A式末四拍")

    if not RE_MOM_RULE.search(body_text):
        cons.append("缺妈妈立论")

    if not RE_LOOP.search(tail_text):
        cons.append("缺追问闭环")

    if speakers and len(speakers) == n:
        if speakers[-1] != "妈妈":
            cons.append("末句非妈妈破功")
        elif not RE_MOM_SOFT.search(lines[-1]):
            cons.append("末句非妈妈破功")

    if speakers and speakers.count("妈妈") > 6:
        cons.append("妈妈说教过长")

    if RE_KID_ASK.search(body_text) and not RE_LOOP.search(tail_text):
        cons.append("缺追问闭环")

    return cons


def humor_revision_hint(issue: str) -> str | None:
    if "妈妈" in issue or "E" in issue or "闭环" in issue:
        return (
            f"【好笑·E】{issue}。"
            "妈妈短立论→孩子字面追问→妈妈改口→孩子用原话闭环→"
            "末句妈妈唉/行行行破功；勿A式末四拍。"
        )
    return None
