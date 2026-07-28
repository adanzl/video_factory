"""B 类观感：末段 scorer 与 profile。"""

from __future__ import annotations

import re
from collections.abc import Callable

from app.services.daily_story.story_types.b import facts as b_facts
from app.services.daily_story.story_types.b import humor as b_humor
from app.services.daily_story.story_types.b import opening as b_opening
from app.services.daily_story.story_types.quality import (
    SHARED_PUNCH_SOFT,
    TypeQualityProfile,
)

_A_STYLE_TAIL = re.compile(r"那不一样|哪里不一样|你刚才说|你自己说")
RE_ALLY = b_humor.RE_ALLY
RE_BLAME = b_humor.RE_BLAME
RE_EXPOSED = b_humor.RE_EXPOSED
RE_PLAN_FAIL = b_humor.RE_PLAN_FAIL
RE_MOM_PUNISH = b_humor.RE_MOM_PUNISH
RE_DOOM = b_humor.RE_DOOM


def score_scene_beat(
    lines: list[str],
    *,
    text_has_hammer_beat: Callable[[str], bool],
) -> tuple[int, list[str]]:
    body = lines[:-4] if len(lines) > 4 else lines[:-1]
    mid_text = "".join(body[: max(1, len(body) * 2 // 3)])
    if text_has_hammer_beat(mid_text):
        return 0, []
    if RE_PLAN_FAIL.search(mid_text):
        return 4, ["同盟走样场面"]
    chain_run = b_humor._longest_chain_run(
        body[1:] if len(body) > 1 else body,
        b_humor.RE_CHAIN_ACTION,
    )
    if chain_run >= 3:
        return 5, ["越补越糟连锁场面"]
    if RE_BLAME.search(mid_text) and RE_ALLY.search("".join(body[: len(body) // 2])):
        return 2, ["走样后甩锅"]
    return 0, []


def score_punchline(
    lines: list[str],
    speakers: list[str],
    prev2: str,
    last: str,
) -> tuple[int, list[str]]:
    n = len(lines)
    if n < 4:
        return 0, []

    tail4 = "".join(lines[-4:])
    tail8 = "".join(lines[-8:]) if n >= 8 else "".join(lines)
    head_third = "".join(lines[: max(1, n // 3)])
    bonus = 0
    details: list[str] = []

    if RE_ALLY.search(head_third):
        bonus += 4
        details.append("前段结盟约定")

    pre_lines, punish_i = b_humor._lines_before_last_punish(lines, speakers)
    if punish_i is not None:
        tail_pre = pre_lines[-8:] if len(pre_lines) >= 8 else pre_lines
        if RE_BLAME.search("".join(tail_pre)):
            bonus += 6
            details.append("联盟自保甩锅")

    if RE_EXPOSED.search(tail4):
        bonus += 8
        details.append("联手露馅收场")

    weak_freeze = b_humor.is_weak_freeze_after_punish(lines, speakers)
    has_bloat = b_humor.analyze_post_freeze_bloat(lines, speakers)[0]
    if (
        RE_MOM_PUNISH.search(tail8)
        and not weak_freeze
        and not has_bloat
    ):
        bonus += 6
        if RE_DOOM.search(tail8):
            details.append("定格戛然而止")
        else:
            details.append("落槌定格够")
    elif RE_MOM_PUNISH.search(tail8) and weak_freeze:
        bonus -= 3
        details.append("落槌定格不足")

    if has_bloat:
        bonus -= 6
        details.append("定格后多余对白")

    if RE_ALLY.search(head_third) and RE_PLAN_FAIL.search(
        "".join(lines[n // 3 : max(n // 3, punish_i or n - 3)]),
    ):
        bonus += 4
        if "走样" not in "".join(details):
            details.append("约定走样")

    if _A_STYLE_TAIL.search(tail4) and RE_BLAME.search(tail4):
        bonus -= 4

    return bonus, details


QUALITY_PROFILE = TypeQualityProfile(
    code="B",
    score_punchline=score_punchline,
    closing_pro_markers=("露馅", "甩锅", "翻车", "破功", "走样", "落槌", "连锁", "定格"),
    summary_highlight_tokens=(
        "推进",
        "露馅",
        "甩锅",
        "翻车",
        "走样",
        "定格",
        "连锁",
        "好笑",
        "事实",
        "开场",
        "自保",
    ),
    punch_before_soft_markers=SHARED_PUNCH_SOFT
    + (
        "都怪你",
        "露馅",
        "完了",
        "是你先",
        "完蛋",
        "站好",
    ),
    collect_humor_issues=b_humor.collect_humor_issues,
    collect_fact_issues=b_facts.collect_fact_issues,
    score_opening_quality=b_opening.score_opening_quality,
    score_scene_beat=score_scene_beat,
    score_funniness_tail=b_humor.score_funniness_tail,
    humor_issue_caps=b_humor.HUMOR_ISSUE_CAPS,
    humor_revision_hint=b_humor.humor_revision_hint,
    penalize_stubborn_end=False,
)
