"""gold_chat 类型对齐：checklist 注入 + 机审 + 精修 issue 收集。"""

from __future__ import annotations

import re
from typing import Any


def align_chain(
    *,
    structure_type: str,
    mechanism: str,
) -> tuple[str, ...]:
    from app.services.daily_story.gold_story.gold_chat.type_bridge import (
        type_align_chain,
    )

    return type_align_chain(structure_type=structure_type, mechanism=mechanism)


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

# closing_intent 常见收场词；未出现则末段禁对应 invent 动作
_CLOSING_INVENT_ALLOW = re.compile(r"帮|扶|递|棉签|送去|一起|回来|不疼了|快点|等你")

# 结构性问题：Pass2 定点修易打补丁，应打回 Pass1 重生
# 「对齐-类型契约」留给 Pass2 定点补槽，不进此集合
STRUCTURAL_ALIGN_KINDS: frozenset[str] = frozenset(
    {
        "保真-互毁前文",
        "保真-互毁对象",
        "保真-对象持有补丁",
        "保真-M5拒和speaker",
        "保真-发起方倒置",
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


def should_regenerate_pass1(issues: list[dict[str, Any]]) -> bool:
    """仅结构性 issue → 打回 Pass1；M5 立规/合并等局部问题留给 Pass2。"""
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


def pass1_align_score(
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
    """预选 Pass1 候选：(结构性 issue 数, 总 issue 数)，越小越好。"""
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
) -> None:
    """B 类 gold_chat：句尾「好不好/了呢呀」垫字过密 → 机审 issue。"""
    hits: list[int] = []
    for i, row in enumerate(rows, 1):
        line = str(row.get("line") or "").strip()
        if RE_PAD_FILLER_TAIL.search(line):
            hits.append(i)
    if len(hits) <= max_tail_filler:
        return
    issues.append(
        _issue(
            lines=hits,
            kind="保真-垫字过密",
            desc=f"句尾垫字「好不好/了呢呀」过多（{len(hits)} 处，上限 {max_tail_filler}）",
            fix="保留 2–3 处即可，其余改短句实词收尾；"
            "互怼句补全宾语，禁「呢呀/好不好呀」堆砌",
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

    特化机审（M5+H / H / F）之外，A–L 一律再跑类型正文契约
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
    """A–L 类型正文契约 → gold_chat issue（绕过 quality_ready）。"""
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


def validate_chat_hard(
    story: dict[str, Any],
    *,
    banned_literals: list[str] | None = None,
    source_type: str = "",
    mom_lines_max: int | None = None,
) -> list[str]:
    """gold_chat / 成品对白 hard 校验。"""
    from statistics import mean

    from app.services.daily_story.gold_story.scene import (
        ALLOWED_SPEAKERS,
        CHAT_AVG_LINE_CHARS_MAX,
        CHAT_LINE_COUNT_MAX,
        CHAT_LINE_COUNT_MIN,
        CHAT_MAX_LINE_CHARS,
        MOM_BANNED_IN_LINE,
        TUTORIAL_RESIDUE,
        collect_voice_errors,
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
    mom_max = 1 if mom_lines_max is None else max(0, int(mom_lines_max))
    mom_count = 0

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
            if any(w in line for w in MOM_BANNED_IN_LINE):
                errors.append(f"dialogue[{i}] 妈妈台词像说教")

    if mom_count > mom_max:
        errors.append(f"妈妈台词须≤{mom_max}句，当前{mom_count}")

    line_count = len([x for x in dialogue if isinstance(x, dict) and str(x.get("line") or "").strip()])
    if line_count < CHAT_LINE_COUNT_MIN:
        errors.append(f"对白句数须≥{CHAT_LINE_COUNT_MIN}，当前{line_count}")
    if line_count > CHAT_LINE_COUNT_MAX:
        errors.append(f"对白句数须≤{CHAT_LINE_COUNT_MAX}，当前{line_count}")

    lenses = _line_lens(dialogue if isinstance(dialogue, list) else [])
    if lenses:
        if max(lenses) > CHAT_MAX_LINE_CHARS:
            errors.append(f"单句过长(max={max(lenses)}>{CHAT_MAX_LINE_CHARS})")
        avg = mean(lenses)
        if avg > CHAT_AVG_LINE_CHARS_MAX:
            errors.append(f"均句过长({avg:.1f}>{CHAT_AVG_LINE_CHARS_MAX})")

    total = dialogue_total_chars(story)
    if total < DAILY_STORY_BODY_CHARS_MIN:
        errors.append(f"正文总字数须≥{DAILY_STORY_BODY_CHARS_MIN}，当前{total}")
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
    from app.services.daily_story.gold_story.scene import collect_narration_dialogue_errors

    errors.extend(collect_narration_dialogue_errors(dialogue if isinstance(dialogue, list) else []))
    return errors
