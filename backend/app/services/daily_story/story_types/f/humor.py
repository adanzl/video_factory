"""F 类好笑维：互呛加码与收束反差。"""

from __future__ import annotations

import re

RE_THREAT = re.compile(r"再说|试试|你敢|讨厌|哼|吼什么")
RE_ESCALATE = re.compile(r"还.{0,4}呢|吼|啊{2,}")
RE_STALE = re.compile(r"不跟你|不理你|谁也不|怂|算了|谁稀罕")
RE_EXTERNAL = re.compile(
    r"拍|镜头|偷拍|尴尬|茄子|闭嘴|闹着玩|干笑|丢人",
)
RE_PIVOT = re.compile(r"拍我们|偷拍|有人拍|镜头|录像")


def close_tail_text(lines: list[str]) -> str:
    """F 收束判定区间：有外部 pivot 则从 pivot 至末；否则末 6 句。"""
    if not lines:
        return ""
    pivot: int | None = None
    for i, ln in enumerate(lines):
        if RE_PIVOT.search(ln):
            pivot = i
            break
    if pivot is not None:
        return "".join(lines[pivot:])
    return "".join(lines[-6:])


def has_close_markers(lines: list[str]) -> bool:
    tail = close_tail_text(lines)
    return bool(RE_STALE.search(tail) or RE_EXTERNAL.search(tail))


def collect_f_humor_issues(
    lines: list[str],
    speakers: list[str] | None = None,
) -> list[str]:
    del speakers
    issues: list[str] = []
    if len(lines) < 8:
        return issues
    body = "".join(lines)
    mid = "".join(lines[: max(1, len(lines) * 2 // 3)])
    tail = close_tail_text(lines)
    if len(RE_THREAT.findall(mid)) < 2:
        issues.append("缺互呛/威胁")
    if not RE_ESCALATE.search(mid):
        issues.append("缺加码升级")
    if not has_close_markers(lines):
        issues.append("末段缺僵持或外部打断收束")
    if RE_EXTERNAL.search(body) and RE_THREAT.search(body):
        return issues
    return issues


def score_funniness_tail(
    lines: list[str],
    speakers: list[str] | None = None,
) -> tuple[int, list[str]]:
    del speakers
    if len(lines) < 6:
        return 0, []
    pts = 0
    pros: list[str] = []
    body = "".join(lines)
    mid = "".join(lines[: max(1, len(lines) * 2 // 3)])
    close = close_tail_text(lines)

    threat_hits = len(RE_THREAT.findall(mid))
    if threat_hits >= 3:
        pts += 4
        pros.append("互呛密集")
    elif threat_hits >= 2:
        pts += 2
        pros.append("有互呛")

    if RE_ESCALATE.search(mid):
        pts += 3
        pros.append("有加码")

    if RE_EXTERNAL.search(close) and RE_THREAT.search(body):
        pts += 4
        pros.append("外部打断反差")
    elif RE_STALE.search(close):
        pts += 2
        pros.append("僵持收束")

    return min(pts, 10), pros
