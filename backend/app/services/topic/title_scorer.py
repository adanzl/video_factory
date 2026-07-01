"""选题标题规则打分（见 docs/选题.md §5）。"""

from __future__ import annotations

import re
from dataclasses import dataclass

_SCORE_THRESHOLD = 85

_HARD_REJECT_PATTERNS = (
    r"医疗|养生|保健|药品|治病|手术|癌症|肿瘤",
    r"理财|股票|股市|基金|投资|赚钱|暴富",
    r"时政|情感|离婚|出轨|明星八卦",
    r"热点|热搜|今日|昨天|刚刚|突发",
    r"真人出镜|真人拍摄|实拍|采访",
)

_HISTORY_VISUAL = (
    r"尸|墓|棺|陵|夜|血|火|刀|毒|失踪|消失|烧|埋|挖|盗|杀|死|逃|藏|封",
)

_SCIENCE_VISUAL = (
    r"水|电|温度|气压|化学|光|磁|电池|网线|宽带|路由器|不锈钢|玻璃|塑料|芯片|光刻|半导体|产能|仓库|产线|工厂|胶|禁运|限芯|禁令|断供",
)

_LIFE_VISUAL = (
    r"空调|暖气|制冷|凉快|省电|电费|电表|家居|厨房|洗衣机|冰箱|热水器|WiFi|网速",
)

_CURIOSITY_PATTERNS = (
    r"[?？]",
    r"为什么|怎么|如何|居然|竟然|真相|误区|多数人|不知道|暗藏|猫腻|之谜|下落|去了哪|无人|不敢|惊魂|诡异|反常|到底",
    r"等你呢|笑而不语|就这|慌了|顶得住|备好了|悄悄|就位|后路|慌了神|怕什么|明明|真以为|天真|堆成山|管够|满仓",
)

_TIMELY_PATTERNS = (
    r"\d{4}年|今年|去年|春节|国庆|高考季|双十一",
)


@dataclass(frozen=True)
class ScoreResult:
    visual: int
    fact: int
    curiosity: int
    compliance: int
    total: int
    rejected_reason: str | None

    def to_dict(self) -> dict:
        return {
            "visual": self.visual,
            "fact": self.fact,
            "curiosity": self.curiosity,
            "compliance": self.compliance,
            "total": self.total,
            "rejected_reason": self.rejected_reason,
        }


def _has_pattern(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(p, text) for p in patterns)


def _clamp(value: float) -> int:
    return max(0, min(100, round(value)))


def score_title(
    title: str,
    *,
    track: str | None = None,
    template: str | None = None,
    hook: str | None = None,
) -> ScoreResult:
    text = title.strip()
    combined = f"{text} {hook or ''}"

    for pattern in _HARD_REJECT_PATTERNS:
        if re.search(pattern, combined):
            return ScoreResult(
                visual=0,
                fact=0,
                curiosity=0,
                compliance=0,
                total=0,
                rejected_reason=f"命中硬性约束：{pattern}",
            )

    is_history = track == "历史悬案"

    visual = 70.0
    if is_history:
        if _has_pattern(text, _HISTORY_VISUAL):
            visual += 20
        if "：" in text or ":" in text:
            visual += 10
    else:
        visual_bonus = 0
        if _has_pattern(text, _SCIENCE_VISUAL):
            visual_bonus = max(visual_bonus, 15)
        if _has_pattern(text, _LIFE_VISUAL):
            visual_bonus = max(visual_bonus, 15)
        # 生活体感类科普（热/冷/暑）画面易用示意动画表达
        if re.search(r"热|冷|暑|寒", text):
            visual_bonus = max(visual_bonus, 12)
        visual += visual_bonus
    if len(text) > 28:
        visual -= 10

    fact = 65.0
    if is_history:
        fact += 10
        if any(kw in text for kw in ("墓", "尸", "失踪", "消失", "真相", "之谜")):
            fact += 10
    elif track in {"日常科学原理", "生活避坑实用常识", "数码小白避坑"}:
        fact += 15
        if template in {"误区反问式", "实操避坑式"}:
            fact += 5

    curiosity = 50.0
    if _has_pattern(text, _CURIOSITY_PATTERNS):
        curiosity += 30
    if is_history:
        if any(kw in text for kw in ("无人", "不敢", "消失", "失踪", "惊魂", "诡异", "反常", "到底")):
            curiosity += 10
    elif "?" in text or "？" in text:
        # 科技类对话反转式标题：问号加好奇心
        curiosity += 8
        if any(kw in text for kw in ("明明", "真以为", "就这", "天真", "慌了", "堆成山")):
            curiosity += 7
    if template == "反差好奇式":
        curiosity += 10
    if hook and len(hook) >= 10:
        curiosity += 5

    compliance = 80.0
    if _has_pattern(combined, _TIMELY_PATTERNS):
        compliance -= 40
    if not track:
        compliance -= 5

    total = _clamp(
        visual * 0.3 + fact * 0.3 + curiosity * 0.2 + compliance * 0.2
    )
    rejected_reason = None
    if total < _SCORE_THRESHOLD:
        rejected_reason = f"总分 {total} 低于阈值 {_SCORE_THRESHOLD}"

    return ScoreResult(
        visual=_clamp(visual),
        fact=_clamp(fact),
        curiosity=_clamp(curiosity),
        compliance=_clamp(compliance),
        total=total,
        rejected_reason=rejected_reason,
    )


def status_from_score(result: ScoreResult) -> str:
    if result.rejected_reason and result.total < _SCORE_THRESHOLD:
        return "rejected"
    return "queued"
