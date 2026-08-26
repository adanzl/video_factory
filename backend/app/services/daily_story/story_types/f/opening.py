"""F 类发现开场校验。"""

from __future__ import annotations

import re

F_OPENING_C_FIGHT_RE = re.compile(
    r"不公平|凭什么你拿|谁先拿|你先选|我的没|归谁|抢",
)
F_OPENING_B_ALLY_RE = re.compile(
    r"别告诉妈|咱俩|一起瞒|分工|你望风|暗号",
)
F_OPENING_THREAT_RE = re.compile(
    r"讨厌|再说|试试|你敢|哼|别吵|吼|烦",
)


def append_f_opening_errors(
    normalized: list[dict],
    *,
    type_code: str | None,
    errors: list[str],
    conflict_core: str = "",
    setting: str = "",
) -> None:
    if (type_code or "").upper() != "F":
        return
    if not normalized:
        return
    first = str(normalized[0].get("line") or "").strip()
    blob = f"{setting}{conflict_core}{first}"
    if F_OPENING_C_FIGHT_RE.search(first):
        errors.append("F类开场：勿写成 C 争物/公平战首句")
    if F_OPENING_B_ALLY_RE.search(first):
        errors.append("F类开场：勿写成 B 密谋结盟首句")
    if not F_OPENING_THREAT_RE.search(blob):
        errors.append("F类开场：首句宜点互呛/生气（讨厌/再说/试试等）")
