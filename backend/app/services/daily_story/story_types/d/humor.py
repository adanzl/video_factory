"""D 类好笑维硬伤与修订 hint。"""

from __future__ import annotations

import re

RE_LITERAL = re.compile(
    r"照做|按你说的|照你说的|你不是说|字面|按规矩|你让我|你说要",
)
RE_MESS = re.compile(
    r"掉了|滑|洒|乱|坏|打不开|饿着|够不着|弄翻|摔|倒了|全掉|洒一地|堆塌|"
    r"解不开|勒|死结|死疙瘩|大马趴",
)
RE_FIX = re.compile(
    r"我来|我捡|我弄|我扶|只好|只能|没办法|我得|只好碰|我来扶|我帮你",
)
# 收束回旋镖：勿用共享「你说的」，会误伤「按你说的」字面句
RE_BOOM_CLOSE = re.compile(
    r"你自己说|你刚才说|你刚说|你现在也|你也碰了|你也动了",
)
_A_STYLE = re.compile(r"那不一样.*哪里不一样|哪里不一样.*都是听")
_EMPTY_DEBATE = re.compile(r"谁对谁错|到底谁有理|你赢了|我不听你的了")

HUMOR_ISSUE_CAPS: tuple[tuple[str, int], ...] = (
    ("偏A式末四拍", 6),
    ("缺字面执行", 7),
    ("缺后果场面", 6),
    ("缺叮嘱方破规", 7),
    ("回旋镖过早", 5),
    ("破规未先于回旋镖", 6),
    ("空辩论注水", 5),
    ("中段拖沓注水", 5),
    ("回旋镖复读", 5),
    ("二次收束注水", 5),
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
    all_text = "".join(lines)

    if _A_STYLE.search(tail_text) or (
        "哪里不一样" in tail_text and "那不一样" in tail_text
    ):
        cons.append("偏A式末四拍，不好笑")

    if not RE_LITERAL.search(body_text):
        cons.append("缺字面执行，不好笑")

    if RE_LITERAL.search(body_text) and not RE_MESS.search(all_text):
        cons.append("缺后果场面，不好笑")

    fix_i = next((i for i, ln in enumerate(lines) if RE_FIX.search(ln)), None)
    boom_i = next((i for i, ln in enumerate(lines) if RE_BOOM_CLOSE.search(ln)), None)

    if boom_i is not None and fix_i is None:
        cons.append("缺叮嘱方破规，不好笑")
    elif fix_i is None and RE_BOOM_CLOSE.search(tail_text):
        cons.append("缺叮嘱方破规，不好笑")

    if boom_i is not None and fix_i is not None and boom_i < fix_i:
        cons.append("破规未先于回旋镖，不好笑")

    if boom_i is not None and boom_i < n // 3:
        cons.append("回旋镖过早，不好笑")

    if _EMPTY_DEBATE.search(all_text) or (
        sum(1 for ln in body if re.search(r"公平|谁先|不公平", ln)) >= 2
    ):
        cons.append("空辩论注水，不好笑")

    # 中段抠定义过久
    nit_n = sum(
        1
        for ln in body
        if re.search(r"你又没说|只说了|也包括|没说别的|当然包括", ln)
    )
    if nit_n >= 3:
        cons.append("空辩论注水，不好笑")

    if n > 18:
        cons.append("中段拖沓注水，不好笑")

    boom_n = sum(1 for ln in lines if RE_BOOM_CLOSE.search(ln))
    if boom_n >= 2:
        cons.append("回旋镖复读，不好笑")

    soft_indices = [
        i
        for i, ln in enumerate(lines)
        if re.search(r"哼|算了|行吧", ln)
    ]
    if len(soft_indices) >= 2 and soft_indices[0] < n - 3:
        # 中段已哼/算了，后面又开第二场
        if any(RE_BOOM_CLOSE.search(lines[i]) for i in range(soft_indices[0] + 1, n)):
            cons.append("二次收束注水，不好笑")

    return cons


def humor_revision_hint(issue: str) -> str | None:
    keys = (
        "字面",
        "后果",
        "破规",
        "回旋镖",
        "末四拍",
        "空辩论",
        "拖沓",
        "复读",
        "二次收束",
        "D",
    )
    if any(k in issue for k in keys):
        return (
            f"【好笑·D】{issue}。"
            "立具体叮嘱→认真字面画面（端热汤/花生米）→意外一锤→"
            "上手破规→回旋镖≤2句→哼；最多一句尾巴，勿第二场回旋镖。"
        )
    return None
