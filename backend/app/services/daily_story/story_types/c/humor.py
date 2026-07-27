"""C 类好笑维硬伤、场面加分与修订 hint。"""

from __future__ import annotations

import re
from collections.abc import Callable

from app.services.daily_story.story_types.quality import (
    RE_BOOMERANG_RULE,
    RE_REVELATION_PROP,
    RE_TWIST_SEGUE,
)

RE_LITERAL_RULE_PLAY = re.compile(
    r"多喝|再多喝|喝水|拿.{0,8}杯|"
    r"让自己|更急|加赛|"
    r"作弊|比赛|还没开始|"
    r"(?:喝|吃|忍|憋).{0,16}(?:急|赢|比赛|更)|"
    r"(?:急|赢|比赛).{0,16}(?:喝|吃|忍|憋)|"
    r"(?:你叠|我叠|叠好).{0,12}(?:给|收|拿|放)|"
    r"(?:按|照).{0,6}(?:规矩|赛规|你说的|你刚说)|"
    r"谁弄乱|弄乱谁收拾|比你更|更久",
)
_OWNERSHIP_CHATTER = re.compile(
    r"都是我的|你的没|各管各|叠了没|不公平|凭什么.*我的|"
    r"有没有我的一件|你没叠",
)
_RULE_LINE = re.compile(r"谁碰|碰了.*负责|弄乱.*负责|谁弄乱")
_FILMABLE_TWIST = re.compile(
    r"歪了|乱了|倒了|洒了|摔了|碰倒|多拿|偷拿|藏了|"
    r"东倒西歪|翻乱|弄乱|乱放|叠好|给你这件|递给你|给你。",
)

HUMOR_ISSUE_CAPS: tuple[tuple[str, int], ...] = (
    ("归属口水战", 5),
    ("偏A式那不一样", 6),
    ("缺可拍争法", 7),
)


def ground_closing_quote(fragment: str, haystack: str) -> bool:
    frag = re.sub(r"[的话呢呀嘛吧啊…\s「」『』\"'‘’：:，,]", "", fragment)
    hay = re.sub(r"[的话呢呀嘛吧啊…\s「」『』\"'‘’：:，,]", "", haystack)
    if len(frag) < 3:
        return True
    if "更急" in frag and "更急" in hay:
        return True
    if "先选" in frag and "先选" in hay:
        return True
    if "公平" in frag and "公平" in hay:
        return True
    if "先到" in frag and ("先到" in hay or "先拿" in hay):
        return True
    return False


def collect_humor_issues(
    lines: list[str],
    speakers: list[str] | None,
) -> list[str]:
    _ = speakers
    cons: list[str] = []
    tail4 = lines[-4:] if len(lines) >= 4 else lines
    tail_text = "".join(tail4)
    late6 = "".join(lines[-6:]) if len(lines) >= 6 else tail_text

    has_boomerang = bool(RE_BOOMERANG_RULE.search(tail_text))
    has_literal = bool(RE_LITERAL_RULE_PLAY.search(late6))
    has_prop = bool(RE_REVELATION_PROP.search(tail_text))

    if "那不一样" in tail_text and not has_literal:
        cons.append("C收束偏A式那不一样")

    pre_close = lines[: max(0, len(lines) - 8)]
    ownership_chatter = sum(1 for ln in pre_close if _OWNERSHIP_CHATTER.search(ln))
    rule_i = next(
        (i for i, ln in enumerate(lines) if _RULE_LINE.search(ln)),
        None,
    )
    chatter_after = 0
    if rule_i is not None:
        tail_start = max(0, len(lines) - 8)
        for ln in lines[rule_i + 1 : tail_start]:
            if _OWNERSHIP_CHATTER.search(ln):
                chatter_after += 1
    if ownership_chatter >= 4 and (rule_i is None or chatter_after >= 3):
        cons.append("C中段归属口水战")

    if has_boomerang and not has_literal and not has_prop:
        filmable = bool(_FILMABLE_TWIST.search(late6))
        if not filmable and not RE_LITERAL_RULE_PLAY.search(late6):
            cons.append("C收束缺可拍争法")

    return cons


def score_scene_beat(
    lines: list[str],
    *,
    text_has_hammer_beat: Callable[[str], bool],
) -> tuple[int, list[str]]:
    body = lines[:-4] if len(lines) > 4 else lines[:-1]
    mid_text = "".join(body[: max(1, len(body) * 2 // 3)])
    full_text = "".join(lines)
    late6 = "".join(lines[-6:]) if len(lines) >= 6 else full_text

    if text_has_hammer_beat(mid_text):
        return 0, []
    if RE_LITERAL_RULE_PLAY.search(mid_text):
        return 4, ["字面加赛场面"]
    if text_has_hammer_beat(full_text):
        return 0, []
    if RE_LITERAL_RULE_PLAY.search(late6):
        return 3, ["字面加赛场面"]
    return 0, []


def score_funniness_tail(lines: list[str]) -> tuple[int, list[str]]:
    tail4 = lines[-4:] if len(lines) >= 4 else lines
    late4_text = "".join(tail4)
    late6 = "".join(lines[-6:]) if len(lines) >= 6 else late4_text
    points = 0
    pros: list[str] = []
    if RE_BOOMERANG_RULE.search(late4_text):
        if RE_TWIST_SEGUE.search(late6):
            points += 4
            pros.append("字面回旋好笑")
        elif RE_LITERAL_RULE_PLAY.search(late6):
            points += 5
            pros.append("字面加赛好笑")
    return points, pros


def humor_revision_hint(issue: str) -> str | None:
    if "归属口水战" in issue:
        return (
            f"【好笑·C】{issue}。"
            "删掉「归谁/你没叠」多轮；前 8 句内立一条可执行赛规"
            "（如谁碰谁负责、谁先拿谁先选）。"
            "中段用量化或动作升级，勿空吵所有权。"
        )
    if "缺可拍争法" in issue:
        return (
            f"【好笑·C】{issue}。"
            "收束前加一件能拍的动作（按赛规字面加赛、"
            "或实物状态变化），再回旋镖扣原话；"
            "勿只靠「指一下/不算」口头诡辩。"
        )
    if "偏A式那不一样" in issue:
        return (
            f"【好笑·C】{issue}。"
            "末段用对方赛规反问，少用「那不一样」甩脱；"
            "破功方嘴硬收场即可。"
        )
    if any(k in issue for k in ("无出处", "模板", "拖沓", "末四拍", "好笑")):
        return (
            f"【好笑·C】{issue}。"
            "中段用一件具体争法升级；"
            "末段用对方规则回旋镖反问，末句嘴硬收场。"
        )
    from app.services.daily_story.story_types.c.facts import fact_revision_hint
    from app.services.daily_story.story_types.c.opening import opening_revision_hint

    return fact_revision_hint(issue) or opening_revision_hint(issue)
