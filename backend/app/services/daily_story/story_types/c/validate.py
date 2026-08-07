"""C 类正文硬卡（收束形态、防写成 A 式末四拍）。"""

from __future__ import annotations

import re

from app.services.daily_story.story_types import parse_story_type_code
from app.services.daily_story.story_types.quality import (
    RE_BOOMERANG_RULE,
    RE_REVELATION_PROP,
    RE_SOFT_LAST,
    RE_SURRENDER,
    RE_TWIST_SEGUE,
)

# A 类末四拍标志性组合（C 稿勿全套照搬）
RE_A_WHERE_DIFF = re.compile(r"哪里不一样|都是听|大人也要听小孩|大人要听小孩")
RE_A_CITE_CLOSE = re.compile(
    r"(?:你刚才(?:明明|自己)?说|你自己(?:刚才)?说|你不是说|你刚说|你说的)",
)
# 末句须收完整（24 字/句限制下尤忌写到一半）
RE_C_LINE_END_OK = re.compile(
    r"(?:[。！？…]|哼|行吧|随便|好吧|算了|认了|你赢|我先|你先|算了算)",
)
# 赛规漂移：换比法/重开的句（"数到三""重来""重新""换一种"等字面词）。
# 同一篇累计 ≥3 且全程无宣判句 → 判定规则被反复单方面推翻（无规则漂移），
# 与「换赛规须当场点破旧局」契约冲突（2026-08-07 专家定夺 3，见稿B 76分）。
# 注意：**不含「不算」**——C 稿「碰到手不算/后放上去不算/喊开始才动不算」
# 是质疑动作有效性，不是换比法（稿A 85/稿C 88 均含 3 次「不算」却非漂移）。
# 合法平局重赛豁免：稿中含「明明说/妈妈裁定/作废」等宣判句则放行（稿A 型）。
_RE_RULE_SWITCH = re.compile(r"重来|重新比|数到三|换一种|重新|再来")
_RE_RULE_VERDICT = re.compile(r"明明说|作废|重赛|妈妈|大人|宣判|点破|这次.*算|重来.*说好")
# 妈妈裁定被无视：妈妈已出场裁定赛规，末段须引用妈妈原规或让妈妈判决收束
# （2026-08-07 专家审 C 橡皮 92：L6 妈妈裁定后正文又吵 17 句，末段双方各说「我先」僵局）
_RE_MOM_RULING_REF = re.compile(
    r"妈妈(?:刚说|刚才说|说的|说的话|定的|定了|的话)|"
    r"妈(?:说|刚说|说的|定的)|按妈妈|听妈妈的|妈妈说的",
)


def _rule_drift_error(lines: list[str]) -> str | None:
    """规则漂移：切换句 ≥3 且无宣判句 → 硬卡（整稿重抽）。"""
    switches = sum(1 for ln in lines if _RE_RULE_SWITCH.search(ln))
    verdicts = sum(1 for ln in lines if _RE_RULE_VERDICT.search(ln))
    if switches >= 3 and verdicts == 0:
        return (
            "C类赛规漂移：全文换比法/重开 ≥3 次（数到三/不算/重来）且无人宣判旧局，"
            "规则被反复单方面推翻；只许一次平局重赛，换规须当场点破旧局"
        )
    return None


def _mom_ruling_ignored_error(
    speakers: list[str],
    lines: list[str],
) -> str | None:
    """妈妈裁定被无视：妈妈出场后，末 3 句须引用妈妈原规或由妈妈本人判决。

    稿B 型错误（专家审 C 橡皮 92）：妈妈 L6 裁定「谁先碰到谁用」后正文又吵
    17 句，末段灿灿「我先碰」/昭昭「我先碰」僵局无人判定。
    末 3 句含妈妈 speaker（妈妈结尾判决）或含「妈妈说/刚说」引用都放行。
    """
    if "妈妈" not in speakers:
        return None
    if "妈妈" in speakers[-3:]:
        return None
    tail3 = "".join(lines[-3:])
    if _RE_MOM_RULING_REF.search(tail3):
        return None
    return (
        "C类：妈妈已出场裁定赛规，末段须引用妈妈原规作决胜证据"
        "（妈妈说/刚说…）或让妈妈本人判决收束，禁止双方末段各说「我先」僵局无人判定"
    )


def _line_incomplete(line: str) -> bool:
    s = line.strip()
    if not s:
        return True
    if s[-1] in "'\"‘’「」":
        return True
    if s.count("'") % 2 == 1 or s.count('"') % 2 == 1:
        return True
    if s.count("「") != s.count("」"):
        return True
    if RE_C_LINE_END_OK.search(s[-4:]):
        return False
    if RE_SOFT_LAST.search(s) or RE_SURRENDER.search(s[-8:]):
        return False
    if s[-1] in "呀嘛啊呢吧了哼":
        return False
    return not bool(re.search(r"[。！？…]$", s))


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


def _closing_ok(tail4: str, tail3: str) -> bool:
    if RE_BOOMERANG_RULE.search(tail4) or RE_BOOMERANG_RULE.search(tail3):
        return True
    if RE_REVELATION_PROP.search(tail4) and (
        RE_TWIST_SEGUE.search(tail3) or RE_BOOMERANG_RULE.search(tail4)
    ):
        return True
    return False


def append_c_body_errors(story: dict, errors: list[str]) -> None:
    punch = str(story.get("punchline_explain") or "")
    if parse_story_type_code(punchline=punch) != "C":
        return

    lines, speakers = _dialogue_lines(story)
    n = len(lines)
    if n < 8:
        errors.append("C类正文过短，不足以完成公平执念收束（至少约 8 句对白）")
        return

    tail4 = "".join(lines[-4:])
    tail3 = "".join(lines[-3:])
    last = lines[-1]
    last_sp = speakers[-1] if speakers else ""

    if last_sp == "妈妈":
        errors.append("C类末句须姐弟一方嘴硬收场，禁止妈妈收束")
        return

    if RE_A_WHERE_DIFF.search(tail4) and (
        "那不一样" in tail4 or RE_A_CITE_CLOSE.search(tail4)
    ):
        errors.append(
            "C类收束勿写成 A 式末四拍（引话+那不一样+哪里不一样）；"
            "应走回旋镖或实物反转",
        )
        return

    for ln in lines[-3:-1]:
        if _line_incomplete(ln):
            errors.append(
                "C类收束对白须写完整（每句≤24字且以。！？或哼/行吧等收束，"
                "禁止停在引号或未说完）",
            )
            return

    if not _closing_ok(tail4, tail3):
        errors.append(
            "C类末段须有回旋镖（用对方刚立的规则反问）"
            "或实物真相反转收束",
        )
        return

    if _line_incomplete(last) and not (
        RE_SOFT_LAST.search(last) or RE_SURRENDER.search(last)
    ):
        errors.append(
            "C类末句须写完整或嘴硬软收（哼/行吧/给你/算了等）",
        )
        return

    if not (
        RE_SOFT_LAST.search(last)
        or RE_SURRENDER.search(last)
    ):
        errors.append(
            "C类末句须被戳穿方嘴硬软收（哼/行吧/给你/算了等），"
            "禁止赢家总结或继续立规矩",
        )
        return

    if len(speakers) >= 2 and speakers[-1] == speakers[-2]:
        errors.append("C类收束末两句须换人，禁止同人连说")
        return

    drift = _rule_drift_error(lines)
    if drift:
        errors.append(drift)

    mom_ignored = _mom_ruling_ignored_error(speakers, lines)
    if mom_ignored:
        errors.append(mom_ignored)