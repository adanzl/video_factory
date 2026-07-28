"""B 类正文硬卡（段5定格收束）。"""

from __future__ import annotations

import re

from app.services.daily_story.story_types import parse_story_type_code


def _lines_and_speakers(story: dict) -> tuple[list[str], list[str]]:
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


def append_b_body_errors(story: dict, errors: list[str]) -> None:
    punch = str(story.get("punchline_explain") or "")
    if parse_story_type_code(punchline=punch) != "B":
        return
    lines, speakers = _lines_and_speakers(story)
    if len(lines) < 8:
        return

    from app.services.daily_story.story_types.b.humor import (
        _landing_doom_lines_repeat,
        _punish_freeze_react,
        analyze_post_freeze_bloat,
        analyze_punish_landing,
        analyze_pre_punish_self_preservation,
    )

    weak, landing_tag = analyze_punish_landing(lines, speakers)
    if weak:
        errors.append(
            "B类：惩罚令后缺定格收束"
            + (f"（{landing_tag}）" if landing_tag else ""),
        )

    bloat, bloat_tag = analyze_post_freeze_bloat(lines, speakers)
    if bloat:
        errors.append(
            "B类：定格后勿再写对白"
            + (f"（{bloat_tag}）" if bloat_tag else ""),
        )

    pre_weak, pre_tag = analyze_pre_punish_self_preservation(lines, speakers)
    if pre_weak:
        errors.append(
            "B类：惩罚令前缺联盟自保甩锅"
            + (f"（{pre_tag}）" if pre_tag else ""),
        )

    punish_i = None
    for i in range(len(lines) - 1, max(-1, len(lines) - 12), -1):
        if speakers[i] == "妈妈" and re.search(
            r"站好|过来|罚|不许|今晚|检讨|说清楚|墙角|罚站|别想吃",
            lines[i],
        ):
            punish_i = i
            break
    if punish_i is not None:
        post_lines = lines[punish_i + 1 :]
        post_speakers = speakers[punish_i + 1 :]
        react_lines = [
            ln
            for sp, ln in zip(post_speakers, post_lines)
            if sp in ("昭昭", "灿灿") and _punish_freeze_react(ln)
        ]
        if _landing_doom_lines_repeat(react_lines):
            errors.append(
                "B类：定格句式重复（勿完蛋了/我也完了连用，改不同句式如真倒霉）",
            )
