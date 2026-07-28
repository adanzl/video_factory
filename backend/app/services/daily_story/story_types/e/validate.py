"""E 类正文硬卡（妈妈破功收束）。"""

from __future__ import annotations

import re

from app.services.daily_story.story_types import parse_story_type_code, resolve_story_type_code
from app.services.daily_story.story_types.quality import RE_SOFT_LAST

RE_A_WHERE_DIFF = re.compile(r"哪里不一样|都是听|大人也要听小孩")
RE_A_CITE_CLOSE = re.compile(
    r"(?:你刚才(?:明明|自己)?说|你自己(?:刚才)?说|你不是说|你刚说|你说的)",
)
RE_MOM_RULE = re.compile(
    r"应该|必须|规矩|听我的|我说|不行|不能|不许|别吃|得睡|别玩",
)
RE_KID_LOOP = re.compile(
    r"你自己说|你刚才|那你也是|你也这样|那你现在|妈妈你也",
)
RE_MOM_WAFFLE = re.compile(
    r"不是|不一样|那是|总之|反正|不是那个|不算|尝咸淡|大人|工作需要",
)
RE_SLEEP_TOPIC = re.compile(r"睡觉|九点|早睡|刷手机|卧床|被窝|挂钟")
RE_SNACK_TOPIC = re.compile(r"零食|尝菜|偷吃|薯片|饭前不吃|瓜子")

E_BODY_LINES_MIN = 10
E_BODY_LINES_MAX = 16


def _dialogue_lines(story: dict) -> tuple[list[str], list[str]]:
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


def append_e_body_errors(story: dict, errors: list[str]) -> None:
    if resolve_story_type_code(story) != "E":
        return

    lines, speakers = _dialogue_lines(story)
    n = len(lines)
    if n < 8:
        errors.append("E类正文过短，不足以完成妈妈破功收束（至少约 8 句对白）")
        return

    if n > E_BODY_LINES_MAX:
        errors.append(
            f"E类正文过长（宜12–16句），当前{n}句",
        )

    anchor = (
        str(story.get("conflict_core") or "")
        + str(story.get("punchline_explain") or "")
        + str(story.get("theme") or "")
        + str(story.get("_theme") or "")
    )
    sleep_t = bool(RE_SLEEP_TOPIC.search(anchor))
    snack_t = bool(RE_SNACK_TOPIC.search(anchor))
    mom_early = "".join(
        ln
        for sp, ln in zip(speakers[: max(1, n // 2)], lines[: max(1, n // 2)])
        if sp == "妈妈"
    )
    if sleep_t and not snack_t and RE_SNACK_TOPIC.search(mom_early):
        if "九点" not in mom_early and "必须睡觉" not in mom_early:
            errors.append("E类睡觉主题禁串场立零食规矩")
    if snack_t and not sleep_t and RE_SLEEP_TOPIC.search(mom_early):
        if "零食" not in mom_early and "尝" not in mom_early:
            errors.append("E类零食主题禁串场立睡觉规矩")

    tail4 = "".join(lines[-4:])
    tail3 = "".join(lines[-3:])
    body = "".join(lines[: max(0, n - 4)])

    if RE_A_WHERE_DIFF.search(tail4) and (
        "那不一样" in tail4 or RE_A_CITE_CLOSE.search(tail4)
    ):
        errors.append(
            "E类收束勿写成 A 式末四拍；应走孩子追问闭环+妈妈破功",
        )
        return

    if not RE_MOM_RULE.search(body):
        errors.append(
            "E类前段须有妈妈立论/立规矩（应该、必须、听我的等）",
        )
        return

    if not RE_KID_LOOP.search(tail3) and not RE_KID_LOOP.search(tail4):
        errors.append(
            "E类末段须孩子用妈妈原话闭环反问（你自己说/那你也是等）",
        )
        return

    last = lines[-1]
    last_sp = speakers[-1] if speakers else ""
    if last_sp != "妈妈":
        errors.append("E类末句须妈妈破功收场")
        return

    if not RE_SOFT_LAST.search(last) and not re.search(
        r"唉|行了|好吧|随便|说不通|行行行",
        last,
    ):
        errors.append(
            "E类末句妈妈须破功（唉/行了/好吧/随便/说不通等）",
        )
        return

    mom_n = sum(1 for sp in speakers if sp == "妈妈")
    if mom_n > 8:
        errors.append(
            "E类妈妈台词过多（宜4–7句），笑点应在逻辑自相矛盾而非空说教",
        )

    if RE_MOM_WAFFLE.search(tail3) and not RE_KID_LOOP.search(tail3):
        errors.append(
            "E类妈妈改口后须紧跟孩子闭环反问，勿只妈妈单方面狡辩",
        )
