"""G 类好笑维：pivot 反差与暖收。"""

from __future__ import annotations

import re

RE_ESCALATE = re.compile(
    r"丢人|嘴硬|怂|没记性|充|大侠|烦|骂|错错",
)
RE_PIVOT = re.compile(
    r"护|撑腰|拼命|动你|心疼|管你|认真的|我怕",
)
RE_STUNNED = re.compile(r"你说啥|……|\.\.\.|愣")
RE_SOFT = re.compile(r"擦|药|说好了|行了|过来|撑腰|相视|笑")


def collect_g_humor_issues(
    lines: list[str],
    speakers: list[str] | None = None,
) -> list[str]:
    del speakers
    issues: list[str] = []
    body = "".join(lines)
    if not RE_ESCALATE.search(body):
        issues.append("缺数落/互损升级")
    if not RE_PIVOT.search(body):
        issues.append("缺 pivot 护短/真心")
    if not RE_STUNNED.search(body):
        issues.append("缺 pivot 后愣住 beat")
    tail = "".join(lines[-3:]) if lines else ""
    if tail and not RE_SOFT.search(tail):
        issues.append("末段缺暖收信号")
    return issues
