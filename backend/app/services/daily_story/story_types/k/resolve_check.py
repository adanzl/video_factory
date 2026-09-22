"""K-B 正文：孩子自行恢复互动（仅看对白 speaker）。"""

from __future__ import annotations

from app.services.daily_story.story_types.k.close_mode import (
    KID_SPEAKERS,
    RE_KB_CHILD_ACCEPT,
    RE_KB_CHILD_REJECT,
    RE_KB_CHILD_RESOLVE,
)


def kid_self_resolve_in_tail(
    speakers: list[str],
    lines: list[str],
    *,
    tail_n: int = 6,
) -> bool:
    """末段须由孩子发起/接住恢复互动，家长邀约不算。"""
    if len(speakers) != len(lines):
        n = min(len(speakers), len(lines))
        speakers = speakers[:n]
        lines = lines[:n]
    tail = [
        (str(sp or "").strip(), str(ln or "").strip())
        for sp, ln in zip(speakers, lines, strict=False)
    ][-tail_n:]
    kid_pairs = [(sp, ln) for sp, ln in tail if sp in KID_SPEAKERS]
    if not kid_pairs:
        return False
    invite_idxs = [
        i
        for i, (_sp, ln) in enumerate(kid_pairs)
        if RE_KB_CHILD_RESOLVE.search(ln)
    ]
    if not invite_idxs:
        return False
    last_invite = invite_idxs[-1]
    after_invite = kid_pairs[last_invite + 1 :]
    if not after_invite:
        return False
    for _sp, ln in after_invite:
        if RE_KB_CHILD_REJECT.search(ln):
            return False
        if RE_KB_CHILD_ACCEPT.search(ln):
            return True
    return False
