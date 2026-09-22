"""K 类对白疑点（非硬拦）。"""

from __future__ import annotations

import re

_KID_NAMES = frozenset({"昭昭", "灿灿"})


def collect_k_dialogue_suspicions(
    lines: list[str],
    speakers: list[str],
) -> list[str]:
    """自称呼等疑点；合法如「我叫昭昭」不记。"""
    suspicions: list[str] = []
    if len(lines) != len(speakers):
        n = min(len(lines), len(speakers))
        lines = lines[:n]
        speakers = speakers[:n]
    for sp, line in zip(speakers, lines, strict=False):
        name = str(sp or "").strip()
        text = str(line or "").strip()
        if name not in _KID_NAMES or name not in text:
            continue
        if re.search(rf"我叫{name}|你喊我{name}|是{name}[！。]|叫{name}[！。]", text):
            continue
        if re.search(rf"^{re.escape(name)}[，,！!？?]|{re.escape(name)}你", text):
            suspicions.append(f"疑点：{name}台词含自名「{name}」需人工看语境")
            break
    tail = lines[-5:] if len(lines) >= 5 else lines
    if len(tail) >= 3:
        cold = sum(
            1
            for ln in tail
            if re.search(r"不理|谁稀罕|不认输|不让你|谁怕谁", ln)
        )
        if cold >= 3:
            suspicions.append("疑点：末段连续冷战表态堆叠")
    return suspicions
