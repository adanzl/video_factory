"""日常故事观感：按矛盾类型（A–E）路由的质检配置与末段评分。"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from app.services.daily_story.story_type_lines import (
    parse_story_type_code,
    story_line_for_code,
)

PunchlineScorer = Callable[
    [list[str], list[str], str, str],
    tuple[int, list[str]],
]

# ── 共用正则（仅作 building block，由各类 scorer 自行选用）──
_RE_BOOMERANG_RULE = re.compile(
    r"你自己说|你说的|你承认|你刚才说|你自己.*说|"
    r"你说的.*你先.*选|你.*说.*先选|你定的.*你先",
)
_RE_REVELATION_PROP = re.compile(
    r"柜子里|第二块|还有一块|烤箱|里面还有|谁说.*洗碗|"
    r"吃完.*洗碗|吃大.*洗碗|还没.*洗|空了|坏了|掉.*地上",
)
_RE_SURRENDER = re.compile(
    r"还是.*吧|那.*吃.*的|算了.*给你|那.*给你|我不要了|"
    r"我不.*了|你吃吧|你拿.*吧|我不管|不管了|反正|"
    r"下次.*听你|这次.*听我",
)
_RE_TWIST_SEGUE = re.compile(r"等等|不对|可是|不过|等一下|你再想")
_STRONG_END_MARKERS = (
    "标签", "已经在了", "说晚了", "那不算", "当然不算",
    "自相矛盾", "你让的", "戳穿",
)

_RE_A_LOOP_CLOSE = re.compile(r"哪里不一样|都是听|到底哪|凭什么听")
_RE_A_PRECEDENT = re.compile(r"上次|之前|你也|明明说|妈妈说过|你不是说|你自己也")
_RE_A_ADMIT = re.compile(
    r"那不一样|你刚才说|你自己说|你也这样|我是教你|不是那个意思",
)
_RE_A_SOFT_LAST = re.compile(r"哼|行吧|随便|好吧|算了|认栽|说不通")
_RE_A_RULE_PUSH = re.compile(r"你刚才说|你自己说|你也这样|那不一样")

_RE_B_ALLY = re.compile(r"一起|咱俩|别告诉|瞒着|约定|联手|暗号")
_RE_B_BLAME = re.compile(r"都怪你|是你先|你答应|不是我的|你先")
_RE_B_EXPOSED = re.compile(r"露馅|完了|糟糕|抓到了|听见了|看见了")

_RE_D_RULE = re.compile(r"不许|别碰|规矩|叮嘱|说了|不能")
_RE_D_LITERAL = re.compile(r"照做|按你说的|你不是说|字面|打开|碰了|动了")
_RE_D_MESS = re.compile(r"掉了|滑|洒|乱|坏|打不开|饿着|够不着")
_RE_D_FIX = re.compile(r"我来|我捡|我弄|只好|只能|没办法|我得")

_RE_E_MOM_TALK = re.compile(r"应该|必须|规矩|听我的|我说|不行")
_RE_E_KID_ASK = re.compile(r"为什么|凭什么|那你|你也|上次")
_RE_E_MOM_WAFFLE = re.compile(r"不是|不一样|那是|总之|反正|不是那个")
_RE_E_LOOP = re.compile(r"你自己说|你刚才|那你也是|你也这样")
_RE_MOM_SOFT = re.compile(r"唉|行了|好吧|随便|说不通|行行行")


def _score_punchline_a(
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
    bonus = 0
    details: list[str] = []

    first_half = "".join(lines[: n // 2])
    second_half = "".join(lines[n // 2:])
    if _RE_A_PRECEDENT.search(second_half) and _RE_A_PRECEDENT.search(tail4):
        if not _RE_A_PRECEDENT.search(first_half) or _RE_A_PRECEDENT.search(tail3):
            bonus += 6
            details.append("引先例收束")

    if _RE_A_LOOP_CLOSE.search(tail3) or (
        _RE_A_ADMIT.search(prev2) and _RE_A_LOOP_CLOSE.search(last)
    ):
        bonus += 5
        if "引先例收束" not in details:
            details.append("追问闭环")

    if _RE_A_ADMIT.search(tail3) and _RE_A_RULE_PUSH.search(tail3):
        bonus += 4
        if not details:
            details.append("规则回旋收束")

    if _RE_A_SOFT_LAST.search(last) and (
        _RE_A_ADMIT.search(prev2) or _RE_A_LOOP_CLOSE.search(prev2)
    ):
        bonus += 4
        if not any("破功" in d for d in details):
            details.append("末句权威破功")

    if _RE_SURRENDER.search(tail3) and not details:
        bonus -= 3

    return bonus, details


def _score_punchline_c(
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

    first_half = "".join(lines[: n // 2])
    second_half = "".join(lines[n // 2:])
    revelations = _RE_REVELATION_PROP.findall(second_half)
    new_revelations = [r for r in revelations if r not in first_half]
    if new_revelations and any(m in tail4 for m in new_revelations):
        bonus += 10
        details.append("实物真相反转")

    if _RE_BOOMERANG_RULE.search(tail3):
        bonus += 8
        if "实物真相反转" not in details:
            details.append("回旋镖收束")

    if _RE_SURRENDER.search(tail3):
        if any(m in tail3 for m in ("洗碗", "洗", "坏了", "掉了", "空了")):
            bonus += 6
            if not details:
                details.append("困境秒怂反转")
        elif not _RE_BOOMERANG_RULE.search(tail3) and not any(
            m in tail3 for m in _STRONG_END_MARKERS
        ):
            bonus -= 3

    twist_matches = _RE_TWIST_SEGUE.findall(tail3)
    if twist_matches and (
        _RE_REVELATION_PROP.search(tail4) or _RE_BOOMERANG_RULE.search(tail4)
    ):
        bonus += 3

    if speakers and len(speakers) >= 2:
        last_sp = speakers[-1]
        prev_sp = speakers[-2]
        if last_sp != prev_sp and _RE_SURRENDER.search(last):
            bonus += 3

    return bonus, details


def _score_punchline_d(
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
    bonus = 0
    details: list[str] = []

    if _RE_D_MESS.search(tail4) and _RE_D_LITERAL.search(tail4):
        bonus += 8
        details.append("字面后果落地")

    if _RE_D_FIX.search(tail3) and _RE_BOOMERANG_RULE.search(tail3):
        bonus += 10
        details.append("叮嘱方破规回旋镖")

    if _RE_BOOMERANG_RULE.search(tail3) and _RE_D_RULE.search(prev2):
        bonus += 6
        if not details:
            details.append("字面回旋镖收束")

    if _RE_A_SOFT_LAST.search(last) and _RE_BOOMERANG_RULE.search(prev2):
        bonus += 4
        details.append("末句叮嘱方破功")

    if _RE_SURRENDER.search(tail3) and not details:
        bonus -= 3

    return bonus, details


def _score_punchline_b(
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
    bonus = 0
    details: list[str] = []

    if _RE_B_BLAME.search(tail3):
        bonus += 6
        details.append("结盟互甩锅")

    if _RE_B_EXPOSED.search(tail4):
        bonus += 10
        details.append("联手露馅收场")

    if _RE_B_ALLY.search("".join(lines[: n // 2])) and _RE_B_EXPOSED.search(tail3):
        bonus += 4
        if "露馅" not in "".join(details):
            details.append("约定翻车")

    if _RE_A_SOFT_LAST.search(last) and _RE_B_BLAME.search(prev2):
        bonus += 3
        details.append("末句嘴硬甩锅")

    return bonus, details


def _score_punchline_e(
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

    if _RE_E_LOOP.search(tail3) and _RE_E_MOM_WAFFLE.search(prev2):
        bonus += 10
        details.append("追问闭环")

    if _RE_E_KID_ASK.search(tail4) and _RE_MOM_SOFT.search(last):
        bonus += 8
        details.append("妈妈破功收束")

    if speakers and speakers[-1] == "妈妈" and _RE_MOM_SOFT.search(last):
        bonus += 5
        if "破功" not in "".join(details):
            details.append("末句妈妈破功")

    if _RE_E_MOM_TALK.search(tail4) and _RE_E_LOOP.search(tail4):
        bonus += 4
        details.append("妈妈逻辑露馅")

    return bonus, details


@dataclass(frozen=True)
class TypeQualityProfile:
    """单类型的观感质检路由配置。"""

    code: str
    score_punchline: PunchlineScorer
    closing_pro_markers: tuple[str, ...]
    summary_highlight_tokens: tuple[str, ...]
    punch_before_soft_markers: tuple[str, ...]
    mom_lines_penalty_at: int = 3
    mom_lines_penalty: int = 10
    penalize_wait_mom_end: bool = True
    penalize_split_end: bool = True
    penalize_stubborn_end: bool = True
    penalize_mom_judge: bool = True

    def layer_patterns(self):
        return story_line_for_code(self.code).layer_patterns

    def revision_hints(self) -> tuple[str, str]:
        line = story_line_for_code(self.code)
        return line.escalation_revision_hint, line.closing_revision_hint


_SHARED_PUNCH_SOFT = (
    "说晚了", "已经在了", "自相矛盾", "矛盾", "打脸",
    "那你也", "你也没", "那不算", "当然不算", "堵死",
    "戳穿", "说不通", "你让的", "重新说", "晚了",
    "改不了", "从来不", "你说的", "你说过",
    "装让", "反悔", "变卦", "自己说", "自己打",
    "你自己说", "你刚说", "上次你说", "自己弄",
)

_PROFILE_A = TypeQualityProfile(
    code="A",
    score_punchline=_score_punchline_a,
    closing_pro_markers=(
        "追问闭环", "引先例", "权威破功", "回旋", "破功",
    ),
    summary_highlight_tokens=(
        "反转", "回旋镖", "推进", "破功", "追问闭环", "引先例", "权威",
    ),
    punch_before_soft_markers=_SHARED_PUNCH_SOFT + (
        "那不一样", "哪里不一样", "凭什么", "你也",
    ),
)

_PROFILE_C = TypeQualityProfile(
    code="C",
    score_punchline=_score_punchline_c,
    closing_pro_markers=("回旋镖", "反转", "破功", "实物", "困境"),
    summary_highlight_tokens=(
        "反转", "回旋镖", "推进", "破功", "实物",
    ),
    punch_before_soft_markers=_SHARED_PUNCH_SOFT,
)

_PROFILE_D = TypeQualityProfile(
    code="D",
    score_punchline=_score_punchline_d,
    closing_pro_markers=("回旋镖", "破功", "字面", "破规", "后果"),
    summary_highlight_tokens=(
        "回旋镖", "推进", "破功", "字面", "后果",
    ),
    punch_before_soft_markers=_SHARED_PUNCH_SOFT + (
        "你自己说", "你刚才", "你现在也",
    ),
)

_PROFILE_B = TypeQualityProfile(
    code="B",
    score_punchline=_score_punchline_b,
    closing_pro_markers=("露馅", "甩锅", "翻车", "破功", "嘴硬"),
    summary_highlight_tokens=(
        "推进", "露馅", "甩锅", "翻车", "破功",
    ),
    punch_before_soft_markers=_SHARED_PUNCH_SOFT + (
        "都怪你", "露馅", "完了",
    ),
)

_PROFILE_E = TypeQualityProfile(
    code="E",
    score_punchline=_score_punchline_e,
    closing_pro_markers=("破功", "闭环", "露馅", "妈妈"),
    summary_highlight_tokens=(
        "推进", "破功", "闭环", "妈妈",
    ),
    punch_before_soft_markers=_SHARED_PUNCH_SOFT + (
        "你自己说", "那你也是", "你也",
    ),
    mom_lines_penalty_at=8,
    penalize_wait_mom_end=False,
    penalize_split_end=True,
    penalize_stubborn_end=False,
    penalize_mom_judge=True,
)

TYPE_QUALITY_PROFILES: dict[str, TypeQualityProfile] = {
    p.code: p
    for p in (
        _PROFILE_A,
        _PROFILE_B,
        _PROFILE_C,
        _PROFILE_D,
        _PROFILE_E,
    )
}


def quality_profile_for_code(type_code: str) -> TypeQualityProfile:
    return TYPE_QUALITY_PROFILES.get(type_code.upper(), _PROFILE_C)


def resolve_quality_profile(
    story: dict | None,
    *,
    story_type: str | None = None,
) -> TypeQualityProfile:
    if not isinstance(story, dict):
        return _PROFILE_C
    code = parse_story_type_code(
        story_type=story_type,
        punchline=str(story.get("punchline_explain") or ""),
    )
    return quality_profile_for_code(code)


def score_punchline_for_profile(
    profile: TypeQualityProfile,
    lines: list[str],
    speakers: list[str],
    prev2: str,
    last: str,
) -> tuple[int, list[str]]:
    return profile.score_punchline(lines, speakers, prev2, last)


def closing_satisfied(pros: list[str], profile: TypeQualityProfile) -> bool:
    markers = profile.closing_pro_markers
    return any(any(m in r for m in markers) for r in pros)
