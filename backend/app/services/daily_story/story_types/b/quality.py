"""B 类观感：末段 scorer 与 profile。"""

from __future__ import annotations

import re

from app.services.daily_story.story_types.quality import (
    RE_SOFT_LAST,
    SHARED_PUNCH_SOFT,
    TypeQualityProfile,
)

RE_ALLY = re.compile(r"一起|咱俩|别告诉|瞒着|约定|联手|暗号")
RE_BLAME = re.compile(r"都怪你|是你先|你答应|不是我的|你先")
RE_EXPOSED = re.compile(r"露馅|完了|糟糕|抓到了|听见了|看见了")


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

    if RE_BLAME.search(tail3):
        bonus += 6
        details.append("结盟互甩锅")

    if RE_EXPOSED.search(tail4):
        bonus += 10
        details.append("联手露馅收场")

    if RE_ALLY.search("".join(lines[: n // 2])) and RE_EXPOSED.search(tail3):
        bonus += 4
        if "露馅" not in "".join(details):
            details.append("约定翻车")

    if RE_SOFT_LAST.search(last) and RE_BLAME.search(prev2):
        bonus += 3
        details.append("末句嘴硬甩锅")

    return bonus, details


QUALITY_PROFILE = TypeQualityProfile(
    code="B",
    score_punchline=score_punchline,
    closing_pro_markers=("露馅", "甩锅", "翻车", "破功", "嘴硬"),
    summary_highlight_tokens=(
        "推进",
        "露馅",
        "甩锅",
        "翻车",
        "破功",
    ),
    punch_before_soft_markers=SHARED_PUNCH_SOFT
    + (
        "都怪你",
        "露馅",
        "完了",
    ),
)
