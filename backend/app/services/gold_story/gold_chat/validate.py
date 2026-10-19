"""gold_chat 类型对齐：checklist 注入 + 机审 + 精修 issue 收集。"""

from __future__ import annotations

import re
from typing import Any


def align_chain(
    *,
    structure_type: str,
    mechanism: str,
    closing_mode: str = "",
    k_close_mode: str = "",
) -> tuple[str, ...]:
    from app.services.gold_story.gold_chat.type_bridge import (
        type_align_chain,
    )

    return type_align_chain(
        structure_type=structure_type,
        mechanism=mechanism,
        closing_mode=closing_mode,
        k_close_mode=k_close_mode,
    )


_BANNED_INVENTED_CLOSES: tuple[str, ...] = (
    "交换礼物/彩虹/酒窝/拉钩一百年",
    "站内模板暖梗（story_raw 未出现则禁）",
)

RE_RETALIATION = re.compile(
    r"也.*(?:弄坏|撕|毁|抢坏)|也(?:弄坏|撕|毁)|还.*(?:弄坏|撕|毁)"
)
RE_RETALIATION_THREAT = re.compile(r"(?:那我也|我也要|还.*)(?:撕|弄坏)")
RE_RETALIATION_INTENT = re.compile(r"(?:那我也|我也要|要|敢).*(?:撕|弄坏)")
RE_RETALIATION_DONE = re.compile(r"撕啦|撕破|撕开|弄坏了|抢你画撕|抢过.*撕|也抢.*撕啦")
RE_OTHER_DAMAGED_SELF = re.compile(r"你.{0,12}(弄坏|弄花|撕|抢坏|毁).*(我的|我)")
RE_PRIOR_DAMAGE = re.compile(r"弄坏|弄花|抢坏|撕坏|撕破|撕了|抓坏|毁|涂坏|.{0,2}坏|撕啦|撕开")
RE_DAMAGE_DONE = re.compile(r"撕了|撕破|撕开|撕啦|弄坏了|弄花了|抓坏了|撕一道")
RE_YOUR_OBJ = re.compile(r"你的.{1,4}")
RE_M5_RULE = re.compile(r"谁先动手|先动手.*道歉")
RE_M5_AUTHORITY = re.compile(r"家规|规矩|规定|说好了")
RE_M5_STUBBORN = re.compile(r"不原谅|免谈|别理我|别想")
RE_M5_ESCALATE = re.compile(r"道歉也没用|画了好久|弄了好久|很久|变回来|辛苦|没那么容易")
RE_MOM_ASK = re.compile(r"谁先动手|谁先.*手")
RE_MOM_BALANCE = re.compile(r"不对|别抢|先推|先动手|你也|都错")
RE_MOM_SOFT = re.compile(r"扯平|各打|算了就好|一笔勾销|都有不对|都有错")
RE_ONE_SIDED = re.compile(
    r"弟弟都道歉|妹妹都道歉|都道歉了|先道歉了.*原谅|原谅他吧|原谅昭昭|原谅灿灿"
)
RE_RECONCILE = re.compile(r"不打了|拉手|对不起|没关系|说好了")
RE_CLOSING_INVENT = re.compile(r"帮|扶|递|棉签|送去|一起|回来|不疼了|快点|等你")
RE_FIGHT_QUESTION = re.compile(r"还打不打架|还打不打|说以后不打架|以后不打架")
RE_IODINE_CLOSE = re.compile(r"碘伏|涂药|涂点药|消消毒")
RE_INJURY = re.compile(r"额|头|蹭|破|磕|撞|疼|痛|血")
RE_IODINE_INVENT = re.compile(r"录|朋友圈|发圈|拍视频|录像")
RE_POST_CLOSE_INVENT = re.compile(
    r"你画|我画|一起|桥墩|桥面|画桥|画墩|以后不撕|不撕你"
)
RE_BROKEN_LINE = re.compile(r"^[，,、…]")
RE_M5_APOLOGY = re.compile(r"对不起|我先推|我错了|不是故意|真的错了")
RE_OBJECT_HOLDER = re.compile(r"也有你的|有你的|拿着你的|拿了你的|我有你的")
RE_OBJECT_CREATE = re.compile(r"你在画|你画[^坏抢]|你写|你搭|你拼|你的.{1,4}在")
RE_AGGRESSIVE_DAMAGE = re.compile(r"撕|弄坏|弄花|抢坏|毁|抓坏|涂坏")
RE_DAMAGE_THREAT = re.compile(r"再.*就.*撕|再抢.*撕|敢.*撕|要不.*撕|否则.*撕")
RE_BEAT_INITIATOR = re.compile(r"抢|看|瞅|占")
RE_BEAT_DEFENDER = re.compile(r"拒看|拒绝|secret|秘密|不行|威胁", re.IGNORECASE)
RE_PAD_FILLER_TAIL = re.compile(r"(?:好不好呀|好不好|了呢呀|了呀呢)$")
# 本地扩写/插句灌尾巴：人读硬伤（不限 B/F）
RE_EXPAND_CLUTTER = re.compile(
    r"你给我听好了|这回算清楚|别再装傻|我可记住了|说了就不改|"
    r"再闹我可恼了|少废话听我的|你少来这套|我说怎样就怎样"
)

# closing_intent 常见收场词；未出现则末段禁对应 invent 动作
_CLOSING_INVENT_ALLOW = re.compile(r"帮|扶|递|棉签|送去|一起|回来|不疼了|快点|等你")

# 结构性问题：精修 定点修易打补丁，应打回扩写重生
# 「对齐-类型契约」留给精修 定点补槽，不进此集合
STRUCTURAL_ALIGN_KINDS: frozenset[str] = frozenset(
    {
        "保真-互毁前文",
        "保真-互毁对象",
        "保真-对象持有补丁",
        "保真-M5拒和speaker",
        "保真-发起方倒置",
        "保真-垫字过密",
        "保真-seed角色",
        "保真-N家长追问拍",
        "保真-N收束归属",
        "保真-N机制词槽",
        "保真-角色表外台词",
        "保真-孩子连说",
        "保真-关键追问归属",
        "保真-N词槽语法",
        "保真-纯动作台词",
    }
)

# warn：不阻塞导出，可进 quality / 人工复核
ALIGN_WARN_KINDS: frozenset[str] = frozenset(
    {
        "保真-M5合并",
        "保真-收场Invent",
        "保真-互毁动作",
    }
)


def is_structural_align_kind(kind: str) -> bool:
    return str(kind or "").strip() in STRUCTURAL_ALIGN_KINDS


def is_align_warn_kind(kind: str) -> bool:
    return str(kind or "").strip() in ALIGN_WARN_KINDS


def split_align_issues(
    issues: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """blocking 未通过则 fail；warn 仅记录，不阻塞导出。"""
    blocking: list[dict[str, Any]] = []
    warn: list[dict[str, Any]] = []
    for item in issues:
        kind = str(item.get("kind") or "")
        if is_align_warn_kind(kind):
            warn.append(item)
        else:
            blocking.append(item)
    return blocking, warn


def should_reexpand(issues: list[dict[str, Any]]) -> bool:
    """仅结构性 issue → 打回扩写；M5 立规/合并等局部问题留给精修。"""
    if not issues:
        return False
    kinds = {str(x.get("kind") or "") for x in issues}
    return bool(kinds & STRUCTURAL_ALIGN_KINDS)


def _sibling_partner(name: str) -> str:
    return "昭昭" if str(name or "").strip() == "灿灿" else "灿灿"


def validate_contract_role_consistency(
    scene_contract: dict[str, Any] | None,
    *,
    conflict_core: str = "",
) -> list[str]:
    """scene_contract 内 conflict / beat_chain / conflict_core 角色分工一致。"""
    sc = scene_contract if isinstance(scene_contract, dict) else {}
    victim = _parse_conflict_victim(str(sc.get("conflict") or ""))
    if not victim:
        return []
    aggressor = _sibling_partner(victim)
    errors: list[str] = []
    core = str(conflict_core or "")
    if victim == "灿灿" and re.search(r"灿灿.{0,8}(抢看|秘密)", core):
        errors.append("conflict_core:灿灿不应为抢看/守秘密方")
    if victim == "昭昭" and re.search(r"昭昭.{0,8}(抢看|秘密)", core):
        errors.append("conflict_core:昭昭不应为抢看/守秘密方")
    chain = sc.get("beat_chain") or []
    if isinstance(chain, list) and chain:
        b0 = chain[0] if isinstance(chain[0], dict) else {}
        sp0 = str(b0.get("speaker") or "").strip()
        intent0 = str(b0.get("intent") or b0.get("beat") or "")
        if sp0 and sp0 != victim:
            errors.append(f"beat_chain[0]_speaker_should_be_{victim}")
        if re.search(r"抢看|秘密", intent0):
            errors.append("beat_chain[0]_forbidden_secret_or_grab")
        for i, row in enumerate(chain):
            if not isinstance(row, dict):
                continue
            intent = str(row.get("intent") or row.get("beat") or "")
            if re.search(r"秘密", intent):
                errors.append(f"beat_chain[{i}]_forbidden_secret")
            sp = str(row.get("speaker") or "").strip()
            if i == 1 and sp and sp != aggressor:
                if re.search(r"捣乱|毁|弄坏|抢", intent):
                    errors.append(f"beat_chain[1]_aggressor_should_be_{aggressor}")
    return errors


def repair_m5_h_conflict_core(
    conflict_core: str,
    scene_contract: dict[str, Any] | None,
) -> tuple[str, bool]:
    """conflict_core 与 scene conflict 受害方对齐（如「灿灿抢看」→「昭昭弄画」）。"""
    sc = scene_contract if isinstance(scene_contract, dict) else {}
    victim = _parse_conflict_victim(str(sc.get("conflict") or ""))
    core = str(conflict_core or "").strip()
    if not victim or not core:
        return conflict_core, False
    aggressor = _sibling_partner(victim)
    if victim == "灿灿" and re.search(r"灿灿.{0,12}(抢看|秘密)", core):
        fixed = re.sub(
            r"灿灿抢看昭昭秘密画",
            "昭昭弄坏灿灿的画",
            core,
        )
        if fixed == core:
            fixed = re.sub(
                r"灿灿.{0,8}抢看.{0,8}昭昭",
                f"{aggressor}弄坏{victim}的画",
                core,
            )
        if fixed != core:
            return fixed, True
    if victim == "昭昭" and re.search(r"昭昭.{0,12}(抢看|秘密)", core):
        fixed = re.sub(
            r"昭昭抢看灿灿秘密画",
            "灿灿弄坏昭昭的画",
            core,
        )
        if fixed != core:
            return fixed, True
    return conflict_core, False


def repair_m5_h_scene_contract(
    scene_contract: dict[str, Any] | None,
    *,
    conflict_core: str = "",
) -> tuple[dict[str, Any], bool]:
    """beat_chain 与 conflict 受害方/先动手方对齐，去掉「秘密画」偏题 beat。"""
    import copy

    sc = scene_contract if isinstance(scene_contract, dict) else {}
    if not sc:
        return sc, False
    errors = validate_contract_role_consistency(sc, conflict_core=conflict_core)
    if not errors:
        return sc, False

    victim = _parse_conflict_victim(str(sc.get("conflict") or ""))
    if not victim:
        return sc, False
    aggressor = _sibling_partner(victim)
    out = copy.deepcopy(sc)
    chain = out.get("beat_chain") or []
    if not isinstance(chain, list) or not chain:
        return sc, False

    changed = False
    b0 = dict(chain[0]) if isinstance(chain[0], dict) else {}
    intent0 = str(b0.get("intent") or b0.get("beat") or "")
    if str(b0.get("speaker") or "").strip() != victim or re.search(
        r"抢看|秘密", intent0
    ):
        b0["speaker"] = victim
        b0["intent"] = f"创作展示：{victim}专心画画"
        chain[0] = b0
        changed = True

    if len(chain) > 1:
        b1 = dict(chain[1]) if isinstance(chain[1], dict) else {}
        intent1 = str(b1.get("intent") or b1.get("beat") or "")
        if str(b1.get("speaker") or "").strip() != aggressor or re.search(
            r"秘密|拒看", intent1
        ):
            b1["speaker"] = aggressor
            b1["intent"] = f"捣乱毁画：弄坏{victim}的画"
            chain[1] = b1
            changed = True

    for i, row in enumerate(chain):
        if not isinstance(row, dict):
            continue
        intent = str(row.get("intent") or row.get("beat") or "")
        if not re.search(r"秘密", intent):
            continue
        patched = dict(row)
        patched["intent"] = re.sub(r"秘密", "画", intent)
        patched["intent"] = re.sub(r"拒看/推搡", "捣乱毁画", patched["intent"])
        chain[i] = patched
        changed = True

    out["beat_chain"] = chain
    return out, changed


def _parse_fight_question_asker(closing_intent: str) -> str | None:
    """closing_intent「灿灿问/总结…还打不打架」→ 指定问句 speaker。"""
    raw = str(closing_intent or "").strip()
    if not raw or "还打" not in raw:
        return None
    m = re.search(r"(昭昭|灿灿).{0,6}(?:问|总结|说|开口)", raw)
    if m:
        return str(m.group(1))
    return None


def _iodine_close_line_index(lines: list[str]) -> int:
    """妈妈碘伏/涂药收场句（1-based），无则 0。"""
    for i, line in enumerate(lines, 1):
        if RE_IODINE_CLOSE.search(line):
            return i
    return 0


def _append_closing_tail_issues(
    lines: list[str],
    speakers: list[str],
    issues: list[dict[str, Any]],
    *,
    closing_intent: str = "",
) -> None:
    """碘伏收场后禁拖句 invent；齐声问句须由 closing_intent 指定角色。"""
    n = len(lines)
    if n < 8:
        return
    asker = _parse_fight_question_asker(closing_intent)
    seen_fight_q = False
    for i, (sp, line) in enumerate(zip(speakers, lines), 1):
        if RE_BROKEN_LINE.search(line):
            issues.append(
                _issue(
                    lines=[i],
                    kind="保真-收场拖句",
                    desc=f"第{i}句残句（句首标点/缺主语）：{line}",
                    fix="删句或改完整口语句；勿句首逗号",
                )
            )
        if RE_FIGHT_QUESTION.search(line):
            if asker and sp != asker:
                issues.append(
                    _issue(
                        lines=[i],
                        kind="保真-齐声问句",
                        desc=(
                            f"第{i}句「还打不打架」须由 closing_intent "
                            f"指定角色 {asker} 说出，当前为 {sp}：{line}"
                        ),
                        fix=f"改 speaker={asker} 问，或删重复问句",
                    )
                )
            if seen_fight_q:
                issues.append(
                    _issue(
                        lines=[i],
                        kind="保真-齐声问句",
                        desc=f"第{i}句重复「还打不打架」问句：{line}",
                        fix="只保留一处问句，齐声「不打了」即可",
                    )
                )
            seen_fight_q = True

    if asker and RE_FIGHT_QUESTION.search(closing_intent or "") and not seen_fight_q:
        issues.append(
            _issue(
                lines=[n],
                kind="保真-齐声问句",
                desc="closing_intent 要求「还打不打架」齐声收场，正文缺问句",
                fix=(
                    f"{asker} 问「以后还打不打架？」后"
                    "姐弟各一句「不打了」"
                ),
            )
        )

    if asker and seen_fight_q:
        fight_idx = next(
            (i for i, line in enumerate(lines, 1) if RE_FIGHT_QUESTION.search(line)),
            0,
        )
        if fight_idx > 0:
            kid_bukeda = [
                i
                for i in range(fight_idx + 1, n + 1)
                if speakers[i - 1] in {"昭昭", "灿灿"}
                and "不打了" in lines[i - 1]
            ]
            if len(kid_bukeda) < 2:
                issues.append(
                    _issue(
                        lines=[fight_idx + 1],
                        kind="保真-齐声问句",
                        desc="「还打不打架」后须姐弟齐声各一句「不打了」",
                        fix="问句后补另一 sibling「不打了」；灿灿可写「不打了！这还差不多。」",
                    )
                )

    iodine_idx = _iodine_close_line_index(lines)
    if iodine_idx <= 0:
        return
    for i in range(iodine_idx + 1, n + 1):
        line = lines[i - 1]
        sp = speakers[i - 1]
        if sp == "妈妈":
            continue
        if RE_POST_CLOSE_INVENT.search(line) or (
            RE_CLOSING_INVENT.search(line) and not RE_RECONCILE.search(line)
        ):
            issues.append(
                _issue(
                    lines=[i],
                    kind="保真-收场拖句",
                    desc=(
                        f"第{i}句碘伏收场（第{iodine_idx}句）后"
                        f"新增 closing 未要求的续写：{line}"
                    ),
                    fix="删碘伏后拖句；收场止于涂碘伏或短应答（嗯/好）",
                )
            )


def expand_align_score(
    story: dict[str, Any],
    *,
    structure_type: str,
    mechanism: str,
    closing_intent: str = "",
    beat_chain: list[Any] | None = None,
    conflict_text: str = "",
    dialogue_seed: list[Any] | None = None,
    beat: list[Any] | None = None,
    object_text: str = "",
    mechanism_text: str = "",
) -> tuple[int, int]:
    """预选扩写候选：(结构性 issue 数, 总 issue 数)，越小越好。"""
    issues = collect_align_issues(
        story,
        structure_type=structure_type,
        mechanism=mechanism,
        closing_intent=closing_intent,
        beat_chain=beat_chain,
        conflict_text=conflict_text,
        dialogue_seed=dialogue_seed,
        beat=beat,
        object_text=object_text,
        mechanism_text=mechanism_text,
    )
    structural = sum(
        1 for x in issues if is_structural_align_kind(str(x.get("kind") or ""))
    )
    return structural, len(issues)


def _append_m5_denial_speaker_issues(
    lines: list[str],
    speakers: list[str],
    issues: list[dict[str, Any]],
    *,
    pre_mom_end: int,
) -> None:
    """若已有服软/道歉句：拒和/加码须由另一方说（不与服软方同 speaker）。"""
    apology_speakers: set[str] = set()
    for i in range(1, pre_mom_end):
        sp = speakers[i - 1]
        if sp not in {"昭昭", "灿灿"}:
            continue
        if RE_M5_APOLOGY.search(lines[i - 1]):
            apology_speakers.add(sp)

    for i in range(1, pre_mom_end):
        line = lines[i - 1]
        sp = speakers[i - 1]
        if sp not in {"昭昭", "灿灿"} or sp not in apology_speakers:
            continue
        if RE_M5_STUBBORN.search(line) or RE_M5_ESCALATE.search(line):
            issues.append(
                _issue(
                    lines=[i],
                    kind="保真-M5拒和speaker",
                    desc=(
                        f"第{i}句 M5 拒和/加码与服软/道歉同 speaker（{sp}）：{line}"
                    ),
                    fix="拒和/加码改由另一方说；服软句保留在原 speaker",
                )
            )





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
    """「也弄坏」前须有破坏/损坏：看前文句，或同句「也/还」之前的半句。"""
    if RE_PRIOR_DAMAGE.search(prior_blob):
        return True
    m = RE_RETALIATION.search(line)
    if not m:
        return False
    return bool(RE_PRIOR_DAMAGE.search(line[: m.start()]))


def _other_damaged_self_prior(
    speaker: str,
    line: str,
    prior_pairs: list[tuple[str, str]],
) -> bool:
    """「也/还+破坏+你的」前，须另一 sibling 先实质破坏本 speaker 侧物。"""
    sp = str(speaker or "").strip()
    if sp not in {"昭昭", "灿灿"}:
        return True
    other = _sibling_partner(sp)
    m_ret = RE_RETALIATION.search(line)
    if m_ret:
        before = line[: m_ret.start()]
        if not _is_damage_threat_only(before) and RE_OTHER_DAMAGED_SELF.search(before):
            return True
    for prior_sp, pline in prior_pairs:
        if prior_sp != other:
            continue
        if _is_damage_threat_only(pline):
            continue
        if RE_AGGRESSIVE_DAMAGE.search(pline):
            return True
    return False


def _reciprocal_objects_established(prior_lines: list[str]) -> bool:
    """前文已写双方各有作品/物品（排除持有补丁句）。"""
    clean = "".join(
        ln
        for ln in prior_lines
        if not (RE_OBJECT_HOLDER.search(ln) and RE_YOUR_OBJ.search(ln))
    )
    if RE_YOUR_OBJ.search(clean):
        return True
    if re.search(r"我.{0,2}画", clean) and re.search(
        r"你的.{0,4}画|你也在画|你画.{0,4}呢|你画.{0,4}！",
        clean,
    ):
        return True
    return False


def _your_object_independently_established(prior_lines: list[str]) -> bool:
    """「你的X」须由独立前文创作/在场句 establish，不能仅靠持有补丁句。"""
    for line in prior_lines:
        if RE_OBJECT_HOLDER.search(line) and RE_YOUR_OBJ.search(line):
            continue
        if RE_YOUR_OBJ.search(line):
            return True
        if RE_OBJECT_CREATE.search(line):
            return True
    return False


def _prior_has_holder_only_patch(prior_lines: list[str]) -> bool:
    recent = prior_lines[-3:] if prior_lines else []
    return any(
        RE_OBJECT_HOLDER.search(line) and RE_YOUR_OBJ.search(line) for line in recent
    )


def _your_object_established(line: str, prior_lines: list[str]) -> bool:
    """报复句含「你的XX」时，前文或同句前半须 establish 对方也有该物。"""
    if not RE_RETALIATION.search(line) or "你的" not in line:
        return True
    m_ret = RE_RETALIATION.search(line)
    before = line[: m_ret.start()] if m_ret else ""
    if _your_object_independently_established(prior_lines):
        return True
    if _prior_has_holder_only_patch(prior_lines):
        return False
    if _reciprocal_objects_established(prior_lines):
        return True
    if RE_PRIOR_DAMAGE.search(before) and RE_YOUR_OBJ.search(line[m_ret.end() :]):  # type: ignore[union-attr]
        return True
    return False


def _m5_phrase_hits(line: str) -> int:
    hits = 0
    if RE_M5_AUTHORITY.search(line) or RE_M5_RULE.search(line):
        hits += 1
    if RE_M5_STUBBORN.search(line):
        hits += 1
    if RE_M5_ESCALATE.search(line):
        hits += 1
    return hits


def _is_damage_threat_only(line: str) -> bool:
    """条件/口头威胁（「再抢我就撕了」）不算已发生的破坏。"""
    raw = str(line or "").strip()
    if not raw or not RE_AGGRESSIVE_DAMAGE.search(raw):
        return False
    return bool(RE_DAMAGE_THREAT.search(raw))


def _retaliation_missing_action(line: str, following: list[str]) -> bool:
    """受害方报复句仅有口头威胁、缺当场撕/弄坏动作。"""
    raw = str(line or "").strip()
    if not raw:
        return False
    is_retaliation = bool(
        RE_RETALIATION.search(raw)
        or RE_RETALIATION_THREAT.search(raw)
        or RE_RETALIATION_INTENT.search(raw)
    )
    if not is_retaliation:
        return False
    blob = raw + "".join(str(x or "") for x in following[:2])
    if RE_RETALIATION_DONE.search(blob):
        return False
    if re.search(r"(?:要|也要|敢).*(?:撕|弄坏)", raw):
        return True
    if re.search(r"撕你的|撕了你|弄坏你的", raw):
        return True
    return not RE_DAMAGE_DONE.search(raw)


def _parse_conflict_victim(text: str) -> str | None:
    """scene conflict「X：…弄坏我的…」→ 受害方 X。"""
    raw = str(text or "").strip()
    if not raw:
        return None
    m = re.match(
        r"^(?P<sp>昭昭|灿灿)[：:].*(弄坏|抢坏|撕|毁).*(我的|我)",
        raw,
    )
    if m:
        return str(m.group("sp"))
    return None


def _normalize_sibling_alias(name: str) -> str | None:
    """站外称谓 → 站内姐弟名；未知返回 None。"""
    raw = str(name or "").strip()
    if raw in {"昭昭", "灿灿"}:
        return raw
    if raw in {"妹妹", "弟弟", "弟"}:
        return "昭昭"
    if raw in {"姐姐", "哥哥", "姐"}:
        return "灿灿"
    return None


def _parse_conflict_propaganda_roles(
    text: str,
) -> tuple[str, str] | None:
    """分数宣传冲突 → (宣传方, 受害方)。

    抽象模式：X 到处说/宣扬 Y 考了低分；Y 可为姐姐/灿灿等称谓。
    """
    raw = str(text or "").strip()
    if not raw:
        return None
    if not re.search(r"宣扬|宣传|到处说", raw):
        return None
    m = re.search(
        r"(?P<a>昭昭|灿灿|妹妹|弟弟|姐姐|哥哥).{0,12}"
        r"(?:到处说|宣扬|宣传).{0,16}"
        r"(?P<b>昭昭|灿灿|妹妹|弟弟|姐姐|哥哥|她|他)?",
        raw,
    )
    if not m:
        return None
    prop = _normalize_sibling_alias(m.group("a"))
    if not prop:
        return None
    victim_raw = str(m.group("b") or "").strip()
    victim = _normalize_sibling_alias(victim_raw) if victim_raw else None
    if not victim:
        # 「到处说姐姐考了…」类：受害方写在宣传动作之后
        m2 = re.search(
            r"(?:到处说|宣扬|宣传).{0,6}"
            r"(?P<b>昭昭|灿灿|妹妹|弟弟|姐姐|哥哥)",
            raw,
        )
        if m2:
            victim = _normalize_sibling_alias(m2.group("b"))
    if not victim:
        victim = _sibling_partner(prop)
    if victim == prop:
        return None
    return prop, victim


def _beat_chain_initiator_defender(
    beat_chain: list[Any] | None,
) -> tuple[str, str]:
    initiator = ""
    defender = ""
    for item in beat_chain or []:
        if not isinstance(item, dict):
            continue
        sp = str(item.get("speaker") or "").strip()
        intent = str(item.get("intent") or item.get("beat") or "")
        if not initiator and sp and RE_BEAT_INITIATOR.search(intent):
            initiator = sp
        elif not defender and sp and RE_BEAT_DEFENDER.search(intent):
            defender = sp
        if initiator and defender:
            break
    return initiator, defender


def _append_beat_role_issues(
    lines: list[str],
    speakers: list[str],
    issues: list[dict[str, Any]],
    *,
    beat_chain: list[Any] | None = None,
    conflict_text: str = "",
) -> None:
    """beat 发起方/受害方与 scene conflict、beat_chain 分工一致。"""
    victim = _parse_conflict_victim(conflict_text)
    if victim:
        for i, (sp, line) in enumerate(zip(speakers, lines), 1):
            if i > 12 or sp not in {"昭昭", "灿灿"}:
                continue
            if RE_RETALIATION.search(line):
                continue
            if RE_RETALIATION_DONE.search(line) or (
                RE_RETALIATION_INTENT.search(line) and "也" in line
            ):
                continue
            if not RE_AGGRESSIVE_DAMAGE.search(line):
                continue
            if _is_damage_threat_only(line):
                continue
            if sp == victim:
                prior_blob = "".join(lines[: i - 1])
                if RE_PRIOR_DAMAGE.search(prior_blob):
                    continue
                issues.append(
                    _issue(
                        lines=[i],
                        kind="保真-发起方倒置",
                        desc=(
                            f"第{i}句受害方({victim})先发起破坏，"
                            f"与 scene conflict 分工不符：{line}"
                        ),
                        fix=(
                            "先毁物/撕抢须由非受害方；"
                            "受害方写保物/拒看/哭腔，勿写受害方先弄坏"
                        ),
                    )
                )
            break

    initiator, defender = _beat_chain_initiator_defender(beat_chain)
    if victim:
        for i, (sp, line) in enumerate(zip(speakers, lines), 1):
            if i > 8 or sp not in {"昭昭", "灿灿"}:
                continue
            if re.search(r"我的|秘密", line):
                if sp != victim:
                    issues.append(
                        _issue(
                            lines=[i],
                            kind="保真-发起方倒置",
                            desc=(
                                f"第{i}句 {sp} 持有/守护物，"
                                f"但 scene conflict 受害方为 {victim}：{line}"
                            ),
                            fix=(
                                f"scene conflict 受害方 {victim} 须 establish 持有物；"
                                "勿把守方与受害方写反"
                            ),
                        )
                    )
                break

    if initiator:
        first_kid = next(
            (i for i, sp in enumerate(speakers, 1) if sp in {"昭昭", "灿灿"}),
            0,
        )
        if first_kid and speakers[first_kid - 1] != initiator:
            issues.append(
                _issue(
                    lines=[first_kid],
                    kind="保真-发起方倒置",
                    desc=(
                        f"第{first_kid}句 speaker 与 beat_chain 发起方"
                        f"({initiator})不一致"
                    ),
                    fix=f"首句对白宜由 beat_chain 发起方 {initiator} 开口",
                )
            )
    if defender and victim and defender == victim:
        issues.append(
            _issue(
                lines=[1],
                kind="保真-发起方倒置",
                desc=(
                    f"beat_chain 守方({defender})与 conflict 受害方({victim})"
                    "冲突，角色分工须与 scene_contract 一致"
                ),
                fix="对齐 beat_chain 与 conflict：守物/受害方同一角色",
            )
        )

    prop_roles = _parse_conflict_propaganda_roles(conflict_text)
    if prop_roles:
        propagandist, victim_p = prop_roles
        re_prop = re.compile(
            r"我宣传|我宣扬|宣传高分|宣传低分|到处说她|到处说他|"
            r"低分被怪|高分.{0,8}谢我|不是我考的|跟我有啥关系"
        )
        re_hurt = re.compile(
            r"同学都笑我|你到处说我|说我考|拿我.{0,6}分|笑我"
        )
        for i, (sp, line) in enumerate(zip(speakers, lines), 1):
            if sp not in {"昭昭", "灿灿"}:
                continue
            if re_prop.search(line) and sp != propagandist:
                issues.append(
                    _issue(
                        lines=[i],
                        kind="保真-宣传方倒置",
                        desc=(
                            f"第{i}句宣传腔由{sp}说，"
                            f"conflict 宣传方为{propagandist}：{line}"
                        ),
                        fix=f"「我宣传/宣扬」须由宣传方{propagandist}说",
                    )
                )
            if re_hurt.search(line) and sp != victim_p:
                issues.append(
                    _issue(
                        lines=[i],
                        kind="保真-宣传方倒置",
                        desc=(
                            f"第{i}句受害腔由{sp}说，"
                            f"conflict 受害方为{victim_p}：{line}"
                        ),
                        fix=f"「你到处说我/同学笑我」须由受害方{victim_p}说",
                    )
                )


def _append_m5_h_issues(
    rows: list[dict[str, Any]],
    issues: list[dict[str, Any]],
    *,
    closing_intent: str = "",
    beat_chain: list[Any] | None = None,
    conflict_text: str = "",
) -> None:
    lines = [str(r.get("line") or "").strip() for r in rows]
    speakers = [str(r.get("speaker") or "").strip() for r in rows]
    n = len(lines)
    if n < 10:
        return

    _append_beat_role_issues(
        lines,
        speakers,
        issues,
        beat_chain=beat_chain,
        conflict_text=conflict_text,
    )

    closing = str(closing_intent or "").strip()
    invent_allowed = bool(_CLOSING_INVENT_ALLOW.search(closing))

    for i, line in enumerate(lines, 1):
        if RE_RETALIATION.search(line):
            sp = speakers[i - 1]
            prior_lines = lines[: i - 1]
            prior_pairs = list(zip(speakers[: i - 1], prior_lines))
            edit_line = max(1, i - 2)
            if sp in {"昭昭", "灿灿"} and not _other_damaged_self_prior(
                sp, line, prior_pairs
            ):
                other = _sibling_partner(sp)
                issues.append(
                    _issue(
                        lines=[edit_line],
                        kind="保真-互毁前文",
                        desc=(
                            f"第{i}句「也/还+破坏+你的」须 {other} 先破坏"
                            f" {sp} 侧物，前文缺另一 speaker 实质破坏：{line}"
                        ),
                        fix=(
                            f"改第{edit_line}句（或更早）补 {other} 弄坏/撕"
                            f" {sp} 侧作品；或删「也/还」改单向报复"
                        ),
                    )
                )
            elif not _retaliation_has_prior_damage(line, "".join(prior_lines)):
                issues.append(
                    _issue(
                        lines=[edit_line],
                        kind="保真-互毁前文",
                        desc=(
                            f"第{i}句「也/还弄坏」类报复，"
                            f"但第{edit_line}–{i - 1}句缺破坏/损坏依据：{line}"
                        ),
                        fix=(
                            f"改第{edit_line}句（或更早）补弄坏/抢坏依据；"
                            f"第{i}句可保留报复句，"
                            "禁止把依据合并进报复同一句"
                        ),
                    )
                )
            elif not _your_object_established(line, prior_lines):
                if _prior_has_holder_only_patch(prior_lines):
                    issues.append(
                        _issue(
                            lines=[max(1, i - 3)],
                            kind="保真-对象持有补丁",
                            desc=(
                                f"第{i}句「也弄坏你的…」前文仅用持有句补丁"
                                f"（如「我也有你的…」），缺创作/在场 establish：{line}"
                            ),
                            fix=(
                                "更早的句写对方也在创作/有作品"
                                "（如「我画…你的画呢」）；"
                                "勿用「我也有你的X」单独补丁"
                            ),
                        )
                    )
                else:
                    issues.append(
                        _issue(
                            lines=[max(1, i - 3)],
                            kind="保真-互毁对象",
                            desc=(
                                f"第{i}句含「你的…」报复，"
                                f"但前文未 establish 对方也有该物：{line}"
                            ),
                            fix=(
                                "在报复句之前的句子里补对方也有作品/物品"
                                "（如先写「我画…你画…」或「你的XX在那」）；"
                                "勿只在同句后半补"
                            ),
                        )
                    )
            victim = _parse_conflict_victim(conflict_text)
            if (
                victim
                and sp == victim
                and _retaliation_missing_action(line, lines[i : min(n, i + 2)])
            ):
                issues.append(
                    _issue(
                        lines=[i],
                        kind="保真-互毁动作",
                        desc=f"第{i}句互毁仅口头威胁，缺当场撕/弄坏动作：{line}",
                        fix="改为「我也抢你画撕啦！」等已完成动作，勿仅「那我也/我也要撕你的」",
                    )
                )

    mom_indices = [i for i, sp in enumerate(speakers, 1) if sp == "妈妈"]
    pre_mom_end = mom_indices[0] if mom_indices else n + 1
    pre_mom = lines[: pre_mom_end - 1]
    if any(RE_IODINE_CLOSE.search(x) for x in lines):
        if pre_mom and not any(RE_INJURY.search(x) for x in pre_mom):
            push_line = next(
                (i for i, x in enumerate(pre_mom, 1) if "推" in x),
                max(1, len(pre_mom) - 1),
            )
            issues.append(
                _issue(
                    lines=[push_line],
                    kind="保真-伤情",
                    desc="有碘伏收场但扭打后缺伤情（额/头/蹭破/疼）",
                    fix="推搡后补受害方喊疼或额头蹭破一句",
                )
            )
    if pre_mom and not any(RE_M5_AUTHORITY.search(x) for x in pre_mom):
        kid_before_mom = [
            i
            for i, sp in enumerate(speakers[: pre_mom_end - 1], 1)
            if sp in {"昭昭", "灿灿"}
        ]
        target = kid_before_mom[-2] if len(kid_before_mom) >= 2 else (
            kid_before_mom[-1] if kid_before_mom else pre_mom_end
        )
        issues.append(
            _issue(
                lines=[target],
                kind="保真-M5立规",
                desc="妈妈介入前缺 M5 立规（家规/规矩/规定）",
                fix="在拒和/加码前补一句「家规就是谁先动手谁道歉」类立规",
            )
        )

    _append_m5_denial_speaker_issues(
        lines, speakers, issues, pre_mom_end=pre_mom_end
    )

    for i, line in enumerate(lines, 1):
        if speakers[i - 1] not in {"昭昭", "灿灿"}:
            continue
        if RE_M5_RULE.search(line) and not RE_M5_AUTHORITY.search(line):
            issues.append(
                _issue(
                    lines=[i],
                    kind="保真-M5立规",
                    desc=f"第{i}句 M5 规则引入突兀：{line}",
                    fix="用「家规/规矩/规定」引入立规；"
                    "立规来源宜为孩子主动引家规，勿写「妈妈说过」类转述",
                )
            )
        if _m5_phrase_hits(line) >= 2:
            issues.append(
                _issue(
                    lines=[i],
                    kind="保真-M5合并",
                    desc=f"第{i}句 M5 立规/不原谅/加码合并：{line}",
                    fix="本句只保留一类功能（立规 或 不原谅 或 加码），"
                    "其余拆到相邻句；不可增删总行数时删句内多余短语",
                )
            )

    mom_indices = [i for i, sp in enumerate(speakers, 1) if sp == "妈妈"]
    if mom_indices:
        first_mom = mom_indices[0]
        pre_mom = lines[: first_mom - 1]
        stubborn_pos = next(
            (i for i, x in enumerate(pre_mom) if RE_M5_STUBBORN.search(x)),
            -1,
        )
        has_hard = stubborn_pos >= 0 or any(RE_M5_STUBBORN.search(x) for x in pre_mom)
        if stubborn_pos >= 0:
            has_escalate_after = any(
                RE_M5_ESCALATE.search(x) for x in pre_mom[stubborn_pos + 1 :]
            )
        else:
            has_escalate_after = any(RE_M5_ESCALATE.search(x) for x in pre_mom)
        if has_hard and not has_escalate_after:
            target = (
                stubborn_pos + 2
                if stubborn_pos >= 0
                else max(1, first_mom - 1)
            )
            issues.append(
                _issue(
                    lines=[target],
                    kind="保真-M5加码",
                    desc=(
                        "拒和句后、妈妈介入前缺 M5 加码"
                        "（画/物弄了好久、变不回来等）"
                    ),
                    fix=(
                        "在「不原谅」后补一句加码，"
                        "如「这画我弄了好久呢！」勿与拒合同句"
                    ),
                )
            )
        elif not has_hard and not any(RE_M5_ESCALATE.search(x) for x in pre_mom):
            issues.append(
                _issue(
                    lines=[first_mom],
                    kind="保真-M5加码",
                    desc=(
                        "妈妈介入前缺 M5 两拍嘴硬"
                        "（拒和 + 加码各至少一句，与是否道歉无关）"
                    ),
                    fix=(
                        "妈妈第一句前补拍：一句拒和（不原谅/免谈），"
                        "再一句加码（画/物弄了好久、变不回来等）；"
                        "勿与拒合同句合并"
                    ),
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
                        fix="分层定责：点出先推/别抢，再劝处理和好的动作",
                    )
                )
            elif RE_MOM_SOFT.search(mom_line):
                issues.append(
                    _issue(
                        lines=[second_mom],
                        kind="保真-H定责",
                        desc=(
                            f"第{second_mom}句妈妈定责过软"
                            f"（扯平/各打五十）：{mom_line}"
                        ),
                        fix=(
                            "先点先动手方不对，再劝受害方原谅；"
                            "禁「扯平/都有错」式各打五十"
                        ),
                    )
                )

    _append_closing_tail_issues(
        lines, speakers, issues, closing_intent=closing_intent
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

    if not invent_allowed:
        reconcile_idx = 0
        for i, line in enumerate(lines, 1):
            if RE_RECONCILE.search(line):
                reconcile_idx = i
        scan_from = max(reconcile_idx, n - 3)
        for i in range(scan_from, n + 1):
            line = lines[i - 1]
            if speakers[i - 1] == "妈妈":
                continue
            if RE_CLOSING_INVENT.search(line) and not RE_RECONCILE.search(line):
                issues.append(
                    _issue(
                        lines=[i],
                        kind="保真-收场Invent",
                        desc=f"第{i}句收场后新增 closing_intent 未要求的动作：{line}",
                        fix="删 invent 动作，收成 closing_intent 内的和好+收场物；"
                        "末句宜短应答（嗯/好）或删本句",
                    )
                )



def _append_h_generic_issues(
    rows: list[dict[str, Any]],
    issues: list[dict[str, Any]],
    *,
    closing_intent: str = "",
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


def _append_pad_filler_issues(
    rows: list[dict[str, Any]],
    issues: list[dict[str, Any]],
    *,
    max_tail_filler: int = 3,
    max_expand_clutter: int = 2,
) -> None:
    """句尾「好不好/了呢呀」或扩写灌尾巴过密 → 机审 issue。"""
    hits: list[int] = []
    clutter: list[int] = []
    for i, row in enumerate(rows, 1):
        line = str(row.get("line") or "").strip()
        if RE_PAD_FILLER_TAIL.search(line):
            hits.append(i)
        if RE_EXPAND_CLUTTER.search(line):
            clutter.append(i)
    if len(hits) > max_tail_filler:
        issues.append(
            _issue(
                lines=hits,
                kind="保真-垫字过密",
                desc=f"句尾垫字「好不好/了呢呀」过多（{len(hits)} 处，上限 {max_tail_filler}）",
                fix="保留 2–3 处即可，其余改短句实词收尾；"
                "互怼句补全宾语，禁「呢呀/好不好呀」堆砌",
            )
        )
    if len(clutter) > max_expand_clutter:
        issues.append(
            _issue(
                lines=clutter,
                kind="保真-垫字过密",
                desc=(
                    f"扩写灌尾巴过多（{len(clutter)} 处，上限 {max_expand_clutter}）："
                    "你给我听好了/这回算清楚/别再装傻…"
                ),
                fix="删灌尾，用 beat 相关实词句内扩写；勿复读同一尾巴",
            )
        )


def _seed_unique_phrase_owners(
    dialogue_seed: list[Any] | None,
) -> dict[str, str]:
    """seed intent 中仅属一方的特色短语 → speaker（抽象，不写死单篇）。

    过短/通用对白词（谁先动手/对不起…）不入库，避免误伤正常引用。
    """
    from collections import defaultdict

    stop = frozenset(
        {
            "谁先动手",
            "对不起",
            "我不玩",
            "拉手吧",
            "不打了",
            "你走开",
            "该你走",
            "怎么了",
            "看招",
            "行不行",
            "好不好",
            "没办法",
            "没关系",
        }
    )
    owners: dict[str, set[str]] = defaultdict(set)
    for item in dialogue_seed or []:
        if not isinstance(item, dict):
            continue
        sp = str(item.get("speaker") or "").strip()
        if sp not in {"昭昭", "灿灿", "妈妈", "爸爸"}:
            continue
        intent = str(item.get("intent") or item.get("line") or "")
        text = "".join(re.findall(r"[\u4e00-\u9fff]", intent))
        if len(text) < 3:
            continue
        if 3 <= len(text) <= 14 and text not in stop:
            owners[text].add(sp)
        for length in range(min(8, len(text)), 3, -1):
            for i in range(0, len(text) - length + 1):
                phr = text[i : i + length]
                if phr in stop or len(phr) < 4:
                    continue
                owners[phr].add(sp)
    unique = {
        phr: next(iter(sps))
        for phr, sps in owners.items()
        if len(sps) == 1 and len(phr) >= 4
    }
    kept: dict[str, str] = {}
    for phr, sp in sorted(unique.items(), key=lambda x: -len(x[0])):
        if any(phr in longer and kept[longer] == sp for longer in kept):
            continue
        kept[phr] = sp
    return kept


def apply_seed_phrase_speaker_align(
    story: dict[str, Any],
    *,
    dialogue_seed: list[Any] | None = None,
) -> tuple[dict[str, Any], bool]:
    """seed 专属短语出现在错 speaker 时，改回 seed 标注角色（机械对齐）。"""
    import copy

    owners = _seed_unique_phrase_owners(dialogue_seed)
    if not owners:
        return story, False

    out = copy.deepcopy(story)
    dialogue = out.get("dialogue")
    if not isinstance(dialogue, list):
        return story, False
    changed = False
    for item in dialogue:
        if not isinstance(item, dict):
            continue
        sp = str(item.get("speaker") or "").strip()
        line = str(item.get("line") or "").strip()
        if not line or sp not in {"昭昭", "灿灿", "妈妈", "爸爸"}:
            continue
        line_han = "".join(re.findall(r"[\u4e00-\u9fff]", line))
        for phr, want in owners.items():
            if phr not in line and phr not in line_han:
                continue
            if sp == want:
                break
            item["speaker"] = want
            changed = True
            break
    return out, changed



_N_BEAT_QUESTION_INTENT = re.compile(
    r"追问|设问|发问|问：|为什么|为啥|怎么(?:会|知道|想)|哪有|凭什么"
)
_N_BEAT_ANSWER_INTENT = re.compile(
    r"离谱|回答|作答|解释|自洽|反驳|嘴硬|讲圆|理由|原因"
)
_N_DIALOGUE_QUESTION = re.compile(
    r"[？?]|为什么|为啥|怎么(?:会|知道|想|在)|哪有|凭什么|"
    r"是不是|要不要|能不能|该不该|吗[？?]?$|呢[？?]?$"
)
_N_DIALOGUE_ANSWER_CUE = re.compile(
    r"^(?:我|因为|所以|当然|就是|才|不是|哪有|有啊|没有|嗯|对|那是)"
)


def _n_beat_role_speakers(
    beat_chain: list[Any] | None,
) -> tuple[str, str]:
    """N 契约唯一确定追问方/回答方时返回二者；含混则不猜。"""
    questioners: set[str] = set()
    answerers: set[str] = set()
    for item in beat_chain or []:
        if not isinstance(item, dict):
            continue
        speaker = str(item.get("speaker") or "").strip()
        if speaker not in {"昭昭", "灿灿"}:
            continue
        intent = str(item.get("intent") or "").strip()
        if _N_BEAT_QUESTION_INTENT.search(intent):
            questioners.add(speaker)
        if _N_BEAT_ANSWER_INTENT.search(intent):
            answerers.add(speaker)
    if len(questioners) != 1 or len(answerers) != 1:
        return "", ""
    questioner = next(iter(questioners))
    answerer = next(iter(answerers))
    if questioner == answerer:
        return "", ""
    return questioner, answerer


def apply_n_beat_role_speaker_align(
    story: dict[str, Any],
    *,
    beat_chain: list[Any] | None = None,
    structure_type: str = "",
) -> tuple[dict[str, Any], bool]:
    """N 类按 beat 的唯一 Q/A 角色纠正 speaker 漂移，不改台词文本。"""
    import copy

    if str(structure_type or story.get("story_type") or "").strip().upper() != "N":
        return story, False
    questioner, answerer = _n_beat_role_speakers(beat_chain)
    if not questioner or not answerer:
        return story, False
    rows = _dialogue_rows(story)
    if not rows:
        return story, False

    out = copy.deepcopy(story)
    dialogue = out.get("dialogue")
    if not isinstance(dialogue, list):
        return story, False

    changed = False
    previous_was_question = False
    for item in dialogue:
        if not isinstance(item, dict):
            previous_was_question = False
            continue
        speaker = str(item.get("speaker") or "").strip()
        line = str(item.get("line") or "").strip()
        if not line:
            previous_was_question = False
            continue

        # beat 已唯一确定追问方时，回答方不能反过来用“你…”追问对方。
        # 因果/第一人称作答里带反问（如「因为…，你不知道吗？」）不算追问。
        is_direct_question = (
            "你" in line
            and bool(_N_DIALOGUE_QUESTION.search(line))
            and not bool(_N_DIALOGUE_ANSWER_CUE.search(line))
        )
        if is_direct_question:
            if speaker == answerer:
                item["speaker"] = questioner
                speaker = questioner
                changed = True
            previous_was_question = speaker == questioner
            continue

        # 紧随追问的第一人称/因果回答若仍挂在追问方名下，一并归回答方。
        if (
            previous_was_question
            and speaker == questioner
            and bool(_N_DIALOGUE_ANSWER_CUE.search(line))
        ):
            item["speaker"] = answerer
            changed = True
        previous_was_question = False

    return out, changed


_RE_N_ASK_BEAT_INTENT = re.compile(
    r"追问|质问|设问|发问|问：|问什么|谁教|问出处|问来历"
)
_N_DIALOGUE_STUN = re.compile(
    r"那……|那\.\.\.|行吧|服了|说不出|无语|愣|哭笑不得|接不住|被噎|算了|放弃"
)
# 追问句判定（只用于「追问主线在谁身上」的计数，不判断内容对错）
_N_DIALOGUE_QUESTION_ASK = re.compile(
    r"[？?]|为什么|为啥|凭什么|怎么(?:会|知道|想)|是不是|要不要|"
    r"能不能|该不该|哪(?:儿|里|来|个|些)"
)


def _n_ask_beat_functions(intent: str) -> set[str]:
    """把「追问」拍归一到关键追问功能集合 + 泛问。

    - ``origin``：追问出处（谁教的/哪来的/出处/来历）
    - ``meaning``：追问意思（什么意思/什么词/怎么解释）
    - ``generic``：其余设问/追问

    只看问什么，不绑剧情词：同一功能可由任意说法的问句落地。
    合并拍（追问意思 + 追问出处合成一拍）会同时带回两个功能，
    此时任一功能落地即算该拍落地。
    """
    text = str(intent or "")
    funcs: set[str] = set()
    if re.search(r"谁教|谁说的|哪儿来|哪里来|哪来|出处|来历|跟谁学", text):
        funcs.add("origin")
    if re.search(r"意思|什么词|什么叫|怎么解释|含义|啥意思", text):
        funcs.add("meaning")
    return funcs or {"generic"}


def _n_question_lines_by(
    rows: list[dict[str, Any]],
    speaker: str,
) -> list[str]:
    return [
        str(row.get("line") or "").strip()
        for row in rows
        if str(row.get("speaker") or "").strip() == speaker
        and _N_DIALOGUE_QUESTION_ASK.search(str(row.get("line") or ""))
    ]


def _n_ask_beat_landed(
    rows: list[dict[str, Any]],
    speaker: str,
    entry: dict[str, Any],
) -> bool:
    """关键追问拍是否由指定说话人落地。

    两条判据取并集，避免叙述式 intent 因锚词不可匹配而误报缺拍：
    1. 追问功能判据（不绑剧情词）：该说话人确有一句问句，且落在该拍的
       origin（追问出处）/ meaning（追问意思）功能上；
    2. 既有拍落地判据（``_line_fulfills_beat``）：该说话人的任一句能对上该拍。
    """
    lines = [
        str(row.get("line") or "").strip()
        for row in rows
        if str(row.get("speaker") or "").strip() == speaker
        and str(row.get("line") or "").strip()
    ]
    if not lines:
        return False
    intent = str(entry.get("intent") or entry.get("beat") or "")
    funcs = _n_ask_beat_functions(intent)
    ask_lines = _n_question_lines_by(rows, speaker)
    if ask_lines:
        if "origin" in funcs and any(
            re.search(r"谁|哪|跟谁", line) for line in ask_lines
        ):
            return True
        if "meaning" in funcs and any(
            re.search(r"什么|啥|怎么|什么意思", line) for line in ask_lines
        ):
            return True
        if "generic" in funcs:
            return True
    return any(_line_fulfills_beat(speaker, line, entry) for line in lines)


_RE_N_TOKEN_BEAT_INTENT = re.compile(
    r"蹦出|冒出|说出|说了个|一个新词|怪词|英文词|外语词|自造词|生造词|单词"
)
_RE_ASCII_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9'\-_]{1,15}")
# 中文自造词：孩子自造的 2–4 字音节组合。合规替换不该往中文童言里塞英文串
# （「waka了呀」这种读起来就不是中文），所以词槽允许中文自造词。
# 只认「」包裹的短词，避免把 intent 里的叙述短语当词槽。
_RE_QUOTED_CN_TOKEN = re.compile(r"[「『“\"]([\u4e00-\u9fff]{2,4})[」』”\"]")


def _n_declared_word_token(intent: str) -> str:
    """从「词槽拍」的 intent 里取契约声明的字面词（合规替换后的锚点）。

    优先「」包裹的 ASCII 词，其次「」包裹的 2–4 字中文自造词；
    intent 未声明字面词时返回空串，调用方即跳过该不变量（不猜、不补词）。
    """
    text = str(intent or "")
    if not _RE_N_TOKEN_BEAT_INTENT.search(text):
        return ""
    quoted = re.search(r"[「『“\"]([A-Za-z][A-Za-z0-9'\-_]{1,15})[」』”\"]", text)
    if quoted:
        return quoted.group(1)
    cn = _RE_QUOTED_CN_TOKEN.search(text)
    if cn:
        return cn.group(1)
    plain = _RE_ASCII_TOKEN.search(text)
    return plain.group(0) if plain else ""


def _append_n_contract_role_issues(
    rows: list[dict[str, Any]],
    issues: list[dict[str, Any]],
    *,
    beat_chain: list[Any] | None,
) -> None:
    """N 类：关键追问拍须由契约追问方落地，收束的愣住拍也归同一方。

    抽象不变量（不数问句总量、不绑剧情词）：
    - 机制链里的关键追问拍（追问出处 / 追问意思）必须由契约指定的追问方说；
      由旁观孩子的问句接管即为转手——立规方被挤成「立规 + 收束」两端，
      N 的「立规方被整懵」机制随之失效（#87 实测）。
    - 旁观孩子的反问只算帮腔；它一旦落在关键追问功能上即打回。
    - 收束窗的愣住/接不住拍须由追问方说；旁观孩子说会把破功主体换人。
    """
    entries = _beat_chain_entries(list(beat_chain or []))
    if len(entries) < 2:
        return
    ask_beats = [
        (beat_no, entry)
        for beat_no, entry in entries
        if _RE_N_ASK_BEAT_INTENT.search(
            str(entry.get("intent") or entry.get("beat") or "")
        )
    ]
    if not ask_beats:
        return

    for beat_no, entry in ask_beats:
        speaker = str(entry.get("speaker") or "").strip()
        if not speaker:
            continue
        if _n_ask_beat_landed(rows, speaker, entry):
            continue
        others = [
            str(row.get("speaker") or "").strip()
            for row in rows
            if str(row.get("speaker") or "").strip() not in {"", speaker}
            and _n_ask_beat_landed(rows, str(row.get("speaker") or "").strip(), entry)
            and _N_DIALOGUE_QUESTION_ASK.search(str(row.get("line") or ""))
        ]
        taken_by = "、".join(dict.fromkeys(others)) or "无人"
        issues.append(
            _issue(
                lines=[],
                kind="保真-N家长追问拍",
                desc=(
                    f"{_beat_summary(entry, beat_no)}未由{speaker}落地"
                    f"（实际由{taken_by}问）"
                ),
                fix=(
                    f"该追问改由{speaker}当场问出口；旁观孩子只做帮腔/看热闹，"
                    "禁代问关键追问（追问意思、追问出处）"
                ),
            ),
        )

    # 机制词槽字面保真：契约声明的怪词必须在正文里真被说出口
    body = "\n".join(str(row.get("line") or "") for row in rows)
    body_lower = body.lower()
    for beat_no, entry in entries:
        token = _n_declared_word_token(
            str(entry.get("intent") or entry.get("beat") or "")
        )
        if not token or token.lower() in body_lower:
            continue
        speaker = str(entry.get("speaker") or "").strip() or "?"
        issues.append(
            _issue(
                lines=[],
                kind="保真-N机制词槽",
                desc=(
                    f"{_beat_summary(entry, beat_no)}声明的词槽「{token}」"
                    "在正文里没有出现，笑点机制被降级"
                ),
                fix=(
                    f"由{speaker}真把「{token}」说出口（先出词，再让追问方问它"
                    "是什么意思），合规替换只换词、不删槽、不改因果顺序"
                ),
            ),
        )

    askers = {
        str(entry.get("speaker") or "").strip()
        for beat_no, entry in entries
        if _N_BEAT_QUESTION_INTENT.search(
            str(entry.get("intent") or entry.get("beat") or "")
        )
    }
    askers.discard("")
    if len(askers) != 1:
        return
    asker = next(iter(askers))
    # 只对「立规方是家长」的稿查收束归属：家长问、孩子答，破功方必是家长。
    # 孩子当设问方时（如 #89 昭昭问妈妈），收束常由家长旁观感叹，属正常收场。
    if asker not in {"妈妈", "爸爸"}:
        return
    tail = [row for row in rows if str(row.get("line") or "").strip()][-4:]
    if not tail:
        return
    stun_rows = [
        row
        for row in tail
        if _N_DIALOGUE_STUN.search(str(row.get("line") or "").strip())
        and not str(row.get("line") or "").strip().endswith(("？", "?"))
    ]
    if not stun_rows:
        return
    if any(str(row.get("speaker") or "").strip() == asker for row in stun_rows):
        return
    speaker = str(stun_rows[0].get("speaker") or "").strip() or "?"
    # 家长**点名问某个孩子**时，那个孩子被问住是机制本身，不是「破功主体被换人」。
    # 原规则假设「家长问 ⇒ 必是家长破功」，但「妈妈点名问灿灿 → 灿灿答不上」
    # 是合法形态（#135 实测：判词把设计的落点当成错误，60 次全灭）。
    # 判据窄：问句那拍的 intent 里必须出现被问住者的名字。
    if speaker:
        for _beat_no, entry in entries:
            _intent = str(entry.get("intent") or entry.get("beat") or "")
            if not _N_BEAT_QUESTION_INTENT.search(_intent):
                continue
            if speaker in _intent:
                return
    issues.append(
        _issue(
            lines=[],
            kind="保真-N收束归属",
            desc=(
                f"收束的愣住/接不住拍由{speaker}说，追问方是{asker}，"
                "破功主体被换人"
            ),
            fix=f"把收束的愣住/接不住句改由{asker}说，再收场",
        ),
    )


def _token_predicate_re(token: str) -> re.Pattern[str]:
    """按**声明词本身**构造「被当谓语/加时态」的检测正则。

    只认真正的词形滥用：
      「会X / 要X / 去X / 能够X」——把词当动作；
      「X了 / X着 / X过」——给它加时态。
    **不含「叫X」**：那是正常命名（「他叫小明」「这词叫哇卡」）。
    **不含「是X」「就是X」**：那是机制要求的合法解释。
    不假设词的语种：中文自造词与外语词同样适用。
    """
    esc = re.escape(token)
    return re.compile(
        rf"(?:会|要|去|能够)\s*{esc}|{esc}(?:了|着|过)"
    )


def _append_n_token_grammar_issues(
    rows: list[dict[str, Any]],
    issues: list[dict[str, Any]],
    *,
    beat_chain: list[Any] | None,
) -> None:
    """N 类：机制怪词只能独立出现，不得当动词/形容词/名字用。

    N 的机制是「孩子蹦出一个无本义的词，再一本正经解释它」。模型很容易
    把这个词当谓语塞进句子（「好人会waka」「waka了呀」），一句话就把机制
    塌成病句——观众听到的是错话而不是笑点（#87 实测，专家两轮都点出这条）。

    这里只查**词形位置**这个抽象特征：词后面紧跟「了/着/过/地/得」，
    或前面紧跟「会/要/去/在/是/叫/有/做/干/弄/搞」，即视为当谓语使用。
    不查剧情词、不查数量。
    """
    entries = _beat_chain_entries(list(beat_chain or []))
    if not entries:
        return
    tokens = {
        tok.lower()
        for _n, entry in entries
        for tok in [_n_declared_word_token(
            str(entry.get("intent") or entry.get("beat") or "")
        )]
        if tok
    }
    if not tokens:
        return
    offenders: list[int] = []
    for i, row in enumerate(rows, 1):
        line = str(row.get("line") or "")
        if not line:
            continue
        for tok in tokens:
            if not re.search(re.escape(tok), line, re.I):
                continue
            if _token_predicate_re(tok).search(line):
                offenders.append(i)
                break
    # 同一怪词被反复重新定义：一次追问只要一次解释，重复定义会让观众听不懂
    redefined: list[int] = []
    for i, row in enumerate(rows, 1):
        line = str(row.get("line") or "")
        if not line:
            continue
        for tok in tokens:
            if tok not in line.lower():
                continue
            # 形如「waka就是/是/指/意思」= 定义句
            if re.search(
                re.escape(tok) + r"\s*(?:就是|是|指|意思是|算是)", line, re.I
            ):
                redefined.append(i)
            break
    if len(redefined) > 1:
        issues.append(
            _issue(
                lines=redefined,
                kind="保真-N词槽语法",
                desc=(
                    f"怪的机制词在第{redefined}句被反复重新定义"
                    "（同一个词一会儿指这、一会儿指那）"
                ),
                fix=(
                    "只在被追问后解释一次；后面再提到一律沿用同一个意思，"
                    "禁止每次提都换一种说法"
                ),
            ),
        )

    if offenders:
        issues.append(
            _issue(
                lines=offenders,
                kind="保真-N词槽语法",
                desc=(
                    f"第{offenders}句把怪词当谓语/名字用了（如「会waka」「waka了」）"
                ),
                fix=(
                    "怪词只能原样独立出现一次，之后用「这个词」或「它」指代；"
                    "禁止给它加「了/着/过」或放在「会/要/是/叫」后面"
                ),
            ),
        )


# ── 纯动作句门限 ────────────────────────────────────────────────────────
# 我们要的是**对话稿**。一句台词必须是角色对现场另一个人说的话；
# 「笑一声」「拍腿笑死我了」这类只是动作/神态描述，是舞台说明不是对白。
# 这类句子没有对话对象、不能配音演出来（观众听到的是演员在念动作），
# 所以在机检里直接拒绝，不指望 LLM 语义审读偶尔抓到。
_ACTION_VERB_RE = re.compile(
    r"笑|点头|摇头|皱眉|叹气|拍腿|拍手|鼓掌|转身|发愣|愣住|瞪|撇嘴|"
    r"耸肩|搓手|跺脚|低头|抬头|伸手|摆手|眨眼|抿嘴|咬牙|挠头|捂脸|"
    r"咳嗽|倒吸|深吸|皱眉|挑眉|翻白眼"
)
# 出现这些标记说明这句话确实在对人说（有人称/疑问/引述/祈使）
_DIALOGUE_MARKER_RE = re.compile(
    r"你|您|问|吗|呢|谁|哪|什么|凭|怎么|"
    r"别|不要|说|讲|喊|叫|"
    r"[？?]|「|」|\""
)


def _looks_like_pure_action(line: str) -> bool:
    """这句话是不是「只有动作、没有对话」的舞台说明。"""
    text = str(line or "").strip()
    if not text:
        return False
    if not _ACTION_VERB_RE.search(text):
        return False
    return not _DIALOGUE_MARKER_RE.search(text)


def _append_pure_action_issues(
    rows: list[dict[str, Any]],
    issues: list[dict[str, Any]],
) -> None:
    """纯动作台词一律拒绝：对话稿里每句都得是人能说出口的话。"""
    offenders = [
        i
        for i, row in enumerate(rows, 1)
        if _looks_like_pure_action(str(row.get("line") or ""))
    ]
    if not offenders:
        return
    issues.append(
        _issue(
            lines=offenders,
            kind="保真-纯动作台词",
            desc=(
                f"第{offenders}句只有动作/神态，没有对话内容"
                "（观众听到的会是演员在念动作说明）"
            ),
            fix=(
                "改成角色对现场人**说出口的话**（比如把「笑了一声」改成"
                "「你可真敢说」）；动作不能当台词，也不要写「（笑）」「（愣住）」"
            ),
        ),
    )


_RE_KEY_ASK_CONTENT = re.compile(
    r"什么意思|啥意思|是什么|是啥|什么词|这词|那词|谁教|哪来|哪儿来|"
    r"什么时候|几点|哪天|在哪儿|什么地方|哪里|几个|多少"
)


def _append_second_kid_ask_usurp_issues(
    rows: list[dict[str, Any]],
    issues: list[dict[str, Any]],
    *,
    beat_chain: list[Any] | None,
) -> None:
    """关键追问只能由立规方发；旁观孩子不得接管。

    N 的机制主体是「立规方被整懵」：追问词义、出处、时间、地点、数量
    这些**关键追问**属于立规方。旁观孩子一旦也做这类追问，妈妈的主线
    就被挤掉，破功主体换人（专家两轮点出）。

    这里只拦「旁观孩子的关键追问」，她表态/帮腔/拆台一律放行。
    """
    entries = _beat_chain_entries(list(beat_chain or []))
    askers = {
        str(entry.get("speaker") or "").strip()
        for _n, entry in entries
        if str(entry.get("speaker") or "").strip() in {"妈妈", "爸爸"}
        and _RE_N_ASK_BEAT_INTENT.search(
            str(entry.get("intent") or entry.get("beat") or "")
        )
    }
    if not askers:
        return
    offenders: list[int] = []
    for i, row in enumerate(rows, 1):
        speaker = str(row.get("speaker") or "").strip()
        if speaker not in {"昭昭", "灿灿"}:
            continue
        line = str(row.get("line") or "")
        if _RE_KEY_ASK_CONTENT.search(line) and re.search(r"[？?]", line):
            offenders.append(i)
    if offenders:
        issues.append(
            _issue(
                lines=offenders,
                kind="保真-关键追问归属",
                desc=(
                    f"第{offenders}句是旁观孩子在问关键内容（词义/出处/时间/地点/数量），"
                    "这类追问归立规方"
                ),
                fix=(
                    "把这句改成表态/帮腔/拆台/复述（不提问）；"
                    "关键追问留给立规方，否则破功主体换人"
                ),
            ),
        )


def _append_consecutive_sibling_issues(
    rows: list[dict[str, Any]],
    issues: list[dict[str, Any]],
) -> None:
    """两个孩子之间禁止同人连说。

    用户裁决：孩子台词靠**两个孩子交替**解决，不许让一个孩子连说。
    连说 5 句的观感是「孩子在自言自语」，N 的机制也随之塌成独白。
    只判孩子（家长额度另有硬卡），只判相邻两句。
    """
    kids = {"昭昭", "灿灿"}
    runs: list[list[int]] = []
    current: list[int] = []
    prev = ""
    for i, row in enumerate(rows, 1):
        speaker = str(row.get("speaker") or "").strip()
        if speaker not in kids or not str(row.get("line") or "").strip():
            if len(current) > 1:
                runs.append(current)
            current = []
            prev = speaker
            continue
        if speaker == prev:
            current.append(i)
        else:
            if len(current) > 1:
                runs.append(current)
            current = [i]
        prev = speaker
    if len(current) > 1:
        runs.append(current)
    for run in runs:
        issues.append(
            _issue(
                lines=run,
                kind="保真-孩子连说",
                desc=f"第{run}句是同一个孩子连说，观众听感像自言自语",
                fix=(
                    "两句之间换另一个孩子接话（笑一声/点头/帮腔/补一句），"
                    "**禁止**同一孩子连着说；不要靠删句解决，要交替"
                ),
            ),
        )


def _append_cast_membership_issues(
    rows: list[dict[str, Any]],
    issues: list[dict[str, Any]],
    *,
    beat_chain: list[Any] | None,
) -> None:
    """出场角色硬闸门：孩子说话必须有对应的契约拍。

    契约 beat_chain 是本场的唯一人物真相。角色表里带着、beat 里一句没有的
    幽灵角色，会被扩写照着写进对白（#87 实测：契约只有妈妈+昭昭，成稿里
    灿灿却有 7 句），随后只能靠下游补丁删掉，字数随之塌方并反复震荡。
    这里在机审层直接拦，任何一处 LLM 重新引入都过不去。

    家长例外：`mom_lines_max` / `parent_lines_max` 本就是给家长的**额度**，
    家长可以在没有独立拍的情况下说反应句（额度由 validate_chat_hard 卡），
    所以只对孩子做「必须有拍」的判定。
    """
    cast = {
        str(row.get("speaker") or "").strip()
        for row in (beat_chain or [])
        if isinstance(row, dict) and str(row.get("speaker") or "").strip()
    }
    if len(cast) < 2:
        # 契约拍不足以判定人物真相时不拦（避免空契约把整篇误杀）
        return
    parent_speakers = {"妈妈", "爸爸"}
    # 产品规则：昭昭/灿灿两个孩子都必须能出场。契约拍若漏写某一方，
    # 不能把他当「闯入者」拦掉——那会与「插反应句拆连说」互相抵消。
    canonical_kids = {"昭昭", "灿灿"}
    intruders: dict[str, list[int]] = {}
    for i, row in enumerate(rows, 1):
        speaker = str(row.get("speaker") or "").strip()
        if not speaker or not str(row.get("line") or "").strip():
            continue
        if speaker in cast or speaker in parent_speakers or speaker in canonical_kids:
            continue
        intruders.setdefault(speaker, []).append(i)
    for speaker, line_nos in intruders.items():
        issues.append(
            _issue(
                lines=line_nos,
                kind="保真-角色表外台词",
                desc=(
                    f"{speaker} 在契约里没有任何拍，却在第{line_nos}句说话"
                    f"（本场角色只有 {'、'.join(sorted(cast))}）"
                ),
                fix=(
                    f"删除 {speaker} 的台词，把话留给 {'、'.join(sorted(cast))}；"
                    "**禁止**把对白扩给契约外角色凑字数"
                ),
            ),
        )


def _append_seed_speaker_issues(
    rows: list[dict[str, Any]],
    issues: list[dict[str, Any]],
    *,
    dialogue_seed: list[Any] | None = None,
) -> None:
    """seed 专属短语出现在对白时，speaker 须与 seed 一致。"""
    owners = _seed_unique_phrase_owners(dialogue_seed)
    if not owners:
        return
    for i, row in enumerate(rows, 1):
        sp = str(row.get("speaker") or "").strip()
        line = str(row.get("line") or "").strip()
        if not line or sp not in {"昭昭", "灿灿", "妈妈", "爸爸"}:
            continue
        line_han = "".join(re.findall(r"[\u4e00-\u9fff]", line))
        for phr, want in owners.items():
            if phr not in line and phr not in line_han:
                continue
            if sp == want:
                continue
            issues.append(
                _issue(
                    lines=[i],
                    kind="保真-seed角色",
                    desc=f"第{i}句「{phr}」属 seed 的{want}，现由{sp}说：{line}",
                    fix=f"将该句 speaker 改为{want}，或把短语挪回{want}台词",
                )
            )
            break


RE_AUTH_RULE_SLOT = re.compile(r"谁先|先.+谁|立规|约好|规定|规矩|定规|说好|约定")
RE_AUTH_VICTIM_DISTRESS = re.compile(
    r"找不到|急死|急哭|急得.*哭|想哭|翻遍|本子呢|作业呢|咦，.*呢"
)
RE_AUTH_HIDER_DENY = re.compile(
    r"没看见|乱放还赖|哭什么|赖我|你自己乱放|我没藏|没藏过|你自己找"
)
RE_AUTH_HIDER_ACT = re.compile(
    r"塞进|藏进|塞到|藏到|冷冻层|冷藏层"
)


def _beat_chain_first_speaker(beat_chain: list[Any] | None) -> str:
    for item in beat_chain or []:
        if not isinstance(item, dict):
            continue
        sp = str(item.get("speaker") or "").strip()
        if sp:
            return sp
    return ""


def _authority_victim_hider(
    beat_chain: list[Any] | None,
) -> tuple[str, str]:
    victim = ""
    hider = ""
    for item in beat_chain or []:
        if not isinstance(item, dict):
            continue
        sp = str(item.get("speaker") or "").strip()
        intent = str(item.get("intent") or item.get("beat") or "")
        if not victim and re.search(r"急哭|找不到|急死", intent):
            victim = sp
        if not hider and re.search(r"藏|占物|塞", intent):
            hider = sp
        if victim and hider:
            break
    return victim, hider


def _append_authority_punchline_align_issues(
    story: dict[str, Any],
    rows: list[dict[str, Any]],
    issues: list[dict[str, Any]],
    *,
    beat_chain: list[Any] | None = None,
) -> None:
    """authority_punchline：开场立规归属 + 受害/藏物说话人一致性。"""
    from app.services.gold_story.structure_resolve import (
        CLOSING_MODE_AUTHORITY_PUNCHLINE,
    )

    mode = str(story.get("closing_mode") or "").strip()
    if mode != CLOSING_MODE_AUTHORITY_PUNCHLINE:
        return
    if not rows:
        return

    speakers = [str(r.get("speaker") or "").strip() for r in rows]
    lines = [str(r.get("line") or "").strip() for r in rows]
    beat0 = _beat_chain_first_speaker(beat_chain)
    if beat0 and speakers[0] != beat0:
        issues.append(
            _issue(
                lines=[1],
                kind="保真-权威开场",
                desc=(
                    f"第1句 speaker 为{speakers[0]}，"
                    f"与 beat_chain 首拍立规方({beat0})不一致：{lines[0]}"
                ),
                fix=f"开场第1句须由{beat0}说出立规/约好，勿从中段起跳",
            )
        )

    head = lines[:2]
    if head and not any(RE_AUTH_RULE_SLOT.search(x) for x in head):
        issues.append(
            _issue(
                lines=[1] if len(lines) == 1 else [1, 2],
                kind="保真-权威开场",
                desc="前2句未出现立规/约好槽（谁先/约好/规定等）",
                fix="前2句内补抽象立规句，且由 beat0 立规方说出",
            )
        )
    elif beat0 and head:
        for i, (sp, line) in enumerate(zip(speakers[:2], head), 1):
            if RE_AUTH_RULE_SLOT.search(line) and sp != beat0:
                issues.append(
                    _issue(
                        lines=[i],
                        kind="保真-权威开场",
                        desc=(
                            f"第{i}句立规槽由{sp}说，"
                            f"立规发起方应为{beat0}：{line}"
                        ),
                        fix=f"立规/约好句须由{beat0}说，勿让孩子代立规",
                    )
                )

    victim, hider = _authority_victim_hider(beat_chain)
    if not victim or not hider or victim == hider:
        return
    for i, (sp, line) in enumerate(zip(speakers, lines), 1):
        if sp not in {"昭昭", "灿灿"}:
            continue
        hit_deny = bool(RE_AUTH_HIDER_DENY.search(line))
        hit_distress = bool(RE_AUTH_VICTIM_DISTRESS.search(line))
        # 同句同时命中：按主语「我没藏」归藏物方，否则归急哭受害方
        if hit_deny and hit_distress:
            if re.search(r"我没藏|没藏过", line):
                hit_distress = False
            else:
                hit_deny = False
        if hit_deny and sp != hider:
            issues.append(
                _issue(
                    lines=[i],
                    kind="保真-权威角色",
                    desc=(
                        f"第{i}句撇清/赖对方语义由{sp}说，"
                        f"beat 藏物方为{hider}：{line}"
                    ),
                    fix=f"撇清/否认句须由藏物方{hider}说",
                )
            )
        elif hit_distress and sp != victim:
            issues.append(
                _issue(
                    lines=[i],
                    kind="保真-权威角色",
                    desc=(
                        f"第{i}句急哭/找不到语义由{sp}说，"
                        f"beat 受害方为{victim}：{line}"
                    ),
                    fix=f"急哭/找不到句须由受害方{victim}说",
                )
            )
        if RE_AUTH_HIDER_ACT.search(line) and sp != hider and sp in {"昭昭", "灿灿"}:
            issues.append(
                _issue(
                    lines=[i],
                    kind="保真-权威角色",
                    desc=(
                        f"第{i}句藏物动作由{sp}说，"
                        f"beat 藏物方为{hider}：{line}"
                    ),
                    fix=f"藏/塞本句须由藏物方{hider}说",
                )
            )



def collect_align_issues(
    story: dict[str, Any],
    *,
    structure_type: str,
    mechanism: str,
    closing_intent: str = "",
    beat_chain: list[Any] | None = None,
    conflict_text: str = "",
    dialogue_seed: list[Any] | None = None,
    beat: list[Any] | None = None,
    object_text: str = "",
    mechanism_text: str = "",
) -> list[dict[str, Any]]:
    """类型对齐机审：返回 polish 同构 issue（抽象不变量，非逐篇剧情）。

    特化机审（M5+H / H / F）之外，A–N 一律再跑类型正文契约
    （不依赖 quality_ready）。
    """
    st = str(structure_type or "").strip().upper()
    mech = str(mechanism or "").strip().upper()
    rows = _dialogue_rows(story)
    if not rows:
        return []

    closing = str(closing_intent or story.get("closing_intent") or "").strip()
    conflict = str(
        conflict_text or story.get("conflict_core") or ""
    ).strip()

    issues: list[dict[str, Any]] = []
    if mech == "M5" and st == "H":
        _append_m5_h_issues(
            rows,
            issues,
            closing_intent=closing,
            beat_chain=beat_chain,
            conflict_text=conflict,
        )
    elif st == "H":
        _append_h_generic_issues(rows, issues, closing_intent=closing)
    elif st == "F":
        from app.services.daily_story.story_types.f.validate import append_f_align_issues

        append_f_align_issues(
            rows,
            issues,
            mechanism=mech,
            dialogue_seed=dialogue_seed,
            beat_chain=beat_chain,
            beat=beat,
            closing_intent=closing,
            conflict_text=conflict,
            object_text=object_text,
            mechanism_text=mechanism_text,
        )
    if st in {"B", "F"}:
        _append_pad_filler_issues(rows, issues)
    else:
        # 全类型拦扩写灌尾巴；B/F 仍走上面含好不好的完整版
        _append_pad_filler_issues(rows, issues, max_tail_filler=99)

    if st == "N":
        _append_n_contract_role_issues(rows, issues, beat_chain=beat_chain)

    if st == "N":
        _append_n_token_grammar_issues(rows, issues, beat_chain=beat_chain)

    # 只对 N 硬拦孩子连说：N 是「两人手 + 家长额度封顶」结构，连说是设计缺陷。
    # 其它类型（M8 互打/A 类破功等）本就需要同一孩子连说，不能一刀切。
    # 纯动作台词：全类型一律拒绝（对话稿不允许舞台说明当台词）
    _append_pure_action_issues(rows, issues)

    if st == "N":
        _append_consecutive_sibling_issues(rows, issues)
        _append_second_kid_ask_usurp_issues(
            rows, issues, beat_chain=beat_chain
        )

    _append_cast_membership_issues(rows, issues, beat_chain=beat_chain)

    _append_seed_speaker_issues(rows, issues, dialogue_seed=dialogue_seed)

    _append_authority_punchline_align_issues(
        story,
        rows,
        issues,
        beat_chain=beat_chain,
    )

    _append_type_contract_align_issues(story, structure_type=st, issues=issues)

    seen: set[tuple[str, int, str]] = set()
    out: list[dict[str, Any]] = []
    for item in issues:
        kind = str(item.get("kind") or "")
        desc = str(item.get("desc") or "")
        line_nos = item.get("lines") or []
        key = (kind, int(line_nos[0]) if line_nos else 0, desc)
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _append_type_contract_align_issues(
    story: dict[str, Any],
    *,
    structure_type: str,
    issues: list[dict[str, Any]],
) -> None:
    """A–N 类型正文契约 → gold_chat issue（绕过 quality_ready）。"""
    from app.services.daily_story.story_types import (
        STORY_TYPE_LABELS,
        append_type_body_validation_errors,
    )

    st = str(structure_type or "").strip().upper()
    if st not in STORY_TYPE_LABELS:
        return

    rows = _dialogue_rows(story)
    n = len(rows)
    if n < 6:
        return

    mini = dict(story)
    mini["story_type"] = st
    punch = str(mini.get("punchline_explain") or "").strip()
    if not punch.upper().startswith(st):
        label = STORY_TYPE_LABELS.get(st, st)
        mini["punchline_explain"] = f"{st}类{label}，{punch}".strip("，")
    # 保留旁路收束模式，供 G validate 分支
    mode = str(story.get("closing_mode") or "").strip()
    if mode:
        mini["closing_mode"] = mode

    errors: list[str] = []
    append_type_body_validation_errors(mini, errors, for_gold_chat=True)
    if not errors:
        return

    # 契约问题多落在中后段；给精修可操作行号
    line_nos = list(range(max(1, n - 5), n + 1))
    for err in errors:
        issues.append(
            {
                "lines": line_nos,
                "kind": "对齐-类型契约",
                "desc": err,
                "fix": "按类型契约改对白：补齐缺槽、删错型收束，勿另起第二轮",
            }
        )


def _line_lens(dialogue: list[Any]) -> list[int]:
    return [
        len(str(item.get("line") or ""))
        for item in dialogue
        if isinstance(item, dict) and str(item.get("line") or "").strip()
    ]


_RE_INTENT_TRIGGER = re.compile(
    r"责备|批评|指责|质问|训斥|催促|责骂|立规|约好|紧张|冲突",
)
_RE_INTENT_BLAME = re.compile(r"责备|批评|指责|训斥|责骂")
_RE_INTENT_RULE = re.compile(r"立规|约好|规定|规矩|定规|说好|约定")
_RE_INTENT_RULE_ANNOUNCE = re.compile(
    r"宣布.{0,12}(?:规则|比赛|竞赛|抢吃|谁先|先吃|先用)",
)
_RE_INTENT_ACCOUNTABILITY = re.compile(r"定责|问责|归责|追责|判责|分责")
_RE_INTENT_INTERRUPT = re.compile(r"插嘴|打断|岔|救场|转移|离谱|请求|打岔")
_RE_INTENT_DEFEND = re.compile(r"辩解|推托|忘|本来|没做|没写|推脱|借口")
_RE_INTENT_STUN = re.compile(r"愣|停|放下|叹气|接不住|傻眼")
_RE_INTENT_REBUTTAL = re.compile(r"质疑|反驳|嘴硬|否认|纠正")
_RE_INTENT_STALL = re.compile(
    r"耍赖|嬉皮笑脸|东拉西扯|转移话题|拖延|磨蹭|打哈哈|插科打诨"
)
_RE_INTENT_DIRECTIVE = re.compile(r"(?:让|叫|喊|催|要求)(?:昭昭|灿灿)")
_RE_STALL_LINE = re.compile(
    r"真好看|真漂亮|漂亮|好帅|真帅|真可爱|"
    r"先(?:歇|休息|等会|等等)|等会|待会|一会儿|"
    r"行不行|能不能|可不可以|别急|聊点|说点别的|"
    r"我(?:手疼|累|渴|饿)"
)
_RE_REBUTTAL_LINE = re.compile(
    r"(?:不是|不叫|不算|才不|哪是|明明|我(?:才|明明|就是|那叫))"
)
_RE_PARENT_TRIGGER_LINE = re.compile(
    r"(?:怎么|为什么|又|还不|还没有|别(?:闹|皮|吵|糊弄)|"
    r"气死|烦死|像什么话|不像话)",
)
_RE_BLAME_LINE = re.compile(
    r"(?:作业|没写|没做|磨蹭|别拖|写完了吗|赶快写|还不写|"
    r"像什么样子|批评|责备)",
)
_RE_ACCOUNTABILITY_LINE = re.compile(
    r"(?:谁先|先(?:动手|推|打|抢|弄|拿)|不对|不该|有错|负责|责任|道歉|补上|补完)",
)
_RE_STUN_REACT_LINE = re.compile(r"你说什么|手停|停在半空|愣")
_RE_DEFEND_LINE = re.compile(
    r"本来|忘了|就是没|还没|得写|要写|马上去|这就去|打算写",
)
_RE_INTERRUPT_OFFER_LINE = re.compile(
    r"(?:你(?:先|来)|试试|摸(?:摸)?|打(?:我|一下)|划算|Q弹|屁股|"
    r"我(?:来|给)|要不)",
)
_RE_STUN_LINE = re.compile(
    r"(?:愣(?:住|了|神)?|傻眼|接不住|说不出|语塞|一时|手停|停在半空|"
    r"(?:叹|沉)|(?:放|搁)下(?:筷|碗|笔|手))",
)
_OPENING_INTENT_STOP = frozenset(
    {
        "气氛",
        "认真",
        "提出",
        "自己",
        "批评",
        "责骂",
        "紧张",
        "已经",
        "开始",
        "场面",
        "打断",
        "请求",
    },
)


def resolve_story_beat_chain(story: dict[str, Any]) -> list[Any]:
    chain = story.get("gold_beat_chain")
    if isinstance(chain, list) and chain:
        return chain
    sc = story.get("scene_contract")
    if isinstance(sc, dict):
        nested = sc.get("beat_chain")
        if isinstance(nested, list) and nested:
            return nested
    return []


def _beat_chain_entries(chain: list[Any]) -> list[tuple[int, dict[str, Any]]]:
    out: list[tuple[int, dict[str, Any]]] = []
    for index, item in enumerate(chain, 1):
        if not isinstance(item, dict):
            continue
        beat_no = item.get("beat")
        if isinstance(beat_no, int) and beat_no > 0:
            out.append((beat_no, item))
        else:
            out.append((index, item))
    return out


def _opening_authority_intent_kind(intent: str) -> str:
    """自由文本 beat 标签归一成 opening 权威触发类别；只看冒号前标签。"""
    text = str(intent or "")
    tag = re.split(r"[：:]", text, maxsplit=1)[0].strip()
    if _RE_INTENT_BLAME.search(tag):
        return "blame"
    if _RE_INTENT_RULE.search(tag) or _RE_INTENT_RULE_ANNOUNCE.search(text):
        return "rule"
    if _RE_INTENT_ACCOUNTABILITY.search(tag):
        return "accountability"
    if _RE_INTENT_DIRECTIVE.search(text):
        return "directive"
    if _RE_INTENT_TRIGGER.search(tag):
        return "trigger"
    return ""


def _intent_speech_acts(intent: str) -> set[str]:
    """优先用 intent 冒号前标签，避免「愣住：…批评」整段误标 trigger。"""
    text = str(intent or "")
    tag = text.split("：", 1)[0].strip()
    body = text.split("：", 1)[1].strip() if "：" in text else ""
    acts: set[str] = set()
    if _opening_authority_intent_kind(text):
        acts.add("trigger")
    elif body and (
        _RE_INTENT_TRIGGER.search(body)
        or _RE_INTENT_RULE.search(body)
        or _RE_INTENT_ACCOUNTABILITY.search(body)
    ) and not _RE_INTENT_STUN.search(tag):
        acts.add("trigger")
    if _RE_INTENT_INTERRUPT.search(tag) or (
        body and _RE_INTENT_INTERRUPT.search(body) and not acts
    ):
        acts.add("interrupt")
    if _RE_INTENT_DEFEND.search(tag) or (
        body and _RE_INTENT_DEFEND.search(body) and not acts
    ):
        acts.add("defend")
    if _RE_INTENT_STUN.search(tag) or (
        body and _RE_INTENT_STUN.search(body) and "愣" in tag
    ):
        acts.add("stun")
    if _RE_INTENT_REBUTTAL.search(tag) or (
        body and _RE_INTENT_REBUTTAL.search(body) and not acts
    ):
        acts.add("rebuttal")
    if _RE_INTENT_STALL.search(tag) or (
        body and _RE_INTENT_STALL.search(body) and not acts
    ):
        acts.add("stall")
    if not acts:
        if (
            _RE_INTENT_TRIGGER.search(text)
            or _RE_INTENT_RULE.search(text)
            or _RE_INTENT_ACCOUNTABILITY.search(text)
        ):
            acts.add("trigger")
        if _RE_INTENT_INTERRUPT.search(text):
            acts.add("interrupt")
        if _RE_INTENT_DEFEND.search(text):
            acts.add("defend")
        if _RE_INTENT_STUN.search(text):
            acts.add("stun")
        if _RE_INTENT_REBUTTAL.search(text):
            acts.add("rebuttal")
        if _RE_INTENT_STALL.search(text):
            acts.add("stall")
    return acts


def _intent_anchor_tokens(intent: str) -> list[str]:
    body = str(intent or "").split("：", 1)[-1].strip()
    parts = re.findall(r"[\u4e00-\u9fff]{2,}", body)
    return [p for p in parts if p not in _OPENING_INTENT_STOP][:6]


# 列举型 intent：抽象描述「说出一串/几个/一堆 名字/词」，字面 anchor 与
# 真实对白毫无交集（intent 是叙述，对白是人名罗列）。这类拍按**列举形态**认：
# 对白里有 ≥2 个并列项即算落地。不绑剧情词，只看结构。
_RE_LIST_INTENT = re.compile(
    r"(?:一串|几个|一堆|一连串|好些个|若干个)\s*(?:编的)?"
    r"(?:名字|名称|人名|词|词语|称呼)"
)
_RE_LIST_ITEM = re.compile(r"[\u4e00-\u9fffA-Za-z0-9]{2,8}")


def _line_looks_like_listing(line: str) -> bool:
    """对白是否在**罗列一串同类事物**（人名/词串）。

    只认两种强形态，避免把普通口语的逗号当列举：
    1) 顿号分隔 ≥2 项（「小明、小红、小刚」）——顿号本身就是并列标记；
    2) 「叫/有/是」+ A、B（逗号分隔 ≥2 项且都很短，像名字）。
    """
    text = str(line or "")
    if "、" in text:
        parts = [
            p.strip("。！？，、… 　")
            for p in re.split(r"[、]", text)
            if p.strip("。！？，、… 　")
        ]
        if len([p for p in parts if _RE_LIST_ITEM.fullmatch(p)]) >= 2:
            return True
    # 「叫A，B」「有A，B，C」：引导词后接 ≥2 个**很短**的项（2–4 字，像名字/词）
    m = re.search(r"(?:叫|有)([^。！？]{4,60})", text)
    if m:
        tail = m.group(1)
        parts = [
            p.strip("。！？，、… 　")
            for p in re.split(r"[，,、]", tail)
            if p.strip("。！？，、… 　")
        ]
        short = [p for p in parts if 2 <= len(p) <= 4]
        if len(short) >= 2:
            return True
    return False


_RE_HAN_RUN = re.compile(r"[\u4e00-\u9fff]+")


def _looks_like_dialogue_line(line: str) -> bool:
    """这句话是否像「对在场某人说的话」。

    只有像对白的句子才允许走宽松的语义兜底；叙述句没有对话对象，
    即便语义命中某拍也不能算台词落地。
    """
    text = str(line or "").strip()
    if not text:
        return False
    if _looks_like_pure_action(text):
        return False
    return bool(_DIALOGUE_MARKER_RE.search(text))


def _bigrams(text: str) -> set[str]:
    """中文双字词集合（滑窗）。用于跨改写的语义近邻判定。"""
    out: set[str] = set()
    for run in _RE_HAN_RUN.findall(str(text or "")):
        for i in range(len(run) - 1):
            out.add(run[i : i + 2])
    return out


def _intent_line_overlap(intent: str, line: str, *, need: int = 3) -> bool:
    """intent 与 line 的双字词交集是否够多（容忍口语改写）。

    机检的 anchor 是**叙述性整句**（「宣布要记录昭昭说的每一句话」），
    真实对白是口语改写（「我拿本子记下你说的每句话」），字面包含判定
    必然失效——这不是模型没写，是判词认不出（#87 实测：18 次误报缺拍）。

    这里改用双字词交集：intent 与 line 共享 ≥``need`` 个不同的双字词即算
    落地。阈值取 3 是实测出来的：取 2 时「你说的这些名字都是谁」会误命中
    「我拿本子记下你说的每句话」（只共享「你说/说的」），取 3 才分得开。
    """
    a = _bigrams(intent)
    if len(a) < 4:
        return False
    b = _bigrams(line)
    return len(a & b) >= need


def _anchor_matches_line(anchor: str, line: str) -> bool:
    """锚词是否落地到对白；容忍口语对压缩 intent 的改写。

    beat intent 常是压缩短语（如「催关灯」「洗袜子」），对白里说成
    「去把灯关了」「把袜子洗了」——字面包含判定会漏，故再接受两种等价：
    相邻二字倒装（关灯↔灯关）；三字以上锚词的字面全覆盖（把字句拆装）。

    叠字对（「昭昭」倒装仍是「昭昭」）不构成倒装，只等于"锚词局部二字被
    对白含住"；长叙事锚词里的人名靠这条会退化命中任意出现该名字的句子
    （beat 顺序校验随之误报），故跳过。
    """
    if not anchor or not line:
        return False
    if anchor in line:
        return True
    han = "".join(re.findall(r"[\u4e00-\u9fff]", line))
    if not han:
        return False
    for i in range(len(anchor) - 1):
        pair = anchor[i : i + 2]
        if len(pair) == 2 and pair[0] != pair[1] and pair[1] + pair[0] in han:
            return True
    if len(anchor) >= 3 and all(ch in han for ch in anchor):
        return True
    return False


_RE_OPENING_META_PREFIX = re.compile(
    r"^(?:(?:一本正经|继续|嘴硬|荒诞)?"
    r"(?:质疑|反驳|追问|设问|发问|回答|作答|解释|自洽|交代旧事|交代|讲述)"
    r"|(?:说|表示|认为|问))+"
)


def _opening_semantic_clauses(intent: str) -> list[str]:
    """从 beat intent 提取少量语义分句；仅用于抽象 speech-act 兜底，不绑定单篇词表。"""
    body = str(intent or "").split("：", 1)[-1].strip()
    out: list[str] = []
    for raw in re.split(r"[，,。；;！？?!、]", body):
        text = _RE_OPENING_META_PREFIX.sub("", raw.strip())
        text = "".join(re.findall(r"[\u4e00-\u9fff]", text))
        if len(text) >= 2:
            out.append(text)
    return out[:4]


def _han_bigrams(text: str) -> set[str]:
    return {text[i : i + 2] for i in range(max(0, len(text) - 1))}


def _opening_clause_matches_line(clause: str, line_han: str) -> bool:
    if clause in line_han:
        return True
    if len(clause) < 2 or len(line_han) < 2:
        return False
    common = _han_bigrams(clause) & _han_bigrams(line_han)
    return len(common) >= (2 if len(clause) >= 4 else 1)


def _opening_rebuttal_matches(intent: str, line: str) -> bool:
    """“质疑/嘴硬反驳”允许自然改写，但须同时命中反驳口气与多段语义。"""
    if not _RE_REBUTTAL_LINE.search(str(line or "")):
        return False
    clauses = _opening_semantic_clauses(intent)
    if not clauses:
        return False
    line_han = "".join(re.findall(r"[\u4e00-\u9fff]", str(line or "")))
    hits = sum(1 for clause in clauses if _opening_clause_matches_line(clause, line_han))
    required = 2 if len(clauses) >= 2 else 1
    return hits >= required

def _opening_rule_semantic_matches(intent: str, line: str) -> bool:
    """立规可由家长或年长孩子发起；允许自然祈使句语义落地，但须有命令/约束口气。"""
    text = str(line or "").strip()
    if not text:
        return False
    if RE_AUTH_RULE_SLOT.search(text):
        return True
    if not re.search(r"别|不许|不准|先|要|得|给我|快|赶紧|行不行|听话", text):
        return False
    clauses = _opening_semantic_clauses(intent)
    if not clauses:
        return False
    line_han = "".join(re.findall(r"[\u4e00-\u9fff]", text))
    hits = sum(1 for clause in clauses if _opening_clause_matches_line(clause, line_han))
    return hits >= 1


_RE_OPENING_DIRECTIVE_ACTION = re.compile(
    r"收|放|归|写|做|拿|捡|扫|洗|关|整|补|读|学|穿|吃|喝|睡|起|坐|站|走|来|去|回"
)
_RE_OPENING_DIRECTIVE_MARKER = re.compile(
    r"别|不许|不准|给我|赶紧|听话|把"
)
_RE_OPENING_DIRECTIVE_ADDRESS = re.compile(r"^(?:昭昭|灿灿)[，,]")


def _opening_directive_matches(intent: str, line: str) -> bool:
    """家长 directive beat：只认可说出口的指令，禁 intent 原句冒充对白。"""
    text = str(line or "").strip()
    if not text or not _RE_OPENING_DIRECTIVE_ACTION.search(text):
        return False
    if not (
        _RE_OPENING_DIRECTIVE_ADDRESS.search(text)
        or _RE_OPENING_DIRECTIVE_MARKER.search(text)
    ):
        return False
    clauses = _opening_semantic_clauses(intent)
    if not clauses:
        return False
    line_han = "".join(re.findall(r"[\u4e00-\u9fff]", text))
    hits = sum(1 for clause in clauses if _opening_clause_matches_line(clause, line_han))
    return hits >= 1


_RE_PARENT_LATE_REACTION_PREFIX = re.compile(
    r"^(?:你(?:刚才)?说(?:啥|什么)|你说的(?:啥|什么)|"
    r"你在说(?:啥|什么)|你再说一遍|你说清楚|"
    r"(?:我|妈妈|爸爸)(?:为什么|为啥|干嘛|干吗|凭什么)(?:还)?(?:要|得|非得))"
)


def _parent_trigger_starts_as_late_reaction(line: str) -> bool:
    """家长首分句若明显是在回应前文，就不能再靠后半句补成 beat1 trigger。"""
    first_clause = re.split(r"[，,。！？?!；;]", str(line or "").strip(), maxsplit=1)[0].strip()
    return bool(first_clause and _RE_PARENT_LATE_REACTION_PREFIX.search(first_clause))


def _line_fulfills_beat(
    speaker: str,
    line: str,
    entry: dict[str, Any],
) -> bool:
    expected = str(entry.get("speaker") or "").strip()
    if not expected or speaker != expected:
        return False
    intent = str(entry.get("intent") or entry.get("beat") or "")
    line = str(line or "").strip()
    if not line:
        return False
    # 纯动作句不算落地：对话稿里动作不是台词，它不可能「说出」任何一拍。
    # （例如 seed 里的叙述句「磕巴念绕口令，口误笑场」被原样抄进对白时，
    # 既不是有效台词，也不能拿它去满足 beat。）
    if _looks_like_pure_action(line):
        return False
    acts = _intent_speech_acts(intent)
    if (
        "trigger" in acts
        and speaker in {"妈妈", "爸爸"}
        and _parent_trigger_starts_as_late_reaction(line)
    ):
        return False
    if "trigger" in acts and speaker in {"妈妈", "爸爸"}:
        # 权威触发明确点名某个孩子时，不能让“正在训另一个孩子”的家长句
        # 即使碰巧命中通用 anchor，也不能误充 beat1；不点名的自然口语仍可匹配。
        named_kids = {name for name in ("昭昭", "灿灿") if name in intent}
        line_kids = {name for name in ("昭昭", "灿灿") if name in line}
        if named_kids and line_kids and not (named_kids & line_kids):
            return False
    if "trigger" in acts and speaker in {"妈妈", "爸爸"}:
        if _opening_authority_intent_kind(intent) == "directive":
            # directive 常把 "家长指令 + 孩子动作" 写在同一条 intent 里。
            # 必须只认家长可说出口的指令，不能因整句复读 intent 同时命中
            # "收玩具/踢积木" 等 anchor，就把剧情描述判成对白。
            return _opening_directive_matches(intent, line)
    if _RE_LIST_INTENT.search(intent) and _line_looks_like_listing(line):
        # 列举型拍：intent 是叙述（「报出一串编的名字」），对白是人名罗列，
        # 字面 anchor 必然对不上，按列举形态认落地。
        return True
    anchors = _intent_anchor_tokens(intent)
    if anchors and any(_anchor_matches_line(token, line) for token in anchors):
        return True
    # 口语改写兜底：叙述性 intent 与对白字面必然不同，用双字词交集认落地。
    # 只对**像对白的句子**启用——叙述句（「蛋挞烤鸭上桌，绕口令抢吃」）
    # 即使语义命中，也不是台词，不能拿它满足拍（我们要的是对话稿）。
    if _looks_like_dialogue_line(line) and _intent_line_overlap(intent, line):
        return True
    if "rebuttal" in acts and _opening_rebuttal_matches(intent, line):
        return True
    if "stall" in acts and speaker in {"昭昭", "灿灿"}:
        return bool(_RE_STALL_LINE.search(line))
    if "trigger" in acts and speaker in {"妈妈", "爸爸"}:
        authority_kind = _opening_authority_intent_kind(intent)
        if authority_kind == "blame":
            if _RE_STUN_REACT_LINE.search(line) and not _RE_BLAME_LINE.search(line):
                return False
            if anchors and any(token in line for token in anchors):
                return True
            # 责备型 beat1 必须真的说出责备/作业等内容；
            # 裸“怎么/为什么”只能说明是疑问，不能证明它在落地本 beat。
            return bool(_RE_BLAME_LINE.search(line))
        if authority_kind == "rule":
            if _opening_rule_semantic_matches(intent, line):
                return True
            # 家长立规/游戏设置常是自然口语，没有命令口气也应按 beat
            # intent 的多段语义落地；至少命中除一段外的其余分句。
            clauses = _opening_semantic_clauses(intent)
            if len(clauses) < 2:
                return False
            line_han = "".join(re.findall(r"[\u4e00-\u9fff]", line))
            hits = sum(
                1 for clause in clauses
                if _opening_clause_matches_line(clause, line_han)
            )
            if hits < max(1, len(clauses) - 1):
                return False
            if not re.search(r"[我你]|别|把|谁|怎么|为什么", line):
                return False
            from app.services.gold_story.scene import looks_like_narration_line

            return not looks_like_narration_line(line)
        if authority_kind == "accountability":
            if _RE_STUN_REACT_LINE.search(line) and not (
                _RE_BLAME_LINE.search(line) or _RE_ACCOUNTABILITY_LINE.search(line)
            ):
                return False
            # 定责型 beat1 至少要有责任/责备实义；不能让无对象的
            # “怎么/为什么”反问借通用 trigger regex 冒充定责。
            return bool(
                _RE_ACCOUNTABILITY_LINE.search(line)
                or _RE_BLAME_LINE.search(line)
            )
        if authority_kind == "directive":
            # 契约常把“家长发出指令 + 孩子随后动作”写在同一 beat intent，
            # 但 beat.speaker 仍是家长。此处只要求家长可说出口的指令部分落地，
            # 不要求家长台词复述孩子动作结果。
            return _opening_directive_matches(intent, line)
        return bool(_RE_PARENT_TRIGGER_LINE.search(line))
    if (
        "trigger" in acts
        and speaker in {"昭昭", "灿灿"}
        and _opening_authority_intent_kind(intent) == "rule"
    ):
        if _opening_rule_semantic_matches(intent, line):
            return True
        # 孩子发起的规则/游戏设置常是自然口语（如 #117 "炸鸡和烤冷面
        # 摆好了，咱们玩猜食物游戏！"），没有家长式命令口气也应按
        # beat intent 的多段语义落地；要求所有语义分句都有对应。
        clauses = _opening_semantic_clauses(intent)
        if not clauses:
            return False
        line_han = "".join(re.findall(r"[\u4e00-\u9fff]", line))
        hits = sum(
            1 for clause in clauses
            if _opening_clause_matches_line(clause, line_han)
        )
        required = len(clauses) if len(clauses) >= 2 else 1
        if hits < required:
            return False
        from app.services.gold_story.scene import looks_like_narration_line

        return not looks_like_narration_line(line)
    if "defend" in acts and speaker in {"昭昭", "灿灿"}:
        return bool(_RE_DEFEND_LINE.search(line))
    if "interrupt" in acts and speaker in {"昭昭", "灿灿"}:
        return bool(_RE_INTERRUPT_OFFER_LINE.search(line))
    if "stun" in acts:
        if anchors and any(token in line for token in anchors):
            return True
        return bool(_RE_STUN_LINE.search(line))
    if "defend" in acts and speaker in {"妈妈", "爸爸"}:
        return False
    return False


def _first_line_matching_beat(
    rows: list[dict[str, Any]],
    entry: dict[str, Any],
) -> int | None:
    for line_no, row in enumerate(rows, 1):
        speaker = str(row.get("speaker") or "").strip()
        line = str(row.get("line") or "").strip()
        if not line:
            continue
        if _line_fulfills_beat(speaker, line, entry):
            return line_no
    return None


def _fulfill_beats_in_dialogue_order(
    rows: list[dict[str, Any]],
    entries: list[tuple[int, dict[str, Any]]],
) -> dict[int, int]:
    """按 beat 顺序扫描对白：一句不能同时充当后序 beat（如责备兼愣住）。"""
    found: dict[int, int] = {}
    beat_idx = 0
    for line_no, row in enumerate(rows, 1):
        if beat_idx >= len(entries):
            break
        speaker = str(row.get("speaker") or "").strip()
        line = str(row.get("line") or "").strip()
        if not line:
            continue
        beat_no, entry = entries[beat_idx]
        if _line_fulfills_beat(speaker, line, entry):
            found[beat_no] = line_no
            beat_idx += 1
    return found


def _beat_summary(entry: dict[str, Any], beat_no: int) -> str:
    speaker = str(entry.get("speaker") or "").strip() or "?"
    intent = str(entry.get("intent") or entry.get("beat") or "").strip()
    head = f"beat={beat_no}·{speaker}"
    return f"{head}（{intent}）" if intent else head


def collect_opening_causality_issues(
    story: dict[str, Any],
    beat_chain: list[Any] | None = None,
    *,
    mom_lines_max: int | None = None,
) -> list[dict[str, Any]]:
    """开场因果：beat_chain 前段须在可见对白中按序落地，setting 不算。"""
    chain = beat_chain if isinstance(beat_chain, list) else resolve_story_beat_chain(story)
    if len(chain) < 2:
        return []
    rows = _dialogue_rows(story)
    if not rows:
        return []

    entries = _beat_chain_entries(chain)
    opening = entries[: min(3, len(entries))]
    if len(opening) < 2:
        return []

    fulfilled = _fulfill_beats_in_dialogue_order(rows, opening)
    mom_max = 1 if mom_lines_max is None else max(0, int(mom_lines_max))
    mom_count = sum(
        1 for row in rows if str(row.get("speaker") or "").strip() == "妈妈"
    )
    mom_quota_full = mom_count >= mom_max and mom_max >= 0

    issues: list[dict[str, Any]] = []

    def _quota_fix(base: str) -> str:
        if not mom_quota_full:
            return base
        return (
            f"{base}；妈妈额度已满，压缩后段非必要妈妈句/重复收场，"
            "在前段对白补触发事件（勿写进 setting）"
        )

    # 触发型 beat1（责备/定责/立规）就是开场因果起点：必须由第1句落地。
    # 不能允许“第7句才补一个妈妈触发，再从后面挑另一个 beat2”来伪造顺序。
    first_row = rows[0]
    first_sp = str(first_row.get("speaker") or "").strip()
    first_line = str(first_row.get("line") or "").strip()
    beat1_no, beat1_entry = opening[0]
    beat2_no, beat2_entry = opening[1]
    beat1_acts = _intent_speech_acts(str(beat1_entry.get("intent") or ""))
    if "trigger" in beat1_acts and not _line_fulfills_beat(
        first_sp, first_line, beat1_entry
    ):
        issues.append(
            {
                "lines": [1],
                "kind": "开场因果",
                "desc": (
                    f"第1句未落地{_beat_summary(beat1_entry, beat1_no)}；"
                    "触发型 beat1 必须是可见对白开场，setting/背景和后段补票都不算"
                ),
                "fix": _quota_fix(
                    f"由{beat1_entry.get('speaker')}在第1句说出"
                    f"触发事件（{beat1_entry.get('intent')}），"
                    f"再进入{beat2_entry.get('speaker')}的后续反应",
                ),
                "missing_beat": {
                    "beat": beat1_no,
                    "intent": str(beat1_entry.get("intent") or "").strip(),
                },
                "before_reaction_beat": beat2_no,
                "before_line_no": 1,
            },
        )

    for idx in range(len(opening) - 1):
        beat_i_no, beat_i = opening[idx]
        beat_j_no, beat_j = opening[idx + 1]
        line_i = fulfilled.get(beat_i_no)
        line_j = fulfilled.get(beat_j_no) or _first_line_matching_beat(rows, beat_j)
        if line_j is None:
            continue
        if line_i is None:
            line_i = _first_line_matching_beat(rows, beat_i)
        if line_i is None:
            issues.append(
                {
                    "lines": [line_j],
                    "kind": "开场因果",
                    "desc": (
                        f"第{line_j}句已出现{_beat_summary(beat_j, beat_j_no)}，"
                        f"但缺少{_beat_summary(beat_i, beat_i_no)}"
                    ),
                    "fix": _quota_fix(
                        f"在第{line_j}句之前补{_beat_summary(beat_i, beat_i_no)}，"
                        f"由{beat_i.get('speaker')}当场说出，勿写进 setting",
                    ),
                    "missing_beat": {
                        "beat": beat_i_no,
                        "intent": str(beat_i.get("intent") or "").strip(),
                    },
                    "before_reaction_beat": beat_j_no,
                    "before_line_no": line_j,
                },
            )
            continue
        if not _line_fulfills_beat(
            str(rows[line_i - 1].get("speaker") or "").strip(),
            str(rows[line_i - 1].get("line") or "").strip(),
            beat_i,
        ):
            issues.append(
                {
                    "lines": [line_i],
                    "kind": "开场因果",
                    "desc": (
                        f"第{line_i}句 speaker 为{rows[line_i - 1].get('speaker')}，"
                        f"但未体现{_beat_summary(beat_i, beat_i_no)}"
                    ),
                    "fix": _quota_fix(
                        f"改写第{line_i}句或在其前插入，使{beat_i.get('speaker')}"
                        f"说出触发（{beat_i.get('intent')}）",
                    ),
                    "missing_beat": {
                        "beat": beat_i_no,
                        "intent": str(beat_i.get("intent") or "").strip(),
                    },
                    "before_reaction_beat": beat_j_no,
                    "before_line_no": line_j,
                },
            )
            continue
        if line_i >= line_j:
            issues.append(
                {
                    "lines": [line_j],
                    "kind": "开场因果",
                    "desc": (
                        f"{_beat_summary(beat_j, beat_j_no)}在第{line_j}句，"
                        f"不晚于{_beat_summary(beat_i, beat_i_no)}（第{line_i}句）"
                    ),
                    "fix": _quota_fix(
                        f"将{_beat_summary(beat_i, beat_i_no)}移到第{line_j}句之前，"
                        f"再保留{_beat_summary(beat_j, beat_j_no)}",
                    ),
                    "missing_beat": {
                        "beat": beat_i_no,
                        "intent": str(beat_i.get("intent") or "").strip(),
                    },
                    "before_reaction_beat": beat_j_no,
                    "before_line_no": line_j,
                },
            )
    return issues


def format_opening_causality_hard_error(issue: dict[str, Any]) -> str:
    desc = str(issue.get("desc") or "").strip()
    mb = issue.get("missing_beat")
    if isinstance(mb, dict):
        beat = mb.get("beat")
        intent = str(mb.get("intent") or "").strip()
        before = issue.get("before_reaction_beat")
        before_line = issue.get("before_line_no")
        extra = f"缺 beat={beat} {intent}".strip()
        if before is not None:
            extra += f"，须早于 beat={before}"
        if before_line is not None:
            extra += f"（第{before_line}句前）"
        return f"opening_causality:{extra}；{desc}"
    return f"opening_causality:{desc}"


def collect_opening_causality_hard_errors(
    story: dict[str, Any],
    *,
    beat_chain: list[Any] | None = None,
    mom_lines_max: int | None = None,
) -> list[str]:
    return [
        format_opening_causality_hard_error(item)
        for item in collect_opening_causality_issues(
            story,
            beat_chain,
            mom_lines_max=mom_lines_max,
        )
    ]


def opening_causality_passes(
    story: dict[str, Any],
    beat_chain: list[Any] | None = None,
    *,
    mom_lines_max: int | None = None,
) -> bool:
    return not collect_opening_causality_issues(
        story, beat_chain, mom_lines_max=mom_lines_max,
    )


def gold_chat_low_info_indexes(dialogue: Any) -> list[int]:
    """低信息行（1-based）：去空白后 ≤2 字，末句豁免（短收场属正常结构）。"""
    rows = [
        x for x in (dialogue or []) if isinstance(x, dict) and str(x.get("line") or "").strip()
    ]
    count = len(rows)
    return [
        i + 1
        for i, item in enumerate(rows)
        if i < count - 1 and len(str(item.get("line") or "").strip()) <= 2
    ]


def gold_chat_effective_min_chars(dialogue: Any) -> int:
    """联合判据下的正文总字数下限：句数达标时放宽一行，余量给自然波动。

    与 ``validate_chat_hard`` 同一口径，供本地补字链路复用，避免「为凑 240
    字回灌句尾粒子」反而被终检判成语病。
    """
    from app.services.daily_story.prompts import DAILY_STORY_BODY_CHARS_MIN
    from app.services.gold_story.scene import CHAT_LINE_COUNT_MIN, CHAT_MAX_LINE_CHARS

    rows = [
        x for x in (dialogue or []) if isinstance(x, dict) and str(x.get("line") or "").strip()
    ]
    low_info = len(gold_chat_low_info_indexes(rows))
    if len(rows) - low_info >= CHAT_LINE_COUNT_MIN:
        return DAILY_STORY_BODY_CHARS_MIN - CHAT_MAX_LINE_CHARS
    return DAILY_STORY_BODY_CHARS_MIN


def validate_chat_hard(
    story: dict[str, Any],
    *,
    banned_literals: list[str] | None = None,
    source_type: str = "",
    mom_lines_max: int | None = None,
    parent_lines_max: int | None = None,
    dad_lines_max: int | None = None,
) -> list[str]:
    """gold_chat / 成品对白 hard 校验。

    家长预算口径（与 expand._trim_gold_chat_mom_lines 共用同一契约）：
    家长合计≤parent_lines_max（默认取 mom_lines_max），妈妈≤mom_lines_max，
    爸爸≤dad_lines_max（默认取 parent_lines_max，不再硬编码 1）。
    """
    from statistics import mean

    from app.services.gold_story.scene import (
        ALLOWED_SPEAKERS,
        CHAT_AVG_LINE_CHARS_MAX,
        CHAT_LINE_COUNT_MIN,
        CHAT_MAX_LINE_CHARS,
        MOM_BANNED_IN_LINE,
        MOM_PREACH_JIAO_RE,
        TUTORIAL_RESIDUE,
        chat_line_cap,
        collect_voice_errors,
        parent_line_looks_preachy,
    )
    from app.services.daily_story.prompts import (
        DAILY_STORY_BODY_CHARS_MAX,
        DAILY_STORY_BODY_CHARS_MIN,
        dialogue_total_chars,
    )

    errors: list[str] = []
    dialogue = story.get("dialogue") or []
    if not isinstance(dialogue, list):
        return ["dialogue 不是列表"]

    allowed = set(ALLOWED_SPEAKERS)
    from app.services.gold_story.scene import resolve_parent_lines_budget

    mom_max, dad_max, parent_max = resolve_parent_lines_budget(
        story,
        mom_lines_max=mom_lines_max,
        dad_lines_max=dad_lines_max,
        parent_lines_max=parent_lines_max,
    )
    mom_count = 0
    dad_count = 0
    parent_count = 0

    for i, item in enumerate(dialogue):
        if not isinstance(item, dict):
            errors.append(f"dialogue[{i}] 不是字典")
            continue
        sp = str(item.get("speaker") or "").strip()
        line = str(item.get("line") or "").strip()
        if sp not in allowed:
            errors.append(f"dialogue[{i}] speaker 非法: {sp!r}")
        if not line:
            errors.append(f"dialogue[{i}] line 为空")
        if sp == "妈妈":
            mom_count += 1
            parent_count += 1
            if parent_line_looks_preachy(line):
                errors.append(f"dialogue[{i}] 妈妈台词像说教")
        if sp == "爸爸":
            dad_count += 1
            parent_count += 1
            if parent_line_looks_preachy(line):
                errors.append(f"dialogue[{i}] 爸爸台词像说教")

    mom_over = mom_count > mom_max
    dad_over = dad_count > dad_max
    if mom_over:
        errors.append(f"妈妈台词须≤{mom_max}句，当前{mom_count}")
    if dad_over:
        errors.append(f"爸爸台词须≤{dad_max}句，当前{dad_count}")
    if not mom_over and not dad_over and parent_count > parent_max:
        errors.append(f"家长台词须≤{parent_max}句，当前{parent_count}")

    rows = [
        x for x in dialogue if isinstance(x, dict) and str(x.get("line") or "").strip()
    ]
    line_count = len(rows)
    st = str(story.get("story_type") or "").strip().upper()
    line_max = chat_line_cap(st)
    total = dialogue_total_chars(story)
    # 联合判据：句数与字数达标其一即可，避免为凑句数灌空应答；但空应答占行仍有上限。
    # 末句豁免（各类型末句都是「哼/行/算了」级短收场，属正常结构）。
    low_info_idx = gold_chat_low_info_indexes(rows)
    low_info = len(low_info_idx)
    informative = line_count - low_info
    # 联合判据（专家方案）：句数与字数达标其一即可，避免为凑字数灌空应答/垫字。
    # 句数已达标时字数下限放宽一行（CHAT_MAX_LINE_CHARS），让 234/240 这类边际稿
    # 由本地补字/重掷的自然波动过门，而不是空掷一次重生成。
    char_floor = gold_chat_effective_min_chars(rows)
    if informative < CHAT_LINE_COUNT_MIN and total < DAILY_STORY_BODY_CHARS_MIN:
        errors.append(f"对白句数须≥{CHAT_LINE_COUNT_MIN}，当前{informative}")
    if total < char_floor:
        errors.append(f"正文总字数须≥{char_floor}，当前{total}")
    if line_count > line_max:
        errors.append(f"对白句数须≤{line_max}，当前{line_count}")
    # 低信息行不超过两成（至少 2 句）：按比例而非固定除数，长稿不会因固定小额度
    # 被单句「嗯。」卡死；四舍五入到整数，18 句稿允许 4 句应答节拍。
    low_info_allow = max(2, int(line_count * 0.2 + 0.5))
    if low_info > low_info_allow:
        marks = "/".join(str(i) for i in low_info_idx)
        errors.append(
            f"空应答占行须≤{low_info_allow}句，当前{low_info}（第{marks}句）"
        )

    lenses = _line_lens(dialogue if isinstance(dialogue, list) else [])
    if lenses:
        if max(lenses) > CHAT_MAX_LINE_CHARS:
            errors.append(f"单句过长(max={max(lenses)}>{CHAT_MAX_LINE_CHARS})")
        avg = mean(lenses)
        if avg > CHAT_AVG_LINE_CHARS_MAX:
            errors.append(f"均句过长({avg:.1f}>{CHAT_AVG_LINE_CHARS_MAX})")

    if total > DAILY_STORY_BODY_CHARS_MAX:
        errors.append(f"正文总字数须≤{DAILY_STORY_BODY_CHARS_MAX}，当前{total}")

    banned = [str(x).strip() for x in (banned_literals or []) if str(x).strip()]
    if banned:
        body = "\n".join(
            str(item.get("line") or "")
            for item in dialogue
            if isinstance(item, dict)
        )
        hits = [w for w in banned if w and w in body]
        if hits:
            errors.append(f"对白含禁词: {'、'.join(hits[:5])}")

    st = str(source_type or "").strip().lower()
    if st == "tutorial":
        body = "\n".join(str(item.get("line") or "") for item in dialogue if isinstance(item, dict))
        for word in TUTORIAL_RESIDUE:
            if word in body:
                errors.append(f"tutorial_residue_in_dialogue:{word}")

    errors.extend(collect_voice_errors(dialogue))
    from app.services.gold_story.scene import collect_narration_dialogue_errors

    errors.extend(collect_narration_dialogue_errors(dialogue if isinstance(dialogue, list) else []))
    errors.extend(
        collect_opening_causality_hard_errors(
            story,
            mom_lines_max=mom_max,
        ),
    )
    return errors
