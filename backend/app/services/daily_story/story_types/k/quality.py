"""K 类观感 profile（家长看戏，k_close_mode 分支）。"""

from __future__ import annotations

from app.services.daily_story.story_types.k import humor as k_humor
from app.services.daily_story.story_types.k import opening as k_opening
from app.services.daily_story.story_types.k.close_mode import (
    K_A_PARENT_FAIL_STALEMATE,
    K_B_CHILD_SELF_RESOLVE,
    K_UNKNOWN,
    k_close_mode_from_story,
)
from app.services.daily_story.story_types.k.close_mode import (
    RE_H_RITUAL,
    RE_KB_PARENT_PASSIVE,
)
from app.services.daily_story.story_types.k.resolve_check import (
    kid_self_resolve_in_tail,
)
from app.services.daily_story.story_types.k.validate import (
    RE_A_BACKFIRE,
    RE_FIGHT,
    RE_H_RECONCILE,
    RE_PARENT_FAIL,
    RE_STALEMATE,
)
from app.services.daily_story.story_types.quality import (
    SHARED_PUNCH_SOFT,
    TypeQualityProfile,
)


def score_punchline(
    lines: list[str],
    speakers: list[str],
    prev2: str,
    last: str,
    *,
    story: dict | None = None,
) -> tuple[int, list[str]]:
    del prev2, last
    n = len(lines)
    if n < 4:
        return 0, []

    mode = (
        k_close_mode_from_story(story)
        if isinstance(story, dict)
        else K_UNKNOWN
    )
    body = "".join(lines)
    tail6 = "".join(lines[-6:])
    tail6_speakers = speakers[-6:] if len(speakers) >= 6 else speakers
    tail6_lines = lines[-6:]
    parent_tail6 = "".join(
        ln
        for sp, ln in zip(tail6_speakers, tail6_lines, strict=False)
        if sp in ("妈妈", "爸爸")
    )
    if RE_A_BACKFIRE.search(tail6):
        return 0, ["K收束含A式反噬标记"]
    if RE_H_RECONCILE.search(tail6) and mode == K_A_PARENT_FAIL_STALEMATE:
        return 0, ["K收束含H式和好"]
    if mode == K_B_CHILD_SELF_RESOLVE and RE_H_RITUAL.search(parent_tail6):
        return 0, ["K_B收束含H式定责仪式"]

    has_fight = bool(RE_FIGHT.search(body))
    if not has_fight:
        return 0, []

    bonus = 0
    details: list[str] = ["互骂升级落位"]
    if mode == K_A_PARENT_FAIL_STALEMATE:
        has_fail = bool(RE_PARENT_FAIL.search(body))
        has_stale = bool(RE_STALEMATE.search(tail6))
        if has_fail:
            details.append("大人劝失败")
        if has_stale:
            bonus = 8
            details.append("僵持不和好")
        else:
            bonus = 5
            details.append("缺僵持收场")
    elif mode == K_B_CHILD_SELF_RESOLVE:
        parent_blob = "".join(
            ln
            for sp, ln in zip(speakers, lines, strict=False)
            if sp in ("妈妈", "爸爸")
        )
        if parent_blob and RE_KB_PARENT_PASSIVE.search(parent_blob):
            bonus += 4
            details.append("家长挡回旁观")
        tail6_sp = speakers[-6:] if len(speakers) >= 6 else speakers
        if kid_self_resolve_in_tail(tail6_sp, tail6_lines):
            bonus += 8
            details.append("孩子自行恢复互动")
        else:
            bonus = max(0, bonus - 6)
            details.append("缺自行恢复互动")
        if RE_H_RITUAL.search(parent_tail6):
            bonus = 0
            details.append("K_B含H仪式污染")
    else:
        bonus = 3
        details.append("K收场模式未定")

    return bonus, details


def humor_revision_hint(issue_text: str) -> str | None:
    if "K_B" in issue_text or "自行恢复" in issue_text:
        if "怂恿" in issue_text or "接着打" in issue_text:
            return (
                "【K_B挡回】家长只挡回/吃饭旁观，勿「接着打/你俩打」；"
                "孩子自行恢复；末句自言自语点题。"
            )
        if "破碎" in issue_text or "尾词" in issue_text:
            return "【K_B口语】删…了呢…碎尾，收成完整可配音短句。"
        if "争执" in issue_text or "不服" in issue_text:
            return (
                "【K_B篇幅】互打宜短；每句须有新信息（道具/动作）；"
                "勿连喊不服/试试看；保留一轮冰棍/邀约收束。"
            )
        return (
            "【K_B收束】挡回旁观；孩子自行恢复互动；"
            "家长末句自言自语点题；勿解说/勿喊爸爸；勿 H 仪式。"
        )
    if "和好" in issue_text or "收束" in issue_text:
        return "【K收束】末段僵持不和好；勿拉手/不打了/和好。"
    if "劝" in issue_text or "推进" in issue_text:
        return "【K推进】补大人劝失败（叹气/管不了），越劝越凶更佳。"
    return None


QUALITY_PROFILE = TypeQualityProfile(
    code="K",
    score_punchline=score_punchline,
    closing_pro_markers=("僵持", "劝失败", "不和好", "看戏", "越劝越", "不理"),
    summary_highlight_tokens=(
        "互骂",
        "升级",
        "劝失败",
        "僵持",
        "看戏",
        "不和好",
        "自行恢复",
        "挡回",
    ),
    punch_before_soft_markers=SHARED_PUNCH_SOFT
    + (
        "不和好",
        "别理",
        "越劝越",
        "管不了",
    ),
    mom_lines_penalty_at=5,
    penalize_wait_mom_end=False,
    penalize_split_end=False,
    penalize_stubborn_end=False,
    penalize_mom_judge=False,
    collect_humor_issues=k_humor.collect_k_humor_issues,
    score_opening_quality=k_opening.score_opening_quality,
    score_funniness_tail=k_humor.score_funniness_tail,
    humor_revision_hint=humor_revision_hint,
)
