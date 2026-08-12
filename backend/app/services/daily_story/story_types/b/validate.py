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


# 段4互甩只许一轮（各1句共2句）；甩锅句结构判定（非主题词）
RE_BLAME_TURN = re.compile(
    r"都怪|全怪|怪你|怪我|赖你|赖我|是你|你光|你也没|你倒是|"
    r"你答应|你先|还说|还怪|还赖|都赖|说我",
)
# 对白禁术语（成人/编剧词，孩子不说）：出现即硬卡
RE_DIALOGUE_JARGON = re.compile(r"露馅|甩锅|结盟|翻车|分工|计划")


def append_b_body_errors(story: dict, errors: list[str]) -> None:
    punch = str(story.get("punchline_explain") or "")
    if parse_story_type_code(punchline=punch) != "B":
        return
    lines, speakers = _lines_and_speakers(story)
    if len(lines) < 8:
        return

    from app.services.daily_story.story_types.b.humor import (
        RE_BLEED_CONTENT,
        RE_GARBAGE_FILLER,
        _freeze_lines_issues,
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
            r"站好|过来|罚|不许|今晚|检讨|说清楚|墙角|罚站|别想吃|偷吃|拿的什么|"
            r"调皮|捣蛋|乱来|胡闹|惹事|闹腾|顽皮|淘气",
            lines[i],
        ):
            punish_i = i
            break
    if punish_i is not None:
        pre_punish = lines[max(0, punish_i - 4) : punish_i]
        blame_n = sum(1 for ln in pre_punish if RE_BLAME_TURN.search(ln))
        if blame_n > 2:
            errors.append(
                f"B类：段4互甩只许一轮（≤2句），当前{blame_n}句"
            )
        post_lines = lines[punish_i + 1 :]
        post_speakers = speakers[punish_i + 1 :]
        react_lines = [
            ln
            for sp, ln in zip(post_speakers, post_lines)
            if sp in ("昭昭", "灿灿") and _punish_freeze_react(ln)
        ]
        if _landing_doom_lines_repeat(react_lines):
            errors.append(
                "B类：定格句式重复（勿两句都用完蛋/完了）",
            )
        if freeze_tag := _freeze_lines_issues(react_lines):
            errors.append(
                "B类：定格收束不当"
                + (f"（{freeze_tag}）" if freeze_tag else ""),
            )

    if RE_BLEED_CONTENT.search("".join(lines)):
        errors.append("B类：勿写实流血/止血/创可贴，可说怕扎到不敢动")

    for i, ln in enumerate(lines):
        if RE_GARBAGE_FILLER.search(ln):
            errors.append(f"B类对白[{i}]含无意义语气垫字（句尾叠了呢了呀/好不好/真的呀等）")
            break
    for i, ln in enumerate(lines):
        if RE_DIALOGUE_JARGON.search(ln):
            errors.append(
                f"B类对白[{i}]含成人/编剧术语（露馅/甩锅/结盟/翻车/分工/计划）：{ln!r}"
            )
            break
