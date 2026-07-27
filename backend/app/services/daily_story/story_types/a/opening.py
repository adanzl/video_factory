"""A 类发现开场校验。"""

from __future__ import annotations

import re

# A 开场禁止先揭穿一锤（灿灿已翻车/双标）
A_OPENING_SPOILER_RE = re.compile(
    r"自己才|自己刷了|自己算错|自己写错|自己弹错|"
    r"草稿.{0,6}错|计时器上自己|你也错了|"
    r"刚玩过|你上次|双标|才刷了半|一分半",
)
# A 开场禁止「互怼中途读数/宣判」——须先看见场面
A_OPENING_MID_FIGHT_RE = re.compile(
    r"计时器才走|才走了\s*\d+\s*秒|才走了\s*[一二三四五六七八九十两半]+\s*秒|"
    r"至少两分钟|牙医说的|重刷|时间到了|到点了",
)


def append_a_opening_errors(
    normalized: list[dict],
    *,
    type_code: str | None,
    errors: list[str],
) -> None:
    code = (type_code or "").strip().upper()[:1]
    if code != "A":
        return
    for i, item in enumerate(normalized):
        line = item["line"]
        if A_OPENING_SPOILER_RE.search(line):
            errors.append(
                f"opening[{i}] A类禁止开场先揭穿灿灿翻车/双标"
                "（自己才刷/算错/刚玩过等），一锤留给正文中段",
            )
            break
        if A_OPENING_MID_FIGHT_RE.search(line):
            errors.append(
                f"opening[{i}] A类开场须像发现现场（物/动作），"
                "禁止读秒宣判或直接立规（如「计时器才走了30秒」）",
            )
            break
