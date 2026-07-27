"""C 类可核对事实（赛规自洽、量化口径）。"""

from __future__ import annotations

import re

from app.services.daily_story.story_types.quality import RE_BOOMERANG_RULE

_COUNT_TOKEN = re.compile(
    r"(?:一共|总共|有)?"
    r"(\d+|[一二三四五六七八九十两]+)"
    r"件",
)
_RULE_DECLARE = re.compile(
    r"(谁弄乱|谁碰|谁先|谁更急|谁叠|切的人|先选|先拿).{0,12}"
    r"(?:规矩|规则|赛规|负责|收拾|定规则|谁先)",
)
_NEW_RULE = re.compile(r"改规矩|不算|另外|重新比|再来|换一条")

_CN: dict[str, int] = {
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}


def _cn_int(tok: str) -> int | None:
    if tok.isdigit():
        return int(tok)
    if tok in _CN:
        return _CN[tok]
    if tok.startswith("十") and len(tok) == 2:
        return 10 + _CN.get(tok[1], 0)
    return None


def _dialogue_lines(story: dict) -> list[str]:
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return []
    return [
        str(d.get("line") or "").strip()
        for d in dialogue
        if isinstance(d, dict) and str(d.get("line") or "").strip()
    ]


def collect_fact_issues(story: dict) -> list[str]:
    """观感层事实硬伤（压低结构分并驱动修订）。"""
    issues: list[str] = []
    lines = _dialogue_lines(story)
    if len(lines) < 6:
        return issues

    full = "".join(lines)
    head = "".join(lines[: max(1, len(lines) * 2 // 5)])
    tail = "".join(lines[-6:])

    counts: set[int] = set()
    for m in _COUNT_TOKEN.finditer(full):
        tok = m.group(1)
        if tok.isdigit():
            counts.add(int(tok))
        else:
            n = _cn_int(tok)
            if n is not None:
                counts.add(n)
    if len(counts) >= 2 and not _NEW_RULE.search(full):
        issues.append("C事实计数口径前后不一")

    rules_head = _RULE_DECLARE.findall(head)
    rules_tail = _RULE_DECLARE.findall(tail)
    if rules_head and rules_tail:
        if set(rules_tail) != set(rules_head) and not _NEW_RULE.search(full):
            issues.append("C事实赛规改口无铺垫")

    if RE_BOOMERANG_RULE.search(tail):
        body = "".join(lines[:-4])
        tail4 = "".join(lines[-4:])
        quoted = re.findall(
            r"(?:你刚说|你说的|你不是说)(.{2,14})",
            tail4,
        )
        body_compact = re.sub(r"\s", "", body)
        for frag in quoted:
            core = re.sub(r"[的话呢呀嘛吧啊…\s「」]", "", frag)
            if len(core) < 4:
                continue
            from app.services.daily_story.story_types.c.humor import (
                ground_closing_quote,
            )

            if ground_closing_quote(core, body_compact):
                continue
            if core not in body_compact:
                issues.append("C事实回旋镖扣话无前文")
                break

    return issues


def fact_revision_hint(issue: str) -> str | None:
    if "C事实" not in issue and "可核对" not in issue:
        return None
    if "计数" in issue:
        return (
            f"【事实·C】{issue}。"
            "全剧只认一种数法；争件数须写清合并规则（外套衬衫算一件等），"
            "勿前后五件四件各说各话。"
        )
    if "赛规" in issue or "改口" in issue:
        return (
            f"【事实·C】{issue}。"
            "换赛规前须有一句不算/改规矩/重新比；"
            "末段回旋镖只扣本场已立的那条。"
        )
    if "扣话" in issue or "回旋镖" in issue:
        return (
            f"【事实·C】{issue}。"
            "要么前文埋同一句赛规，要么改末段引话为前文子串。"
        )
    return (
        f"【事实·C】{issue}。"
        "量化/赛规全文自洽，勿末段另立新规。"
    )
