"""B 类观感：末段 scorer 与 profile。"""

from __future__ import annotations

import re
from collections.abc import Callable

from app.services.daily_story.story_types.quality import (
    RE_BOOMERANG_RULE,
    RE_SOFT_LAST,
    SHARED_PUNCH_SOFT,
    TypeQualityProfile,
)

RE_ALLY = re.compile(
    r"一起|咱俩|别告诉|瞒着|瞒妈|约定|联手|暗号|分工|你望风|你放风|说好了",
)
RE_BLAME = re.compile(
    r"都怪你|是你先|你答应|不是我的|你先|赖我|你不是说好|才不是我的",
)
RE_EXPOSED = re.compile(
    r"露馅|完了|糟糕|抓到了|听见了|看见了|妈妈|撞见|藏不住",
)
RE_PLAN_FAIL = re.compile(
    r"多拿|忘藏|说漏|掉了|洒了|露出来|忘了藏|袋口|碎|脚印|油渍",
)
_A_STYLE_TAIL = re.compile(r"那不一样|哪里不一样|你刚才说|你自己说")

HUMOR_ISSUE_CAPS: tuple[tuple[str, int], ...] = (
    ("偏A式末四拍", 6),
    ("缺结盟约定", 5),
    ("缺互甩锅", 7),
    ("偏C式争公平", 5),
)


def collect_humor_issues(
    lines: list[str],
    speakers: list[str] | None,
) -> list[str]:
    _ = speakers
    cons: list[str] = []
    n = len(lines)
    if n < 6:
        return cons

    head6 = "".join(lines[:6])
    tail6 = "".join(lines[-6:])
    tail4 = "".join(lines[-4:])

    if _A_STYLE_TAIL.search(tail4) and not RE_BLAME.search(tail6):
        cons.append("B收束偏A式末四拍")

    if not RE_ALLY.search(head6) and not RE_ALLY.search("".join(lines[: n // 3])):
        cons.append("B缺结盟约定")

    if RE_EXPOSED.search(tail4) and not RE_BLAME.search(tail6):
        cons.append("B露馅前缺互甩锅")

    body_pre = "".join(lines[: max(0, n - 8)])
    if body_pre.count("不公平") >= 2 and not RE_ALLY.search(head6):
        cons.append("B偏C式争公平口号")

    if RE_BOOMERANG_RULE.search(tail4) and not RE_BLAME.search(tail6):
        cons.append("B收束偏回旋镖非甩锅")

    return cons


def score_scene_beat(
    lines: list[str],
    *,
    text_has_hammer_beat: Callable[[str], bool],
) -> tuple[int, list[str]]:
    body = lines[:-4] if len(lines) > 4 else lines[:-1]
    mid_text = "".join(body[: max(1, len(body) * 2 // 3)])
    if text_has_hammer_beat(mid_text):
        return 0, []
    if RE_PLAN_FAIL.search(mid_text):
        return 4, ["同盟走样场面"]
    if RE_BLAME.search(mid_text) and RE_ALLY.search("".join(body[: len(body) // 2])):
        return 3, ["走样后甩锅"]
    return 0, []


def humor_revision_hint(issue: str) -> str | None:
    if "缺结盟" in issue:
        return (
            f"【好笑·B】{issue}。"
            "前 6 句姐弟亲口约定分工或暗号（望风/下手/别告诉妈），扣主题实物。"
        )
    if "缺互甩锅" in issue:
        return (
            f"【好笑·B】{issue}。"
            "露馅前先互甩 2 句：都怪你/是你先/你答应的；须扣同盟分工。"
        )
    if "偏A" in issue:
        return (
            f"【好笑·B】{issue}。"
            "收束用互甩锅+一起露馅+末句嘴硬推给对方；"
            "勿「那不一样/哪里不一样」四连拍。"
        )
    if "偏C" in issue or "回旋镖" in issue:
        return (
            f"【好笑·B】{issue}。"
            "主线是同盟裂了互推，不是争公平赛规或回旋镖扣原话。"
        )
    return None


def score_funniness_tail(lines: list[str]) -> tuple[int, list[str]]:
    tail4 = lines[-4:] if len(lines) >= 4 else lines
    late4_text = "".join(tail4)
    points = 0
    pros: list[str] = []
    if RE_BLAME.search(late4_text) and RE_EXPOSED.search(late4_text):
        points += 3
        pros.append("露馅互甩好笑")
    if RE_ALLY.search("".join(lines[: max(1, len(lines) // 4)])) and RE_PLAN_FAIL.search(
        late4_text,
    ):
        points += 2
        pros.append("同盟翻车好笑")
    return points, pros


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
    head_third = "".join(lines[: max(1, n // 3)])
    bonus = 0
    details: list[str] = []

    if RE_ALLY.search(head_third):
        bonus += 4
        details.append("前段结盟约定")

    if RE_BLAME.search(tail3):
        bonus += 6
        details.append("结盟互甩锅")

    if RE_EXPOSED.search(tail4):
        bonus += 10
        details.append("联手露馅收场")

    if RE_ALLY.search(head_third) and RE_PLAN_FAIL.search(
        "".join(lines[n // 3 : n - 3]),
    ):
        bonus += 4
        if "走样" not in "".join(details):
            details.append("约定走样")

    if RE_SOFT_LAST.search(last) and RE_BLAME.search(prev2 + last):
        bonus += 4
        details.append("末句嘴硬甩锅")
    elif RE_BLAME.search(last) and speakers and speakers[-1] in ("灿灿", "昭昭"):
        bonus += 3
        details.append("末句嘴硬甩锅")

    if _A_STYLE_TAIL.search(tail4) and RE_BLAME.search(tail4):
        bonus -= 4

    return bonus, details


QUALITY_PROFILE = TypeQualityProfile(
    code="B",
    score_punchline=score_punchline,
    closing_pro_markers=("露馅", "甩锅", "翻车", "破功", "嘴硬", "走样"),
    summary_highlight_tokens=(
        "推进",
        "露馅",
        "甩锅",
        "翻车",
        "破功",
        "走样",
    ),
    punch_before_soft_markers=SHARED_PUNCH_SOFT
    + (
        "都怪你",
        "露馅",
        "完了",
        "是你先",
        "你答应",
    ),
    collect_humor_issues=collect_humor_issues,
    score_scene_beat=score_scene_beat,
    score_funniness_tail=score_funniness_tail,
    humor_issue_caps=HUMOR_ISSUE_CAPS,
    humor_revision_hint=humor_revision_hint,
    penalize_stubborn_end=False,
)
