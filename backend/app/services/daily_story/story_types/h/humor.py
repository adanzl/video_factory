"""H 类好笑维：升级互毁、第三方调解、仪式性和好。"""

from __future__ import annotations

import re

from app.services.daily_story.story_types.h.validate import (
    RE_ESCALATE,
    RE_MOM_MEDIATE,
    RE_RECONCILE,
)

RE_CHORUS = re.compile(r"不打了|说好了|齐声")
RE_BANTER = re.compile(r"小气鬼|哼|家规|你赔|偏要|互不相让|我不原谅")
RE_WARM_DETAIL = re.compile(r"碘伏|涂药|擦药|额头|蹭破|谢谢妈妈")
RE_MOM_LAYER = re.compile(r"谁先|都错|别打")


def collect_h_humor_issues(
    lines: list[str],
    speakers: list[str] | None = None,
) -> list[str]:
    del speakers
    issues: list[str] = []
    if len(lines) < 8:
        return issues
    body = "".join(lines)
    tail4 = "".join(lines[-4:])
    mom_index = next(
        (i for i, ln in enumerate(lines) if "别打" in ln or "谁先" in ln),
        -1,
    )
    pre_mediation = (
        "".join(lines[:mom_index])
        if mom_index > 0
        else body[: len(body) // 2]
    )
    if not RE_ESCALATE.search(pre_mediation):
        issues.append("H缺调解前升级/僵持")
    if not RE_MOM_MEDIATE.search(body):
        issues.append("H缺第三方定责劝和")
    if not RE_RECONCILE.search(tail4):
        issues.append("H末段缺仪式性和好")
    return issues


def score_funniness_tail(
    lines: list[str],
    speakers: list[str] | None = None,
) -> tuple[int, list[str]]:
    """H 好笑维：只计互怼/暖收细节，不计结构节拍（那些已在结构分）。"""
    del speakers
    if len(lines) < 8:
        return 0, []
    pts = 0
    pros: list[str] = []
    body = "".join(lines)
    tail = "".join(lines[-5:])

    banter_hits = len(RE_BANTER.findall(body))
    if banter_hits >= 2:
        pts += 4
        pros.append("互怼有梗")
    elif banter_hits >= 1:
        pts += 2
        pros.append("有互怼")

    if RE_MOM_LAYER.search(body) and RE_ESCALATE.search(body):
        pts += 2
        pros.append("调解有层次")

    if RE_WARM_DETAIL.search(tail):
        pts += 2
        pros.append("暖收细节")

    if RE_CHORUS.search(tail):
        pts += 1
        pros.append("齐声收束")

    return min(pts, 10), pros
