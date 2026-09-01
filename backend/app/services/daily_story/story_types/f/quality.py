"""F 类观感 profile（互呛加码）。"""

from __future__ import annotations

import re

from app.services.daily_story.story_types.f import humor as f_humor
from app.services.daily_story.story_types.quality import (
    SHARED_PUNCH_SOFT,
    TypeQualityProfile,
)

RE_EXTERNAL = f_humor.RE_EXTERNAL
RE_THREAT = f_humor.RE_THREAT
RE_ESCALATE = f_humor.RE_ESCALATE
RE_STALE = f_humor.RE_STALE
RE_B_ALLIANCE_TAIL = re.compile(
    r"一伙|一致对外|甩锅|露馅|瞒妈|别告诉妈|分工|你望风",
)
RE_G_SOFT = re.compile(r"擦药|撑腰|说好了|心疼|护姐|护短|给你擦")
RE_A_BACKFIRE = re.compile(r"那不一样|都是听|破功|哪里不一样")


def score_scene_beat(
    lines: list[str],
    *,
    text_has_hammer_beat,
) -> tuple[int, list[str]]:
    del text_has_hammer_beat
    body = "".join(lines)
    mid = "".join(lines[: max(1, len(lines) * 2 // 3)])
    reasons: list[str] = []
    score = 0
    hits = len(RE_THREAT.findall(mid))
    if hits >= 2:
        score += 3
        reasons.append("互呛威胁")
    if RE_ESCALATE.search(mid):
        score += 4
        reasons.append("互呛加码")
    if RE_EXTERNAL.search(body):
        score += 3
        reasons.append("外部打断反差")
    return score, reasons


def score_punchline(
    lines: list[str],
    speakers: list[str],
    prev2: str,
    last: str,
) -> tuple[int, list[str]]:
    del speakers, prev2, last
    close = f_humor.close_tail_text(lines)
    if RE_B_ALLIANCE_TAIL.search(close) and not RE_EXTERNAL.search(close):
        return 0, ["F收束似B结盟"]
    if RE_G_SOFT.search(close):
        return 0, ["F收束含G暖收"]
    if RE_A_BACKFIRE.search(close):
        return 0, ["F收束含A反噬"]
    if f_humor.has_close_markers(lines):
        return 5, ["僵持或外部打断收束"]
    return 0, []


QUALITY_PROFILE = TypeQualityProfile(
    code="F",
    score_punchline=score_punchline,
    closing_pro_markers=(
        "僵持",
        "露怯",
        "外部打断",
        "偷拍",
        "尴尬",
        "互呛",
        "加码",
    ),
    summary_highlight_tokens=(
        "推进",
        "互呛",
        "加码",
        "僵持",
        "外部打断",
        "尴尬",
    ),
    punch_before_soft_markers=SHARED_PUNCH_SOFT
    + (
        "再说",
        "试试",
        "偷拍",
        "尴尬",
        "茄子",
        "闭嘴",
    ),
    penalize_stubborn_end=False,
    penalize_wait_mom_end=False,
    penalize_mom_judge=False,
    collect_humor_issues=f_humor.collect_f_humor_issues,
    score_scene_beat=score_scene_beat,  # type: ignore[union-attr]
    score_funniness_tail=f_humor.score_funniness_tail,
)
