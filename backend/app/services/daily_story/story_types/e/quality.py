"""E 类观感：末段 scorer 与 profile。"""

from __future__ import annotations

import re

from app.services.daily_story.story_types.quality import (
    SHARED_PUNCH_SOFT,
    TypeQualityProfile,
)

RE_MOM_TALK = re.compile(r"应该|必须|规矩|听我的|我说|不行")
RE_KID_ASK = re.compile(r"为什么|凭什么|那你|你也|上次")
RE_MOM_WAFFLE = re.compile(r"不是|不一样|那是|总之|反正|不是那个")
RE_LOOP = re.compile(r"你自己说|你刚才|那你也是|你也这样")
RE_MOM_SOFT = re.compile(r"唉|行了|好吧|随便|说不通|行行行")


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
    tail3 = "".join(lines[-3:])
    bonus = 0
    details: list[str] = []

    if RE_LOOP.search(tail3) and RE_MOM_WAFFLE.search(prev2):
        bonus += 10
        details.append("追问闭环")

    if RE_KID_ASK.search(tail4) and RE_MOM_SOFT.search(last):
        bonus += 8
        details.append("妈妈破功收束")

    if speakers and speakers[-1] == "妈妈" and RE_MOM_SOFT.search(last):
        bonus += 5
        if "破功" not in "".join(details):
            details.append("末句妈妈破功")

    if RE_MOM_TALK.search(tail4) and RE_LOOP.search(tail4):
        bonus += 4
        details.append("妈妈逻辑露馅")

    return bonus, details


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
        "那你也是",
        "你也",
    ),
    mom_lines_penalty_at=8,
    penalize_wait_mom_end=False,
    penalize_split_end=True,
    penalize_stubborn_end=False,
    penalize_mom_judge=True,
)
