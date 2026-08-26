"""单类型的观感质检路由配置。"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field

from app.services.daily_story.story_types import parse_story_type_code, story_line_for_code

PunchlineScorer = Callable[
    [list[str], list[str], str, str],
    tuple[int, list[str]],
]
HumorIssueCollector = Callable[
    [list[str], list[str] | None],
    list[str],
]
GroundQuoteFn = Callable[[str, str], bool]
QuoteHaystackFn = Callable[[list[str], list[str] | None, str], str]
SceneBeatScorer = Callable[
    [list[str], Callable[[str], bool]],
    tuple[int, list[str]],
]
FunninessTailScorer = Callable[
    [list[str], list[str] | None],
    tuple[int, list[str]],
]
SpecificityBonusScorer = Callable[[list[str], list[str] | None], int]
HumorRevisionHintFn = Callable[[str], str | None]
FactIssueCollector = Callable[[dict], list[str]]
OpeningQualityScorer = Callable[[dict], tuple[int, list[str], list[str]]]

RE_BOOMERANG_RULE = re.compile(
    r"你自己说|你说的|你承认|你刚才说|你刚说|你不是说|你自己.*说|"
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
RE_SOFT_LAST = re.compile(
    r"哼|行吧|随便|好吧|算了|认栽|说不通|说不清(?:楚)?|讲不清(?:楚)?"
)

# C 类末句嘴硬话词表（用户定 2026-08-08）：被戳穿方末句禁光杆叹词单字收尾，
# 须一句有内容的嘴硬话。三类合法形式：
#   ① 认栽不认输（口头上让、心里不服）：「行，算你手快！」「好吧，这次让你。」
#   ② 撂狠话/告状（不服当下，约下次或搬救兵）：「明天我比你早！」「我告诉妈妈去！」
#   ③ 情绪退出（抢不过就撂挑子）：「那我不玩了！」「不跟你好了！」
# 该词表只做 C 类末句硬卡的放宽补充，不替换共享 RE_SOFT_LAST/RE_SURRENDER。
RE_C_STUBBORN_LAST = re.compile(
    # ① 认栽不认输（口头上让、心里不服）
    r"算你手快|算你厉害|算你狠|算你行|这次让你|让着你|让给你|"
    r"你拿去吧|那给你|给你给你|你先来|你先看|你先用|你先玩|你先吃|"
    r"好吧|行行行|"
    # ② 撂狠话/告状（不服当下，约下次或搬救兵）
    r"明天我|下次我|你等着|走着瞧|我记着|我告诉妈妈|去喊妈妈|"
    r"喊妈妈|叫妈妈|告诉妈妈|你小心|你后悔|"
    # ③ 情绪退出（抢不过就撂挑子）
    r"不跟你好了|不跟你玩了|不理你了|我不玩了|我不管了|不玩了"
)

# 光杆叹词单字收尾（C 类末句禁）：「哼。」「行吧。」「算了。」
RE_C_BARE_TONE_END = re.compile(
    r"^(?:哼|切|嘁|哈|行吧|随便|好吧|算了|认栽|说不通|行行行)[。！？…]?$"
)

# C 类末句禁词（排除式：末句命中即非合格嘴硬话收场）。
# 用户定 2026-08-08：光杆叹词之外，「不解释、不拖沓」约束靠这几类词拦下——
# ① 赢家总结（你赢了/算你狠/归你了——胜利者收场，非被戳穿方嘴硬）；
# ② 解释尾巴（因为/所以/是因为…——末句解释理由就拖沓破功）；
# ③ 重分赃（籽归你西瓜归我——把奖品重新切分）；
# ④ 发新规则（那我数到三/下次先给我——当下再立新赛规重新判）。
RE_C_LAST_BANNED = re.compile(
    r"你赢了|归你了|我赢了|赢的|"
    r"因为|所以|是因为|其实|本来|就是说|"
    r"籽归你|归你.{0,3}归我|你先.{0,3}我先|"
    r"重新|重来|数到三|先给我|该我了|轮到我了"
)

# 仪式判据动词（时长/姿势仪式，用户 2026-08-09；2026-08-11 补单脚站系）：
# 举过头顶/坚持X秒/坐稳/站稳/稳住 + 单脚站/金鸡独立/站满十秒/数满十秒。
# 仪式判据场 = 达标制（做到没做到），不比先后、不比时长长短、不比高低标准。
RE_C_RITUAL_VERB = re.compile(
    r"举过头顶|举着.{0,3}(?:不动|不落)|坚持.{0,4}秒|稳住|站稳|坐稳(?:了)?|"
    r"单脚站|金鸡独立|站满十秒|数满十秒",
)
# 末句嘴硬比较维度词（用户 2026-08-09 v27：果汁「比你早」/棒棒糖巧克力「比你举得久」）。
# 仪式判据场，末句比法维度（早/快/先/久/高/标准/直/稳/远/多/晚…）必须字面出现在
# 本场立规句里——立规是「举过头顶坚持三秒」就没有「比谁久/比谁早」维度，末句发明
# 新比法 = 收束换赛规。万能「明天我一定赢过你」与锚定仪式动词（抢先举过头顶）由调用方先豁免。
RE_C_STUBBORN_DIM = re.compile(
    r"比你[^，。！？]{0,4}(早|快|先|久|高|标准|直|稳|远|多|晚|慢|准|好|大|小|厉害)",
)
# 仪式判据场末句换赛规话（非「比你X」句式，2026-08-11 酸奶 v46 抓）：单脚站/举过头顶
# 是达标制不比先后，末句「明天我肯定先抢到/先拿到」= 把赛规偷偷换回先到先得；
# 「比你先」等时序比较由 RE_C_STUBBORN_DIM 先兜，这里兜非「比你」措辞。
RE_C_RITUAL_SWITCH_LAST = re.compile(
    r"先抢到|先拿到|抢先拿到",
)


def c_closing_echo_error(lines: list[str]) -> str | None:
    """末句嘴硬比法漂移（硬卡级）：仪式判据场，末句比较维度须字面在本场立规句。

    C 类收束末句是仪式判据（举过头顶坚持三秒）时，末句嘴硬话只许锚定
    ① 万能胜负「明天我一定赢过你」（任何赛规都成立）；② 仪式动词本身
    （「明天我抢先举过头顶」）；③ 认栽/退出（无比你X比较）。禁发明立规句里
    没有的比较维度——「比你早/比你快」是时序（本场不比先后）、「比你举得久/
    比你高/比你标准」是时长/质量比较（本场是达标制），都是收束换赛规。
    返回错误串（validate 硬卡命中即整稿重抽）或 None。
    """
    if len(lines) < 3:
        return None
    ritual: str | None = None
    ritual_line: str | None = None
    for ln in lines:
        m = RE_C_RITUAL_VERB.search(ln)
        if m and re.search(r"才算|归我|归你|谁先|该我|该你", ln):
            ritual = m.group(0)
            ritual_line = ln
            break
    if not ritual:
        return None  # 先到先得/无仪式判据场不拦（「比你早」在比先后场合法）
    last = lines[-1]
    # 万能胜负 / 锚定仪式动词本身 → 放行
    if "赢过你" in last or RE_C_RITUAL_VERB.search(last):
        return None
    m = RE_C_STUBBORN_DIM.search(last)
    if not m:
        # 非「比你X」的换赛规话（先抢到/先拿到）也拦：仪式场不比先后
        if RE_C_RITUAL_SWITCH_LAST.search(last):
            return (
                f"C末句嘴硬比法漂移：本场仪式判据「{ritual}」，末句「{last[:16]}」"
                "在比先后/换赛规（先抢到/先拿到）——仪式场不比先后；嘴硬话只锚定"
                "仪式动词（明天我抢先单脚站）或万能「明天我一定赢过你！」"
            )
        return None
    dim = m.group(1)
    if dim in ritual_line:
        return None  # 维度字面在本场立规句 → 合法（如立规「谁举得久」→ 比你久）
    return (
        f"C末句嘴硬比法漂移：本场仪式判据「{ritual}」，末句「{last[:16]}」在比「{dim}」，"
        "但立规句没有这个比法——仪式场不比先后（比你早/比你快）、不比长短质量"
        "（比你举得久/比你高/比你标准）；嘴硬话只锚定赛规动词（抢先举过头顶/"
        "坚持到三秒）或万能「明天我一定赢过你！」"
    )

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
    collect_humor_issues: HumorIssueCollector | None = None
    closing_quote_haystack: QuoteHaystackFn | None = None
    ground_closing_quote: GroundQuoteFn | None = None
    stop_on_ungrounded_quote: bool = True
    score_scene_beat: SceneBeatScorer | None = None
    score_funniness_tail: FunninessTailScorer | None = None
    score_specificity_bonus: SpecificityBonusScorer | None = None
    humor_issue_caps: tuple[tuple[str, int], ...] = field(default_factory=tuple)
    humor_revision_hint: HumorRevisionHintFn | None = None
    collect_fact_issues: FactIssueCollector | None = None
    score_opening_quality: OpeningQualityScorer | None = None
    fact_issue_penalty: int = 7

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
    st = story_type or str(story.get("story_type") or "").strip() or None
    code = parse_story_type_code(
        story_type=st,
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
    from app.services.daily_story.story_types.f import quality as quality_f
    from app.services.daily_story.story_types.g import quality as qg
    from app.services.daily_story.story_types.h import quality as quality_h
    from app.services.daily_story.story_types.i import quality as quality_i
    from app.services.daily_story.story_types.l import quality as quality_l

    profiles = (
        qa.QUALITY_PROFILE,
        qb.QUALITY_PROFILE,
        qc.QUALITY_PROFILE,
        qd.QUALITY_PROFILE,
        qe.QUALITY_PROFILE,
        quality_f.QUALITY_PROFILE,
        qg.QUALITY_PROFILE,
        quality_h.QUALITY_PROFILE,
        quality_i.QUALITY_PROFILE,
        quality_l.QUALITY_PROFILE,
    )
    return {p.code: p for p in profiles}


TYPE_QUALITY_PROFILES: dict[str, TypeQualityProfile] = _register_profiles()
_PROFILE_C = TYPE_QUALITY_PROFILES["C"]

__all__ = [
    "PunchlineScorer",
    "RE_C_BARE_TONE_END",
    "RE_C_LAST_BANNED",
    "RE_C_STUBBORN_LAST",
    "SHARED_PUNCH_SOFT",
    "TYPE_QUALITY_PROFILES",
    "TypeQualityProfile",
    "closing_satisfied",
    "quality_profile_for_code",
    "resolve_quality_profile",
    "score_punchline_for_profile",
]
