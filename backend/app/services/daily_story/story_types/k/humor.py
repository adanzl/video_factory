"""K 类好笑维：按 k_close_mode 分支。"""

from __future__ import annotations

import re

from app.services.daily_story.story_types.k.close_mode import (
    K_A_PARENT_FAIL_STALEMATE,
    K_B_CHILD_SELF_RESOLVE,
    K_UNKNOWN,
    k_close_mode_from_story,
)
from app.services.daily_story.story_types.k.dialogue_quality import (
    collect_k_dialogue_suspicions,
)
from app.services.daily_story.story_types.k.validate import (
    RE_FIGHT,
    RE_H_RECONCILE,
    RE_PARENT_FAIL,
    RE_STALEMATE,
)

RE_BANTER = re.compile(r"哼|滚|讨厌|谁怕|别理|越劝越|看戏|管不着")


def collect_k_humor_issues(
    lines: list[str],
    speakers: list[str] | None = None,
    *,
    story: dict | None = None,
) -> list[str]:
    spk = speakers or []
    issues: list[str] = []
    if len(lines) < 8:
        return issues
    mode = (
        k_close_mode_from_story(story)
        if isinstance(story, dict)
        else K_UNKNOWN
    )
    body = "".join(lines)
    tail4 = "".join(lines[-4:])
    if not RE_FIGHT.search(body):
        issues.append("K缺互骂升级")
    if mode == K_A_PARENT_FAIL_STALEMATE:
        if not RE_PARENT_FAIL.search(body):
            issues.append("K缺大人劝失败")
        if not RE_STALEMATE.search(tail4):
            issues.append("K末段缺僵持不和好")
    elif mode == K_B_CHILD_SELF_RESOLVE:
        from app.services.daily_story.story_types.k.close_mode import (
            RE_KB_PARENT_PASSIVE,
        )
        from app.services.daily_story.story_types.k.resolve_check import (
            kid_self_resolve_in_tail,
        )

        parent_blob = "".join(
            ln
            for sp, ln in zip(spk, lines, strict=False)
            if sp in ("妈妈", "爸爸")
        )
        if parent_blob and not RE_KB_PARENT_PASSIVE.search(parent_blob):
            issues.append("K_B缺家长挡回/旁观")
        if not kid_self_resolve_in_tail(spk, lines):
            issues.append("K_B末段缺自行恢复互动")
    issues.extend(collect_k_dialogue_suspicions(lines, spk))
    return issues


def score_funniness_tail(
    lines: list[str],
    speakers: list[str] | None = None,
    *,
    story: dict | None = None,
) -> tuple[int, list[str]]:
    """K 好笑维：K-A 劝不动僵持；K-B 反差自行和好。"""
    spk = speakers or []
    if len(lines) < 8:
        return 0, []
    mode = (
        k_close_mode_from_story(story)
        if isinstance(story, dict)
        else K_UNKNOWN
    )
    pts = 0
    pros: list[str] = []
    body = "".join(lines)
    tail = "".join(lines[-5:])
    tail5_speakers = spk[-5:] if len(spk) >= 5 else spk
    tail5_lines = lines[-5:]
    parent_tail = "".join(
        ln
        for sp, ln in zip(tail5_speakers, tail5_lines, strict=False)
        if sp in ("妈妈", "爸爸")
    )

    if mode == K_A_PARENT_FAIL_STALEMATE:
        if RE_PARENT_FAIL.search(body) and RE_FIGHT.search(body):
            pts += 4
            pros.append("大人劝失败反差")
        if "越劝越" in body:
            pts += 2
            pros.append("越劝越凶")
        if RE_STALEMATE.search(tail):
            pts += 2
            pros.append("僵持收场")
    elif mode == K_B_CHILD_SELF_RESOLVE:
        from app.services.daily_story.story_types.k.close_mode import (
            RE_KB_PARENT_PASSIVE,
        )
        from app.services.daily_story.story_types.k.resolve_check import (
            kid_self_resolve_in_tail,
        )

        if RE_KB_PARENT_PASSIVE.search(body):
            pts += 3
            pros.append("家长旁观挡回")
        if kid_self_resolve_in_tail(spk, lines):
            pts += 5
            pros.append("孩子自行恢复互动")
        if RE_FIGHT.search(body) and kid_self_resolve_in_tail(spk, lines):
            pts += 2
            pros.append("打后反差转场")

    banter_hits = len(RE_BANTER.findall(body))
    if banter_hits >= 2:
        pts += 2
        pros.append("互骂有梗")
    if RE_H_RECONCILE.search(parent_tail) and mode == K_B_CHILD_SELF_RESOLVE:
        pts = max(0, pts - 4)
        pros.append("K_B勿H仪式和好")

    return min(pts, 10), pros
