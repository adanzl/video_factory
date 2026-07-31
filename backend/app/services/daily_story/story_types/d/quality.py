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
RE_LITERAL = re.compile(
    r"照做|按你说的|你不是说|字面|打开|碰了|动了|"
    r"你说[^，。！？]{1,8}我就|我按你|你叫我|你要我|我照你",
)
RE_MESS = re.compile(
    r"掉了|滑落|滑掉|洒|弄乱|乱了|乱成|全乱|坏了|打不开|饿着|够不着|倒了|全掉|弄翻|"
    r"解不开|勒|死结|死疙瘩|大马趴|溢|变形|"
    r"[削剪切磨啃抠]没|只剩|就剩|快没了|小一圈|露出来|[削切剪磨啃]成",
)
# 与 humor.RE_FIX 同源，避免「我来解」一类破规漏认
RE_FIX = d_humor.RE_FIX


def score_scene_beat(
    lines: list[str],
    *,
    text_has_hammer_beat,
) -> tuple[int, list[str]]:
    """D 的一锤优先认「歪读可拍画面」，其次才是倒/洒。"""
    _ = text_has_hammer_beat
    text = "".join(lines)
    if d_humor.RE_TWIST_VISUAL.search(text) and RE_MESS.search(text):
        return 5, ["有字面歪读一锤"]
    if d_humor.RE_TWIST_VISUAL.search(text):
        return 4, ["有字面歪读场面"]
    if RE_MESS.search(text):
        return 2, ["有后果场面"]
    return 0, []


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
    # 后果/字面可在全文，破规+回旋镖看后段
    full = "".join(lines)
    late = "".join(lines[max(0, n - 8) :])
    bonus = 0
    details: list[str] = []

    if RE_MESS.search(full) and RE_LITERAL.search(full):
        bonus += 8
        details.append("字面后果落地")

    if RE_FIX.search(late) and RE_BOOMERANG_RULE.search(late):
        bonus += 10
        details.append("叮嘱方破规回旋镖")

    if RE_BOOMERANG_RULE.search(tail3) and RE_RULE.search(prev2 + full[:80]):
        bonus += 6
        if not details:
            details.append("字面回旋镖收束")

    if RE_SOFT_LAST.search(last) and RE_BOOMERANG_RULE.search(prev2):
        bonus += 4
        details.append("末句叮嘱方破功")
    elif RE_SOFT_LAST.search(last):
        bonus += 2
        details.append("末句叮嘱方破功")
    # 哼不在末句 = 收束没落地，不加分

    if RE_SURRENDER.search(tail3) and not details:
        bonus -= 3

    return bonus, details


def _d_revision_hint(issue: str) -> str | None:
    from app.services.daily_story.story_types.d.humor import humor_revision_hint
    from app.services.daily_story.story_types.d.opening import opening_revision_hint

    return humor_revision_hint(issue) or opening_revision_hint(issue)


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
    score_scene_beat=score_scene_beat,
    humor_issue_caps=d_humor.HUMOR_ISSUE_CAPS,
    humor_revision_hint=_d_revision_hint,
    closing_quote_haystack=d_humor.closing_quote_haystack,
    stop_on_ungrounded_quote=True,
)
