"""D 类观感：末段 scorer 与 profile。"""

from __future__ import annotations

import re

from app.services.daily_story.story_types.d import humor as d_humor
from app.services.daily_story.story_types.d import opening as d_opening
from app.services.daily_story.story_types.quality import (
    RE_BOOMERANG_RULE,
    RE_SOFT_LAST,
    RE_SURRENDER,
    SHARED_PUNCH_SOFT,
    TypeQualityProfile,
)

RE_RULE = re.compile(r"不许|别碰|规矩|叮嘱|说了|不能")
RE_LITERAL = re.compile(r"照做|按你说的|你不是说|字面|打开|碰了|动了")
RE_MESS = re.compile(r"掉了|滑|洒|乱|坏|打不开|饿着|够不着")
RE_FIX = re.compile(r"我来|我捡|我弄|只好|只能|没办法|我得")


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

    if RE_MESS.search(tail4) and RE_LITERAL.search(tail4):
        bonus += 8
        details.append("字面后果落地")

    if RE_FIX.search(tail3) and RE_BOOMERANG_RULE.search(tail3):
        bonus += 10
        details.append("叮嘱方破规回旋镖")

    if RE_BOOMERANG_RULE.search(tail3) and RE_RULE.search(prev2):
        bonus += 6
        if not details:
            details.append("字面回旋镖收束")

    if RE_SOFT_LAST.search(last) and RE_BOOMERANG_RULE.search(prev2):
        bonus += 4
        details.append("末句叮嘱方破功")

    if RE_SURRENDER.search(tail3) and not details:
        bonus -= 3

    return bonus, details


QUALITY_PROFILE = TypeQualityProfile(
    code="D",
    score_punchline=score_punchline,
    closing_pro_markers=("回旋镖", "破功", "字面", "破规", "后果"),
    summary_highlight_tokens=(
        "回旋镖",
        "推进",
        "破功",
        "字面",
        "后果",
    ),
    punch_before_soft_markers=SHARED_PUNCH_SOFT
    + (
        "你自己说",
        "你刚才",
        "你现在也",
    ),
    collect_humor_issues=d_humor.collect_humor_issues,
    score_opening_quality=d_opening.score_opening_quality,
    humor_issue_caps=d_humor.HUMOR_ISSUE_CAPS,
    humor_revision_hint=d_humor.humor_revision_hint,
)
