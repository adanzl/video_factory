"""D 类观感：末段 scorer 与 profile。"""

from __future__ import annotations

import re

from app.services.daily_story.story_types.d import humor as d_humor
from app.services.daily_story.story_types.d import opening as d_opening
from app.services.daily_story.story_types.d import facts as d_facts
from app.services.daily_story.story_types.quality import (
    RE_BOOMERANG_RULE,
    RE_SOFT_LAST,
    RE_SURRENDER,
    SHARED_PUNCH_SOFT,
    TypeQualityProfile,
)

RE_RULE = re.compile(
    r"不许|别碰|规矩|叮嘱|说了|不能|别浇|别多|别响|"
    r"轻轻|轻点|慢点|慢慢|轻擦|系紧|别毛|别用力|别猛",
)
RE_LITERAL = re.compile(
    r"照做|按你说的|你不是说|字面|打开|碰了|动了|"
    r"你说[^，。！？]{1,8}，?我就|我按你|你叫我|你要我|我照你",
)
RE_MESS = re.compile(
    r"掉了|滑落|滑掉|洒|弄乱|乱了|乱成|全乱|坏了|打不开|饿着|够不着|倒了|全掉|弄翻|"
    r"解不开|勒|死结|死疙瘩|大马趴|溢|变形|"
    r"流|淌|泡|淹|漫|漏|渗|满|皱|鼓|肿|挤|碎|破|断|歪|"
    r"泼|甩|滴水|滴到|滴在|湿透|水痕|水渍|水印|"
    r"[削剪切磨啃抠]没|只剩|就剩|快没了|小一圈|露出来|[削切剪磨啃]成",
)
# 与 humor.RE_FIX 同源，避免「我来解」一类破规漏认
RE_FIX = d_humor.RE_FIX

# 收束引话的 D 放宽：与 validate._cite_grounded_in_hay 对齐——3–6 字短引文
# 允许同词序调整（叠衣「叠衣服要轻点」→ 引「要轻点叠」也算忠实），
# 逐字子串/4 连字已由共享 `_fragment_grounded_in_text` 兜住。
_RE_BAG_NOISE = re.compile(r"[的话呢呀嘛吧啊…\s「」『』“”\"'‘’：:]")


def _ground_closing_quote_by_bag(frag: str, hay: str) -> bool:
    f = _RE_BAG_NOISE.sub("", frag or "")
    h = re.sub(r"[\s「」『』“”\"'‘’]", "", hay or "")
    return 3 <= len(f) <= 6 and all(
        h.count(c) >= f.count(c) for c in set(f)
    )

# D 的 +2 同位替代（避免评分只偏爱某一种笑点风味）：
#   通道A·数字具体量：≥2 句昭昭台词各含一个真实可数的数量
#      （分钟/秒/块/层/遍/次/圈、数到X；剔「一下」虚量词、不认每块/整层/半截）
#   通道B·荒诞整体执行：1 句昭昭台词把歪读产物当「整体」搬运/处理
#      （整座端进箱、连塔一起端、两手托住底座端）
#   任一通道满足即 +2，不叠加。
_RE_NUM_DURATION = re.compile(r"(?:\d+|[一二三四五六七八九十两]+)(?:分钟|秒)")
_RE_NUM_COUNT = re.compile(r"数到\s*[一二三四五六七八九十\d]+")
_RE_NUM_ITEM = re.compile(r"[一二三四五六七八九十两\d]+(?:块|层|遍|次|圈)")
_RE_CLIMAX_WHOLE = re.compile(
    r"(?:整座|整个|整根|一整|连[^，。！？]{0,3}(?:一起|一块))"
    r"[^，。！？]{0,6}(?:端|抬|搬|挪|托|抱|扛|举|捧|放|进)|"
    r"(?:双手|两手|托住|抱住)[^，。！？]{0,8}(?:整座|整个|整根|端|抬|搬|挪)",
)


def score_specificity_bonus(
    lines: list[str],
    speakers: list[str] | None,
) -> int:
    """D：数字具体量 OR 荒诞整体执行，任一风味即给 +2（同位替代，不叠加）。"""
    if not speakers:
        return 0
    zz = [ln for ln, sp in zip(lines, speakers) if sp == "昭昭"]
    if any(_RE_CLIMAX_WHOLE.search(ln) for ln in zz):
        return 2
    num_lines = {
        ln
        for ln in zz
        if (
            _RE_NUM_DURATION.search(ln)
            or _RE_NUM_COUNT.search(ln)
            or _RE_NUM_ITEM.search(ln)
        )
    }
    return 2 if len(num_lines) >= 2 else 0


def score_scene_beat(
    lines: list[str],
    *,
    text_has_hammer_beat,
) -> tuple[int, list[str]]:
    """D 的一锤优先认「歪读可拍画面」，其次才是倒/洒。"""
    _ = text_has_hammer_beat
    text = "".join(lines)
    if d_humor.RE_TWIST_VISUAL.search(text) and RE_MESS.search(text):
        return 5, ["有字面歪读一锤"]
    if d_humor.RE_TWIST_VISUAL.search(text):
        return 4, ["有字面歪读场面"]
    if RE_MESS.search(text):
        return 2, ["有后果场面"]
    return 0, []


def score_funniness_tail(
    lines: list[str],
    speakers: list[str] | None = None,
) -> tuple[int, list[str]]:
    """D 收束三拍好笑独立加分：破规具体 → 回旋镖点破 → 末句破功。

    与 score_punchline 互补：punchline 侧重结构完整性，
    本函数侧重尾段好笑密度（末四拍的画面/语感）。
    """
    _ = speakers
    n = len(lines)
    if n < 4:
        return 0, []

    tail4 = "".join(lines[-4:])
    tail3 = "".join(lines[-3:])
    late = "".join(lines[max(0, n - 8):])
    points = 0
    pros: list[str] = []

    # 破规具体（指甲抠/赶紧解开→动作词+破规意图）
    if RE_FIX.search(late):
        points += 3
        pros.append("破规具体好笑")

    # 回旋镖点破（「怎么现在又上手来解了」）
    if RE_BOOMERANG_RULE.search(tail4):
        points += 4
        pros.append("回旋镖点破好笑")

    # 末句破功（哼/算了/随便）
    last = lines[-1] if n >= 1 else ""
    if RE_SOFT_LAST.search(last):
        points += 2
        pros.append("末句破功好笑")

    # 字面执行走样的视觉好笑（塔倒/水溢）
    if d_humor.RE_TWIST_VISUAL.search(late) and RE_MESS.search(late):
        points += 2
        pros.append("字面歪读收束好笑")

    return points, pros


def score_punchline(
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
    # 后果/字面可在全文，破规+回旋镖看后段
    full = "".join(lines)
    late = "".join(lines[max(0, n - 8) :])
    bonus = 0
    details: list[str] = []

    if RE_MESS.search(full) and RE_LITERAL.search(full):
        bonus += 8
        details.append("字面后果落地")

    if RE_FIX.search(late) and RE_BOOMERANG_RULE.search(late):
        bonus += 10
        details.append("叮嘱方破规回旋镖")

    if RE_BOOMERANG_RULE.search(tail3) and RE_RULE.search(prev2 + full[:80]):
        bonus += 6
        if not details:
            details.append("字面回旋镖收束")

    if RE_SOFT_LAST.search(last) and RE_BOOMERANG_RULE.search(prev2):
        bonus += 4
        details.append("末句叮嘱方破功")
    elif RE_SOFT_LAST.search(last):
        bonus += 2
        details.append("末句叮嘱方破功")
    # 哼不在末句 = 收束没落地，不加分

    if RE_SURRENDER.search(tail3) and not details:
        bonus -= 3

    return bonus, details


def _d_revision_hint(issue: str) -> str | None:
    from app.services.daily_story.story_types.d.humor import humor_revision_hint
    from app.services.daily_story.story_types.d.opening import opening_revision_hint

    return humor_revision_hint(issue) or opening_revision_hint(issue)


QUALITY_PROFILE = TypeQualityProfile(
    code="D",
    score_punchline=score_punchline,
    closing_pro_markers=("回旋镖", "破功", "字面", "破规", "后果"),
    summary_highlight_tokens=(
        "回旋镖",
        "推进",
        "破功",
        "字面",
        "后果",
    ),
    punch_before_soft_markers=SHARED_PUNCH_SOFT
    + (
        "你自己说",
        "你刚才",
        "你自己刚才",
        "自己刚才说",
        "你现在也",
        # 变体回旋镖：浇花类主题「你说别太多，我就把整壶水都倒完」
        # （只认尾段位置——先破功再软收只看倒数第 2、3 句，中段字面执行句不会落这里）
        "你说别",
    ),
    collect_humor_issues=d_humor.collect_humor_issues,
    collect_fact_issues=d_facts.collect_fact_issues,
    score_opening_quality=d_opening.score_opening_quality,
    score_scene_beat=score_scene_beat,
    score_funniness_tail=score_funniness_tail,
    score_specificity_bonus=score_specificity_bonus,
    humor_issue_caps=d_humor.HUMOR_ISSUE_CAPS,
    humor_revision_hint=_d_revision_hint,
    closing_quote_haystack=d_humor.closing_quote_haystack,
    ground_closing_quote=_ground_closing_quote_by_bag,
    stop_on_ungrounded_quote=True,
)
