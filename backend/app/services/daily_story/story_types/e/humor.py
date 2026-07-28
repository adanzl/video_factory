"""E 类好笑维硬伤与修订 hint。"""

from __future__ import annotations

import re

RE_MOM_RULE = re.compile(
    r"应该|必须|规矩|听我的|我说|不行|不能|不许|别吃|得睡|别玩",
)
RE_KID_ASK = re.compile(
    r"为什么|凭什么|那你|你也|上次|妈妈你也|算不算|怎么又",
)
RE_MOM_WAFFLE = re.compile(
    r"不是|不一样|那是|总之|反正|不是那个|不算|尝咸淡|大人|工作需要",
)
RE_LOOP = re.compile(
    r"你自己说|你刚才|那你也是|你也这样|那你现在|妈妈你也",
)
RE_MOM_SOFT = re.compile(r"唉|行了|好吧|随便|说不通|行行行|算了")
_A_STYLE = re.compile(r"那不一样.*哪里不一样|哪里不一样.*都是听")
_EMPTY = re.compile(r"你赢了|算你厉害|谁对谁错|我不听了")

HUMOR_ISSUE_CAPS: tuple[tuple[str, int], ...] = (
    ("偏A式末四拍", 6),
    ("缺妈妈立论", 6),
    ("缺孩子追问", 6),
    ("缺妈妈改口", 6),
    ("缺追问闭环", 7),
    ("末句非妈妈破功", 7),
    ("妈妈说教过长", 5),
    ("空说教注水", 5),
    ("中段拖沓注水", 5),
    ("破功过早", 5),
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
    all_text = "".join(lines)
    mid = lines[2:-3] if n > 6 else body

    if _A_STYLE.search(tail_text) or (
        "哪里不一样" in tail_text and "那不一样" in tail_text
    ):
        cons.append("偏A式末四拍，不好笑")

    if not RE_MOM_RULE.search(body_text) and not RE_MOM_RULE.search(
        "".join(lines[: max(1, n // 2)]),
    ):
        cons.append("缺妈妈立论，不好笑")

    if not RE_KID_ASK.search("".join(mid)) and not RE_KID_ASK.search(body_text):
        cons.append("缺孩子追问，不好笑")

    if not RE_MOM_WAFFLE.search(all_text):
        cons.append("缺妈妈改口，不好笑")

    if not RE_LOOP.search(tail_text):
        cons.append("缺追问闭环，不好笑")

    if speakers and len(speakers) == n:
        if speakers[-1] != "妈妈":
            cons.append("末句非妈妈破功，不好笑")
        elif not RE_MOM_SOFT.search(lines[-1]):
            cons.append("末句非妈妈破功，不好笑")
        if speakers.count("妈妈") > 8:
            cons.append("妈妈说教过长，不好笑")

    soft_i = next(
        (i for i, ln in enumerate(lines) if RE_MOM_SOFT.search(ln)),
        None,
    )
    if soft_i is not None and soft_i < n - 2 and speakers:
        # 破功后还继续讲理
        if any(
            speakers[i] == "妈妈" and RE_MOM_RULE.search(lines[i])
            for i in range(soft_i + 1, n)
        ):
            cons.append("破功过早，不好笑")

    lecture_n = sum(
        1
        for i, ln in enumerate(lines)
        if speakers
        and i < len(speakers)
        and speakers[i] == "妈妈"
        and re.search(r"听我的|我说了|必须听|要听话|道理", ln)
    )
    if lecture_n >= 3 or _EMPTY.search(all_text):
        cons.append("空说教注水，不好笑")

    if n > 16:
        cons.append("中段拖沓注水，不好笑")

    return cons


def humor_revision_hint(issue: str) -> str | None:
    keys = (
        "妈妈",
        "E",
        "闭环",
        "追问",
        "改口",
        "立论",
        "说教",
        "拖沓",
        "末四拍",
        "破功",
    )
    if any(k in issue for k in keys):
        return (
            f"【好笑·E】{issue}。"
            "妈妈短立论→孩子用场面抓现行→妈妈改口开脱→"
            "孩子用原话闭环→末句妈妈行行行；勿A式末四拍、勿长说教。"
        )
    return None
