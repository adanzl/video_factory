"""O 类正文硬卡（立赛规 + 死磕过程 + 资源溜走 + 点题）。"""

from __future__ import annotations

import re

from app.services.daily_story.story_types import parse_story_type_code

# 抽象不变量：赛规过程执念 + 资源溜走 + 点题；禁单篇菜名/猜拳词表穷举剧情
RE_GAME_RULE = re.compile(
    r"剪刀石头布|猜拳|赢的.*(?:才)?能?吃|赢了.*吃|谁赢|规则是|吹蜡烛"
)
RE_PROCESS_FOCUS = re.compile(r"我赢了|又赢|再来|出拳|认真|光顾着赢|一心|专注")
RE_PRIZE_GONE = re.compile(
    r"少了|没了|空了|见底|只剩|吃光|吃完|吃得差不多|盘子"
)
RE_GOAL_PUNCH = re.compile(
    r"光顾着赢|顾着赢|菜都没了|赢了.*没|白赢|目标.*没|过程.*输"
)
RE_C_BOOMERANG_CLOSE = re.compile(r"你刚说|你说的|那不一样|哪里不一样|八百|吃商")
RE_A_BACKFIRE = re.compile(r"那不一样|都是听|破功|自相矛盾|你刚才说")
RE_N_SOLEMN = re.compile(r"因为.*就能|一本正经|荒诞自洽")
RE_I_SOUL = re.compile(r"爱学习|你爱吗|灵魂|拷问")


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


def append_o_body_errors(story: dict, errors: list[str]) -> None:
    punch = str(story.get("punchline_explain") or "")
    code = parse_story_type_code(
        story_type=str(story.get("story_type") or "") or None,
        punchline=punch,
    )
    if code != "O":
        return
    lines, _speakers = _lines_and_speakers(story)
    if len(lines) < 6:
        return

    body = "".join(lines)
    tail5 = "".join(lines[-5:])
    core = str(story.get("conflict_core") or "")
    blob = f"{core}{body}"
    if not RE_GAME_RULE.search(blob) and not RE_PROCESS_FOCUS.search(body):
        errors.append("O类：正文须有立赛规或死磕过程（猜拳/赢赛/再来等）")
    if not RE_PRIZE_GONE.search(blob):
        errors.append("O类：须有资源溜走（少了/没了/只剩/吃光等）")
    if not RE_GOAL_PUNCH.search(blob) and not RE_GOAL_PUNCH.search(tail5):
        errors.append("O类：收束须点题顾过程丢目标（光顾着赢/X没了等）")
    if RE_A_BACKFIRE.search(tail5):
        errors.append("O类：末段勿 A 式反噬/破功链")
    if RE_C_BOOMERANG_CLOSE.search(tail5) and not RE_GOAL_PUNCH.search(tail5):
        errors.append("O类：末段勿套 C 回旋镖收束，须落点题认栽")
    if RE_I_SOUL.search(body):
        errors.append("O类：勿写成 I 灵魂拷问（爱学习/你爱吗）")
    if RE_N_SOLEMN.search(body) and not RE_GOAL_PUNCH.search(body):
        errors.append("O类：勿写成 N 正经胡说自洽链")
