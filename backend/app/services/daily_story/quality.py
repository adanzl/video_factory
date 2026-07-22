"""日常故事观感打分（规则版，贴近人工质检口径）。"""

from __future__ import annotations

from typing import Any

# 与 prompts 校验口径对齐（本地副本，避免依赖私有符号）
_LIMP_SOFT_CLOSE_MARKERS = (
    "给你", "算了", "好吧", "好了好了", "行吧", "随你",
)
_PUNCH_BEFORE_SOFT_MARKERS = (
    "说晚了", "已经在了", "自相矛盾", "那你也", "你也没",
    "那不算", "当然不算", "堵死", "戳穿", "说不通",
    "你让的", "重新说", "晚了",
)
_PUNCHLINE_TYPE_MARKERS = (
    "权威翻车", "公平执念", "字面执行", "结盟翻车", "妈妈破功",
    "A类", "C类", "D类", "B类", "E类",
    "A：", "C：", "D：", "B：", "E：",
)
_MOM_JUDGE_PATTERNS = (
    "谁先放好谁先选",
    "算你赢",
    "算他赢",
    "一人一半",
    "一人一个",
)

_WEAK_END_WAIT_MOM = ("等妈", "叫妈", "问妈", "告诉妈", "妈回来", "评理")
_WEAK_END_SPLIT = ("一人一半", "平分", "倒杯子", "一人一个")
_WEAK_END_STUBBORN = ("反正我要用", "反正橡皮", "反正是我的", "谁用谁小狗")

_STRONG_END_MARKERS = (
    "标签", "已经在了", "说晚了", "那不算", "当然不算",
    "自相矛盾", "你让的", "戳穿",
)


def _dialogue_lines(story: dict) -> list[str]:
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return []
    out: list[str] = []
    for item in dialogue:
        if not isinstance(item, dict):
            continue
        text = str(item.get("line") or "").strip()
        if text:
            out.append(text)
    return out


def _grade_from_score(score: int) -> str:
    if score >= 75:
        return "好"
    if score >= 55:
        return "中"
    return "偏弱"


def _has_consecutive_sibling(dialogue: list) -> bool:
    prev = ""
    run = 0
    for item in dialogue:
        if not isinstance(item, dict):
            continue
        sp = str(item.get("speaker") or "").strip()
        if sp not in ("昭昭", "灿灿"):
            prev, run = sp, 0
            continue
        if sp == prev:
            run += 1
            if run >= 2:
                return True
        else:
            prev, run = sp, 1
    return False


def score_daily_story(story: dict | None) -> dict[str, Any]:
    """给故事打观感分。

    返回 grade(好/中/偏弱)、score(0–100)、summary、reasons。
    """
    if not isinstance(story, dict):
        return {
            "grade": "偏弱",
            "score": 0,
            "summary": "无有效故事内容",
            "reasons": ["故事为空"],
        }

    score = 70
    pros: list[str] = []
    cons: list[str] = []

    dialogue = story.get("dialogue") if isinstance(story.get("dialogue"), list) else []
    lines = _dialogue_lines(story)
    last = lines[-1] if lines else ""
    tail2 = "".join(lines[-2:]) if lines else ""
    prev2 = "".join(lines[-3:-1]) if len(lines) >= 3 else "".join(lines[:-1])

    if str(story.get("conflict_core") or "").strip():
        score += 5
        pros.append("有 conflict_core")
    else:
        score -= 10
        cons.append("缺 conflict_core")

    explain = str(story.get("punchline_explain") or "")
    if explain and any(m in explain for m in _PUNCHLINE_TYPE_MARKERS):
        score += 5
        pros.append("笑点有类型标签")
    else:
        score -= 10
        cons.append("笑点解析缺类型")

    opening = story.get("discovery_opening")
    if isinstance(opening, list) and 1 <= len(opening) <= 2:
        score += 5
        pros.append("有发现开场")
    else:
        score -= 5
        cons.append("缺发现开场")

    mom_n = sum(
        1
        for d in dialogue
        if isinstance(d, dict) and str(d.get("speaker") or "").strip() == "妈妈"
    )
    if mom_n == 0:
        score += 5
        pros.append("纯姐弟主戏")
    elif mom_n >= 3:
        score -= 10
        cons.append(f"妈妈台词偏多（{mom_n}句）")
    # 1–2 句妈妈旁听不加减分、不进摘要扣分池

    for pat in _MOM_JUDGE_PATTERNS:
        if any(
            pat in str(d.get("line") or "")
            for d in dialogue
            if isinstance(d, dict) and d.get("speaker") == "妈妈"
        ):
            score -= 25
            cons.append(f"妈妈裁判式收场（{pat}）")
            break

    if _has_consecutive_sibling(dialogue):
        score -= 15
        cons.append("存在同人连说")
    else:
        score += 5
        pros.append("轮流说话")

    weak_hit = False
    if any(m in tail2 for m in _WEAK_END_WAIT_MOM):
        score -= 25
        cons.append("收束甩给妈妈（等妈评理）")
        weak_hit = True
    if any(m in tail2 for m in _WEAK_END_SPLIT):
        score -= 20
        cons.append("收束偏和解（一人一半/平分）")
        weak_hit = True
    if any(m in last for m in _WEAK_END_STUBBORN):
        score -= 15
        cons.append("耍赖软收（反正我要用）")
        weak_hit = True

    limp = any(m in last for m in _LIMP_SOFT_CLOSE_MARKERS)
    punched = any(m in prev2 for m in _PUNCH_BEFORE_SOFT_MARKERS) or any(
        m in prev2 or m in last for m in _STRONG_END_MARKERS
    )
    if limp and not punched:
        score -= 20
        cons.append("无破功软收")
        weak_hit = True
    elif limp and punched:
        score += 8
        pros.append("先破功再软收")
    elif any(m in last for m in _STRONG_END_MARKERS):
        score += 12
        pros.append("末句有破功落点")
    elif not weak_hit and last:
        pros.append("收束中性")

    score = max(0, min(100, score))
    grade = _grade_from_score(score)

    if cons:
        primary = next(
            (c for c in cons if c.startswith("收束") or "软收" in c or "耍赖" in c),
            cons[0],
        )
        summary = primary
        if grade == "偏弱" and len(cons) > 1:
            summary = f"{primary}；另有{len(cons) - 1}项减分"
    elif any("破功" in p for p in pros):
        summary = next(p for p in pros if "破功" in p)
        if "纯姐弟" in "".join(pros):
            summary += "，纯姐弟"
    else:
        summary = "结构完整，收束一般"

    return {
        "grade": grade,
        "score": score,
        "summary": summary,
        "reasons": [*pros, *cons],
    }


def attach_daily_story_quality(story: dict[str, Any]) -> dict[str, Any]:
    """原地写入 story['quality'] 并返回。"""
    if not isinstance(story, dict):
        return story
    story["quality"] = score_daily_story(story)
    return story
