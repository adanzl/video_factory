"""gold_chat 扩写 / 精修提示词模板。"""

from typing import Any

from app.services.daily_story.dialogue_text import DAILY_STORY_LINE_CHARS_MAX
from app.services.daily_story.prompts import (
    DAILY_STORY_BODY_CHARS_MAX,
    DAILY_STORY_BODY_CHARS_MIN,
    DAILY_STORY_KEY_CHARS_MAX,
    DAILY_STORY_KEY_CHARS_MIN,
)
from app.services.daily_story.gold_story.gold_chat.validate import (
    _BANNED_INVENTED_CLOSES,
    _parse_conflict_victim,
    _parse_fight_question_asker,
    _sibling_partner,
    collect_align_issues,
    align_chain,
    is_structural_align_kind,
)

CHAT_MAX_LINE_CHARS = DAILY_STORY_LINE_CHARS_MAX
# 提示词软目标：低于硬卡上限，避免顶着 370 写爆
CHARS_SOFT_LO = DAILY_STORY_BODY_CHARS_MIN + 40  # 280
CHARS_SOFT_HI = DAILY_STORY_BODY_CHARS_MAX - 30  # 340
DIALOGUE_ROUNDS_SOFT_LO = 12
DIALOGUE_ROUNDS_SOFT_HI = 16
DIALOGUE_ROUNDS_HARD_MAX = 18

_SYSTEM = (
    "你是日常故事编剧。输入为金故事 scene_contract（可拍场景契约）"
    "与 dialogue_seed intent，扩写成昭昭(7岁弟)/灿灿(10岁姐)可拍对白剧本。\n"
    "站外口播/科普/第三人称论述须 **还原成第一人称现场对白**："
    "角色当场说、当场吵、当场做，禁止转述「妈妈说/教过/曾经」。\n"
    "站外爸爸/父亲/宝爸须写为妈妈（少出场）；speaker 只允许昭昭/灿灿/妈妈。\n"
    "只输出一个合法 JSON 对象：无解释、无注释、无 markdown 代码围栏。\n"
    "输出 JSON 须与站内 daily_story 字段一致。\n"
    "**输出预算**：先保证正文 ≥240 字（目标 280–340），"
    "dialogue 约 12–16 条后闭合；禁止复读/草稿并列/循环加戏。"
)

_USER = """金故事标题：{title}
机制/结构：{mechanism} / {structure_type}（{structure_label}）
冲突核：{conflict_core}

{scene_contract_block}

{role_binding_block}

{beat_sequence_block}

{m5_h_beat_block}

{pass1_feedback_block}

dialogue_seed（剧情要点，不是最终台词）：
{dialogue_seed}

{seed_span_block}

收束意图（只落实要点，勿把说明整段写进对白）：{closing_intent}
映射说明：{speaker_map_note}
story_raw（背景，勿照抄；口播/论述须转现场对白）：{story_raw}
禁词（对白中禁止出现）：{banned_literals}
funny_why：{funny_why}
source_type：{source_type}（tutorial 时禁保留教程口吻/第几招）
{structure_hint}
{align_block}

{gold_chat_snippet}

输出 JSON：
{{
  "scene_title": "短标题，口语钩子；用词须在对白/正文中原样出现，禁自创与正文不一致的说法",
  "setting": "地点 + 冲突物落点（谁面前/谁端着哪件）",
  "key": "{key_min}-{key_max}字内容标签",
  "conflict_core": "一句话冲突核",
  "dialogue": [
    {{"speaker": "昭昭|灿灿|妈妈", "line": "…"}}
  ],
  "punchline_explain": "{structure_type}类…"
}}

规则：
- **扣题（硬卡）**：金故事标题「{title}」的核心词须在对白中自然出现至少一处；
  scene_title 须与标题同调，禁正文完全跑题
- **字数硬卡（最优先）**：正文 dialogue 总字数必须 ≥{chars_min} 且 ≤{chars_max}；
  目标落在 {chars_soft_lo}–{chars_soft_hi}。**未满 {chars_min} 禁止收束闭合**
- **句数**：对白宜 {rounds_soft_lo}–{rounds_soft_hi} 轮，最多 {rounds_hard_max} 轮；
  禁止循环复读注水；不够字数时用**beat 相关实词**句内扩写或必要反应句补满，
  禁灌尾巴（「你给我听好了/这回算清楚/别再装傻/说了就不改」等）
- **收束时机**：字数已 ≥{chars_min} 且冲突按 closing 落实后立刻闭合；
  禁止超过 {chars_max}，禁止顶着上限注水
- **单句** ≤{max_line} 字，**宜 16–22 字**（过短难满 240 总字）；**key** 须 {key_min}–{key_max} 字；
  **punchline_explain 必填**，含「{structure_type}类」前缀，宜短
- **seed**：通常每条扩 1–2 句；可保留关键词，禁止逐字照抄；
  禁止一条 seed 改写成多版本/草稿并列；
  **seed 专属动作/口号须由 seed 标注 speaker 来说**（禁角色对调）
- **seed 收束**：全部拍写完且 closing 落实后即停；禁止另起第二轮；
  禁止同一句对白重复循环凑字数
- **setting**：地点 + 冲突物落点（谁面前/谁端着哪件）；双方各持一物须两件都写；禁止只写地点和「在吵架」
- **第一人称现场对白**：每句是角色对另一角色当场说的话；禁第三人称论述、禁转述（「妈妈说/教过/说过」）
- 口播/育儿科普/「第几招」：选一个具体场面演出来，勿保留教程口吻
- 严格按 scene_contract.beat_chain **与上方事件顺序硬约束、金稿对齐 checklist** 顺序推进；妈妈台词 ≤ mom_lines_max
- **互毁段**：「也/还+撕/弄坏+你的」须由受害方说，且先毁方已实质破坏；speaker 不得调序
- **M5 妈妈前**：须两拍嘴硬（拒和 + 加码），与是否道歉无关；禁止妈妈一句「都错了」立刻和好
- **M5 角色绑定**：前文互毁/推搡锁定先动手方与受害方；服软/道歉与拒和/加码**不得同一 speaker**
- **M5 受害方**：scene conflict 受害方须 establish 持有物；先毁物/撕抢者≠受害方
- **H 调解**：妈妈须分层（先问谁先动手 → 再定责劝和），勿合并成一句；禁「扯平/都有错」
- **收束**：严格按 closing_intent 要点；「还打不打架」须由 closing_intent 指定角色问；碘伏/涂药后禁止新剧情（一起画/续写承诺）
- **句尾语气词**：每句结尾最多一个（呢/嘛/呀/啊/吧）；
  禁「了呢了呀/着呢了呀/呢呀」等叠尾；禁叠「呢呢」
- 若有上方金稿对白正例：语气/句长可参考；剧情须来自本稿 scene_contract + seed
- 昭昭/灿灿 交替为主，妈妈少出场；口语化、可拍
- **禁止对白出现「哥哥」「弟弟」**；称呼用姐姐/昭昭/灿灿
- 互毁须双向：先毁方实质弄坏/撕，受害方须**当场动手**报复（写撕了/撕啦/弄坏了），禁仅「那我也撕你的」口头威胁
- **齐声「不打了」**=昭昭一句+灿灿一句各应答，勿合并括号舞台说明
- line 禁止括号舞台说明（如「（从厨房走出来）」「（语塞）」）
- 站外爸爸/父亲/宝爸一律写妈妈，勿用爸爸作 speaker
- 站外陌生小孩/对方家长→映射为灿灿/妈妈，**禁止**「小男孩」「对方」等第三 speaker
- 按 beat 顺序推进，末段落实收束意图
- 禁止直接使用禁词列表里的词
- 不要输出 discovery_opening / quality 等额外字段
"""


_FIX_SYSTEM = (
    "你是日常故事编辑。根据校验错误修正 JSON。\n"
    "须改成第一人称现场对白：角色当场说，禁止转述/旁白/括号说明。\n"
    "speaker 只允许昭昭/灿灿/妈妈（爸爸/父亲须改为妈妈）。\n"
    "字数不足则扩写；字数超限则压缩（可删注水/复读句）；\n"
    "缺字段则补齐。只输出完整合法 JSON。"
)

_FIX_USER = """校验错误：
{errors}

当前 JSON：
{story_json}

规则：
- 正文 dialogue 总字数必须落在 {chars_min}–{chars_max}（目标 {chars_soft_lo}–{chars_soft_hi}）
- **未满 {chars_min}**：必须扩写到 ≥{chars_min}（句内加 **beat 相关实词**，
  禁「你给我听好了/这回算清楚/别再装傻」等灌尾；可加必要反应句，禁复读循环）
- **超过 {chars_max}**：压缩到上限内（可删注水句，勿另起第二轮）
- 对白宜 {rounds_soft_lo}–{rounds_soft_hi} 轮，最多 {rounds_hard_max} 轮；每句 ≤{max_line} 字
- key 须 {key_min}–{key_max} 字；缺 punchline_explain 须补且含类型前缀
- 妈妈台词须 ≤{mom_lines_max} 句；末句宜姐弟对白（非 hard）
- 若违反金稿对齐 checklist（跳步/自编暖收/互毁缺「也」的依据/M5 无加码），须按 checklist 补拍
- seed 专属短语须由 seed 标注 speaker 来说，禁角色对调
- 禁词须同义改写：{banned_literals}
- 转述/旁白/括号说明须改为当场对白
- speaker 非法须改为昭昭/灿灿/妈妈
只输出 JSON。"""

M8_J_BEAT_BUDGET_BLOCK = """【M8+J 篇幅 beat 预算（禁止 1:1 扩 seed）】
| beat | 句数 | 字数 | 备注 |
| 扭打/压制 | 2–3 | 55–75 | 动作短句，可含拟声/反应 |
| 立规/谁赢谁说了算 | 2 | 40–55 | 明确规则，可互顶 |
| 应战/互顶 | 3 | 65–85 | 核心扩写区，可成对出现 |
| 一锤定音 | 1–2 | 25–45 | 短促，不拖泥带水 |
| 认输/收束 | 2 | 35–55 | 收束，禁止新增对抗 |
| 合计 | 12–14 | 260–340 | 优先保句数 |

硬约束：
- 禁止 1:1 扩写 seed；中段互顶/立规/应战须各加码 1–2 句
- 认输后不得出现新的对抗、威胁、反驳、不服、再来一回合
- 每句 ≤24 字；禁止灌尾巴凑字"""

_M8_J_MID_REWRITE_SYSTEM = (
    "你是 M8+J 日常故事编辑。须保留开头扭打段和结尾认输段，"
    "只重写中段「立规→应战→一锤」对白。\n"
    "speaker 只允许昭昭/灿灿/妈妈。只输出完整合法 JSON。"
)

_M8_J_MID_REWRITE_USER = """任务：保留首尾，重写中段以补满篇幅。

保留开头（不得改动 speaker/句序/大意）：
{head_json}

保留结尾认输段（不得改动；认输后禁止新增对抗/不服/再来）：
{tail_json}

当前中段（可整体替换）：
{mid_json}

要求：
- 中段须写满「立规/谁赢谁说了算→互顶应战→一锤定音」
- 中段『立规→应战→一锤』共需 120–160 字（占全文 50–67%）；禁止在首尾垫字
- 中段新增 2–3 组互顶/应战对白（每组 2 句），每句 ≤{max_line} 字
- 全文 dialogue 总字数须 ≥{chars_min}（目标 {chars_soft_lo}–{chars_soft_hi}）
- 认输段句数不增加；认输后禁止不服/再来/威胁
- 禁词：{banned_literals}

当前 JSON（只改 dialogue，其余字段保持）：
{story_json}

只输出 JSON。"""

_ALIGN_REFINE_SYSTEM = (
    "你是 gold_chat 类型对齐精修编辑。只改被点到的对白行，其余字段与行数不动。\n"
    "须落实金稿对齐 checklist；M5 立规用「家规/规矩/规定」，勿写「妈妈说过」类转述。\n"
    "互毁：报复句之前须 establish 双方物/作品；改机审标定行，"
    "禁止把前文合并进「也/还弄坏」同一句。\n"
    "M5 立规/拒和/加码各占一句，禁止一句三连；"
    "拆句时须保留拒和与加码各一句且在妈妈前（与是否道歉无关）。\n"
    "修复不得减少正文总字数、不得删句；不足则在句内扩写。\n"
    "收场严格按 closing_intent，不发明帮拿/搀扶等新动作；"
    "碘伏/涂药后禁止续写新剧情；「还打不打架」speaker 须与 closing_intent 一致。\n"
    "末 4 句须有拉手或齐声「不打了」。\n"
    "只输出 JSON：{\"fixes\":[{\"no\":行号,\"line\":\"改好后的一句\"}]}"
)

_ALIGN_REFINE_USER = """对齐机审问题（只改标定行）：
{issues_block}

{align_block}

当前 JSON（dialogue 节选）：
{story_json}

硬约束：
- 只改上方标定行号；行数、speaker 不变；每句 ≤{max_line} 字
- **不得减少正文总字数、不得删句**；改句后总字数仍须 ≥{chars_min}
- **保真-互毁**：在报复句**之前**的句 establish 破坏依据（抢坏/弄坏）与对方也有该物
  （如「我画…你的画呢」）；报复句可保留，勿合并成一句
- **保真-M5合并/保真-M5加码**：立规、拒和、加码须分句且在妈妈介入前各至少一句
- **保真-和好**：末 4 句补「拉手」或姐弟齐声「不打了」
- **保真-M5拒和speaker**：若已有服软/道歉，拒和/加码须另一方说
- **保真-对象持有补丁**：勿用「我也有你的X」单独补丁互毁对象
- **保真-收场Invent**：删 closing_intent 外的帮忙/搀扶/回来/不疼了等，收成短应答
- **保真-收场拖句**：碘伏/涂药后多余句**可删**；删后总字数仍须 ≥{chars_min}；残句改完整或删
- **保真-齐声问句**：「还打不打架」改 closing_intent 指定角色问；删重复问句
- **保真-H定责**：妈妈分层定责，禁「扯平/都有错」；先点先动手方再劝和
- 正文总字数 {chars_min}–{chars_max}；妈妈台词 ≤{mom_lines_max} 句；末句宜姐弟对白
- 禁词须同义改写：{banned_literals}
- line 只写台词，不带说话人前缀；禁括号说明
只输出 fixes JSON。"""

_SHORTEN_SYSTEM = (
    "你是 gold_chat 缩句编辑。只缩短超长对白行，语义与 speaker 不变。\n"
    f"每句须 ≤{CHAT_MAX_LINE_CHARS} 字。只输出完整 JSON。"
)

_SHORTEN_USER = """以下对白有单句超过 {max_chars} 字，请**只改超长行**（删冗余词/语气词，勿改剧情）：
{long_lines}

当前 JSON：
{story_json}

规则：行数、speaker、字段不变；每句 ≤{max_chars} 字；禁括号说明。
只输出 JSON。"""


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
    from app.services.daily_story.gold_story.scene import format_beat_chain

    mech = str(mechanism or "").strip().upper()
    st = str(structure_type or "").strip().upper()
    victim = _parse_conflict_victim(conflict_text)

    parts = [
        "【事件顺序硬约束 · 对白须逐步落实，禁止跳步/调序/speaker 互换】",
    ]
    chain_text = format_beat_chain(beat_chain)  # type: ignore[arg-type,union-attr,assignment]
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


def format_m8_j_beat_budget_block(
    *,
    mechanism: str = "",
    structure_type: str = "",
) -> str:
    from app.services.daily_story.gold_story.gold_chat.type_bridge import (
        is_m8_j_domination,
    )

    if not is_m8_j_domination(
        mechanism=mechanism,
        structure_type=structure_type,
    ):
        return ""
    return M8_J_BEAT_BUDGET_BLOCK


def format_pass1_regen_feedback(
    error: str,
    story: dict[str, Any] | None,
    *,
    structure_type: str,
    mechanism: str,
    closing_intent: str = "",
    beat_chain: list[Any] | None = None,
    conflict_text: str = "",
    short_regen_count: int = 0,
) -> str:
    """Pass1 重试：把上一轮失败原因注入 prompt。"""
    err = str(error or "").strip()
    if not err:
        return ""
    if err.startswith("structure_score:"):
        return format_structure_score_feedback(err, story)

    if err.startswith(("align_structural:", "align_refine_failed:")):
        issues: list[dict[str, Any]] = []
        if isinstance(story, dict):
            raw = collect_align_issues(
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
                if is_structural_align_kind(str(x.get("kind") or ""))
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

    # 硬校验失败（字数/缺字段/单句过长等）也回灌，避免同提示空转
    from app.services.daily_story.gold_story.gold_chat.type_bridge import (
        is_m8_j_domination,
    )

    parts = ["【上一轮 Pass1 硬校验失败 · 本轮须一次写对】", f"错误：{err[:400]}"]
    if "正文总字数须≥" in err:
        parts.append(
            f"- 正文必须先写满 ≥{DAILY_STORY_BODY_CHARS_MIN} 字，"
            f"目标 {CHARS_SOFT_LO}–{CHARS_SOFT_HI}；未满禁止收束；"
            "禁灌「你给我听好了/这回算清楚」尾巴"
        )
    if "对白句数须≥" in err or "句数须≥" in err:
        if is_m8_j_domination(mechanism=mechanism, structure_type=structure_type):
            parts.append(
                f"- 对白必须 ≥{DIALOGUE_ROUNDS_SOFT_LO} 句；"
                "M8+J：中段加「互顶/立规/应战」各 1–2 句，"
                "勿只把 seed 短句 1:1 扩完；禁止提早收束"
            )
        else:
            parts.append(
                f"- 对白必须 ≥{DIALOGUE_ROUNDS_SOFT_LO} 句；"
                "seed 1:1 扩完不够时，中段加「哀求/加码+否决」来回；"
                "禁止提早收束"
            )
    m8_j = is_m8_j_domination(mechanism=mechanism, structure_type=structure_type)
    if m8_j and _is_short_content_feedback_error(err):
        parts.append(format_m8_j_beat_budget_block(
            mechanism=mechanism,
            structure_type=structure_type,
        ))
        if short_regen_count >= 3:
            parts.extend(
                [
                    "- **第 3 次重试：强制中段重写**",
                    "- 保留开头扭打段与结尾认输段不动",
                    "- 只重写「立规→应战→一锤」中段，插入 2–3 组互顶/应战对",
                    "- 认输后禁止不服/再来/威胁；禁止尾部灌水",
                ]
            )
        elif short_regen_count >= 2:
            parts.extend(
                [
                    "- **第 2 次重试：中段 beat 不足**",
                    "- 立规/应战段各须再加 1–2 句互顶对白",
                    "- 禁止在认输后加戏；禁止 1:1 扩 seed",
                ]
            )
        elif "正文总字数须≥" in err:
            parts.append(
                "- M8+J：扭打互顶→立规谁赢谁说了算→应战挑衅→一锤取胜→认输收场；"
                "每句宜 16–22 字写满 beat，禁止只扩 seed 短句就停"
            )
    if "正文总字数须≤" in err:
        parts.append(
            f"- 正文不得超过 {DAILY_STORY_BODY_CHARS_MAX} 字；删注水/复读，勿顶上限"
        )
    if "punchline_explain" in err:
        parts.append("- 必须含 punchline_explain，且带类型前缀")
    if "key 须" in err:
        parts.append("- key 须 2–8 字")
    if "单句过长" in err:
        parts.append(f"- 每句 ≤{CHAT_MAX_LINE_CHARS} 字")
    if "finish_reason=length" in err or "truncated" in err:
        parts.extend(
            [
                "- 上次输出过长被截断：禁止复读/草稿并列/循环加戏",
                f"- 仍须写满 ≥{DAILY_STORY_BODY_CHARS_MIN} 字"
                f"（目标 {CHARS_SOFT_LO}–{CHARS_SOFT_HI}），未满禁止收束",
                f"- dialogue 宜 {DIALOGUE_ROUNDS_SOFT_LO}–"
                f"{DIALOGUE_ROUNDS_SOFT_HI} 条"
                f"（≤{DIALOGUE_ROUNDS_HARD_MAX}）",
                "- 每条 seed 通常扩 1–2 句；写完 beat+closing 立刻闭合",
            ]
        )
    return "\n".join(parts)


def _is_short_content_feedback_error(err: str) -> bool:
    return (
        "正文总字数须≥" in err
        or "dialogue 至少" in err
        or "对白句数须≥" in err
    )


def format_structure_score_feedback(
    error: str,
    story: dict[str, Any] | None,
) -> str:
    """Pass1 重试：上一轮结构分未过线时的修订指令。"""
    from app.services.daily_story.quality import (
        STRUCTURE_PUBLISH_MIN,
        build_quality_revision_hints,
        structure_score_of,
    )

    err = str(error or "").strip()
    score_txt = err.split(":", 1)[-1] if ":" in err else err
    parts = [
        f"【上一轮结构分未过线（须≥{STRUCTURE_PUBLISH_MIN}）· 本轮抬结构】",
        f"机审：结构分 {score_txt}",
    ]
    if isinstance(story, dict):
        quality = story.get("quality") if isinstance(story.get("quality"), dict) else {}
        struct = structure_score_of(quality)
        if struct:
            parts.append(f"当前结构分：{struct}")
        cons = [
            str(r)
            for r in (quality.get("reasons") or [])  # type: ignore[arg-type,union-attr,assignment]
            if any(
                str(r).startswith(p) or p in str(r)
                for p in ("缺", "未", "拖", "不足", "勿", "过", "偏", "跑题", "-")
            )
        ][:5]
        for c in cons:
            parts.append(f"- {c}")
        hints = build_quality_revision_hints(quality, story=story).strip()  # type: ignore[arg-type,union-attr,assignment]
        if hints:
            parts.append(hints[:500])
    parts.append("禁止另起第二轮；收束槽位落在末段后即停。")
    return "\n".join(parts)


def format_seed_span_block(
    seed: list[Any] | None,
    *,
    structure_type: str = "",
    mechanism: str = "",
) -> str:
    """seed 条数不足 12 时，强制提示中段加码扩句，禁止 1:1 扩完就停。"""
    from app.services.daily_story.gold_story.gold_chat.type_bridge import (
        is_m8_j_domination,
    )
    from app.services.daily_story.gold_story.scene import CHAT_LINE_COUNT_MIN
    from app.services.daily_story.prompts import DAILY_STORY_BODY_CHARS_MIN

    m8_j = is_m8_j_domination(
        mechanism=mechanism,
        structure_type=structure_type,
    )
    n = 0
    for item in seed or []:
        if isinstance(item, dict) and (
            str(item.get("intent") or item.get("line") or "").strip()
        ):
            n += 1
        elif str(item or "").strip():
            n += 1
    need_lines = max(0, CHAT_LINE_COUNT_MIN - n)
    parts = [
        f"【篇幅硬卡】dialogue_seed 共 {n} 条；"
        f"正文必须 ≥{CHAT_LINE_COUNT_MIN} 句且 ≥{DAILY_STORY_BODY_CHARS_MIN} 字"
        f"（目标 280–340）；每句宜 16–22 字，禁灌尾巴凑字。",
    ]
    if need_lines > 0:
        if m8_j:
            parts.append(
                f"seed 少于 {CHAT_LINE_COUNT_MIN}：中段至少把 {need_lines} 条"
                "扩成「互顶/立规/应战」各 1–2 句（扭打升级、重申谁赢谁说了算、"
                "挑衅要对方出招），共补 ≥"
                f"{need_lines} 句；禁止 seed 1:1 短句扩完就停；"
                "禁止灌尾巴（你给我听好了/这回算清楚等）凑字。"
            )
        else:
            parts.append(
                f"seed 少于 {CHAT_LINE_COUNT_MIN}：中段至少把 {need_lines} 条"
                "扩成「哀求/加码 + 否决」两句（共补 ≥"
                f"{need_lines} 句），禁止 seed 1:1 扩完就停；"
                "禁止灌尾巴（你给我听好了/这回算清楚等）凑字。"
            )
    else:
        parts.append(
            "禁止提早收束；句内用 beat 实词写满字数，禁灌尾巴凑字。"
        )
    beat_budget = format_m8_j_beat_budget_block(
        mechanism=mechanism,
        structure_type=structure_type,
    )
    if beat_budget:
        parts.extend(["", beat_budget])
    return "\n".join(parts)


def format_story_beats(beat: list[Any] | None) -> str:
    lines: list[str] = []
    for i, item in enumerate(beat or [], start=1):
        text = str(item or "").strip()
        if text:
            lines.append(f"{i}. {text}")
    return "\n".join(lines) if lines else "（无 beat 摘要）"


def format_align_block(
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
    chain = align_chain(structure_type=st, mechanism=mech)

    parts = [
        "【金稿对齐 checklist · 扩写时逐步落实，禁止跳步】",
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


def format_align_issues_block(issues: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for item in issues:
        nos = "、".join(str(n) for n in item.get("lines") or [])
        lines.append(
            f"- 第{nos}句 [{item.get('kind')}]: {item.get('desc')}\n"
            f"  改法：{item.get('fix')}"
        )
    return "\n".join(lines) if lines else "（无）"
