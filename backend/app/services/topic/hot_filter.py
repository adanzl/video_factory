"""热搜词 L1 筛选：规则硬筛 + LLM 分类（direct/expand/reject）。"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Literal

from app.config import get_settings
from app.services.topic.hot_fetcher import HotKeyword
from app.services.topic.hot_llm import chat_json, extract_items_array

logger = logging.getLogger(__name__)

FilterMode = Literal["direct", "expand"]

# word_type: 4=新 5=热 7=直播 9=梗 11=话题 12=独家/宣发
_REJECT_WORD_TYPES = frozenset({7, 12})

# 仅保留无歧义、合规向的硬性丢弃（游戏/体育/娱乐等明显非科普）
_REJECT_PATTERNS = (
    r"医疗|养生|保健|药品|治病|手术|癌症|肿瘤",
    r"理财|股票|股市|基金|投资|赚钱|暴富",
    r"时政|情感|离婚|出轨|明星|八卦|绯闻",
    r"夺冠|战舞|转会|官宣|开服|公测|抽卡|皮肤|新角色|实机|PV|版本更新",
    r"战胜|比分|VS|vs|联赛|世界杯|欧冠|NBA|LPL|LCK|电竞",
    r"Major|冠军|MVP|赛事复盘|科隆|大师赛|belike",
    r"舞台|神级|MV|演唱会|歌词|翻唱|舞蹈|饭拍|直拍",
    r"\d+[-:：]\d+",
)

# 仅用于规则模式：热搜本身已含科普/生活/数码语义时直接放行
_DIRECT_PATTERNS = (
    r"为什么|怎么|如何|原理|真相|误区|省电|充电|发烫|鼓包",
    r"空调|冰箱|洗衣机|热水器|路由器|宽带|WiFi|wifi|网线|手机|电池",
    r"水|电|温度|气压|化学|光|磁|消毒|保质期|过敏|睡眠",
    r"不锈钢|玻璃|塑料|内存|缓存|清理|参数|选购",
)

_L1_LLM_SYSTEM = (
    "你是 B 站科普短视频选题策划。对每条热搜判断：能否进入「AI 全自动科普成片」选题池。"
    "本项目的「科普」≠ 仅自然科学原理；凡能落到下列四大赛道、且有可验证固定事实的，都算合格："
    "①日常科学原理（物理化学生物等）；②生活避坑实用常识（升学志愿、消费误区、安全避险、办事规则等）；"
    "③数码小白避坑；④古代冷门生活史（民俗由来、古人技艺）。"
    "输出 JSON：items 数组，每项含 keyword、accept(bool)、mode、reason。"
    "判定流程："
    "1) 能否从热搜抽出上述任一战道的「长尾选题角度」？"
    "   要求：有唯一或主流可核验答案，能画成示意插画，不追时效八卦。"
    "   不能 → accept=false。"
    "2) 能 → 选 mode："
    "   direct：热搜本身已是问句/误区/常识话题，几乎可直接策划；"
    "   expand：热搜是新闻、节日、社会讨论、热议现象，需剥离人名/赛果/日期/官宣/被查后做相关性扩展。"
    "3) expand 的关键是「领域扩展」而非「新闻复述」："
    "   · 教育升学热议 → 生活避坑（分数段含义、志愿规则、常见误区），不是自然科学；"
    "   · 安全事故新闻 → 生活避坑（成因、自救、避险常识），不写具体案件与责任人；"
    "   · 节日民俗活动 → 古代生活史或科学原理（习俗由来、背后力学/化学）；"
    "   · 消费/参数讨论 → 数码避坑或生活常识。"
    "4) 勿用「无科学原理」「纯社会现象」作为拒绝理由——生活实用常识、规则误区同样合格。"
    "拒绝：医疗养生、理财股市、时政立场/人事查处、游戏宣发、体育赛果、电竞战报、明星娱乐、纯情感梗、无法核验的争议。"
    "示意（类型对照，非答案模板）："
    "· expand：「不同家庭对分数段的理解差异」——生活避坑，非自然科学；"
    "· expand：「某地矿井突发事故」——矿井瓦斯/透水避险，不写被查；"
    "· direct：「路由器放墙角网速变差」——数码/生活误区；"
    "· reject：「某队总决赛让二追三」——纯赛果；"
    "· reject：「手游周年庆送十连」——游戏运营。"
    "reason 一句话说明落入哪条赛道、为何 direct/expand，勿照抄示意。"
)


@dataclass(frozen=True)
class HotFilterResult:
    item: HotKeyword
    accepted: bool
    mode: FilterMode | None
    reason: str


def _matches(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(p, text) for p in patterns)


def _hard_reject(item: HotKeyword) -> HotFilterResult | None:
    text = f"{item.keyword} {item.show_name}"
    if item.word_type in _REJECT_WORD_TYPES:
        return HotFilterResult(
            item=item,
            accepted=False,
            mode=None,
            reason=f"word_type={item.word_type} 不适合科普长尾",
        )
    for pattern in _REJECT_PATTERNS:
        if re.search(pattern, text):
            return HotFilterResult(
                item=item,
                accepted=False,
                mode=None,
                reason=f"命中硬性丢弃：{pattern}",
            )
    return None


def filter_hot_keyword_rules(item: HotKeyword) -> HotFilterResult:
    """规则 L1：仅硬性丢弃 + 明显 direct，不做相关性扩展判定。"""
    hard = _hard_reject(item)
    if hard:
        return hard

    text = f"{item.keyword} {item.show_name}"
    if _matches(text, _DIRECT_PATTERNS):
        return HotFilterResult(
            item=item,
            accepted=True,
            mode="direct",
            reason="含科普/生活/数码向关键词",
        )

    return HotFilterResult(
        item=item,
        accepted=False,
        mode=None,
        reason="未命中直接科普信号，需 L1 LLM 做相关性判定",
    )


def _mock_l1_classify(item: HotKeyword) -> HotFilterResult:
    """MOCK_MODE 下模拟 LLM：硬筛 + direct 同规则，其余标为 expand 候选。"""
    hard = _hard_reject(item)
    if hard:
        return hard

    text = f"{item.keyword} {item.show_name}"
    if _matches(text, _DIRECT_PATTERNS):
        return HotFilterResult(
            item=item,
            accepted=True,
            mode="direct",
            reason="含科普/生活/数码向关键词",
        )

    return HotFilterResult(
        item=item,
        accepted=True,
        mode="expand",
        reason="mock L1：作扩展候选，待 L2 转化",
    )


def _parse_l1_payload(
    raw: Any,
    items: list[HotKeyword],
) -> list[HotFilterResult]:
    by_keyword = {item.keyword: item for item in items}
    rows = extract_items_array(raw)

    out: list[HotFilterResult] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        keyword = str(row.get("keyword") or "").strip()
        item = by_keyword.get(keyword)
        if not item or keyword in seen:
            continue
        seen.add(keyword)
        if not row.get("accept"):
            reason = str(row.get("reason") or "LLM 判定不适合科普").strip()
            out.append(
                HotFilterResult(item=item, accepted=False, mode=None, reason=reason)
            )
            continue
        mode_raw = str(row.get("mode") or "expand").strip().lower()
        mode: FilterMode = "expand" if mode_raw == "expand" else "direct"
        reason = str(row.get("reason") or "LLM 判定可进入选题池").strip()
        out.append(
            HotFilterResult(item=item, accepted=True, mode=mode, reason=reason)
        )

    for item in items:
        if item.keyword in seen:
            continue
        out.append(
            HotFilterResult(
                item=item,
                accepted=False,
                mode=None,
                reason="LLM 未返回判定，默认丢弃",
            )
        )
    return out


def filter_hot_keywords_llm(items: list[HotKeyword]) -> list[HotFilterResult]:
    if not items:
        return []

    settings = get_settings()
    if settings.mock_mode:
        return [_mock_l1_classify(item) for item in items]

    lines = [
        f"- keyword={item.keyword!r} show_name={item.show_name!r} heat={item.heat_score}"
        for item in items
    ]
    user = "请分类以下热搜词：\n" + "\n".join(lines)
    raw = chat_json(_L1_LLM_SYSTEM, user)
    results = _parse_l1_payload(raw, items)
    kept = sum(1 for r in results if r.accepted)
    logger.info("[HOT] L1 llm kept=%d rejected=%d from=%d", kept, len(results) - kept, len(items))
    return results


def filter_hot_keywords(
    items: list[HotKeyword],
    *,
    use_llm: bool = True,
) -> tuple[list[HotFilterResult], list[HotFilterResult]]:
    if not items:
        return [], []

    if use_llm:
        pre_rejected: list[HotFilterResult] = []
        candidates: list[HotKeyword] = []
        for item in items:
            hard = _hard_reject(item)
            if hard:
                pre_rejected.append(hard)
            else:
                candidates.append(item)
        llm_results = filter_hot_keywords_llm(candidates)
        all_results = llm_results + pre_rejected
    else:
        all_results = [filter_hot_keyword_rules(item) for item in items]

    kept = [r for r in all_results if r.accepted]
    rejected = [r for r in all_results if not r.accepted]
    return kept, rejected


filter_hot_keyword = filter_hot_keyword_rules
