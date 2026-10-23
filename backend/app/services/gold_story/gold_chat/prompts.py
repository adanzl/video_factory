"""gold_chat 扩写/ 精修提示词模板。"""

import json
import re
from typing import Any

from app.services.daily_story.dialogue_text import DAILY_STORY_LINE_CHARS_MAX
from app.services.daily_story.prompts import (
    DAILY_STORY_BODY_CHARS_MAX,
    DAILY_STORY_BODY_CHARS_MIN,
    DAILY_STORY_KEY_CHARS_MAX,
    DAILY_STORY_KEY_CHARS_MIN,
)
from app.services.gold_story.gold_chat.validate import (
    _BANNED_INVENTED_CLOSES,
    _parse_conflict_propaganda_roles,
    _parse_conflict_victim,
    _parse_fight_question_asker,
    _sibling_partner,
    collect_align_issues,
    align_chain,
    is_structural_align_kind,
)

CHAT_MAX_LINE_CHARS = DAILY_STORY_LINE_CHARS_MAX
# ── 句长的唯一权威口径 ──────────────────────────────────────────────────
# 出厂设定：正文 240 字靠「句数 × 句长」凑，句长落在这个区间最容易同时满足
# 「儿童口语化」和「够字数」。此前这个数在提示词里有三套写法
# （18–22 / 16–22 / 12–18），模型每轮按哪套写全看运气，字数与句数的账
# 自然对不上。所有提示词一律引用这两个常量，禁止再写字面区间。
SAFE_LINE_CHARS_LO = 18
SAFE_LINE_CHARS_HI = 22
SAFE_LINE_CHARS_HINT = f"{SAFE_LINE_CHARS_LO}–{SAFE_LINE_CHARS_HI} 字"
# 提示词软目标：低于硬卡上限，避免顶着 370 写爆
CHARS_SOFT_LO = DAILY_STORY_BODY_CHARS_MIN + 40  # 280
CHARS_SOFT_HI = DAILY_STORY_BODY_CHARS_MAX - 30  # 340
DIALOGUE_ROUNDS_SOFT_LO = 12
DIALOGUE_ROUNDS_SOFT_HI = 16
DIALOGUE_ROUNDS_HARD_MAX = 18

# 否定前缀：避免「不和好」误触发「和好」规则
_RE_NEG_BEFORE = re.compile(r"(?:不|勿|别|没|无|非|禁|莫)[\u4e00-\u9fff]{0,2}$")
_MOM_ABSENT_MARKERS = (
    "妈妈不出场",
    "妈妈不介入",
    "家长不出场",
    "大人不出场",
    "妈妈不在场",
)
_RECONCILE_DENY_MARKERS = (
    "不和好",
    "勿和好",
    "别和好",
    "禁止和好",
    "无需和好",
    "不要和好",
)


def _token_affirmed(text: str, token: str) -> bool:
    """token 出现且局部无否定前缀；「不打了」整词视为肯定收束。"""
    raw = str(text or "")
    if not token or not raw:
        return False
    if token == "不打了":
        return "不打了" in raw
    start = 0
    while True:
        i = raw.find(token, start)
        if i < 0:
            return False
        prefix = raw[max(0, i - 4) : i]
        if _RE_NEG_BEFORE.search(prefix):
            start = i + len(token)
            continue
        return True


def _any_token_affirmed(text: str, tokens: tuple[str, ...]) -> bool:
    return any(_token_affirmed(text, t) for t in tokens)


def _reconcile_wanted(
    *,
    structure_type: str,
    closing_intent: str = "",
    conflict_text: str = "",
) -> bool:
    """是否需要仪式性和好；以 closing_intent 为准，中段拒和不当全篇禁止。"""
    st = str(structure_type or "").strip().upper()
    closing = str(closing_intent or "").strip()
    conflict = str(conflict_text or "").strip()
    if closing:
        # 结尾明确禁止 → 关；结尾明确和好/拉手 → 开
        if any(m in closing for m in _RECONCILE_DENY_MARKERS):
            return False
        if _any_token_affirmed(
            closing, ("和好", "拉手", "不打了", "劝和", "调解")
        ):
            return True
        # 收束未谈和好：H 默认真好；其余不因 conflict 中段「不和好」关掉
        return st == "H"
    # 无收束文案时：H 默认开；否则只认 conflict 的肯定表述（不认中段否定）
    if st == "H":
        return True
    return _any_token_affirmed(
        conflict, ("和好", "拉手", "不打了", "劝和", "调解")
    )


def _mom_adjudicate_wanted(
    *,
    structure_type: str,
    closing_intent: str = "",
    conflict_text: str = "",
) -> bool:
    """是否需要妈妈定责；缺席声明与肯定要求均优先看 closing_intent。"""
    st = str(structure_type or "").strip().upper()
    closing = str(closing_intent or "").strip()
    conflict = str(conflict_text or "").strip()
    if closing:
        if any(m in closing for m in _MOM_ABSENT_MARKERS):
            return False
        if _any_token_affirmed(
            closing, ("调解", "劝和", "定责", "妈妈介入", "妈妈定责")
        ):
            return True
        return st == "H"
    if any(m in conflict for m in _MOM_ABSENT_MARKERS):
        return False
    if st == "H":
        return True
    return _any_token_affirmed(
        conflict, ("调解", "劝和", "定责", "妈妈介入", "妈妈定责")
    )

_SYSTEM = (
    "你是日常故事编剧。输入为金故事 scene_contract（可拍场景契约）"
    "与 dialogue_seed intent，扩写成**契约在场人物**的可拍对白剧本"
    "（人物与人数一律以【出场角色】块为准，不得沿用其它题材的常见组合）。\n"
    "站外口播/科普/第三人称论述须 **还原成第一人称现场对白**："
    "角色当场说、当场吵、当场做，禁止转述「妈妈说/教过/曾经」。\n"
    "家长：能用妈妈就用妈妈；源稿是爸爸且妈妈代不了时保留「爸爸」；"
    "speaker **只能用【出场角色】块里列出的那些**，"
    "未列出的角色一律不许出场（禁补旁观手足凑戏）。\n"
    "**人数按契约定**：契约只给一个孩子时写家长×孩子两人手；"
    "契约给了两个孩子才写双孩同侧；戏核家长（责备/反问/定责/破功）须按 beat 出场，"
    "**禁止**压成两人并台词。\n"
    "学段与分数须贴 7–10 岁小学量级；禁止沿用中考/高考不可能总分。\n"
    "只输出一个合法 JSON 对象：无解释、无注释、无 markdown 代码围栏。\n"
    "输出 JSON 须与站内 daily_story 字段一致。\n"
    "**输出预算**：先保证正文 ≥240 字（目标 280–340），"
    "dialogue 约 14 条后闭合，每句 " + SAFE_LINE_CHARS_HINT + "（靠句长凑 240 字，不靠重复注水）；"
    "禁止复读/草稿并列/循环加戏。\n"
    "seed 是压缩素材，不是完整事件表：同一说话人、同一质问/态度的换词复述只落一次；"
    "story_raw 里已有、但 seed 被压缩掉的请求/前因若被后文回答或拒绝，必须先落地该请求。\n"
    "句数不足时按“请求/追问 + 对方回答/反应”的话轮对扩写，"
    "不得用同一角色连续自我表态凑句数。"
)

_USER = """金故事标题：{title}
机制/结构：{mechanism} / {structure_type}（{structure_label}）
冲突核：{conflict_core}

{cast_block}

{scene_contract_block}

{role_binding_block}

{beat_sequence_block}

{m5_h_beat_block}

{expand_feedback_block}

{retry_missing_events_block}

dialogue_seed（剧情要点，不是最终台词）：
{dialogue_seed}

{seed_span_block}

{seed_skeleton_block}

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
    {{"speaker": "【出场角色】里的某个名字", "line": "…"}}
  ],
  "punchline_explain": "{structure_type}类…"
}}

规则：
- **扣题（硬卡）**：金故事标题「{title}」的核心事件须在对白中自然出现；
  scene_title 须与对白人物同调。若源标题人物未进对白（如妈妈被映射成灿灿/姐姐），
  scene_title/key/conflict_core 必须按对白改写，禁止沿用「怼妈」这类对不上的源标题
- **元数据跟契约**：conflict_core / scene_title / key 须与 scene_contract
  （含迁龄后的分数、学段、人物）一致；禁止把站外旧分数/旧称谓写进元数据
- **字数硬卡（最优先）**：正文 dialogue 总字数必须 ≥{chars_min} 且 ≤{chars_max}；
  目标落在 {chars_soft_lo}–{chars_soft_hi}。**未满 {chars_min} 禁止收束闭合**
- **句数**：对白宜 {rounds_soft_lo}–{rounds_soft_hi} 轮，最多 {rounds_hard_max} 轮；
  禁止循环复读注水；不够字数时用**beat 相关实词**句内扩写或必要反应句补满，
  禁灌尾巴（「你给我听好了/这回算清楚/别再装傻/说了就不改」等）
- **收束时机**：字数已 ≥{chars_min} 且冲突按 closing 落实后立刻闭合；
  禁止超过 {chars_max}，禁止顶着上限注水
- **单句** ≤{max_line} 字，**宜 {safe_lo}–{safe_hi} 字**（过短难满 240 总字）；**key** 须 {key_min}–{key_max} 字；
  **punchline_explain 必填**，含「{structure_type}类」前缀，宜短
- **seed**：通常每条扩 1–2 句；可保留关键词，禁止逐字照抄；
  禁止一条 seed 改写成多版本/草稿并列；
  **seed 专属动作/口号须由 seed 标注 speaker 来说**（禁角色对调）
- **seed 收束**：全部拍写完且 closing 落实后即停；禁止另起第二轮；
  禁止同一句对白重复循环凑字数
- **setting**：地点 + 冲突物落点（谁面前/谁端着哪件）；双方各持一物须两件都写；禁止只写地点和「在吵架」
- **第一人称现场对白**：每句是角色对另一角色当场说的话；禁第三人称论述、禁转述（「妈妈说/教过/说过」）；
  在场姐弟互指用「你」或名字，禁止「她/他」旁白式转述对方分数或行为
- **开场因果（硬）**：先让观众从**可见对白**理解冲突的触发事件，再出现回应或解围；
  不得只保留回应、删除其依赖的前提；**setting 不算**已向观众交代。
  不强制妈妈首句，也不要求机械复制第一拍，但 beat 中的触发须在对白里可感知。
- 口播/育儿科普/「第几招」：选一个具体场面演出来，勿保留教程口吻
- 严格按 scene_contract.beat_chain **与上方事件顺序硬约束、金稿对齐 checklist** 顺序推进；妈妈台词 ≤ mom_lines_max
- **金稿正例防串**：语气/句长可参考正例；**禁止**把正例的 object/口号/冲突核
  抄进本稿（本稿 beat/object/seed 未出现的梗一律禁用）
- **禁空转**：禁止无新信息的复读句凑轮次（同义空喊连发）
- **禁垫字脏尾**：禁复合灌尾（「真的了呢」「不行了吧」叠「真的」一类）
{scenario_rules_block}
- **句尾语气词**：每句结尾最多一个（呢/嘛/呀/啊/吧）；
  禁「了呢了呀/着呢了呀/呢呀」等叠尾；禁叠「呢呢」
- 若有上方金稿对白正例：语气/句长可参考；剧情须来自本稿 scene_contract + seed
- 按【出场角色】块列出的角色交替；妈妈配角少台词，但 mom_lines_max≥1 或 beat 含家长时须按拍出场；
  爸爸更少（能用妈不用爸）；口语化、可拍
- **迁龄**：对白中的考试/分数须是小学 7–10 岁可拍量级；禁止中考/高考不可能总分原样入戏
- 称呼只用【出场角色】里的人名；**禁止**「哥哥」「弟弟」这类亲属称谓入戏
  （站外稿里的哥哥/弟弟按人物映射规则换成本稿人名，不要保留原称谓直呼）
- line 禁止括号舞台说明（如「（从厨房走出来）」「（语塞）」）
- 源稿是爸爸且妈妈代不了 → speaker 写「爸爸」；可替则优先妈妈
- 站外陌生小孩/对方家长→映射为【出场角色】里已有的成员，
  **禁止**「小男孩」「对方」等第三 speaker，也**禁止**在角色表外新增名字
- 按 beat 顺序推进，末段落实收束意图；beat 未写的新冲突线禁止另起
- 禁止直接使用禁词列表里的词
- 不要输出 discovery_opening / quality 等额外字段
"""


_FIX_SYSTEM = (
    "你是日常故事编辑。根据校验错误修正 JSON。\n"
    "须改成第一人称现场对白：角色当场说，禁止转述/旁白/括号说明。\n"
    "speaker 只能用【出场角色】块列出的人物（父亲/老爸/宝爸归一为爸爸；"
    "能用妈妈就用妈妈）；名单外角色一律不许新增。\n"
    "**但只能用【出场角色】块里列出的那些**：未列出的角色一律不许出场，"
    "也**不许**为了凑字数新增角色。\n"
    "字数不足则扩写；字数超限则压缩（可删注水/复读句）；\n"
    "缺字段则补齐。只输出完整合法 JSON。"
)

_FIX_USER = """校验错误：
{errors}

{cast_block}

当前 JSON：
{story_json}

规则：
- **出场角色（硬）**：speaker 必须在上方【出场角色】块列出的名单内；
  契约里没有拍的角色一律删除，禁止新增角色凑字数
- 正文 dialogue 总字数必须落在 {chars_min}–{chars_max}（目标 {chars_soft_lo}–{chars_soft_hi}）
- **未满 {chars_min}**：必须扩写到 ≥{chars_min}（句内加 **beat 相关实词**，
  禁「你给我听好了/这回算清楚/别再装傻」等灌尾；可加必要反应句，禁复读循环）
- **超过 {chars_max}**：压缩到上限内（可删注水句，勿另起第二轮）
- 对白宜 {rounds_soft_lo}–{rounds_soft_hi} 轮，最多 {rounds_hard_max} 轮；每句 ≤{max_line} 字
- key 须 {key_min}–{key_max} 字；缺 punchline_explain 须补且含类型前缀
- 妈妈台词须 ≤{mom_lines_max} 句；爸爸台词宜更少（≤1，能用妈不用爸）；末句宜姐弟对白（非 hard）
- 若违反金稿对齐 checklist（跳步/自编暖收/互毁缺「也」的依据/M5 无加码），须按 checklist 补拍
- seed 专属短语须由 seed 标注 speaker 来说，禁角色对调
- 禁词须同义改写：{banned_literals}
- 转述/旁白/括号说明须改为当场对白
- speaker 非法须改为【出场角色】里的人物；契约外角色须删除，禁止新增角色
- 复合垫字尾（真的了呢/不行了吧叠真的）须删干净
- conflict_core/scene_title 须与 scene_contract 迁龄后口径一致
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
    "speaker 只能用【出场角色】块列出的人物。只输出完整合法 JSON。"
)

_M8_J_MID_REWRITE_USER = """任务：保留首尾，重写中段以补满篇幅。

保留开头（不得改动 speaker/句序/大意）：
{head_json}

保留结尾认输段（不得改动；认输后禁止新增对抗/不服/再来）：
{tail_json}

当前中段（可整体替换）：
{mid_json}

要求：
- 中段须分 3 部分明确展开（禁止灌水）：
  1. 立规（2 句）：一方明确规则、另一方确认或反顶，每句 12–18 字
  2. 应战（4–5 句）：每句推进新的挑战、动作或局势，每句 16–22 字
  3. 一锤定音（2 句）：事实落定后立即判输赢，每句 12–18 字
- 中段『立规→应战→一锤』共需 120–160 字（占全文 50–67%）；禁止在首尾垫字
- 全文 dialogue 总字数须 ≥{chars_min}（目标 {chars_soft_lo}–{chars_soft_hi}）
- 认输段句数不增加；认输后禁止不服/再来/威胁
- 禁词：{banned_literals}

当前 JSON（只改 dialogue，其余字段保持）：
{story_json}

只输出 JSON。"""

_ALIGN_REFINE_SYSTEM_BASE = (
    "你是 gold_chat 类型对齐精修编辑。只改被点到的对白行，其余字段与行数不动。\n"
    "须落实金稿对齐 checklist。\n"
    "标定行可句内改短或扩写；全文总字数须落在硬卡区间内，"
    "改短后仍不得低于下限；不得删句、不得留空 line。\n"
    "收场严格按 closing_intent，不发明帮拿/搀扶等新动作；"
    "碘伏/涂药后禁止续写新剧情；「还打不打架」speaker 须与 closing_intent 一致。\n"
    "只输出 JSON：{\"fixes\":[{\"no\":行号,\"line\":\"改好后的一句\"}]}"
)

_ALIGN_REFINE_USER_BASE = """对齐机审问题（只改标定行）：
{issues_block}

{align_block}

当前 JSON（dialogue 节选）：
{story_json}

硬约束：
- 只改上方标定行号；**行数不变**；每句 ≤{max_line} 字
- **speaker 默认不变**；仅当问题是「末四拍/收束槽位错位」时，
  允许改标定行的 speaker（在该行 fixes 里同时给出 `"speaker":"出场角色里的人名"`），
  其余行一律不得改 speaker
- 标定行可句内**改短或扩写**；改后全文总字数须 **≥{chars_min} 且 ≤{chars_max}**
  （拖句改短时其他行不动，靠删冗余措辞，勿低于下限）；禁止留空 line、禁止删行
- **保真-收场Invent**：删 closing_intent 外的帮忙/搀扶/回来/不疼了等，收成短应答
- **保真-收场拖句**：碘伏/涂药后标定拖句须改短（句内删冗余），接口不支持删行
- 正文总字数 {chars_min}–{chars_max}；妈妈台词 ≤{mom_lines_max} 句；末句宜姐弟对白
- 禁词须同义改写：{banned_literals}
- line 只写台词，不带说话人前缀；禁括号说明
{type_constraints}
只输出 fixes JSON。"""


def format_align_refine_type_constraints(
    *,
    mechanism: str = "",
    structure_type: str = "",
    closing_intent: str = "",
    conflict_text: str = "",
) -> str:
    """精修阶段按机制/结构裁剪；与 format_scenario_rules_block 同口径。"""
    mech = str(mechanism or "").strip().upper()
    st = str(structure_type or "").strip().upper()
    context = " ".join(
        [
            str(conflict_text or ""),
            str(closing_intent or ""),
        ]
    )
    lines: list[str] = []
    need_mutual = mech == "M5" or _any_token_affirmed(
        context, ("互毁", "撕坏", "弄坏", "推搡")
    )
    need_m5 = mech == "M5"
    need_reconcile = _reconcile_wanted(
        structure_type=st,
        closing_intent=closing_intent,
        conflict_text=conflict_text,
    )
    need_mom = _mom_adjudicate_wanted(
        structure_type=st,
        closing_intent=closing_intent,
        conflict_text=conflict_text,
    )
    need_fight_q = "还打不打架" in context or bool(
        _parse_fight_question_asker(closing_intent)
    )
    need_iodine = _any_token_affirmed(
        context, ("碘伏", "涂药", "上药", "包扎")
    )

    if need_mutual:
        lines.extend(
            [
                "- **保真-互毁**：在报复句**之前**的句 establish 破坏依据（抢坏/弄坏）"
                "与对方也有该物（如「我画…你的画呢」）；报复句可保留，勿合并成一句",
                "- **保真-对象持有补丁**：勿用「我也有你的X」单独补丁互毁对象",
            ]
        )
    if need_m5:
        lines.extend(
            [
                "- **保真-M5合并/保真-M5加码**：立规、拒和、加码须分句且在妈妈介入前"
                "各至少一句",
                "- **保真-M5拒和speaker**：若已有服软/道歉，拒和/加码须另一方说",
            ]
        )
    if need_reconcile:
        lines.append(
            "- **保真-和好**：仅当 closing_intent 要求时，末 4 句补「拉手」"
            "或姐弟齐声「不打了」；勿擅自套到无和好契约的类型"
        )
    if need_fight_q:
        lines.append(
            "- **保真-齐声问句**：「还打不打架」改 closing_intent 指定角色问；"
            "删重复问句"
        )
    if need_mom:
        lines.append(
            "- **保真-H定责**：妈妈分层定责，禁「扯平/都有错」；先点先动手方再劝和"
        )
    if need_iodine:
        lines.append(
            "- **保真-上药**：上药完成即收束，之后禁止另起一起画、拉钩等新剧情"
        )
    if st == "A":
        # 末四拍槽位错位无法靠改文本修（说话人就是错的），故显式解冻 speaker
        lines.append(
            "- **A类末四拍（可改 speaker）**：末 4 句须按"
            "「挑战方→权威方→挑战方→权威方」交替，语义依次为"
            "引原话→给具体例外→追问例外→软破功；"
            "**挑战方是跟大人作对的孩子（两个孩子都算，可换着说）**，"
            "权威方是那位大人且**末句必须由他说**。"
            "错位时改标定行的 speaker（在该行 fixes 加 `\"speaker\"` 字段）并同时给出新台词"
        )
    if not lines:
        return (
            "- 本场只按 align checklist 与 closing_intent 定点修；"
            "禁止借用 M5/H 互毁和好模板"
        )
    return "\n".join(lines)


def format_align_refine_system(
    *,
    mechanism: str = "",
    structure_type: str = "",
    closing_intent: str = "",
    conflict_text: str = "",
) -> str:
    """精修 system：通用底稿 + 仅本场契约相关的 M5/H 条款。"""
    mech = str(mechanism or "").strip().upper()
    st = str(structure_type or "").strip().upper()
    context = f"{conflict_text or ''} {closing_intent or ''}"
    extras: list[str] = []
    if mech == "M5":
        extras.append(
            "M5 立规用「家规/规矩/规定」，勿写「妈妈说过」类转述。"
            "M5 立规/拒和/加码各占一句，禁止一句三连；"
            "拆句时须保留拒和与加码各一句且在妈妈前（与是否道歉无关）。"
        )
    if mech == "M5" or _any_token_affirmed(
        context, ("互毁", "撕坏", "弄坏", "推搡")
    ):
        extras.append(
            "互毁：报复句之前须 establish 双方物/作品；改机审标定行，"
            "禁止把前文合并进「也/还弄坏」同一句。"
        )
    if _reconcile_wanted(
        structure_type=st,
        closing_intent=closing_intent,
        conflict_text=conflict_text,
    ):
        extras.append(
            "收场和好仅在 closing_intent 要求时写拉手或齐声「不打了」；"
            "禁止给无和好契约的类型硬套末四句和好。"
        )
    if extras:
        return _ALIGN_REFINE_SYSTEM_BASE + "\n" + "\n".join(extras)
    return _ALIGN_REFINE_SYSTEM_BASE


def format_align_refine_user(
    *,
    issues_block: str,
    align_block: str,
    story_json: str,
    chars_min: int,
    chars_max: int,
    banned_literals: str,
    mom_lines_max: int,
    max_line: int,
    mechanism: str = "",
    structure_type: str = "",
    closing_intent: str = "",
    conflict_text: str = "",
    contract: dict[str, Any] | None = None,
) -> str:
    """精修 user：通用硬约束 + 按类型裁剪的保真条款。"""
    type_constraints = format_align_refine_type_constraints(
        mechanism=mechanism,
        structure_type=structure_type,
        closing_intent=closing_intent,
        conflict_text=conflict_text,
    )
    cast_block = format_cast_block(contract)
    if cast_block:
        type_constraints = f"{cast_block}\n{type_constraints}".strip()
    return _ALIGN_REFINE_USER_BASE.format(
        issues_block=issues_block,
        align_block=align_block,
        story_json=story_json,
        chars_min=chars_min,
        chars_max=chars_max,
        banned_literals=banned_literals,
        mom_lines_max=mom_lines_max,
        max_line=max_line,
        type_constraints=type_constraints,
    )


# 兼容旧名：默认无类型条款（仅通用底稿）；新调用请走 format_align_refine_*。
_ALIGN_REFINE_SYSTEM = _ALIGN_REFINE_SYSTEM_BASE
_ALIGN_REFINE_USER = _ALIGN_REFINE_USER_BASE.replace(
    "{type_constraints}",
    "- 本场只按 align checklist 与 closing_intent 定点修",
)

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


def format_scenario_rules_block(
    *,
    mechanism: str,
    structure_type: str,
    conflict_text: str,
    closing_intent: str,
    beat_chain: list[Any] | None = None,
) -> str:
    """仅注入本次契约涉及的互毁、调解与上药规则。"""
    context = " ".join(
        [
            str(conflict_text or ""),
            str(closing_intent or ""),
            *[
                str(item.get("intent") or item)
                if isinstance(item, dict)
                else str(item)
                for item in (beat_chain or [])
            ],
        ]
    )
    rules: list[str] = []
    mech = str(mechanism or "").upper()
    st = str(structure_type or "").upper()
    if mech == "M5" or _any_token_affirmed(
        context, ("互毁", "撕坏", "弄坏", "推搡")
    ):
        rules.extend(
            [
                "- 【本场互毁】先动手方与受害方按 scene_contract 绑定；"
                "报复须发生在首次实质破坏之后，speaker 不得调序。",
                "- 【本场互毁】若 closing 要求家长介入，介入前拒和与加码分开表达；"
                "服软方不得同时承担拒和。",
            ]
        )
    if _mom_adjudicate_wanted(
        structure_type=st,
        closing_intent=closing_intent,
        conflict_text=conflict_text,
    ):
        rules.append(
            "- 【本场调解】按 closing_intent 分层处理责任与和解；"
            "只有契约要求时才写拉手或双方分别承诺，禁止擅自套用齐声收束。"
        )
    elif _reconcile_wanted(
        structure_type=st,
        closing_intent=closing_intent,
        conflict_text=conflict_text,
    ):
        rules.append(
            "- 【本场和好】仅按 closing_intent 写拉手或分别承诺；"
            "禁止擅自引入妈妈定责或齐声收束。"
        )
    if _any_token_affirmed(context, ("碘伏", "涂药", "上药", "包扎")):
        rules.append(
            "- 【本场上药】上药完成即收束，之后禁止另起一起画、拉钩等新剧情。"
        )
    if not rules:
        return "- 本场只按 scene_contract 与 beat_chain 展开，禁止借用其他金稿事件。"
    return "\n".join(rules)


def format_role_binding_block(conflict_text: str) -> str:
    """扩写注入：从 scene conflict 解析受害方/先动手方/宣传方分工。"""
    prop_roles = _parse_conflict_propaganda_roles(conflict_text)
    if prop_roles:
        propagandist, victim = prop_roles
        return (
            "【角色分工锁定 · 硬约束 · 分数宣传】\n"
            f"- 宣传方 = {propagandist}：第一人称「我宣传/宣扬/到处说」"
            f"与「宣传高分该谢、低分怪分数」辩解只能由 {propagandist} 说\n"
            f"- 受害方 = {victim}：被说低分、同学笑话、抗议「你到处说」"
            f"只能由 {victim} 说；可用短促抗议，禁止空转复读同一短句\n"
            f"- 禁止：{victim} 说「我宣传…」；{propagandist} 说"
            f"「你到处说我/同学笑我」受害腔\n"
            "- 在场互指用你/名字，禁止「她考了…」第三人称转述对方\n"
            "- 家长拷问须打穿宣传方「跟我无关」借口；优先换位反问，"
            "勿写成帮「谁都能评」开脱；勿并给姐弟"
        )
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


_PARENT_NAMES = frozenset({"妈妈", "爸爸"})
_KID_NAMES = frozenset({"昭昭", "灿灿"})


def format_cast_block(contract: dict[str, Any] | None) -> str:
    """扩写注入：本次只允许哪些 speaker 出场、是几人戏。

    人数以契约 ``characters`` 为准（契约已由归一化层收敛过）：
    - 只给一个孩子 → 家长 × 孩子两人手，禁补旁观手足；
    - 给两个孩子 → 双孩同侧 + 家长。
    这条块是硬约束：先前提示里写死「单孩源须拆双孩」，与本层两人手直接冲突，
    模型会照旧造出旁观角色，随后被清理，字数来回震荡（#87 实测）。
    """
    sc = contract if isinstance(contract, dict) else {}
    from app.services.gold_story.scene import supplemental_witness_kid

    witness_kid = supplemental_witness_kid(sc)
    cast = [
        str(c).strip()
        for c in (sc.get("characters") or [])
        if str(c).strip()
    ]
    # 角色表对齐 beat：没有拍的角色不许出场。存量的旧契约可能仍带着幽灵角色
    # （角色表有、beat_chain 一句没有），这里兜住，避免提示把它们又写进对白。
    beat_speakers = {
        str(row.get("speaker") or "").strip()
        for row in (sc.get("beat_chain") or [])
        if isinstance(row, dict) and str(row.get("speaker") or "").strip()
    }
    if cast and beat_speakers:
        aligned = [c for c in cast if c in beat_speakers]
        if aligned:
            cast = aligned
    # 角色表缺失时退回 beat_chain 的说话人，避免空块让模型自由发挥
    if not cast:
        cast = list(
            dict.fromkeys(
                str(row.get("speaker") or "").strip()
                for row in (sc.get("beat_chain") or [])
                if isinstance(row, dict) and str(row.get("speaker") or "").strip()
            )
        )
    if not cast:
        return ""
    kids = [c for c in cast if c in _KID_NAMES]
    parents = [c for c in cast if c in _PARENT_NAMES]
    lines = [
        "【出场角色 · 硬约束】",
        f"- 本场 speaker 只能是：{'、'.join(cast)}；"
        "**禁止**出现任何一个未列出的角色（不得为凑字数、凑轮次另造孩子/家长/邻居）",
    ]
    if len(kids) == 1 and parents:
        lines.append(
            f"- 本次是**两人手**：{parents[0]} × {kids[0]}。"
            f"对白只在 {'、'.join(cast)} 之间交替，"
            "**禁止**添加第二个孩子或旁观手足来提问/帮腔/看热闹"
        )
        lines.append(
            f"- 字数靠 {kids[0]} 的荒诞解释与 {parents[0]} 的追问推进，"
            "**禁止**用新角色注水"
        )
        n_beats = len(sc.get("beat_chain") or []) or 6
        # 240 字 = 句数 × 均句长。要求句数太高会逼模型「同一句换词再说一遍」，
        # 终检随即判重复（#87 实测：16 句要求下稳定出现换词重复）。
        # 这里取「句数够、每句稍长」的组合：14 句 × 18 字 = 252 字，
        # 既有余量又不逼注水。
        need_lines = max(14, n_beats + 2)
        lines.append(
            f"- **句数预算（硬）**：两人手没有第三方分担，总共写 **{need_lines} 句左右**"
            f"（{n_beats} 个拍）；每句 **{SAFE_LINE_CHARS_HINT}**（比儿歌长一点、比书面语短一点），"
            f"单句不得超过 {CHAT_MAX_LINE_CHARS} 字"
        )
        lines.append(
            "- **每拍只写一次**：同一个意思只许说一遍。拍与拍之间的推进靠**新内容**"
            "（新的人/新的细节/新的态度），不靠把上一句换个说法再说一遍"
        )
        lines.append(
            "- **禁换词重复（硬）**：同一个意思全场只说一次。要凑够句数必须引入"
            "**新的具体信息**（新的人/新的词/新的细节/新的动作），"
            "禁止把已说过的解释换个说法再说一遍"
        )
        lines.append(
            "- **每句自洽（硬）**：一句一个完整意思。禁止把两件不相干的事用"
            "「因为…」「所以…」硬接；孩子一本正经讲圆也要讲得通、能听懂，"
            "不许写出连自己都解释不通的句子"
        )
        lines.append(
            "- **必须露出的机制词（硬）**：孩子讲圆那一侧要**明写因果连词**"
            "（因为……所以…… / 这样就能……），"
            "家长那一侧要有**明写追问**（什么意思 / 谁教的），"
            "收束句要**明写破功词**（行吧 / 服了 / 说不出 / 接不住）。"
            "这三类词是 N 类的机制骨架，缺一类即判不合格"
        )
        lines.append(
            "- **追问句只问两个点（硬）**：家长一句里最多问两件事"
            "（如「什么意思、谁教的」）。**禁止**三连问堆成审讯清单；"
            "问完之后孩子至少回应其中一个主问点，允许他荒诞跑偏，"
            "但不许对整句追问完全不理"
        )
        lines.append(
            "- **怪词只出现一次原形（硬）**：说出口之后一律用「这个词」「它」指代，"
            "**禁止**写成「waka了」「会waka」「waka呀」这类加时态/当动词的形态"
        )
        lines.append(
            "- **怪词只有一个含义（硬）**：孩子给出的解释必须**从头到尾是同一个意思**，"
            "后面再提到时只能沿用这个意思。**禁止**让同一个词一会儿指人、"
            "一会儿指行为、一会儿又指别的东西——那样观众听完不知道在说什么"
        )
        lines.append(
            "- **一次追问配一次解释（硬）**：家长问「什么意思」之后，孩子只解释**一遍**；"
            "**禁止**在后面的句子里反复重新定义同一个词"
        )
        lines.append(
            "- **句句咬住（硬）**：每一句都要接住上一句——回答它、反驳它、"
            "追问它、或接着它往下说。禁止换话题、偷换对象（上一句说橡皮、"
            "下一句说欠账）、也禁止凭空冒出一个新词；收束句之前必须把"
            "最后一个话头交代完"
        )
        lines.append(
            "- **收束前归位（硬）**：家长决定「先打草稿/服了」之前，"
            "最后一个话头必须已经落地（孩子把该说的说完，或家长已经问完），"
            "禁止在话头悬着时突然收束"
        )
    elif len(kids) >= 2 and witness_kid:
        main_kid = next((k for k in kids if k != witness_kid), kids[0])
        parent = parents[0] if parents else "家长"
        lines.append(
            f"- 本次仍是双孩同场，但 {witness_kid} 只是**见证位**："
            f"**优先不写**；确需出场时全场最多 1 句，"
            "且必须实质接住上一句（作答/给出新信息），"
            "禁止只说「我听着/你慢慢说/你先别急」这类空安抚；"
            "**不要用见证位拆主孩子的连续陈述**。"
            "主冲突与追问仍由"
            f" {parent} × {main_kid} 直接完成，"
            "**禁止**让见证位逐句插话、连续追问，或把两人的对质拆成访谈"
        )
        lines.append(
            f"- **每句长度**：{SAFE_LINE_CHARS_HINT}"
            f"（单句 ≤{CHAT_MAX_LINE_CHARS} 字）；"
            "不要靠重复态度句凑字数"
        )
    elif len(kids) >= 2:
        lines.append(
            f"- 本次是**双孩同侧**：{'、'.join(kids)} 同侧齐上，家长为配角；"
            "禁止把孩子写成对立"
        )
        lines.append(
            f"- **每句长度**：{SAFE_LINE_CHARS_HINT}"
            f"（单句 ≤{CHAT_MAX_LINE_CHARS} 字）；"
            "两个孩子交替接话，句数自然够，不要靠拉长单句凑字数"
        )
        lines.append(
            "- **严禁孩子连说（硬）**：任意相邻两句的孩子不能是同一个人——"
            f"必须是 {'/'.join(kids)} 交替。"
            "**禁止**让同一个孩子连着说两句以上，"
            "**也不许**为了不连说把内容删掉"
        )
        # #111 实测：交替位只能靠「追问细节/说出疑惑」填，模型就给旁观孩子编
        # 一串无信息的追问（「为啥」「快说说」），终审全判接不上。交替位置的
        # 内容必须限定在四类功能句，且不许用疑问链推进。
        lines.append(
            "- **搭档位只做功能句（硬）**：拍少的那个孩子（搭档位）全场 ≤5 句、"
            "其中疑问句 **≤1 句**；她的每一句只能是四类之一——"
            "递话（把话头交给对方）、代述（替别人把要求说出口）、"
            "反应（不信/犯怵/看热闹）、道具动作（放筷子/递醋）；"
            "**禁止**用「为啥/为什么/你说清楚/然后呢/快说说/谁教的」这类空追问充数，"
            "也禁止连续两句都以问号结尾"
        )
    # 包袱归属与零发明（#111 实测）：seed 漏掉源稿收尾包袱时，模型会把包袱
    # 改派给旁观孩子，再让另一个孩子追问一个前文没建立的事件（「老师逗你」），
    # 终审判「缺前提」整稿退回。这里把归属和出处写死，不绑具体剧情词。
    if str(sc.get("punchline") or "").strip():
        lines.append(
            "- **包袱归属（硬）**：源稿收尾那个包袱必须由 story_raw 里说这句话的"
            "**同一个孩子**说一次，位置在收束拍前；家长和另一个孩子"
            "**不得代说、不得改写成追问**，也不得只做同义复述"
        )
        lines.append(
            "- **包袱前提（硬）**：谁逗谁、谁让谁做了什么，必须由当事人在前文"
            "用一句台词交代清楚；包袱若依赖 **【出场角色】里没有的人物或事件**"
            "（源稿的旁观者、邻居、老师等），把包袱**改挂到在场角色**"
            "（谁在场就说谁），挂不上的整句弃用——不要引用不在场者说过的话，"
            "审读会判「引用无据」整稿退回"
        )
    lines.append(
        "- **不在场的人只许提、不许演（硬）**：dialogue_seed / story_raw 里点到、"
        "但【出场角色】里没有的人（老师/邻居/同学等）不承担任何一拍——"
        "本来夸他的改成**夸在场的人**，本来问他的改成**问在场的人**；"
        "不要让他说话、不要让角色转述他的话，也不要为他把话题拐走"
    )
    lines.append(
        "- **零发明（硬）**：对白里出现的每件事、每个人、每件道具，"
        "都要能在 dialogue_seed 或 story_raw 找到出处；"
        "禁止为了凑句数补一段前文没提过的事件"
    )
    lines.append(
        "- **严禁插拍（硬）**：seed 的顺序就是正文顺序，一拍说完再进下一拍；"
        "**禁止**在两拍之间插入自编的追问/反应（要补句就在拍内补，"
        "或把下一拍提前落一半，别横插一段）"
    )
    lines.append(
        "- **禁元话语（硬）**：「我是认真讲的/不是随口说说/我刚才就是这么说的/"
        "你爱信不信/这话我可/你怎么还在解释/理由说通了/照这个道理/"
        "一本正经继续」这类**对说话本身的评论**一律不许写——"
        "它们不含新信息，插在问句后面必被判「答非所问」"
    )
    lines.append(
        "- **自洽要落在剧情上（硬）**：「一本正经自洽」只能用**剧情内的因果**交代"
        "（为什么把妈妈比作老虎、老虎一吼会怎样、饺子和这事什么关系），"
        "**不能拿「我解释过了/理由说得通/我不是随口说的」来冒充因果**——"
        "那是在谈对话本身，审读必判「接不上」"
    )
    lines.append(
        "- **包袱只说一次（硬）**：点题的那句话全篇只出现一次，"
        "换词复述第二遍算「重复」，终检直接退回"
    )
    if parents:
        mom_max = sc.get("mom_lines_max")
        # 契约额度是派生约束，种子拍才是骨架：seed 里家长已经占 4 拍而额度只给
        # 3 句时，提示词会要求模型「合并掉一拍」，模型只能把追问外派给孩子或
        # 打乱拍序（#111 实测）。这里按拍数兜底，避免契约自相矛盾。
        parent_beats = [
            r
            for r in (sc.get("beat_chain") or [])
            if isinstance(r, dict)
            and str(r.get("speaker") or "").strip() in parents
            and str(r.get("intent") or "").strip()
        ]
        try:
            cap_n = len(parent_beats)
            if mom_max is not None:
                cap_n = max(int(mom_max), cap_n)
        except (TypeError, ValueError):
            cap_n = len(parent_beats)
        if cap_n > 0:
            lines.append(
                f"- 家长台词合计 ≤ {cap_n} 句（句数上限，不是字数上限）："
                "额度紧就合并措辞，**禁止**把家长的追问/责备整体挪给孩子"
            )
            # 额度必须优先保证「追问」还在：立规与收束很容易把额度吃光，
            # 追问一消失，N 的机制就塌成孩子独白（#87 实测多次「无人问」）。
            ask_beats = [
                r
                for r in (sc.get("beat_chain") or [])
                if isinstance(r, dict)
                and str(r.get("speaker") or "").strip() in parents
                and re.search(
                    r"追问|问|什么意思|谁教|哪来|怎么",
                    str(r.get("intent") or r.get("beat") or ""),
                )
            ]
            if ask_beats and cap_n >= 1:
                n_ask = cap_n
                need_open = 1  # 立规/触发
                need_close = 1  # 收束/破功
                # 额度够 → 追问可以占多句；不够 → 追问必须合并成一句，
                # 但**保底一句**，因为追问一缺席 N 的机制就塌了。
                ask_budget = max(1, n_ask - need_open - need_close)
                ask_budget = min(ask_budget, len(ask_beats), n_ask)
                lines.append(
                    f"- **家长额度分配（硬）**：{n_ask} 句 = 立规 {need_open} 句"
                    f" + 追问 {ask_budget} 句 + 收束 {need_close} 句"
                    f"（共 {need_open + ask_budget + need_close} 句；"
                    f"若超出 {n_ask}，追问合并成一句问全——意思是/谁教的/在哪儿，"
                    "但**不许取消追问**）；"
                    "**禁止**让家长的追问缺席、也禁止把追问改由孩子自问自答"
                )
    return "\n".join(lines)


def format_m5_h_expand_beat_block(
    *,
    conflict_text: str,
    closing_intent: str = "",
) -> str:
    """M5+H 扩写固定节拍表（对齐金稿 #5 正例结构）。"""
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



def format_authority_punchline_expand_block(
    *,
    beat_chain: list[Any] | None = None,
) -> str:
    """M4+G authority_punchline 扩写开场硬约束（抽象槽，禁绑单篇词）。"""
    beat0_sp = ""
    beat0_intent = ""
    for item in beat_chain or []:
        if not isinstance(item, dict):
            continue
        sp = str(item.get("speaker") or "").strip()
        intent = str(item.get("intent") or "").strip()
        if sp:
            beat0_sp = sp
            beat0_intent = intent
            break
    who = beat0_sp or "立规方"
    intent_hint = beat0_intent or "谁先完成谁得资源"
    return "\n".join(
        [
            "【M4+G 权威点题 · 扩写开场硬约束 · 不可协商】",
            f"- 第1句必须由 {who} 说，且必须是立规/约定句（要点：{intent_hint}）。",
            "- 不得从执行、回应、急哭、藏物、撇清起稿。",
            "- 立规句须含抽象规则：「谁先…谁…」或「先…先…」或约好/规定/说好；"
            "禁止旁白、心理、追问、后置立规。",
            "- 开场2句内必须完成立规；第3句后才允许反将/抗拒/受害者反应。",
            "- 立规未出现前，不得出现资源归属宣称、藏物、急哭、撇清、让渡、点题。",
            "- 急哭/找不到句须受害方说；藏物撇清句须藏物方说，不得对调。",
            "- 认怂让渡后至多1句过渡，随即权威点题收束；禁止省略号空句、纯拉扯占行。",
            "- 补刀/揭短须用前文已埋短处（如藏物本身），勿凭空新开未铺垫的短处。",
        ]
    )


def format_beat_sequence_block(
    *,
    conflict_text: str,
    beat_chain: list[Any] | None = None,
    mechanism: str = "",
    structure_type: str = "",
) -> str:
    """扩写注入：beat 事件顺序硬约束 + 互毁正/反例。"""
    from app.services.gold_story.scene import format_beat_chain

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
                "须按以下 beat 顺序展开；标了「须≥N个回合」的拍必须写足 N 个有推进的回合"
                "（一方说内容、另一方接得住），不得用「嗯/哦/行」等空应答占行：",
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
    from app.services.gold_story.gold_chat.type_bridge import (
        is_m8_j_domination,
    )

    if not is_m8_j_domination(
        mechanism=mechanism,
        structure_type=structure_type,
    ):
        return ""
    return M8_J_BEAT_BUDGET_BLOCK


A_BEAT_BUDGET_BLOCK = """【A 权威翻车 篇幅 beat 预算（禁止 1:1 扩 seed）】
| beat | 句数 | 字数 | 备注 |
| 立规/亮权威 | 2 | 40–55 | 权威当场定性、给规矩 |
| 追问/顶回 | 2–3 | 45–65 | 核心扩写区，挑战方连着顶 |
| 一锤可拍 | 1–2 | 25–45 | 权威自己当场违规，画面可拍 |
| 埋可引用原话 | 1 | 15–25 | 权威亲口说的 3–10 字断言 |
| 末四拍 | 4 | 70–100 | 引话→例外→追问→软破功 |
| 合计 | 10–12 | 260–340 | 优先保末四拍与句数 |

硬约束：
- 禁止 1:1 扩写 seed；中段「追问/顶回」须各加码 1–2 句
- 末四拍必须写满 4 句，按「挑战方→权威方→挑战方→权威方」交替：
  倒数第 4 句挑战方引话、倒数第 3 句权威方找例外、倒数第 2 句挑战方追问、
  倒数第 1 句权威方软破功
- **挑战方＝跟大人作对的孩子（可以两个孩子都算）**：
  2 孩子 vs 1 大人时，两个孩子在挑战方一侧**可以换着说**
  （例：姐姐引话→妈妈找例外→弟弟追问→妈妈破功），同侧换人不算错；
  **权威方必须是那位大人，且末句由他说**；不得让孩子替大人认输
- 倒数第 4 句必须写成「你刚才说…／你不是说…」并接权威方前文 3–10 字原话，
  不得只写反问或讨要
- 禁止在首尾垫字；每句 ≤24 字；禁止复读注水"""


def format_a_beat_budget_block(
    *,
    structure_type: str = "",
) -> str:
    if str(structure_type or "").strip().upper() != "A":
        return ""
    return A_BEAT_BUDGET_BLOCK


def format_expand_regen_feedback(
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
    """扩写重试：把上一轮失败原因注入 prompt。"""
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

        parts = ["【上一轮扩写失败 · 本轮须修正】"]
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
    from app.services.gold_story.gold_chat.type_bridge import (
        is_m8_j_domination,
    )

    parts = ["【上一轮扩写硬校验失败 · 本轮须一次写对】", f"错误：{err[:400]}"]
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
                f"每句宜 {SAFE_LINE_CHARS_HINT} 写满 beat，禁止只扩 seed 短句就停"
            )
    if "正文总字数须≤" in err:
        parts.append(
            f"- 正文不得超过 {DAILY_STORY_BODY_CHARS_MAX} 字；删注水/复读，勿顶上限"
        )
    # A 类短稿：同 M8+J 思路——先给 beat 字数预算（含末四拍），再按重试次数加码
    if (
        str(structure_type or "").strip().upper() == "A"
        and _is_short_content_feedback_error(err)
    ):
        parts.append(format_a_beat_budget_block(structure_type=structure_type))
        if short_regen_count >= 3:
            parts.extend(
                [
                    "- **第 3 次重试：强制中段重写**",
                    "- 保留开头立规句与末四拍不动",
                    "- 只重写中段「追问/顶回→一锤→埋句」，插入 2–3 组顶回对",
                    "- 禁止尾部灌水/复读；末四拍四句缺一即不合格",
                ]
            )
        elif short_regen_count >= 2:
            parts.extend(
                [
                    "- **第 2 次重试：中段 beat 不足**",
                    "- 追问/顶回段须再加 1–2 句，一锤写清可拍动作",
                    "- 禁止 1:1 扩 seed；禁止早早收束",
                ]
            )
        else:
            parts.append(
                "- A：立规亮权威→孩子追问顶回→权威自己当场违规（一锤）→"
                f"埋可引用原话→末四拍；每句宜 {SAFE_LINE_CHARS_HINT} 写满 beat，"
                "禁止只把 seed 扩成短句就停"
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
    """扩写重试：上一轮结构分未过线时的修订指令。"""
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
        from app.services.daily_story.quality import structure_cons_for_log

        cons = structure_cons_for_log(quality)[:5]  # type: ignore[arg-type]
        for c in cons:
            parts.append(f"- {c}")
        hints = build_quality_revision_hints(quality, story=story).strip()  # type: ignore[arg-type,union-attr,assignment]
        if hints:
            parts.append(hints[:500])
    parts.append("禁止另起第二轮；收束槽位落在末段后即停。")
    return "\n".join(parts)


def format_retry_missing_events_block(row: dict[str, Any]) -> str:
    """甲重掷反馈块：上一轮终检缺了哪些叙事事件、犯了哪些语义问题。

    只承载**语义**（事件意图 + 期望说话人 + 抽象约束），不带 beat 编号与行号——
    重掷会重建契约，旧编号在新契约里没有意义（专家裁决）。
    语病/垫字类不进本块：那类走本地定点修复，回灌只会让模型整篇改写。
    """
    feedback = row.get("gold_chat_retry_feedback")
    if not isinstance(feedback, dict):
        return ""
    events = feedback.get("missing_events")
    events = events if isinstance(events, list) else []
    constraints = feedback.get("semantic_constraints")
    constraints = constraints if isinstance(constraints, list) else []
    lines: list[str] = []
    if events:
        lines += [
            "【上一轮缺拍·必须补齐】",
            "上一轮成稿在终检被判「缺前提」：下列叙事事件没有被任何角色说出口。",
            "本轮须让它们在对应角色的话里真实发生（可换措辞，不得改事件本身，勿新增道具）：",
        ]
        for item in events[:4]:
            if not isinstance(item, dict):
                continue
            intent = str(item.get("original_intent") or "").strip()
            if not intent:
                continue
            speaker = str(item.get("expected_speaker") or "").strip()
            lines.append(
                f"- {intent}" + (f"（说话人应为{speaker}）" if speaker else "")
            )
    if constraints:
        lines += [
            "【上一轮终检问题·勿重复】",
            "上一轮成稿在终检被判下列连贯性问题。本轮只修这些问题：已通过的拍及其顺序、"
            "各角色台词额度、句数篇幅、收束位置保持不变，不得新增事件或道具。",
        ]
        lines += [
            f"- {str(item).strip()}" for item in constraints[:4] if str(item).strip()
        ]
    if not lines:
        return ""
    return "\n".join(lines)


def format_semantic_acceptance_feedback(
    error: str, *, allow_insert: bool = False
) -> str:
    """终检语义硬伤后的定点修稿指令（保留主线，修问题句及必要上下文）。

    ``allow_insert``：缺拍类硬伤只靠改写补不出前提，放行「补拍一行」；
    默认仍严格冻结行数，避免常规语义修稿借插行缝补绕过问题。
    """
    err = str(error or "").strip()
    parts = [
        "【终检硬伤·定点修稿】",
        "保留主线冲突与类型收束；只改机审点名的问题行，未点名行只作只读上下文。",
    ]
    if allow_insert:
        parts.append(
            "除机审明确点名的缺拍补行外，不得增删、合并、拆分对白，"
            "不得换 speaker，不得调整行序；勿引入新设定。"
        )
    else:
        parts.append(
            "不得增删、合并、拆分对白，不得换 speaker，不得调整行序；勿引入新设定。"
        )
    parts.extend(
        [
            "speaker 与 line 须一致：谁做动作、谁被打、「我/你/姐/哥」须按当前说话人视角前后连贯。",
            "问答/接话问题必须直接接住上一句的话头；修指代时先确认谁在问、谁在答，再改我/你/称呼。",
            "重复问题只在点名行内删除或改掉重复含义，保留开场触发和必要因果。",
            "收束拍只可表层改写：末句若是「赢了但没消气」，不得改成完全满意/收下道歉"
            "（这还差不多、我原谅你、没事了…）；要保住这点没消气的余味。",
            f"机审：{err}",
        ]
    )
    return "\n".join(parts)


def format_seed_skeleton_block(
    seed: list[Any] | None,
    *,
    skeleton_len: int = 6,
) -> str:
    """草稿前 N 拍须逐字落实 seed 骨架（专家裁决：前提链必须在开头建立）。

    缺前提（后文引用未交代的物证/旧账）是结构问题，提示词软约束压不住；
    seed 已含完整前提链，故要求开头先把骨架按序落地成可见对白，
    之后才允许自由扩写。这里只列骨架内容，不写剧情词。
    """
    rows: list[tuple[str, str]] = []
    for item in seed or []:
        if isinstance(item, dict):
            speaker = str(item.get("speaker") or "").strip()
            text = str(item.get("intent") or item.get("line") or "").strip()
        else:
            speaker, text = "", str(item or "").strip()
        if text:
            rows.append((speaker, text))
    if not rows:
        return ""
    head = rows[:skeleton_len]
    lines = "\n".join(
        f"  {i}. {sp or '（按契约角色）'}：{text}"
        for i, (sp, text) in enumerate(head, 1)
    )
    return (
        f"【开头骨架（前 {len(head)} 拍逐字落实，硬要求）】\n"
        f"{lines}\n"
        "要求：正文**前若干句必须按上表顺序依次落地**，每拍至少一句可见对白，"
        "被引用的一方要**真把那句话说出口**（如家长压人的那句），"
        "物证/旧账要先由在场人当场交代一次（谁看见、在哪看见、什么样），"
        "之后才允许自由扩写与加码；"
        "**禁止**跳过骨架直接从反问或引用开场，也禁止引用骨架里没交代过的物证。"
        "seed 是压缩素材：若结果句在回答/拒绝 story_raw 中某人先前的请求或追问，"
        "必须先把该请求/追问写成可见对白；近义重复的 seed 只落地一次。"
    )


def format_seed_span_block(
    seed: list[Any] | None,
    *,
    structure_type: str = "",
    mechanism: str = "",
) -> str:
    """seed 条数不足 12 时，强制提示中段加码扩句，禁止 1:1 扩完就停。"""
    from app.services.gold_story.gold_chat.type_bridge import (
        is_m8_j_domination,
    )
    from app.services.gold_story.scene import CHAT_LINE_COUNT_MIN
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
        f"（目标 280–340）；每句宜 {SAFE_LINE_CHARS_HINT}，禁灌尾巴凑字。",
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
            # 「哀求/加码 + 否决」是别的类型的节拍，N 类照抄会让模型写成
            # 跟本场无关的拉扯句（本地补丁再灌一堆「不让/不给」态度句凑字）。
            # 这里改成类型中性的「一拍两句」：一方提出/追问，对方当场回应。
            parts.append(
                f"seed 少于 {CHAT_LINE_COUNT_MIN}：把其中 {need_lines} 条各铺成"
                "**两句**——一方先提出/追问，另一方**当场回答/反应**"
                "（追问细节/表态/拆台/被噎），共补 ≥"
                f"{need_lines} 句；两句都必须落在同一条 seed 拍的内容里，"
                "禁止 seed 1:1 扩完就停；"
                "禁止同一角色连续换词复述同一质问或同一态度；"
                "后一句必须新增依据、后果或对象，或由对方回答；"
                "禁止用与剧情无关的态度句（不让/不给/你能拿我怎么样）凑字，"
                "禁止灌尾巴（你给我听好了/这回算清楚等）。"
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
    closing_mode: str = "",
    k_close_mode: str = "",
) -> str:
    """注入 gold_chat prompt：金稿关键拍 checklist。"""
    st = str(structure_type or "").strip().upper()
    mech = str(mechanism or "").strip().upper()
    k_mode = str(k_close_mode or "").strip()
    chain = align_chain(
        structure_type=st,
        mechanism=mech,
        closing_mode=closing_mode,
        k_close_mode=k_mode,
    )

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


PERBEAT_SYSTEM = (
    "你是日常家庭对白的「单拍填词器」。只写当前这一拍的一句台词。\n"
    "硬性要求：\n"
    "1. 说话人必须等于本拍给出的 speaker，绝不替别的角色说话，也不得替后面的拍说出关键句。\n"
    "2. 只写 1 句，18–22 字，口语，能直接念出来；宁可多带一个具体名词，也不要空泛。\n"
    "3. 这是角色**对着在场的人**说的一句话：不得出现自己的名字，"
    "不许念旁白、不许自述动作过程（「我夹起饺子」「我汤勺举在半空」"
    "「我看看妈妈手里的筷子落不落」都不算台词）；"
    "动作只能当一句话的由头，话本身要对着人说。\n"
    "4. 禁止元话语：不得写「你怎么还在解释／我说的是真的／理由说得通／不是随口说的／"
    "反正我就是」这类谈对话本身的话。\n"
    "5. 只许出现【在场角色】里的人、桌上那盘东西、以及碗筷这些当场就在手上的餐具；"
    "不得出现任何新的物件（书包/彩笔/橡皮/零钱/汤/苹果/镜子…）、新的地点、新的人物、"
    "新的前情——写不出来就只谈桌上那盘东西和眼前这三个人。\n"
    "6. 必须接住前文最后一句的话头：**照搬它里面的一个具体词**（那盘东西、那个味道、"
    "那句判断），这一句要能证明自己听懂了上一句，不能另起一件事。\n"
    "6a. 若写「你说…」，引语必须是上一句**真说过**的字词；不许替对方补一句"
    "「老虎发威吓人」再反驳。\n"
    "7. 上一句若是**问句**，本句必须**先回答那个问题**（给出具体答案/具体判断），"
    "不许把同一个问题反问回去，也不许换个人问同一件事。\n"
    "8. 本句功能若是**反应/道具**：只许对刚才那句话表态、补一个当场看得见的具体细节；"
    "**不许提出新的问题**，不许开启新话题，也不许写安抚/催促/递话空话。\n"
    "9. 同一个比喻/同一个判断全篇只说一次；说过「老虎」的，本句换成盘子、筷子、"
    "饺子皮、嗓门这些别的具体东西，不许再说一遍老虎怎么样。\n"
    "【反面例子（这些都算废句，绝对不许写）】\n"
    "- 「X，你说这盘饺子是谁包的。」→ 把上一句原样抛回去，没有内容\n"
    "- 「你说的这是什么意思？」→ 反问回去，掐断对话\n"
    "- 「我怎么听着这么玄乎，越琢磨越觉得悬。」→ 空泛评价，没有具体东西\n"
    "- 「你这话我可接不住。」→ 元话语，谈对话本身\n"
    "10. 反应/插话句必须**指名道姓地说清在说谁、在说哪样东西**，"
    "并给出一个明确立场（信/不信、能吃/不能吃、该改口/不该改口）；"
    "不许用「比喻/道理/这话/意思/玄乎/离谱」这类抽象词充当内容——"
    "审读会把抽象反应判成「指代不清、立场矛盾」。\n"
    "10a. 表态必须给理由：不能只写「我不同意」「我不信」就收尾；"
    "要么说明因为哪一点，要么指出对方话里哪里不成立。\n"
    "10a-2. 不许只附和或收下夸奖（「这夸得挺对」「好话我收下了」）；"
    "同一个「我同意/我不同意」表态动作全篇只做一次，后面换成反问、补充或纠错。\n"
    "10a-3. 上一句同时有批评和夸奖时，先接**批评那一半**；"
    "不许绕开批评，另补脸色/长相/眉眼/头发/穿着等外貌细节来夸。\n"
    "10a-4. 不许只复述「你先说X、又说Y」的表面矛盾；"
    "必须拿出一个前文已经发生的具体行为（端饺子、让你尝、改口等）作依据，再表态。"
    "反驳「像老虎」时要说脾气/神态，不能只拿「没吼过你」作字面反驳；"
    "同一个理由全篇只说一次。\n"
    "10b. 不许引用前文没发生的事：前面没演过发威/吼/摔等事件，"
    "就不能说「你刚才也瞧见了」「你刚才也听见了吧」。\n"
    "10c. 家长要求孩子改口时（「改口祝妈妈像公主」），家长自称用「我」、"
    "对孩子用「你改口」；不能写成家长自己「我改口，祝妈妈像公主」。\n"
    "10d. 孩子回应改口要求时，不能反过来说「所以你别改口了」；"
    "要就「像公主还是像老虎」继续给判断。\n"
    "10e. 上一句不是「为什么」问句时，不要用「因为」或「所以」硬接；"
    "直接给判断，或用「可/可这」转。\n"
    "10f. 上一句要求改口时，先正面回「改口也没用」，"
    "再用「因为老虎一吼，公主也得现出原形」落回契约；"
    "不要写「装公主」「扮公主」，也不要把老虎和公主写成互相变身。\n"
    "10g. 认栽说「以后说话先打草稿」前，先接住现场并点名是谁的嘴让自己没辙"
    "（如「管不了，昭昭你这张嘴」）；不要自述「这话真把我噎住了」这类旁白。\n"
    "【正面例子（反应句就照这个写法）】\n"
    "- 「妈你先别气，他这比喻我接不住呀。」（对着人表态 + 指向上一句的比喻）\n"
    "- 「行，那我就在旁边看着你把这事说圆。」（不追问，只表态并给出自己的立场）\n"
    "- 「这皮擀得跟鞋底似的，你俩还真吃得下去。」（点名具体东西 + 明确立场）\n"
    "- 「这盘饺子我尝过了，芯子确实发苦，妈你别不服。」（点名东西 + 站队）\n"
    "- 「芯子难吃我也吃出来了，可妈妈眉清目秀也没说错。」（先接批评，再接夸奖）\n"
    "- 「妈妈可不像暴躁老虎，她刚还问你饺子好不好吃。」（用已发生的问话反驳）\n"
    "只输出 JSON：{\"line\": \"...\"}"
)


def format_perbeat_user(
    *,
    scene_contract: dict[str, Any],
    punchline: str,
    prev_lines: list[tuple[str, str]],
    speaker: str,
    intent: str,
    function: str,
    beat_id: int,
    beat_count: int,
    used_details: list[str],
    must_words: list[str] | None = None,
    required_word_groups: list[list[str]] | None = None,
    upcoming: list[tuple[int, str, str]] | None = None,
    retry_feedback: str = "",
) -> str:
    """逐拍填词的单拍用户消息：全局卡 + 已写的全部对白 + 本拍契约 + 后面还有什么。

    「已定稿前文」给**全篇**而不是最近三句：只给三句时模型会把上一句的
    问题接错（#138 实测：妈妈问「咋舍得夸我」，孩子答成「为啥像老虎」，
    因为看不到前面已经问过什么）。后面要发生的拍也一并给出，插话就不会
    抢后面的剧情、也不会另起一件事。
    """
    cast = "、".join(str(x) for x in (scene_contract.get("characters") or []))
    prev_txt = (
        "\n".join(f"{sp}：{ln}" for sp, ln in prev_lines[-14:])
        or "（无，本拍是开场）"
    )
    upcoming_txt = (
        "\n".join(f"拍{bid} {sp}：{it}" for bid, sp, it in (upcoming or []))
        or "（无，本拍是最后一句）"
    )
    used_txt = "、".join(used_details[-4:]) or "（无）"
    groups = [list(group) for group in required_word_groups or []]
    if must_words and must_words not in groups:
        groups.insert(0, must_words)
    must_txt = ""
    if groups:
        must_txt = "必需条件组须全部满足，每组任选一个词原样出现：\n" + "".join(
            f"- 第{i}组：{'/'.join(group)}\n"
            for i, group in enumerate(groups, 1)
        )
    return (
        f"【全局卡】\n"
        f"类型：{scene_contract.get('story_type') or ''}\n"
        f"场景：{scene_contract.get('location') or '家里'}；在场角色：{cast}\n"
        f"故事核：{scene_contract.get('conflict') or ''}\n"
        f"关键包袱（全篇只说一次，只能由指定角色说）：{punchline or '（无）'}\n"
        f"篇幅：全篇约 {beat_count} 拍，每句 18–22 字\n\n"
        f"【已定稿前文】（全篇顺序，最后一句就是要你接的那句）\n{prev_txt}\n\n"
        f"【后面还要发生的拍】（不许提前说、不许抢）\n{upcoming_txt}\n\n"
        f"【本拍】\n"
        f"beat_id：{beat_id}/{beat_count}\n"
        f"speaker：{speaker}\n"
        f"intent：{intent}\n"
        f"本句功能：{function}\n"
        f"{must_txt}"
        f"{retry_feedback}\n"
        f"已经用过的具体细节（不要重复，换一个新的）：{used_txt}\n\n"
        f"【输出】{{\"line\": \"这一句台词\"}}"
    )


PERBEAT_FILLER_REWRITE_SYSTEM = (
    "你是家庭日常对白的「反应句补位器」。只写当前这一句草稿：说话人不是本拍的"
    "当事人时，也只写一句当场反应，不交代事实。\n"
    "硬性要求：\n"
    "1. 只输出一句 14–24 字的口语台词，能直接念出来，以句号/问号/感叹号收尾。\n"
    "2. 必须接住上一句：抓住上一句里一个具体的词，当场顶一句、反问一句或表态。"
    "**禁止**写安抚、催促、递话、评理（「你先别急」「慢慢说」「我听着」"
    "「我不插嘴」「把话交回给他」「让他自己说清楚」「我在旁边看着」），"
    "也禁止复述上一句。\n"
    "3. 不许把上一句讲过的事再说一遍：与上一句连续相同的字不得超过 4 个；"
    "换主语、换词改写上一句的内容同样不许。\n"
    "4. 不许用「我」说别人做过/想过/委屈/没错的事（「我也弄坏了」「我想自己弄好」"
    "「反正我没错」都算抢戏）。\n"
    "5. 不许引入新的物件、新的人物、新的前情，也不许替当事人回答或做决定；"
    "不许念旁白、不许自述动作过程。\n"
    "只输出 JSON：{\"line\": \"这一句台词\"}"
)


def format_perbeat_filler_rewrite_user(
    *,
    speaker: str,
    intent: str,
    function: str,
    prev_lines: list[tuple[str, str]],
    reason: str,
    scene_contract: dict[str, Any] | None = None,
    party: bool = False,
) -> str:
    """旁观插话槽的定向重写用户消息：只给上下文 + 这一句要做什么 + 上轮判废原因。"""
    cast = "、".join(
        str(x) for x in ((scene_contract or {}).get("characters") or [])
    )
    prev_txt = "\n".join(f"{sp}：{ln}" for sp, ln in prev_lines[-6:]) or "（无）"
    role = (
        "你是**这场冲突的当事人**，不是和事佬：只回一句态度/情绪或顶一句，"
        "不许劝对方「别急/慢慢说」，也不许把后面自己那拍要交代的事实"
        "（谁弄脏的、为什么、怎么弄）提前说掉。"
        if party
        else "你是**当场在场的人**：只对上一句回一句短反应（顶一句/反问一句/"
        "表态），手上没有事实要交代；不许安慰、催促、递话或评理。"
    )
    return (
        f"【在场角色】{cast or '（略）'}\n"
        f"【已写好的前文】（最后一句就是刚才那句话）\n{prev_txt}\n\n"
        f"【这一句】说话人：{speaker}；本句功能：{function}；\n"
        f"要求做的事：{intent}\n"
        f"【身份】{role}\n"
        f"【上一轮被打回的原因】{reason}\n\n"
        f"【输出】{{\"line\": \"这一句台词\"}}"
    )


PERBEAT_BATCH_SYSTEM = (
    "你是家庭日常对白的「填词器」。给你一张**已经定好的分配表**：每一句的序号、谁来念、这一句要干什么、必须出现哪个词。你只负责把台词填进去，**不许改序号、不许改说话人、不许增删句子**。\n"
    "硬性要求：\n"
    "1. 说话人严格按分配表，绝不替别的角色说话，也不许把两句合成一句；某个动作/要求/表态是拍主的活，别人不能替他做（换了人就是「串戏」）。\n"
    "2. 每句 8–24 字，口语，能直接念出来；以句号/问号/感叹号收尾，必须说完整。"
    "孩子的话可以很短（「是！」「我声音最大。」），别为了凑字数加铺垫。\n"
    "3. 这是角色**对着在场的人**说的话：不得出现自己的名字，不许念旁白、不许自述动作过程（「我夹起筷子」「我把碗举在半空」都不算台词）。\n"
    "3a. 分配表「这一句要干什么」里写「再说想自己弄干净」这类转述时，只把**内容**说出来（「我自己弄干净，因为疼妈妈」），不许写成「说想/说要/说觉得」——那等于替自己念旁白。\n"
    "4. 禁止元话语：「你怎么还在解释／我说的是真的／理由说得通／这话我可接不住」这类谈对话本身的话一律不许写。\n"
    "5. 只许出现在场角色和**本拍说明里出现过**的物件；不得出现新物件、新地点、新人物、新前情。\n"
    "6. 每一句都要在语义上承接上一句；可用代词或省略自然衔接，不必重复同一词。素材行按分配表推进既定内容。\n"
    "6a. 若写「你说…」，引语必须是上一句**真说过**的字词；不许替对方补一句再反驳。\n"
    "7. 上一句是问句时，下一句要回应它，不能逃避；分配表明确要求回声/反问的素材行可按原意反问，其余不能把同一问题换个人重问。\n"
    "8. 同一个比喻/同一个判断全篇只说一次；说过之后换别的具体依据，不要换词复述同一态度。\n"
    "9. 分配表里标了「必须出现」的句子，那个词要**原样**出现在该句里。\n"
    "9a. 说明里标了「必现（缺一不可）」的句子：每个必现词的任一写法都必须出现在这句里；字数不够就砍别的内容，不许砍这些词。\n"
    "10. 标了「反应/插话」的句子：只回应刚才的具体内容，可表态或自然追问；不许开启新话题，不许只写「你先别急/慢慢说/我听着/把话交回给他」这类安抚、催促、递话，也不许拿「比喻/道理/这话/意思」这类抽象词充当内容。\n"
    "10a. 标了「拆句·后半」的句子：这一拍原稿是一整句，现在拆给两个人说——拍主已说**前半**，你只说**后半**，不要复述拍主，也不要只表态。\n"
    "10a-1. 标了「契约拍·前半」的句子：本拍内容分给两个人，你只说**前半**，后半留给后面标了「拆句·后半」的那个人；不要把后半也说了。\n"
    "10a-3. 拆句之后，后半句的内容算**拆句人**说的：后文要引用它时，必须称呼拆句人；不许再按契约的拍主称呼。\n"
    "10a-2. 反应句只写**一个回应**：不许前半句接话、后半句又拐去挑新毛病；上一句若没在说这个细节，就不得另起。\n"
    "10b. 反应句表态必须给理由：不能只写「我不同意」「我不信」就收尾；要么说明因为哪一点，要么指出对方话里哪里不成立。\n"
    "10b-2. 不许只附和或收下夸奖；同一个「我同意/我不同意」表态全篇只做一次。\n"
    "10b-3. 上一句同时有批评和夸奖时，先接**批评那一半**，不许绕开批评只夸外貌。\n"
    "10b-4. 不许只复述「你先说X、又说Y」的表面矛盾；必须拿出一个前文已经发生的具体行为作依据，再表态；同一个理由全篇只说一次。\n"
    "10c. 不许引用前文没发生的事：前面没演过的情节，不能说「你刚才也瞧见了」「你刚才也听见了吧」。\n"
    "10d. 不许把「谁对谁做了什么」说反：谁提要求谁发话，被要求的人不能把对方的要求说成自己的动作，也不能反过来说「所以你别说」。\n"
    "10e. 上一句不是「为什么」问句时，不要用「因为」或「所以」硬接；直接给判断，或用「可/可这」转。\n"
    "10f. 认栽/服软要接住现场并点名是谁的话让自己没辙；不要自述「这话真把我噎住了」这类旁白。\n"
    "10g. 标了「反应/插话」的句子，若说话人是**旁观者**：不许用「我」认领上一句里属于拍主的事实、动机、委屈或动作——「我也弄坏了」「我想自己弄好」「反正我没错，你不该那样说我」都算串戏；只许对上一句回一句当场反应（顶一句/反问/表态），不许看/听/劝/递话。\n"
    "10h. 标了「反应/插话」的句子不许照抄上一句连续五个字以上，也不许换词把同一件事再说一遍。\n"
    "10i. 全篇有多句「反应/插话」时，每句要抓住上一句**不同的具体词**，"
    "不许换词复述，也不许写安抚/催促/递话（「别急/慢慢说/我听着/你没错/把话交回给他」）。\n"
    "10j. 若「反应/插话」句的说话人本身就是**冲突当事人**（不是旁边看着的人）：只许回一句态度、"
    "顶一句或反问，接着把自己的话往下说；不许劝对方「别急/慢慢说」（那是和事佬的活，会被判"
    "「安抚对象错位」），也不许把后面自己那拍要交代的事实（谁弄脏的、为什么、怎么弄）提前说掉——"
    "说了后面那拍就只能重复你这一句。\n"
    "11. 分配表里每句的说明只是**给你看的舞台提示**，不是台词。不许把其中的情绪/动作词抄进句子开头——「气笑了」「不慌不忙」「狐疑」「认栽」「愣住」「一本正经」一律不得出现在台词里。\n"
    "12. 上一句提出要求时，先正面回应对这个要求的态度，再用一句本拍契约里的判断落回来；不要把双方的说法写反，也不要把比喻写成现实设定。\n"
    "【反面例子（都算废句）】\n"
    "- 「X，你说这盘东西是谁做的。」→ 把上一句原样抛回去\n"
    "- 「你说的这是什么意思？」→ 反问回去，掐断对话\n"
    "- 「我怎么听着这么玄乎，越琢磨越觉得悬。」→ 空泛评价，没有具体东西\n"
    "- 「你这话我可接不住。」→ 元话语\n"
    "【正面例子（反应句照这个写法：接住具体词 + 给新信息）】\n"
    "- 「这东西你尝过了吧，闻着就不对，妈你别不服。」\n"
    "- 「行，那我就在旁边看着你把这事说圆。」\n"
    "- 「难吃我也吃出来了，可你刚夸的那句也没说错。」（先接批评，再接夸奖）\n"
    "- 「她可不像你说的那样，她刚还问你好不好吃。」（用已发生的问话反驳）\n"
    "只输出 JSON：{\"lines\": [{\"i\": 1, \"line\": \"...\"}, {\"i\": 2, \"line\": \"...\"}]}"
)


_PERBEAT_STAGE_PREFIXES = (
    "先直接回答上一句问的问题",
    "一本正经说",
    "一本正经",
    "气笑要求",
    "气笑",
    "不慌不忙",
    "狐疑追问",
    "狐疑",
    "认栽说",
    "认栽",
    "愣住",
    "愣",
    "苦笑",
    "无奈",
    "正色说",
    "正色",
    "板着脸",
    "挑眉",
    "撇嘴",
    "转头",
    "抬眼",
)


# 舞台提示不一定只出现在 intent 开头：契约写「说自己不是想讨好处，再一本正经说
# 妈妈像老虎」时，模型会把后半段原样抄进台词。这里统一识别「神态/语气 + 说」
# 的表演说明，既用于清理分配表，也用于生成端硬拒。
PERBEAT_STAGE_DIRECTION_RE = re.compile(
    r"(?:(?:我|俺|他|她)?(?:再|又|才|便|就|先|还)?)"
    r"(?:一本正经|不慌不忙|气笑|狐疑|认栽|愣住|苦笑|无奈|正色|"
    r"板着脸|挑眉|撇嘴|转头|抬眼)"
    r"(?:了|着|地)?(?:说|问|答|回|道|要求|喊|嘟囔|嘀咕)"
)


def _perbeat_clean_intent(intent: str) -> str:
    """去掉 intent 开头的「舞台提示」词。

    契约拍 intent 是给写手看的舞台说明（「气笑要求改口祝妈妈像一个公主」），
    原样塞进分配表后模型会把它当台词开头抄下来——实测出现过
    「气笑了，你改口祝妈妈像一个公主」「不慌不忙，老虎一吼…」，
    这种句子读起来像旁白，终检直接判错位。去掉提示词只留有信息的那部分，
    模型就没有可抄的动作前缀了。
    """
    text = str(intent or "").strip()
    changed = True
    while changed and text:
        changed = False
        for prefix in _PERBEAT_STAGE_PREFIXES:
            if text.startswith(prefix):
                text = text[len(prefix):]
                text = text.lstrip("，,、：: 着一地得")
                changed = True
                break
    # 拍意图里常有「举着筷子半天没落下，被昭昭这句噎住接不上话，认栽说…」
    # 这种「动作 + 反应 + 才开口」的复句：开头的动作段若原样进分配表，模型会把
    # 它写进台词（#138 第 12 句「行吧，我这筷子举半天没落下…」被判自述动作）。
    # 逐段丢弃「不含说话动词」的前置段，直到出现 说/问/答/回/要求/喊 这类词。
    parts = [x for x in re.split(r"[，,]", text) if x.strip()]
    while len(parts) > 1 and re.search(
        r"^(?:举着|端着|拿着|放下|坐下|站起|转头|抬眼|低头|皱眉|摇头|叹气|被.{1,12}噎住)", parts[0]
    ) and not re.search(
        r"说|问|答|回|要求|喊|叫|骂|夸|劝|让|承认|认输", parts[0]
    ):
        parts.pop(0)
    text = "，".join(parts) if parts else text
    text = PERBEAT_STAGE_DIRECTION_RE.sub("", text)
    text = re.sub(r"[，,；;]\s*[，,；;]+", "，", text)
    text = re.sub(r"\s{2,}", " ", text).strip("，,；; ")
    return text or str(intent or "").strip()


def format_perbeat_batch_user(
    *,
    scene_contract: dict[str, Any],
    punchline: str,
    slots: list[dict[str, Any]],
    feedback: str = "",
) -> str:
    """整篇逐拍填词的用户消息：全局卡 + 分配表（一次填完所有句）。

    分配表由本地代码确定性生成（说话人、拍序、功能、必含词都锁死），
    模型只填台词。相比一句一调，调用次数从 ~50 降到 1，同时不会张冠李戴：
    说话人根本不由模型决定。
    """
    cast = "、".join(str(x) for x in (scene_contract.get("characters") or []))
    from app.services.gold_story.scene import CHAT_MAX_LINE_CHARS
    target_chars = min(DAILY_STORY_BODY_CHARS_MIN, len(slots) * CHAT_MAX_LINE_CHARS)
    min_chars = min(target_chars, DAILY_STORY_BODY_CHARS_MIN - CHAT_MAX_LINE_CHARS + 12)
    source_mode = bool(slots) and all(s.get("source_plan") for s in slots)
    line_target = (DAILY_STORY_BODY_CHARS_MIN - CHAT_MAX_LINE_CHARS + len(slots) - 1) // max(1, len(slots))
    rows: list[str] = []
    for idx, slot in enumerate(slots, 1):
        groups = [
            list(g) for g in (slot.get("required_word_groups") or [])
        ]
        words = list(slot.get("must_words") or [])
        if words and words not in groups:
            groups.insert(0, words)
        must = "；".join("或".join(g) for g in groups)
        if slot.get("split_role") == "second_half":
            tag = "拆句·后半"
        elif slot.get("split_role") == "first_half":
            tag = "契约拍·前半"
        elif slot.get("is_split"):
            tag = "拆句/另一半"
        elif slot.get("is_filler"):
            tag = "反应/插话"
        else:
            tag = "契约拍"
        row = (
            f"{idx}. 【{tag}】{slot['speaker']}："
            f"{str(slot.get('intent') or '') if slot.get('planned_content') else _perbeat_clean_intent(str(slot.get('intent') or ''))}"
            f"（本句功能：{slot.get('function') or '推进本拍'}）"
        )
        if slot.get("planned_speech_act") in {"echo", "retort"}:
            row += "｜原素材明确为回声/反问，保留该言语行为"
        if source_mode:
            row += f"｜本句目标{line_target}–{CHAT_MAX_LINE_CHARS}字（含标点，补清角色/对象/回忆指代，不添加新事实）"
        beat_intent = str(slot.get("beat_intent") or "").strip()
        if beat_intent and slot.get("split_role"):
            row += f"｜本拍内容：{_perbeat_clean_intent(beat_intent)}"
        if must:
            row += f"｜必须出现：{must}"
        points = [
            list(g) for g in (slot.get("required_semantic_terms") or [])
        ]
        if points:
            row += "｜必现（缺一不可）：" + "；".join(
                "或".join(g) for g in points
            )
        rows.append(row)
    fb = f"\n【上一轮被打回的原因（今回必须避开）】\n{feedback}\n" if feedback else ""
    return (
        f"【全局卡】\n"
        f"场景：{scene_contract.get('location') or '家里'}；在场角色：{cast}\n"
        f"故事核：{scene_contract.get('conflict') or ''}\n"
        f"关键包袱（全篇只说一次，只能由指定角色说）：{punchline or '（无）'}\n"
        f"篇幅：共 {len(slots)} 句，每句 8–24 字，全篇按序号顺序发生\n"
        f"类型：{scene_contract.get('story_type') or ''}；表达契约：{json.dumps(scene_contract.get('gold_n_expression_contract'), ensure_ascii=False)}\n"
        f"全篇总字数目标{target_chars}字（含标点，至少{min_chars}字）：按各槽目标写足表达，不能因为照抄短素材而篇幅不足。\n\n"
        f"【分配表】（照此填词，序号/说话人/顺序都不许改）\n"
        + "\n".join(rows)
        + f"\n{fb}\n"
        f"【输出】{{\"lines\": [{{\"i\": 1, \"line\": \"第一句台词\"}}, "
        f"{{\"i\": 2, \"line\": \"第二句台词\"}}, …]}}"
    )


LINE_PLAN_SYSTEM = (
    "你是家庭日常短视频的「对白编排」。说话人、拍号和句序已经排好，你只负责"
    "给每一行写 intent——这一句要干什么。你不写台词。\n"
    "硬性规则：\n"
    "1. 行数恰好等于要求句数，i 从 1 连续编号，不许增删改行。\n"
    "2. intent 写「这句话回应上一句的哪个具体词、给出什么具体依据或后果」，"
    "8–24 字，主语就是该行说话人。\n"
    "3. 不写动作、神态、心理（愣住、气笑、看妈妈、举着筷子），"
    "也不写空表态（「我不信」「你说得对」「我同意」）。\n"
    "4. 全篇不许两行 intent 互为换词复述；同一个意思只排一次。\n"
    "5. 反应行不是垫话：必须抓住上一句里最具体的一个词，给出新信息或新后果。"
    "禁止写安抚/催促/递话/评理（「你先别急」「慢慢说」「我听着」「我不插嘴」"
    "「把话交回给他」「让他自己说清楚」「我在旁边看着」），也不许复述上一句；"
    "标了「无素材」的行同样要写当场能说的一句短反应，不许改成旁白或导演指令，"
    "不许凭空添加人物、物件或前情。\n"
    "6. 第 1 行开新话题；最后一行由收束拍说话人收口，不许写成问句。\n"
    "7. 不许新增源故事里没有的人物、物件、地点、前情。\n"
    "只输出 JSON：{\"lines\": [{\"i\": 1, \"intent\": \"这一句要干什么\"}, ...]}"
)


def format_line_plan_user(
    *,
    scene_contract: dict[str, Any],
    story_raw: str,
    rows: list[dict[str, Any]],
    feedback: str = "",
    no_material_speakers: set[str] | None = None,
) -> str:
    """逐句计划的用户消息：源故事 + 已定好的说话人/拍序表，只让模型填 intent。"""
    cast = "、".join(str(x) for x in (scene_contract.get("characters") or []))
    beats = {
        int(b.get("beat") or 0): str(b.get("intent") or "").strip()
        for b in (scene_contract.get("beat_chain") or [])
        if isinstance(b, dict)
    }
    table: list[str] = []
    for idx, row in enumerate(rows, 1):
        if row.get("from_beat"):
            # 拍主行已按拍意图写定，不必占用模型输出
            continue
        role = "主句" if row.get("role") == "main" else "反应"
        beat_no = int(row.get("beat") or 0)
        beat_intent = beats.get(beat_no) or ""
        if row.get("split"):
            # 拆句行必须补「另一半」：把本拍完整内容摊给它看，否则它只能
            # 复述拍主刚说的那句（校验会判「没补出本拍另一半内容」）。
            half = str(row.get("split_half") or "").strip()
            role += (
                "（拆句·后半：本拍完整内容是「"
                + beat_intent
                + "」，拍主只说其中一块，你只说剩下的那块"
                + (f"，也就是「{half}」" if half else "")
                + "，不许重复拍主那块）"
            )
        elif row.get("role") == "main":
            role += "（若本下标了拆句，你只说其中一块，剩下那块归拆句行）"
        elif str(row.get("speaker") or "").strip() in (
            no_material_speakers or set()
        ):
            # 源故事里这个角色根本没出声（#144 的旁观角色灿灿）：要求它「给新信息」
            # 容易变成转述，但放它写「旁观/递话/安抚」必被判接不上/错位/旁白
            # （#154 两轮实测：「你先别急」「把话交回给灿灿」）。只许写当场
            # 一句短反应，扣住上一句的具体词。
            role += (
                "（无素材：只写当场一句短反应，扣住上一句的具体词；"
                "禁安抚/催促/递话/旁白，不许凭空加人/物件）"
            )
        table.append(
            f"{idx}. 第{beat_no}拍｜{row.get('speaker')}｜{role}"
            + (f"｜本拍内容：{beat_intent}" if beat_intent and not row.get("split") else "")
        )
    fb = f"\n{feedback}\n" if feedback else ""
    return (
        f"【源故事（只准用这里已有的信息）】\n{story_raw or '（无）'}\n\n"
        f"【这一篇要排的对白（说话人、拍号已定，不许改）】\n"
        + "\n".join(table)
        + f"\n\n【场景】\n"
        f"地点：{scene_contract.get('location') or ''}；"
        f"现场物件：{scene_contract.get('object') or ''}\n"
        f"故事核：{scene_contract.get('conflict') or ''}\n"
        f"收束：{scene_contract.get('closing_intent') or ''}\n"
        f"在场角色：{cast or '（未给出）'}\n"
        f"{fb}\n"
        f"【输出】{{\"lines\": [{{\"i\": 1, \"intent\": \"…\"}}, …]}}，"
        f"只填上面列出的 {sum(1 for r in rows if not r.get('from_beat'))} 行，"
        f"其余行的 intent 已按拍意图写定，不要输出，不要解释。"
    )


# source 路径覆盖关系：角色/顺序/字数/标点留在机检；问答、人物归属、
# 事实前提、句子完整、重复、旁白、接话与无新事实交逐行 source_audit。
# 原全文硬卡、类型结构分与导出门槛共用，不以本提示替代终验。
SOURCE_BATCH_SYSTEM = """你是对白编剧，任务是润色扩写简略素材，写成自然家庭对白，只输出JSON。
序号、说话人、内容单元归属与顺序不可改变；台词措辞需要你改写，不是抄写素材表。所有素材都须完整表达，不能删事实。
content行表达自己被分配的素材；reaction行仅对已出事件表态或追问，不能代说后续答案、补新事实、空转或重复。原文中尚未在前面台词交代的细节，也不能被reaction提前说出。
回忆/引用过去的对话要让人称明确；人物是在聊天，不是在念舞台动作。每句完整，前后问答自然，不能为了凑字添前情。
回忆里的第一/二人称反问须明确引用对象，例如“我问他……”，不能把原对话的受话人换成当前聊天的人。
每句含标点8–24字，reaction至少14字；按每槽目标写足表达，可补清省略的说话对象与回忆指代，不能用重复或新前情凑字。
N类须自然具备设问、追问、孩子自洽、末段大人服了或接不住。若表达契约为rhetorical，自洽通过来源反问成立，追问保留原有问答形态，不硬塞为什么/因为/所以；没有此契约时使用显式追问与因果表达。
这些类型功能须服务素材，不可为了塞词改变问题或发明理由；不要强迫某个固定位置携词。
只输出 {"lines":[{"i":1,"line":"台词"}]}，不输出角色名或解释。
"""

def format_source_revision_user(
    *, scene_contract: dict, slots: list[dict], filled: dict[int, str],
    failures: list[tuple[int, str, str]], source_text: str,
) -> str:
    """只交付失败行的编辑任务；完整候选只提供上下文，不重复整表填词。"""
    global_repair = any(i == 0 for i, _, _ in failures)
    reasons = {i: why for i, _, why in failures}
    targets = [
        {"i": i, "speaker": slot["speaker"], "source_meaning": slot.get("intent"),
         "current_line": filled.get(i, ""), "must_fix": reasons.get(i, reasons.get(0)),
         "speech_act": slot.get("planned_speech_act")}
        for i, slot in enumerate(slots, 1) if global_repair or i in reasons
    ]
    context = [{"i": i, "speaker": slot["speaker"], "line": filled.get(i, "")}
               for i, slot in enumerate(slots, 1)]
    return (
        "改写下列失败句，保留全部素材含义。字数不足时补清原本省略的角色、对象、回忆指代；"
        "不要照抄原句，不添加事实，不重复填词。每句最多24字，按must_fix给出的目标完成。\n"
        f"【需要改写】{json.dumps(targets, ensure_ascii=False)}\n"
        f"【只读全文上下文】{json.dumps(context, ensure_ascii=False)}\n"
        f"【只读原始素材】{source_text}\n"
        f"【类型表达契约】{json.dumps(scene_contract.get('gold_n_expression_contract'), ensure_ascii=False)}\n"
        "只输出需要改写的行，其余行由程序原样保留："
        '{"lines":[{"i":原序号,"line":"改写后的完整台词"}]}。'
    )


SOURCE_LINE_PLAN_SYSTEM = """你为家庭对话稿补充接话意图，只输出 JSON。
分句计划已按已有素材的说话人和先后顺序锁定，content 行不许改。
你只填写 reaction 行的 intent。只回应上一句的具体内容，不引入新事实，不抢说后面的答案。
前一句是问题时，回应必须正面回答，不能转移话题；不得重复前后内容句的意思。
若反应句要追问，必须确认后一条已锁定素材能够回答它；否则写陈述式反应，不留下悬空问题。
结合源文辨清回忆和现场：引用中的你们指原对话对象，不自动指在场的家人。
先在心里逐行试读，确保接话不重复前面的提问，不把新话题硬塞到原答案前面。
接话可指出已出说法或行为之间的反差，但不要发明新的常识判断、替原稿纠错或补一个无人提过的前提。
接话是现在听完后的评价，不续演过去现场，不猜当时另一个人怎样想/怎样回应。不要为迎合整体故事核，硬把一条本来正确的回答说成无效；每句只评已说出的具体内容。
原素材孩子的误答已由content承担；reaction要按前文真实含义接话，不能另造错误判断并把它当新的歪理笑点。
不要写‘我不信/越听越玄乎/你继续说/我就在旁边听着’等通用空话，也不写动作或神态。
输出 {"lines":[{"i":需要填写的行号,"intent":"这句要表达的具体内容"}]}。
"""


def format_source_line_plan_user(
    *, scene_contract: dict, seed: list[dict], story_raw: str,
    rows: list[dict], feedback: str = "",
) -> str:
    table = [{"i": i, "speaker": r["speaker"], "role": r["role"], "intent": r.get("intent")}
             for i, r in enumerate(rows, 1)]
    picks = [i for i, r in enumerate(rows, 1) if r["role"] == "reaction"]
    tasks = [{"i": i, "speaker": rows[i - 1]["speaker"],
              "heard_content": [r for r in table[:i - 1] if r["role"] == "content"],
              "next_content": next((r for r in table[i:] if r["role"] == "content"), None)}
             for i in picks]
    scene = {k: scene_contract.get(k) for k in ("location", "characters", "conflict", "closing_intent", "story_type")}
    return (
        f"【接话任务】{json.dumps(tasks, ensure_ascii=False)}\n"
        "每句接话只可使用该任务heard_content里已经说出的事实；next_content只用来检查衔接，不能提前代说。"
        "反应只说当前听者的评价，不编原事件里别人当时的反应；若后句不回答，就不要新增问句。\n"
        f"【场景】{json.dumps(scene, ensure_ascii=False)}\n"
        f"【只读完整分句计划】{json.dumps(table, ensure_ascii=False)}\n"
        f"【原故事，仅供辨明指代】{story_raw}\n"
        f"只补行号{picks}的接话意图，其他行保持不变。"
        "每个接话位最终需要8–24字，须接住前一句具体内容且不抢后一句的事实。"
        "同一拍里原说话人的两段回答已各占一行，不要让另一个孩子代说后半段。"
        f"\n上一版错误：{feedback or '无'}\n"
        '输出 {"lines":[{"i":行号,"intent":"具体接话内容"}]}。'
    )


REVISE_SYSTEM = """你是家庭对话稿的修稿人。给你一篇已经写好的对白和审读意见，
你只改被点名的那几行，其余行一个字都不许动。

规则：
- 只输出被点名的行，格式 {"lines":[{"i":3,"line":"…"}]}，不要解释、不要输出其它行。
- 改写后仍要满足：与上一句咬合（上一句是问句就必须正面回答）、说人话、
  8–24 字、不写动作/旁白、不替别人说话。
- 不许引入前文没有的人物、物件、事件；不许指认对方说过没说过的话。
- 能不改说话人就不改，必须换人时在 JSON 里带上 "speaker"。
"""


def format_revise_user(
    *,
    dialogue: list[dict[str, str]],
    issue_text: str,
    indices: list[int],
    feedback: str = "",
) -> str:
    """把整篇对白与审读意见交给修稿人，只要求改点名的行。"""
    rows = "\n".join(
        f"{idx}. {item.get('speaker') or ''}：{item.get('line') or ''}"
        for idx, item in enumerate(dialogue, 1)
    )
    picks = "、".join(f"第{i}句" for i in indices)
    return (
        f"【对白】\n{rows}\n\n"
        f"【审读意见】\n{issue_text or '（无）'}\n\n"
        f"【只改这些行】{picks}\n"
        + (f"【上一版改完仍不合格】{feedback}\n" if feedback else "")
        + f"输出 {{\"lines\":[{{\"i\":{indices[0] if indices else 1},\"line\":\"…\"}}, …]}}"
    )
