"""H3a scene_contract：可拍场景契约。"""

from __future__ import annotations

import json
import re
from typing import Any

from app.services.daily_story.dialogue_text import DAILY_STORY_LINE_CHARS_MAX
from app.services.daily_story.speaker import DAILY_STORY_SPEAKER_NAMES

ALLOWED_SPEAKERS = frozenset(DAILY_STORY_SPEAKER_NAMES)
ILLEGAL_SPEAKER_HINTS = (
    "小男孩",
    "小女孩",
    "陌生",
    "对方",
    "老师",
    "博主",
    "哥哥",
    "妹妹",
)
TUTORIAL_RESIDUE = (
    "第一招",
    "第二招",
    "第三招",
    "第四招",
    "四招",
    "方法",
    "经验分享",
    "应该",
    "告诉",
    "教会",
)
MOM_BANNED_IN_LINE = ("应该", "告诉", "记住")
# 「教」只在家长**说教**时算违规；追问出处（谁教你的/哪学的）是机制拍，不算说教
MOM_PREACH_JIAO_RE = re.compile(r"(?<![谁哪])教")


def parent_line_looks_preachy(line: str) -> bool:
    """家长台词是否像说教（含「教」的说教用法，放过追问出处）。"""
    text = str(line or "")
    if any(word in text for word in MOM_BANNED_IN_LINE):
        return True
    return bool(MOM_PREACH_JIAO_RE.search(text))

# 身份自称归属：孩子标签（逐字稿/seed 都可能用）与家长标签。
# 只认「身份自称」这一强排他谓词，不碰任何剧情/行为词。
CHILD_SPEAKER_LABELS = frozenset(
    {"宝宝", "孩子", "儿子", "女儿", "女孩", "男孩", "弟弟", "妹妹", "昭昭", "灿灿"}
)
PARENT_SPEAKER_LABELS = ("妈妈", "爸爸")
_PARENT_IDENTITY_SELF_CLAIM = re.compile(
    r"我是(?:你|你们)?(?:妈|妈妈|爸|爸爸|家长|母亲|父亲)"
)
# 回声（扣原话/反问）：孩子复述家长身份主张时须转换人称，而非换归属
_PARENT_IDENTITY_ECHO_FRAME = re.compile(
    r"你还知道|你不是说|你说过|说我是|学我|学你"
)
_ROLEPLAY_FRAME = re.compile(r"假装|扮演|演一下|过家家")
_QUOTE_PAIRS = (("“", "”"), ("「", "」"), ("『", "』"))


def _inside_quotes(text: str, pos: int) -> bool:
    """match 起点是否落在引号内（真引述照原样保留）。"""
    head = text[:pos]
    for opener, closer in _QUOTE_PAIRS:
        if head.count(opener) > head.count(closer):
            return True
    return head.count('"') % 2 == 1


def _swap_person_deixis(span: str) -> str:
    """我/你 对调：孩子复述家长身份主张时用。"""
    return span.translate(str.maketrans({"我": "你", "你": "我"}))

_PAREN_IN_LINE = re.compile(r"（[^）]*）|\([^)]*\)")
_RELAY_SPEECH = re.compile(
    r"(?:妈妈|爸爸)(?:说了|说，|教过|告诉我|说过)|"
    r"你上次说的呀|一位(?:妈妈|爸爸)|经验分享|第[一二三四1-4]招"
)
_RELAY_PARENT_PREFIX = re.compile(r"^(?:妈妈|爸爸)(?:说了|说过|说)[，,:： ]+")
_REMAP_SIBLING_TERMS = re.compile(r"哥哥|弟弟")

CHAT_LINE_COUNT_MIN = 12
CHAT_LINE_COUNT_MAX = 24
CHAT_MAX_LINE_CHARS = DAILY_STORY_LINE_CHARS_MAX
CHAT_AVG_LINE_CHARS_MAX = 22
SEED_MIN = 4
BEAT_CHAIN_MIN = 4
# 每拍声明的「可落地最小回合数」上下界，以及正文回合数下限（= 正文最少句数）。
BEAT_MIN_TURNS_MIN = 1
BEAT_MIN_TURNS_MAX = 3
DIALOGUE_TURNS_MIN = CHAT_LINE_COUNT_MIN


_TERMINAL_NO_REPLY_RE = re.compile(
    r"(?:不再|没再|不敢再)(?:接话|搭话|回话|顶嘴|回嘴|反驳|说话)|"
    r"(?:不|没)(?:接话|搭话|回话|说话)|"
    r"低头[^，。！？]{0,16}(?:不接话|不说话|没再说)|"
    r"沉默(?:收场|下来|不语)?$|无话可说$"
)


_TERMINAL_NO_REPLY_DIALOGUE_INTENT = re.compile(
    r"^(?:回答|作答|解释|反驳|嘴硬|接话|回嘴)[:：]"
)


def is_terminal_no_reply_intent(intent: str) -> bool:
    """是否是只能作为表演结果、不能再生成一条对白的末拍。"""
    text = str(intent or "").strip()
    if not text:
        return False
    if _TERMINAL_NO_REPLY_DIALOGUE_INTENT.match(text):
        return False
    if re.search(r"[？?]", text):
        return False
    return bool(_TERMINAL_NO_REPLY_RE.search(text))


def trim_terminal_no_reply_rows(rows: list[Any] | None) -> tuple[list[Any], list[str]]:
    """去掉末尾“沉默/不再接话”结果行；中段语塞/停顿仍可保留。"""
    out = list(rows or [])
    notes: list[str] = []
    while out:
        row = out[-1]
        if not isinstance(row, dict):
            break
        if isinstance(row, dict) and str(row.get("line") or "").strip():
            break
        intent = str(row.get("intent") or row.get("beat") or "").strip()
        if not is_terminal_no_reply_intent(intent):
            break
        notes.append(intent)
        out.pop()
    return out, notes


def normalize_scene_dialogue_beats(
    contract: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    """scene beat_chain 只保留可展开成对白的末拍，避免 punchline 后硬续“沉默”。"""
    if not isinstance(contract, dict):
        return contract, []
    chain = contract.get("beat_chain")
    if not isinstance(chain, list) or not chain:
        return contract, []
    trimmed, removed = trim_terminal_no_reply_rows(chain)
    if not removed:
        return contract, []
    out = dict(contract)
    normalized: list[Any] = []
    for idx, row in enumerate(trimmed, 1):
        if isinstance(row, dict):
            item = dict(row)
            if "beat" in item:
                item["beat"] = idx
            normalized.append(item)
        else:
            normalized.append(row)
    out["beat_chain"] = normalized
    return out, [f"移除末尾纯静默结果拍:{text}" for text in reversed(removed)]


_RETROSPECTIVE_TOPIC_RE = re.compile(
    r"(?:旧事|往事|回忆|经历|小时候|童年|当年|曾经|以前|那次|事故|的事)$|"
    r"(?:旧事|往事|回忆|经历|小时候|童年|当年|曾经|以前|那次|事故)"
)
_RETROSPECTIVE_MATERIALIZE_NOTE_RE = re.compile(
    r"(?:替代|近似|换成|改成|搬到|搬进|端出|拿出|重演)"
)


def is_retrospective_topic_object(value: str) -> bool:
    """object 是过去事件/回忆话题，而不是当前场景要持有的实体物。"""
    text = str(value or "").strip()
    return bool(text and _RETROSPECTIVE_TOPIC_RE.search(text))


_PARENT_SPEAKER_SET = frozenset({"妈妈", "爸爸"})
# ── 出厂设定：本系统永远不允许「只有一个孩子出场」 ────────────────────────
# 这是产品级约束，不是某一类的临时处理：孩子戏份靠两个孩子交替，才能既有
# 需要的句数、又不出现同人连说。所有「补角色 / 查人数 / 单孩兜底」都必须
# 走下面这两个函数，禁止在各处再写 `if len(kids) == 1` 的临时分支
# （此前这种分支散在 16 处，逐个补必然漏，且互相冲突）。
_KID_SPEAKER_SET = frozenset({"昭昭", "灿灿"})
_DEFAULT_KID_ORDER: tuple[str, str] = ("昭昭", "灿灿")


def kid_speakers_of(names: Any) -> list[str]:
    """从任意名单里挑出孩子，并按既定顺序（昭昭 → 灿灿）返回。"""
    raw = {str(n).strip() for n in (names or []) if str(n).strip()}
    return [k for k in _DEFAULT_KID_ORDER if k in raw]


def ensure_two_kids(names: Any) -> list[str]:
    """保证至少两个孩子在场（不足则补齐）。

    唯一权威入口：任何要产出/校验对白人物的地方都用它，
    不要在调用点再判断人数。
    """
    kids = kid_speakers_of(names)
    if not kids:
        return list(_DEFAULT_KID_ORDER)
    if len(kids) >= 2:
        return kids
    # 只有一个孩子：补另一个同侧孩子（不是删他）
    for cand in _DEFAULT_KID_ORDER:
        if cand not in kids:
            kids.append(cand)
            break
    return kids


def ensure_two_kid_cast(cast: Any) -> list[str]:
    """把「家长 + 孩子」名单补成「家长 + 两个孩子」，保持原有顺序风格。"""
    items = [str(c).strip() for c in (cast or []) if str(c).strip()]
    parents = [c for c in items if c in _PARENT_SPEAKER_SET]
    kids = ensure_two_kids(items)
    # 家长在前、孩子在后（与项目既有约定一致）；没有家长信息时保留默认家长
    if not parents:
        parents = ["妈妈"]
    ordered = list(dict.fromkeys([*parents, *kids]))
    return ordered



# 家长拍的对话动词（越权塞进孩子拍时会暴露）
_PARENT_ASK_CLAUSE_RE = re.compile(
    r"(?:妈妈|爸爸)[^，,。；;]{0,6}?(?:追问|质问|反问|问|震惊追问|插问)"
    r"[^，,。；;]{0,24}"
)


def normalize_parent_beat_ownership(
    contract: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    """拍位所有权：家长动作不得塞在孩子拍里；家长追问拍数不得超额度。

    两条机读不变量（抽象，不绑剧情词）：
    - 每拍 intent 只写该拍 speaker 自己的动作。孩子拍里混入「妈妈追问…」
      这类越权动作时剥离，并归并到相邻的家长拍（无相邻家长拍则丢弃该短语，
      由提示词保证下次不写）。
    - 家长功能拍数不得超过 ``mom_lines_max``：超额的追问拍按功能合并成
      一拍（追问意思 + 追问出处并入同一问句），不把追问外派给旁观孩子。
    """
    if not isinstance(contract, dict):
        return contract, []
    chain = contract.get("beat_chain")
    if not isinstance(chain, list) or not chain:
        return contract, []
    rows: list[dict[str, Any]] = []
    notes: list[str] = []
    changed = False
    orphan_clauses: list[tuple[int, str]] = []
    for row in chain:
        if not isinstance(row, dict):
            continue
        item = dict(row)
        speaker = str(item.get("speaker") or "").strip()
        intent = str(item.get("intent") or "").strip()
        if speaker and speaker not in _PARENT_SPEAKER_SET and intent:
            clauses = _PARENT_ASK_CLAUSE_RE.findall(intent)
            if clauses:
                stripped = intent
                for clause in clauses:
                    stripped = stripped.replace(clause, "")
                    orphan_clauses.append((len(rows), clause.strip("，,。；;")))
                    notes.append(f"剥离越权家长动作:{clause.strip('，,。；;')}")
                stripped = re.sub(r"[，,]{2,}", "，", stripped).strip("，,。；; ")
                item["intent"] = stripped or intent
                changed = True
        rows.append(item)
    if not rows:
        return contract, []
    # 剥离出的家长动作归并到**最近的**家长拍（后优先、再前），笑点链不被删除
    for orphan_idx, clause in orphan_clauses:
        parent_idx = [
            idx
            for idx, row in enumerate(rows)
            if str(row.get("speaker") or "").strip() in _PARENT_SPEAKER_SET
        ]
        if not parent_idx:
            break
        after = [idx for idx in parent_idx if idx > orphan_idx]
        host_idx = after[0] if after else parent_idx[-1]
        host = rows[host_idx]
        host_intent = str(host.get("intent") or "").strip()
        if clause and clause not in host_intent:
            host["intent"] = f"{host_intent}、{clause}".strip("、")
            notes.append(f"归并家长动作到第{host_idx + 1}拍")
    try:
        mom_max = max(0, int(contract.get("mom_lines_max") or 0))
    except (TypeError, ValueError):
        mom_max = 0
    # 预算按「家长拍总数」算（含收束拍）：超额的追问拍按功能合并成一拍
    parent_rows = [
        (idx, row)
        for idx, row in enumerate(rows)
        if str(row.get("speaker") or "").strip() in _PARENT_SPEAKER_SET
        and str(row.get("intent") or "").strip()
    ]
    if mom_max and len(parent_rows) > mom_max:
        merge_rows = [
            (idx, row)
            for idx, row in parent_rows
            if re.search(r"追问|质问|反问|设问|发问", str(row.get("intent") or ""))
        ]
        need_drop = len(parent_rows) - mom_max
        while need_drop > 0 and len(merge_rows) > 1:
            # 合并到**最后一拍追问**（而非第一拍）：家长的合并追问落在孩子的
            # 怪词/自洽之后，开场因果（孩子拍先落地）不被推到家长问句后面。
            host_idx, host = merge_rows[-1]
            donor_idx, donor = merge_rows[0]
            host_intent = str(host.get("intent") or "").strip()
            donor_intent = str(donor.get("intent") or "").strip()
            host["intent"] = f"{host_intent}、{donor_intent}"[:120]
            rows.pop(donor_idx)
            notes.append(f"合并家长追问拍:{donor_intent[:16]}→{host_intent[:16]}")
            changed = True
            parent_rows = [
                (idx, row)
                for idx, row in enumerate(rows)
                if str(row.get("speaker") or "").strip() in _PARENT_SPEAKER_SET
                and str(row.get("intent") or "").strip()
            ]
            merge_rows = [
                (idx, row)
                for idx, row in parent_rows
                if re.search(r"追问|质问|反问|设问|发问", str(row.get("intent") or ""))
            ]
            need_drop = len(parent_rows) - mom_max
    # 契约自洽：家长拍数是机制骨架（立规 / 追问 / 收束），额度是派生约束。
    # 合并后仍装不下时，把额度抬到拍数——否则「契约要求妈妈问、又只给 N 句额度」
    # 是死锁，任何一稿都必然违规（#87 实测：3 拍 vs mom_lines_max=2）。
    parent_rows = [
        (idx, row)
        for idx, row in enumerate(rows)
        if str(row.get("speaker") or "").strip() in _PARENT_SPEAKER_SET
        and str(row.get("intent") or "").strip()
    ]
    if parent_rows and len(parent_rows) > int(contract.get("mom_lines_max") or 0):
        out_budget = dict(contract)
        out_budget["mom_lines_max"] = len(parent_rows)
        notes.append(f"家长额度抬到拍数:{contract.get('mom_lines_max')}→{len(parent_rows)}")
        contract = out_budget
    if not changed:
        return contract, notes if notes else []
    out = dict(contract)
    normalized: list[Any] = []
    for idx, row in enumerate(rows, 1):
        item = dict(row)
        if "beat" in item:
            item["beat"] = idx
        normalized.append(item)
    out["beat_chain"] = normalized
    return out, notes


_N_MECHANISM_ASK_RE = re.compile(r"追问|质问|反问|设问|发问|问：|问")
# N 机制推进拍：孩子「一本正经回答/解释/自洽」那一侧才是机制主体
_N_MECHANISM_CHILD_RE = re.compile(
    r"回答|作答|解释|自洽|讲圆|理由|原因|离谱|报出|说出|嘴硬|秒答|反驳"
)


def normalize_cast_to_beats(
    contract: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    """角色表只保留 beat_chain 里**真有拍**的角色。

    没有拍的角色不许出场：H3a 的角色表常被「单孩源拆双孩」提示带上一个
    全程没有拍的孩子（#87：characters 含灿灿，beat_chain 只有妈妈+昭昭）。
    这个幽灵角色会让扩写照着角色表把她写进对白，随后又被契约补丁删除，
    字数随之塌方、垫字与去重来回打架。角色表对齐 beat 是更上游的修法。
    """
    chain = contract.get("beat_chain")
    if not isinstance(contract, dict) or not isinstance(chain, list) or not chain:
        return contract, []
    used = {
        str(row.get("speaker") or "").strip()
        for row in chain
        if isinstance(row, dict) and str(row.get("speaker") or "").strip()
    }
    chars = [
        str(c).strip()
        for c in (contract.get("characters") or [])
        if str(c).strip()
    ]
    if not chars or not used:
        return contract, []
    kept = [c for c in chars if c in used]
    if not kept or kept == chars:
        return contract, []
    out = dict(contract)
    out["characters"] = kept
    removed = [c for c in chars if c not in used]
    return out, [f"移除无拍角色:{'、'.join(removed)}"]


def needs_second_kid(contract: dict[str, Any] | None) -> bool:
    """契约是否应补第二个孩子（单孩源拆双孩）。

    N 类家长当追问方时是两人手（家长 × 单孩），不补第二孩：
    否则 seed 先被补、再被两人手规则删掉，来回震荡（#87 实测）。
    """
    # 两个孩子是「禁同人连说」的解法：只给一个孩子时，家长额度一旦封顶，
    # 剩下的句子只能由同一个孩子连说（用户裁决：禁止连说 → 必须补第二孩）。
    return True


_N_CAUSAL_INTENT_RE = re.compile(r"因为|所以|就这么|这样就能|就能|理由|讲圆|自洽")
_N_STUN_INTENT_RE = re.compile(r"愣|服了|接不住|说不出|算了|放弃|噎")
_N_CHILD_REASON_INTENT_RE = re.compile(r"解释|回答|作答|讲圆|自洽|理由|原因")


def normalize_n_formula_slots(
    contract: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    """N 公式槽自洽：契约必须写明「一本正经自洽」与「愣住/接不住收束」两槽。

    N 的机检按公式判（正文须有因为/所以那类自洽、收束须落愣住/接不住），
    但 H3a 常只写「解释成…」「决定以后先打草稿」——契约没这两个槽，
    照契约写的稿必然被判不合格（#87 实测：20 次缺自洽、17 次缺收束）。

    这里只给契约**补公式槽位标注**，不新造剧情事实：
    - 孩子已有解释/回答拍却缺因果连词 → 在该拍 intent 前标「讲圆」并点明用因为/所以；
    - 末拍家长收束缺愣住/接不住 → 在 intent 末尾补「最后只能服了/接不住」。
    """
    if not isinstance(contract, dict):
        return contract, []
    if str(contract.get("story_type") or "").strip().upper() != "N":
        return contract, []
    chain = contract.get("beat_chain")
    if not isinstance(chain, list) or not chain:
        return contract, []
    rows = [dict(r) for r in chain if isinstance(r, dict)]
    if not rows:
        return contract, []
    notes: list[str] = []
    changed = False

    # 收束拍缺失：N 必须有立规方的破功收束（这是机制终点，不是可选装饰）。
    # 缺了会同时导致「收束须愣住」和「家长额度不够」两类判词（#87 实测）。
    parent_rows_all = [
        r for r in rows if str(r.get("speaker") or "").strip() in _PARENT_SPEAKER_SET
    ]
    has_close = False
    for r in parent_rows_all:
        c_text = str(r.get("intent") or r.get("beat") or "")
        # 追问句里也常带「愣住」（愣住追问），那是问不是收束，必须排除，
        # 否则缺口会被误判成「已经有收束」（#87 实测）。
        if re.search(r"追问|质问|反问|设问|问：|谁教|什么意思", c_text):
            continue
        if re.search(r"收束|决定|以后|打草稿|认栽|服了|接不住", c_text):
            has_close = True
            break
    if parent_rows_all and not has_close:
        tail_kid = rows[-1]
        tail_sp = str(tail_kid.get("speaker") or "").strip()
        closer = {"speaker": parent_rows_all[-1].get("speaker") or "妈妈",
                  "intent": "收束：认栽，说以后说话得先打草稿，最后只能服了/接不住"}
        if tail_sp in _PARENT_SPEAKER_SET:
            rows.append(closer)
        else:
            rows.append(closer)
        notes.append("补N收束拍")
        changed = True

    has_causal = any(
        _N_CAUSAL_INTENT_RE.search(str(r.get("intent") or r.get("beat") or ""))
        for r in rows
    )
    if not has_causal:
        target = next(
            (
                r
                for r in rows
                if str(r.get("speaker") or "").strip() not in _PARENT_SPEAKER_SET
                and _N_CHILD_REASON_INTENT_RE.search(
                    str(r.get("intent") or r.get("beat") or "")
                )
            ),
            None,
        )
        if target is not None:
            intent = str(target.get("intent") or target.get("beat") or "").strip()
            target["intent"] = f"一本正经讲圆（用因为/所以）：{intent}"[:160]
            notes.append("补N自洽槽标注")
            changed = True

    parent_rows = [
        r for r in rows if str(r.get("speaker") or "").strip() in _PARENT_SPEAKER_SET
    ]
    if parent_rows:
        closing = parent_rows[-1]
        c_intent = str(closing.get("intent") or closing.get("beat") or "").strip()
        if not _N_STUN_INTENT_RE.search(c_intent):
            closing["intent"] = f"{c_intent}，最后只能服了/接不住"[:160]
            notes.append("补N愣住收束槽")
            changed = True

    if not changed:
        return contract, []
    # 重编号并同步家长额度：额度是拍数的派生约束，拍数变了额度必须跟着变，
    # 否则「契约要求妈妈追问 + 收束，却只给 2 句」会再次死锁。
    for i, row in enumerate(rows, 1):
        row["beat"] = i
    out = dict(contract)
    out["beat_chain"] = rows
    parent_n = sum(
        1 for r in rows
        if str(r.get("speaker") or "").strip() in _PARENT_SPEAKER_SET
        and str(r.get("intent") or "").strip()
    )
    if parent_n:
        try:
            cur = int(out.get("mom_lines_max") or 0)
        except (TypeError, ValueError):
            cur = 0
        if parent_n > cur:
            out["mom_lines_max"] = parent_n
            notes.append(f"家长额度抬到拍数:{cur}→{parent_n}")
    return out, notes


# 同侧第二个孩子的反应拍（抽象，不承担机制、不代问关键追问）。
# 用户/专家口径：孩子不能连说 5 句；戏份交给第二个孩子交替，而不是把
# 第二个孩子删掉（删了她就只剩两人手，孩子必然连说 3+ 句）。
# 第二个孩子的拍：只给**意图**，不给台词。
#
# 这是一次方向修正。此前我把她该说的话写成死句子（「有几个？」「在哪儿？」），
# 结果是静态模板去接动态对话——问「几个人知道」答「你信不信都行」，必然
# 答非所问；换个模板就换一种错法，永远收敛不了（#87 实测 10+ 轮）。
#
# 正确做法：契约只声明「她这一拍要干什么」，台词交给模型结合上下文写。
# 三条约束保持：不引用上下文、不提那个机制词、不承担机制。
# 第二孩的拍：**给具体台词，不给抽象意图**。
#
# 这是走了十几轮弯路才认的账：抽象意图（「补一个现场细节」「表示自己不信」）
# 交给模型自由发挥，产出的句子必然和上下文撞车——要么接不上前句、要么和
# 另一拍同义重复、要么凭空编出前文没有的东西。每换一种意图描述就换一种错法，
# 永远收敛不了。
#
# 她是主角之一（和机制孩子合伙把谎编圆），所以她的台词**自足**：不依赖
# 上文、不需要谁回答、也不含那个怪词。这种句子写死在契约里，模型照用即可。
#
# 分层设计，相邻几拍不会撞车：
#   报名 → 穿戴 → 场面 → 加码 → 情形 → 入伙
_N_SECOND_KID_LINES: tuple[str, ...] = (
    "我也认识几个好人，叫小美、小强、小丽。",
    "他上回还说要带一帮人来呢。",
    "这事儿有意思，我得盯着看。",
    "那我以后也这么说话成不成？",
    "你这么讲，我听着都替他害臊。",
    "他那人就这样，越说越来劲。",
)


def refresh_second_kid_intents(
    contract: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    """把旁观孩子（非机制方）的拍意图刷新成最新意图池。

    契约复用会保留库里的旧意图，于是「追问时间/地点」这类旧写法一直活着，
    而机检又拦关键追问 → 每轮都判归属错。搭档的拍本来就是我方补的，
    每次刷新安全且幂等。
    """
    if not isinstance(contract, dict):
        return contract, []
    if str(contract.get("story_type") or "").strip().upper() != "N":
        return contract, []
    chain = contract.get("beat_chain")
    if not isinstance(chain, list) or not chain:
        return contract, []
    rows = [dict(r) for r in chain if isinstance(r, dict)]
    kids = kid_speakers_of(
        [*(r.get("speaker") or "" for r in rows), *(contract.get("characters") or [])]
    )
    if len(kids) < 2:
        return contract, []
    mech: dict[str, int] = {}
    for r in rows:
        sp = str(r.get("speaker") or "").strip()
        if sp in kids and _N_MECHANISM_CHILD_RE.search(
            str(r.get("intent") or r.get("beat") or "")
        ):
            mech[sp] = mech.get(sp, 0) + 1
    if not mech:
        return contract, []
    main_kid = max(mech, key=lambda k: mech[k])
    partner = next((k for k in kids if k != main_kid), "")
    if not partner:
        return contract, []
    partner_rows = [
        r for r in rows if str(r.get("speaker") or "").strip() == partner
    ]
    if not partner_rows:
        return contract, []
    changed = 0
    for idx, row in enumerate(partner_rows):
        new_intent = _N_SECOND_KID_LINES[idx % len(_N_SECOND_KID_LINES)]
        if str(row.get("intent") or "") != new_intent:
            row["intent"] = new_intent
            changed += 1
    if not changed:
        return contract, []
    out = dict(contract)
    out["beat_chain"] = rows
    return out, [f"刷新第二孩意图:{changed}拍"]


_RE_SEED_EXPLAIN_PREFIX = re.compile(r"^解释这个词是什么意思[：:]\s*")
_RE_SEED_HALF_CAUSAL = re.compile(r"^(?:所以|因此|于是|才能|才)")


_RE_SECOND_PERSON_DRIFT = re.compile(
    r"就是你在|就你在|你在街上|你自己在|你们在|你那"
)


def fix_second_person_drift(seed: list[Any]) -> tuple[list[Any], list[str]]:
    """把 seed 里「你在……工作」这类**主语漂移**改成第一人称。

    机制孩子解释自己的事，说成「你在街上工作，别人给你钱」时，
    「你」就指向了家长——家长并没有上街工作，句子主谓错位，
    终检判「读一遍不知道在说什么」（#87 实测反复出现）。

    只改主语，不动其余内容；改成「我在街上工作」后语义自洽。
    """
    rows: list[Any] = []
    fixed = 0
    for item in seed or []:
        if not isinstance(item, dict):
            rows.append(item)
            continue
        row = dict(item)
        for key in ("intent", "line"):
            text = row.get(key)
            if not isinstance(text, str) or not text:
                continue
            if not _RE_SECOND_PERSON_DRIFT.search(text):
                continue
            new_text = text
            for old_pat, repl in (
                ("就是你在", "就是我在"),
                ("就你在", "就我在"),
                ("你在街上", "我在街上"),
                ("你自己在", "我自己在"),
                ("你们在", "我们在"),
                ("你那", "我那"),
            ):
                new_text = new_text.replace(old_pat, repl)
            if new_text != text:
                row[key] = new_text
                fixed += 1
        rows.append(row)
    if not fixed:
        return seed or [], []
    return rows, [f"seed主语漂移修正:{fixed}处"]


def clean_seed_fragments(seed: list[Any]) -> tuple[list[Any], list[str]]:
    """清掉 seed 里的**因果残句**。

    拆「怪词 + 解释」时会产生这种碎片：「解释这个词是什么意思：所以才能来」
    ——只有「所以」没有「因为」。模型照着写，成稿必然是因果断裂、
    答非所问（#87 实测多轮都栽在这句上）。

    只做保守处理：删掉以「所以/因此/才」开头的解释残句（信息量为零），
    完整解释由其它 seed 行提供。
    """
    rows: list[Any] = []
    fixed = 0
    for item in seed or []:
        if not isinstance(item, dict):
            rows.append(item)
            continue
        intent = str(item.get("intent") or "")
        m = _RE_SEED_EXPLAIN_PREFIX.match(intent)
        if m:
            tail = intent[m.end():].strip()
            if _RE_SEED_HALF_CAUSAL.match(tail):
                # 残句不能直接删！它是「解释这词」那一行，删了孩子就没解释过，
                # 后面家长再问「这词什么意思」会判「引用无据」（#87 实测）。
                # 换成一条完整的荒诞解释（保持抽象，不绑剧情物件）。
                row = dict(item)
                row["intent"] = (
                    "解释这个词是什么意思：一本正经给个荒诞但自洽的说法"
                    "（用第一人称说自己的事，不要把对方扯进去）"
                )
                rows.append(row)
                fixed += 1
                continue
        rows.append(item)
    if not fixed:
        return seed or [], []
    return rows, [f"修正seed因果残句:{fixed}条"]


_RE_DENY_TAUGHT = re.compile(r"^(?:否认有人教|否认教)[：:]\s*")
_RE_EXPLAIN = re.compile(r"^解释这个词是什么意思[：:]\s*")


def merge_seed_consecutive_kid_rows(
    seed: list[Any],
) -> tuple[list[Any], list[str]]:
    """把同一个孩子相邻的两条 seed 并成一行。

    连说在 N 里是硬禁止，而 seed 把「否认有人教」和「解释词义」拆成两行时，
    模型只能让同一个孩子连说两句，再叠上「苹果」就是三连（#87 实测：
    孩子连说 20–50 次，多数来自这里）。这两件事本来就该一口气说完，
    合成一行既自然、又少一次连说风险。
    """
    rows = [dict(r) if isinstance(r, dict) else r for r in (seed or [])]
    out: list[Any] = []
    merged = 0
    for item in rows:
        if not isinstance(item, dict) or not out:
            out.append(item)
            continue
        prev = out[-1]
        if not isinstance(prev, dict):
            out.append(item)
            continue
        same_speaker = (
            str(prev.get("speaker") or "").strip()
            and str(prev.get("speaker") or "").strip()
            == str(item.get("speaker") or "").strip()
        )
        if not same_speaker:
            out.append(item)
            continue
        prev_intent = str(prev.get("intent") or "")
        cur_intent = str(item.get("intent") or "")
        # 「否认有人教」后面紧跟同一孩子说的话 → 并成一行。
        # 不必要求下一行长得像「解释…」：清理残句后它就是普通句子，
        # 只按「同人说 + 前一句是否认」判断即可。
        if not _RE_DENY_TAUGHT.match(prev_intent):
            out.append(item)
            continue
        tail = _RE_EXPLAIN.sub("", cur_intent).strip()
        if not tail:
            out.append(item)
            continue
        merged_row = dict(item)
        merged_row["intent"] = (
            "解释这个词是什么意思：没人教，自己想的，" + tail
        )
        out[-1] = merged_row
        merged += 1
    if not merged:
        return seed or [], []
    return out, [f"合并孩子相邻seed:{merged}处"]


_RE_ASK_INTENT = re.compile(r"追问|质问|反问|设问|问：|什么意思|谁教|哪来|怎么|谁")


_N_DECLARED_TOKEN_SEARCH = re.compile(r"「[^」]{2,6}」|怪词|自造词")
_RE_SEED_TOKEN_OUT = re.compile(r"只说出这个词|说出这个词|蹦出")
_RE_SEED_TOKEN_EXPLAIN = re.compile(r"解释这个词")


def keep_seed_token_pair_adjacent(seed: list[Any]) -> tuple[list[Any], list[str]]:
    """seed 里「说出词 → 家长追问 → 解释」必须按这个顺序相邻。

    两个坑，都会直接判错：
      ① 中间夹旁观的拍 → 模型写成两段互不相连的因果
         （「因为街上有人工作」…「所以别人给你钱」被判因果断裂）；
      ② 解释排在家长追问**之前** → 提前答了后文的问题（判错位）。
    """
    rows = [dict(r) if isinstance(r, dict) else r for r in (seed or [])]
    out_i = next(
        (i for i, r in enumerate(rows) if isinstance(r, dict)
         and _RE_SEED_TOKEN_OUT.search(str(r.get("intent") or ""))),
        -1,
    )
    exp_i = next(
        (i for i, r in enumerate(rows) if isinstance(r, dict)
         and _RE_SEED_TOKEN_EXPLAIN.search(str(r.get("intent") or ""))),
        -1,
    )
    if out_i < 0 or exp_i < 0 or exp_i < out_i:
        return seed or [], []

    notes: list[str] = []

    def _is_parent_ask(row: Any) -> bool:
        if not isinstance(row, dict):
            return False
        return (
            str(row.get("speaker") or "").strip() in _PARENT_SPEAKER_SET
            and bool(
                _RE_ASK_INTENT.search(
                    str(row.get("intent") or row.get("line") or "")
                )
            )
        )

    # ① 清掉出词与解释之间的旁观拍
    between = [
        r
        for r in rows[out_i + 1 : exp_i]
        if isinstance(r, dict)
        and str(r.get("speaker") or "").strip() not in _PARENT_SPEAKER_SET
    ]
    if between:
        row = rows.pop(exp_i)
        rows.insert(out_i + 1, row)
        exp_i = out_i + 1
        notes.append("seed词与解释之间清掉旁观拍")

    # ② 家长追问必须在解释之前
    has_ask_before = any(_is_parent_ask(r) for r in rows[out_i:exp_i])
    if not has_ask_before:
        donor = next(
            (k for k in range(exp_i + 1, len(rows)) if _is_parent_ask(rows[k])),
            -1,
        )
        if donor >= 0:
            row_d = rows.pop(donor)
            rows.insert(exp_i, row_d)
            notes.append("seed家长追问移到解释前")

    # ③ 同一孩子不得相邻：把重复的那条挪到后面（收束前）去
    kids = {"昭昭", "灿灿"}
    parent_last = max(
        (
            k
            for k, r in enumerate(rows)
            if isinstance(r, dict)
            and str(r.get("speaker") or "").strip() in _PARENT_SPEAKER_SET
        ),
        default=len(rows) - 1,
    )
    for k in range(len(rows) - 1):
        a = str(rows[k].get("speaker") or "").strip() if isinstance(rows[k], dict) else ""
        b = (
            str(rows[k + 1].get("speaker") or "").strip()
            if isinstance(rows[k + 1], dict)
            else ""
        )
        if a in kids and a == b:
            row = rows.pop(k + 1)
            # 插到最后一个家长拍**之前**（收束必须在最后）；
            # 下标要在 pop 之后重新算，否则会插到末尾去。
            close_now = max(
                (
                    z
                    for z, rr in enumerate(rows)
                    if isinstance(rr, dict)
                    and str(rr.get("speaker") or "").strip()
                    in _PARENT_SPEAKER_SET
                ),
                default=len(rows) - 1,
            )
            pos = max(1, min(close_now, len(rows) - 1))
            rows.insert(pos, row)
            notes.append("seed同人相邻已拆开")
            break

    if not notes:
        return seed or [], []
    return rows, notes



def align_seed_to_contract_beats(
    seed: list[Any],
    *,
    contract: dict[str, Any] | None = None,
) -> tuple[list[Any], list[str]]:
    """让 seed **覆盖契约每一拍的说话人**。

    这是踩了十几轮才看清的架构缺口：契约给第二个孩子排了 3 拍，
    而 seed 里她**一条行都没有**（源素材只有单孩）。模型拿到的契约说
    「第 3 拍灿灿说话」，seed 却没有她的素材 → 只能凭空编，编出来的
    必然被判「接不上/缺前提/引用无据」。

    只有在「契约某说话人在 seed 里完全缺席」时才做重排（避免干扰正常稿）：
    按契约拍序逐拍取用 seed 里同说话人的下一行；缺席者用该拍 intent 合成。
    这样 seed 与契约的说话人序列一致，模型不用再编。
    """
    sc = contract if isinstance(contract, dict) else {}
    rows = [dict(r) for r in (seed or []) if isinstance(r, dict)]
    beats = [r for r in (sc.get("beat_chain") or []) if isinstance(r, dict)]
    if not rows or len(beats) < 2:
        return seed or [], []
    beat_speakers = [str(b.get("speaker") or "").strip() for b in beats]
    seed_speakers = {str(r.get("speaker") or "").strip() for r in rows}
    missing = {sp for sp in beat_speakers if sp and sp not in seed_speakers}
    # 家长问句在 seed 里可能多于契约的追问拍（追问被合并后会留下孤儿问句，
    # 没人回答 → 必判答非所问）。这种情况也要重排，把孤儿问句丢掉。
    contract_asks = [
        str(b.get("intent") or "")
        for b in beats
        if str(b.get("speaker") or "").strip() in _PARENT_SPEAKER_SET
        and _RE_ASK_INTENT.search(str(b.get("intent") or ""))
    ]
    seed_asks = [
        str(r.get("intent") or r.get("line") or "")
        for r in rows
        if str(r.get("speaker") or "").strip() in _PARENT_SPEAKER_SET
        and _RE_ASK_INTENT.search(str(r.get("intent") or r.get("line") or ""))
    ]
    orphan_asks = max(0, len(seed_asks) - len(contract_asks))
    if not missing and not orphan_asks:
        return seed or [], []
    if orphan_asks:
        # 逐个比对：seed 的家长问句能在契约追问里找到语义近邻才保留
        def _bigrams(text: str) -> set[str]:
            out_b: set[str] = set()
            for run in re.findall(r"[\u4e00-\u9fff]+", text):
                for k in range(len(run) - 1):
                    out_b.add(run[k : k + 2])
            return out_b

        kept_rows: list[Any] = []
        contract_grams = [_bigrams(a) for a in contract_asks]
        for r in rows:
            is_parent_ask = (
                str(r.get("speaker") or "").strip() in _PARENT_SPEAKER_SET
                and _RE_ASK_INTENT.search(str(r.get("intent") or r.get("line") or ""))
            )
            if not is_parent_ask:
                kept_rows.append(r)
                continue
            grams = _bigrams(str(r.get("intent") or r.get("line") or ""))
            if any(len(grams & cg) >= 1 for cg in contract_grams):
                kept_rows.append(r)
        rows = kept_rows

    pool = list(rows)
    out: list[Any] = []
    synthesized = 0
    for beat in beats:
        sp = str(beat.get("speaker") or "").strip()
        if not sp:
            continue
        idx = next(
            (
                i
                for i, r in enumerate(pool)
                if str(r.get("speaker") or "").strip() == sp
            ),
            -1,
        )
        if idx >= 0:
            out.append(pool.pop(idx))
            continue
        intent = str(beat.get("intent") or beat.get("beat") or "").strip()
        out.append(
            {
                "speaker": sp,
                "intent": intent or "顺着上一句接一句，说出自己的看法",
            }
        )
        synthesized += 1
    # 契约没覆盖到的 seed 行放回**收束前**，保证收束仍在末尾
    if pool:
        out = out[:-1] + pool + out[-1:]
    notes = [f"seed按契约补齐说话人:{'、'.join(sorted(missing))}(合成{synthesized}条)"]
    return out, notes


def prefix_answer_after_parent_ask(
    contract: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    """家长问句后面的那一拍，孩子必须**先直接回答**，再往下讲。

    反复出现的语义硬伤「妈妈问 X，孩子答 Y」（答非所问）根因在契约层：
    契约把「妈妈追问」和「孩子讲圆」排成相邻两拍，却没告诉模型这两拍是
    问答关系。模型就各写各的，终检必然判接不上。
    """
    if not isinstance(contract, dict):
        return contract, []
    chain = contract.get("beat_chain")
    if not isinstance(chain, list) or len(chain) < 2:
        return contract, []
    rows = [dict(r) for r in chain if isinstance(r, dict)]
    # 机制主体 = 说怪词/解释/自洽的那个孩子：家长问的、要他答的就是他。
    # 旁观孩子的拍是挑衅/帮腔，不承担「回答家长」的义务（加了反而错位）。
    mech: dict[str, int] = {}
    for r in rows:
        sp = str(r.get("speaker") or "").strip()
        if sp and sp not in _PARENT_SPEAKER_SET and _N_MECHANISM_CHILD_RE.search(
            str(r.get("intent") or r.get("beat") or "")
        ):
            mech[sp] = mech.get(sp, 0) + 1
    mech_kid = max(mech, key=lambda k: mech[k]) if mech else ""
    changed = 0
    for i in range(len(rows) - 1):
        cur = rows[i]
        nxt = rows[i + 1]
        cur_sp = str(cur.get("speaker") or "").strip()
        nxt_sp = str(nxt.get("speaker") or "").strip()
        if cur_sp not in _PARENT_SPEAKER_SET or nxt_sp in _PARENT_SPEAKER_SET:
            continue
        if mech_kid and nxt_sp != mech_kid:
            continue
        if not _RE_ASK_INTENT.search(str(cur.get("intent") or "")):
            continue
        intent = str(nxt.get("intent") or "")
        if intent.startswith("先直接回答"):
            continue
        nxt["intent"] = (
            "先直接回答上一句问的问题（点出具体答案，别绕开），" + intent
        )[:160]
        changed += 1
    if not changed:
        return contract, []
    out = dict(contract)
    out["beat_chain"] = rows
    return out, [f"问答配对标注:{changed}处"]


def keep_qa_adjacent(contract: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """家长问句后面必须紧跟机制孩子的回答，中间不许插旁观的拍。

    反复出现的「妈妈问 X，孩子答 Y／没人答」根因在此：交替规则会把同伴的
    挑衅拍插到「家长追问」和「机制孩子回答」中间，问答就被打断了。
    """
    if not isinstance(contract, dict):
        return contract, []
    chain = contract.get("beat_chain")
    if not isinstance(chain, list) or len(chain) < 3:
        return contract, []
    rows = [dict(r) for r in chain if isinstance(r, dict)]
    mech: dict[str, int] = {}
    for r in rows:
        sp = str(r.get("speaker") or "").strip()
        if sp and sp not in _PARENT_SPEAKER_SET and _N_MECHANISM_CHILD_RE.search(
            str(r.get("intent") or r.get("beat") or "")
        ):
            mech[sp] = mech.get(sp, 0) + 1
    mech_kid = max(mech, key=lambda k: mech[k]) if mech else ""
    if not mech_kid:
        return contract, []
    moved = 0
    for _ in range(4):
        acted = False
        for i in range(len(rows) - 1):
            cur_sp = str(rows[i].get("speaker") or "").strip()
            nxt_sp = str(rows[i + 1].get("speaker") or "").strip()
            if cur_sp not in _PARENT_SPEAKER_SET:
                continue
            if not _RE_ASK_INTENT.search(str(rows[i].get("intent") or "")):
                continue
            if nxt_sp in _PARENT_SPEAKER_SET or nxt_sp == mech_kid:
                continue
            # 把这条旁观的拍移到「下一个机制孩子拍」之后
            intruder = rows.pop(i + 1)
            target = next(
                (
                    j
                    for j in range(i + 1, len(rows))
                    if str(rows[j].get("speaker") or "").strip() == mech_kid
                ),
                -1,
            )
            if target < 0:
                rows.insert(i + 1, intruder)
                continue
            rows.insert(target + 1, intruder)
            moved += 1
            acted = True
            break
        if not acted:
            break
    if not moved:
        return contract, []
    for idx, row in enumerate(rows, 1):
        row["beat"] = idx
    out = dict(contract)
    out["beat_chain"] = rows
    return out, [f"问答相邻修复:{moved}处"]


def spread_kid_beats(contract: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """契约里两个孩子不得相邻连说（N 类硬规则）。

    任何一次「插入/搬移」都可能让两个孩子的拍挨在一起，扩写就会照着连说。
    这里做最后一次分配：把重复的那一拍挪到最近的安全空位
    （不在家长问句之后、不在收束之后）。
    """
    if not isinstance(contract, dict):
        return contract, []
    chain = contract.get("beat_chain")
    if not isinstance(chain, list) or len(chain) < 4:
        return contract, []
    rows = [dict(r) for r in chain if isinstance(r, dict)]
    kids = {"昭昭", "灿灿"}
    close_idx = max(
        (
            i
            for i, r in enumerate(rows)
            if str(r.get("speaker") or "").strip() in _PARENT_SPEAKER_SET
        ),
        default=len(rows) - 1,
    )

    # 旁观孩子的拍必须排在**机制已经展开之后**。
    # 只要求「机制孩子说过话」不够：他刚报完名字还没进入机制，她就来一句
    # 「我心里直打鼓」，必然无话头可接（#87 实测反复）。所以要排到
    # 第一个**机制拍**（讲圆/解释/说出怪词）之后。
    mech_sp = ""
    _mech_count: dict[str, int] = {}
    for r in rows:
        sp_r = str(r.get("speaker") or "").strip()
        if sp_r in kids and _N_MECHANISM_CHILD_RE.search(
            str(r.get("intent") or r.get("beat") or "")
        ):
            _mech_count[sp_r] = _mech_count.get(sp_r, 0) + 1
    if _mech_count:
        mech_sp = max(_mech_count, key=lambda k: _mech_count[k])
    first_kid_idx = next(
        (
            i
            for i, r in enumerate(rows)
            if mech_sp
            and str(r.get("speaker") or "").strip() == mech_sp
            and _N_MECHANISM_CHILD_RE.search(
                str(r.get("intent") or r.get("beat") or "")
            )
        ),
        -1,
    )
    if first_kid_idx < 0:
        first_kid_idx = next(
            (
                i
                for i, r in enumerate(rows)
                if str(r.get("speaker") or "").strip() in kids
            ),
            -1,
        )
    # 同伙加码不依赖机制是否展开：她可以紧跟对方报名字就跟着报一个。
    # 所以这里退回到「对方说过话之后即可」。
    first_kid_idx = next(
        (
            i
            for i, r in enumerate(rows)
            if str(r.get("speaker") or "").strip() in kids
        ),
        first_kid_idx,
    )

    def _safe_positions() -> list[int]:
        positions: list[int] = []
        for i in range(1, len(rows)):
            if first_kid_idx >= 0 and i <= first_kid_idx:
                continue
            prev_sp = str(rows[i - 1].get("speaker") or "").strip()
            # 不在家长问句之后（问答必须相邻）
            if prev_sp in _PARENT_SPEAKER_SET and _RE_ASK_INTENT.search(
                str(rows[i - 1].get("intent") or "")
            ):
                continue
            if i >= close_idx:
                continue
            positions.append(i)
        return positions

    moved = 0
    for _ in range(6):
        acted = False
        for i in range(len(rows) - 1):
            a = str(rows[i].get("speaker") or "").strip()
            b = str(rows[i + 1].get("speaker") or "").strip()
            if a not in kids or b not in kids or a != b:
                continue
            for pos in _safe_positions():
                if pos in (i, i + 1):
                    continue
                prev_sp = str(rows[pos - 1].get("speaker") or "").strip()
                next_sp = (
                    str(rows[pos].get("speaker") or "").strip()
                    if pos < len(rows)
                    else ""
                )
                if prev_sp == b or next_sp == b:
                    continue
                row = rows.pop(i + 1)
                rows.insert(pos, row)
                moved += 1
                acted = True
                break
            if acted:
                break
        if not acted:
            break
    if not moved:
        return contract, []
    for idx, row in enumerate(rows, 1):
        row["beat"] = idx
    out = dict(contract)
    out["beat_chain"] = rows
    return out, [f"孩子连说分配:{moved}处"]


_RE_KEY_ASK = re.compile(r"这词|什么意思|谁教|哪来|出处")


def collapse_extra_parent_asks(contract: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """家长只保留**一个**信息型追问；其余删掉。

    反复出现的硬伤「妈妈问 X，孩子没答 X」根因在契约：家长排了两个追问拍
    （问名字 + 问词义），但只有后者有对应的回答拍，前者永远没人答，
    孩子只能跳过去说别的，语义审读必然判答非所问（#87 实测多轮）。

    规则（抽象，不绑剧情）：
      - 家长的信息型追问拍最多留一个，优先保留含「这词/什么意思/谁教」的
        机制关键追问；
      - 被删的追问拍不影响机制链（立规、收束、孩子的拍都不动）。
    """
    if not isinstance(contract, dict):
        return contract, []
    chain = contract.get("beat_chain")
    if not isinstance(chain, list) or len(chain) < 4:
        return contract, []
    rows = [dict(r) for r in chain if isinstance(r, dict)]
    ask_idx = [
        i
        for i, r in enumerate(rows)
        if str(r.get("speaker") or "").strip() in _PARENT_SPEAKER_SET
        and _RE_ASK_INTENT.search(str(r.get("intent") or ""))
    ]
    if len(ask_idx) <= 1:
        return contract, []
    # 优先保留机制关键追问（含「这词/什么意思/谁教」）
    key = [
        i
        for i in ask_idx
        if _RE_KEY_ASK.search(str(rows[i].get("intent") or ""))
    ]
    keep = key[0] if key else ask_idx[-1]
    drop = [i for i in ask_idx if i != keep]
    if not drop:
        return contract, []
    for i in sorted(drop, reverse=True):
        rows.pop(i)
    for idx, row in enumerate(rows, 1):
        row["beat"] = idx
    out = dict(contract)
    out["beat_chain"] = rows
    # 额度跟着拍数走（家长拍变少，额度同步收窄，避免虚高额度被拿去加句）
    parent_n = sum(
        1
        for r in rows
        if str(r.get("speaker") or "").strip() in _PARENT_SPEAKER_SET
        and str(r.get("intent") or "").strip()
    )
    if parent_n:
        out["mom_lines_max"] = parent_n
    return out, [f"家长追问合并:{len(drop)}拍→共{parent_n}拍"]


_RE_MECHANISM_EXPLAIN = re.compile(r"讲圆|解释|自洽|因为|所以")


def keep_mechanism_chain_adjacent(contract: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """机制孩子的「说出词 → 解释」两拍必须紧邻，中间不许插旁观的拍。

    「因为街上有人工作呀」+「所以别人给你钱」被灿灿一句隔开，就成了
    两段互不相连的因果（终检判「中间缺了定义句」）。语序上这两句本来就
    该一口气说完。
    """
    if not isinstance(contract, dict):
        return contract, []
    chain = contract.get("beat_chain")
    if not isinstance(chain, list) or len(chain) < 4:
        return contract, []
    rows = [dict(r) for r in chain if isinstance(r, dict)]
    mech: dict[str, int] = {}
    for r in rows:
        sp = str(r.get("speaker") or "").strip()
        if sp and sp not in _PARENT_SPEAKER_SET and _N_MECHANISM_CHILD_RE.search(
            str(r.get("intent") or r.get("beat") or "")
        ):
            mech[sp] = mech.get(sp, 0) + 1
    mech_kid = max(mech, key=lambda k: mech[k]) if mech else ""
    if not mech_kid:
        return contract, []
    moved = 0
    for _ in range(4):
        acted = False
        for i in range(len(rows) - 2):
            if str(rows[i].get("speaker") or "").strip() != mech_kid:
                continue
            if not _RE_MECHANISM_EXPLAIN.search(str(rows[i].get("intent") or "")):
                continue
            mid_sp = str(rows[i + 1].get("speaker") or "").strip()
            nxt_sp = str(rows[i + 2].get("speaker") or "").strip()
            if mid_sp in _PARENT_SPEAKER_SET or mid_sp == mech_kid:
                continue
            if nxt_sp != mech_kid:
                continue
            # 把中间那条旁观拍挪到机制孩子第二句之后
            intruder = rows.pop(i + 1)
            rows.insert(i + 2, intruder)
            moved += 1
            acted = True
            break
        if not acted:
            break
    if not moved:
        return contract, []
    for idx, row in enumerate(rows, 1):
        row["beat"] = idx
    out = dict(contract)
    out["beat_chain"] = rows
    return out, [f"机制链相邻修复:{moved}处"]


# 机制关键拍的**成品台词**（{token} 会替换成契约声明的怪词）。
# 讲圆那句必须包含怪词本身，否则词槽在正文里没落地，下游会判「机制词槽缺失」。
def _n_token_of_intent(intent: str) -> str:
    """从 intent 里取出契约声明的怪词（「哇卡」这类）。"""
    m = re.search(r"「([^」]{1,8})」", str(intent or ""))
    return m.group(1) if m else ""


_N_MECH_LINE_BY_TAG: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"报出一串|编的名字|找个好人"),
        "我要找个好人来，叫小明、小红、小刚。",
    ),
    (
        re.compile(r"讲圆|解释|因为|所以"),
        "因为{token}就是好人给我钱，所以我得去找他们。",
    ),
    (re.compile(r"苹果"), "苹果。"),
    (
        re.compile(r"收束|认栽|服了"),
        "行吧，我认栽，以后说话得先打草稿。",
    ),
)


def pin_mechanism_kid_lines(contract: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """把机制孩子的**关键拍**也写成具体台词（不只是抽象 intent）。

    只钉旁观孩子不够：昭昭那句仍由模型自由发挥，写出来的句子不接任何人
    的话头，于是灿灿的（已钉住的）台词就全部对不上——终检连着判
    「接不上/答非所问」（#87 实测）。

    只钉三类关键拍（报名字 / 讲圆 / 补词），其余（如「先直接回答」这类
    需要结合上下文的）仍交给模型，避免过度僵化。
    """
    if not isinstance(contract, dict):
        return contract, []
    if str(contract.get("story_type") or "").strip().upper() != "N":
        return contract, []
    chain = contract.get("beat_chain")
    if not isinstance(chain, list) or not chain:
        return contract, []
    rows = [dict(r) for r in chain if isinstance(r, dict)]
    pinned = 0
    for row in rows:
        sp = str(row.get("speaker") or "").strip()
        if sp in _PARENT_SPEAKER_SET:
            continue
        intent = str(row.get("intent") or "")
        if not _N_MECHANISM_CHILD_RE.search(intent):
            continue
        token = _n_token_of_intent(intent)
        for pat, line_tpl in _N_MECH_LINE_BY_TAG:
            if pat.search(intent) and not intent.endswith(("。", "！", "？")):
                if "{token}" in line_tpl and not token:
                    continue
                line = line_tpl.format(token=token)
                row["intent"] = intent = f"{intent}｜台词：{line}"
                pinned += 1
                break
    if not pinned:
        return contract, []
    out = dict(contract)
    out["beat_chain"] = rows
    return out, [f"机制拍附具体台词:{pinned}处"]


# N 类双孩的**回合计划**：13 个回合，每回合一类内容，互不重复。
#
# 这是为解决「两人各说各的 + 内容重复 + 字数不够」三件事一起做的收敛：
#   - 每个搭档回合都紧跟在它能咬住的机制回合之后（比数量接报名字、
#     入伙接给钱、认下接补词、帮腔接嘴硬），咬合由位置保证；
#   - 每类只出现一次，不会换词重复；
#   - 每句按 18–22 字写足，13 句即可过 240 字。
# 机制内容（怪词、名字）仍来自 H3b seed，不写死剧情。
# role: mom=家长 mech=机制孩子 side=搭档孩子
# 每一拍都**承接上一拍**，并且**带来新信息**（这是同时满足
# 「不各说各的」「不换词重复」的唯一排法）。
# 相邻两拍的关系：认下→反驳→追问→回答→加码→顶回去……
# 每一拍都**承接上一拍**，并且**带来新信息**（这是同时满足
# 「不各说各的」「不换词重复」的唯一排法）。
# 相邻两拍的关系：认下→驳回→追问→回答→加码→顶回去……
# 三处专治过实测硬伤：
#   ① 第4拍必须回应第3拍的「好记」（否则判没接住话头）；
#   ② 第6拍只**命名**不定义，第8拍才**定义**（否则判同一定义说两遍）；
#   ③ 「苹果」由第10拍首次引入，第11拍不得说「又」（否则判缺前提）。
# 每一拍都**承接上一拍**，并且**带来新信息**（这是同时满足
# 「不各说各的」「不换词重复」的唯一排法）。
# 关键结构约束（都是实测踩出来的）：
#   ① 第4拍必须咬住第3拍的原话重点（不能自说自话）；
#   ② 怪词先**命名**、妈妈追问、再**定义**，不能同一定义说两遍；
#   ③ 「苹果」必须**有人问、它来答**：第9拍先问「你要我做什么」，
#      第10拍才淡定回「苹果。」——这样既是荒诞秒答，又接住话头；
#      后续两拍再围绕它抬杠。
# 每一拍都**承接上一拍**，并且**带来新信息**。
#
# 专家复核 (2026-10) 的关键意见：灿灿不能把昭昭的**对话对象**拉走。
# 机制主线是「孩子对妈妈一本正经胡说 → 妈妈破功」；一旦昭昭转去跟灿灿
# 争辩，妈妈就被边缘化、破功感消失。所以：
#   ① 灿灿只做「凑热闹/帮腔/被带偏」这类同伴式反应，不向昭昭提问、
#      不要求昭昭解释机制（她一问，昭昭就去答她了）；
#   ② 怪词必须由昭昭**主动**蹦出，不是被灿灿反问引出来的；
#   ③ 昭昭的关键解释一律面向妈妈（回答妈妈第7拍那个追问）。
# 另按专家意见去掉成人腔：「有个专门的叫法」「我说了算」「我认栽」。
# 每一拍都**承接上一拍**，并且**带来新信息**；孩子严格交替。
#
# 专家复核 (2026-10) 的关键意见：灿灿不能把昭昭的**对话对象**拉走。
# 机制主线是「孩子对妈妈一本正经胡说 → 妈妈破功」；一旦昭昭转去跟灿灿
# 争辩，妈妈就被边缘化、破功感消失。所以：
#   ① 灿灿只做「凑热闹/帮腔/被带偏」这类同伴式反应，**不向昭昭提问**、
#      不要求昭昭解释机制（她一问，昭昭就去答她了）；
#   ② 怪词必须由昭昭**主动**蹦出，不是被灿灿反问引出来的；
#   ③ 昭昭的关键解释一律面向妈妈（回答妈妈的关键追问那一拍）。
# 另按专家意见去掉成人腔：「有个专门的叫法」「我说了算」「我认栽」。
# 每一拍都**承接上一拍**，并且**带来新信息**；孩子严格交替。
#
# 专家复核 (2026-10) 的关键意见：灿灿不能把昭昭的**对话对象**拉走。
# 机制主线是「孩子对妈妈一本正经胡说 → 妈妈破功」；一旦昭昭转去跟灿灿
# 争辩，妈妈就被边缘化、破功感消失。所以：
#   ① 灿灿只做「凑热闹/帮腔/被带偏」这类同伴式反应，**不向昭昭提问**；
#   ② 怪词必须由昭昭主动蹦出，不是被灿灿反问引出来的；
#   ③ 昭昭的关键解释一律面向妈妈。
#
# 因果链必须自下而上建立，不能凭空出现设定（终检反复判「缺前提」）：
#   妈妈立规 → 昭昭报名 → 妈妈问「好人」是谁 → 昭昭给定义（给钱）
#   → 妈妈追问词 → 昭昭解释 → 补词 → 妈妈收束
_N_TWO_KID_PLAN: tuple[tuple[str, str, str], ...] = (
    ("mom", "立规", "我把你今天说的每一句话都记下来，看你会不会骗人。"),
    ("mech", "报名字", "我要找个好人来，叫小明、小红、小刚，都是好人。"),
    ("side", "凑热闹", "我也会报名字，我认识的比他说的还要多呢。"),
    ("mom", "追问定义", "你说的好人，到底得是什么样的人才算？"),
    ("mech", "给出定义", "好人就是会给我钱的那种，别人都不算。"),
    ("side", "跟上", "那我信他，反正好人给钱这事我也拦不住。"),
    ("mech", "主动抛怪词", "对了，这事我还会说，就一个字，哇卡。"),
    ("mom", "关键追问", "这词是什么意思，我怎么从没听过，是谁教你的？"),
    ("mech", "回答妈妈", "没人教我，哇卡就是好人给我钱，所以我才找他们。"),
    ("side", "被带偏", "那我明天也去街上站着，看看有没有人给我钱。"),
    ("mech", "再补一个", "苹果。"),
    ("side", "跟着要", "那我的那份呢，你可别忘了给我也留一个。"),
    ("mom", "收束", "行吧，我说不过你，以后问你话得先打个草稿。"),
)


def build_n_two_kid_dialogue(
    contract: dict[str, Any],
    *,
    existing: list[Any] | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """按回合计划生成 N 类双孩对白；已有的好句子优先复用。

    复用规则：报名字、补词、家长三句若库里已有合格文本就沿用（保住素材
    真实感），其余回合用计划台词。怪词从契约取，保证与词槽一致。
    """
    if not isinstance(contract, dict):
        return [], []
    chain = [r for r in (contract.get("beat_chain") or []) if isinstance(r, dict)]
    kids = kid_speakers_of(
        [*(str(r.get("speaker") or "") for r in chain),
         *(contract.get("characters") or [])]
    )
    if len(kids) < 2:
        return [], []
    token = ""
    for row in chain:
        tok = _n_token_of_intent(str(row.get("intent") or ""))
        if tok:
            token = tok
            break
    if not token:
        return [], []
    # 机制孩子 = 词槽持有者
    mech_kid = ""
    for row in chain:
        if _n_token_of_intent(str(row.get("intent") or "")):
            mech_kid = str(row.get("speaker") or "").strip()
            break
    if mech_kid not in kids:
        return [], []
    side_kid = next(k for k in kids if k != mech_kid)

    old = [r for r in (existing or []) if isinstance(r, dict)]
    old_lines = [str(r.get("line") or "").strip() for r in old]

    def _reuse(predicate, *, min_len: int = 18) -> str:
        for line in old_lines:
            if line and len(line) >= min_len and predicate(line):
                return line
        return ""

    names_line = _reuse(lambda x: ("叫" in x or "名字" in x), min_len=20)
    addon_line = _reuse(
        lambda x: 0 < len(re.sub(r"[^\u4e00-\u9fffA-Za-z]", "", x)) <= 4
    )
    mom_opening = _reuse(lambda x: "记" in x)
    mom_ask = _reuse(lambda x: re.search(r"什么意思|谁教|什么词", x) is not None)
    mom_close = _reuse(lambda x: re.search(r"认栽|服了|打草稿|草稿", x) is not None)

    out: list[dict[str, Any]] = []
    for role, tag, template in _N_TWO_KID_PLAN:
        line = template.replace("{token}", token)
        if role == "mech" and tag == "报名字" and names_line:
            line = names_line
        elif role == "mech" and tag == "补词" and addon_line:
            line = addon_line
        elif role == "mom" and tag == "立规" and mom_opening:
            line = mom_opening
        elif role == "mom" and tag == "追问" and mom_ask:
            line = mom_ask
        elif role == "mom" and tag == "收束" and mom_close:
            line = mom_close
        speaker = "妈妈" if role == "mom" else (mech_kid if role == "mech" else side_kid)
        out.append({"speaker": speaker, "line": line})
    return out, ["按回合计划重建双孩对白:13回合"]


def normalize_payload_tokens(payload: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """把**契约与 seed 一起**做词槽归一化（唯一入口）。

    踩过的坑：只归一化 scene_contract 而漏掉 dialogue_seed，结果契约写「哇卡」、
    seed 还写「waka」，模型两边都看到，成稿中途改口 → 判「缺前提/接不上」
    （#87 实测）。词槽是同一件事，必须在同一处一起改。
    """
    if not isinstance(payload, dict):
        return payload, []
    out = dict(payload)
    notes: list[str] = []
    contract = out.get("scene_contract")
    if isinstance(contract, dict):
        new_contract, c_notes = neutralize_mechanism_token(contract)
        if c_notes:
            out["scene_contract"] = new_contract
            notes.extend(c_notes)
        out["scene_contract"], r_notes = refresh_second_kid_intents(
            out["scene_contract"]
        )
        if r_notes:
            notes.extend(r_notes)
    seed = out.get("dialogue_seed")
    if isinstance(seed, list) and seed:
        new_seed, s_notes = neutralize_seed_tokens(seed)
        if s_notes:
            out["dialogue_seed"] = new_seed
            notes.extend(s_notes)
        _seed_p, p_notes = fix_second_person_drift(
            out.get("dialogue_seed") or []
        )
        if p_notes:
            out["dialogue_seed"] = _seed_p
            notes.extend(p_notes)
        new_seed, f_notes = clean_seed_fragments(out.get("dialogue_seed") or [])
        if f_notes:
            out["dialogue_seed"] = new_seed
            notes.extend(f_notes)
        new_seed, m_notes = merge_seed_consecutive_kid_rows(
            out.get("dialogue_seed") or []
        )
        if m_notes:
            out["dialogue_seed"] = new_seed
            notes.extend(m_notes)
        # 问答必须相邻：家长问句后面不许插旁观的拍
        out["scene_contract"], k_notes = keep_qa_adjacent(
            out.get("scene_contract") or {}
        )
        if k_notes:
            notes.extend(k_notes)
        # 机制关键拍附带具体台词（否则模型自由发挥，别人的台词全对不上）
        out["scene_contract"], _pin1 = pin_mechanism_kid_lines(
            out.get("scene_contract") or {}
        )
        if _pin1:
            notes.extend(_pin1)
        # 家长只留一个信息型追问（多余的永远没人答）
        out["scene_contract"], c_notes = collapse_extra_parent_asks(
            out.get("scene_contract") or {}
        )
        if c_notes:
            notes.extend(c_notes)
        # 机制链（说词→解释）必须紧邻
        out["scene_contract"], mc_notes = keep_mechanism_chain_adjacent(
            out.get("scene_contract") or {}
        )
        if mc_notes:
            notes.extend(mc_notes)
        # 契约层收敛：孩子相邻与问答相邻互相影响，交替跑到不动为止
        for _ in range(3):
            out["scene_contract"], sp_notes = spread_kid_beats(
                out.get("scene_contract") or {}
            )
            out["scene_contract"], k2_notes = keep_qa_adjacent(
                out.get("scene_contract") or {}
            )
            if sp_notes:
                notes.extend(sp_notes)
            if k2_notes:
                notes.extend(k2_notes)
            if not sp_notes and not k2_notes:
                break
        # 家长问句之后的拍：机制孩子必须先直接回答
        out["scene_contract"], q_notes = prefix_answer_after_parent_ask(
            out.get("scene_contract") or {}
        )
        if q_notes:
            notes.extend(q_notes)
    # ── 最终对齐：契约已收敛，seed 必须与之一致 ────────────────────────
    # 必须放在契约收敛之后，否则孤儿问句/缺说话人按旧契约判定，等于没修。
    _seed_final, _align_notes = align_seed_to_contract_beats(
        out.get("dialogue_seed") or [],
        contract=out.get("scene_contract"),
    )
    if _align_notes:
        out["dialogue_seed"] = _seed_final
        notes.extend(_align_notes)
    # 旁观主角的 seed 行按契约拍序刷新意图（契约已改成同伙加码，
    # seed 若还留着旧的「不信/拆台」写法，模型会照旧写成旁观者）
    _seed_rows = [dict(r) for r in (out.get("dialogue_seed") or []) if isinstance(r, dict)]
    _beats = [
        r for r in (out.get("scene_contract") or {}).get("beat_chain") or []
        if isinstance(r, dict)
    ]
    if _seed_rows and _beats:
        _mech: dict[str, int] = {}
        for r in _beats:
            sp_r = str(r.get("speaker") or "").strip()
            if sp_r and sp_r not in _PARENT_SPEAKER_SET and _N_MECHANISM_CHILD_RE.search(
                str(r.get("intent") or "")
            ):
                _mech[sp_r] = _mech.get(sp_r, 0) + 1
        # 词槽持有者才是机制主体（他负责那个怪词）
        _slot_owner = ""
        for r in _beats:
            if _N_DECLARED_TOKEN_SEARCH.search(str(r.get("intent") or "")):
                _slot_owner = str(r.get("speaker") or "").strip()
                break
        _main = _slot_owner or (max(_mech, key=lambda k: _mech[k]) if _mech else "")
        _partner = next(
            (
                k
                for k in ("昭昭", "灿灿")
                if k != _main
            ),
            "",
        )
        if _partner:
            _partner_beats = [
                str(r.get("intent") or "")
                for r in _beats
                if str(r.get("speaker") or "").strip() == _partner
            ]
            _pi = 0
            _changed_seed = 0
            for _r in _seed_rows:
                if str(_r.get("speaker") or "").strip() != _partner:
                    continue
                if _pi >= len(_partner_beats):
                    break
                if str(_r.get("intent") or "") != _partner_beats[_pi]:
                    _r["intent"] = _partner_beats[_pi]
                    _changed_seed += 1
                _pi += 1
            if _changed_seed:
                out["dialogue_seed"] = _seed_rows
                notes.append(f"刷新第二孩seed意图:{_changed_seed}条")
    # 词与解释必须相邻（中间被隔开会写成互不相连的两段因果）
    _seed_pair, _p2 = keep_seed_token_pair_adjacent(
        out.get("dialogue_seed") or []
    )
    if _p2:
        out["dialogue_seed"] = _seed_pair
        notes.extend(_p2)
    # 合并可能因对齐重新出现的相邻同行
    _seed_merged, _m2 = merge_seed_consecutive_kid_rows(
        out.get("dialogue_seed") or []
    )
    if _m2:
        out["dialogue_seed"] = _seed_merged
    return out, notes


def neutralize_seed_tokens(seed: list[Any]) -> tuple[list[Any], list[str]]:
    """seed 里的机制怪词同样换成中性词（与契约保持同一个词）。"""
    rows: list[Any] = []
    replaced: list[str] = []
    for item in seed or []:
        if not isinstance(item, dict):
            rows.append(item)
            continue
        row = dict(item)
        for key in ("intent", "line"):
            text = row.get(key)
            if not isinstance(text, str) or not text:
                continue
            new_text = text
            for old, new in _GOLD_CHAT_NEUTRAL_TOKEN_MAP.items():
                pat = re.compile(
                    r"(?<![A-Za-z])" + re.escape(old) + r"(?![A-Za-z])", re.I
                )
                if pat.search(new_text):
                    new_text = pat.sub(new, new_text)
                    replaced.append(f"{old}→{new}")
            row[key] = new_text
        rows.append(row)
    return rows, (["seed怪词中性化:" + "、".join(dict.fromkeys(replaced))] if replaced else [])


def enforce_two_kid_cast(contract: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """出厂设定落地：契约的角色表与 beat 里必须有两个孩子。

    这是「永远不允许只有一个孩子出场」的**唯一执行点**。放在契约归一化的
    最后一环，下游（扩写/补丁/机检）就再也不会遇到单孩契约，各处那些
    `if len(kids) == 1` 的临时分支也随之失去意义。

    做法是「补」不是「删」：若某个孩子完全没有拍，就给他补一条反应拍，
    让他有真实戏份；同时把他写进 characters。
    """
    if not isinstance(contract, dict):
        return contract, []
    sc = dict(contract)
    chain = sc.get("beat_chain")
    if not isinstance(chain, list) or not chain:
        return contract, []
    rows = [dict(r) for r in chain if isinstance(r, dict)]
    names = [str(r.get("speaker") or "").strip() for r in rows]
    names += [str(c).strip() for c in (sc.get("characters") or [])]
    kids = kid_speakers_of(names)
    if len(kids) >= 2:
        return contract, []
    partner = next(k for k in _DEFAULT_KID_ORDER if k not in kids) if kids else "灿灿"
    solo = kids[0] if kids else ""
    notes: list[str] = []
    react_i = 0
    inserted = 0
    out_rows: list[Any] = []
    prev_kid = ""
    for row in rows:
        sp = str(row.get("speaker") or "").strip()
        # 只能在**第一个孩子拍之后**插入搭档拍：插在开场之前会把
        # 「报名字」这类前置拍推到后面，开场因果立刻判缺拍（#87 实测）。
        seen_kid = any(
            str(r.get("speaker") or "").strip() == solo for r in out_rows
        )
        if solo and seen_kid and sp == solo and sp == prev_kid:
            out_rows.append(
                {
                    "speaker": partner,
                    "intent": _N_SECOND_KID_LINES[
                        react_i % len(_N_SECOND_KID_LINES)
                    ],
                }
            )
            react_i += 1
            inserted += 1
            prev_kid = partner
        out_rows.append(row)
        prev_kid = sp if sp not in _PARENT_SPEAKER_SET else ""
    if not inserted:
        # 孩子没有连续拍，也要给他一条反应拍（保证他真的出场）
        target = next(
            (
                i
                for i, r in enumerate(out_rows)
                if isinstance(r, dict)
                and str(r.get("speaker") or "").strip() == solo
            ),
            -1,
        )
        if target < 0:
            return contract, []
        out_rows.insert(
            target + 1,
            {"speaker": partner, "intent": _N_SECOND_KID_LINES[0]},
        )
        inserted = 1
    # ── 按句数反推她需要几拍 ────────────────────────────────────────────
    # 正文 ≥240 字、妈妈额度封顶后，剩下 9–11 句全归孩子；两孩严格交替时
    # 每个孩子要承担约 5 句。若契约只给她 1 拍，扩写只能靠编空话凑，
    # 结果就是「你接着说」反复出现、被判原地打转（#87 实测）。
    # 所以这里把她缺的拍补够：目标 = 与她需承担的句数相当。
    try:
        mom_cap = max(0, int(sc.get("mom_lines_max") or 0))
    except (TypeError, ValueError):
        mom_cap = 0
    kid_lines_needed = max(0, CHAT_LINE_COUNT_MIN - mom_cap)
    per_kid_lines = -(-kid_lines_needed // 2)
    # 每拍可以扩成 2 句，所以「拍数」≈ 句数的一半。契约拍数是骨架，
    # 不是最终句数——按句数直接给拍会让她的拍塞不进交替位置。
    per_kid = -(-per_kid_lines // 2)
    # 交替位置最多等于另一个孩子的拍数 + 1（她可以在末尾多接一拍），
    # 但至少要与她对称：契约拍数不等时，扩写必然把差额压给同一个人 → 连说。
    solo_beats = sum(
        1
        for r in out_rows
        if isinstance(r, dict) and str(r.get("speaker") or "").strip() == solo
    )
    per_kid = max(1, min(per_kid, solo_beats))
    partner_beats = sum(
        1
        for r in out_rows
        if isinstance(r, dict) and str(r.get("speaker") or "").strip() == partner
    )
    pool_i = partner_beats
    # 交错分布：每次插在**下一个该孩子拍之后**，避免她的拍全堆在末尾
    # （堆在末尾会让她自己连说，等于把连说问题换个孩子重演）。
    # 目标：与她对称（= solo_beats）。契约两侧拍数不等，扩写就会把差额
    # 全压给同一个孩子，形成连说（#87 实测）。
    per_kid = max(per_kid, solo_beats)
    while partner_beats < per_kid and pool_i < len(_N_SECOND_KID_LINES):
        if len(out_rows) >= CHAT_LINE_COUNT_MAX:
            break
        # 找到「上一个孩子拍」的位置，插在它前面（即紧邻前一个孩子拍之前）
        kid_positions = [
            i
            for i, r in enumerate(out_rows)
            if isinstance(r, dict)
            and str(r.get("speaker") or "").strip() in {solo, partner}
        ]
        if not kid_positions:
            break
        def _safe_insert(at: int) -> bool:
            """插入后必须不产生孩子连说，否则换位置。"""
            prev_sp = (
                str(out_rows[at - 1].get("speaker") or "").strip() if at > 0 else ""
            )
            next_sp = (
                str(out_rows[at].get("speaker") or "").strip()
                if at < len(out_rows)
                else ""
            )
            return prev_sp != partner and next_sp != partner

        # 收束拍（最后一个家长拍）之后不得插入：收束必须在最后
        close_idx = max(
            (
                i
                for i, r in enumerate(out_rows)
                if isinstance(r, dict)
                and str(r.get("speaker") or "").strip() in _PARENT_SPEAKER_SET
            ),
            default=len(out_rows) - 1,
        )
        placed = False
        candidates = list(range(close_idx, 0, -1))
        for at in candidates:
            if not _safe_insert(at):
                continue
            # 只能插在两个「已存在的孩子拍」之间或孩子拍之后，不能破坏开场
            if at == 0:
                continue
            out_rows.insert(
                at,
                {"speaker": partner, "intent": _N_SECOND_KID_LINES[pool_i]},
            )
            partner_beats += 1
            pool_i += 1
            inserted += 1
            placed = True
            break
        if not placed:
            break
    for idx, row in enumerate(out_rows, 1):
        if isinstance(row, dict):
            row["beat"] = idx
    # ── 把搭档的拍统一刷新成本池的最新意图 ──────────────────────────────
    # 契约复用会保留库里旧意图，于是「追问时间/地点」这类旧写法一直活着，
    # 机检又拦它 → 每轮都判关键追问归属（#87 实测）。
    # 搭档的拍本来就是我方补的，每次刷新是安全的，且保证幂等。
    partner_rows = [
        r for r in out_rows
        if isinstance(r, dict) and str(r.get("speaker") or "").strip() == partner
    ]
    for idx, row in enumerate(partner_rows):
        row["intent"] = _N_SECOND_KID_LINES[idx % len(_N_SECOND_KID_LINES)]

    sc["beat_chain"] = out_rows
    sc["characters"] = ensure_two_kid_cast(
        [*(sc.get("characters") or []), solo, partner]
    )
    notes.append(f"保证两孩出场:补{partner}({inserted}拍)")
    return sc, notes


def ensure_n_two_kid_alternation(
    contract: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    """N 类：两个孩子的台词交错，禁止同一个孩子连说。

    两条硬约束相互作用会逼出连说：
    「正文 ≥240 字 + 家长额度只有 3 句」→ 剩下 9 句全归孩子；
    若只有 1 个孩子，必然出现连续 3 句以上。用户裁决：**禁止连说**，
    孩子戏份靠**两个孩子交替**解决。所以这里不做删除，而是：
    在机制孩子出现「连续两拍」的位置，插入另一个孩子的一拍反应，
    把连说拆开。反应拍抽象、不代问关键追问、不抢机制。
    """
    if not isinstance(contract, dict):
        return contract, []
    if str(contract.get("story_type") or "").strip().upper() != "N":
        return contract, []
    chain = contract.get("beat_chain")
    if not isinstance(chain, list) or not chain:
        return contract, []
    rows = [dict(r) for r in chain if isinstance(r, dict)]
    if not rows:
        return contract, []
    # 孩子来源有两处：beat_chain 里已说话的，以及 characters 里登记但还没给的拍。
    # 后者正是「角色表有、beat 没有」的幽灵角色——旧做法是删掉她（于是只剩
    # 两人手、孩子必然连说），现在改成给她反应拍，用她来拆连说。
    kids = list(
        dict.fromkeys(
            [
                str(r.get("speaker") or "").strip()
                for r in rows
                if str(r.get("speaker") or "").strip()
                and str(r.get("speaker") or "").strip() not in _PARENT_SPEAKER_SET
            ]
            + [
                str(c).strip()
                for c in (contract.get("characters") or [])
                if str(c).strip()
                and str(c).strip() not in _PARENT_SPEAKER_SET
            ]
        )
    )
    if len(kids) < 2:
        # 只有一个孩子：禁止连说就无从满足（家长额度封顶后剩下的句子只能
        # 由他连说）。按用户裁决，这里主动**补一个同侧孩子**，用他承担
        # 交替位的反应拍——不是删孩子、也不是豁免连说。
        solo = kids[0] if kids else ""
        partner = "灿灿" if solo == "昭昭" else "昭昭"
        if not solo:
            return contract, []
        rows_with_partner: list[Any] = []
        prev_kid = ""
        react_i = 0
        inserted = 0
        for row in rows:
            sp = str(row.get("speaker") or "").strip()
            if sp == solo and sp == prev_kid:
                rows_with_partner.append(
                    {
                        "speaker": partner,
                        "intent": _N_SECOND_KID_LINES[
                            react_i % len(_N_SECOND_KID_LINES)
                        ],
                    }
                )
                react_i += 1
                inserted += 1
                prev_kid = partner
            rows_with_partner.append(row)
            prev_kid = sp if sp not in _PARENT_SPEAKER_SET else ""
        if not inserted:
            return contract, []
        for idx, row in enumerate(rows_with_partner, 1):
            if isinstance(row, dict):
                row["beat"] = idx
        out_solo = dict(contract)
        out_solo["beat_chain"] = rows_with_partner
        chars_solo = [
            str(c).strip()
            for c in (contract.get("characters") or [])
            if str(c).strip()
        ]
        if partner not in chars_solo:
            chars_solo.append(partner)
        out_solo["characters"] = chars_solo
        return out_solo, [f"N单孩补第二个孩子:{partner}(插{inserted}拍反应)"]
    # 机制主体 = 承担机制推进拍的孩子
    mech: dict[str, int] = {}
    for r in rows:
        sp = str(r.get("speaker") or "").strip()
        if sp in kids and _N_MECHANISM_CHILD_RE.search(
            str(r.get("intent") or r.get("beat") or "")
        ):
            mech[sp] = mech.get(sp, 0) + 1
    main_kid = max(mech, key=lambda k: mech[k]) if mech else kids[0]
    other_kid = next((k for k in kids if k != main_kid), "")

    out_rows: list[Any] = []
    prev_kid = ""
    react_i = 0
    inserted = 0
    for row in rows:
        sp = str(row.get("speaker") or "").strip()
        seen_main = any(
            str(r.get("speaker") or "").strip() == main_kid for r in out_rows
        )
        if seen_main and sp in kids and sp == prev_kid and sp == main_kid and other_kid:
            out_rows.append(
                {
                    "speaker": other_kid,
                    "intent": _N_SECOND_KID_LINES[
                        react_i % len(_N_SECOND_KID_LINES)
                    ],
                }
            )
            react_i += 1
            inserted += 1
            prev_kid = other_kid
        out_rows.append(row)
        prev_kid = sp if sp in kids else ""
    if not inserted:
        return contract, []
    # 全量重编号：插入的拍没有原 beat 号，必须补上，否则契约拍号断档
    for idx, row in enumerate(out_rows, 1):
        if isinstance(row, dict):
            row["beat"] = idx
    out = dict(contract)
    out["beat_chain"] = out_rows
    chars = [
        str(c).strip() for c in (contract.get("characters") or []) if str(c).strip()
    ]
    if other_kid and other_kid not in chars:
        chars.append(other_kid)
    if chars:
        out["characters"] = chars
    return out, [f"N孩子交替:插入{inserted}拍{other_kid}反应"]



_RE_QUOTED_WORD = re.compile(r"[「『“\"]([A-Za-z][A-Za-z0-9'\-_]{1,15}|[\u4e00-\u9fff]{2,4})[」』”\"]")
_RE_BARE_ASCII_WORD = re.compile(r"[A-Za-z][A-Za-z0-9'\-_]{1,15}")


class _TokenFinder:
    """在 intent 文本里定位「契约声明的字面词」。

    优先「」包裹的词（ASCII 或 2–4 字中文自造词），其次裸 ASCII 词。
    中文自造词是合规替换后的常规形态——不该往中文童言里塞英文串。
    """

    @staticmethod
    def find(text: str) -> str:
        raw = str(text or "")
        quoted = _RE_QUOTED_WORD.search(raw)
        if quoted:
            return quoted.group(1)
        # 没加引号时，只认「替换表里的中性词」——中文裸词太多，
        # 不能随便把叙述里的普通词当词槽。
        for neutral in set(_GOLD_CHAT_NEUTRAL_TOKEN_MAP.values()):
            if neutral and neutral in raw:
                return neutral
        bare = _RE_BARE_ASCII_WORD.search(raw)
        return bare.group(0) if bare else ""

    @staticmethod
    def findall(text: str) -> list[str]:
        tok = _TokenFinder.find(text)
        return [tok] if tok else []

# 合规替换：源素材里的成人词必须换成「无本义音节词」。有实物含义的词
# （水果/动物/品牌）会和剧情里的物件打架——观众一听就出戏，终检也判
# 「语义混乱」（#87 实测：banana 被解释成「站街上干活」，又与「买苹果」冲突）。
# 这里给一个**可复用**的替换表：只换词，不动因果链。
_GOLD_CHAT_NEUTRAL_TOKEN_MAP: dict[str, str] = {
    "banana": "哇卡",
    "job": "哇卡",
    "work": "哇卡",
    "waka": "哇卡",
}


def neutralize_mechanism_token(contract: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """把契约里的怪词替换成无本义音节词（幂等，只换词不改剧情）。"""
    sc = contract if isinstance(contract, dict) else {}
    if not sc:
        return contract, []
    import json as _json

    raw = _json.dumps(sc, ensure_ascii=False)
    replaced: list[str] = []
    out_text = raw
    for old, new in _GOLD_CHAT_NEUTRAL_TOKEN_MAP.items():
        pat = re.compile(r"(?<![A-Za-z])" + re.escape(old) + r"(?![A-Za-z])", re.I)
        if pat.search(out_text):
            out_text = pat.sub(new, out_text)
            replaced.append(f"{old}→{new}")
    if not replaced:
        return contract, []
    try:
        out = _json.loads(out_text)
    except Exception:
        return contract, []
    return (out if isinstance(out, dict) else contract), ["怪词中性化:" + "、".join(replaced)]


_N_TOKEN_SPLIT_PREFIXES = ("只说出这个词（不解释）：", "解释这个词是什么意思：")


# 契约里的「出处问」：立规方问这句话是从哪来的
_N_ORIGIN_ASK_RE = re.compile(r"谁教|哪儿来|哪里来|哪学|跟谁学|谁告诉|从哪")
# seed 里已有出处答案的迹象（否认外部来源也算答案）
_N_ORIGIN_ANSWER_RE = re.compile(
    r"没人教|自己想的|自己编|自己想的|我编的|瞎编|做梦|电视上|书上|同学说|老师"
)


def ensure_origin_ask_answerable(
    seed: list[Any] | None,
    *,
    contract: dict[str, Any] | None = None,
) -> tuple[list[Any], list[str]]:
    """契约问了出处，seed 就必须有一条不靠编人的答案。

    N 的机制链固定含「立规方追问出处（谁教的）」。源素材里孩子对这句
    往往没有回答，于是生成端只有两条路：编一个具体的人当老师（终检判
    「引用无据」），或者干脆不答（终检判「接不上」）——两条都是违规，
    这个问在契约层就是无解的（#87 实测：19 轮里 2 次引用无据、2 次接不上）。

    补一条**否认外部来源**的答案即可解套：不引入任何新实体，且本身就是
    童言无忌的常见形态（「没人教，我自己想的」）。只在该问确实存在、
    而 seed 确实没答案时才补，已有答案不覆盖。
    """
    sc = contract if isinstance(contract, dict) else {}
    if str(sc.get("story_type") or "").strip().upper() != "N":
        return seed or [], []
    rows = [dict(x) if isinstance(x, dict) else x for x in (seed or [])]
    if not rows:
        return rows, []
    chain = [
        r for r in (sc.get("beat_chain") or []) if isinstance(r, dict)
    ]
    # 契约里谁在问出处
    asker = ""
    for r in chain:
        sp = str(r.get("speaker") or "").strip()
        intent = str(r.get("intent") or r.get("beat") or "")
        if sp and _PARENT_SPEAKER_SET and sp in _PARENT_SPEAKER_SET:
            if _N_ORIGIN_ASK_RE.search(intent):
                asker = sp
                break
    if not asker:
        return rows, []
    # 机制主体（说怪词的孩子）
    kid = ""
    for r in chain:
        sp = str(r.get("speaker") or "").strip()
        if sp and sp not in _PARENT_SPEAKER_SET:
            kid = sp
            break
    if not kid:
        return rows, []
    # seed 里已经有出处答案 → 不动
    for row in rows:
        if isinstance(row, dict) and _N_ORIGIN_ANSWER_RE.search(
            str(row.get("intent") or row.get("line") or "")
        ):
            return rows, []
    # 找 seed 里该家长问出处的那一行，答案紧跟其后
    insert_at = -1
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        if str(row.get("speaker") or "").strip() != asker:
            continue
        if _N_ORIGIN_ASK_RE.search(str(row.get("intent") or row.get("line") or "")):
            insert_at = i + 1
    if insert_at < 0:
        # seed 没写这一问 → 不新增问题（那是契约/生成的事），直接返回
        return rows, []
    rows.insert(
        insert_at,
        {"speaker": kid, "intent": "否认有人教：没人教，自己想的"},
    )
    return rows, ["补出处答案:否认外部来源"]


def split_n_token_from_explanation(
    seed: list[Any] | None,
    *,
    contract: dict[str, Any] | None = None,
) -> tuple[list[Any], list[str]]:
    """N 类：把「怪词 + 解释」同塞一句的 seed 拆成两条。

    N 的机制是「孩子先蹦出怪词 → 立规方追问 → 孩子再解释」。seed 把两件事
    写进同一句（「banana！就是你在街上工作别人给钱」）时，模型会把怪词当
    谓语塞进因果句（「好人会banana」「她天天在那儿banana」），机制塌成语法
    错误（#87 实测，专家也点出这一条）。

    拆成「只说出这个词」+「解释这个词的意思」两条，模型自然分开写。
    只拆不去：解释内容原样保留，不新造剧情。
    """
    sc = contract if isinstance(contract, dict) else {}
    if str(sc.get("story_type") or "").strip().upper() != "N":
        return seed or [], []
    rows = seed if isinstance(seed, list) else []
    if not rows:
        return rows, []
    out: list[Any] = []
    notes: list[str] = []
    emitted_tokens: set[str] = set()
    for item in rows:
        if not isinstance(item, dict):
            out.append(item)
            continue
        intent = str(item.get("intent") or item.get("line") or "").strip()
        speaker = str(item.get("speaker") or "").strip()
        # 幂等：本函数产出的意图会被写回 seed，重跑时必须原样放行，
        # 否则模板文本会被再次当作「前缀」处理，越跑越脏（#87 实测）。
        if intent.startswith(_N_TOKEN_SPLIT_PREFIXES):
            tokens_seen = _TokenFinder.findall(intent)
            if tokens_seen:
                key = tokens_seen[0].lower()
                if key in emitted_tokens:
                    # 同一怪词的重复出词行：丢弃（保留解释行）
                    notes.append(f"丢弃重复出词行:{key}")
                    continue
                emitted_tokens.add(key)
            out.append(item)
            continue
        # 只拆孩子的「说词 + 解释」；家长的追问句照原样留着
        if speaker in {"妈妈", "爸爸"}:
            out.append(item)
            continue
        # 追问/设问句不是解释，不能拆
        if re.search(r"什么|啥|谁教|哪来|怎么|问", intent):
            out.append(item)
            continue
        tokens = _TokenFinder.findall(intent)
        if not tokens:
            out.append(item)
            continue
        token = tokens[0]
        # 怪词后面还有中文解释内容 → 拆
        idx = intent.find(token)
        tail = intent[idx + len(token):].lstrip("」』”\"！!，,。：: 　")
        # 怪词出现在句中被当前缀/谓语/名字用（「因为好人叫banana」「好人会banana」）
        # 时，前缀本身就是病句，一律丢掉：只留「说出这个词」这一句。
        if token.lower() in emitted_tokens:
            # 同一怪词只保留一次「独立出词」（另一处已拆出），重复会让
            # seed 出现同义重复行，模型照抄即触发换词重复
            if len(tail) >= 4:
                only = dict(item)
                only["intent"] = f"解释这个词是什么意思：{tail}"
                out.append(only)
            continue
        emitted_tokens.add(token.lower())
        first = dict(item)
        first["intent"] = f"只说出这个词（不解释）：{token}"
        if len(tail) >= 4:
            second = dict(item)
            second["intent"] = f"解释这个词是什么意思：{tail}"
            out.extend([first, second])
            notes.append(f"拆分怪词与解释:{token}")
            continue
        if idx > 0:
            notes.append(f"剔除怪词前缀:{intent[:idx][:12]}")
        out.append(first)
    return out, notes


def trim_n_decorative_kid_seed(
    seed: list[Any] | None,
    *, 
    contract: dict[str, Any] | None = None,
) -> tuple[list[Any], list[str]]:
    """保留第二个孩子的 seed 行（现在她是**交替位置**的承担者）。

    旧设计把她当「装饰旁观」删掉，改成两人手；但两人手 + 家长额度封顶
    必然让孩子连说 3 句以上，而用户裁决是**禁止同人连说**。
    现在第二个孩子在契约里有真实反应拍，她的 seed 行要留着供扩写落地。

    唯一仍要处理的情形：她只剩一行且**带追问功能**（会抢立规方的关键追问），
    该行改派给契约追问方由 ``realign_seed_viewer_questions_to_asker`` 负责，
    这里不再删除。
    """
    return list(seed or []), []



def normalize_retrospective_topic_contract(
    contract: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    """回忆型 object 不应被 remap_note 强行物化成当前道具。"""
    if not isinstance(contract, dict):
        return contract, []
    if not is_retrospective_topic_object(str(contract.get("object") or "")):
        return contract, []
    note = str(contract.get("remap_note") or "").strip()
    if not note:
        return contract, []
    parts = [p.strip(" 。") for p in re.split(r"[；;]", note) if p.strip(" 。")]
    kept = [p for p in parts if not _RETROSPECTIVE_MATERIALIZE_NOTE_RE.search(p)]
    if kept == parts:
        return contract, []
    out = dict(contract)
    out["remap_note"] = "；".join(kept)
    return out, ["移除回忆话题物化 remap_note"]


_RETROSPECTIVE_PARENT_EXPOSITION_RE = re.compile(
    r"重提|讲|回忆|旧事|定论|定性|命大|补充|说.*(?:命|运气)"
)
_RETROSPECTIVE_N_SUPPORT_RE = re.compile(
    r"帮腔|附和|赞同|同意|讲得对|说得对|就是命大|确实命大|命真大"
)
_RETROSPECTIVE_N_REBUTTAL_RE = re.compile(
    r"反驳|嘴硬|不是.{0,8}命|会挑地方|自己会|主动"
)


def normalize_retrospective_n_opening_parent_beats(
    contract: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    """N 型回忆稿避免开场连续两拍家长讲解，合并成一个前提拍。"""
    if not isinstance(contract, dict):
        return contract, []
    if str(contract.get("story_type") or "").strip().upper() != "N":
        return contract, []
    if not is_retrospective_topic_object(str(contract.get("object") or "")):
        return contract, []
    chain = contract.get("beat_chain")
    # 至少 5 拍才合并，避免把合法 4 拍压到 scene_contract 最低拍数以下。
    if not isinstance(chain, list) or len(chain) < 5:
        return contract, []
    first, second = chain[0], chain[1]
    if not isinstance(first, dict) or not isinstance(second, dict):
        return contract, []
    speaker1 = str(first.get("speaker") or "").strip()
    speaker2 = str(second.get("speaker") or "").strip()
    if speaker1 not in {"妈妈", "爸爸"}:
        return contract, []
    intent1 = str(first.get("intent") or first.get("beat") or "").strip()
    intent2 = str(second.get("intent") or second.get("beat") or "").strip()

    third = chain[2] if len(chain) > 2 else None
    if (
        speaker2 != speaker1
        and _RETROSPECTIVE_N_SUPPORT_RE.search(intent2)
        and isinstance(third, dict)
        and _RETROSPECTIVE_N_REBUTTAL_RE.search(
            str(third.get("intent") or third.get("beat") or "")
        )
    ):
        new_chain = [first, *chain[2:]]
        normalized_support: list[Any] = []
        for idx, row in enumerate(new_chain, 1):
            if isinstance(row, dict):
                item = dict(row)
                if "beat" in item:
                    item["beat"] = idx
                normalized_support.append(item)
            else:
                normalized_support.append(row)
        out = dict(contract)
        out["beat_chain"] = normalized_support
        return out, [f"移除N回忆开场冗余附和拍:{speaker2}"]

    if speaker2 != speaker1:
        return contract, []
    if not _RETROSPECTIVE_PARENT_EXPOSITION_RE.search(intent2):
        return contract, []

    merged_first = dict(first)
    merged_first["intent"] = f"{intent1}；{intent2}".strip("；")
    new_chain: list[Any] = [merged_first, *chain[2:]]
    normalized_merged: list[Any] = []
    for idx, row in enumerate(new_chain, 1):
        if isinstance(row, dict):
            item = dict(row)
            if "beat" in item:
                item["beat"] = idx
            normalized_merged.append(item)
        else:
            normalized_merged.append(row)
    out = dict(contract)
    out["beat_chain"] = normalized_merged
    return out, [f"合并N回忆开场连续家长拍:{speaker1}"]


def _beat_min_turns(raw: Any) -> int:
    """单拍声明的 min_turns，非法值按 1 处理。"""
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return BEAT_MIN_TURNS_MIN
    return max(BEAT_MIN_TURNS_MIN, min(BEAT_MIN_TURNS_MAX, value))


def normalize_beat_min_turns(
    contract: dict[str, Any],
    *,
    min_total: int = DIALOGUE_TURNS_MIN,
) -> tuple[dict[str, Any], list[str]]:
    """给每拍补 ``min_turns``（可落地最小回合数），并保证 Σ ≥ 正文句数下限。

    契约拍数（4–6）天然少于正文最少句数（12）；若不让每拍声明最小回合数，
    模型只能靠空应答/换词重复凑句数。声明值缺省 1，总和不足 ``min_total`` 时
    按拍轮转抬到上限 ``BEAT_MIN_TURNS_MAX``，让每拍都拿到明确回合额度。
    """
    if not isinstance(contract, dict):
        return contract, []
    chain = contract.get("beat_chain")
    if not isinstance(chain, list) or not chain:
        return contract, []
    rows: list[Any] = []
    declared: list[int] = []
    for row in chain:
        if isinstance(row, dict):
            item = dict(row)
            turn = _beat_min_turns(item.get("min_turns"))
            item["min_turns"] = turn
            rows.append(item)
            declared.append(turn)
        else:
            rows.append(row)
            declared.append(BEAT_MIN_TURNS_MIN)
    notes: list[str] = []
    total = sum(declared)
    if total < min_total and any(v < BEAT_MIN_TURNS_MAX for v in declared):
        slot = 0
        while total < min_total:
            if declared[slot] < BEAT_MIN_TURNS_MAX:
                declared[slot] += 1
                total += 1
            slot = (slot + 1) % len(declared)
            if all(v >= BEAT_MIN_TURNS_MAX for v in declared):
                break
        for pos, row in enumerate(rows):
            if isinstance(row, dict):
                row["min_turns"] = declared[pos]
        notes.append(f"最小回合数抬额:{sum(declared)}")
    return {**contract, "beat_chain": rows}, notes


def normalize_dialogue_setting_for_contract(
    setting: str,
    contract: dict[str, Any] | None,
) -> tuple[str, bool]:
    """回忆/旧事类 object 只作为当前谈话主题，不把历史物件搬进 setting。"""
    sc = contract if isinstance(contract, dict) else {}
    if not is_retrospective_topic_object(str(sc.get("object") or "")):
        return str(setting or "").strip(), False
    location = str(sc.get("location") or "").strip()
    neutral = f"{location}，一家人聊起以前的事" if location else "一家人聊起以前的事"
    current = str(setting or "").strip()
    return neutral, neutral != current


_DIALOGUE_META_LABEL_RE = re.compile(
    r"一锤定音|镇住话题|嘴硬收场|旁观感叹|一招制敌|语塞收场|愣住收束"
)
_DIALOGUE_META_LABEL_SUFFIX_RE = re.compile(
    r"(?:[，,；;。！？!?]?\s*)"
    r"(?:一锤定音|镇住话题|嘴硬收场|旁观感叹|一招制敌|语塞收场|愣住收束)"
    r"[。！？!?]*$"
)
_DIALOGUE_META_LABEL_STRIP_RE = re.compile(
    r"[，,；;]?\s*"
    r"(?:一锤定音|镇住话题|嘴硬收场|旁观感叹|一招制敌|语塞收场|愣住收束)"
    r"[。！？!?]*"
)


def has_dialogue_meta_label(line: str) -> bool:
    """结构/审稿标签不得由角色念出口。"""
    return bool(_DIALOGUE_META_LABEL_RE.search(str(line or "")))


def _strip_dialogue_meta_label(match: re.Match[str]) -> str:
    return "，" if match.start() > 0 else ""


def sanitize_dialogue_meta_label_suffix(line: str) -> str:
    """剥句尾或句中的结构标签；整句只有标签时留给 hard gate/LLM 修稿。"""
    text = str(line or "").strip()
    if not text:
        return text
    without_labels = _DIALOGUE_META_LABEL_RE.sub("", text)
    if not re.sub(r"[，,；;。！？!?\s]", "", without_labels):
        return text
    match = _DIALOGUE_META_LABEL_SUFFIX_RE.search(text)
    if match:
        prefix = text[: match.start()].rstrip("，,；;。！？!? ")
        if prefix:
            tail = text[-1] if text[-1] in "。！？!?" else "。"
            return f"{prefix}{tail}"
    cleaned = _DIALOGUE_META_LABEL_STRIP_RE.sub(_strip_dialogue_meta_label, text)
    cleaned = re.sub(r"[，,；;]{2,}", "，", cleaned)
    cleaned = re.sub(r"^[，,；;]+", "", cleaned)
    cleaned = re.sub(r"[，,；;]+$", "", cleaned).strip()
    if not cleaned:
        return text
    if cleaned[-1] not in "。！？!?":
        cleaned += "。"
    return cleaned


def format_beat_chain(chain: list[Any]) -> str:
    lines: list[str] = []
    for i, item in enumerate(chain or [], start=1):
        if not isinstance(item, dict):
            continue
        sp = str(item.get("speaker") or "").strip()
        intent = str(item.get("intent") or item.get("beat") or "").strip()
        if sp and intent:
            turn = item.get("min_turns")
            quota = ""
            if isinstance(turn, int) and not isinstance(turn, bool) and turn > 1:
                quota = f"（须≥{turn}个回合）"
            lines.append(f"{i}. {sp}：{intent}{quota}")
    return "\n".join(lines)


def format_scene_block(contract: dict[str, Any]) -> str:
    """注入块 / gold_chat 用的 scene_contract 文本。"""
    if not isinstance(contract, dict):
        return "（无 scene_contract）"
    parts = [
        "【可拍场景契约 scene_contract】",
        f"source_type: {contract.get('source_type') or 'field'}",
        f"location: {contract.get('location') or ''}",
        f"object: {contract.get('object') or ''}",
        f"characters: {', '.join(contract.get('characters') or [])}",
        f"conflict: {contract.get('conflict') or ''}",
        f"mechanism: {contract.get('mechanism') or ''}",
        f"mom_lines_max: {contract.get('mom_lines_max', 0)}",
        f"remap_note: {contract.get('remap_note') or ''}",
        "beat_chain:",
        format_beat_chain(contract.get("beat_chain") or []) or "（无）",
    ]
    closing = str(contract.get("closing_intent") or "").strip()
    if closing:
        parts.append(f"closing_intent: {closing}")
    facts_block = format_fact_slots_block(contract.get("facts"))
    if facts_block:
        parts.append(facts_block)
    banned = contract.get("banned_literals") or []
    if banned:
        parts.append(
            "banned_literals: "
            + "、".join(str(x) for x in banned if str(x).strip())
        )
    return "\n".join(parts)


def fact_role_pair(contract: dict[str, Any] | None) -> tuple[str, str]:
    """把柄稿的两方：(挑战方, 权威方)。

    挑战方＝指认/翻旧账的人；权威方＝被指认后自曝、辩解、服软的人。
    优先读 ``facts``，其次读 ``beat_chain`` 的 speech_act；推不出返回空串。
    """
    sc = contract if isinstance(contract, dict) else {}
    challenger = ""
    authority = ""
    facts = sc.get("facts")
    if isinstance(facts, list):
        for item in facts:
            if not isinstance(item, dict):
                continue
            if not challenger:
                challenger = str(
                    item.get("accuser") or item.get("discoverer") or ""
                ).strip()
            if not authority:
                authority = str(
                    item.get("secret_holder") or item.get("denier") or ""
                ).strip()
    chain = sc.get("beat_chain")
    if isinstance(chain, list):
        for row in chain:
            if not isinstance(row, dict):
                continue
            speaker = str(row.get("speaker") or "").strip()
            if not speaker:
                continue
            act = str(row.get("speech_act") or "").strip().lower()
            if not challenger and act in {"accuse", "expose", "echo", "retort"}:
                challenger = speaker
            if not authority and act in {"deny", "admit", "confess"}:
                authority = speaker
    if challenger and authority and challenger != authority:
        return challenger, authority
    return "", ""


def format_fact_slots_block(facts: list[Any] | None) -> str:
    """把把柄事实的角色槽位写进 prompt：谁做过、谁指认、谁讨要。

    下游扩写最容易犯的错是让「做过那件事的人」去索要补偿、或让孩子
    认领家长的行为；注入槽位后由提示词约束，不靠剧情词正则。
    """
    lines: list[str] = []
    for item in facts or []:
        if not isinstance(item, dict):
            continue
        if not is_attribution_relevant_fact(item):
            continue
        fact_id = str(item.get("fact_id") or "").strip() or "F"
        event = str(item.get("event") or "").strip()
        slots = [
            f"{key}={str(item.get(key)).strip()}"
            for key in (
                "secret_holder",
                "accuser",
                "discoverer",
                "denier",
                "claimant",
            )
            if str(item.get(key) or "").strip()
        ]
        if not slots:
            continue
        head = f"facts[{fact_id}]: " + "；".join(slots)
        if event:
            head += f"（事件：{event}）"
        lines.append(head)
    if not lines:
        return ""
    return "\n".join(
        [
            "把柄事实角色（认领/自曝/辩解只能由 secret_holder 说，",
            "指认只能由 accuser 说，索要补偿只能由 claimant 说；",
            "secret_holder 不得反过来向对方讨要）：",
            *lines,
        ]
    )


_PARENT_SPEAKERS = frozenset({"妈妈", "爸爸"})
_RE_ADULT_EXAM = re.compile(r"高考|中考|考研|成考")
_RE_SCORE_NUM = re.compile(r"(\d{2,3})分")


def _contract_age_check_blob(contract: dict[str, Any]) -> str:
    """迁龄检查只看可拍正文口径，不含 remap_note 说明句（避免「高考→小学」误伤）。"""
    parts: list[str] = []
    for key in ("object", "conflict", "mechanism", "closing_intent"):
        parts.append(str(contract.get(key) or ""))
    for row in contract.get("beat_chain") or []:
        if isinstance(row, dict):
            parts.append(str(row.get("intent") or ""))
        else:
            parts.append(str(row))
    return "\n".join(parts)


def age_remap_contract_errors(
    story_raw: str,
    contract: dict[str, Any],
) -> list[str]:
    """站外成人考语境迁入 7–10 岁后，契约仍残留成人考/大总分则报错。

    抽象门槛：源稿含高考/中考等，且契约正文仍写成人考词，或原样带回 ≥300 的分值。
    """
    raw = str(story_raw or "")
    if not _RE_ADULT_EXAM.search(raw):
        return []
    blob = _contract_age_check_blob(contract) if contract else ""
    errors: list[str] = []
    if _RE_ADULT_EXAM.search(blob):
        errors.append("age_remap:contract_still_has_adult_exam")
    raw_big = {int(x) for x in _RE_SCORE_NUM.findall(raw) if int(x) >= 300}
    out_big = {int(x) for x in _RE_SCORE_NUM.findall(blob) if int(x) >= 300}
    if raw_big & out_big:
        errors.append("age_remap:adult_total_score_carried_over")
    return errors


def _elementary_score_map(raw: str, text: str) -> dict[int, int]:
    """把 ≥300 的成人总分映射为小学百分制高低对比（抽象，非单篇分值）。"""
    big = sorted(
        {
            int(x)
            for x in _RE_SCORE_NUM.findall(f"{raw}\n{text}")
            if int(x) >= 300
        }
    )
    if not big:
        return {}
    mapping: dict[int, int] = {}
    if len(big) == 1:
        mapping[big[0]] = 58 if big[0] < 550 else 98
        return mapping
    mapping[big[0]] = 58
    mapping[big[-1]] = 98
    for mid in big[1:-1]:
        mapping[mid] = 78
    return mapping


def _remap_adult_exam_text(text: str, *, score_map: dict[int, int]) -> str:
    out = _RE_ADULT_EXAM.sub("考试", str(text or ""))
    for old, new in sorted(score_map.items(), reverse=True):
        out = out.replace(f"{old}分", f"{new}分")
    return out


def remap_story_raw_scores_for_prompt(
    story_raw: str,
    *,
    contract: dict[str, Any] | None = None,
) -> str:
    """扩写/seed 提示用：把成人考大总分改成小学量级，避免原稿分数字面污染对白。"""
    text = str(story_raw or "")
    if not text:
        return text
    blob = ""
    if isinstance(contract, dict):
        blob = _contract_age_check_blob(contract)
    score_map = _elementary_score_map(text, blob or text)
    if not score_map and not _RE_ADULT_EXAM.search(text):
        return text
    return _remap_adult_exam_text(text, score_map=score_map)


def force_age_score_remap(
    contract: dict[str, Any],
    *,
    story_raw: str,
) -> tuple[dict[str, Any], bool]:
    """LLM 迁龄仍残留成人考/大总分时，本地改写契约文本字段。"""
    if not isinstance(contract, dict):
        return contract, False
    if not age_remap_contract_errors(story_raw, contract):
        return contract, False
    score_map = _elementary_score_map(
        story_raw,
        _contract_age_check_blob(contract),
    )
    out = dict(contract)
    changed = False
    for key in (
        "object",
        "conflict",
        "mechanism",
        "closing_intent",
        "remap_note",
    ):
        old = str(out.get(key) or "")
        if not old:
            continue
        new = _remap_adult_exam_text(old, score_map=score_map)
        if new != old:
            out[key] = new
            changed = True
    chain = out.get("beat_chain")
    if isinstance(chain, list):
        new_chain: list[Any] = []
        for row in chain:
            if not isinstance(row, dict):
                new_chain.append(row)
                continue
            item = dict(row)
            old = str(item.get("intent") or "")
            new = _remap_adult_exam_text(old, score_map=score_map)
            if new != old:
                item["intent"] = new
                changed = True
            new_chain.append(item)
        out["beat_chain"] = new_chain
    note = str(out.get("remap_note") or "").strip()
    marker = "成人考分已迁小学量级"
    if marker not in note:
        out["remap_note"] = f"{note}；{marker}".strip("；") if note else marker
        changed = True
    return out, changed


_RE_EXAM_SCORE = re.compile(r"(?<!\d)(\d{1,3})分")
_RE_SIBLING_LABEL = (
    (re.compile(r"妹妹"), "昭昭"),
    (re.compile(r"弟弟"), "昭昭"),
    (re.compile(r"姐姐"), "灿灿"),
    (re.compile(r"哥哥"), "灿灿"),
)


def remap_story_raw_sibling_roles(story_raw: str) -> str:
    """源稿把站内名反挂（姐姐昭昭/弟弟灿灿）时，按姐弟角色映回站内名。

    只处理「角色标 + 昭昭/灿灿」反挂；其他站外真名仍交 H3a remap。
    """
    text = str(story_raw or "")
    if not text.strip():
        return text
    swapped = bool(
        re.search(r"(?:姐姐|哥哥)\s*昭昭", text)
        or re.search(r"(?:弟弟|妹妹)\s*灿灿", text)
    )
    if not swapped:
        out = re.sub(r"(?:姐姐|哥哥)\s*灿灿", "灿灿", text)
        out = re.sub(r"(?:弟弟|妹妹)\s*昭昭", "昭昭", out)
        return out

    sis_ph, bro_ph = "<<SIS>>", "<<BRO>>"
    out = text
    out = re.sub(r"(?:姐姐|哥哥)\s*昭昭", sis_ph, out)
    out = re.sub(r"(?:弟弟|妹妹)\s*灿灿", bro_ph, out)
    out = out.replace("昭昭", sis_ph).replace("灿灿", bro_ph)
    out = re.sub(r"姐姐|哥哥", sis_ph, out)
    out = re.sub(r"弟弟|妹妹", bro_ph, out)
    out = out.replace(sis_ph, "灿灿").replace(bro_ph, "昭昭")
    out = re.sub(r"(灿灿){2,}", "灿灿", out)
    out = re.sub(r"(昭昭){2,}", "昭昭", out)
    return out


def scrub_h3_beat_list(
    beat: list[Any] | None,
    *,
    story_raw: str = "",
) -> list[Any]:
    """H3 beat 进 H3a 前：迁龄分数字面 + 站外姐弟称谓 → 站内名。"""
    if not isinstance(beat, list):
        return []
    score_map = _elementary_score_map(story_raw, story_raw) if story_raw else {}
    out: list[Any] = []
    for step in beat:
        text = str(step or "")
        if not text:
            out.append(step)
            continue
        if score_map or _RE_ADULT_EXAM.search(text):
            text = _remap_adult_exam_text(text, score_map=score_map)
        for pat, repl in _RE_SIBLING_LABEL:
            text = pat.sub(repl, text)
        out.append(text)
    return out


def canonical_exam_score_from_texts(*blobs: str) -> int | None:
    """从 seed/beat 文本抽小学百分制考分（1–100）；众数优先。"""
    from collections import Counter

    scores: list[int] = []
    for blob in blobs:
        for m in _RE_EXAM_SCORE.finditer(str(blob or "")):
            n = int(m.group(1))
            if 1 <= n <= 100:
                scores.append(n)
    if not scores:
        return None
    mode, _cnt = Counter(scores).most_common(1)[0]
    return mode


def sync_contract_exam_scores(
    contract: dict[str, Any],
    *,
    dialogue_seed: list[Any] | None = None,
    conflict_core: str = "",
) -> tuple[dict[str, Any], str, bool]:
    """契约与 seed 考分口径对齐：以 seed/beat_chain 众数为准改写 conflict 等。"""
    if not isinstance(contract, dict):
        return contract, conflict_core, False
    seed_blob = "\n".join(
        str(r.get("intent") or "")
        for r in (dialogue_seed or [])
        if isinstance(r, dict)
    )
    chain_blob = "\n".join(
        str(r.get("intent") or "")
        for r in (contract.get("beat_chain") or [])
        if isinstance(r, dict)
    )
    canon = canonical_exam_score_from_texts(seed_blob, chain_blob)
    if canon is None:
        return contract, conflict_core, False

    def _rewrite(text: str) -> str:
        raw = str(text or "")
        if not raw:
            return raw

        def _sub(m: re.Match[str]) -> str:
            n = int(m.group(1))
            if 1 <= n <= 100 and n != canon:
                return f"{canon}分"
            return m.group(0)

        return _RE_EXAM_SCORE.sub(_sub, raw)

    out = dict(contract)
    changed = False
    for key in ("object", "conflict", "mechanism", "closing_intent", "remap_note"):
        old = str(out.get(key) or "")
        new = _rewrite(old)
        if new != old:
            out[key] = new
            changed = True
    chain = out.get("beat_chain")
    if isinstance(chain, list):
        new_chain: list[Any] = []
        for row in chain:
            if not isinstance(row, dict):
                new_chain.append(row)
                continue
            item = dict(row)
            old = str(item.get("intent") or "")
            new = _rewrite(old)
            if new != old:
                item["intent"] = new
                changed = True
            new_chain.append(item)
        out["beat_chain"] = new_chain
    core = _rewrite(conflict_core)
    if core != str(conflict_core or ""):
        changed = True
    return out, core, changed


def _parent_in_h3_beats(h3: dict[str, Any] | None) -> bool:
    """H3 beat 文案是否把家长写成戏内行动者。"""
    if not isinstance(h3, dict):
        return False
    for step in h3.get("beat") or []:
        text = str(step or "")
        if any(p in text for p in ("妈妈", "爸爸", "家长")):
            return True
    return False


def _parent_in_contract(contract: dict[str, Any]) -> bool:
    chars = {
        str(c).strip()
        for c in (contract.get("characters") or [])
        if str(c).strip()
    }
    if chars & _PARENT_SPEAKERS:
        return True
    for row in contract.get("beat_chain") or []:
        if not isinstance(row, dict):
            continue
        if str(row.get("speaker") or "").strip() in _PARENT_SPEAKERS:
            return True
    note = f"{contract.get('remap_note') or ''} {contract.get('mechanism') or ''}"
    return any(p in note for p in ("妈妈", "爸爸", "家长"))


_K_PARENT_INTERVENTION_RE = re.compile(
    r"止争|平息|调解|劝架|提议|建议|一人.{0,8}一个|各.{0,6}一个|别抢|别闹|分开"
)
_K_PARENT_FAIL_CLOSE_RE = re.compile(
    r"叹气|劝不动|劝不了|管不了|拦不住|制止失败|僵持|不和好"
)


def normalize_k_parent_intervention_budget(
    contract: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    """K-A 两句家长预算下合并同轮干预，保住开场因果与最终劝失败。

    仅处理窄形状：K、mom_lines_max=2、恰有 3 个同一家长 beat，
    首拍与中拍都是干预/止争，末拍明确是劝失败/僵持。其它形状不猜。
    """
    if not isinstance(contract, dict):
        return contract, []
    if str(contract.get("story_type") or "").strip().upper() != "K":
        return contract, []
    try:
        mom_max = max(0, int(contract.get("mom_lines_max") or 0))
    except (TypeError, ValueError):
        return contract, []
    if mom_max != 2:
        return contract, []
    chain = contract.get("beat_chain")
    if not isinstance(chain, list) or len(chain) < 5:
        return contract, []

    parent_rows: list[tuple[int, dict[str, Any]]] = []
    for idx, row in enumerate(chain):
        if not isinstance(row, dict):
            continue
        if str(row.get("speaker") or "").strip() in _PARENT_SPEAKERS:
            parent_rows.append((idx, row))
    if len(parent_rows) != 3:
        return contract, []

    (first_idx, first), (middle_idx, middle), (last_idx, last) = parent_rows
    parent = str(first.get("speaker") or "").strip()
    if any(str(row.get("speaker") or "").strip() != parent for _, row in parent_rows):
        return contract, []
    first_intent = str(first.get("intent") or first.get("beat") or "").strip()
    middle_intent = str(middle.get("intent") or middle.get("beat") or "").strip()
    last_intent = str(last.get("intent") or last.get("beat") or "").strip()
    if not (
        _K_PARENT_INTERVENTION_RE.search(first_intent)
        and _K_PARENT_INTERVENTION_RE.search(middle_intent)
        and _K_PARENT_FAIL_CLOSE_RE.search(last_intent)
        and first_idx < middle_idx < last_idx
    ):
        return contract, []

    merged_first = dict(first)
    merged_first["intent"] = f"{first_intent}；同轮继续干预：{middle_intent}".strip("；")
    new_chain: list[Any] = []
    for idx, row in enumerate(chain):
        if idx == middle_idx:
            continue
        new_chain.append(merged_first if idx == first_idx else row)

    normalized: list[Any] = []
    for beat_no, row in enumerate(new_chain, 1):
        if isinstance(row, dict):
            item = dict(row)
            if "beat" in item:
                item["beat"] = beat_no
            normalized.append(item)
        else:
            normalized.append(row)
    out = dict(contract)
    out["beat_chain"] = normalized
    return out, [f"K家长预算2合并同轮干预:{parent}"]


def _parent_beat_count(chain: Any, *, speaker: str = "") -> int:
    """beat_chain 中由家长承担的拍数；给定 speaker 时只数该家长。"""
    if not isinstance(chain, list):
        return 0
    rows: list[Any] = []
    for row in chain:
        if not isinstance(row, dict):
            continue
        sp = str(row.get("speaker") or "").strip()
        if speaker:
            if sp == speaker:
                rows.append(row)
        elif sp in _PARENT_SPEAKERS:
            rows.append(row)
    return len(rows)


def chat_line_cap(structure_type: str = "") -> int:
    """对白句数硬上限：K 类（家长看戏）允许 +2，与 validate/length 同口径。"""
    st = str(structure_type or "").strip().upper()
    return CHAT_LINE_COUNT_MAX + (2 if st == "K" else 0)


def resolve_parent_lines_budget(
    source: dict[str, Any] | None = None,
    *,
    mom_lines_max: int | None = None,
    dad_lines_max: int | None = None,
    parent_lines_max: int | None = None,
    default_mom_lines_max: int = 1,
) -> tuple[int, int, int]:
    """家长台词预算权威口径：(mom_max, dad_max, parent_max)。

    取值优先级：显式入参 > ``source``（scene_contract / story）同名字段 > 派生默认。

    - ``mom_max``：妈妈上限，默认 ``default_mom_lines_max``；
    - ``parent_max``：家长合计上限，默认 ``mom_max + 1``
      （另一位家长最多 1 句，与"爸爸宜更少"的提示词口径一致）；
    - ``dad_max``：爸爸上限，默认 ``1``（家长预算为 0 时即 0）。

    再按 beat_chain 兜底抬额：契约自身要求某位家长承担 N 拍，却不给 N 句额度，会让任何
    合规稿都无法通过硬卡（死锁）。只按拍数抬额度，不凭剧情猜词。

    最后统一封顶到 ``chat_line_cap``：家长句数不可能超过全稿句数上限，故该封顶
    只挡脏契约（拍数异常膨胀），不会挡任何合法稿，也就不可能重新引入死锁。
    注意封顶用 ``min(max(契约值, 拍数), 上限)``：若写成 ``min(契约值, 拍数)``
    会反而把额度压到低于拍数，死锁复现。

    额度优先读 ``source`` 的显式字段，其次读 gold_chat 成稿注入的
    ``_gold_chat_<key>``（硬卡与评分层必须同口径）；cast 里只有一位家长时，
    把家长总预算让给在场的那一位，不让缺席家长的默认额度闲置。
    """

    def _pick(key: str, explicit: int | None, fallback: int) -> tuple[int, bool]:
        if explicit is not None:
            try:
                return max(0, int(explicit)), True
            except (TypeError, ValueError):
                return fallback, False
        if isinstance(source, dict):
            raw = source.get(key)
            if raw is None:
                # gold_chat 成稿会把契约额度以 `_gold_chat_*` 注入 chat，
                # 硬卡与评分层须读同一份口径，否则「评分按契约、硬卡按默认」
                # 的错开会把合规稿判死。
                raw = source.get(f"_gold_chat_{key}")
            if raw is not None:
                try:
                    return max(0, int(raw)), True
                except (TypeError, ValueError):
                    return fallback, False
        return fallback, False

    chain = None
    story_type = ""
    if isinstance(source, dict):
        chain = source.get("beat_chain") or source.get("gold_beat_chain")
        story_type = str(
            source.get("story_type") or source.get("structure_type") or ""
        )
    mom_beats = _parent_beat_count(chain, speaker="妈妈")
    dad_beats = _parent_beat_count(chain, speaker="爸爸")
    parent_beats = _parent_beat_count(chain)

    mom, _ = _pick("mom_lines_max", mom_lines_max, max(0, int(default_mom_lines_max)))
    parent, _ = _pick("parent_lines_max", parent_lines_max, mom + 1)
    dad, _ = _pick("dad_lines_max", dad_lines_max, 1 if parent > 0 else 0)

    cap = chat_line_cap(story_type)
    mom = min(max(mom, mom_beats), cap)
    dad = min(max(dad, dad_beats), cap)
    parent = min(max(parent, mom, dad, parent_beats), cap)

    # 只到一位家长时，另一位家长的默认额度不该继续占着家长总预算：``dad`` 默认 1 的
    # 前提是「妈妈是主家长、爸爸最多 1 句」。若 cast 里根本没有妈妈，唯一在场的家长仍被
    # 这个默认压到 1 句，而 parent 预算（如 3）白白闲置——只要契约要求这位家长多说一句
    # （解说、挡回、旁观表态），任何合规稿都过不了硬卡，属于死锁。按 cast 把额度让给在场
    # 的那一位，仍封顶到 ``cap``，不按剧情猜词。
    cast_raw = source.get("characters") if isinstance(source, dict) else None
    present = {
        str(x).strip()
        for x in (cast_raw if isinstance(cast_raw, (list, tuple, set)) else [])
        if str(x).strip()
    }
    lone = sorted(present & _PARENT_SPEAKERS)
    if len(lone) == 1:
        if lone[0] == "爸爸":
            dad = min(max(dad, parent), cap)
            mom = 0
        else:
            mom = min(max(mom, parent), cap)
            dad = 0
        parent = min(max(parent, mom, dad), cap)
    return mom, dad, parent


def apply_parent_role_budget(
    contract: dict[str, Any],
    *,
    h3: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """源稿/beat 有家长戏核时，勿把 mom_lines_max 压成 0、勿抹掉家长。

    不发明家长戏；只抬预算、补角色位。beat_chain 谁说哪句由 H3a 提示词约束。
    """
    if not isinstance(contract, dict):
        return contract
    st = str(
        contract.get("story_type")
        or (h3 or {}).get("structure_type")
        or "C"
    ).upper().strip()
    need_parent = _parent_in_h3_beats(h3) or _parent_in_contract(contract)

    raw_max = contract.get("mom_lines_max")
    if raw_max is None:
        if st == "H":
            contract["mom_lines_max"] = 3
        elif st == "K":
            contract["mom_lines_max"] = 2
        else:
            contract["mom_lines_max"] = 2 if need_parent else 0
    else:
        try:
            mom_max = max(0, int(raw_max))
        except (TypeError, ValueError):
            mom_max = 0
        contract["mom_lines_max"] = mom_max

    if need_parent:
        floor = 3 if st == "H" else 2
        if int(contract.get("mom_lines_max") or 0) < floor:
            contract["mom_lines_max"] = floor
        chars = [
            str(c).strip()
            for c in (contract.get("characters") or [])
            if str(c).strip()
        ]
        if not (set(chars) & _PARENT_SPEAKERS):
            chars.append("妈妈")
            contract["characters"] = chars
        note = str(contract.get("remap_note") or "").strip()
        marker = "戏核家长须保留出场"
        if marker not in note:
            contract["remap_note"] = (
                f"{note}；{marker}".strip("；") if note else marker
            )
    return contract


def validate_scene(contract: dict[str, Any] | None) -> list[str]:
    """H3a / H4a 规则：scene_contract 硬卡。"""
    errors: list[str] = []
    if not isinstance(contract, dict):
        return ["scene_contract_missing"]
    chars = contract.get("characters") or []
    if not isinstance(chars, list) or not chars:
        errors.append("scene_contract_characters_empty")
    else:
        for name in chars:
            n = str(name or "").strip()
            if n and n not in ALLOWED_SPEAKERS:
                errors.append(f"scene_contract_illegal_character:{n}")
    chain = contract.get("beat_chain") or []
    if not isinstance(chain, list) or len(chain) < BEAT_CHAIN_MIN:
        errors.append(
            f"beat_chain_too_short:"
            f"{len(chain) if isinstance(chain, list) else 0}"
        )
    else:
        declared_turns: list[int] = []
        for i, row in enumerate(chain):
            if not isinstance(row, dict):
                errors.append(f"beat_chain[{i}]_invalid")
                continue
            sp = str(row.get("speaker") or "").strip()
            if sp not in ALLOWED_SPEAKERS:
                errors.append(f"beat_chain[{i}]_speaker_illegal:{sp!r}")
            if "min_turns" in row:
                turn = row.get("min_turns")
                if not isinstance(turn, int) or isinstance(turn, bool):
                    errors.append(f"beat_chain[{i}]_min_turns_invalid:{turn!r}")
                elif not BEAT_MIN_TURNS_MIN <= turn <= BEAT_MIN_TURNS_MAX:
                    errors.append(f"beat_chain[{i}]_min_turns_invalid:{turn!r}")
                else:
                    declared_turns.append(turn)
        # 归一化后每拍都带 min_turns；此时校验契约能否撑起正文最少句数。
        if len(declared_turns) == len(chain):
            total_turns = sum(declared_turns)
            if total_turns < DIALOGUE_TURNS_MIN:
                errors.append(
                    f"beat_chain_turns_insufficient:"
                    f"{total_turns}<{DIALOGUE_TURNS_MIN}"
                )
            elif total_turns > CHAT_LINE_COUNT_MAX:
                errors.append(
                    f"beat_chain_turns_exceed:{total_turns}>{CHAT_LINE_COUNT_MAX}"
                )
        last = chain[-1] if chain else None
        if isinstance(last, dict):
            last_intent = str(last.get("intent") or last.get("beat") or "").strip()
            if is_terminal_no_reply_intent(last_intent):
                errors.append("beat_chain_terminal_no_reply_not_dialogue")
    source_type = str(contract.get("source_type") or "").strip().lower()
    if source_type == "tutorial":
        check_blob = (
            f"{contract.get('conflict')} "
            f"{contract.get('mechanism')} "
            f"{contract.get('remap_note')}"
        )
        for word in TUTORIAL_RESIDUE:
            if word in check_blob:
                errors.append(f"tutorial_residue_in_contract:{word}")
    return errors


def validate_dialogue_seed_speakers(seed: list[Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(seed, list) or len(seed) < SEED_MIN:
        errors.append(f"dialogue_seed_too_short:{len(seed) if isinstance(seed, list) else 0}")
        return errors
    for i, row in enumerate(seed):
        if not isinstance(row, dict):
            errors.append(f"dialogue_seed[{i}]_invalid")
            continue
        sp = str(row.get("speaker") or "").strip()
        if sp not in ALLOWED_SPEAKERS:
            errors.append(f"dialogue_seed[{i}]_speaker_illegal:{sp!r}")
    return errors


_NARRATION_LINE_RE = re.compile(
    r"(?:^|[，,])"
    r"(?:松手|转身离开|愣住|留下面面相觑|推向(?:灿灿|昭昭)|"
    r"放下牛奶|心里不是滋味，但坚持)|"
    # 第三人称分镜/动作说明（抽象形态，非单篇词表）
    r"被(?:灿灿|昭昭|妈妈)[^。！？]{0,20}|"
    r"^(?:叹气|愣住)[，,]|"
    r"(?:一把|挣扎着|护着手)[^。！？]{0,24}"
    r"(?:揪|按|拍|打|推|抓)|"
    r"(?:揪住|按住|推向)(?:昭昭|灿灿|她|他)|"
    r"按在地上|"
    r"又?补[一二两三四五两1-5]?下|"
    r"缩到角落|嘟囔着|一边[^，。]{0,10}一边|"
    r"(?:哼，)?(?:缩到|嘟囔|趴下|扭头走开)|"
    # 咀嚼/塞食动作说明（非口语；须带宾语/结果，避免误伤「看我一口吞」）
    r"一口(?:吞下|塞进|吞了)[^。！？?]{0,20}|"
    r"(?:^|[，,])奶油都?(?:挤|溢)(?:出来|出)?|"
    # 舞台指示：动作链 / 问：台词 / 纯动作收场（抽象，不绑单篇）
    r"(?:站直了|叉着?腰站|叉腰问)|"
    r"手指戳|"
    r"(?:^|[，,])戳(?:着)?(?:你的?)?(?:腰侧|腰眼)|"
    r"抽抽搭搭|"
    r"摇摇头|"
    r"转身回|"
    r"探(?:出)?头|"
    r"俯视|"
    r"问[:：]|"
    r"开口[:：]|"
    r"(?:不|没)说话|"
    r"没再管|"
    r"(?:把|将)(?:笔|东西)?举高|"
    r"(?:按倒在|追着)(?:灿灿|昭昭|沙发)|"
    r"(?:灿灿|昭昭)腰侧|"
    r"笑出眼泪后|"
    r"哇地一声|"
    r"嘴抿紧|"
    r"缩回[^，。]{0,6}|"
    r"拼命扭|"
    r"开始挠痒|"
    r"松手叉腰|"
    r"瞪(?:灿灿|昭昭|她|他)一眼|"
    # 当场动作指令入对白（抽象：按/继续+肢体，非「你抓我干嘛」控诉）
    r"按在沙发上|按沙发上|"
    r"(?:^|[，,])继续挠|"
    r"(?:看我)?吐舌头|"
    r"瞪你一眼|"
    # 动作+结果被模型直接塞进 line：巴掌/端碗/吞咽/抹泪/冷眼均须口语化
    r"(?:^|[，,])(?:抬手|扬手|挥手)[^。！？]{0,18}(?:一巴掌|巴掌|拍|打)|"
    r"(?:^|[，,])(?:乖乖)?(?:端|端起|接过|拿起)[^。！？]{0,8}(?:碗|杯)|"
    r"(?:^|[，,])仰头[^。！？]{0,12}(?:喝|灌)|"
    r"(?:^|[，,])(?:抹着|擦着)眼泪|"
    r"(?:^|[，,])眼神一冷|"
    # 动作/神态说明混入对白（抽象，不绑场景名词）
    r"拎起|"
    r"塞进(?:袋子|包)|"
    r"拉链一拉|"
    r"鞋跟一踩|"
    r"换好鞋|"
    r"(?:^|[，,])对视一眼|"
    r"(?:^|[，,])笑出声|"
    r"沉默几秒|沉默一会儿|"
    r"我俩都愣住|都愣住|"
    r"气全消了|"
    r"撞见(?:她|他)|"
    # 姿态分镜词（宜改口语「一起走/一起吃」，勿当 line 开头旁白）
    r"勾肩搭背|肩并肩|手挽手|挽着手臂|"
    # 叙述式起句：角色不可能自述「（突然）蹦出/冒出个 X」，只能当场说出内容
    r"(?:突然)?(?:蹦出|冒出)(?:了)?(?:个|一句|一串|一个)[^。！？]{0,12}|"
    # 身体动作叙述混入对白（与「叹气/愣住」同族，须改成当场反应）
    r"(?:^|[，,])(?:我)?(?:深?吸了?一?口气)[^。！？]{0,12}"
)
_RE_ACTION_CHUNK = re.compile(
    r"又?补[一二两三四五两1-5]?下|按在地上|"
    r"(?:一把|挣扎着|护着手)[^。！？]{0,24}(?:揪|按|拍|打|推|抓)|"
    r"(?:揪住|按住|推向)(?:昭昭|灿灿|她|他)|"
    r"被(?:灿灿|昭昭|妈妈)[^。！？]{0,16}|"
    r"缩到角落|嘟囔着|"
    r"^(?:叹气|愣住)$|"
    r"(?:站直了|叉着?腰站|叉腰问)[^，。！？]{0,12}|"
    r"手指戳[^，。！？]{0,12}|"
    r"(?:^|[，,])戳(?:着)?(?:你的?)?(?:腰侧|腰眼)[^，。！？]{0,8}|"
    r"抽抽搭搭[^，。！？]{0,12}|"
    r"摇摇头[^，。！？]{0,16}|"
    r"转身回[^，。！？]{0,12}|"
    r"探(?:出)?头[^，。！？]{0,16}|"
    r"俯视[^，。！？]{0,8}|"
    r"(?:不|没)说话|"
    r"没再管|"
    r"瞪(?:灿灿|昭昭|她|他)一眼|"
    r"(?:把|将)(?:笔|东西)?举高[^，。！？]{0,12}|"
    r"(?:按倒在|追着)(?:灿灿|昭昭|沙发)[^，。！？]{0,12}|"
    r"笑出眼泪后[^，。！？]{0,12}|"
    r"哇地一声[^，。！？]{0,8}|"
    r"嘴抿紧[^，。！？]{0,12}|"
    r"缩回[^，。！？]{0,8}|"
    r"拼命扭|"
    r"开始挠痒[^，。！？]{0,8}|"
    r"松手叉腰[^，。！？]{0,12}|"
    r"按在沙发上|"
    r"(?:^|[，,])继续挠[^，。！？]{0,6}|"
    r"(?:^|[，,])吐舌头"
)


def looks_like_narration_line(text: str) -> bool:
    """对白/seed 是否像分镜动作说明而非可说出口的话。"""
    line = str(text or "").strip()
    return bool(line and _NARRATION_LINE_RE.search(line))


def rewrite_narration_to_speech(text: str, *, speaker: str = "") -> str:
    """把动作说明压成可说出口的短句；无口语尾巴则给抽象兜底。"""
    raw = str(text or "").strip()
    if not raw or not looks_like_narration_line(raw):
        return raw
    sp = str(speaker or "").strip()
    # “端碗只说一个字：喝”这类动作+原话，优先保留真正说出口的原话。
    m_only_word = re.search(
        r"只说(?:一个字|一句)[：:]\s*[“]?([^，。！？!?“”]{1,6})",
        raw,
    )
    if m_only_word:
        tail = m_only_word.group(1).strip()
        if tail:
            return tail + ("" if tail[-1] in "？！。!?" else "！")

    # “抹着眼泪，二十年后……”：动作前缀去掉，保留后面的现场放话。
    m_tears = re.match(r"^(?:抹着|擦着)眼泪[，,]\s*(.+)$", raw)
    if m_tears:
        tail = m_tears.group(1).strip("，。！？ ")
        if tail and not looks_like_narration_line(tail):
            return tail + ("" if tail[-1] in "？！。!?" else "！")

    # “瞪他一眼，作业写不写”：去神态，只留可说出口的追问。
    m_glare = re.match(
        r"^瞪(?:灿灿|昭昭|她|他|你)?一眼[，,]\s*(.+)$",
        raw,
    )
    if m_glare:
        tail = m_glare.group(1).strip("，。！？ ")
        if tail and not looks_like_narration_line(tail):
            mark = "？" if re.search(r"不|吗|么|啥|什么|怎么|为什么", tail) else "！"
            return tail + mark

    # 一锤动作+对方秒怂是分镜结果，不让角色自述动作过程；保留“一巴掌/老实”结构锚。
    if re.search(r"(?:抬手|扬手|挥手).{0,18}(?:一巴掌|巴掌|拍|打)", raw):
        if re.search(r"老实|缩手|怂|不敢", raw):
            return "一巴掌就老实了吧！"
        return "还敢跟我顶嘴！"

    # 接碗/仰头喝属于表演动作；角色只说当场反应。
    if re.search(
        r"(?:乖乖)?(?:端|端起|接过|拿起).{0,8}(?:碗|杯)|仰头.{0,12}(?:喝|灌)",
        raw,
    ):
        if re.search(r"苦|咧嘴", raw):
            return "苦死我了！"
        return "我喝了！"

    # 咀嚼/塞食动作 → 可说的逞强短句（抽象，不绑具体食物）
    if re.search(r"一口(?:吞下|塞进|吞了)|奶油都?(?:挤|溢)", raw):
        return "看我一口吞！"
    m_pose = re.match(
        r"^(?:勾肩搭背|肩并肩|手挽手|挽着手臂)[，,]\s*(.+)$",
        raw,
    )
    if m_pose:
        tail = m_pose.group(1).strip("，。！？ ")
        if tail and not looks_like_narration_line(tail):
            if tail[-1] not in "？！。!?":
                tail = f"{tail}！"
            return tail
        return "咱俩一起走！" if sp in {"昭昭", "灿灿"} else "一起走！"
    if re.search(r"^(?:勾肩搭背|肩并肩|手挽手)", raw):
        return "咱俩一起走！" if sp in {"昭昭", "灿灿"} else "一起走！"
    # 「…问：台词」/「…开口：台词」只留冒号后口语
    m_ask = re.search(r"(?:问|开口)[:：]\s*(.+)$", raw)
    if m_ask:
        tail = m_ask.group(1).strip("，。！？ ")
        if tail and not looks_like_narration_line(tail):
            if tail[-1] not in "？！。!?":
                tail = f"{tail}！"
            return tail
    # 「（突然）蹦出个 X，内容」：叙述动词剥掉，只留当场说出的内容
    m_blurt = re.match(
        r"^(?:突然)?(?:蹦出|冒出)(?:了)?(?:个|一句|一串|一个)"
        r"[^，,。！？]{0,12}[，,]\s*(.+)$",
        raw,
    )
    if m_blurt:
        tail = m_blurt.group(1).strip("，。！？ ")
        if tail and not looks_like_narration_line(tail):
            if tail[-1] not in "？！。!?":
                tail = f"{tail}！"
            return tail
    # 「我深吸一口气，内容」：剥掉身体动作，只留当场说出的话
    m_breath = re.match(
        r"^(?:我)?(?:深?吸了?一?口气)[，,]\s*(.+)$",
        raw,
    )
    if m_breath:
        tail = m_breath.group(1).strip("，。！？ ")
        if tail and not looks_like_narration_line(tail):
            if tail[-1] not in "？！。!?":
                tail = f"{tail}！"
            return tail
    # 「笑出声，口语尾巴」只留可说部分
    m_laugh = re.match(r"笑出声[，,]\s*(.+)$", raw)
    if m_laugh:
        tail = m_laugh.group(1).strip("，。！？ ")
        if tail and not looks_like_narration_line(tail):
            if tail[-1] not in "？！。!?":
                tail = f"{tail}！"
            return tail
    # 「对视一眼，…」剥掉神态块，留口语尾巴
    m_gaze = re.match(r"对视一眼[，,]\s*(.+)$", raw)
    if m_gaze:
        tail = m_gaze.group(1).strip()
        tail = re.sub(r"^气全消了[，,]?\s*", "", tail).strip("，。！？ ")
        if tail and not looks_like_narration_line(tail):
            if tail[-1] not in "？！。!?":
                tail = f"{tail}！"
            return tail
    # 家长旁观笑声 → 可说的旁观句（勿劝架）
    if sp in {"妈妈", "爸爸"} and re.search(r"笑", raw):
        return "你们闹吧，我看着！"
    # 僵持/不说话收场 → 短哼
    if re.search(r"(?:不|没)说话|不敢再闹|缩回|瞪.{0,4}一眼", raw):
        if sp not in {"妈妈", "爸爸"}:
            return "哼！"
    fallback = (
        "唉，我管不了你们了" if sp in {"妈妈", "爸爸"} else "你别过来！"
    )
    parts = [p.strip() for p in re.split(r"[，,]", raw) if p.strip()]
    spoken: list[str] = []
    for part in parts:
        # 纯动作块即使带「我」也剥掉（如「我补两下」）
        if _RE_ACTION_CHUNK.search(part) and not re.search(
            r"[？！]|疼|怕|不服|活该|警告|别逼|松手|嘴硬|还不哭",
            part,
        ):
            cleaned = _RE_ACTION_CHUNK.sub("", part).strip("，。！？ ")
            cleaned = re.sub(r"^我$", "", cleaned).strip()
            if cleaned and re.search(r"[我你]|疼|怕|警告|别|嘴硬|哭", cleaned):
                spoken.append(cleaned)
            continue
        if looks_like_narration_line(part) and not re.search(
            r"[？！]|警告|别|喊|妈|疼|怕|不服|活该|管不了|嘴硬|还不哭",
            part,
        ):
            continue
        if re.search(
            r"[我你]|[？！]|警告|别|喊|妈|疼|怕|不服|活该|管不了|劝不|嘴硬|还不哭",
            part,
        ):
            spoken.append(part)
    if spoken:
        out = spoken[0]
        for part in spoken[1:]:
            if out and out[-1] in "？！。!?":
                out = f"{out}{part}"
            else:
                out = f"{out}，{part}"
        out = _RE_ACTION_CHUNK.sub("", out)
        out = re.sub(r"[？！。!?][，,]+", lambda m: m.group(0)[0], out)
        out = re.sub(r"[，,]{2,}", "，", out)
        out = re.sub(r"(?:^|[，,])我(?=[，,]|$)", "", out)
        out = out.strip("，。 ")
        if not out:
            return fallback
        if looks_like_narration_line(out):
            return fallback
        if out[-1] not in "？！。!?":
            out = f"{out}！"
        return out
    return fallback


def sanitize_dialogue_seed_speech(seed: list[Any] | None) -> list[Any]:
    """seed intent/line 若是分镜说明，压成可说出口的话（全类型通用）。"""
    if not isinstance(seed, list):
        return []
    out: list[Any] = []
    for item in seed:
        if not isinstance(item, dict):
            out.append(item)
            continue
        row = dict(item)
        sp = str(row.get("speaker") or "").strip()
        key = "intent" if str(row.get("intent") or "").strip() else "line"
        text = str(row.get(key) or "").strip()
        if text and looks_like_narration_line(text):
            row[key] = rewrite_narration_to_speech(text, speaker=sp)
        out.append(row)
    return out


def patch_dialogue_narration_to_speech(story: dict[str, Any]) -> list[str]:
    """正文对白里的分镜说明压成口语。"""
    notes: list[str] = []
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return notes
    for i, item in enumerate(dialogue):
        if not isinstance(item, dict):
            continue
        sp = str(item.get("speaker") or "").strip()
        line = str(item.get("line") or "").strip()
        relay_direct = _RELAY_PARENT_PREFIX.sub("", line).strip()
        if relay_direct and relay_direct != line:
            item["line"] = relay_direct
            line = relay_direct
            notes.append(f"转述→现场对白[{i + 1}]")
        if not looks_like_narration_line(line):
            continue
        new_line = rewrite_narration_to_speech(line, speaker=sp)
        if looks_like_narration_line(new_line):
            new_line = (
                "唉，我管不了你们了"
                if sp in {"妈妈", "爸爸"}
                else "你别过来！"
            )
        if new_line != line:
            item["line"] = new_line
            notes.append(f"旁白→口语[{i + 1}]")
    return notes


def collect_narration_dialogue_errors(dialogue: list[Any]) -> list[str]:
    """分镜/动作句误当对白。"""
    errors: list[str] = []
    for i, item in enumerate(dialogue or []):
        if not isinstance(item, dict):
            continue
        line = str(item.get("line") or "").strip()
        if looks_like_narration_line(line):
            errors.append(f"dialogue[{i}] narration_not_speech")
    return errors


def collect_voice_errors(dialogue: list[Any]) -> list[str]:
    errors: list[str] = []
    for i, item in enumerate(dialogue or []):
        if not isinstance(item, dict):
            continue
        line = str(item.get("line") or "").strip()
        if not line:
            continue
        if _PAREN_IN_LINE.search(line):
            errors.append(f"dialogue[{i}] 含括号说明，须改为当场对白")
        elif _RELAY_SPEECH.search(line):
            errors.append(f"dialogue[{i}] 像转述/论述，须改为第一人称现场对白")
        elif _REMAP_SIBLING_TERMS.search(line):
            errors.append(
                f"dialogue[{i}] 含站外称谓哥哥/弟弟，须改姐姐/昭昭/灿灿"
            )
    return errors


# banned_literals 仅保留站外真名 / 须 remap 的 speaker 称谓（H3 prompt 对齐）
SPEAKER_REMAP_BANNED: frozenset[str] = frozenset(
    {
        "哥哥",
        "妹妹",
        "弟弟",
        "姐姐",
        "小男孩",
        "小女孩",
        "爸爸",
        "父亲",
        "母亲",
        "宝爸",
        "宝妈",
        "老爸",
        "对方",
        "陌生小孩",
        "对方家长",
        "对方妈妈",
        "对方爸爸",
        "小朋友",
        "对方孩子",
    },
)

# 常见 scene / 笑点词，禁止 LLM 误写入 banned_literals
_BANNED_LITERAL_NEVER: frozenset[str] = frozenset(
    {
        "画画",
        "碘伏",
        "朋友圈",
        "涂药",
        "扭打",
        "相声",
    },
)

# 站内姐弟体系下对白可用的合法称呼：产品要求昭昭称灿灿为「姐姐」
# （见 gold_chat/prompts.py「昭昭口中禁止直呼灿灿，一律称姐姐」）。
# 这类称呼是目标用语而非源稿称谓，不得因 H3 误列而进禁词表——否则
# 「昭昭：姐姐…」会被自己的禁词表拦下，甚至被反向改写成直呼其名。
_IN_PRODUCT_KINSHIP_ALLOWED: frozenset[str] = frozenset({"姐姐"})

_SURNAME_HINT = re.compile(r"[贾赵李王张刘陈杨黄周吴徐孙马朱胡郭何高林罗郑梁]")


def _scene_core_blob(
    scene_contract: dict[str, Any] | None,
    beat: list[Any] | None,
) -> str:
    sc = scene_contract or {}
    parts: list[str] = [
        str(sc.get("object") or ""),
        str(sc.get("conflict") or ""),
        str(sc.get("mechanism") or ""),
        str(sc.get("closing_intent") or ""),
        str(sc.get("location") or ""),
    ]
    for row in sc.get("beat_chain") or []:
        if isinstance(row, dict):
            parts.append(str(row.get("intent") or row.get("beat") or ""))
    for item in beat or []:
        parts.append(str(item or ""))
    return "".join(parts)


def _is_source_proper_name(word: str) -> bool:
    w = str(word or "").strip()
    if len(w) < 3 or len(w) > 8:
        return False
    if not re.fullmatch(r"[\u4e00-\u9fff]+", w):
        return False
    if w in _BANNED_LITERAL_NEVER:
        return False
    return bool(_SURNAME_HINT.search(w))


# 站内姐弟体系的长幼约定（产品固定）：灿灿=姐姐=年长，昭昭=弟弟=年幼。
IN_PRODUCT_SENIOR_NAME = "灿灿"
IN_PRODUCT_JUNIOR_NAME = "昭昭"

# 源标题里的长幼称谓
_RE_TITLE_SENIOR_TERM = re.compile(r"哥哥|姐姐")
_RE_TITLE_JUNIOR_TERM = re.compile(r"弟弟|妹妹")
_RE_DIRECT_MAPPING_NOTE = re.compile(r"直接映射|原样映射|一对一映射")

# 源称谓体系 → (年长性别, 年幼性别)；站内固定为女长男幼
_SOURCE_SENIORITY_SYSTEMS: dict[frozenset[str], str] = {
    frozenset({"哥哥", "妹妹"}): "兄妹",
    frozenset({"姐姐", "弟弟"}): "姐弟",
    frozenset({"哥哥", "弟弟"}): "兄弟",
    frozenset({"姐姐", "妹妹"}): "姐妹",
}
_IN_PRODUCT_SYSTEM = "姐弟"


def source_sibling_seniority(bili_title: str) -> str:
    """从源标题识别兄弟姐妹体系（兄妹/姐弟/兄弟/姐妹）；识别不出返回空。"""
    text = str(bili_title or "")
    senior = _RE_TITLE_SENIOR_TERM.findall(text)
    junior = _RE_TITLE_JUNIOR_TERM.findall(text)
    if not senior or not junior:
        return ""
    # 同一性别或跨性别各取一个代表词，拼成可识别组合
    pair = frozenset({senior[0], junior[0]})
    return _SOURCE_SENIORITY_SYSTEMS.get(pair, "")


def sibling_seniority_warnings(
    *,
    bili_title: str = "",
    remap_note: str = "",
    speaker_map_note: str = "",
) -> list[str]:
    """源兄弟姐妹体系与站内姐弟约定不同构时，提示核对长幼方向。

    站内固定「灿灿=姐姐=年长，昭昭=弟弟=年幼」。若源是兄妹/兄弟/姐妹，
    长幼方向与站内不同构，「直接映射」不可能成立，须逐人确认谁对应灿灿。
    """
    system = source_sibling_seniority(bili_title)
    if not system or system == _IN_PRODUCT_SYSTEM:
        return []
    note = f"{remap_note or ''}{speaker_map_note or ''}"
    if _RE_DIRECT_MAPPING_NOTE.search(note):
        return [
            f"源兄弟姐妹体系为「{system}」，与站内「{_IN_PRODUCT_SYSTEM}」"
            f"（{IN_PRODUCT_SENIOR_NAME}=姐姐=年长，"
            f"{IN_PRODUCT_JUNIOR_NAME}=弟弟=年幼）不同构，"
            "不能声明「直接映射」；须逐人核对长幼方向，"
            "避免源中年长者被映射成站内年幼者"
        ]
    if not re.search(r"年长|长幼|姐姐|弟弟|妹妹|哥哥", note):
        return [
            f"源兄弟姐妹体系为「{system}」，与站内「{_IN_PRODUCT_SYSTEM}」不同构，"
            "remap/speaker_map 未说明长幼方向；须补明谁对应"
            f"{IN_PRODUCT_SENIOR_NAME}（年长）"
        ]
    return []


def sanitize_banned_literals(
    banned: list[Any] | None,
    *,
    scene_contract: dict[str, Any] | None = None,
    beat: list[Any] | None = None,
) -> list[str]:
    """过滤 H3 误伤的 scene/笑点词，只留 remap 称谓与站外真名。"""
    core = _scene_core_blob(scene_contract, beat)
    out: list[str] = []
    seen: set[str] = set()
    for raw in banned or []:
        w = str(raw or "").strip()
        if not w or w in seen:
            continue
        if w in _BANNED_LITERAL_NEVER:
            continue
        if w in _IN_PRODUCT_KINSHIP_ALLOWED:
            continue
        if w in core:
            continue
        if w in SPEAKER_REMAP_BANNED or _is_source_proper_name(w):
            seen.add(w)
            out.append(w)
    return out


def seed_from_beat_chain(chain: list[Any]) -> list[dict[str, str]]:
    """beat_chain → dialogue_seed 兜底；末尾纯静默结果不生成假对白。"""
    rows, _ = trim_terminal_no_reply_rows(chain)
    out: list[dict[str, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        sp = str(row.get("speaker") or "").strip()
        intent = str(row.get("intent") or row.get("beat") or "").strip()
        if sp in ALLOWED_SPEAKERS and intent:
            out.append({"speaker": sp, "intent": intent})
    return out


def align_seed_two_kids_vs_parent(
    seed: list[Any] | None,
    *,
    characters: list[Any] | None = None,
) -> tuple[list[Any], list[str]]:
    """单孩+家长稿的 seed 补齐第二个孩子（同侧），避免模型自编立场。

    源视频多为「一个孩子 vs 家长」，但本流水线的成稿形态是**两个孩子同侧**
    齐上（用户口径：2 孩子 vs 大人）。seed 只含一个孩子时，模型必须自己
    发明第二个孩子的立场，实测会漂成「替家长辩护」或「跟同伴对立」，
    终检必报身份/对话对象错位。

    这里按结构化信息补一拍：在**把柄被抛出的那一拍之后**，让另一位孩子
    以同侧身份接话（见证/帮腔），不新增冲突、不改变既有拍序。
    只在「恰好一个孩子 + 至少一位家长」时生效。
    """
    rows = [r for r in (seed or []) if isinstance(r, dict)]
    if not rows:
        return list(seed or []), []
    chars = [
        str(c).strip() for c in (characters or []) if str(c).strip()
    ]
    kids: list[str] = []
    for row in rows:
        sp = str(row.get("speaker") or "").strip()
        if sp in CHILD_SPEAKER_LABELS and sp not in kids:
            kids.append(sp)
    has_parent = any(
        str(row.get("speaker") or "").strip() in PARENT_SPEAKER_LABELS
        for row in rows
    )
    if len(kids) != 1 or not has_parent:
        return list(seed or []), []
    kid = kids[0]
    other = next(
        (
            c
            for c in ("昭昭", "灿灿")
            if c in CHILD_SPEAKER_LABELS and c != kid
        ),
        "",
    )
    if not other:
        return list(seed or []), []
    # 角色表已含两个孩子时无需补；只列一个孩子时按「单孩源须拆双孩」补齐
    # （与扩写系统提示同一口径），避免契约与提示词互相打架。
    listed_kids = [c for c in chars if c in CHILD_SPEAKER_LABELS]
    if len(listed_kids) >= 2:
        return list(seed or []), []
    # 找把柄抛出拍：结构化槽位 accuse/claim_compensation 优先
    anchor = -1
    for i, row in enumerate(rows):
        act = str(row.get("speech_act") or "").strip().lower()
        role = str(row.get("claim_role") or "").strip().lower()
        if act in {"accuse", "expose"} or role in {"accuser", "discoverer"}:
            anchor = i
    if anchor < 0:
        return list(seed or []), []
    if any(
        str(row.get("speaker") or "").strip() == other
        for row in rows[anchor:]
    ):
        return list(seed or []), []
    out: list[Any] = list(seed or [])
    insert_at = anchor + 1
    out.insert(
        insert_at,
        {
            "speaker": other,
            # 必须写成**能说出口的对白**：seed 的 intent 会被当台词补进正文，
            # 写成说明（含括号/勿/禁）会被终检判旁白。
            "intent": "我也看见了，这事你别想赖！",
            "speech_act": "echo",
            "claim_role": "accuser",
        },
    )
    return out, [f"seed补同侧第二孩:{other}@{insert_at + 1}"]


_N_SEED_ASK_INTENT = re.compile(
    r"追问|质问|设问|发问|问：|问什么|为什么|为啥|凭什么|怎么(?:会|想|知道)"
)
_N_SEED_ANSWER_INTENT = re.compile(
    r"回答|作答|解释|自洽|离谱|反驳|嘴硬|讲圆|理由|原因|补一句"
)
# 只旁观的孩子若在 seed 里承担这些意图，就会被扩写写成追问方
_N_SEED_VIEWER_QUESTION = re.compile(
    r"追问|质问|设问|发问|问：|问什么|为什么|为啥|凭什么|"
    r"怎么(?:会|想|知道|回事)|是不是|要不要|能不能|"
    r"哪(?:儿|里|来|个|些)?|谁(?:教|说|给|让)|什么(?:意思|名字|东西)"
)


def realign_seed_viewer_questions_to_asker(
    seed: list[Any] | None,
    *,
    contract: dict[str, Any] | None = None,
) -> tuple[list[Any], list[str]]:
    """N：追问拍只归立规方，旁观孩子不得在骨架里代问。

    契约里设问/追问的说话人唯一时，把**旁观孩子**（既非追问方也非回答方）
    的追问类 seed 改派给追问方。旁观者只保留旁观反应（笑/看热闹/接一句
    无关的）；否则扩写会把立规方挤成「立规 + 总结」两端，N 的
    「立规方被整句整懵」机制随之失效（#87 实测）。

    只改 speaker，不改 intent、不新增剧情；非 N 或追问方不唯一时原样返回。
    """
    rows = [r for r in (seed or []) if isinstance(r, dict)]
    if not rows:
        return list(seed or []), []
    sc = contract if isinstance(contract, dict) else {}
    if str(sc.get("story_type") or "").strip().upper() != "N":
        return list(seed or []), []
    chain = sc.get("beat_chain") or []
    askers: set[str] = set()
    answerers: set[str] = set()
    for item in chain:
        if not isinstance(item, dict):
            continue
        speaker = str(item.get("speaker") or "").strip()
        if not speaker:
            continue
        intent = str(item.get("intent") or "")
        if _N_SEED_ASK_INTENT.search(intent):
            askers.add(speaker)
        if _N_SEED_ANSWER_INTENT.search(intent):
            answerers.add(speaker)
    if len(askers) != 1:
        return list(seed or []), []
    asker = next(iter(askers))
    if asker in answerers:
        return list(seed or []), []
    viewers = {
        str(row.get("speaker") or "").strip()
        for row in rows
    } - askers - answerers
    viewers = {v for v in viewers if v}
    if not viewers:
        return list(seed or []), []
    out: list[Any] = []
    notes: list[str] = []
    for index, row in enumerate(seed or []):
        if not isinstance(row, dict):
            out.append(row)
            continue
        speaker = str(row.get("speaker") or "").strip()
        intent = str(row.get("intent") or "")
        if speaker in viewers and _N_SEED_VIEWER_QUESTION.search(intent):
            new_row = dict(row)
            new_row["speaker"] = asker
            out.append(new_row)
            notes.append(f"seed旁观追问改派:{speaker}→{asker}@{index + 1}")
            continue
        out.append(row)
    return out, notes


def parent_identity_claim_target(text: str) -> str | None:
    """自称家长身份的目标角色（妈妈/爸爸）；非自称或非身份句返回 None。"""
    raw = str(text or "")
    match = _PARENT_IDENTITY_SELF_CLAIM.search(raw)
    if not match or _ROLEPLAY_FRAME.search(raw):
        return None
    if _inside_quotes(raw, match.start()):
        return None
    span = match.group(0)
    if "妈" in span:
        return "妈妈"
    if "爸" in span:
        return "爸爸"
    return None


def realign_parent_identity_rows(
    rows: list[Any] | None,
    *,
    parent_labels: tuple[str, ...] = (),
) -> tuple[list[Any], list[str]]:
    """孩子 speaker 的家长身份句：裸自称归位家长，回声句转换人称。

    只认身份自称这一强排他谓词，不按剧情/行为词过滤，避免过拟合单篇；
    裸自称的家长不在 ``parent_labels``（本稿角色表）内则丢弃该行，
    不硬塞给不存在的角色。引号内真引述与扮演框架原样保留。
    """
    parents = tuple(str(p).strip() for p in parent_labels if str(p).strip())
    out: list[Any] = []
    notes: list[str] = []
    for row in rows or []:
        if not isinstance(row, dict):
            out.append(row)
            continue
        speaker = str(row.get("speaker") or "").strip()
        if speaker not in CHILD_SPEAKER_LABELS:
            out.append(row)
            continue
        field = next(
            (
                key
                for key in ("intent", "text", "line")
                if str(row.get(key) or "").strip()
            ),
            "",
        )
        text = str(row.get(field) or "") if field else ""
        match = _PARENT_IDENTITY_SELF_CLAIM.search(text)
        if not match or _ROLEPLAY_FRAME.search(text):
            out.append(row)
            continue
        if _inside_quotes(text, match.start()):
            out.append(row)
            continue
        if _PARENT_IDENTITY_ECHO_FRAME.search(text):
            # 回声/扣原话：保留归属与关键词，只把错误自称换成对方身份
            fixed = (
                text[: match.start()]
                + _swap_person_deixis(match.group(0))
                + text[match.end():]
            )
            item = dict(row)
            item[field] = fixed
            out.append(item)
            notes.append(f"身份回声人称转换:{speaker}:{text}→{fixed}")
            continue
        target = parent_identity_claim_target(text)
        if target is None or target not in parents:
            notes.append(f"身份自称家长不在本稿，丢弃:{speaker}:{text}")
            continue
        item = dict(row)
        item["speaker"] = target
        out.append(item)
        notes.append(f"身份自称归位:{speaker}→{target}")
    return out, notes


# ---- 事实角色（「谁做过那件事」）：H3a 出 facts，H3b seed 带角色标注 ----
# 代码只校验 LLM 自己标好的结构化角色，不解析剧情词。
FACT_ROLE_KEYS: tuple[str, ...] = (
    "secret_holder",
    "discoverer",
    "accuser",
    "denier",
    "claimant",
    "beneficiary",
)
FACT_ATTRIBUTION_STATUSES: frozenset[str] = frozenset(
    {"resolved", "ambiguous", "review_pending"}
)
FACT_ADMIT_ACTS: frozenset[str] = frozenset(
    {"admit", "confess", "self_report", "deny"}
)
FACT_ACCUSE_ACTS: frozenset[str] = frozenset({"accuse", "expose", "tease"})
FACT_CLAIM_ACTS: frozenset[str] = frozenset(
    {"claim_compensation", "demand", "bargain"}
)
FACT_ECHO_ACTS: frozenset[str] = frozenset({"echo", "retort"})
_FACT_UNKNOWN_VALUES = frozenset({"unknown", "null", "none"})


def normalize_fact_attributions(raw: Any) -> list[dict[str, Any]]:
    """H3a facts 规范化：只留带 fact_id 的条目，未知角色清空。"""
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        fact = dict(item)
        fact_id = str(fact.get("fact_id") or fact.get("id") or "").strip()
        if not fact_id:
            continue
        fact["fact_id"] = fact_id
        for key in FACT_ROLE_KEYS:
            value = str(fact.get(key) or "").strip()
            fact[key] = "" if value.lower() in _FACT_UNKNOWN_VALUES else value
        status = str(fact.get("attribution_status") or "").strip().lower()
        fact["attribution_status"] = (
            status if status in FACT_ATTRIBUTION_STATUSES else "ambiguous"
        )
        out.append(fact)
    return out


def fact_attribution_index(
    facts: list[Any] | None,
) -> dict[str, dict[str, Any]]:
    """fact_id → fact；无 fact_id 的条目忽略。"""
    index: dict[str, dict[str, Any]] = {}
    for item in facts or []:
        if not isinstance(item, dict):
            continue
        fact_id = str(item.get("fact_id") or "").strip()
        if fact_id:
            index[fact_id] = item
    return index


def fact_role_conflict_reason(
    row: dict[str, Any],
    facts: dict[str, dict[str, Any]],
) -> str | None:
    """结构化角色绑定校验；无标注或与事实无关的行一律放行。"""
    if not isinstance(row, dict):
        return None
    fact_ref = str(row.get("fact_ref") or "").strip()
    if not fact_ref or fact_ref not in facts:
        return None
    fact = facts[fact_ref]
    if fact.get("role_play") or fact.get("quotation_frame"):
        return None
    speaker = str(row.get("speaker") or "").strip()
    speech_act = str(row.get("speech_act") or "").strip().lower()
    claim_role = str(row.get("claim_role") or "").strip().lower()
    holder = str(fact.get("secret_holder") or "")
    if not speaker or not speech_act:
        return None
    if speech_act in FACT_ADMIT_ACTS:
        if holder and speaker != holder:
            return f"{speech_act} 应归 secret_holder={holder}，实为 {speaker}"
        return None
    if speech_act in FACT_ACCUSE_ACTS:
        if claim_role not in {"accuser", "discoverer"}:
            return (
                f"{speech_act} 的 claim_role 应为 accuser/discoverer，"
                f"实为 {claim_role or '空'}"
            )
        expected = str(fact.get(claim_role) or "")
        if expected and speaker != expected:
            return f"{speech_act} 应归 {claim_role}={expected}，实为 {speaker}"
        if holder and speaker == holder:
            return f"{speech_act} 不得由 secret_holder={holder} 说（除非自曝）"
        return None
    if speech_act in FACT_CLAIM_ACTS:
        if claim_role not in {"claimant", "beneficiary"}:
            return (
                f"{speech_act} 的 claim_role 应为 claimant/beneficiary，"
                f"实为 {claim_role or '空'}"
            )
        expected = str(fact.get(claim_role) or "")
        if expected and speaker != expected:
            return f"{speech_act} 应归 {claim_role}={expected}，实为 {speaker}"
        if holder and speaker == holder:
            return f"{speech_act} 不得由 secret_holder={holder} 说（除非自补偿）"
        return None
    if speech_act in FACT_ECHO_ACTS:
        # 回声/回旋镖：claim_role 须按当前说话人重标，不得沿用对方角色
        if claim_role:
            expected = str(fact.get(claim_role) or "")
            if expected and speaker != expected:
                return (
                    f"{speech_act} 的 claim_role={claim_role} 应归 {expected}，"
                    f"实为 {speaker}"
                )
        return None
    return None


def filter_fact_bound_rows(
    rows: list[Any] | None,
    facts: list[Any] | None,
) -> tuple[list[Any], list[str]]:
    """丢弃与事实角色绑定冲突的行；facts 为空时原样返回。"""
    index = fact_attribution_index(facts)
    if not index:
        return list(rows or []), []
    kept: list[Any] = []
    conflicts: list[str] = []
    for row in rows or []:
        if not isinstance(row, dict):
            kept.append(row)
            continue
        reason = fact_role_conflict_reason(row, index)
        if reason:
            label = str(row.get("intent") or row.get("line") or "")
            conflicts.append(f"{row.get('speaker')}:{label}（{reason}）")
            continue
        kept.append(row)
    return kept, conflicts


def fact_attribution_review_required(facts: list[Any] | None) -> bool:
    """事实归属未定稿即需复核：只有显式 ``resolved`` 才放行。

    只拦**真的做了归属**的事实（有 secret_holder/accuser/denier）：
    没有把柄、只是复述事件的空槽位条目不参与门控，避免误伤正常稿。
    无 facts 表示本稿不涉及「谁做过那件事」的角色槽位，不拦。
    """
    for item in facts or []:
        if not isinstance(item, dict):
            continue
        if not is_attribution_relevant_fact(item):
            continue
        status = str(item.get("attribution_status") or "").strip().lower()
        if status != "resolved":
            return True
    return False


def is_attribution_relevant_fact(fact: dict[str, Any]) -> bool:
    """该 fact 是否真的指定了行为人（否则只是事件复述，不参与门控）。"""
    if not isinstance(fact, dict):
        return False
    return any(
        str(fact.get(key) or "").strip()
        for key in ("secret_holder", "accuser", "denier")
    )


def fact_claim_alignment_notes(
    facts: list[Any] | None,
    rows: list[Any] | None,
) -> list[str]:
    """facts 声明了讨要方，却没有任何讨要/补偿拍时给出提示。

    facts 与 beat/seed 必须自洽：填了 ``claimant`` 就意味着源稿确有讨要动作，
    收束拍不得被省略；若源稿其实没有讨要，应把 ``claimant`` 写成 unknown，
    而不是留下悬空角色。``beneficiary`` 只标注得利方，不强制讨要拍。
    """
    claimants: list[tuple[str, str]] = []
    for item in facts or []:
        if not isinstance(item, dict):
            continue
        value = str(item.get("claimant") or "").strip()
        if value:
            fact_id = str(item.get("fact_id") or "").strip() or "?"
            claimants.append((fact_id, value))
    if not claimants:
        return []
    has_claim_row = False
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        act = str(row.get("speech_act") or "").strip().lower()
        if act in FACT_CLAIM_ACTS:
            has_claim_row = True
            break
    if has_claim_row:
        return []
    return [
        f"{fact_id} 声明 claimant={value}，但没有任何讨要/补偿拍"
        for fact_id, value in claimants[:2]
    ]


# 标题里的「被背着我」式抱怨：说话方是抱怨者/发现者，被抱怨方才是做过那件事的人
_TITLE_BACKSIDE_MARKER = re.compile(
    r"背着|瞒着|不告诉|没告诉|没叫|没带|偷偷|不喊|趁我"
)
_TITLE_CHILD_ROLE = re.compile(r"女儿|儿子|闺女|宝宝|孩子|小娃|弟弟|妹妹")
_TITLE_PARENT_ROLE = re.compile(r"妈妈|母亲|爸爸|父亲|家长|爹|娘")


def title_complaint_direction(video_title: str) -> str:
    """标题是否明示「孩子抱怨家长背着自己做事」。

    只读角色称谓与抱怨标记（不读剧情词）；命中时事实层应以标题为准：
    ``accuser/discoverer`` 是抱怨的孩子，``secret_holder`` 是家长。
    返回 ``"child_accuses_parent"`` / ``""``（无法判定）。
    """
    title = str(video_title or "")
    if not title:
        return ""
    if not _TITLE_BACKSIDE_MARKER.search(title):
        return ""
    if not _TITLE_CHILD_ROLE.search(title) or not _TITLE_PARENT_ROLE.search(title):
        return ""
    return "child_accuses_parent"


def fact_title_conflict_notes(
    facts: list[Any] | None,
    *,
    video_title: str,
    characters: list[Any] | None = None,
) -> list[str]:
    """facts 与标题抱怨方向矛盾时给出提示（标题为准）。"""
    if title_complaint_direction(video_title) != "child_accuses_parent":
        return []
    chars = {str(c).strip() for c in (characters or []) if str(c).strip()}
    kids = {c for c in chars if c in CHILD_SPEAKER_LABELS}
    parents = {
        p for p in PARENT_SPEAKER_LABELS if not chars or p in chars
    }
    if not kids or not parents:
        return []
    notes: list[str] = []
    for item in facts or []:
        if not isinstance(item, dict):
            continue
        holder = str(item.get("secret_holder") or "").strip()
        accuser = str(item.get("accuser") or "").strip()
        discoverer = str(item.get("discoverer") or "").strip()
        fact_id = str(item.get("fact_id") or "").strip() or "?"
        if holder in kids:
            notes.append(
                f"{fact_id} 标题表明抱怨方是孩子，secret_holder 不应是 {holder}"
            )
        if (accuser and accuser not in kids) or (
            discoverer and discoverer not in kids
        ):
            notes.append(
                f"{fact_id} 标题表明抱怨方是孩子，accuser/discoverer 应是孩子"
            )
    return notes


def mark_facts_ambiguous(
    facts: list[Any] | None,
    *,
    reason: str,
) -> tuple[list[Any], bool]:
    """把未定稿事实标成 ambiguous，交由复核门控拦截，不硬改角色。"""
    out: list[Any] = []
    changed = False
    for item in facts or []:
        if not isinstance(item, dict):
            out.append(item)
            continue
        fact = dict(item)
        if str(fact.get("attribution_status") or "").strip().lower() == "resolved":
            fact["attribution_status"] = "ambiguous"
            basis = fact.get("attribution_basis")
            basis_list = [str(b) for b in basis] if isinstance(basis, list) else []
            if reason and reason not in basis_list:
                basis_list.append(reason)
            fact["attribution_basis"] = basis_list
            changed = True
        out.append(fact)
    return out, changed
