"""G 类发现开场校验。"""

from __future__ import annotations

import re

G_OPENING_C_FIGHT_RE = re.compile(
    r"不公平|凭什么你拿|谁先拿|你先选|我的没|归谁|抢",
)
G_OPENING_PREMISE_RE = re.compile(
    r"咋了|怎么|又|手|伤|丢人|闯祸|骂|烦|气",
)


def append_g_opening_errors(
    normalized: list[dict],
    *,
    type_code: str | None,
    errors: list[str],
    conflict_core: str = "",
    setting: str = "",
) -> None:
    if (type_code or "").upper() != "G":
        return
    if not normalized:
        return
    first = str(normalized[0].get("line") or "").strip()
    if G_OPENING_C_FIGHT_RE.search(first):
        errors.append("G类开场：勿写成 C 争物/公平战首句")
    blob = f"{setting}{conflict_core}{first}"
    if not G_OPENING_PREMISE_RE.search(blob):
        errors.append("G类开场：首句宜点现状/担心/生气，再进数落")
