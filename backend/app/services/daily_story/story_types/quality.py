"""观感：共用 building block、TypeQualityProfile、按类型注册表。"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from app.services.daily_story.story_types import parse_story_type_code, story_line_for_code

PunchlineScorer = Callable[
    [list[str], list[str], str, str],
    tuple[int, list[str]],
]

RE_BOOMERANG_RULE = re.compile(
    r"你自己说|你说的|你承认|你刚才说|你自己.*说|"
    r"你说的.*你先.*选|你.*说.*先选|你定的.*你先",
)
RE_REVELATION_PROP = re.compile(
    r"柜子里|第二块|还有一块|烤箱|里面还有|谁说.*洗碗|"
    r"吃完.*洗碗|吃大.*洗碗|还没.*洗|空了|坏了|掉.*地上",
)
RE_SURRENDER = re.compile(
    r"还是.*吧|那.*吃.*的|算了.*给你|那.*给你|我不要了|"
    r"我不.*了|你吃吧|你拿.*吧|我不管|不管了|反正|"
    r"下次.*听你|这次.*听我",
)
RE_TWIST_SEGUE = re.compile(r"等等|不对|可是|不过|等一下|你再想")
STRONG_END_MARKERS = (
    "标签",
    "已经在了",
    "说晚了",
    "那不算",
    "当然不算",
    "自相矛盾",
    "你让的",
    "戳穿",
)
RE_SOFT_LAST = re.compile(r"哼|行吧|随便|好吧|算了|认栽|说不通")

SHARED_PUNCH_SOFT = (
    "说晚了",
    "已经在了",
    "自相矛盾",
    "矛盾",
    "打脸",
    "那你也",
    "你也没",
    "那不算",
    "当然不算",
    "堵死",
    "戳穿",
    "说不通",
    "你让的",
    "重新说",
    "晚了",
    "改不了",
    "从来不",
    "你说的",
    "你说过",
    "装让",
    "反悔",
    "变卦",
    "自己说",
    "自己打",
    "你自己说",
    "你刚说",
    "上次你说",
    "自己弄",
)


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


def _register_profiles() -> dict[str, TypeQualityProfile]:
    from app.services.daily_story.story_types.a import quality as qa
    from app.services.daily_story.story_types.b import quality as qb
    from app.services.daily_story.story_types.c import quality as qc
    from app.services.daily_story.story_types.d import quality as qd
    from app.services.daily_story.story_types.e import quality as qe

    profiles = (
        qa.QUALITY_PROFILE,
        qb.QUALITY_PROFILE,
        qc.QUALITY_PROFILE,
        qd.QUALITY_PROFILE,
        qe.QUALITY_PROFILE,
    )
    return {p.code: p for p in profiles}


TYPE_QUALITY_PROFILES: dict[str, TypeQualityProfile] = _register_profiles()
_PROFILE_C = TYPE_QUALITY_PROFILES["C"]

__all__ = [
    "PunchlineScorer",
    "SHARED_PUNCH_SOFT",
    "TYPE_QUALITY_PROFILES",
    "TypeQualityProfile",
    "closing_satisfied",
    "quality_profile_for_code",
    "resolve_quality_profile",
    "score_punchline_for_profile",
]
