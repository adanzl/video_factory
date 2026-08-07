"""B 类可核对事实（同盟分工、定量约定、惩罚落槌）。"""

from __future__ import annotations

import re

from app.services.daily_story.story_types import parse_story_type_code
from app.services.daily_story.story_types.b.humor import RE_PLAN_FAIL

RE_MOM_PUNISH = re.compile(
    r"站好|过来|罚|不许|今晚|检讨|说清楚|墙角|罚站|别想吃|偷吃|拿的什么|"
    r"调皮|捣蛋|乱来|胡闹|惹事|闹腾|顽皮|淘气",
)
RE_DOOM = re.compile(r"完蛋|完了|糟糕|死定了|藏不住")
RE_PACT_ROLE = re.compile(
    r"(我|你).{0,10}(望风|放风|盯|拆|拿|藏|下手)",
)
RE_SHARE = re.compile(
    r"一人([半一二三四五六七八两\d]+)(?:块|份|半|个)",
)
RE_TAKE_N = re.compile(
    r"(?:拿|抓|拆了?|吃了?)([半一二三四五六七八两三四五六\d]+)(?:块|份|个|片)",
)
RE_EXECUTION_ONLY_CORE = re.compile(
    r"争谁负责|谁负责望风|谁望风谁动手|谁望风|谁动手|谁下手|谁负责藏|谁来望风",
)
# 分工翻转：望风/盯门类强分工词的所有者前后不一致（2026-08-07 专家 P1）。
# 「谁望风」是 B 稿分工核心：开场昭昭望风→正文灿灿望风=分工翻转（观众出戏）。
# (?<!没) 排除甩锅句「你没望风」（那是责备，不是分工声明）；
# 只认「我/你+望风类词」的分工命令句，拧/拿/藏等执行动作可流转不查（防误伤）。
# 望风/盯门/盯门口/看门/放哨 全归同一「望风」角色——它们是同一种分工的不同说法，
# 「我望风」→「你盯着厨房门」就是翻转（稿B 型），不能因词不同漏检。
RE_WATCH_DIVISION = re.compile(r"(?<!没)(我|你)(?:的)?(望风|放风|盯门|盯门口|盯人|看门|放哨|打掩护)")


def _dialogue_blob(story: dict) -> tuple[list[str], list[str], str]:
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return [], [], ""
    lines: list[str] = []
    speakers: list[str] = []
    for d in dialogue:
        if not isinstance(d, dict):
            continue
        lines.append(str(d.get("line") or ""))
        speakers.append(str(d.get("speaker") or "").strip())
    return lines, speakers, "".join(lines)


def _is_b_story(story: dict) -> bool:
    return parse_story_type_code(
        punchline=str(story.get("punchline_explain") or ""),
    ) == "B"


def _division_flip_error(
    lines: list[str],
    speakers: list[str],
) -> str | None:
    """分工翻转：望风/盯门类词的所有者前后矛盾 → 硬卡。

    开场「昭昭拧盖/灿灿望风」→ 正文「灿灿拧盖/昭昭盯门」=分工翻转。
    只认「我/你+望风类词」的分工命令句；所有者取说话人（我）或对方（你）。
    """
    kids = [s for s in set(speakers) if s in ("昭昭", "灿灿")]
    if len(kids) < 2:
        return None
    owner: dict[str, str] = {}
    for ln, sp in zip(lines, speakers):
        if sp not in kids:
            continue
        other = [k for k in kids if k != sp][0]
        for m in RE_WATCH_DIVISION.finditer(ln):
            who = m.group(1)
            person = sp if who == "我" else other
            if "望风" in owner and owner["望风"] != person:
                return (
                    f"B类分工翻转：望风/盯门前文归{owner['望风']}，"
                    f"后文又归{person}，结盟分工定死后全文只认一套"
                )
            owner["望风"] = person
    return None


def append_b_fact_errors(story: dict, errors: list[str]) -> None:
    """生成硬卡：同盟落槌、分工翻转、可核对定量。"""
    if not _is_b_story(story):
        return
    lines, speakers, full = _dialogue_blob(story)
    if not lines:
        return
    drift = _division_flip_error(lines, speakers)
    if drift:
        errors.append(drift)

    mom_i = next(
        (i for i, sp in enumerate(speakers) if sp == "妈妈"),
        None,
    )
    if mom_i is not None:
        tail = "".join(lines[mom_i:])
        if not RE_MOM_PUNISH.search(tail):
            errors.append(
                "B类：妈妈出场后须有短惩罚令（站好/过来/今晚别想…）",
            )
        else:
            from app.services.daily_story.story_types.b.humor import (
                analyze_punish_landing,
            )

            weak, landing_tag = analyze_punish_landing(lines, speakers)
            if weak:
                errors.append(
                    "B类：惩罚令后缺落槌定格"
                    + (f"（{landing_tag}）" if landing_tag else ""),
                )

    share_m = RE_SHARE.search(full)
    if share_m:
        token = share_m.group(1)
        for take_m in RE_TAKE_N.finditer(full):
            taken = take_m.group(1)
            if token == "半" and taken in ("一", "1", "两", "2", "三", "3"):
                errors.append(
                    "B类可核对事实：约定一人一半却拿整份/多块，"
                    "须写清走样或改口",
                )
                break
            if token.isdigit() and taken.isdigit():
                if int(taken) > int(token) + 1:
                    errors.append(
                        f"B类可核对事实：约定一人{token}份，"
                        f"却出现拿{taken}份，须与走样连锁一致",
                    )
                    break


def collect_fact_issues(story: dict) -> list[str]:
    """观感层事实硬伤（压低结构分并驱动修订）。"""
    if not _is_b_story(story):
        return []
    issues: list[str] = []
    lines, speakers, full = _dialogue_blob(story)
    if len(lines) < 8:
        return issues
    core = str(story.get("conflict_core") or "").strip()

    if core and RE_EXECUTION_ONLY_CORE.search(core):
        issues.append("B conflict_core 偏局部分工，未写清联手瞒妈妈做什么")

    head = "".join(lines[:10])
    roles = RE_PACT_ROLE.findall(head)
    if len(roles) >= 2:
        verbs = {v for _, v in roles}
        if len(verbs) >= 2:
            later = "".join(lines[10:])
            swaps = sum(
                1
                for m in RE_PACT_ROLE.finditer(later)
                if m.group(2) in verbs
            )
            # 后文只要出现真实走样（连锁意外），就不是「无走样却改口」；
            # 字面「走样」常写成具体意外（掉了/洒了/卡住），勿按词穷举
            if (
                swaps >= 2
                and "都怪你" in later
                and "走样" not in later
                and not RE_PLAN_FAIL.search(later)
            ):
                issues.append("B事实分工约定后无走样却改口")

    mom_i = next(
        (i for i, sp in enumerate(speakers) if sp == "妈妈"),
        None,
    )
    if mom_i is not None:
        tail = "".join(lines[mom_i:])
        if not RE_MOM_PUNISH.search(tail):
            issues.append("B事实缺惩罚令")

    punch = str(story.get("punchline_explain") or "")
    if "罚站" in punch or "站好" in punch:
        if not RE_MOM_PUNISH.search(full):
            issues.append("B事实笑点解析与正文惩罚不符")

    if RE_SHARE.search(full) and RE_TAKE_N.search(full):
        if not RE_PACT_ROLE.search(head):
            issues.append("B事实有定量约定但未写清分工")

    return issues


def fact_revision_hint(issue: str) -> str | None:
    if "事实" not in issue and "可核对" not in issue:
        return None
    if "完蛋" in issue or "惩罚" in issue or "定格" in issue or "落槌" in issue:
        tag = ""
        if "（" in issue and "）" in issue:
            tag = issue.split("（", 1)[-1].rstrip("）")
        from app.services.daily_story.story_types.b.humor import landing_revision_hint

        return f"【事实·B】{issue}。" + landing_revision_hint(tag)
    if "定量" in issue or "一半" in issue or "份" in issue:
        return (
            f"【事实·B】{issue}。"
            "约定几人几份后，多拿须写在走样连锁里，勿前后改口无交代。"
        )
    if "conflict_core" in issue:
        return (
            f"【事实·B】{issue}。"
            "把 conflict_core 改成「姐弟联手瞒妈妈做什么，执行翻车露馅」，"
            "不要只写谁负责望风/谁动手。"
        )
    return (
        f"【事实·B】{issue}。"
        "前段分工（谁望风谁下手）写清；后文甩锅扣该分工，勿无走样改角色。"
    )
