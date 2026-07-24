"""日常故事观感打分（规则版，贴近人工质检口径）。"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

_LIMP_SOFT_CLOSE_MARKERS = (
    "给你", "算了", "好吧", "好了好了", "行吧", "随你",
    "我不管", "不管了", "随便你", "那行", "行行行",
    "哼", "吃吧", "你赢",
)
_PUNCHLINE_TYPE_MARKERS = (
    "权威翻车", "公平执念", "字面执行", "结盟翻车", "妈妈破功",
    "A类", "C类", "D类", "B类", "E类",
    "A：", "C：", "D：", "B：", "E：",
)
_MOM_JUDGE_PATTERNS = (
    "谁先放好谁先选", "算你赢", "算他赢", "一人一半", "一人一个",
)

_WEAK_END_WAIT_MOM = ("等妈", "叫妈", "问妈", "告诉妈", "妈回来", "评理")
_WEAK_END_SPLIT = ("一人一半", "平分", "倒杯子", "一人一个")
_WEAK_END_STUBBORN = ("反正我要用", "反正橡皮", "反正是我的", "谁用谁小狗")

_STRONG_END_MARKERS = (
    "标签", "已经在了", "说晚了", "那不算", "当然不算",
    "自相矛盾", "你让的", "戳穿",
)

from app.services.daily_story.quality_by_type import (
    closing_satisfied,
    resolve_quality_profile,
    score_punchline_for_profile,
)
# ── 绕圈检测 ──
_REDUNDANCY_STOP_WORDS: frozenset[str] = frozenset({
    "我", "你", "他", "她", "我们", "你们", "他们", "她们",
    "的", "了", "是", "在", "不", "就", "也", "都", "要",
    "会", "能", "有", "和", "还", "这", "那", "说", "个",
    "吗", "呢", "吧", "啊", "嘛", "哦", "嗯", "呀",
    "怎么", "什么", "为什么", "没有", "不是", "可以", "不能",
    "这个", "那个", "一个", "已经", "现在", "所以", "因为",
    "但是", "如果", "虽然", "而且", "还是", "应该", "必须",
})
_CONTENT_WORD_RE = re.compile(r"[\u4e00-\u9fff]{2,}")

# 结构（格式/节奏/类型收束形态）满分上限；超过须靠好笑维度叠加
STRUCTURE_SCORE_CAP = 80
# 好笑维度 0–20：≥5 才可到 85 档，≥15 才可到 95 档
_HUMOR_POINTS_FOR_GOOD = 5
_HUMOR_POINTS_FOR_GREAT = 15

_RE_HAMMER = re.compile(
    r"\d+|[一二三四五六七八九十]+(?:分钟|秒|块|个|次|遍)|"
    r"算错|写错|弹错|多玩|少玩|进位|竖式|升fa|降",
)

# ── 好笑 / 节奏（规则近似人工：具体、有出处、少复读）──
_RE_DIRECT_QUOTE = re.compile(
    r"(?:你刚才说|你自己说|你不是说|你刚说|你说的)([^，。！？…]{3,})",
)
_RE_MOM_PRECEDENT_CLAIM = re.compile(
    r"(?:上次|之前|昨天).{0,10}(?:妈|妈妈)|妈妈(?:说过|说要|也说过)",
)
_A_DRUDGE_PHRASES = (
    "你得听", "听我的", "我是姐姐", "考验", "我没错", "那不一样",
    "凭什么", "不公平", "教你", "规矩",
)
_A_TEMPLATE_MARKERS = ("哪里不一样", "都是听", "大人也要听小孩", "大人要听小孩")


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


def _dialogue_speakers(story: dict) -> list[str]:
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return []
    out: list[str] = []
    for item in dialogue:
        if not isinstance(item, dict):
            continue
        sp = str(item.get("speaker") or "").strip()
        text = str(item.get("line") or "").strip()
        if text:
            out.append(sp)
    return out


def _grade_from_score(score: int) -> str:
    if score >= 70:
        return "好"
    if score >= 45:
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


def _score_escalation(
    lines: list[str],
    *,
    layer_patterns: tuple[tuple[str, re.Pattern[str]], ...],
) -> tuple[int, list[str]]:
    n = len(lines)
    if n < 6:
        return -12, ["冲突无明显推进"]

    quarter = max(1, n // 4)
    segments = [
        lines[:quarter],
        lines[quarter:quarter * 2],
        lines[quarter * 2:quarter * 3],
        lines[quarter * 3:],
    ]

    triggered_per_seg: list[set[str]] = []
    for seg in segments:
        seg_text = "".join(seg)
        triggered: set[str] = set()
        for label, pat in layer_patterns:
            if pat.search(seg_text):
                triggered.add(label)
        triggered_per_seg.append(triggered)

    layer_first_seg: dict[str, int] = {}
    for i, triggered in enumerate(triggered_per_seg):
        for label in triggered:
            if label not in layer_first_seg:
                layer_first_seg[label] = i

    layer_count = len(layer_first_seg)

    layer_scores = {0: -12, 1: -6, 2: 2, 3: 8, 4: 14, 5: 18}
    bonus = layer_scores.get(layer_count, 18)

    if layer_count >= 4:
        return bonus, [f"冲突推进{layer_count}层"]
    if layer_count == 3:
        return bonus, [f"冲突推进{layer_count}层"]
    if layer_count == 2:
        return bonus, ["冲突层次偏少"]
    if layer_count <= 1:
        return bonus, ["冲突无明显推进"]
    return bonus, []


def _score_relevancy(story: dict, theme: str | None) -> tuple[int, list[str]]:
    if not theme:
        return 0, []

    theme_chars_raw = re.findall(r"[\u4e00-\u9fff]", theme)
    theme_words: list[str] = []
    for length in (4, 3, 2):
        for i in range(len(theme_chars_raw) - length + 1):
            w = "".join(theme_chars_raw[i:i + length])
            if w not in theme_words:
                theme_words.append(w)
    if not theme_words:
        return 0, []

    core = str(story.get("conflict_core") or "")
    setting = str(story.get("setting") or "")
    lines = _dialogue_lines(story)
    first4 = "".join(lines[:4]) if len(lines) >= 4 else "".join(lines)
    check_text = core + setting + first4

    matched_long = [w for w in theme_words if len(w) >= 3 and w in check_text]
    matched_any = [w for w in theme_words if w in check_text]
    if not matched_any:
        return -30, [f"跑题：主题「{theme}」未在核心/开场中体现"]
    return 0, []


def _score_redundancy(lines: list[str]) -> tuple[int, list[str]]:
    n = len(lines)
    if n < 8:
        return 0, []

    body_end = max(4, n - 4)
    body_lines = lines[:body_end]
    if len(body_lines) < 4:
        return 0, []

    all_text = "".join(body_lines)
    word_counts = Counter(
        w for w in _CONTENT_WORD_RE.findall(all_text)
        if w not in _REDUNDANCY_STOP_WORDS
    )
    debate_words = {w for w, _ in word_counts.most_common(8)}

    max_consecutive_hits = 0
    worst_word = ""
    for i in range(len(body_lines) - 3):
        window = body_lines[i:i + 4]
        for word in debate_words:
            hit_lines = sum(1 for line in window if word in line)
            if hit_lines > max_consecutive_hits:
                max_consecutive_hits = hit_lines
                worst_word = word

    if max_consecutive_hits >= 4:
        return -10, [f"「{worst_word}」连续4句绕圈"]
    if max_consecutive_hits >= 3:
        return -5, [f"「{worst_word}」连续3句偏绕"]

    hook_hits = 0
    worst_hook = ""
    for phrase in _A_DRUDGE_PHRASES:
        n_hit = sum(1 for line in body_lines if phrase in line)
        if n_hit > hook_hits:
            hook_hits = n_hit
            worst_hook = phrase
    if hook_hits >= 5:
        return -12, [f"中段「{worst_hook}」复读拖沓"]
    if hook_hits >= 4:
        return -7, [f"中段「{worst_hook}」偏重复"]

    return 2, ["节奏紧凑"]


def _fragment_grounded_in_text(fragment: str, haystack: str, *, min_run: int = 5) -> bool:
    frag = re.sub(r"[的话呢呀嘛吧啊…\s「」『』\"'‘’：:]", "", fragment)
    hay = re.sub(r"[\s「」『』\"'‘’]", "", haystack)
    if len(frag) < min_run:
        min_run = max(3, len(frag))
    if len(frag) < 3:
        return True
    # ≥6 字引文：须连续命中，禁止靠 2 字片拼出「假出处」
    if len(frag) >= 6:
        run = min(6, len(frag))
        for i in range(len(frag) - run + 1):
            if frag[i:i + run] in hay:
                return True
        return False
    run = min(min_run, len(frag))
    for i in range(len(frag) - run + 1):
        if frag[i:i + run] in hay:
            return True
    # 短引文才允许同义改写：2 字片过半命中
    pieces = [frag[i:i + 2] for i in range(0, len(frag) - 1, 2)]
    if len(pieces) >= 3:
        hit = sum(1 for p in pieces if p in hay)
        if hit >= (len(pieces) * 2 + 2) // 3:
            return True
    return False


def _a_close_four_beat_complete(tail4: list[str]) -> bool:
    if len(tail4) < 4:
        return False
    block = "".join(tail4)
    return (
        "那不一样" in tail4[-3]
        and ("哪里不一样" in tail4[-2] or "都是听" in tail4[-2])
        and any(m in tail4[-1] for m in ("哼", "行吧", "随便", "好吧", "算了"))
    )


def _collect_humor_issues(
    lines: list[str],
    *,
    type_code: str,
    speakers: list[str] | None = None,
) -> list[str]:
    """好笑维度的硬伤（不直接改结构分，用于压低好笑分）。"""
    cons: list[str] = []
    if len(lines) < 6:
        return cons

    body = lines[:-4] if len(lines) > 4 else lines[:-1]
    tail4 = lines[-4:] if len(lines) >= 4 else lines
    body_text = "".join(body)
    tail_text = "".join(tail4)
    # A 类埋句须出灿灿之口；禁止昭昭自造「特殊情况可以」再假装引用
    quote_haystack = body_text
    if type_code == "A" and speakers and len(speakers) == len(lines):
        body_n = len(body)
        cancan = "".join(
            lines[i]
            for i in range(body_n)
            if speakers[i] == "灿灿"
        )
        if cancan.strip():
            quote_haystack = cancan

    for line in tail4:
        for m in _RE_DIRECT_QUOTE.finditer(line):
            frag = m.group(1).strip()
            if not _fragment_grounded_in_text(frag, quote_haystack):
                cons.append(f"收束引话无出处（「{frag[:12]}」）")
                return cons

    if type_code == "A":
        if ("哪里不一样" in body_text or "都是听" in body_text) and (
            "哪里不一样" in tail_text or "都是听" in tail_text
        ):
            cons.append("追问闭环模板复读")
        if "不公平" in body_text and "凭什么" not in body_text[:40]:
            cons.append("偏C式争公平口号")
    if type_code == "A" and not _a_close_four_beat_complete(tail4):
        cons.append("末四拍不完整")

    return cons


def _score_funniness(
    lines: list[str],
    *,
    type_code: str,
    humor_issues: list[str],
) -> tuple[int, list[str], list[str]]:
    """好笑维度 0–20，叠在结构分（≤80）之上。"""
    cons = list(humor_issues)
    pros: list[str] = []
    if len(lines) < 6:
        return 0, pros, cons

    if any("无出处" in c for c in cons):
        return 0, pros, cons

    body = lines[:-4] if len(lines) > 4 else lines[:-1]
    tail4 = lines[-4:] if len(lines) >= 4 else lines
    body_text = "".join(body)
    mid_text = "".join(body[: max(1, len(body) * 2 // 3)])
    full_text = "".join(lines)

    points = 0

    if _RE_HAMMER.search(mid_text):
        points += 5
        pros.append("有一锤场面")
    elif _RE_HAMMER.search(full_text):
        points += 2
        pros.append("有具体场面")

    grounded_tail = any(
        p in "".join(tail4)
        for p in ("你刚才说", "你自己说", "你不是说", "明明说", "你自己")
    )
    if grounded_tail and not any("无出处" in c for c in cons):
        points += 4
        pros.append("收束扣原话")

    if len(re.findall(r"\d+", full_text)) >= 2:
        points += 2

    if points >= 9 and not cons:
        pros.append("好笑够格")

    for c in cons:
        if "模板复读" in c:
            points = min(points, 6)
        elif "末四拍不完整" in c:
            points = min(points, 5)
        elif "偏C" in c:
            points = min(points, 8)

    points = max(0, min(20, points))
    if points >= _HUMOR_POINTS_FOR_GREAT:
        pros.append("很好笑")
    elif points >= _HUMOR_POINTS_FOR_GOOD:
        pros.append("好笑达标")

    return points, pros, cons


def score_daily_story(
    story: dict | None,
    *,
    theme: str | None = None,
) -> dict[str, Any]:
    """给故事打观感分。

    评分模型：
    - 结构分（格式、层数、收束形态、节奏）上限 80
    - 好笑维度 0–20 叠加上去；≥5 才可能到 85，≥15 才可能到 95
    """
    if not isinstance(story, dict):
        return {
            "grade": "偏弱",
            "score": 0,
            "summary": "无有效故事内容",
            "reasons": ["故事为空"],
        }

    score = 40
    pros: list[str] = []
    cons: list[str] = []

    dialogue = story.get("dialogue") if isinstance(story.get("dialogue"), list) else []
    lines = _dialogue_lines(story)
    speakers = _dialogue_speakers(story)
    last = lines[-1] if lines else ""
    tail2 = "".join(lines[-2:]) if lines else ""
    prev2 = "".join(lines[-3:-1]) if len(lines) >= 3 else "".join(lines[:-1])

    # ── 跑题：一次扣到位 ──
    rel_bonus, rel_details = _score_relevancy(story, theme)
    score += rel_bonus
    if rel_bonus < 0:
        cons.extend(rel_details)

    # ── 结构：只扣不加 ──
    if not str(story.get("conflict_core") or "").strip():
        score -= 10
        cons.append("缺 conflict_core")

    explain = str(story.get("punchline_explain") or "")
    profile = resolve_quality_profile(story)

    if not explain or not any(m in explain for m in _PUNCHLINE_TYPE_MARKERS):
        score -= 10
        cons.append("笑点解析缺类型")

    opening = story.get("discovery_opening")
    if not isinstance(opening, list) or not (1 <= len(opening) <= 2):
        score -= 5
        cons.append("缺发现开场")

    # ── 角色违规 ──
    mom_n = sum(
        1 for d in dialogue
        if isinstance(d, dict) and str(d.get("speaker") or "").strip() == "妈妈"
    )
    if mom_n >= profile.mom_lines_penalty_at:
        score -= profile.mom_lines_penalty
        cons.append(f"妈妈台词偏多（{mom_n}句）")

    if profile.penalize_mom_judge:
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

    # ── 收束硬伤 ──
    weak_hit = False
    if profile.penalize_wait_mom_end and any(m in tail2 for m in _WEAK_END_WAIT_MOM):
        score -= 25
        cons.append("收束甩给妈妈")
        weak_hit = True
    if profile.penalize_split_end and any(m in tail2 for m in _WEAK_END_SPLIT):
        score -= 20
        cons.append("收束偏和解")
        weak_hit = True
    if profile.penalize_stubborn_end and any(m in last for m in _WEAK_END_STUBBORN):
        score -= 15
        cons.append("耍赖软收")
        weak_hit = True

    limp = any(m in last for m in _LIMP_SOFT_CLOSE_MARKERS)
    punched = any(m in prev2 for m in profile.punch_before_soft_markers) or any(
        m in prev2 or m in last for m in _STRONG_END_MARKERS
    )
    if limp and not punched:
        score -= 20
        cons.append("无破功软收")
        weak_hit = True
    elif limp and punched:
        score += 7
        pros.append("先破功再软收")
    elif any(m in last for m in _STRONG_END_MARKERS):
        score += 14
        pros.append("末句有破功落点")

    layer_patterns = profile.layer_patterns()

    # ── 核心质量维度 ──
    esc_bonus, esc_details = _score_escalation(lines, layer_patterns=layer_patterns)
    score += esc_bonus
    if esc_bonus > 0:
        pros.extend(esc_details)
    elif esc_bonus < 0:
        cons.extend(esc_details)

    red_bonus, red_details = _score_redundancy(lines)
    score += red_bonus
    if red_bonus < 0:
        cons.extend(red_details)
    elif red_bonus > 0:
        pros.extend(red_details)

    punch_bonus, punch_details = score_punchline_for_profile(
        profile, lines, speakers, prev2, last,
    )
    humor_issues = _collect_humor_issues(
        lines, type_code=profile.code, speakers=speakers,
    )
    if humor_issues:
        grounded = not any("无出处" in c for c in humor_issues)
        if not grounded and punch_bonus > 8:
            punch_bonus = 8
            punch_details = [
                d for d in punch_details
                if "破功" in d or "闭环" in d
            ][:2]

    score += punch_bonus
    if punch_bonus > 0:
        pros.extend(punch_details)
    elif punch_bonus < 0:
        cons.extend(punch_details)

    structure_score = max(0, min(STRUCTURE_SCORE_CAP, score))
    humor_points, humor_pros, humor_cons = _score_funniness(
        lines,
        type_code=profile.code,
        humor_issues=humor_issues,
    )
    pros.extend(humor_pros)
    cons.extend(humor_cons)

    score = max(0, min(100, structure_score + humor_points))
    if humor_points < _HUMOR_POINTS_FOR_GOOD:
        score = min(score, STRUCTURE_SCORE_CAP)
    elif humor_points < _HUMOR_POINTS_FOR_GREAT:
        score = min(score, 94)
    if structure_score >= 70 and humor_points < _HUMOR_POINTS_FOR_GOOD:
        cons.append(
            f"格式达标但好笑不足（好笑{humor_points}/20，须≥{_HUMOR_POINTS_FOR_GOOD}才宜≥85）",
        )
    pros.append(f"结构{structure_score}")
    pros.append(f"好笑{humor_points}")
    grade = _grade_from_score(score)
    summary = _build_summary(
        pros, cons, grade, profile.summary_highlight_tokens,
    )

    return {
        "grade": grade,
        "score": score,
        "summary": summary,
        "reasons": [*pros, *cons],
    }


def _build_summary(
    pros: list[str],
    cons: list[str],
    grade: str,
    highlight_tokens: tuple[str, ...],
) -> str:
    highlights = [
        p for p in pros
        if any(k in p for k in highlight_tokens)
    ]

    if cons:
        severe = any(
            w in c
            for c in cons
            for w in (
                "甩给妈妈", "和解", "无破功", "跑题",
                "无出处", "未埋旧账", "模板", "拖沓", "好笑不足", "末四拍",
            )
        )
        if severe or grade == "偏弱":
            primary = next(
                (
                    c for c in cons
                    if any(
                        k in c
                        for k in (
                            "收束", "软收", "绕圈", "跑题", "推进",
                            "出处", "模板", "拖沓", "公平", "好笑",
                        )
                    )
                ),
                cons[0],
            )
            summary = primary
            if len(cons) > 1:
                summary += f"，另有{len(cons) - 1}项"
            return summary
        if highlights:
            parts = list(highlights)
            minor = next((c for c in cons if "绕圈" in c), None)
            if minor:
                parts.append(f"（{minor}）")
            return "，".join(parts)

    if highlights:
        return "，".join(highlights)
    if grade == "偏弱":
        return "无明显亮点"
    return "结构完整，收束一般"


def attach_daily_story_quality(
    story: dict[str, Any],
    *,
    theme: str | None = None,
) -> dict[str, Any]:
    if not isinstance(story, dict):
        return story
    story["quality"] = score_daily_story(story, theme=theme)
    return story


def build_quality_revision_hints(
    quality: dict,
    *,
    story: dict | None = None,
) -> str:
    """根据质量评分结果，生成针对性修订指令。

    返回空字符串表示无需修订（已达目标）。
    """
    reasons = quality.get("reasons", [])
    pros = [r for r in reasons if not any(
        r.startswith(w) for w in (
            "缺", "存", "妈", "无破功", "收束偏", "耍赖", "跑题",
            "收束引", "引先例收", "追问闭", "偏C", "模板", "拖沓",
        )
    )]
    cons = [r for r in reasons if r not in pros]

    hints: list[str] = []
    profile = resolve_quality_profile(story)
    esc_type_hint, close_type_hint = profile.revision_hints()

    # 冲突层次不足
    layer_info = next((r for r in pros if "推进" in r), "")
    if not layer_info or "2层" in layer_info or "偏少" in layer_info:
        hints.append(esc_type_hint)
    elif "3层" in layer_info:
        hints.append(esc_type_hint)

    # 收束质量
    has_punch_ending = closing_satisfied(pros, profile)

    if not has_punch_ending:
        hints.append(close_type_hint)

    # 绕圈
    redundancy = next((c for c in cons if "绕圈" in c), None)
    if redundancy:
        hints.append(
            f"【去绕圈】{redundancy}。删掉重复的回合，同一逻辑点最多 2 句讲完。"
            "删掉后若字数不够，在别处插入新维度的交锋补上。"
        )

    humor_issue = next(
        (
            c for c in cons
            if any(
                k in c
                for k in ("无出处", "未埋旧账", "模板", "拖沓", "公平", "好笑不足", "末四拍")
            )
        ),
        None,
    )
    if humor_issue:
        hints.append(
            f"【好笑】{humor_issue}。"
            "收束只能引用前文真实说过的话；中段用一件具体小事升级，"
            "勿复读同一句式或套「哪里不一样」模板。"
        )

    # 结构性缺失
    for c in cons:
        if "缺 conflict_core" in c:
            hints.append("【补 conflict_core】添加 ≤24 字的冲突摘要，格式'谁vs谁争什么'。")
        if "缺发现开场" in c:
            hints.append("【补开场】添加 1-2 句发现/质问开场白，点名冲突实物或动作。")

    if not hints:
        return ""

    return "\n".join(hints)
