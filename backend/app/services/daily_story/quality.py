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
_PUNCH_BEFORE_SOFT_MARKERS = (
    "说晚了", "已经在了", "自相矛盾", "矛盾", "打脸",
    "那你也", "你也没", "那不算", "当然不算", "堵死",
    "戳穿", "说不通", "你让的", "重新说", "晚了",
    "改不了", "从来不", "已经.*了", "你说的", "你说过",
    "装让", "反悔", "变卦", "自己说", "自己打",
    "你自己说", "你刚说", "上次你说", "自己弄",
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

# ── 冲突升级层级检测 ──
_LAYER_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("L1_争归属", re.compile(
        r"凭什么.*拿|怎么在.*你手|我先|归谁|凭什么.*你的|你抢|"
        r"应该给我|我要.*块|我吃.*的|谁先|拿.*大|大的.*我|我大.*我吃",
    )),
    ("L2_挑战规则", re.compile(
        r"谁说的|没说过|不算|你定的|你刚说|你编的|规矩|切的人|"
        r"拿到的人|谁说|又不是你定的|规则是你|反悔|变来变去|"
        r"说话不算|凭什么.*定|你说的不算|你自己.*又说",
    )),
    ("L3_挑战权威", re.compile(
        r"凭什么你|你说了算|你又不是|你是姐姐|你凭什么|"
        r"不是.*说了算|又不是你|你定.*不算|我比你大|"
        r"大的该给|大的.*应该|大的.*给.*小|按年龄|我是姐姐",
    )),
    ("L4_新证据", re.compile(
        r"上次|之前|上一次|妈妈说过|爸爸.*说|柜子里|第二块|"
        r"还有.*块|烤箱|里面还有|等等.*说|说过什么|你再想想|"
        r"记得.*说|谁说.*洗碗|谁先.*洗碗|吃大.*洗碗|吃完.*洗碗|"
        r"上次.*分|上次.*说|上次.*梨|上次.*规则",
    )),
    ("L5_收束", re.compile(
        r"那.*你还|你还要|还是吃|我不要|我才不|你洗碗|那你吃|"
        r"说不过|反正我|就是|不管了|给你|那给你|下次.*算|"
        r"哼|算了算了|归我|归你|大的归|自相矛盾|嘴硬",
    )),
]

# ── 收束质量检测 ──
_BOOMERANG_RE = re.compile(
    r"你自己说|你说的|你承认|你刚才说|你自己.*说|"
    r"你说的.*你先.*选|你.*说.*先选|你定的.*你先",
)
_REVELATION_RE = re.compile(
    r"柜子里|第二块|还有一块|烤箱|里面还有|谁说.*洗碗|"
    r"吃完.*洗碗|吃大.*洗碗|还没.*洗|空了|坏了|掉.*地上",
)
_SURRENDER_RE = re.compile(
    r"还是.*吧|那.*吃.*的|算了.*给你|那.*给你|我不要了|"
    r"我不.*了|你吃吧|你拿.*吧|我不管|不管了|反正|"
    r"下次.*听你|这次.*听我",
)
_TWIST_SEGUE_RE = re.compile(r"等等|不对|可是|不过|等一下|你再想")

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


def _score_escalation(lines: list[str]) -> tuple[int, list[str]]:
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
        for label, pat in _LAYER_PATTERNS:
            if pat.search(seg_text):
                triggered.add(label)
        triggered_per_seg.append(triggered)

    layer_first_seg: dict[str, int] = {}
    for i, triggered in enumerate(triggered_per_seg):
        for label in triggered:
            if label not in layer_first_seg:
                layer_first_seg[label] = i

    layer_count = len(layer_first_seg)

    layer_scores = {0: -12, 1: -6, 2: 2, 3: 10, 4: 18, 5: 25}
    bonus = layer_scores.get(layer_count, 25)

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
    return 5, ["无绕圈"]


def _score_punchline_quality(
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

    first_half = "".join(lines[:n // 2])
    second_half = "".join(lines[n // 2:])
    revelations = _REVELATION_RE.findall(second_half)
    new_revelations = [r for r in revelations if r not in first_half]
    if new_revelations and any(m in tail4 for m in new_revelations):
        bonus += 10
        details.append("实物真相反转")

    if _BOOMERANG_RE.search(tail3):
        bonus += 8
        if "实物真相反转" not in details:
            details.append("回旋镖收束")

    if _SURRENDER_RE.search(tail3):
        if any(m in tail3 for m in ("洗碗", "洗", "坏了", "掉了", "空了")):
            bonus += 6
            if not details:
                details.append("困境秒怂反转")
        # 有回旋镖/戳穿垫底的不扣分，没理由的纯怂才扣
        elif not _BOOMERANG_RE.search(tail3) and not any(
            m in tail3 for m in _STRONG_END_MARKERS
        ):
            bonus -= 3

    twist_matches = _TWIST_SEGUE_RE.findall(tail3)
    if twist_matches and (_REVELATION_RE.search(tail4) or _BOOMERANG_RE.search(tail4)):
        bonus += 3

    if speakers and len(speakers) >= 2:
        last_sp = speakers[-1]
        prev_sp = speakers[-2]
        if last_sp != prev_sp and _SURRENDER_RE.search(last):
            bonus += 3

    return bonus, details


def score_daily_story(
    story: dict | None,
    *,
    theme: str | None = None,
) -> dict[str, Any]:
    """给故事打观感分。

    评分模型：
    - 基础分 40（及格线以下起步，靠质量拉分）
    - 结构项只扣不加（合规是义务，不是加分项）
    - 质量项（推进层数、收束类型、绕圈）决定最终分数
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
    if mom_n >= 3:
        score -= 10
        cons.append(f"妈妈台词偏多（{mom_n}句）")

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
    if any(m in tail2 for m in _WEAK_END_WAIT_MOM):
        score -= 25
        cons.append("收束甩给妈妈")
        weak_hit = True
    if any(m in tail2 for m in _WEAK_END_SPLIT):
        score -= 20
        cons.append("收束偏和解")
        weak_hit = True
    if any(m in last for m in _WEAK_END_STUBBORN):
        score -= 15
        cons.append("耍赖软收")
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
        score += 10
        pros.append("先破功再软收")
    elif any(m in last for m in _STRONG_END_MARKERS):
        score += 14
        pros.append("末句有破功落点")

    # ── 核心质量维度 ──
    esc_bonus, esc_details = _score_escalation(lines)
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

    punch_bonus, punch_details = _score_punchline_quality(lines, speakers, prev2, last)
    score += punch_bonus
    if punch_bonus > 0:
        pros.extend(punch_details)
    elif punch_bonus < 0:
        cons.extend(punch_details)

    score = max(0, min(100, score))
    grade = _grade_from_score(score)
    summary = _build_summary(pros, cons, grade)

    return {
        "grade": grade,
        "score": score,
        "summary": summary,
        "reasons": [*pros, *cons],
    }


def _build_summary(pros: list[str], cons: list[str], grade: str) -> str:
    highlights = [p for p in pros if "反转" in p or "回旋镖" in p or "推进" in p or "破功" in p]

    if cons:
        severe = any("甩给妈妈" in c or "和解" in c or "无破功" in c or "跑题" in c for c in cons)
        if severe or grade == "偏弱":
            primary = next(
                (c for c in cons if "收束" in c or "软收" in c or "绕圈" in c or "跑题" in c or "推进" in c),
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


def build_quality_revision_hints(quality: dict) -> str:
    """根据质量评分结果，生成针对性修订指令。

    返回空字符串表示无需修订（已达目标）。
    """
    reasons = quality.get("reasons", [])
    pros = [r for r in reasons if not any(
        r.startswith(w) for w in ("缺", "存", "妈", "无破功", "收束偏", "耍赖", "跑题")
    )]
    cons = [r for r in reasons if r not in pros]

    hints: list[str] = []

    # 冲突层次不足
    layer_info = next((r for r in pros if "推进" in r), "")
    if not layer_info or "2层" in layer_info:
        hints.append(
            "【冲突升级】当前层次偏少。在中间插入 2-4 句新维度交锋："
            "先引入第三方规则（如'妈妈说过的'/'上次你也是这样'），"
            "再让一方用字面逻辑反推对方规则，形成自相矛盾。"
        )
    elif "3层" in layer_info:
        hints.append(
            "【冲突升级】再加 1 层推进。在后半段引入一个对方没料到的新证据"
            "（如'上次你明明说过'/'妈妈定的规矩是'），"
            "用事实戳穿对方当前的规则。"
        )

    # 收束质量
    has_boomerang = any("回旋镖" in r for r in pros)
    has_revelation = any("反转" in r for r in pros)
    has_punch_ending = any("破功" in r for r in pros)

    if not has_boomerang and not has_revelation:
        hints.append(
            "【收束升级】当前收束缺乏反转感。把倒数第3-4句改为回旋镖模式："
            "用对方刚说的规则原路反问ta（如'你自己说切的人先选，那你切的你选，我拿大的就行了'），"
            "让对方陷入自相矛盾，末句ta只能嘴硬认栽。"
            "末句必须由被戳穿方说话（'……哼/……行/……随便'开头）。"
        )
    elif not has_punch_ending:
        hints.append(
            "【收束落点】末句缺乏破功感。确保末句说话人是被戳穿的一方，"
            "用'……行'/'……算了'/'……随便你'/'……哼'开头，带出嘴硬但认栽的语气。"
        )

    # 绕圈
    redundancy = next((c for c in cons if "绕圈" in c), None)
    if redundancy:
        hints.append(
            f"【去绕圈】{redundancy}。删掉重复的回合，同一逻辑点最多 2 句讲完。"
            "删掉后若字数不够，在别处插入新维度的交锋补上。"
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
