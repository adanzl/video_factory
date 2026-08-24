"""gold_chat 金稿保真：checklist 注入 + 机审 + 精修 issue 收集。"""

from __future__ import annotations

import re
from typing import Any

# mechanism + structure 组合的扩写链（顺序不可跳步）
_MECH_STRUCTURE_CHAINS: dict[tuple[str, str], tuple[str, ...]] = {
    ("M5", "H"): (
        "升级：抢看/占物 → 拒看/推搡（object 须可拍）",
        "双向互毁：须写清谁先弄坏谁、谁报复；「也弄坏你的」须有前文",
        "伤情：story_raw 有则可拍一句（蹭破/头破/要涂碘伏）",
        "哭腔道歉：昭昭/弱势方先软",
        "M5 拒和：立规（如谁先动手谁道歉）+ 不原谅",
        "M5 加码：妈妈介入前至少 1 句仍嘴硬（道歉也没用/不原谅）",
        "H 调解①：妈妈问「谁先动手」",
        "H 调解②：定责劝和（分层，勿一句「都错了」了事）",
        "仪式性和好：拉手/勉强松口",
        "齐声承诺：以后还打不打架 → 不打了",
        "收场：story_raw 有碘伏/涂药则写；可选妈妈一句录下来/发圈",
    ),
    ("M5", "A"): (
        "立规/拒和 escalating",
        "加码：嘴硬不原谅",
        "A 末四拍或等价收束（引话/破功）",
    ),
    ("M4", "G"): (
        "互怼/数落 escalating",
        "pivot：护短/真心一句",
        "愣住 beat",
        "暖收或半暖",
    ),
}

_DEFAULT_H_CHAIN: tuple[str, ...] = (
    "冲突升级（4–8 句）",
    "僵持/拒和",
    "妈妈定责劝和（2–4 句）",
    "仪式性和好",
)

_BANNED_INVENTED_CLOSES: tuple[str, ...] = (
    "交换礼物/彩虹/酒窝/拉钩一百年",
    "站内模板暖梗（story_raw 未出现则禁）",
)

RE_RETALIATION = re.compile(r"也.*弄坏|也弄坏")
RE_PRIOR_DAMAGE = re.compile(r"弄坏|抢坏|撕坏|抓坏|画.{0,4}坏")
RE_M5_RULE = re.compile(r"谁先动手|先动手.*道歉")
RE_M5_AUTHORITY = re.compile(r"家规|规矩|说好了")
RE_STUBBORN_HARD = re.compile(r"不原谅|免谈|别理我")
RE_STUBBORN_ESCALATE = re.compile(r"道歉也没用|画了好久|很久|变回来|免谈")
RE_MOM_ASK = re.compile(r"谁先动手|谁先.*手")
RE_MOM_BALANCE = re.compile(r"不对|别抢|先推|你也|都错")
RE_ONE_SIDED = re.compile(r"弟弟都道歉|妹妹都道歉|都道歉了")
RE_RECONCILE = re.compile(r"不打了|拉手|对不起|没关系|说好了")


def fidelity_chain(
    *,
    structure_type: str,
    mechanism: str,
) -> tuple[str, ...]:
    st = str(structure_type or "").strip().upper()
    mech = str(mechanism or "").strip().upper()
    return _MECH_STRUCTURE_CHAINS.get((mech, st), _DEFAULT_H_CHAIN if st == "H" else ())


def format_story_beats(beat: list[Any] | None) -> str:
    lines: list[str] = []
    for i, item in enumerate(beat or [], start=1):
        text = str(item or "").strip()
        if text:
            lines.append(f"{i}. {text}")
    return "\n".join(lines) if lines else "（无 beat 摘要）"


def format_fidelity_block(
    *,
    structure_type: str,
    mechanism: str,
    beat: list[Any] | None,
    closing_intent: str = "",
    story_raw: str = "",
) -> str:
    """注入 gold_chat prompt：金稿关键拍 checklist。"""
    st = str(structure_type or "").strip().upper()
    mech = str(mechanism or "").strip().upper()
    chain = fidelity_chain(structure_type=st, mechanism=mech)

    parts = [
        "【金稿保真 checklist · 扩写时逐步落实，禁止跳步】",
        *([f"- {step}" for step in chain]),
    ]

    beat_text = format_story_beats(beat)
    parts.extend(
        [
            "",
            "【本稿 story beat 摘要（须在对白中体现）】",
            beat_text,
        ],
    )

    closing = str(closing_intent or "").strip()
    if closing:
        parts.extend(["", f"closing_intent（收束原意，优先于自编剧情）：{closing}"])

    raw = str(story_raw or "").strip()
    if raw:
        parts.extend(
            [
                "",
                "story_raw 对照：只取可拍现场拍，叙述/meta 可改为妈妈一句台词；",
                "勿用 story_raw 未出现的物品/仪式替换收束。",
            ],
        )

    parts.extend(
        [
            "",
            "【禁止 Invent】",
            *[f"- {x}" for x in _BANNED_INVENTED_CLOSES],
        ],
    )
    return "\n".join(parts)


def _dialogue_rows(story: dict[str, Any]) -> list[dict[str, Any]]:
    rows = story.get("dialogue")
    if not isinstance(rows, list):
        return []
    return [r for r in rows if isinstance(r, dict)]


def _issue(
    *,
    lines: list[int],
    kind: str,
    desc: str,
    fix: str,
) -> dict[str, Any]:
    return {"lines": lines, "kind": kind, "desc": desc, "fix": fix}


def _retaliation_has_prior_damage(line: str, prior_blob: str) -> bool:
    """「也弄坏」前须有弄坏/抢坏：看前文句，或同句「也弄坏」之前的半句。"""
    if RE_PRIOR_DAMAGE.search(prior_blob):
        return True
    m = RE_RETALIATION.search(line)
    if not m:
        return False
    return bool(RE_PRIOR_DAMAGE.search(line[: m.start()]))


def _append_m5_h_issues(
    rows: list[dict[str, Any]],
    issues: list[dict[str, Any]],
) -> None:
    lines = [str(r.get("line") or "").strip() for r in rows]
    speakers = [str(r.get("speaker") or "").strip() for r in rows]
    n = len(lines)
    if n < 10:
        return

    for i, line in enumerate(lines, 1):
        if RE_RETALIATION.search(line):
            prior = "".join(lines[max(0, i - 4) : i - 1])
            if not _retaliation_has_prior_damage(line, prior):
                edit_line = max(1, i - 2)
                issues.append(
                    _issue(
                        lines=[edit_line],
                        kind="保真-互毁前文",
                        desc=(
                            f"第{i}句「也弄坏」类报复，"
                            f"但第{edit_line}–{i - 1}句缺弄坏/抢坏：{line}"
                        ),
                        fix=(
                            f"改第{edit_line}句（或更早）补画被抢坏/弄坏"
                            f"（如「你把我画抢坏了」）；"
                            f"第{i}句可保留「我也弄坏你的画」，"
                            "禁止把前文合并进「也弄坏」所在句"
                        ),
                    )
                )

    for i, line in enumerate(lines, 1):
        if speakers[i - 1] in {"昭昭", "灿灿"} and RE_M5_RULE.search(line):
            if not RE_M5_AUTHORITY.search(line):
                issues.append(
                    _issue(
                        lines=[i],
                        kind="保真-M5立规",
                        desc=f"第{i}句 M5 规则引入突兀：{line}",
                        fix="用「家规就是谁先动手谁道歉」或「规矩在先」引入；"
                        "禁「妈妈说过/教过」（会撞转述 hard 卡）",
                    )
                )

    mom_indices = [i for i, sp in enumerate(speakers, 1) if sp == "妈妈"]
    if mom_indices:
        first_mom = mom_indices[0]
        pre_mom = lines[: first_mom - 1]
        pre_blob = "".join(pre_mom)
        has_hard = any(RE_STUBBORN_HARD.search(x) for x in pre_mom)
        has_escalate = any(RE_STUBBORN_ESCALATE.search(x) for x in pre_mom)
        if not (has_hard and has_escalate):
            issues.append(
                _issue(
                    lines=[first_mom],
                    kind="保真-M5加码",
                    desc="妈妈介入前缺嘴硬加码（须「不原谅」+「道歉也没用/画了好久」各至少一句）",
                    fix="在妈妈第一句前补 1 句灿灿/昭昭仍嘴硬（如「道歉也没用！我画了好久呢！」）",
                )
            )

        if not RE_MOM_ASK.search(lines[first_mom - 1]) and "别打" not in lines[first_mom - 1]:
            issues.append(
                _issue(
                    lines=[first_mom],
                    kind="保真-H调解",
                    desc=f"妈妈首句须问「谁先动手」或「别打了」：{lines[first_mom - 1]}",
                    fix="改成「别打了！谁先动手的？」",
                )
            )

        if len(mom_indices) >= 2:
            second_mom = mom_indices[1]
            mom_line = lines[second_mom - 1]
            if RE_ONE_SIDED.search(mom_line) and not RE_MOM_BALANCE.search(mom_line):
                issues.append(
                    _issue(
                        lines=[second_mom],
                        kind="保真-H定责",
                        desc=f"第{second_mom}句妈妈劝和偏一边倒：{mom_line}",
                        fix="分层定责：点出先推/别抢画，再劝处理和好的动作",
                    )
                )

    tail4 = "".join(lines[-4:])
    if not RE_RECONCILE.search(tail4):
        issues.append(
            _issue(
                lines=list(range(max(1, n - 3), n + 1)),
                kind="保真-和好",
                desc="末 4 句缺仪式性和好（拉手/不打了/对不起）",
                fix="末段补拉手或齐声「不打了」",
            )
        )


def _append_h_generic_issues(
    rows: list[dict[str, Any]],
    issues: list[dict[str, Any]],
) -> None:
    lines = [str(r.get("line") or "").strip() for r in rows]
    speakers = [str(r.get("speaker") or "").strip() for r in rows]
    n = len(lines)
    if n < 8:
        return
    mom_indices = [i for i, sp in enumerate(speakers, 1) if sp == "妈妈"]
    if not mom_indices:
        issues.append(
            _issue(
                lines=[n],
                kind="保真-H调解",
                desc="H 类须有妈妈调解台词",
                fix="补 2–4 句妈妈定责劝和",
            )
        )
    tail4 = "".join(lines[-4:])
    if not RE_RECONCILE.search(tail4):
        issues.append(
            _issue(
                lines=list(range(max(1, n - 3), n + 1)),
                kind="保真-和好",
                desc="末 4 句缺仪式性和好",
                fix="末段补拉手/不打了/对不起",
            )
        )


def collect_fidelity_issues(
    story: dict[str, Any],
    *,
    structure_type: str,
    mechanism: str,
) -> list[dict[str, Any]]:
    """保真机审：返回 polish 同构 issue 列表（抽象不变量，非逐篇剧情）。"""
    st = str(structure_type or "").strip().upper()
    mech = str(mechanism or "").strip().upper()
    rows = _dialogue_rows(story)
    if not rows:
        return []

    issues: list[dict[str, Any]] = []
    if mech == "M5" and st == "H":
        _append_m5_h_issues(rows, issues)
    elif st == "H":
        _append_h_generic_issues(rows, issues)

    # 去重：同 kind+首行号保留一条
    seen: set[tuple[str, int]] = set()
    out: list[dict[str, Any]] = []
    for item in issues:
        kind = str(item.get("kind") or "")
        line_nos = item.get("lines") or []
        key = (kind, int(line_nos[0]) if line_nos else 0)
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def format_fidelity_issues_block(issues: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for item in issues:
        nos = "、".join(str(n) for n in item.get("lines") or [])
        lines.append(
            f"- 第{nos}句 [{item.get('kind')}]: {item.get('desc')}\n"
            f"  改法：{item.get('fix')}"
        )
    return "\n".join(lines) if lines else "（无）"
