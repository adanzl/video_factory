"""日常故事对白字数与截断（供 prompts 与 story_types 共用）。"""

from __future__ import annotations

import re

DAILY_STORY_LINE_CHARS_MAX = 24

# 正片开端：背景地点 / 可拍画面（质量加分用，不做硬卡词表误杀）
OPENING_PLACE_RE = re.compile(
    r"厨房|客厅|卧室|门口|玄关|床边|床上|被窝|沙发|灶台|书桌|"
    r"卫生间|浴室|洗手台|阳台|地板|抽屉|书包|餐桌|冰箱|挂钟",
)
OPENING_VISUAL_RE = re.compile(
    r"亮着|歪|松了|鼓鼓|攥|抢|藏|溅|沫|壳|屏幕|勺子|嘴角|"
    r"泡沫|散了|拖|空着|少了|黏|烫|倒|洒|堆|指向|红红|"
    r"一堆|塞|歪着|系一块|打开了|还亮|"
    r"一包|一袋|一块|零食|饼干|薯片|巧克力|糖果|"
    r"发现|滚出|露出|藏着|看到|底下|下面|茶几|"
    r"碎片|碎渣|渣|杯子|水杯",
)


def dialogue_char_count(line: str) -> int:
    """与成片时长估算一致：按台词字符串长度计。"""
    return len(line or "")


def truncate_overlong_line(
    line: str,
    *,
    max_chars: int = DAILY_STORY_LINE_CHARS_MAX,
) -> str:
    limit = max_chars
    cut = -1
    for i, ch in enumerate(line):
        if i >= limit:
            break
        if ch in "，、；; ":
            cut = i
    if cut >= 6:
        return line[:cut].rstrip("，、；; ")
    return line[:limit]


def score_opening_cinematic(
    lines: list[str],
) -> tuple[int, list[str], list[str]]:
    """正片开端口感：有背景+画面加分，过薄扣分。约 -3～+3。"""
    pros: list[str] = []
    cons: list[str] = []
    pts = 0
    joined = "".join(lines)
    has_place = bool(OPENING_PLACE_RE.search(joined))
    has_visual = bool(OPENING_VISUAL_RE.search(joined))
    if len(lines) >= 2:
        pts += 1
        pros.append("开场双句定格")
    else:
        cons.append("开场过薄缺第二镜")
        pts -= 2
    if has_place:
        pts += 1
        pros.append("开场有背景地点")
    if has_visual:
        pts += 1
        pros.append("开场有可拍画面")
    if not has_place and not has_visual:
        cons.append("开场过薄缺背景画面")
        pts -= 3
    elif not has_place:
        cons.append("开场缺背景地点")
        pts -= 1
    elif not has_visual:
        cons.append("开场缺可拍画面")
        pts -= 1
    return pts, pros, cons
