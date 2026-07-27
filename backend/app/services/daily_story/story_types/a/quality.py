"""A 类观感：末段 scorer 与 profile。"""

from __future__ import annotations

import re

from app.services.daily_story.story_types.quality import (
    RE_SOFT_LAST,
    RE_SURRENDER,
    SHARED_PUNCH_SOFT,
    TypeQualityProfile,
)

RE_LOOP_CLOSE = re.compile(r"哪里不一样|都是听|到底哪|凭什么听")
RE_PRECEDENT = re.compile(r"上次|之前|你也|明明说|妈妈说过|你不是说|你自己也")
RE_ADMIT = re.compile(
    r"那不一样|你刚才说|你自己说|你也这样|我是教你|不是那个意思",
)
RE_RULE_PUSH = re.compile(r"你刚才说|你自己说|你也这样|那不一样")


def score_punchline(
    lines: list[str],
    speakers: list[str],
    prev2: str,
    last: str,
) -> tuple[int, list[str]]:
    _ = speakers
    n = len(lines)
    if n < 4:
        return 0, []

    tail4 = "".join(lines[-4:])
    tail3 = "".join(lines[-3:])
    bonus = 0
    details: list[str] = []

    first_half = "".join(lines[: n // 2])
    second_half = "".join(lines[n // 2:])
    if RE_PRECEDENT.search(second_half) and RE_PRECEDENT.search(tail4):
        if not RE_PRECEDENT.search(first_half) or RE_PRECEDENT.search(tail3):
            bonus += 6
            details.append("引先例收束")

    if RE_LOOP_CLOSE.search(tail3) or (
        RE_ADMIT.search(prev2) and RE_LOOP_CLOSE.search(last)
    ):
        bonus += 5
        if "引先例收束" not in details:
            details.append("追问闭环")

    if RE_ADMIT.search(tail3) and RE_RULE_PUSH.search(tail3):
        bonus += 4
        if not details:
            details.append("规则回旋收束")

    if RE_SOFT_LAST.search(last) and (
        RE_ADMIT.search(prev2) or RE_LOOP_CLOSE.search(prev2)
    ):
        bonus += 4
        if not any("破功" in d for d in details):
            details.append("末句权威破功")

    if RE_SURRENDER.search(tail3) and not details:
        bonus -= 3

    return bonus, details


QUALITY_PROFILE = TypeQualityProfile(
    code="A",
    score_punchline=score_punchline,
    closing_pro_markers=(
        "追问闭环",
        "引先例",
        "权威破功",
        "回旋",
        "破功",
    ),
    summary_highlight_tokens=(
        "反转",
        "回旋镖",
        "推进",
        "破功",
        "追问闭环",
        "引先例",
        "权威",
    ),
    punch_before_soft_markers=SHARED_PUNCH_SOFT
    + (
        "那不一样",
        "哪里不一样",
        "凭什么",
        "你也",
    ),
)
