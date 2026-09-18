"""G 类正文硬卡（pivot + 暖收，非 C/F 收束）。

M4+G 权威点题旁路：``closing_mode=authority_punchline`` 时改用
立规→反将→认怂让渡→权威点题槽位，不放宽标准 G 的 pivot/暖收。
"""

from __future__ import annotations

import re

from app.services.daily_story.story_types import parse_story_type_code
from app.services.daily_story.story_types.quality import RE_BOOMERANG_RULE
from app.services.gold_story.structure_resolve import (
    CLOSING_MODE_AUTHORITY_PUNCHLINE,
)

# 去掉裸「管你」，避免「不用你管」假阳性；同路巧合允许「先问去向」类关心
RE_PIVOT = re.compile(
    r"护|撑腰|拼命|动你|心疼|认真的|我怕|别叫我|老弟|我弟|重要|舍不得|在乎|"
    r"你去哪|去哪儿|你一个人|一个人走|一个人回|陪你|放心不下|怕你|"
    r"你先说|你先讲",
)
RE_STUNNED = re.compile(
    r"你说啥|你说什么|……|\.\.\.|愣|啥\？|什么\？|笑出声|噗|忍不住笑",
)
RE_SOFT_CLOSE = re.compile(
    r"擦|药|说好了|行了|过来|撑腰|嗯|笑|好\s*吧|别.*欺负|识相|饶|原谅|算了|"
    r"一起走|一起去|一起回|走吧|同路|顺路|没走成|谁也没",
)
# 须双方僵持结构；裸「谁也不」会误伤「谁也没走成」
RE_F_STALE = re.compile(
    r"不跟你玩|不跟你好了|不理你|回家.*不|"
    r"谁也不理谁|谁也不跟谁说话|谁也不让谁|爱咋咋",
)

# 权威点题旁路槽位（抽象，禁绑平板/巧克力等单篇词）
RE_AUTH_RULE = re.compile(r"谁先|立规|约好|规定|规矩|定规|作业|写完")
RE_AUTH_REVERSE = re.compile(
    r"不罚|没发火|反而|反把|那今晚|那你负责|你负责|今晚你|负责哄|藏得"
)
RE_AUTH_CEDE = re.compile(
    r"立刻.*(给|塞|让)|你玩你玩|我哄|认怂|塞给|让出|你玩"
)
RE_AUTH_PUNCH = re.compile(
    r"记住|宣布|点破|并列|第[一二三]|这个家|这个班|听清楚|我说了算"
)
# 反将后抗拒/辩解（抽象：不会/不要/换/真不会，禁绑单篇词）
RE_AUTH_RESIST = re.compile(
    r"不会|不要|换件|换事|我真|凭什么|为啥|干嘛|不行吧|太难"
)


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


def _is_authority_punchline_mode(story: dict) -> bool:
    mode = str(story.get("closing_mode") or "").strip()
    return mode == CLOSING_MODE_AUTHORITY_PUNCHLINE


def _append_g_authority_punchline_errors(
    story: dict,
    errors: list[str],
    *,
    lines: list[str],
) -> None:
    body = "".join(lines)
    tail4 = "".join(lines[-4:])
    last = lines[-1] if lines else ""
    if not RE_AUTH_RULE.search(body):
        errors.append("G类(权威点题)：正文须有立规/约好槽")
    if not RE_AUTH_REVERSE.search(body):
        errors.append("G类(权威点题)：正文须有反将任务/不罚反递槽")
    if not RE_AUTH_RESIST.search(body):
        errors.append("G类(权威点题)：反将后须有抗拒/辩解槽")
    if not RE_AUTH_CEDE.search(body):
        errors.append("G类(权威点题)：正文须有认怂让渡槽")
    if not RE_AUTH_PUNCH.search(last):
        errors.append("G类(权威点题)：末句须权威点题/秩序宣布")
    elif not RE_AUTH_CEDE.search("".join(lines[:-1])):
        errors.append("G类(权威点题)：权威点题前须已有认怂让渡")
    if RE_BOOMERANG_RULE.search(tail4):
        errors.append("G类：末段勿 C 式回旋镖戳穿")
    if RE_F_STALE.search(tail4) and not RE_AUTH_PUNCH.search(tail4):
        errors.append("G类：末段勿 F 式威胁僵持")


def append_g_body_errors(story: dict, errors: list[str]) -> None:
    punch = str(story.get("punchline_explain") or "")
    if parse_story_type_code(punchline=punch) != "G":
        return
    lines, _speakers = _lines_and_speakers(story)
    if len(lines) < 10:
        return

    if _is_authority_punchline_mode(story):
        _append_g_authority_punchline_errors(story, errors, lines=lines)
        return

    body = "".join(lines)
    tail3 = "".join(lines[-3:])
    if not RE_PIVOT.search(body):
        errors.append("G类：正文须有 pivot（护短/护姐/真心一句）")
    if not RE_STUNNED.search(body):
        errors.append("G类：pivot 后须有愣住 beat（你说啥/……等）")
    if not RE_SOFT_CLOSE.search(tail3):
        errors.append("G类：末段须暖收或半暖（擦药/撑腰/说好了等）")
    if RE_BOOMERANG_RULE.search(tail3):
        errors.append("G类：末段勿 C 式回旋镖戳穿")
    # 末段已有暖收信号时，不把残余互呛词当 F 僵持
    if RE_F_STALE.search(tail3) and not RE_SOFT_CLOSE.search(tail3):
        errors.append("G类：末段勿 F 式威胁僵持")
