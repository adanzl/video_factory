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
        "弱势方先软：story_raw/beat 有哭腔或服软则写，**非必选**",
        "M5 角色：前文互毁/推搡锁定先动手方与受害方；"
        "服软/道歉与拒和/加码不得同一 speaker",
        "M5 角色：scene conflict 受害方须 establish 持有物，先毁物者≠受害方",
        "M5 立规：家规/规矩/规定引入（如谁先动手谁担责）",
        "M5 拒和：妈妈介入前至少 1 句嘴硬拒和（不原谅/免谈等）",
        "M5 加码：妈妈介入前再 1 句升级嘴硬（画/物弄了好久、变不回来等；与是否道歉无关）",
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

RE_RETALIATION = re.compile(
    r"也.*(?:弄坏|撕|毁|抢坏)|也(?:弄坏|撕|毁)|还.*(?:弄坏|撕|毁)"
)
RE_OTHER_DAMAGED_SELF = re.compile(r"你.{0,12}(弄坏|撕|抢坏|毁).*(我的|我)")
RE_PRIOR_DAMAGE = re.compile(r"弄坏|抢坏|撕坏|抓坏|.{0,2}坏")
RE_YOUR_OBJ = re.compile(r"你的.{1,4}")
RE_M5_RULE = re.compile(r"谁先动手|先动手.*道歉")
RE_M5_AUTHORITY = re.compile(r"家规|规矩|规定|说好了")
RE_M5_STUBBORN = re.compile(r"不原谅|免谈|别理我|别想")
RE_M5_ESCALATE = re.compile(r"道歉也没用|画了好久|弄了好久|很久|变回来|辛苦|没那么容易")
RE_MOM_ASK = re.compile(r"谁先动手|谁先.*手")
RE_MOM_BALANCE = re.compile(r"不对|别抢|先推|先动手|你也|都错")
RE_MOM_SOFT = re.compile(r"扯平|各打|算了就好|一笔勾销")
RE_ONE_SIDED = re.compile(r"弟弟都道歉|妹妹都道歉|都道歉了")
RE_RECONCILE = re.compile(r"不打了|拉手|对不起|没关系|说好了")
RE_CLOSING_INVENT = re.compile(r"帮|扶|递|棉签|送去|一起|回来|不疼了|快点|等你")
RE_FIGHT_QUESTION = re.compile(r"还打不打架|还打不打")
RE_IODINE_CLOSE = re.compile(r"碘伏|涂药|涂点药|消消毒")
RE_POST_CLOSE_INVENT = re.compile(
    r"你画|我画|一起|桥墩|桥面|画桥|画墩|以后不撕|不撕你"
)
RE_BROKEN_LINE = re.compile(r"^[，,、…]")
RE_M5_APOLOGY = re.compile(r"对不起|我先推|我错了|不是故意|真的错了")
RE_OBJECT_HOLDER = re.compile(r"也有你的|有你的|拿着你的|拿了你的|我有你的")
RE_OBJECT_CREATE = re.compile(r"你在画|你画[^坏抢]|你写|你搭|你拼|你的.{1,4}在")
RE_AGGRESSIVE_DAMAGE = re.compile(r"撕|弄坏|抢坏|毁|抓坏")
RE_DAMAGE_THREAT = re.compile(r"再.*就.*撕|再抢.*撕|敢.*撕|要不.*撕|否则.*撕")
RE_BEAT_INITIATOR = re.compile(r"抢|看|瞅|占")
RE_BEAT_DEFENDER = re.compile(r"拒看|拒绝|secret|秘密|不行|威胁", re.IGNORECASE)

# closing_intent 常见收场词；未出现则末段禁对应 invent 动作
_CLOSING_INVENT_ALLOW = re.compile(r"帮|扶|递|棉签|送去|一起|回来|不疼了|快点|等你")

# 结构性问题：Pass2 定点修易打补丁，应打回 Pass1 重生
STRUCTURAL_FIDELITY_KINDS: frozenset[str] = frozenset(
    {
        "保真-互毁前文",
        "保真-互毁对象",
        "保真-对象持有补丁",
        "保真-M5拒和speaker",
        "保真-发起方倒置",
    }
)

# 保真 warn：不阻塞导出，可进 quality / 人工复核
FIDELITY_WARN_KINDS: frozenset[str] = frozenset(
    {
        "保真-M5合并",
        "保真-收场Invent",
    }
)


def is_structural_fidelity_kind(kind: str) -> bool:
    return str(kind or "").strip() in STRUCTURAL_FIDELITY_KINDS


def is_fidelity_warn_kind(kind: str) -> bool:
    return str(kind or "").strip() in FIDELITY_WARN_KINDS


def split_fidelity_issues(
    issues: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """blocking 未通过则 fail；warn 仅记录，不阻塞导出。"""
    blocking: list[dict[str, Any]] = []
    warn: list[dict[str, Any]] = []
    for item in issues:
        kind = str(item.get("kind") or "")
        if is_fidelity_warn_kind(kind):
            warn.append(item)
        else:
            blocking.append(item)
    return blocking, warn


def should_regenerate_pass1(issues: list[dict[str, Any]]) -> bool:
    """仅结构性 issue → 打回 Pass1；M5 立规/合并等局部问题留给 Pass2。"""
    if not issues:
        return False
    kinds = {str(x.get("kind") or "") for x in issues}
    return bool(kinds & STRUCTURAL_FIDELITY_KINDS)


def _sibling_partner(name: str) -> str:
    return "昭昭" if str(name or "").strip() == "灿灿" else "灿灿"


def format_role_binding_block(conflict_text: str) -> str:
    """Pass1 注入：从 scene conflict 解析受害方/先动手方分工。"""
    victim = _parse_conflict_victim(conflict_text)
    if not victim:
        return ""
    aggressor = _sibling_partner(victim)
    return (
        "【角色分工锁定 · 硬约束】\n"
        f"- scene conflict 受害方 = {victim}：前 2 句须 establish {victim} 持有/正在创作\n"
        f"- 先动手/先毁方 = {aggressor}：第 3–4 句由其发起捣乱/毁画/推搡\n"
        f"- 禁止：{victim} 开口抢看/先撕先毁；{aggressor} 不得先说「不原谅/加码」\n"
        "- 禁止「秘密画」偏题；互毁须围绕画作双向展开\n"
        f"- 双向互毁：{victim} 说「也/还+撕/弄坏+你的」前，"
        f"须 {aggressor} 先实质毁 {victim} 侧作品；"
        f"禁止 {aggressor} 在 {victim} 未毁 {aggressor} 侧物时说「我也撕/弄坏你的」\n"
        f"- 妈妈介入前：{aggressor} 道歉/服软；{victim} 拒和 + 加码"
        "（各一句，不得同一 speaker）"
    )


def format_beat_sequence_block(
    *,
    conflict_text: str,
    beat_chain: list[Any] | None = None,
    mechanism: str = "",
    structure_type: str = "",
) -> str:
    """Pass1 注入：beat 事件顺序硬约束 + 互毁正/反例。"""
    from app.services.daily_story.gold_story.scene_contract import format_beat_chain

    mech = str(mechanism or "").strip().upper()
    st = str(structure_type or "").strip().upper()
    victim = _parse_conflict_victim(conflict_text)

    parts = [
        "【事件顺序硬约束 · 对白须逐步落实，禁止跳步/调序/speaker 互换】",
    ]
    chain_text = format_beat_chain(beat_chain)
    if chain_text:
        parts.extend(
            [
                "须按以下 beat 顺序展开（每拍 1–3 句对白）：",
                chain_text,
            ]
        )
    if mech == "M5" and st == "H" and victim:
        aggressor = _sibling_partner(victim)
        parts.extend(
            [
                "",
                "互毁段 speaker 顺序（硬卡）：",
                f"① {victim} establish 作品 → ② {aggressor} 实质毁 {victim} 侧物",
                f"→ ③ {victim} 说「也/还+撕/弄坏+你的」",
                "→ ④ 推搡/受伤",
                "",
                "正例：",
                f"- {aggressor}：弄坏/撕了 {victim} 的画",
                f"- {victim}：那我也弄坏/撕你的",
                "",
                "反例（禁止）：",
                f"- {aggressor} 说「我也撕你的」但前文只有 {aggressor} 毁"
                f" {victim} 的画",
                f"- {victim} 抢看/守秘密、{aggressor} 受害（角色倒置）",
            ]
        )
    elif victim:
        aggressor = _sibling_partner(victim)
        parts.append(
            f"\n受害方 {victim} 须先 establish；先动手/毁物方 {aggressor} 后介入"
        )
    return "\n".join(parts)


def format_pass1_regen_feedback(
    error: str,
    story: dict[str, Any] | None,
    *,
    structure_type: str,
    mechanism: str,
    closing_intent: str = "",
    beat_chain: list[Any] | None = None,
    conflict_text: str = "",
) -> str:
    """Pass1 重试：把上一轮 structural 机审问题注入 prompt。"""
    err = str(error or "").strip()
    if not err.startswith(("fidelity_structural:", "fidelity_refine_failed:")):
        return ""

    issues: list[dict[str, Any]] = []
    if isinstance(story, dict):
        raw = collect_fidelity_issues(
            story,
            structure_type=structure_type,
            mechanism=mechanism,
            closing_intent=closing_intent,
            beat_chain=beat_chain,
            conflict_text=conflict_text,
        )
        issues = [
            x
            for x in raw
            if is_structural_fidelity_kind(str(x.get("kind") or ""))
        ]

    parts = ["【上一轮 Pass1 失败 · 本轮须修正】"]
    parts.append(f"机审：{err.split(':', 1)[-1]}")
    if issues:
        for item in issues[:4]:
            kind = str(item.get("kind") or "")
            lines = item.get("lines") or []
            ln = "、".join(str(n) for n in lines[:3]) if lines else "?"
            desc = str(item.get("desc") or "")[:120]
            parts.append(f"- {kind}（第{ln}句）：{desc}")
            fix = str(item.get("fix") or "").strip()
            if fix:
                parts.append(f"  → {fix[:100]}")
    else:
        parts.append("- 对照上方事件顺序硬约束重写，勿重复同类错误")
    return "\n".join(parts)


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


def _parse_fight_question_asker(closing_intent: str) -> str | None:
    """closing_intent「灿灿问…还打不打架」→ 指定问句 speaker。"""
    raw = str(closing_intent or "").strip()
    if not raw or "还打" not in raw:
        return None
    m = re.search(r"(昭昭|灿灿)问", raw)
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


def pass1_fidelity_score(
    story: dict[str, Any],
    *,
    structure_type: str,
    mechanism: str,
    closing_intent: str = "",
    beat_chain: list[Any] | None = None,
    conflict_text: str = "",
) -> tuple[int, int]:
    """预选 Pass1 候选：(结构性 issue 数, 总 issue 数)，越小越好。"""
    issues = collect_fidelity_issues(
        story,
        structure_type=structure_type,
        mechanism=mechanism,
        closing_intent=closing_intent,
        beat_chain=beat_chain,
        conflict_text=conflict_text,
    )
    structural = sum(
        1 for x in issues if is_structural_fidelity_kind(str(x.get("kind") or ""))
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
    if RE_PRIOR_DAMAGE.search(before) and RE_YOUR_OBJ.search(line[m_ret.end() :]):
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
            if not RE_AGGRESSIVE_DAMAGE.search(line):
                continue
            if _is_damage_threat_only(line):
                continue
            if sp == victim:
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

    mom_indices = [i for i, sp in enumerate(speakers, 1) if sp == "妈妈"]
    pre_mom_end = mom_indices[0] if mom_indices else n + 1
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
        has_hard = any(RE_M5_STUBBORN.search(x) for x in pre_mom)
        has_escalate = any(RE_M5_ESCALATE.search(x) for x in pre_mom)
        if not (has_hard and has_escalate):
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


def _last_kid_idx_before_mom(
    rows: list[dict[str, Any]],
    first_mom: int,
) -> int:
    for j in range(first_mom - 2, -1, -1):
        if str(rows[j].get("speaker") or "") in {"昭昭", "灿灿"}:
            return j
    return -1


def _escalate_line_for_context(pre_mom_lines: list[str]) -> str:
    blob = "".join(pre_mom_lines)
    if "画" in blob:
        return "这画我弄了好久呢！"
    if RE_PRIOR_DAMAGE.search(blob):
        return "哼，变不回来了！"
    return "哼，没那么容易算！"


_M5_RULE_AUTHORITY_PREFIX = "家规就是"


def patch_m5_rule_authority(
    story: dict[str, Any],
    *,
    max_line_chars: int = 30,
) -> tuple[dict[str, Any], bool]:
    """M5 立规缺 authority 词时句首补「家规就是」（Pass2 本地修，不打回 Pass1）。"""
    import copy

    rows = _dialogue_rows(story)
    if not rows:
        return story, False

    out = copy.deepcopy(story)
    dlg = out["dialogue"]
    changed = False
    for item in dlg:
        if not isinstance(item, dict):
            continue
        sp = str(item.get("speaker") or "").strip()
        if sp not in {"昭昭", "灿灿"}:
            continue
        line = str(item.get("line") or "").strip()
        if not line or not RE_M5_RULE.search(line):
            continue
        if RE_M5_AUTHORITY.search(line):
            continue
        if line.startswith(_M5_RULE_AUTHORITY_PREFIX):
            continue
        candidate = f"{_M5_RULE_AUTHORITY_PREFIX}{line}"
        if len(candidate) > max_line_chars:
            continue
        item["line"] = candidate
        changed = True
    return out, changed


def patch_trim_post_iodine_tail(story: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """碘伏/涂药妈妈句后删拖句 invent（Pass2 本地，不手改 export）。"""
    import copy

    rows = _dialogue_rows(story)
    if len(rows) < 12:
        return story, False
    lines = [str(r.get("line") or "").strip() for r in rows]
    iodine_idx = _iodine_close_line_index(lines)
    if iodine_idx <= 0 or iodine_idx >= len(rows):
        return story, False
    if iodine_idx == len(rows):
        return story, False
    out = copy.deepcopy(story)
    out["dialogue"] = list(rows[:iodine_idx])
    return out, True


def apply_m5_h_local_patches(story: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """M5+H Pass2 本地补丁：立规 → 加码 → 碘伏后删尾。"""
    data, c1 = patch_m5_rule_authority(story)
    data, c2 = patch_m5_pre_mom_escalation(data)
    data, c3 = patch_trim_post_iodine_tail(data)
    return data, c1 or c2 or c3


def patch_m5_pre_mom_escalation(story: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """妈妈介入前缺 M5 拒和/加码时本地补拍（与是否道歉无关）。"""
    import copy

    rows = _dialogue_rows(story)
    if len(rows) < 10:
        return story, False

    lines = [str(r.get("line") or "").strip() for r in rows]
    speakers = [str(r.get("speaker") or "").strip() for r in rows]
    mom_indices = [i for i, sp in enumerate(speakers, 1) if sp == "妈妈"]
    if not mom_indices:
        return story, False

    first_mom = mom_indices[0]
    pre_mom = lines[: first_mom - 1]
    has_hard = any(RE_M5_STUBBORN.search(x) for x in pre_mom)
    has_escalate = any(RE_M5_ESCALATE.search(x) for x in pre_mom)
    if has_hard and has_escalate:
        return story, False

    out = copy.deepcopy(story)
    dlg = out["dialogue"]
    kid_idx = _last_kid_idx_before_mom(dlg, first_mom)
    if kid_idx < 0:
        return story, False

    if not has_escalate:
        candidate = _escalate_line_for_context(pre_mom)
        cur = str(dlg[kid_idx].get("line") or "").strip()
        if RE_M5_STUBBORN.search(cur):
            for j in range(kid_idx - 1, -1, -1):
                if str(dlg[j].get("speaker") or "") not in {"昭昭", "灿灿"}:
                    continue
                prev = str(dlg[j].get("line") or "").strip()
                if not RE_M5_ESCALATE.search(prev) and len(candidate) <= 30:
                    dlg[j]["line"] = candidate
                    return out, True
                break
        elif len(candidate) <= 30 and not RE_M5_ESCALATE.search(cur):
            dlg[kid_idx]["line"] = candidate
            return out, True

    if not has_hard:
        stub = "哼，不原谅！"
        cur = str(dlg[kid_idx].get("line") or "").strip()
        if RE_M5_ESCALATE.search(cur):
            for j in range(kid_idx - 1, -1, -1):
                if str(dlg[j].get("speaker") or "") not in {"昭昭", "灿灿"}:
                    continue
                prev = str(dlg[j].get("line") or "").strip()
                if not RE_M5_STUBBORN.search(prev) and len(stub) <= 30:
                    dlg[j]["line"] = stub
                    return out, True
                break
        elif len(stub) <= 30 and not RE_M5_STUBBORN.search(cur):
            dlg[kid_idx]["line"] = stub
            return out, True

    return story, False


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


def collect_fidelity_issues(
    story: dict[str, Any],
    *,
    structure_type: str,
    mechanism: str,
    closing_intent: str = "",
    beat_chain: list[Any] | None = None,
    conflict_text: str = "",
) -> list[dict[str, Any]]:
    """保真机审：返回 polish 同构 issue 列表（抽象不变量，非逐篇剧情）。"""
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
