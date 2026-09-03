"""I 类正文硬卡（灵魂拷问 + 语塞 + 一招制敌）。"""

from __future__ import annotations

import re

from app.services.daily_story.story_types import parse_story_type_code

RE_SOUL_QUESTION = re.compile(
    r"爱学习|你爱吗|灵魂|拷问|凭啥|相同|为啥|"
    r"那你怎么|你那是.*吗|为你好|你才.*呢|"
    r"快乐.*重要|重要.*快乐|双标|强词夺理|你自己"
)
# 语塞：明示败北 + 抽象卡壳/结巴（省略号认输），勿按单篇词表堆叠
RE_SPEECHLESS = re.compile(
    r"说不过|语塞|哑口|不说了|看.{0,2}窗外|憋不出|张了张嘴|委屈|"
    r"答不上|说不出|接不上|卡壳|服了|张口结舌|憋红|"
    r"我……|……我"
)
RE_WIN_STUBBORN = re.compile(
    r"一招制敌|制敌|服不服|别跟我吵|不爱学习还|不爱学习就别|看你还说|还说啥|嘴硬"
)
RE_A_BACKFIRE = re.compile(r"那不一样|都是听|破功|自相矛盾|你刚才说")
_RE_CLOSING_WIN_CLAIM = re.compile(r"总结|制敌|得意|嘴硬|问倒")
# 服软：语塞后首次服软/放弃争夺即收束点（抽象表达，勿按单篇台词堆叠）
RE_I_SURRENDER = re.compile(
    r"认输|服了|我这就去|这就去写|行了吧|听你的|真的呀.*写|"
    r"说得对|你赢了|不跟你争|不跟你抢|我去写"
)
# 首次收束后允许的拖尾句数（与 patch 裁尾容忍一致）
I_CLOSING_TAIL_ALLOW = 1


def find_i_close_index(lines: list[str]) -> int:
    """首次收束段末尾（连续制敌/服软拍的最后一拍）下标；未出现则 -1。

    收束段 = 语塞后的制敌/服软句及其后紧邻的制敌/服软拍
    （「制敌→服软」「服软→制敌」都算收束过程），段后拖尾须裁。
    """
    speechless_seen = False
    for i, ln in enumerate(lines):
        if RE_SPEECHLESS.search(ln):
            speechless_seen = True
        if not (RE_WIN_STUBBORN.search(ln) or
                (speechless_seen and RE_I_SURRENDER.search(ln))):
            continue
        j = i
        while j + 1 < len(lines):
            nxt = lines[j + 1]
            if RE_WIN_STUBBORN.search(nxt) or (
                speechless_seen and RE_I_SURRENDER.search(nxt)
            ):
                j += 1
            else:
                break
        return j
    return -1


def repair_closing_intent_from_seed_win(
    closing_intent: str,
    dialogue_seed: list | None,
) -> str:
    """I：closing 赢家与 seed 末段制敌 speaker 冲突时，以 seed 为准。"""
    closing = str(closing_intent or "").strip()
    if not isinstance(dialogue_seed, list) or not dialogue_seed:
        return closing
    win_speaker = ""
    for item in reversed(dialogue_seed):
        if not isinstance(item, dict):
            continue
        text = str(item.get("intent") or item.get("line") or "").strip()
        if not text or not RE_WIN_STUBBORN.search(text):
            continue
        sp = str(item.get("speaker") or "").strip()
        if sp:
            win_speaker = sp
            break
    if not win_speaker:
        return closing
    if not closing:
        return f"{win_speaker}得意总结一招制敌"
    others = [n for n in ("灿灿", "昭昭") if n != win_speaker]
    wrong = any(
        o in closing and _RE_CLOSING_WIN_CLAIM.search(closing) for o in others
    )
    if wrong or (
        win_speaker not in closing and _RE_CLOSING_WIN_CLAIM.search(closing)
    ):
        return f"{win_speaker}得意总结一招制敌"
    return closing


def _seed_soul_or_win_speaker(dialogue_seed: list | None) -> str:
    if not isinstance(dialogue_seed, list):
        return ""
    for item in dialogue_seed:
        if not isinstance(item, dict):
            continue
        text = str(item.get("intent") or item.get("line") or "").strip()
        if RE_SOUL_QUESTION.search(text):
            sp = str(item.get("speaker") or "").strip()
            if sp:
                return sp
    for item in reversed(dialogue_seed):
        if not isinstance(item, dict):
            continue
        text = str(item.get("intent") or item.get("line") or "").strip()
        if RE_WIN_STUBBORN.search(text):
            sp = str(item.get("speaker") or "").strip()
            if sp:
                return sp
    return ""


def repair_conflict_core_from_seed_win(
    conflict_core: str,
    dialogue_seed: list | None,
) -> str:
    """I：conflict 把拷问/制胜安错人时，按 seed 灵魂拷问/制敌 speaker 纠偏。"""
    conflict = str(conflict_core or "").strip()
    agent = _seed_soul_or_win_speaker(dialogue_seed)
    if not agent or not conflict:
        return conflict
    other = "灿灿" if agent == "昭昭" else ("昭昭" if agent == "灿灿" else "")
    if not other:
        return conflict
    # 姐姐≈灿灿；若 seed 赢家是昭昭却写「姐姐用…制胜」→ 纠偏
    wrong_agent = False
    if agent == "昭昭" and re.search(r"姐姐用|灿灿用|姐姐.*?(拷问|制胜|问倒)", conflict):
        wrong_agent = True
    if agent == "灿灿" and re.search(r"昭昭用|弟弟用|昭昭.*?(拷问|制胜|问倒)", conflict):
        wrong_agent = True
    if not wrong_agent and agent in conflict:
        return conflict
    if wrong_agent or agent not in conflict:
        return f"姐弟现场冲突，{agent}灵魂拷问问倒{other}，一招制敌"
    return conflict


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


def append_i_body_errors(story: dict, errors: list[str]) -> None:
    punch = str(story.get("punchline_explain") or "")
    code = parse_story_type_code(
        story_type=str(story.get("story_type") or "") or None,
        punchline=punch,
    )
    if code != "I":
        return
    lines, _speakers = _lines_and_speakers(story)
    if len(lines) < 8:
        return

    body = "".join(lines)
    tail4 = "".join(lines[-4:])
    if not RE_SOUL_QUESTION.search(body):
        errors.append("I类：正文须有灵魂拷问/价值高地（你爱吗/爱学习等）")
    if not RE_SPEECHLESS.search(body):
        errors.append("I类：正文须写对方语塞/败北（说不过/看窗外等）")
    if not RE_WIN_STUBBORN.search(tail4):
        errors.append("I类：末段须赢家一招制敌（制敌/服不服等）")
    if RE_A_BACKFIRE.search(tail4):
        errors.append("I类：末段勿 A 式反噬/破功链")
    close_idx = find_i_close_index(lines)
    if close_idx >= 0 and len(lines) - close_idx - 1 > I_CLOSING_TAIL_ALLOW:
        errors.append(
            f"I类：首次收束（第{close_idx + 1}句制敌/服软）后仍有"
            f"{len(lines) - close_idx - 1}句拖尾，首轮收束即止"
        )
