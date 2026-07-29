"""日常故事「人读」审稿：逐句查读着出戏的硬伤。

关键词打分只认字面，抓不到「一粒米都没有」和「把剩饭倒掉了」互相打架、
「我藏车你藏零食」下一句被说反、同一质问问三遍这类问题，故加一道审读。

次数写死，无回环：
1. `collect_local_issues` 程序先查同义重复句与两字空句；
2. 审读 1 次（LLM 以读者身份逐句读）→ 结构化问题清单；
3. 定点修 1 次（只回改动行，按行号替换，说话人与行数不动）；
4. 再审读 1 次 → 剩余问题直接扣分并写进 quality，不再重生成。
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

REVIEW_KINDS: tuple[str, ...] = ("矛盾", "错位", "示范", "重复", "塑料", "其他")

# 各类硬伤扣分（读着最出戏的扣最重）
_KIND_PENALTY: dict[str, int] = {
    "矛盾": 8,
    "错位": 8,
    "示范": 10,
    "重复": 5,
    "塑料": 5,
    "其他": 3,
}
REVIEW_PENALTY_CAP = 25
REVIEW_MAX_ISSUES = 6
# 单遍审读召回不稳（同一篇稿两次结论会差），首轮取两遍并集
REVIEW_FIRST_PASSES = 2

_RE_PUNCT = re.compile(r"[，。！？…、：；~—\s·「」“”\"'?!.,]")


def _dialogue(story: dict) -> list[dict]:
    rows = story.get("dialogue")
    if not isinstance(rows, list):
        return []
    return [r for r in rows if isinstance(r, dict)]


def numbered_dialogue(story: dict) -> str:
    """给审读用的带行号台词表（行号从 1 起）。"""
    out: list[str] = []
    for i, row in enumerate(_dialogue(story), 1):
        sp = str(row.get("speaker") or "").strip()
        line = str(row.get("line") or "").strip()
        out.append(f"{i}. {sp}：{line}")
    return "\n".join(out)


def _norm(line: str) -> str:
    return _RE_PUNCT.sub("", line)


def _bigrams(text: str) -> set[str]:
    return {text[i : i + 2] for i in range(len(text) - 1)}


def _near_duplicate(a: str, b: str) -> bool:
    na, nb = _norm(a), _norm(b)
    # 下限压到 6 字：「要诚实不能说谎」只有 7 字，卡 8 字会漏掉整句复读
    if len(na) < 6 or len(nb) < 6:
        return False
    if na == nb or na in nb or nb in na:
        return True
    ga, gb = _bigrams(na), _bigrams(nb)
    if not ga or not gb:
        return False
    return len(ga & gb) / len(ga | gb) >= 0.55


def collect_local_issues(story: dict) -> list[dict[str, Any]]:
    """程序能直接判死的：同义重复句、两三字空句。"""
    rows = _dialogue(story)
    lines = [str(r.get("line") or "").strip() for r in rows]
    issues: list[dict[str, Any]] = []

    seen_pairs: set[int] = set()
    for i in range(len(lines)):
        if i in seen_pairs:
            continue
        for j in range(i + 1, len(lines)):
            if j in seen_pairs or not _near_duplicate(lines[i], lines[j]):
                continue
            seen_pairs.add(j)
            issues.append({
                "lines": [i + 1, j + 1],
                "kind": "重复",
                "desc": f"第{i + 1}句与第{j + 1}句说的是同一件事，换词重复",
                "fix": f"把第{j + 1}句改成推进新信息的话，勿复述第{i + 1}句",
            })
            break

    for i, line in enumerate(lines, 1):
        # 「怎么办！」这类三字惊慌句是有效反应，只揪「行！」级别的空应答
        if len(_norm(line)) <= 2:
            issues.append({
                "lines": [i],
                "kind": "其他",
                "desc": f"第{i}句是空应答（{line}），占行不推进",
                "fix": f"把第{i}句改成带信息的一句，或并进相邻句",
            })

    return issues


def build_review_prompts(theme: str, story: dict) -> tuple[str, str]:
    """审读提示：读者视角挑硬伤，不做风格建议。"""
    system = (
        "你是儿童短视频文案的审稿人，不是作者。"
        "你的唯一任务是像观众一样逐句读这段对白，挑出「读着出戏」的硬伤。\n"
        "只报下面 6 类，别报风格偏好、别夸、别改写全文：\n"
        "1 矛盾：前后事实打架"
        "（例：说「锅里一粒米都没有」，后面又说「你把剩饭倒掉了」）。\n"
        "2 错位：谁做什么前后对不上"
        "（例：约定「我藏车你藏零食」，下一句却说成「你塞零食我塞车」；"
        "或某人做的事后来被说成另一人做的）。\n"
        "3 示范：大人开口指导孩子去隐瞒或说谎"
        "（例：妈妈说「这事不能让奶奶知道」「别告诉爸爸」）。\n"
        "  注意：大人自己言行不一、被孩子当场抓住双标，是本片的笑点设定，"
        "不算坏示范，别报；孩子之间商量瞒着大人也是设定，别报。\n"
        "4 重复：同一件事换词说两遍以上，或同一个质问反复问。\n"
        "5 塑料：不像真人会说的话"
        "（例：被当场抓住的人不接话，张口先讲道理教育对方）。\n"
        "6 其他：上面装不下但确实读着出戏的。\n\n"
        "下面几处是本类结构设计，即使看着像重复也别报：\n"
        "- 开场两句是片头定格，与正文开头重合是正常拼接；\n"
        "- 最后一句大人认输软收，倒数第二句孩子引用大人原话闭环。\n"
        "除此之外，同一个质问被反复问、同一条规矩被说两遍，都要报。\n"
        "没问题就返回空数组，不要为凑数硬报。\n\n"
        "按三步走，别跳步：\n"
        "第一步 facts：逐条记下读到的事实——谁答应做什么（分工、约定）、"
        "出现过哪些实物状态（锅空/碗干/袋破/渣在哪）、"
        "每个人做过哪些动作。先记事实才能发现打架的地方。\n"
        "第二步 checks：上面 5 类**每一类都必须表态**，"
        "写「无」或写清哪几句有问题，不许省略某一类。\n"
        "第三步 issues：把 checks 里判「有」的逐条展开。\n\n"
        "只输出 JSON：\n"
        '{"facts":["3昭昭分工:自己藏车、灿灿藏零食","5锅里没米","6剩饭被倒掉"],'
        '"checks":{"矛盾":"第5句锅里没米，第6句又倒剩饭","错位":"无",'
        '"示范":"无","重复":"第5句与第8句都说碗干","塑料":"无"},'
        '"issues":[{"lines":[5,6],"kind":"矛盾",'
        '"desc":"第5句说锅里一粒米都没有，第6句又说把剩饭倒掉了",'
        '"fix":"第6句改成…"}]}\n'
        f"lines 用左侧行号；最多报 {REVIEW_MAX_ISSUES} 条，按严重度排序；"
        "fix 写一句具体怎么改，别写空话。"
    )
    user = (
        f"主题：{theme}\n"
        f"场景：{story.get('setting') or ''}\n"
        f"矛盾内核：{story.get('conflict_core') or ''}\n\n"
        f"对白：\n{numbered_dialogue(story)}\n\n"
        "逐句读一遍，按上面 6 类输出 JSON。"
    )
    return system, user


def parse_review_issues(raw: Any, *, line_count: int) -> list[dict[str, Any]]:
    """解析审读输出，丢掉行号越界与类型不认的条目。"""
    if not isinstance(raw, dict):
        return []
    items = raw.get("issues")
    if not isinstance(items, list):
        return []
    out: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind") or "").strip()
        if kind not in REVIEW_KINDS:
            kind = "其他"
        nos = item.get("lines")
        if isinstance(nos, int):
            nos = [nos]
        if not isinstance(nos, list):
            continue
        picked = [
            int(n)
            for n in nos
            if isinstance(n, (int, float)) and 1 <= int(n) <= line_count
        ]
        if not picked:
            continue
        desc = str(item.get("desc") or "").strip()
        if not desc:
            continue
        out.append({
            "lines": picked,
            "kind": kind,
            "desc": desc,
            "fix": str(item.get("fix") or "").strip(),
        })
        if len(out) >= REVIEW_MAX_ISSUES:
            break
    return out


def merge_issues(*groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """合并问题清单：同类且行号有交集视为同一条，避免同一处重复扣分。"""
    out: list[dict[str, Any]] = []
    for group in groups:
        for item in group:
            lines = set(item["lines"])
            for kept in out:
                if kept["kind"] == item["kind"] and lines & set(kept["lines"]):
                    kept["lines"] = sorted(set(kept["lines"]) | lines)
                    break
            else:
                out.append({**item, "lines": sorted(lines)})
    return out[:REVIEW_MAX_ISSUES]


def build_spot_fix_prompts(
    theme: str,
    story: dict,
    issues: list[dict[str, Any]],
    *,
    line_chars_max: int,
) -> tuple[str, str]:
    """定点修提示：只回被点出的那几行，行数与说话人不动。"""
    system = (
        "你是儿童短视频文案的修订者。给你一段对白和审稿人挑出的问题，"
        "只重写被点到的那几行，其余一字不动。\n"
        "硬要求：\n"
        f"- 行数不变、说话人不变、每行≤{line_chars_max}字；\n"
        "- line 只写台词本身，**不要带「昭昭：」这种说话人前缀**；\n"
        "- 只改被点到的行号，勿顺手改别处，勿新增或删除行；\n"
        "- 改完后前后事实要对得上，别再造新矛盾；\n"
        "- **末段孩子引用大人原话的闭环句与最后一句认输，一律不许改**"
        "（那是收束硬结构）；\n"
        "- 口语，像真人小孩和妈妈说话，勿写旁白与镜头描写。\n"
        "只输出 JSON：\n"
        '{"fixes":[{"no":5,"line":"改好的这一句"}]}'
    )
    issue_text = "\n".join(
        f"- 第{'、'.join(str(n) for n in it['lines'])}句"
        f"（{it['kind']}）：{it['desc']}"
        + (f" 建议：{it['fix']}" if it.get("fix") else "")
        for it in issues
    )
    user = (
        f"主题：{theme}\n"
        f"场景：{story.get('setting') or ''}\n"
        f"矛盾内核：{story.get('conflict_core') or ''}\n\n"
        f"对白：\n{numbered_dialogue(story)}\n\n"
        f"审稿人挑出的问题：\n{issue_text}\n\n"
        "只输出需要改的行（no 用左侧行号）。"
    )
    return system, user


def _strip_speaker_prefix(line: str, *, speaker: str) -> str:
    """模型爱把「昭昭：」抄进台词，带前缀会顶爆单句字数硬卡。"""
    for name in (speaker, "昭昭", "灿灿", "妈妈"):
        if name and line.startswith(name):
            return line[len(name) :].lstrip("：:").strip()
    return line


def fix_line_numbers(raw: Any) -> list[int]:
    """取出定点修想改的行号，供逐条试用。"""
    if not isinstance(raw, dict) or not isinstance(raw.get("fixes"), list):
        return []
    out: list[int] = []
    for item in raw["fixes"]:
        if not isinstance(item, dict):
            continue
        try:
            no = int(item.get("no"))
        except (TypeError, ValueError):
            continue
        if no not in out:
            out.append(no)
    return out


def apply_spot_fixes(
    story: dict,
    raw: Any,
    *,
    only: set[int] | None = None,
) -> tuple[dict, list[str]]:
    """按行号替换台词；同步 discovery_opening；返回新故事与改动说明。

    `only` 限定本次只落哪几行，用于逐条试落、避开会破硬卡的那条。
    """
    import copy

    if not isinstance(raw, dict):
        return story, []
    fixes = raw.get("fixes")
    if not isinstance(fixes, list):
        return story, []

    out = copy.deepcopy(story)
    rows = _dialogue(out)
    opening = out.get("discovery_opening")
    notes: list[str] = []
    for item in fixes:
        if not isinstance(item, dict):
            continue
        try:
            no = int(item.get("no"))
        except (TypeError, ValueError):
            continue
        new_line = _strip_speaker_prefix(
            str(item.get("line") or "").strip(),
            speaker=str(rows[no - 1].get("speaker") or "").strip()
            if 1 <= no <= len(rows)
            else "",
        )
        if not new_line or not (1 <= no <= len(rows)):
            continue
        if only is not None and no not in only:
            continue
        old_line = str(rows[no - 1].get("line") or "").strip()
        if new_line == old_line:
            continue
        rows[no - 1]["line"] = new_line
        notes.append(f"第{no}句")
        # 开场是正文前两句的副本，改了就得同步，否则拼接后自相矛盾
        if isinstance(opening, list) and no <= len(opening):
            row = opening[no - 1]
            if isinstance(row, dict) and str(row.get("line") or "").strip() == old_line:
                row["line"] = new_line
    return out, notes


def review_penalty(issues: list[dict[str, Any]]) -> tuple[int, list[str]]:
    """剩余硬伤换算扣分与 quality 里要写的原因。"""
    if not issues:
        return 0, []
    points = 0
    reasons: list[str] = []
    for item in issues:
        points += _KIND_PENALTY.get(item["kind"], _KIND_PENALTY["其他"])
        nos = "、".join(str(n) for n in item["lines"])
        reasons.append(f"审读第{nos}句{item['kind']}：{item['desc']}")
    return min(REVIEW_PENALTY_CAP, points), reasons


def apply_review_to_quality(
    story: dict,
    issues: list[dict[str, Any]],
) -> dict:
    """把审读结果落到 quality：扣分、记原因、存清单。"""
    from app.services.daily_story.quality import _grade_from_score

    quality = story.get("quality")
    if not isinstance(quality, dict):
        return story
    points, reasons = review_penalty(issues)
    quality["review_issues"] = issues
    if not points:
        return story
    score = max(0, int(quality.get("score") or 0) - points)
    quality["score"] = score
    quality["grade"] = _grade_from_score(score)
    quality["reasons"] = [*(quality.get("reasons") or []), *reasons]
    head = reasons[0]
    quality["summary"] = (
        f"{head}，另有{len(reasons) - 1}项" if len(reasons) > 1 else head
    )
    return story


def _apply_fixes_greedily(
    story: dict,
    raw_fixes: Any,
    *,
    theme: str,
) -> dict:
    """逐条试落定点修：能过硬卡的留下，会破结构的那条丢掉。

    审读只看读感，不知道各类的收束硬卡（如末段须扣原话闭环、
    说谎题须留实物反证），整批落盘常被硬卡整体打回，逐条试才留得下好的。
    """
    from app.services.daily_story.prompts import validate_daily_story_json
    from app.services.daily_story.quality import attach_daily_story_quality

    accepted: set[int] = set()
    for no in fix_line_numbers(raw_fixes):
        trial = accepted | {no}
        cand, notes = apply_spot_fixes(story, raw_fixes, only=trial)
        if not notes:
            continue
        try:
            validate_daily_story_json(cand, phase="full")
        except ValueError as exc:
            logger.info(
                "[DAILY_STORY] spot fix line %d dropped (breaks hard card): %s",
                no,
                exc,
            )
            continue
        accepted = trial

    if not accepted:
        logger.warning("[DAILY_STORY] spot fix produced nothing usable")
        return story

    fixed, notes = apply_spot_fixes(story, raw_fixes, only=accepted)
    attach_daily_story_quality(fixed, theme=theme)
    logger.info("[DAILY_STORY] spot fix applied: %s", "，".join(notes))
    return fixed


def run_daily_story_review(
    client: Any,
    theme: str,
    story: dict,
) -> dict:
    """审读→定点修→复审，全程固定次数；客户端不支持则只走程序检查。"""
    if not isinstance(story, dict) or not _dialogue(story):
        return story

    review = getattr(client, "review_daily_story_issues", None)
    spot_fix = getattr(client, "spot_fix_daily_story", None)

    # 首轮审读跑两遍取并集：单遍召回会漏，两遍能稳住明显硬伤
    issues = merge_issues(
        collect_local_issues(story),
        *(
            [review(theme, story) for _ in range(REVIEW_FIRST_PASSES)]
            if callable(review)
            else []
        ),
    )
    if not issues:
        logger.info("[DAILY_STORY] review clean, no spot fix")
        return apply_review_to_quality(story, [])

    logger.info(
        "[DAILY_STORY] review found %d issue(s): %s",
        len(issues),
        "；".join(f"{i['kind']}@{i['lines']}" for i in issues),
    )

    if callable(spot_fix):
        story = _apply_fixes_greedily(
            story,
            spot_fix(theme, story, issues),
            theme=theme,
        )

    remaining = merge_issues(
        collect_local_issues(story),
        review(theme, story) if callable(review) else [],
    )
    if remaining:
        logger.warning(
            "[DAILY_STORY] review remaining %d issue(s) after spot fix",
            len(remaining),
        )
    return apply_review_to_quality(story, remaining)
