"""H 类发现开场校验。"""

from __future__ import annotations

import re

H_OPENING_MEDIATE_RE = re.compile(r"妈妈|别打|和好|调解")
H_OPENING_FIGHT_RE = re.compile(r"抢|弄坏|打|推|不原谅|生气")


def append_h_opening_errors(
    normalized: list[dict],
    *,
    type_code: str | None,
    errors: list[str],
    conflict_core: str = "",
    setting: str = "",
) -> None:
    if (type_code or "").upper() != "H":
        return
    if not normalized:
        return
    first = str(normalized[0].get("line") or "").strip()
    blob = f"{setting}{conflict_core}{first}"
    if H_OPENING_MEDIATE_RE.search(first):
        errors.append("H类开场：首句勿妈妈调解，冲突升级留正文")
    if not H_OPENING_FIGHT_RE.search(blob):
        errors.append("H类开场：首句宜点当场冲突（抢/毁/推等）")
