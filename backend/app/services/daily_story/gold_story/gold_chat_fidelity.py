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
    ("M11", "I"): (
        "争锋/互怼 escalating（可含双规则拉扯）",
        "立价值标准/道德高地（须可拍一句）",
        "灵魂拷问：抛出不可答/不可接问题",
        "对方语塞/败北 beat",
        "赢家嘴硬总结（一招制敌；无反噬）",
    ),
    ("M8", "J"): (
        "闹/求放行/试探权威",
        "一锤定音威慑（镇住，不翻车）",
        "对方怂/不敢再顶",
        "家长旁观或感叹（非 A 反噬）",
    ),
    ("M5", "J"): (
        "互打/求放过/试探规矩",
        "否决权/拒放行压住",
        "对方怂/不敢再顶",
        "家长旁观或感叹（非 H 劝和）",
    ),
    ("M12", "K"): (
        "互打互骂升级",
        "大人躲/叹/劝失败",
        "僵持（不和好；禁止套 H）",
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
        "保真-互毁动作",
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


def format_m5_h_pass1_beat_block(
    *,
    conflict_text: str,
    closing_intent: str = "",
) -> str:
    """M5+H Pass1 固定节拍表（对齐金稿 #5 正例结构）。"""
    victim = _parse_conflict_victim(conflict_text)
    if not victim:
        return ""
    aggressor = _sibling_partner(victim)
    asker = _parse_fight_question_asker(closing_intent) or victim
    return (
        "【M5+H 固定节拍表 · 须逐拍落实，禁止跳步/调序/speaker 互换】\n"
        f"① {victim} establish 创作/持有（1–2 句）\n"
        f"② {aggressor} 实质捣乱/毁 {victim} 侧画作（1 句）\n"
        f"③ {victim} 抗议 → {aggressor} 推搡（须写推→额/头/蹭破/疼）\n"
        f"④ {victim} **当场动手**撕/弄坏 {aggressor} 侧画"
        f"（须写「抢/撕了/撕啦/弄坏了」，禁仅口头「那我也撕」）\n"
        f"⑤ {victim} 伤情一句（额/蹭破/疼）\n"
        f"⑥ {aggressor} 哭腔道歉/服软\n"
        f"⑦ {victim} 立规（家规/谁先动手谁道歉）\n"
        f"⑧ {aggressor} 求和/认错\n"
        f"⑨ {victim} 拒和 + 加码（各一句，不得同一 speaker）\n"
        "⑩ 妈妈问「谁先动手」\n"
        f"⑪ {aggressor} 承认先弄花/先推/先动手\n"
        "⑫ 妈妈定责分层（先弄画不对 + 别推人 + 额头先处理）\n"
        "⑬ 仪式性和好（拉手/勉强松口）\n"
        f"⑭ {asker} 问「以后还打不打架？」\n"
        "⑮ 齐声承诺=昭昭「不打了！」+灿灿「不打了！这还差不多。」（各一句，勿合并舞台说明）\n"
        "⑯ 妈妈拿碘伏/涂药收场\n"
        "禁止：秘密画/抢看偏题；妈妈代问「还打不打架」；"
        "句尾堆「呢呢」；碘伏后新剧情（一起画/拉钩 invent）"
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


_MAX_M5_CONSECUTIVE_FIXES = 8


def _pick_m5_bridge_line(
    speaker: str,
    prev_line: str,
    next_line: str,
) -> tuple[str, str]:
    alt = "昭昭" if speaker == "灿灿" else "灿灿"
    blob = prev_line + next_line
    if "拉手" in prev_line or "还打不" in next_line:
        return alt, "嗯……好吧。"
    if "不原谅" in next_line or "道歉也没用" in next_line:
        return alt, "哼！别说了！"
    if "赔" in blob or "撕" in blob or "弄花" in blob:
        return alt, "呜……别闹了！"
    if "画" in blob:
        return alt, "你住手！"
    return alt, "别说了！"


def patch_m5_break_sibling_consecutive(
    story: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    """M5+H：姐弟同人连说处插短接话，满足观感交替节奏。"""
    import copy

    from app.services.daily_story.dialogue_text import (
        DAILY_STORY_LINE_CHARS_MAX,
        dialogue_char_count,
    )

    rows = _dialogue_rows(story)
    if len(rows) < 2:
        return story, False
    out = copy.deepcopy(story)
    dlg = out.get("dialogue")
    if not isinstance(dlg, list):
        return story, False
    changed = False
    fixes = 0
    i = 1
    while i < len(dlg) and fixes < _MAX_M5_CONSECUTIVE_FIXES:
        a, b = dlg[i - 1], dlg[i]
        if not isinstance(a, dict) or not isinstance(b, dict):
            i += 1
            continue
        sa = str(a.get("speaker") or "").strip()
        sb = str(b.get("speaker") or "").strip()
        if sa not in ("昭昭", "灿灿") or sa != sb:
            i += 1
            continue
        prev_line = str(a.get("line") or "")
        next_line = str(b.get("line") or "")
        bridge_sp, bridge_ln = _pick_m5_bridge_line(sa, prev_line, next_line)
        if dialogue_char_count(bridge_ln) > DAILY_STORY_LINE_CHARS_MAX:
            i += 1
            continue
        dlg.insert(i, {"speaker": bridge_sp, "line": bridge_ln})
        changed = True
        fixes += 1
        i += 2
    return (out, True) if changed else (story, False)


_M5_RULE_AUTHORITY_PREFIX = "家规就是"
_M5_RULE_CANONICAL = "家规就是谁先动手谁道歉！"
_RE_MOM_RULE_REF = re.compile(r"妈妈(?:说过|说|讲|告诉)")


def patch_m5_retaliation_action(
    story: dict[str, Any],
    *,
    conflict_text: str = "",
) -> tuple[dict[str, Any], bool]:
    """受害方互毁句缺当场动作时，改为「抢你画撕啦」类已完成破坏。"""
    import copy

    victim = _parse_conflict_victim(conflict_text)
    if not victim:
        return story, False
    rows = _dialogue_rows(story)
    if len(rows) < 6:
        return story, False
    lines = [str(r.get("line") or "").strip() for r in rows]
    speakers = [str(r.get("speaker") or "").strip() for r in rows]
    out = copy.deepcopy(story)
    changed = False
    for idx, (sp, line) in enumerate(zip(speakers, lines)):
        if sp != victim:
            continue
        following = lines[idx + 1 : idx + 3]
        if RE_RETALIATION_DONE.search(line) and not re.search(
            r"也抢|那我也|我也", line
        ):
            out["dialogue"][idx]["line"] = "我也抢你画撕啦！你赔！"
            changed = True
            continue
        if not _retaliation_missing_action(line, following):
            continue
        new_line = "我也抢你画撕啦！你赔！"
        if len(new_line) > 30:
            new_line = "我也抢你画撕啦！"
        out["dialogue"][idx]["line"] = new_line
        changed = True
    return out, changed


def patch_m5_soften_premature_push_blame(
    story: dict[str, Any],
    *,
    conflict_text: str = "",
) -> tuple[dict[str, Any], bool]:
    """伤情句前昭昭「你推我」暗示受害方先推人；改为抱怨勿提前写推搡。"""
    import copy
    import re as _re

    victim = _parse_conflict_victim(conflict_text)
    if not victim:
        return story, False
    rows = _dialogue_rows(story)
    if len(rows) < 6:
        return story, False
    lines = [str(r.get("line") or "").strip() for r in rows]
    speakers = [str(r.get("speaker") or "").strip() for r in rows]
    victim_pushed_i = next(
        (
            i
            for i, (sp, line) in enumerate(zip(speakers, lines))
            if sp == victim and "推我" in line and RE_INJURY.search(line)
        ),
        next(
            (
                i
                for i, (sp, line) in enumerate(zip(speakers, lines))
                if sp == victim and _re.search(r"哎哟.*推|推.*疼|推.*破", line)
            ),
            -1,
        ),
    )
    if victim_pushed_i <= 0:
        return story, False

    out = copy.deepcopy(story)
    changed = False
    for i in range(victim_pushed_i):
        if speakers[i] != "昭昭":
            continue
        line = lines[i]
        if not _re.search(r"推我|你推", line):
            continue
        new_line = _re.sub(r"你推我干嘛[！!？?]*", "你干嘛凶我！", line)
        new_line = _re.sub(r"你推我[！!？?]*", "你干嘛凶我！", new_line)
        if new_line == line:
            new_line = "我就碰了一下，你干嘛凶我！"
        out["dialogue"][i]["line"] = new_line
        changed = True
    if not changed:
        return story, False
    return out, True


def patch_m5_denial_speaker_swap(story: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """服软方说了拒和/加码时，改由另一方 speaker（Pass2 本地）。"""
    import copy

    rows = _dialogue_rows(story)
    if len(rows) < 8:
        return story, False
    lines = [str(r.get("line") or "").strip() for r in rows]
    speakers = [str(r.get("speaker") or "").strip() for r in rows]
    mom_indices = [i for i, sp in enumerate(speakers, 1) if sp == "妈妈"]
    if not mom_indices:
        return story, False
    pre_mom_end = mom_indices[0]
    apology_speakers: set[str] = set()
    for i in range(1, pre_mom_end):
        sp = speakers[i - 1]
        if sp in {"昭昭", "灿灿"} and RE_M5_APOLOGY.search(lines[i - 1]):
            apology_speakers.add(sp)
    if not apology_speakers:
        return story, False
    out = copy.deepcopy(story)
    dlg = out["dialogue"]
    changed = False
    for i in range(1, pre_mom_end):
        sp = speakers[i - 1]
        line = lines[i - 1]
        if sp not in apology_speakers:
            continue
        if not (RE_M5_STUBBORN.search(line) or RE_M5_ESCALATE.search(line)):
            continue
        dlg[i - 1]["speaker"] = _sibling_partner(sp)
        changed = True
    return out, changed


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
        if not line:
            continue
        if _RE_MOM_RULE_REF.search(line) and RE_M5_RULE.search(line):
            new_line = _RE_MOM_RULE_REF.sub(_M5_RULE_AUTHORITY_PREFIX, line)
            if len(new_line) <= max_line_chars:
                item["line"] = new_line
                changed = True
            elif len(_M5_RULE_CANONICAL) <= max_line_chars:
                item["line"] = _M5_RULE_CANONICAL
                changed = True
            continue
        if not RE_M5_RULE.search(line):
            continue
        if RE_M5_AUTHORITY.search(line):
            continue
        if line.startswith(_M5_RULE_AUTHORITY_PREFIX):
            continue
        candidate = f"{_M5_RULE_AUTHORITY_PREFIX}{line}"
        if len(candidate) <= max_line_chars:
            item["line"] = candidate
            changed = True
        elif len(_M5_RULE_CANONICAL) <= max_line_chars:
            item["line"] = _M5_RULE_CANONICAL
            changed = True
    return out, changed


def patch_m5_insert_authority_before_mom(
    story: dict[str, Any],
    *,
    max_line_chars: int = 30,
) -> tuple[dict[str, Any], bool]:
    """妈妈介入前全无家规/规矩时，补一句 canonical 立规（句数满则替换嘴硬句）。"""
    import copy

    from app.services.daily_story.gold_story.scene_contract import (
        CHAT_LINE_COUNT_MAX,
    )

    rows = _dialogue_rows(story)
    if len(rows) < 8:
        return story, False
    lines = [str(r.get("line") or "").strip() for r in rows]
    speakers = [str(r.get("speaker") or "").strip() for r in rows]
    mom_indices = [i for i, sp in enumerate(speakers, 1) if sp == "妈妈"]
    if not mom_indices:
        return story, False
    first_mom = mom_indices[0]
    pre_mom = lines[: first_mom - 1]
    if any(RE_M5_AUTHORITY.search(x) for x in pre_mom):
        return story, False
    if len(_M5_RULE_CANONICAL) > max_line_chars:
        return story, False

    out = copy.deepcopy(story)
    dlg = out["dialogue"]
    rule = {"speaker": "灿灿", "line": _M5_RULE_CANONICAL}
    insert_at = first_mom - 1
    if len(dlg) < CHAT_LINE_COUNT_MAX:
        dlg.insert(insert_at, rule)
        return out, True

    for j in range(first_mom - 2, -1, -1):
        if speakers[j] not in {"昭昭", "灿灿"}:
            continue
        cur = lines[j]
        if RE_M5_STUBBORN.search(cur) or RE_M5_ESCALATE.search(cur):
            dlg[j]["line"] = _M5_RULE_CANONICAL
            return out, True
    if insert_at >= 0 and speakers[insert_at - 1] in {"昭昭", "灿灿"}:
        dlg[insert_at - 1]["line"] = _M5_RULE_CANONICAL
        return out, True
    return story, False


_INJURY_LINE = "啊！额头磕到了，好疼！"


def patch_ensure_injury_after_push(story: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """碘伏收场稿：推搡后缺伤情时补一句受害方喊疼。"""
    import copy

    rows = _dialogue_rows(story)
    if len(rows) < 8:
        return story, False
    lines = [str(r.get("line") or "").strip() for r in rows]
    if not any(RE_IODINE_CLOSE.search(x) for x in lines):
        return story, False
    speakers = [str(r.get("speaker") or "").strip() for r in rows]
    mom_i = next((i for i, sp in enumerate(speakers) if sp == "妈妈"), len(rows))
    pre_mom = lines[:mom_i]
    if any(RE_INJURY.search(x) for x in pre_mom):
        return story, False
    push_i = next((i for i, x in enumerate(pre_mom) if "推" in x), -1)
    if push_i < 0:
        return story, False
    out = copy.deepcopy(story)
    dlg = out["dialogue"]
    target = push_i + 1
    if target >= len(dlg):
        return story, False
    dlg[target]["speaker"] = "灿灿"
    dlg[target]["line"] = _INJURY_LINE
    return out, True


def patch_m5_fix_pre_mom_sequence(story: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """妈妈问谁先动手须晚于服软+立规+拒和+加码（Pass2 本地重排）。"""
    import copy

    rows = _dialogue_rows(story)
    if len(rows) < 12:
        return story, False
    out = copy.deepcopy(story)
    dlg = out["dialogue"]
    changed = False

    def _snapshot() -> tuple[list[str], list[str]]:
        ls = [str(r.get("line") or "").strip() for r in dlg]
        sps = [str(r.get("speaker") or "").strip() for r in dlg]
        return ls, sps

    lines, speakers = _snapshot()
    rule_i = next(
        (
            i
            for i, (sp, line) in enumerate(zip(speakers, lines))
            if sp in {"昭昭", "灿灿"}
            and RE_M5_AUTHORITY.search(line)
            and RE_M5_RULE.search(line)
        ),
        -1,
    )
    apology_i = next(
        (
            i
            for i, (sp, line) in enumerate(zip(speakers, lines))
            if sp in {"昭昭", "灿灿"} and RE_M5_APOLOGY.search(line)
        ),
        -1,
    )
    if rule_i >= 0 and apology_i > rule_i:
        dlg.insert(rule_i, dlg.pop(apology_i))
        changed = True
        lines, speakers = _snapshot()

    mom_ask_i = next(
        (
            i
            for i, (sp, line) in enumerate(zip(speakers, lines))
            if sp == "妈妈" and RE_MOM_ASK.search(line)
        ),
        -1,
    )
    if mom_ask_i < 0:
        return (out, changed) if changed else (story, False)
    after_mom = [
        i
        for i in range(mom_ask_i + 1, len(lines))
        if speakers[i] in {"昭昭", "灿灿"}
        and (
            RE_M5_STUBBORN.search(lines[i])
            or RE_M5_ESCALATE.search(lines[i])
        )
    ]
    if not after_mom:
        return (out, changed) if changed else (story, False)

    last_i = after_mom[-1]
    mom_row = dlg.pop(mom_ask_i)
    insert_at = last_i if last_i < mom_ask_i else last_i
    dlg.insert(insert_at + 1, mom_row)
    return out, True


def patch_sanitize_iodine_line(story: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """碘伏收场句删 story_raw 未提 invent（录视频/发朋友圈）。"""
    import copy

    out = copy.deepcopy(story)
    changed = False
    for item in out.get("dialogue") or []:
        if not isinstance(item, dict):
            continue
        if str(item.get("speaker") or "").strip() != "妈妈":
            continue
        line = str(item.get("line") or "").strip()
        if not RE_IODINE_CLOSE.search(line):
            continue
        if not RE_IODINE_INVENT.search(line):
            continue
        trimmed = re.sub(r"[，,]?我?(?:录|发).*$", "", line).strip("，, ")
        item["line"] = trimmed or "来，额头涂点碘伏消消毒。"
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


def _trim_m5_merged_line(line: str) -> str:
    """一句内 M5 立规/拒和/加码合并 → 只保留立规段。"""
    raw = str(line or "").strip()
    if _m5_phrase_hits(raw) < 2:
        return raw
    m = re.search(
        r"((?:家规|规矩|规定).{0,24}?(?:谁先动手|先动手).{0,16}?[！!])",
        raw,
    )
    if m:
        return m.group(1)
    if RE_M5_STUBBORN.search(raw) and not RE_M5_ESCALATE.search(raw):
        m2 = re.search(r"[^！!]*不原谅[^！!]*[！!]?", raw)
        if m2:
            return m2.group(0).strip()
    if RE_M5_ESCALATE.search(raw) and not RE_M5_STUBBORN.search(raw):
        m3 = re.search(r"[^！!]*(?:道歉也没用|弄了好久|变不回来)[^！!]*[！!]?", raw)
        if m3:
            return m3.group(0).strip()
    return raw


def patch_split_m5_merged_line(
    story: dict[str, Any],
    *,
    max_line_chars: int = 30,
) -> tuple[dict[str, Any], bool]:
    """Pass2：M5 立规/拒和/加码同句合并时只保留立规（其余靠邻句/本地补拍）。"""
    import copy

    rows = _dialogue_rows(story)
    if not rows:
        return story, False
    out = copy.deepcopy(story)
    changed = False
    for item in out["dialogue"]:
        if not isinstance(item, dict):
            continue
        if str(item.get("speaker") or "").strip() not in {"昭昭", "灿灿"}:
            continue
        line = str(item.get("line") or "").strip()
        if _m5_phrase_hits(line) < 2:
            continue
        trimmed = _trim_m5_merged_line(line)
        if trimmed and trimmed != line and len(trimmed) <= max_line_chars:
            item["line"] = trimmed
            changed = True
    return out, changed


def patch_fight_question_speaker(
    story: dict[str, Any],
    *,
    closing_intent: str = "",
) -> tuple[dict[str, Any], bool]:
    """Pass2：「还打不打架」speaker 对齐 closing_intent（允许改 speaker）。"""
    import copy

    asker = _parse_fight_question_asker(closing_intent)
    if not asker:
        return story, False
    rows = _dialogue_rows(story)
    if not rows:
        return story, False
    out = copy.deepcopy(story)
    changed = False
    for item in out["dialogue"]:
        if not isinstance(item, dict):
            continue
        line = str(item.get("line") or "").strip()
        if not RE_FIGHT_QUESTION.search(line):
            continue
        sp = str(item.get("speaker") or "").strip()
        if sp != asker:
            item["speaker"] = asker
            changed = True
    return out, changed


def patch_remap_sibling_terms(story: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Pass2：站外兄弟称谓 → 姐弟映射（哥哥→姐姐，弟弟→昭昭）。"""
    import copy

    rows = _dialogue_rows(story)
    if not rows:
        return story, False
    out = copy.deepcopy(story)
    changed = False
    for item in out["dialogue"]:
        if not isinstance(item, dict):
            continue
        line = str(item.get("line") or "")
        if not line:
            continue
        new_line = (
            line.replace("哥哥", "姐姐")
            .replace("弟弟", "昭昭")
        )
        if new_line != line:
            item["line"] = new_line
            changed = True
    return out, changed


def patch_ensure_chorus_bukeda(
    story: dict[str, Any],
    *,
    closing_intent: str = "",
) -> tuple[dict[str, Any], bool]:
    """closing 齐声：缺问句则整段插入；有问句则补第二句「不打了」。"""
    import copy

    rows = _dialogue_rows(story)
    if len(rows) < 8:
        return story, False
    lines = [str(r.get("line") or "").strip() for r in rows]
    speakers = [str(r.get("speaker") or "").strip() for r in rows]
    fight_idx = next(
        (i for i, line in enumerate(lines, 1) if RE_FIGHT_QUESTION.search(line)),
        0,
    )
    asker = _parse_fight_question_asker(closing_intent) or "灿灿"
    closing_needed = bool(RE_FIGHT_QUESTION.search(closing_intent or ""))

    if fight_idx <= 0:
        if not closing_needed:
            return story, False
        iodine_idx = _iodine_close_line_index(lines)
        hand_i = next(
            (i for i, line in enumerate(lines) if "拉手" in line),
            -1,
        )
        if hand_i >= 0:
            insert_at = hand_i + 1
        elif iodine_idx > 0:
            insert_at = iodine_idx - 1
        else:
            insert_at = len(rows)
        out = copy.deepcopy(story)
        dlg = out["dialogue"]
        block = [
            {"speaker": asker, "line": "以后还打不打架？"},
            {"speaker": "昭昭", "line": "不打了！"},
            {"speaker": "灿灿", "line": "不打了！这还差不多。"},
        ]
        for j, item in enumerate(block):
            dlg.insert(insert_at + j, item)
        return out, True

    kid_bukeda = [
        i
        for i in range(fight_idx + 1, len(lines) + 1)
        if speakers[i - 1] in {"昭昭", "灿灿"} and "不打了" in lines[i - 1]
    ]
    if len(kid_bukeda) >= 2:
        return story, False
    out = copy.deepcopy(story)
    dlg = out["dialogue"]
    if len(kid_bukeda) == 1:
        only_i = kid_bukeda[0]
        only_sp = speakers[only_i - 1]
        other = _sibling_partner(only_sp)
        insert_at = only_i
        insert_line = "不打了！这还差不多。" if other == "灿灿" else "不打了！"
        dlg.insert(insert_at, {"speaker": other, "line": insert_line})
        return out, True
    if closing_needed:
        insert_at = fight_idx
        dlg.insert(insert_at, {"speaker": "昭昭", "line": "不打了！"})
        dlg.insert(insert_at + 1, {"speaker": "灿灿", "line": "不打了！这还差不多。"})
        return out, True
    return story, False


def patch_fix_mom_ask_admission(
    story: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    """妈妈问谁先动手后，昭昭须承认推/动手/先弄画。"""
    import copy

    rows = _dialogue_rows(story)
    if len(rows) < 12:
        return story, False
    lines = [str(r.get("line") or "").strip() for r in rows]
    speakers = [str(r.get("speaker") or "").strip() for r in rows]
    mom_ask_i = next(
        (
            i
            for i, (sp, line) in enumerate(zip(speakers, lines))
            if sp == "妈妈" and RE_MOM_ASK.search(line)
        ),
        -1,
    )
    if mom_ask_i < 0 or mom_ask_i >= len(rows) - 1:
        return story, False
    next_i = mom_ask_i + 1
    if speakers[next_i] != "昭昭":
        return story, False
    line = lines[next_i]
    blames_sister = bool(
        re.search(r"姐姐先|是姐姐|都怪姐姐", line)
        and not re.search(r"我.{0,6}先", line)
    )
    admits = bool(re.search(r"推|动手|弄花|弄坏|我先|我……先", line))
    if admits and not blames_sister:
        return story, False
    out = copy.deepcopy(story)
    out["dialogue"][next_i]["line"] = "我……我先弄花的，姐姐对不起！"
    return out, True


def patch_dedupe_ne_suffix(story: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """句尾「呢呢」叠字 → 单「呢」。"""
    import copy

    out = copy.deepcopy(story)
    changed = False
    for item in out.get("dialogue") or []:
        if not isinstance(item, dict):
            continue
        line = str(item.get("line") or "")
        if not line.endswith("呢呢"):
            continue
        item["line"] = line[:-1]
        changed = True
    return (out, True) if changed else (story, False)


def patch_fix_role_pronouns(story: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """妈妈台词：推他/推她 → 推姐姐；避免性别称谓错位。"""
    import copy

    out = copy.deepcopy(story)
    changed = False
    for item in out.get("dialogue") or []:
        if not isinstance(item, dict):
            continue
        if str(item.get("speaker") or "").strip() != "妈妈":
            continue
        line = str(item.get("line") or "")
        new_line = (
            line.replace("推他", "推姐姐")
            .replace("推她", "推姐姐")
            .replace("原谅他", "原谅昭昭")
        )
        if new_line != line:
            item["line"] = new_line
            changed = True
    return out, changed


def patch_strip_mom_fight_question(
    story: dict[str, Any],
    *,
    closing_intent: str = "",
) -> tuple[dict[str, Any], bool]:
    """closing_intent 指定灿灿问时，删妈妈句内重复「还打不打架」。"""
    import copy

    asker = _parse_fight_question_asker(closing_intent)
    if asker != "灿灿":
        return story, False
    out = copy.deepcopy(story)
    changed = False
    for item in out.get("dialogue") or []:
        if not isinstance(item, dict):
            continue
        if str(item.get("speaker") or "").strip() != "妈妈":
            continue
        line = str(item.get("line") or "").strip()
        if not RE_FIGHT_QUESTION.search(line):
            continue
        if "拉手" in line:
            item["line"] = "来，拉手。"
        else:
            trimmed = RE_FIGHT_QUESTION.sub("", line).strip("，, ")
            item["line"] = trimmed or "好了。"
        changed = True
    return out, changed


def patch_fix_mom_balance_line(
    story: dict[str, Any],
    *,
    conflict_text: str = "",
) -> tuple[dict[str, Any], bool]:
    """妈妈第二句定责：先点先动手方，再点受害方报复，禁单边原谅。"""
    import copy

    victim = _parse_conflict_victim(conflict_text)
    if not victim:
        return story, False
    rows = _dialogue_rows(story)
    mom_rows: list[tuple[int, str]] = []
    for i, row in enumerate(rows):
        if str(row.get("speaker") or "").strip() != "妈妈":
            continue
        line = str(row.get("line") or "").strip()
        if RE_MOM_ASK.search(line) or "住手" in line or "别打" in line:
            continue
        mom_rows.append((i, line))
    if not mom_rows:
        return story, False
    out = copy.deepcopy(story)
    changed = False
    for target_idx, line in mom_rows:
        if RE_MOM_BALANCE.search(line) and victim in line and "互相" not in line:
            continue
        if RE_ONE_SIDED.search(line) or (
            "原谅" in line and victim not in line
        ):
            new_line = (
                f"昭昭先撕不对，{victim}你也别撕回去。推人不对，额头先处理。"
            )
        elif "也有错" in line or RE_MOM_SOFT.search(line) or "互相" in line:
            new_line = (
                f"昭昭先撕不对，{victim}你也别撕回去。推人不对，额头先处理。"
            )
        elif "推" in line and victim not in line:
            new_line = (
                f"昭昭先撕不对，{victim}你也别撕回去。"
                f"推{victim}不对，额头先处理。"
            )
        else:
            continue
        new_line = f"昭昭先撕不对，{victim}别撕回去。先处理伤口。"
        out["dialogue"][target_idx]["line"] = new_line
        changed = True
    if not changed:
        return story, False
    return out, True


def patch_m5_move_rule_before_denial(
    story: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    """M5 立规句移到首句拒和/加码之前。"""
    import copy

    rows = _dialogue_rows(story)
    if len(rows) < 10:
        return story, False
    lines = [str(r.get("line") or "").strip() for r in rows]
    speakers = [str(r.get("speaker") or "").strip() for r in rows]
    rule_i = next(
        (
            i
            for i, (sp, line) in enumerate(zip(speakers, lines))
            if sp in {"昭昭", "灿灿"}
            and RE_M5_AUTHORITY.search(line)
            and RE_M5_RULE.search(line)
        ),
        -1,
    )
    deny_i = next(
        (
            i
            for i, (sp, line) in enumerate(zip(speakers, lines))
            if sp in {"昭昭", "灿灿"}
            and (RE_M5_STUBBORN.search(line) or RE_M5_ESCALATE.search(line))
        ),
        -1,
    )
    if rule_i < 0 or deny_i < 0 or rule_i < deny_i:
        return story, False
    out = copy.deepcopy(story)
    dlg = out["dialogue"]
    dlg.insert(deny_i, dlg.pop(rule_i))
    return out, True


def patch_trim_closing_invent(story: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """删 story_raw 未提 invent：拉钩/小狗/一起重画等。"""
    import copy
    import re as _re

    inv = _re.compile(r"拉钩|谁打谁|小狗|一起重画|交换礼物")
    rows = _dialogue_rows(story)
    if not rows:
        return story, False
    out = copy.deepcopy(story)
    kept: list[dict] = []
    changed = False
    for item in out.get("dialogue") or []:
        if not isinstance(item, dict):
            continue
        line = str(item.get("line") or "").strip()
        if inv.search(line):
            changed = True
            continue
        kept.append(item)
    if not changed:
        return story, False
    out["dialogue"] = kept
    return out, True


def patch_remove_mom_forced_forgive(
    story: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    """删妈妈「道歉了就要原谅」类单边逼和句。"""
    import copy

    rows = _dialogue_rows(story)
    if not rows:
        return story, False
    out = copy.deepcopy(story)
    kept: list[dict] = []
    changed = False
    for item in out.get("dialogue") or []:
        if not isinstance(item, dict):
            kept.append(item)
            continue
        if str(item.get("speaker") or "").strip() != "妈妈":
            kept.append(item)
            continue
        line = str(item.get("line") or "").strip()
        if "就要原谅" in line or "道歉了就要" in line:
            changed = True
            continue
        kept.append(item)
    if not changed:
        return story, False
    out["dialogue"] = kept
    return out, True


def patch_m5_remove_premature_mom_blame(
    story: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    """删妈妈问谁先动手之前的定责/扯平句（Pass2 本地）。"""
    import copy

    rows = _dialogue_rows(story)
    if len(rows) < 12:
        return story, False
    lines = [str(r.get("line") or "").strip() for r in rows]
    speakers = [str(r.get("speaker") or "").strip() for r in rows]
    mom_ask_i = next(
        (
            i
            for i, (sp, line) in enumerate(zip(speakers, lines))
            if sp == "妈妈" and RE_MOM_ASK.search(line)
        ),
        -1,
    )
    if mom_ask_i <= 0:
        return story, False
    out = copy.deepcopy(story)
    dlg = out["dialogue"]
    changed = False
    for i in range(mom_ask_i - 1, -1, -1):
        if speakers[i] != "妈妈":
            continue
        line = lines[i]
        if RE_MOM_ASK.search(line):
            break
        if (
            "也有错" in line
            or "该道歉" in line
            or RE_MOM_SOFT.search(line)
            or RE_ONE_SIDED.search(line)
        ):
            dlg.pop(i)
            changed = True
    if not changed:
        return story, False
    return out, True


def apply_m5_h_local_patches(
    story: dict[str, Any],
    *,
    closing_intent: str = "",
    conflict_text: str = "",
) -> tuple[dict[str, Any], bool]:
    """M5+H Pass2 本地补丁：称谓 → 定责 → 立规 → 拆合并 → 问句 speaker → 齐声 → 加码 → 碘伏后删尾。"""
    data, c0 = patch_remap_sibling_terms(story)
    data, c0b = patch_fix_role_pronouns(data)
    data, c0c = patch_fix_mom_balance_line(data, conflict_text=conflict_text)
    data, c1 = patch_m5_rule_authority(data)
    data, c1r = patch_m5_move_rule_before_denial(data)
    data, c2 = patch_split_m5_merged_line(data)
    data, c2b = patch_m5_retaliation_action(data, conflict_text=conflict_text)
    data, c2c = patch_m5_soften_premature_push_blame(data, conflict_text=conflict_text)
    data, c3b = patch_strip_mom_fight_question(data, closing_intent=closing_intent)
    data, c3 = patch_fight_question_speaker(data, closing_intent=closing_intent)
    data, c4 = patch_ensure_chorus_bukeda(data, closing_intent=closing_intent)
    data, c5 = patch_m5_pre_mom_escalation(data)
    data, c7 = patch_ensure_injury_after_push(data)
    data, c8 = patch_m5_fix_pre_mom_sequence(data)
    data, c8b = patch_m5_remove_premature_mom_blame(data)
    data, c8c = patch_remove_mom_forced_forgive(data)
    data, c1b = patch_m5_insert_authority_before_mom(data)
    data, c0d = patch_m5_denial_speaker_swap(data)
    data, c8d = patch_fix_mom_ask_admission(data)
    data, c9 = patch_sanitize_iodine_line(data)
    data, c9b = patch_trim_closing_invent(data)
    data, c6 = patch_trim_post_iodine_tail(data)
    data, c10 = patch_dedupe_ne_suffix(data)
    return (
        data,
        c0
        or c0b
        or c0d
        or c0c
        or c1
        or c1r
        or c1b
        or c2
        or c2b
        or c2c
        or c3
        or c3b
        or c4
        or c5
        or c7
        or c8
        or c8b
        or c8c
        or c8d
        or c9
        or c9b
        or c6
        or c10,
    )


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
    stubborn_idx = next(
        (i for i, x in enumerate(pre_mom) if RE_M5_STUBBORN.search(x)),
        -1,
    )
    has_hard = stubborn_idx >= 0 or any(RE_M5_STUBBORN.search(x) for x in pre_mom)
    if stubborn_idx >= 0:
        has_escalate = any(
            RE_M5_ESCALATE.search(x) for x in pre_mom[stubborn_idx + 1 :]
        )
    else:
        has_escalate = any(RE_M5_ESCALATE.search(x) for x in pre_mom)
    if has_hard and has_escalate:
        return story, False

    out = copy.deepcopy(story)
    dlg = out["dialogue"]
    candidate = _escalate_line_for_context(pre_mom)

    if stubborn_idx >= 0 and not has_escalate:
        insert_at = stubborn_idx + 1
        sp = str(dlg[insert_at].get("speaker") or "").strip()
        if sp not in {"昭昭", "灿灿"}:
            sp = str(dlg[stubborn_idx].get("speaker") or "灿灿").strip()
        if len(candidate) <= 30:
            from app.services.daily_story.gold_story.scene_contract import (
                CHAT_LINE_COUNT_MAX,
            )

            if len(dlg) >= CHAT_LINE_COUNT_MAX:
                dlg[stubborn_idx]["line"] = candidate
            else:
                dlg.insert(insert_at, {"speaker": sp, "line": candidate})
            return out, True

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
        if RE_M5_AUTHORITY.search(cur):
            return story, False
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
