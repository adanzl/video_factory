"""C 类观感：末段 scorer 与 profile。"""

from __future__ import annotations

from app.services.daily_story.story_types.quality import (
    RE_BOOMERANG_RULE,
    RE_REVELATION_PROP,
    RE_SURRENDER,
    RE_TWIST_SEGUE,
    SHARED_PUNCH_SOFT,
    STRONG_END_MARKERS,
    TypeQualityProfile,
)


def score_punchline(
    lines: list[str],
    speakers: list[str],
    prev2: str,
    last: str,
) -> tuple[int, list[str]]:
    _ = prev2
    n = len(lines)
    if n < 4:
        return 0, []

    tail4 = "".join(lines[-4:])
    tail3 = "".join(lines[-3:])
    bonus = 0
    details: list[str] = []

    first_half = "".join(lines[: n // 2])
    second_half = "".join(lines[n // 2:])
    revelations = RE_REVELATION_PROP.findall(second_half)
    new_revelations = [r for r in revelations if r not in first_half]
    if new_revelations and any(m in tail4 for m in new_revelations):
        bonus += 10
        details.append("实物真相反转")

    if RE_BOOMERANG_RULE.search(tail3):
        bonus += 8
        if "实物真相反转" not in details:
            details.append("回旋镖收束")

    if RE_SURRENDER.search(tail3):
        if not RE_BOOMERANG_RULE.search(tail3) and not any(
            m in tail3 for m in STRONG_END_MARKERS
        ):
            bonus -= 3

    twist_matches = RE_TWIST_SEGUE.findall(tail3)
    if twist_matches and (
        RE_REVELATION_PROP.search(tail4) or RE_BOOMERANG_RULE.search(tail4)
    ):
        bonus += 3

    if speakers and len(speakers) >= 2:
        last_sp = speakers[-1]
        prev_sp = speakers[-2]
        if last_sp != prev_sp and RE_SURRENDER.search(last):
            bonus += 3

    return bonus, details


QUALITY_PROFILE = TypeQualityProfile(
    code="C",
    score_punchline=score_punchline,
    closing_pro_markers=("回旋镖", "反转", "破功", "实物", "困境"),
    summary_highlight_tokens=(
        "反转",
        "回旋镖",
        "推进",
        "破功",
        "实物",
    ),
    punch_before_soft_markers=SHARED_PUNCH_SOFT,
)
