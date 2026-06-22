"""热搜词 L2：转化为长尾科普 theme。"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from app.config import get_settings
from app.services.topic.hot_fetcher import HotKeyword
from app.services.topic.hot_filter import FilterMode, HotFilterResult
from app.services.topic.hot_llm import chat_json, extract_items_array

logger = logging.getLogger(__name__)

_TRACKS = frozenset(
    {
        "日常科学原理",
        "生活避坑实用常识",
        "数码小白避坑",
        "古代冷门生活史",
    }
)

_SYSTEM_PROMPT = (
    "你是 B 站科普短视频策划。把已通过 L1 的热搜改写为「长尾科普视频主题」theme。"
    "输出 JSON：items 数组，每项含 keyword、accept(bool)、theme、track、reason、mode。"
    "输入会附带 mode（direct/expand）和 l1_reason，请遵循："
    "· direct：去掉时效词后贴近原话题，强化误区/反差/原理角度；"
    "· expand：做相关性扩展——从热搜抽取可长期搜索的「领域问题」，"
    "  不写人名、队名、日期、具体事故地点、赛事结果、官宣、被查、八卦。"
    "theme 要求：15-40 字中文，适合 AI 插画成片，有明确常识锚点（科学原理、生活规则、数码参数、历史民俗均可）。"
    "track 四选一：日常科学原理、生活避坑实用常识、数码小白避坑、古代冷门生活史。"
    "无法产出合规长尾主题 → accept=false，theme 为空。"
    "禁止：医疗养生、理财股市、时政情感、游戏宣发、体育赛果。"
    "扩展原则（按类型思考，勿套用固定词表）："
    "· 自然现象/天气 → 背后物理或安全常识；"
    "· 节日民俗/传统活动 → 习俗由来或涉及的力学/化学/生物原理；"
    "· 安全事故/灾害新闻 → 成因与自救避险，不追具体案件；"
    "· 教育/升学/志愿/职场讨论 → 生活避坑：可验证的规则、分数段含义、常见误区（不要求自然科学）；"
    "· 消费/数码讨论 → 参数、原理、选购误区。"
)


@dataclass(frozen=True)
class HotTheme:
    keyword: str
    theme: str
    track: str
    reason: str
    mode: FilterMode | None = None

    def to_dict(self) -> dict[str, str]:
        data = {
            "keyword": self.keyword,
            "theme": self.theme,
            "track": self.track,
            "reason": self.reason,
        }
        if self.mode:
            data["mode"] = self.mode
        return data


def _heuristic_theme(item: HotKeyword, *, mode: FilterMode | None = None) -> HotTheme | None:
    """离线启发式仅处理 direct；expand 必须走 LLM。"""
    if mode == "expand":
        return None

    text = item.show_name or item.keyword
    cleaned = re.sub(r"\s+", "", text)
    if not cleaned:
        return None

    track = "日常科学原理"
    if re.search(r"手机|电脑|路由器|宽带|网线|WiFi|wifi|内存|缓存|参数", cleaned):
        track = "数码小白避坑"
    elif re.search(r"避坑|猫腻|扣费|省钱|省电|误区", cleaned):
        track = "生活避坑实用常识"
    elif re.search(r"古人|古代|宋朝|唐朝|明朝|清朝", cleaned):
        track = "古代冷门生活史"

    theme = re.sub(r"(最新|今日|刚刚|突发|被查).*$", "", cleaned)
    if len(theme) < 4:
        return None

    return HotTheme(
        keyword=item.keyword,
        theme=theme,
        track=track,
        reason="启发式转化（mock/离线）",
        mode=mode,
    )


def _parse_theme_payload(raw: Any) -> list[HotTheme]:
    items = extract_items_array(raw)

    out: list[HotTheme] = []
    for row in items:
        if not isinstance(row, dict):
            continue
        if not row.get("accept"):
            continue
        keyword = str(row.get("keyword") or "").strip()
        theme = re.sub(r"\s+", "", str(row.get("theme") or "").strip())
        if not keyword or not theme:
            continue
        track = str(row.get("track") or "").strip()
        if track not in _TRACKS:
            track = "日常科学原理"
        reason = str(row.get("reason") or "").strip()
        mode_raw = str(row.get("mode") or "").strip().lower()
        mode: FilterMode | None = "expand" if mode_raw == "expand" else (
            "direct" if mode_raw == "direct" else None
        )
        out.append(
            HotTheme(
                keyword=keyword,
                theme=theme,
                track=track,
                reason=reason,
                mode=mode,
            )
        )
    return out


def convert_hot_to_themes(
    filter_results: list[HotFilterResult],
    *,
    use_llm: bool = True,
) -> list[HotTheme]:
    if not filter_results:
        return []

    settings = get_settings()
    if settings.mock_mode or not use_llm:
        out: list[HotTheme] = []
        for row in filter_results:
            theme = _heuristic_theme(row.item, mode=row.mode)
            if theme:
                out.append(theme)
        logger.info("[HOT] heuristic themes count=%d from=%d", len(out), len(filter_results))
        return out

    lines = [
        (
            f"- keyword={r.item.keyword!r} show_name={r.item.show_name!r} "
            f"mode={r.mode} heat={r.item.heat_score} l1_reason={r.reason!r}"
        )
        for r in filter_results
    ]
    user = "请转化以下热搜词：\n" + "\n".join(lines)
    raw = chat_json(_SYSTEM_PROMPT, user)
    themes = _parse_theme_payload(raw)
    logger.info("[HOT] llm themes count=%d from=%d", len(themes), len(filter_results))
    return themes
