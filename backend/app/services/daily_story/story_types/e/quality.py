"""E 类观感：末段 scorer 与 profile。"""

from __future__ import annotations

import re

from app.services.daily_story.story_types.e import humor as e_humor
from app.services.daily_story.story_types.e import opening as e_opening
from app.services.daily_story.story_types.e import facts as e_facts
from app.services.daily_story.story_types.quality import (
    SHARED_PUNCH_SOFT,
    TypeQualityProfile,
)

RE_MOM_TALK = e_humor.RE_MOM_RULE
RE_KID_ASK = e_humor.RE_KID_ASK
RE_MOM_WAFFLE = e_humor.RE_MOM_WAFFLE
RE_LOOP = e_humor.RE_LOOP
RE_MOM_SOFT = e_humor.RE_MOM_SOFT
RE_CATCH = re.compile(
    r"嘴角|勺子|勺上|腮帮|手机|还在刷|尝了|咽|敷衍|撒谎|说瞎话|三大勺|"
    r"菜叶|油渍|油花|试吃|试菜|"
    r"空(?:的)?锅|锅是空|饭锅|碗还干|碗是干|外卖盒|泡面桶|肚子(?:还)?咕咕|"
    r"拨到|拨开|碗边|青菜",
)
RE_KID_SELF_APPLY = e_humor.RE_KID_SELF_APPLY
_RE_PICKY_RULE_TOKEN = re.compile(r"(?:不准|不许|不能|别)挑食")


def ground_closing_quote(fragment: str, haystack: str) -> bool:
    """挑食规矩词不许/不能视为同出；「不算数」类出尔反尔质问不算假引话。"""
    frag = (fragment or "").strip()
    hay = haystack or ""
    if _RE_PICKY_RULE_TOKEN.search(frag) and _RE_PICKY_RULE_TOKEN.search(hay):
        return True
    # 「你自己说的不算数啦」= 你出尔反尔，不是声称妈妈说过「不算数」。
    if "不算数" in frag and "不算数" not in hay:
        return True
    return False


def score_scene_beat(
    lines: list[str],
    *,
    text_has_hammer_beat,
) -> tuple[int, list[str]]:
    """E 的一锤=抓住妈妈现行（嘴角/勺子/手机还亮）。"""
    _ = text_has_hammer_beat
    text = "".join(lines)
    if RE_CATCH.search(text):
        return 5, ["有一锤场面"]
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

    full = "".join(lines)
    late = "".join(lines[max(0, n - 8) :])
    tail3 = "".join(lines[-3:])
    bonus = 0
    details: list[str] = []

    if RE_MOM_TALK.search(full) and RE_MOM_WAFFLE.search(full) and RE_LOOP.search(late):
        bonus += 10
        details.append("追问闭环")

    if RE_LOOP.search(tail3) and RE_MOM_WAFFLE.search(prev2 + late):
        bonus += 4
        if "闭环" not in "".join(details):
            details.append("追问闭环")

    if speakers and speakers[-1] == "妈妈" and RE_MOM_SOFT.search(last):
        bonus += 8
        details.append("妈妈破功收束")

    if RE_CATCH.search(full) and RE_LOOP.search(late):
        bonus += 5
        details.append("妈妈逻辑露馅")

    if RE_KID_ASK.search(full) and RE_MOM_SOFT.search(last):
        bonus += 3
        if "破功" not in "".join(details):
            details.append("妈妈破功收束")

    if RE_KID_SELF_APPLY.search(late) and RE_MOM_SOFT.search(last):
        bonus += 5
        details.append("自套逻辑反杀")

    return bonus, details


def _e_revision_hint(issue: str) -> str | None:
    from app.services.daily_story.story_types.e.humor import humor_revision_hint
    from app.services.daily_story.story_types.e.opening import opening_revision_hint

    return humor_revision_hint(issue) or opening_revision_hint(issue)


QUALITY_PROFILE = TypeQualityProfile(
    code="E",
    score_punchline=score_punchline,
    closing_pro_markers=("破功", "闭环", "露馅", "妈妈"),
    summary_highlight_tokens=(
        "推进",
        "破功",
        "闭环",
        "妈妈",
    ),
    punch_before_soft_markers=SHARED_PUNCH_SOFT
    + (
        "你自己说",
        "自己说",
        "那你也是",
        "你也",
        "你刚才",
    ),
    mom_lines_penalty_at=18,
    penalize_wait_mom_end=False,
    penalize_split_end=True,
    penalize_stubborn_end=False,
    penalize_mom_judge=True,
    collect_humor_issues=e_humor.collect_humor_issues,
    collect_fact_issues=e_facts.collect_fact_issues,
    score_opening_quality=e_opening.score_opening_quality,
    score_scene_beat=score_scene_beat,
    score_funniness_tail=e_humor.score_funniness_tail,
    ground_closing_quote=ground_closing_quote,
    humor_issue_caps=e_humor.HUMOR_ISSUE_CAPS,
    humor_revision_hint=_e_revision_hint,
)
