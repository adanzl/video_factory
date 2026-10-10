"""H0c/H2/H3/H3b：金故事 LLM 结构化。"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.services.gold_story.types import (
    GOLD_STORY_MECHANISM_CODES,
    GOLD_STORY_MECHANISM_LABELS,
    GOLD_STORY_TYPE_CATALOG,
    align_mechanism_structure,
)
from app.services.gold_story.scene import (
    PARENT_SPEAKER_LABELS,
    SEED_MIN,
    age_remap_contract_errors,
    apply_parent_role_budget,
    fact_attribution_review_required,
    filter_fact_bound_rows,
    force_age_score_remap,
    normalize_dialogue_setting_for_contract,
    normalize_fact_attributions,
    normalize_k_parent_intervention_budget,
    normalize_retrospective_topic_contract,
    normalize_retrospective_n_opening_parent_beats,
    normalize_scene_dialogue_beats,
    realign_parent_identity_rows,
    remap_story_raw_scores_for_prompt,
    sanitize_banned_literals,
    seed_from_beat_chain,
    trim_terminal_no_reply_rows,
    validate_scene,
)
from app.services.gold_story.gold_chat.setting import (
    format_place_catalog_for_prompt,
    normalize_scene_contract_location,
)
from app.services.gold_story.structure_resolve import resolve_h3_structure
from app.services.llm.llm_mgr import llm_mgr

# 金稿正例：只允许引用已入库金故事原文；prompt 内禁止自造示范句。
GOLD_H3A_SCENE_SNIPPET = """【金稿 scene_contract · BV1ND4y1X7Mm《灵魂拷问一招制敌》】
location: 车内
object: 爱学习的定义
conflict: 灿灿：我爱学习你爱吗？
mechanism: 双标规则：学习哭vs玩不哭
beat_chain:
1. 灿灿：立规：以爱学习为标准质问昭昭
2. 昭昭：字面执行：用爱姐姐转移话题
3. 灿灿：加码：用学习哭vs玩不哭双标回击
4. 昭昭：反杀：无言以对，委屈看窗外
5. 灿灿：嘴硬：一招制敌
closing_intent: 灿灿得意总结一招制敌
"""

GOLD_H3B_SEED_SNIPPET = """【金稿 dialogue_seed · BV1ND4y1X7Mm】
- 灿灿: 我超爱学习，你爱吗？
- 昭昭: 我……我也爱吧。
- 灿灿: 那你怎么老不写作业？
- 昭昭: 可我更爱你呀。
- 灿灿: 少来这套，转移话题。
- 灿灿: 让你学习你哭哭啼啼。
- 灿灿: 让你玩你咋不哭呢？
- 昭昭: ……（委屈看向窗外）
- 灿灿: 哼，一招制敌。
"""

GOLD_CHAT_LINES_SNIPPET_SOURCE_ID = "BV1sh411G7aX"

GOLD_CHAT_LINES_SNIPPET = """【金稿对白 · BV1sh411G7aX《画作争夺战》】
灿灿：昭昭，你趴那儿弄啥呢？让我瞅瞅。
昭昭：不行！这是我的秘密，你不能看！
灿灿：哼，小气鬼！我偏要看！
昭昭：你走开！再抢我打你了！
灿灿：你敢！哎呀！你推我！
昭昭：谁让你抢的！我也弄坏你的画！
灿灿：你赔！我额头都蹭破了！
昭昭：呜……对不起嘛，我不是故意的。
灿灿：谁先动手谁道歉！哼，我不原谅！
妈妈：别打了！谁先动手的？
昭昭：我……我先推的，姐姐对不起！
妈妈：以后还打不打架？
昭昭：不打了！
灿灿：不打了！这还差不多。
妈妈：我去拿碘伏，你额头上还没涂呢。
"""

GOLD_CHAT_LINES_SNIPPET_SAME_SOURCE = f"""【同源金稿 · 不注入全文正例】
本稿与金稿对白正例同源（{GOLD_CHAT_LINES_SNIPPET_SOURCE_ID}），
禁止按正例句数/字数复现。
须按上方 scene_contract.beat_chain + dialogue_seed
写到目标 280–340 字、12–16 轮（硬卡 240–370，最多 18 轮）。
**未满 240 字禁止收束**；写够后立刻闭合，禁止循环注水/复读。
语气参考 M5+H：互毁双向、拒和加码、妈妈分层调解；
勿连续两句照抄 seed。"""


def resolve_gold_chat_snippet(source_id: str) -> str:
    """同源金稿不注入全文正例，避免 LLM 锚定在 ~180 字短稿。"""
    sid = str(source_id or "").strip()
    if sid == GOLD_CHAT_LINES_SNIPPET_SOURCE_ID:
        return GOLD_CHAT_LINES_SNIPPET_SAME_SOURCE
    return GOLD_CHAT_LINES_SNIPPET

logger = logging.getLogger(__name__)

# 逐字稿「听不懂」占位标记：H0c 产出，H2/H3b 都不得把它展开成对白。
UNINTELLIGIBLE_MARKER = "[听不清]"

# story_raw 里带占位标记的引语 → 非引语概括（动作/氛围，不给下游对白来源）
_UNINTELLIGIBLE_SUMMARY = "嘟囔了一句听不清的话"
_QUOTED_UNINTELLIGIBLE_RE = re.compile(
    r"[“\"「『][^”\"」』]*"
    + re.escape(UNINTELLIGIBLE_MARKER)
    + r"[^”\"」』]*[”\"」』]"
)

_H0C_SYSTEM = (
    "你是短视频口播逐字稿修复师。输入为 faster-whisper 自动转写："
    "有错字、断句乱、分不清说话人。\n"
    "结合标题/简介推断角色，修正同音错字，按对话拆行并标注说话人。\n"
    "**不要假设说话人严格交替**：ASR 没有可靠说话人标签，须按语义归属判定，"
    "同一角色可以连说多行；判不定就写「未知」，不得为凑交替硬拆。\n"
    "不要编造视频中未出现的情节；听不清处用 [听不清]。\n"
    "不许把听不懂的碎片改写成通顺台词：无法在不编造信息的前提下恢复语义时，"
    "保留 [听不清] 标记；整行都不可恢复时只输出「角色：[听不清]」。\n"
    "每句还要做指称自洽：当前说话人不得自称对方身份；"
    "复述/回旋镖他人原话时须按当前说话人重算「我/你」。\n"
    "只输出 JSON。"
)

_H0C_USER = """视频标题：{title}

【简介】
{description}

【ASR 原文（可能有错，一行或多行）】
{transcript}

输出 JSON：
{{
  "speakers": ["妈妈", "宝宝"],
  "lines": [
    {{"speaker": "妈妈", "text": "修正后的这一句", "status": "ok"}},
    {{"speaker": "宝宝", "text": "…", "status": "ok"}}
  ],
  "repair_confidence": 0.0,
  "repair_notes": "一句说明推断依据"
}}

规则：
- speaker 用简短称谓：妈妈、爸爸、宝宝、女孩、男孩、哥哥、妹妹等；
  判不定时写「未知」（并照常标注 status），在 repair_notes 说明
- **归属按语义，不按行序**，判据优先级：
  ①身份自称/关系自称（「我是你妈/我是你爸」等）只能归对应家长，
  除非处于引述、反问回声、扮演框架；
  ②第一人称承认/辩解/自曝自己做过某事的句子，归做过那件事的人，
  但引述、反问、回旋镖句除外；判「谁做过」以标题/简介与上下文为准
  （标题点明是谁的糗事就按标题），不要只按句式猜；
  ③指认、质问、要求、命令句看对象与冲突推进方向
- **允许同一 speaker 连说多行**：相邻句语义/语气接续像同一人（如把话补完、
  连说两句压人）时写成同一 speaker 的连续行，禁止为凑交替硬拆成两人
- 合并 ASR 误切的碎句；修正明显同音错字（结合语境，勿脑补新剧情）
- **每行必须带 status**：`ok`（语义可判）| `vague`（部分可判）| `unusable`（整行不可判）
- **不可恢复判据**：①只剩语气词/拟声/重复音节；②同音碎片拼起来仍无稳定交际意图；
  ③要靠视频里没有的信息才讲得通；④只能猜大意，定不了说话对象或目的
- 整行不可恢复时：`text` 写 `[听不清]`，`status` 写 `unusable`；
  **禁止把听不懂的 ASR 原文抄进 text**，也禁止补词改写成通顺台词
- 只有局部不可恢复时：保留可确定部分，碎片处写 `[听不清]`，`status` 写 `vague`
- **人称自洽**：当前说话人不得自称对方身份；复述对方原话时，
  原话里的「我」指原说话人的要改成「你」，「你」指当前说话人的要改成「我」；
  转换后不通则改成概括说法，不得照抄错误指称
- repair_confidence 只表示说话人/断句把握，不表示句子通顺
- **合并连续重复的同一短语**，只保留 1–2 次
- lines 至少 2 条；repair_confidence<0.35 视为失败
- ASR 再差也要尽力修复；confidence 表示角色/断句把握（≥0.5 为佳，≥0.35 可接受）
- text 字段不要重复 speaker 前缀
"""

_H2_SYSTEM = (
    "你是站外短视频故事抽取器。从逐字稿/热评/简介中选出 **一条** 微型故事"
    "（80–400 字第三方叙述），含冲突、升级、收束。\n"
    "若逐字稿为口播/科普/经验分享（博主对着镜头讲方法），"
    "须从中 **还原一个具体可拍现场**（谁在哪做了什么），"
    "禁止只写方法论摘要或「第几招」清单。\n"
    "合集多梗时只取最好笑的一条。\n"
    "只输出 JSON。"
)

_H2_USER = """视频标题：{title}

【逐字稿】
{transcript}

【简介】
{description}

【热评摘录】
{replies}

输出 JSON：
{{
  "story_raw": "第三方叙述全文…",
  "source_type": "field | tutorial | mixed",
  "perspective": "third_person | mixed | direct_dialogue",
  "has_complete_arc": true,
  "extract_confidence": 0.0
}}

规则：
- story_raw **必须 80–400 字**；太短（单句笑话/只有一个梗）一律 has_complete_arc=false
- 口播/科普/教程：source_type=tutorial，须改写 **一个姐弟可拍现场**，禁「第几招」清单
- 角色允许昭昭、灿灿、妈妈、爸爸；陌生小孩须映射或删除。
  源稿是爸爸且妈妈代不了时保留爸爸；能用妈妈就用妈妈；
  单孩+家长须拆成昭昭+灿灿双孩戏份，家长仍配角。
  不得保留站外真名/小男孩/对方等在 story_raw
- 优先选热评里 **整段复述**（有然后/最后/被问/嘴硬）的完整微型故事
- has_complete_arc=false 或 extract_confidence<0.5 即失败
- **引号只给有效对白**：语义完整、说话人与目的可判定的才可加引号；
  逐字稿里 [听不清] 或语义不通、听不明白的碎片 **禁止**写进引号，
  也禁止补词把它改成台词
- **归属自洽（硬）**：引号对白必须是「这个角色说得出口」的话——
  孩子不得自称家长身份（「我是你妈/我是你爸」），
  也不得承认只有家长做过的事；被指认方与指认方要分清。
- **标题是事实层的最强线索**：标题/简介写明某人抱怨、揭发另一方做过某事时，
  该事归 **被抱怨/被揭发那一方**；标题里出现「都背着我」「不告诉我」这类
  被排除表达时，说这话的人是抱怨方，另一方才是做过那件事的人。
  逐字稿推断与标题冲突的，以标题为准改正归属。
  H0c 归错的和句子本身冲突的，按标题/简介/语义重新归属，
  仍判不定的写成非引语概括（如「有人用把柄反将一军」「家长心虚否认」），
  不得把错位原话写进引号
- 结尾碎念只作氛围：写成非引语概括（如「嘟囔了一句听不清的话」），不加引号；
  若尾部只剩听不清碎片，按已发生的收束事件收尾；
  删掉后不足 80 字用动作/环境/心理补足，不新增事件
- 不要输出 quote 字段；引号对白保留在 story_raw 内
"""


_H3_SYSTEM = (
    "你是金故事结构化师。输入 story_raw，输出机制 M 码 + 结构类型 + beat。\n"
    "mechanism 必须是 M1–M15 之一；structure_type 必须是 A–E、F、G、H、I、J、K、L、N、O、P 或 Q。\n"
    "M5 拒和加码：纯姐弟内部僵持→A；有妈妈/第三方调解收束→H；"
    "否决权/拒放行压住且不翻车→J（禁止套 A 反噬）。\n"
    "M8 泛一锤：后续有反噬/破功→A；一锤镇住对方怂、不翻车→J。\n"
    "M11 价值高地灵魂拷问/不可答问题→I（赢家嘴硬，无反噬）。\n"
    "M12 家长旁观：互打互骂升级、大人躲/叹/劝失败、僵持不和好→K；"
    "禁止套 H（H 必须有定责劝和+仪式性和好）。\n"
    "M6 正经胡说/童化歪理：设问→离谱答→追问→荒诞自洽→愣住→N；"
    "禁止把无回旋镖的正经胡说标成 M2+C；偶发权威反噬→A，妈妈改口破功→E。\n"
    "M13 顾赛不顾奖：立赛规→死磕过程/赢赛→资源溜走→点题认栽→O；"
    "禁止把「光顾着赢、奖品没了」标成 M2+C（无双规则互戳回旋镖）。\n"
    "M14 以牙还牙：道具整蛊/挑战下料→硬撑或自食→回敬加码→认怂散场→P；"
    "禁止把整蛊互整标成 M2+C；口头威胁互呛无道具回敬→M3+F。\n"
    "M15 耍赖翻车：立玩法→耍赖/借口加码→被拆穿→反噬收场→Q；"
    "与 E 妈妈破功对仗（E=大人被绕穿；Q=孩子被拆穿）；"
    "禁止把「看穿洗碗」亲子反将硬套 M14+P。\n"
    "M7 字面执行：须歪读跑偏且叮嘱方破规+原话回旋镖→D；"
    "**禁止**仅因出现「规矩/谁…谁…」就标 M7。\n"
    "M4 嘴硬心软：立规/互怼后真情或反转示好→对方愣住→暖收→G；"
    "立规后孩子争着帮忙/抢活、家长愣住暖心→M4+G（不是 M7+D）。\n"
    "M2 双规则/自私包装公平：须双方各执公平判据且同场回旋镖引原话→C；"
    "若收束为拒领点破表演公平→L；若收束为灵魂拷问问倒→M11+I。\n"
    "禁止把 M2+C 用于武力扭打/一锤 KO：仅有「谁赢了谁说了算」单方定规、"
    "对方认输/怂、或「长大再算账」延后不服→M8+J（镇住不翻车，非双规则回旋镖）。\n"
    "**严禁默认套 M2+C**：缺「双规则+同场回旋镖」任一条件时禁止标 M2+C；"
    "宁可 structure_confidence<0.5 让本步失败，也不硬套。\n"
    "下列一律禁止标 M2+C（confidence 须 <0.5）："
    "纯温馨哄娃/感动拥抱无争；婴语「我爱你」纠正；夫妻/家长理性共识无孩子对手戏；"
    "成人恋爱抢对象/片场醋意。\n"
    "孩子与家长趣味冲突（抽签耍赖、逞强被回敬、追问破功）可标对应 M/结构，"
    "不必改成姐弟公平战。\n"
    "beat 4–6 步，禁止贴 story_raw 原文。\n"
    "只输出 JSON。"
)

_H3_USER = """视频标题：{title}

story_raw：
{story_raw}

机制表（M 码）：
{mechanism_table}

结构类型 A–E / F / G / H / I / J / K / L / N / O / P / Q：
{type_catalog}

输出 JSON：
{{
  "title": "短标题",
  "conflict_core": "一句话冲突核",
  "funny_why": "为何好笑",
  "mechanism": "M2",
  "structure_type": "C",
  "theme_family": "占有|消耗|结盟|操作 等",
  "beat": ["…", "…", "…", "…"],
  "banned_literals": ["…"],
  "structure_confidence": 0.0,
  "structure_mapping_note": ""
}}

banned_literals 规则（仅填 remap/真名，勿填场景与笑点词）：
- **可填**：站外真名（如贾西西）、须 remap 的称谓（哥哥/妹妹/小男孩/对方）
- **禁止填**：场景本体（画画/画作）、可拍道具与动作（碘伏/涂药）、
  笑点细节、叙述/meta（朋友圈/发视频）、object/conflict 已有词
- 换物/换说法写在 structure_mapping_note，不要靠禁词删场景
"""


_H3A_SYSTEM = (
    "你是金故事场景契约师。把 story_raw 转成昭昭(7岁弟)/灿灿(10岁姐) **可拍现场契约**。\n"
    "口播/教程须强制 remap 为姐弟现场：施教方→灿灿(立规)，被教方→昭昭，陌生小孩→灿灿(占物)。\n"
    "characters 允许昭昭/灿灿/妈妈/爸爸；"
    "源稿是孩子与家长趣味冲突时 **保留妈妈/爸爸为配角对手**，"
    "**禁止**把戏核家长硬映成灿灿/昭昭；单孩可加另一孩旁观或联手，但勿偷换对手。\n"
    "源稿 beat 含家长责备/反问/定责/破功等戏核拍时：**必须**把妈妈（或爸爸）留在 "
    "characters 与 beat_chain，**禁止**为「压成两人」把家长台词并进姐弟。\n"
    "学段与分数须按 7–10 岁迁校：中考/高考/成人考分口吻改成小学可拍量级"
    "（百分制或两三科合计），保留高低分对比梗，禁止原样保留不可能的总分。\n"
    "上方金稿正例只供格式参考；**禁止**把正例 object/口号抄进本稿，"
    "除非 story_raw / beat 本身已有该梗。\n"
    "能用妈妈就用妈妈，源稿爸爸且代不了才保留爸爸；beat_chain 至少 4 拍。\n"
    "只输出 JSON。"
)

_H3A_USER = """视频标题（角色分工的最强线索，须据此还原谁做了/谁被揭发）：
{video_title}

H3 结构化：
{h3_json}

story_raw：
{story_raw}

source_type：{source_type}

{gold_scene_snippet}

允许地点表（location 须从中选一，可拍室内锚点）：
{place_catalog}

输出 JSON：
{{
  "story_type": "C",
  "source_type": "field|tutorial|mixed",
  "location": "可拍地点",
  "characters": ["灿灿", "昭昭"],
  "object": "争的具体物品或话题",
  "conflict": "姐弟当场冲突一句",
  "mechanism": "来自 story_raw 的可拍规则/机制一句",
  "facts": [
    {{
      "fact_id": "F1",
      "event": "把柄/秘密事件（只写发生了什么，不写谁）",
      "secret_holder": "实际做过/拥有秘密的人",
      "discoverer": "发现的人",
      "accuser": "指认/揭发的人",
      "denier": "否认/辩解的人",
      "claimant": "索赔/讨要补偿的人",
      "beneficiary": "从中得利的人",
      "attribution_status": "resolved|ambiguous|review_pending",
      "attribution_basis": ["title|claim_direction|defense_pattern|evidence_source"],
      "attribution_confidence": 0.0,
      "role_play": false,
      "quotation_frame": false
    }}
  ],
  "beat_chain": [
    {{
      "beat": 1,
      "speaker": "灿灿|昭昭|妈妈|爸爸",
      "intent": "立规/占物/…",
      "addressee": "对谁说",
      "speech_act": "accuse|deny|admit|claim_compensation|echo|other",
      "claim_role": "accuser|secret_holder|claimant|…",
      "fact_ref": "F1"
    }}
  ],
  "closing_intent": "末句嘴硬/反转",
  "mom_lines_max": 0,
  "remap_note": "站外角色如何映射（孩子vs家长须保留家长；能用妈不用爸）",
  "banned_literals": ["…"],
  "contract_confidence": 0.0
}}

banned_literals：同 H3，仅 remap 称谓与站外真名；禁止填画画/碘伏/朋友圈等场景与笑点词。

事实角色（facts）规则：
- 每个**把柄/秘密/专属过错**事件拆成角色槽位：谁做过（secret_holder）、
  谁发现、谁指认、谁否认、谁讨要补偿；取值只能来自 characters；
  不确定写 `unknown`，**禁止猜**
- **标题/简介是事实层最强线索**：与逐字稿推断冲突时以标题/简介为准；
  标题里抱怨方是 accuser/discoverer，被背着/被揭发的那一方才是 secret_holder
- 判不出 secret_holder 时 `attribution_status=ambiguous`，
  **禁止**为了故事完整硬指定
- 引述家长原话、过家家扮演的事件标 `quotation_frame`/`role_play=true`
- 与事实相关的拍必须带 `fact_ref` + `speech_act` + `claim_role`；
  与事实无关的拍可不标

规则：
- object/conflict/mechanism **须能在 story_raw 找到依据**；禁止发明 story_raw 没有的物品/仪式/场景
- object：争的具体物品或话题；双方各持一物时两件都写入 object
- **回忆/旧事/过去经历类 object 只是当前谈话主题**：禁止把历史物件搬进当前场景，
  也禁止用“旧物/收纳筐/替代物”复刻过去事故；location 只写现在聊天发生的地点
- location：须为允许地点表中的 place；站外场景选最接近的一项（如车内→卧室，午休垫→地板）
- 禁止无依据套用站内仪式模板（举过头顶/三秒/单脚站/金鸡独立等）
- **禁止**把妈妈/爸爸映成灿灿或昭昭来「制造姐弟戏」；家长是对手就留在 characters
- **禁止**因「妈妈少出场」默认就压成昭昭+灿灿两人；H3 beat 写了家长行动，
  characters/beat_chain **必须**保留对应家长 speaker
- **迁龄（硬）**：站外中考/高考/大学/成人职场考分 → 改写成 7–10 岁小学语境；
  分数用小学可拍量级（如单科百分制差分 vs 高分，或两三科合计），
  保留「差分被宣传挨骂 / 高分被宣传该谢」一类对比；禁止原样保留不可能的总分口吻
- **姐弟映射（硬）**：源稿妹妹/弟弟→昭昭，姐姐/哥哥→灿灿；家长保留妈妈/爸爸；
  conflict/beat_chain/remap_note 须用站内名，勿混用妹妹/姐姐称谓
- 同一稿分数口径须统一（conflict/object/beat_chain/remap_note 同一考分），
  禁止同篇混写两个不同百分制分值
- C类 beat_chain：争资源→双规则（每轮新判据）→三轮升级→同场回旋镖→嘴硬（至少4拍）；
  **禁止**把单方「谁赢了谁说了算」+武力压制+认输标 C；
  **禁止**把道具整蛊互整（下料→回敬→认怂）标 C（应 M14+P）
  **禁止**把耍赖被拆穿反噬（抽签/借口/看穿）硬套 M14+P（应 M15+Q）
- P类 beat_chain（**须 4–6 拍**）：下料/挑战递物→硬撑或自食→回敬加码→认怂散场；
  禁止 C 回旋镖、G 暖收、F 纯口头威胁当主戏
- J类与 C 边界：J=一锤镇住对方怂/不敢再顶；C=双规则同场回旋镖引原话
- I类 beat_chain（**须 4–6 拍**）：争锋/互怼→立价值标准→灵魂拷问→对方语塞→赢家嘴硬总结；
  禁止 A 末四拍反噬/破功；closing 须赢家一招制敌；
  若灵魂拷问/冰箱类反问由家长说出，speaker 写妈妈（或爸爸），勿并给姐弟
- J类 beat_chain（**须 4–5 拍**）：闹/求放行/试探权威→一锤威慑或否决压住
  →对方怂的**可说出台词**→家长旁观或感叹（可无）；若结果只是“沉默/不再接话/不再顶”，
  不得单列 beat，直接作为 closing 效果；禁止 A 末四拍反噬/破功
- N类 beat_chain（**须 4–6 拍**）：前提/怪回答→对方设问或追问→一本正经荒诞解释
  →继续追问→荒诞自洽→对方接不住（可并拍）；每一拍都必须推动问答逻辑。
  **禁止**在前提与荒诞反驳之间塞“某人附和/帮腔说他说得对”这种只重复前提的拍；
  回忆型 N 可由家长首拍交代旧事，随后直接让孩子质疑/反驳/追问
- K类 beat_chain（**须 4–6 拍**）：互打互骂升级→大人躲/叹/劝失败→僵持；
  禁止写成第三方和好（勿套 H 定责劝和+仪式性和好）
- H类 beat_chain（**须 6–8 拍**，逐步写清，禁止合并跳步）：
  1 抢看/占物 → 2 拒看/推搡 → 3 **双向互毁**（谁先弄坏谁+报复，须对称）
  → 4 伤情可拍 → 5 哭腔道歉 → 6 M5拒和+加码（不原谅，妈妈介入前）
  → 7 妈妈问谁先动手+定责劝和 → 8 仪式性和好/碘伏/收场
  M5+H 时 object 须是 story_raw 争物（如画作），勿改成「抢秘密」替代互毁
- **正例只允许上方金稿原文**；本稿须按 story_raw 写，禁止把金稿场景套到本稿
- **归属自洽（硬）**：beat_chain 每拍写「谁对谁做什么、谁说哪类话」；
  身份主张、承认/否认、指认/反指认三类拍，
  归属必须与视频标题/冲突推进方向一致（标题点明谁被揭发、
  谁的糗事，就按标题分工），不得把被揭发方的自曝/辩解写成揭发方的话；
  孩子不自称家长身份、不承认家长做过的事。
  逐字稿归属可疑或标「未知」时，只写功能不写原话
  （如「孩子用家长把柄反将一军」「家长心虚否认」）
- mom_lines_max：H 类 2–3；K 类 1–2（旁观叹气）；
  源稿/beat 含家长戏核拍（责备/反问/定责/破功/旁观）时 **至少 2**（I/E/Q 等同类）；
  纯姐弟无家长戏才可 0；最多 3；禁止为压两人强行写 0
- 禁止 characters/beat_chain 出现陌生小孩/对方；爸爸仅源稿需要且妈妈代不了时保留
- tutorial 源禁止 mechanism/conflict 含「四招/方法/应该/告诉」
"""


_H3B_SYSTEM = (
    "你是金故事对话化师。根据 scene_contract.beat_chain 展开 dialogue_seed。\n"
    "intent 必须能转成一句角色可说出口的现场对白；动作只能伴随对白，"
    "纯沉默/低头/不再接话不能单独成为 seed。\n"
    "intent 只能来自可判定的有效对白或 beat_chain 的拍："
    "听不清碎片、[听不清] 占位、纯语气词、语义不通的短句一律不得成为 intent。\n"
    "每条 intent 还要 speaker 自洽：孩子不得自称家长身份（「我是你妈/我是你爸」），"
    "也不得把家长的自曝/辩解写成孩子的话。\n"
    "dialogue_seed 至少 4 条，建议 12–20 条短 intent；只输出 JSON。"
)

_H3B_USER = """视频标题（角色分工的最强线索，须据此还原谁做了/谁被揭发）：
{video_title}

scene_contract：
{scene_contract_json}

H3：
{h3_json}

story_raw（背景，勿照抄）：
{story_raw}

{gold_seed_snippet}

输出 JSON：
{{
  "setting": "地点 + 谁面前/端着哪件冲突物",
  "dialogue_seed": [
    {{"speaker": "昭昭|灿灿|妈妈|爸爸", "intent": "…",
      "addressee": "对谁说",
      "speech_act": "accuse|deny|admit|claim_compensation|echo|other",
      "claim_role": "accuser|secret_holder|claimant|…",
      "fact_ref": "F1"}}
  ],
  "closing_intent": "与 scene_contract 一致",
  "speaker_map_note": "映射说明",
  "dialogue_confidence": 0.0
}}

规则：
- setting 须含地点；当前场景确有实体冲突物时再写谁持有。若 object 是回忆/旧事/过去经历，
  只写“在该地点聊起旧事”，禁止凭空端出历史物件或替代道具
- 严格按 beat_chain 顺序展开；每拍 1–3 条 seed
- **事实角色绑定（硬）**：与 `facts` 相关的每条 seed 必须带 `fact_ref`/`speech_act`/`claim_role`：
  承认、自曝、否认、辩解句（admit/confess/deny）的 speaker 必须等于该 fact 的
  `secret_holder`；指认、揭发句（accuse/expose）的 speaker 必须等于
  `accuser`/`discoverer`；索赔、讨要句（claim_compensation/demand/bargain）的
  speaker 必须等于 `claimant`/`beneficiary`；回声、回旋镖句（echo/retort）
  按当前说话人重标 `claim_role`，不得沿用对方角色。
  与 facts 冲突时**不要输出该条**，改用 beat_chain 里身份自洽的拍补足
- `facts` 为空或未标注时按 beat_chain 与会话常识展开
- punchline 后若契约效果是“沉默/不再接话/不再顶”，直接结束；这种纯无声结果不得生成 dialogue_seed
- M5+H：seed 须含「双向互毁」「拒和/不原谅」「妈妈问谁先动手」分拍，勿合并
- intent 须来自 scene_contract（beat_chain/conflict/object）+
  story_raw 里 **可判定** 的对白
- **来源排除**：story_raw 里的 [听不清]、语义不通碎片、以及
  「嘟囔/含糊/听不清」一类无具体信息的概括，禁止展开成 intent
- **speaker 自洽（硬）**：身份主张、承认/否认、指认/反指认三类拍，
  归属必须与 beat_chain 的角色分工一致；孩子不得自称家长身份，
  也不得说「我偷吃/我做过」这类只有家长做过的事。
  与 speaker 冲突的 intent 按语义归位；归不了就换一句身份自洽的现场对白，
  不得照抄错位原话
- **回声/回旋镖人称转换**：复述、反问、扣原话时保留对方原话的关键词与攻击点，
  但「我/你」要按当前说话人重算（对方原话的「我」→「你」，
  对方原话的「你」→「我」）；不得让当前说话人自称对方身份。
  转换不自然就改成等价反问或概括，不得保留错误自称
- 过滤后若 seed 不足 4 条，用 beat_chain 里还没被覆盖的拍补足，
  只服务该拍冲突或收束；禁止复述逐字稿乱码，
  禁止引入新事件/地点/道具/人物
- **正例只允许上方金稿原文**；本稿禁止照抄金稿 intent 到不同场景
- speaker 允许昭昭/灿灿/妈妈/爸爸；妈妈 seed 条数 ≤ scene_contract.mom_lines_max
- 若 mom_lines_max≥2 或 beat_chain 含妈妈/爸爸：seed **必须**保留对应家长 intent，
  禁止把家长拍并进姐弟
- **迁龄**：intent/setting 中的分数、学段须已是小学 7–10 岁可拍量级；
  禁止沿用中考/高考不可能总分
- 爸爸 seed 宜更少（能用妈不用爸）；单孩+家长须拆成双孩 intent
- 单条 intent ≤18 字；总 seed ≥4 条
"""


def _client():
    return llm_mgr._get_client()


def _mechanism_table() -> str:
    lines = [
        f"- {code} {GOLD_STORY_MECHANISM_LABELS[code]}"
        for code in sorted(GOLD_STORY_MECHANISM_CODES)
    ]
    return "\n".join(lines)


def _type_catalog() -> str:
    lines = [
        f"- {row['code']} {row['name']}：{row['formula']}"
        for row in GOLD_STORY_TYPE_CATALOG
    ]
    return "\n".join(lines)


def _chat_json(system: str, user: str) -> dict[str, Any]:
    raw, _finish = _client()._chat_json(  # type: ignore[attr-defined]
        system,
        user,
        thinking_enabled=False,
        temperature=0.35,
    )
    if not isinstance(raw, dict):
        raise ValueError("LLM JSON must be object")
    return raw


def repair_transcript(
    *,
    title: str,
    transcript: str,
    description: str = "",
) -> dict[str, Any]:
    """H0c：ASR 逐字稿 → 纠错 + 说话人标注。"""
    transcript_text = str(transcript or "").strip()
    if not transcript_text:
        raise ValueError("H0c missing transcript")
    user = _H0C_USER.format(
        title=title,
        description=str(description or "").strip()[:2000] or "（无）",
        transcript=transcript_text[:12000],
    )
    data = _chat_json(_H0C_SYSTEM, user)
    lines = data.get("lines") or []
    if not isinstance(lines, list) or len(lines) < 2:
        raise ValueError("H0c lines must have at least 2 entries")
    cleaned: list[dict[str, str]] = []
    unusable_lines = 0
    for row in lines:
        if not isinstance(row, dict):
            continue
        speaker = str(row.get("speaker") or "").strip() or "未知"
        text = str(row.get("text") or "").strip()
        status = str(row.get("status") or "").strip().lower()
        if status == "unusable" and text:
            # 整行不可恢复：只留占位标记，禁止把 ASR 乱码留在逐字稿里
            text = UNINTELLIGIBLE_MARKER
            unusable_lines += 1
        if text:
            cleaned.append(
                {"speaker": speaker, "text": text, "status": status or "ok"}
            )
    if len(cleaned) < 2:
        raise ValueError("H0c cleaned lines too short")
    confidence = float(data.get("repair_confidence") or 0.0)
    if confidence < 0.35:
        raise ValueError(f"H0c low repair_confidence={confidence:.2f}")
    speakers = data.get("speakers") or []
    if not isinstance(speakers, list):
        speakers = []
    # 身份自洽兜底：孩子标签的家长身份句归位家长 / 回声句转换人称
    cleaned, identity_notes = realign_parent_identity_rows(
        cleaned,
        parent_labels=PARENT_SPEAKER_LABELS,
    )
    if identity_notes:
        logger.info("H0c parent identity realign=%s", identity_notes[:4])
    return {
        "lines": cleaned,
        "speakers": [str(s).strip() for s in speakers if str(s).strip()],
        "repair_confidence": confidence,
        "repair_notes": str(data.get("repair_notes") or "").strip(),
        "unusable_lines": unusable_lines,
    }


def scrub_unintelligible_quotes(story_raw: str) -> tuple[str, int]:
    """story_raw 里含 [听不清] 的引语改成非引语概括。

    下游 H3b 会把引号内容当对白来源，故不允许带占位符的引语留在叙述里；
    只认标记与引号，不按剧情词过滤。
    """
    text = str(story_raw or "")
    if UNINTELLIGIBLE_MARKER not in text:
        return text, 0
    out, count = _QUOTED_UNINTELLIGIBLE_RE.subn(
        _UNINTELLIGIBLE_SUMMARY,
        text,
    )
    return out, count


def extract_story_raw(
    *,
    title: str,
    transcript: str,
    description: str = "",
    replies: list[str] | None = None,
) -> dict[str, Any]:
    """H2：逐字稿 + 热评 → story_raw。"""
    reply_text = "\n---\n".join(replies or []) or "（无）"
    transcript_text = str(transcript or "").strip() or "（无逐字稿）"
    user = _H2_USER.format(
        title=title,
        transcript=transcript_text[:12000],
        description=str(description or "").strip()[:2000] or "（无）",
        replies=reply_text[:6000],
    )
    data = _chat_json(_H2_SYSTEM, user)
    story_raw = str(data.get("story_raw") or "").strip()
    if not story_raw:
        raise ValueError("H2 missing story_raw")
    story_raw, scrubbed_quotes = scrub_unintelligible_quotes(story_raw)
    if scrubbed_quotes:
        logger.info("H2 scrubbed unintelligible quotes=%s", scrubbed_quotes)
    confidence = float(data.get("extract_confidence") or 0.0)
    has_arc = bool(data.get("has_complete_arc"))
    if not has_arc or confidence < 0.5:
        raise ValueError(
            f"H2 rejected arc={has_arc} confidence={confidence:.2f}"
        )
    if len(story_raw) < 80:
        raise ValueError(f"H2 story_raw too short: {len(story_raw)} chars (min 80)")
    if len(story_raw) > 450:
        story_raw = trim_story_raw(story_raw, max_chars=380)
    return {
        "story_raw": story_raw,
        "source_type": str(data.get("source_type") or "field").strip().lower(),
        "perspective": str(data.get("perspective") or "third_person"),
        "extract_confidence": confidence,
        "has_complete_arc": has_arc,
    }


def structurize_story(
    *,
    title: str,
    story_raw: str,
) -> dict[str, Any]:
    """H3：story_raw → mechanism + beat。"""
    user = _H3_USER.format(
        title=title,
        story_raw=story_raw[:4000],
        mechanism_table=_mechanism_table(),
        type_catalog=_type_catalog(),
    )
    data = _chat_json(_H3_SYSTEM, user)
    mechanism = str(data.get("mechanism") or "").strip().upper()
    if mechanism not in GOLD_STORY_MECHANISM_CODES:
        raise ValueError(f"H3 invalid mechanism: {mechanism!r}")
    mech, st, align_note = align_mechanism_structure(
        mechanism,
        str(data.get("structure_type") or ""),
    )
    data["mechanism"] = mech
    data["structure_type"] = st
    if align_note:
        note = str(data.get("structure_mapping_note") or "").strip()
        data["structure_mapping_note"] = (
            f"{note}；{align_note}".strip("；") if note else align_note
        )
    beat = data.get("beat") or []
    if not isinstance(beat, list) or len(beat) < 4:
        raise ValueError("H3 beat must have 4–6 steps")
    data["banned_literals"] = sanitize_banned_literals(
        data.get("banned_literals") if isinstance(data.get("banned_literals"), list) else [],
        beat=data.get("beat") if isinstance(data.get("beat"), list) else [],
    )
    data, resolve_notes = resolve_h3_structure(data, story_raw=story_raw)
    if resolve_notes:
        note = str(data.get("structure_mapping_note") or "").strip()
        suffix = ";".join(resolve_notes)
        data["structure_mapping_note"] = f"{note};{suffix}".strip(";") if note else suffix
    confidence = float(data.get("structure_confidence") or 0.0)
    if confidence < 0.5:
        raise ValueError(f"H3 low structure_confidence={confidence:.2f}")
    return data


def build_scene_contract(
    *,
    story_raw: str,
    h3: dict[str, Any],
    source_type: str = "field",
    video_title: str = "",
) -> dict[str, Any]:
    """H3a：story_raw → 可拍场景契约。"""
    from app.services.gold_story.scene import remap_story_raw_sibling_roles

    story_raw = remap_story_raw_sibling_roles(story_raw)
    base_user = _H3A_USER.format(
        video_title=str(video_title or "").strip() or "（未知）",
        h3_json=json.dumps(h3, ensure_ascii=False, indent=2),
        story_raw=story_raw[:4000],
        source_type=source_type or "field",
        gold_scene_snippet=GOLD_H3A_SCENE_SNIPPET,
        place_catalog=format_place_catalog_for_prompt(),
    )
    age_retry_hint = (
        "\n\n【迁龄重试硬约束】源稿含高考/中考等成人考语境时，"
        "object/conflict/beat_chain/mechanism **禁止**残留成人考词，"
        "也禁止原样带回 ≥300 的站外总分；须改成小学可拍量级"
        "（百分制或两三科合计），并保留高低分对比梗。"
    )
    data: dict[str, Any] | None = None
    last_age_errs: list[str] = []
    for attempt in range(2):
        user = base_user + (age_retry_hint if attempt else "")
        data = _chat_json(_H3A_SYSTEM, user)
        # 以库内 structure_type 为准，勿被 LLM 默认 C 带偏
        target_st = str(h3.get("structure_type") or "").strip().upper()
        if target_st:
            data["story_type"] = target_st
        else:
            data.setdefault("story_type", "C")
        data["source_type"] = str(
            data.get("source_type") or source_type or "field"
        ).lower()
        data["facts"] = normalize_fact_attributions(data.get("facts"))
        if fact_attribution_review_required(data["facts"]):
            logger.info(
                "H3a fact attribution not resolved: %s",
                [f.get("fact_id") for f in data["facts"]],
            )
        data, _loc_notes = normalize_scene_contract_location(
            data,
            activity_context=story_raw[:800],
        )
        raw_banned = data.get("banned_literals") or h3.get("banned_literals") or []
        data["banned_literals"] = sanitize_banned_literals(
            raw_banned if isinstance(raw_banned, list) else [],
            scene_contract=data,
            beat=h3.get("beat") if isinstance(h3.get("beat"), list) else [],
        )
        data = apply_parent_role_budget(data, h3=h3)
        data, _k_parent_notes = normalize_k_parent_intervention_budget(data)
        data, _dialogue_notes = normalize_scene_dialogue_beats(data)
        data, _retro_notes = normalize_retrospective_topic_contract(data)
        data, _retro_open_notes = normalize_retrospective_n_opening_parent_beats(data)
        errors = validate_scene(data)
        if errors:
            raise ValueError(
                f"H3a scene_contract invalid: {'; '.join(errors[:5])}"
            )
        last_age_errs = age_remap_contract_errors(story_raw, data)
        if not last_age_errs:
            break
        data, _forced = force_age_score_remap(data, story_raw=story_raw)
        last_age_errs = age_remap_contract_errors(story_raw, data)
        if not last_age_errs:
            break
    assert data is not None
    if last_age_errs:
        data, _ = force_age_score_remap(data, story_raw=story_raw)
        last_age_errs = age_remap_contract_errors(story_raw, data)
    if last_age_errs:
        raise ValueError(
            f"H3a age_remap failed: {'; '.join(last_age_errs[:3])}"
        )
    # remap_note 说明里常残留「高考383迁龄」字样，单独洗净
    note = str(data.get("remap_note") or "")
    if note:
        scrubbed = remap_story_raw_scores_for_prompt(note, contract=data)
        if scrubbed != note:
            data = dict(data)
            data["remap_note"] = scrubbed
    confidence = float(data.get("contract_confidence") or 0.0)
    if confidence < 0.35:
        raise ValueError(f"H3a low contract_confidence={confidence:.2f}")
    return data


def build_dialogue_seed(
    *,
    story_raw: str,
    h3: dict[str, Any],
    scene_contract: dict[str, Any] | None = None,
    video_title: str = "",
) -> dict[str, Any]:
    """H3b：scene_contract → dialogue_seed。"""
    contract = scene_contract or {}
    user = _H3B_USER.format(
        video_title=str(video_title or "").strip() or "（未知）",
        scene_contract_json=json.dumps(contract, ensure_ascii=False, indent=2),
        h3_json=json.dumps(h3, ensure_ascii=False, indent=2),
        story_raw=story_raw[:4000],
        gold_seed_snippet=GOLD_H3B_SEED_SNIPPET,
    )
    data = _chat_json(_H3B_SYSTEM, user)
    seed = _seed_rows(data)
    seed, _silent_seed_notes = trim_terminal_no_reply_rows(seed)
    seed, unintelligible_notes = drop_unintelligible_seed_rows(seed)
    if unintelligible_notes:
        logger.info(
            "H3b dropped unintelligible seed rows=%s sample=%s",
            len(unintelligible_notes),
            unintelligible_notes[:3],
        )
    seed, identity_notes = _realign_seed_parent_identity(seed, contract)
    if identity_notes:
        logger.info("H3b parent identity realign=%s", identity_notes[:4])
    facts = normalize_fact_attributions(contract.get("facts"))
    seed, fact_conflicts = filter_fact_bound_rows(seed, facts)
    if fact_conflicts:
        logger.info(
            "H3b fact role conflicts=%s sample=%s",
            len(fact_conflicts),
            fact_conflicts[:3],
        )
        # 带角色硬约束重抽一次：成功则整体替换，否则留首轮合规稿
        retry = _retry_seed_with_fact_constraints(
            user=user,
            contract=contract,
            facts=facts,
            conflicts=fact_conflicts,
            fallback=seed,
        )
        if retry is not None:
            data, seed = retry
    if len(seed) < SEED_MIN:
        seed = seed_from_beat_chain(contract.get("beat_chain") or [])
        data["dialogue_seed"] = seed
    if len(seed) < SEED_MIN:
        raise ValueError("H3b dialogue_seed too short")
    mom_max = max(0, int(contract.get("mom_lines_max") or 0))
    preserve_k_fail_tail = (
        str(contract.get("story_type") or "").strip().upper() == "K"
        and (
            str(contract.get("k_close_mode") or "") == "K_A_PARENT_FAIL_STALEMATE"
            or any(
                token in str(contract.get("closing_intent") or "")
                for token in ("劝不动", "劝不了", "管不了", "僵持", "不和好")
            )
        )
    )
    seed = _trim_mom_dialogue_seed(
        seed,
        mom_max,
        preserve_last=preserve_k_fail_tail,
    )
    seed, _silent_seed_notes2 = trim_terminal_no_reply_rows(seed)
    if len(seed) < SEED_MIN:
        seed = seed_from_beat_chain(contract.get("beat_chain") or [])
    data["dialogue_seed"] = seed
    confidence = float(data.get("dialogue_confidence") or 0.0)
    if confidence < 0.35:
        raise ValueError(f"H3b low dialogue_confidence={confidence:.2f}")
    if not str(data.get("closing_intent") or "").strip():
        data["closing_intent"] = str(contract.get("closing_intent") or "")
    if not str(data.get("speaker_map_note") or "").strip():
        data["speaker_map_note"] = str(contract.get("remap_note") or "")
    normalized_setting, _setting_changed = normalize_dialogue_setting_for_contract(
        str(data.get("setting") or ""),
        contract,
    )
    if normalized_setting:
        data["setting"] = normalized_setting
    return data


def _seed_rows(data: dict[str, Any]) -> list[Any]:
    seed = data.get("dialogue_seed") or []
    return seed if isinstance(seed, list) else []


def _fact_binding_constraint_block(
    facts: list[dict[str, Any]],
    conflicts: list[str],
) -> str:
    """重抽用的角色硬约束块：只给结构槽位，不给剧情词。"""
    lines = [
        "",
        "",
        "【角色绑定硬约束 · 上一稿有冲突，必须改正】",
        "上一稿这些 seed 与 facts 角色绑定冲突，已剔除：",
    ]
    lines.extend(f"- {item}" for item in conflicts[:6])
    lines.append("facts 角色槽位：")
    for fact in facts:
        slots = [
            f"{key}={fact.get(key)}"
            for key in ("secret_holder", "accuser", "discoverer", "claimant")
            if fact.get(key)
        ]
        lines.append(f"- {fact.get('fact_id')}: {', '.join(slots)}")
    lines.extend(
        [
            "认领/自曝/否认/辩解句（admit/confess/deny）只能由 secret_holder 说；"
            "指认/揭发句（accuse/expose）只能由 accuser/discoverer 说；"
            "索赔/讨要句（claim_compensation/demand/bargain）只能由 claimant 说；"
            "回声/回旋镖句按当前说话人重标 claim_role。",
            "请重新输出完整 dialogue_seed（≥4 条），每条带 "
            "fact_ref/speech_act/claim_role/addressee。",
        ]
    )
    return "\n".join(lines)


def _retry_seed_with_fact_constraints(
    *,
    user: str,
    contract: dict[str, Any],
    facts: list[dict[str, Any]],
    conflicts: list[str],
    fallback: list[Any],
) -> tuple[dict[str, Any], list[Any]] | None:
    """冲突后带约束重抽一次；重抽稿合规且不短于首轮合规稿才采纳。"""
    if not facts:
        return None
    try:
        retry_data = _chat_json(
            _H3B_SYSTEM,
            user + _fact_binding_constraint_block(facts, conflicts),
        )
    except Exception as exc:
        logger.info("H3b fact binding retry failed: %s", exc)
        return None
    retry_seed = _seed_rows(retry_data)
    retry_seed, _silent = trim_terminal_no_reply_rows(retry_seed)
    retry_seed, _unintelligible = drop_unintelligible_seed_rows(retry_seed)
    retry_seed, _identity = _realign_seed_parent_identity(retry_seed, contract)
    retry_seed, retry_conflicts = filter_fact_bound_rows(retry_seed, facts)
    if retry_conflicts or len(retry_seed) < max(SEED_MIN, len(fallback)):
        logger.info(
            "H3b fact binding retry kept first pass: conflicts=%s rows=%s",
            len(retry_conflicts),
            len(retry_seed),
        )
        return None
    logger.info("H3b fact binding retry accepted rows=%s", len(retry_seed))
    return retry_data, retry_seed


def _seed_parent_labels(contract: dict[str, Any]) -> tuple[str, ...]:
    """在场家长（妈妈优先）；无家长则空，裸身份自称将无处归位。"""
    raw = contract.get("characters")
    chars = [str(c).strip() for c in raw] if isinstance(raw, list) else []
    return tuple(p for p in PARENT_SPEAKER_LABELS if p in chars)


def _realign_seed_parent_identity(
    seed: list[Any],
    contract: dict[str, Any],
) -> tuple[list[Any], list[str]]:
    """裸身份自称归位家长、回声句转换人称（确定性兜底）。"""
    return realign_parent_identity_rows(
        seed,
        parent_labels=_seed_parent_labels(contract),
    )


def drop_unintelligible_seed_rows(seed: list[Any]) -> tuple[list[Any], list[str]]:
    """H3b 后置硬卡：带 [听不清] 占位的种子不得进对话骨架。

    只认 H0c 的标记与括号变体，不按单篇剧情词过滤；丢弃后 seed 不足时
    由 ``seed_from_beat_chain`` 兜底，不新造剧情。
    """
    kept: list[Any] = []
    dropped: list[str] = []
    for row in seed:
        if not isinstance(row, dict):
            kept.append(row)
            continue
        intent = str(row.get("intent") or "")
        normalized = (
            intent.replace("［", "[")
            .replace("］", "]")
            .replace("【", "[")
            .replace("】", "]")
            .replace(" ", "")
        )
        if UNINTELLIGIBLE_MARKER in normalized:
            dropped.append(intent.strip())
            continue
        kept.append(row)
    return kept, dropped


def _trim_mom_dialogue_seed(
    seed: list[Any],
    mom_max: int,
    *,
    preserve_last: bool = False,
) -> list[Any]:
    """妈妈 seed 超预算时裁剪；K-A 可保留首干预+末劝失败。"""
    limit = max(0, int(mom_max))
    mom_idxs = [
        idx
        for idx, row in enumerate(seed)
        if isinstance(row, dict) and str(row.get("speaker") or "") == "妈妈"
    ]
    if len(mom_idxs) <= limit:
        return list(seed)
    if preserve_last and limit >= 2:
        keep_mom = set(mom_idxs[: limit - 1] + [mom_idxs[-1]])
        return [
            row
            for idx, row in enumerate(seed)
            if not (
                isinstance(row, dict)
                and str(row.get("speaker") or "") == "妈妈"
                and idx not in keep_mom
            )
        ]
    kept_mom = 0
    out: list[Any] = []
    for row in seed:
        if isinstance(row, dict) and str(row.get("speaker") or "") == "妈妈":
            if kept_mom >= limit:
                continue
            kept_mom += 1
        out.append(row)
    return out


_H4A_SYSTEM = (
    "你是金故事机审员。判断站外微型故事能否迁移为"
    "昭昭(7岁弟)/灿灿(10岁姐)日常可拍短视频。\n"
    "主戏可以是：姐弟互怼；姐弟联手对家长；"
    "**或单孩与家长的趣味冲突**（抽签耍赖、逞强被回敬、追问破功等），"
    "家长宜配角少台词。\n"
    "须卡掉：婴儿婴语/纯温馨无冲突、冲突太短无可拍链、"
    "家长当唯一主角且孩子无戏、映射把戏核家长硬改成孩子导致失真、"
    "成人恋爱/夫妻决策无孩子对手戏。\n"
    "源稿爸爸且妈妈代不了时可保留爸爸；能用妈妈就用妈妈。\n"
    "只输出 JSON。"
)

_H4A_USER = """原视频标题：{video_title}
结构化标题：{title}
机制/结构：{mechanism} / {structure_type}

冲突核：{conflict_core}

story_raw：
{story_raw}

speaker_map_note：
{speaker_map_note}

dialogue_seed：
{dialogue_seed}

beat：
{beat}

逐字稿摘录：
{transcript}

输出 JSON：
{{
  "pass": true,
  "sibling_fit": 0.0,
  "age_fit": 0.0,
  "conflict_usable": 0.0,
  "mapping_fit": 0.0,
  "reject_reasons": [],
  "audit_notes": "一句"
}}

评分说明（0–1，越高越好）：
- sibling_fit：能否落到站内可拍主戏（姐弟互怼 / 姐弟联手对家长 /
  **单孩对家长趣味冲突** 均可）。
  **禁止**因「有爸爸/妈妈」或「只有一个孩子」就打低分；
  只卡纯母婴育儿、无孩子对手戏、或孩子未成形。
- age_fit：能否自然落到约 7–10 岁孩（拒绝婴语、过小）；
  中考/高考/成人考分未迁成小学量级须降分或判不通过。
- conflict_usable：是否有可拍争/抢/歪理/追问/破功/以牙还牙链，不是温馨旁白。
- mapping_fit：映射是否自然。保留戏核家长（爸爸/妈妈）为配角对手可接受；
  把必须出场的家长硬映成昭昭/灿灿应降分；家长唯一主角且孩子无戏应降分；
  能用妈不用爸；**禁止**因「压成两人」抹掉戏核家长。

pass=true 仅当四维均 ≥0.55 且无硬伤；否则 pass=false 并列出 reject_reasons。
**reject_reasons 禁止写「非姐弟冲突」「无昭昭/须拆双孩」来挡孩子与家长的趣事。**
"""


_TRIM_STORY_RAW_SYSTEM = (
    "你是故事编辑。把过长的第三方叙述精简到可拍微型故事，保留冲突弧与收束。\n"
    "只输出 JSON。"
)

_TRIM_STORY_RAW_USER = """story_raw（过长，须精简）：
{story_raw}

输出 JSON：
{{
  "story_raw": "精简后全文…",
  "trim_notes": "一句说明删了什么"
}}

规则：保留 80–{max_chars} 字；不丢冲突/升级/收束；勿引入新情节；只输出 JSON。
"""


def trim_story_raw(story_raw: str, *, max_chars: int = 380) -> str:
    """过长 story_raw → LLM 精简。"""
    text = str(story_raw or "").strip()
    if len(text) <= max_chars:
        return text
    user = _TRIM_STORY_RAW_USER.format(story_raw=text[:6000], max_chars=max_chars)
    data = _chat_json(_TRIM_STORY_RAW_SYSTEM, user)
    trimmed = str(data.get("story_raw") or "").strip()
    if len(trimmed) < 80:
        raise ValueError(f"trim_story_raw too short: {len(trimmed)}")
    if len(trimmed) > max_chars + 40:
        raise ValueError(f"trim_story_raw still too long: {len(trimmed)}")
    return trimmed


def audit_story_fit(
    *,
    video_title: str,
    title: str,
    story_raw: str,
    conflict_core: str,
    mechanism: str,
    structure_type: str,
    speaker_map_note: str,
    dialogue_seed: list[Any],
    beat: list[Any],
    transcript: str = "",
    description: str = "",
    min_sibling_fit: float = 0.55,
    min_age_fit: float = 0.55,
    min_conflict_usable: float = 0.55,
    min_mapping_fit: float = 0.55,
) -> dict[str, Any]:
    """H4a LLM 机审。"""
    user = _H4A_USER.format(
        video_title=video_title,
        title=title,
        mechanism=mechanism,
        structure_type=structure_type,
        conflict_core=conflict_core[:500],
        story_raw=story_raw[:4000],
        speaker_map_note=speaker_map_note[:800] or "（无）",
        dialogue_seed=json.dumps(dialogue_seed, ensure_ascii=False, indent=2)[:4000],
        beat=json.dumps(beat, ensure_ascii=False)[:2000],
        transcript=str(transcript or description or "")[:4000] or "（无）",
    )
    data = _chat_json(_H4A_SYSTEM, user)
    sibling_fit = float(data.get("sibling_fit") or 0.0)
    age_fit = float(data.get("age_fit") or 0.0)
    conflict_usable = float(data.get("conflict_usable") or 0.0)
    mapping_fit = float(data.get("mapping_fit") or 0.0)
    llm_pass = bool(data.get("pass"))
    reasons = [str(r) for r in (data.get("reject_reasons") or []) if str(r).strip()]
    thresholds_ok = (
        sibling_fit >= min_sibling_fit
        and age_fit >= min_age_fit
        and conflict_usable >= min_conflict_usable
        and mapping_fit >= min_mapping_fit
    )
    passed = llm_pass and thresholds_ok
    if not thresholds_ok:
        if sibling_fit < min_sibling_fit:
            reasons.append(f"sibling_fit_low:{sibling_fit:.2f}")
        if age_fit < min_age_fit:
            reasons.append(f"age_fit_low:{age_fit:.2f}")
        if conflict_usable < min_conflict_usable:
            reasons.append(f"conflict_usable_low:{conflict_usable:.2f}")
        if mapping_fit < min_mapping_fit:
            reasons.append(f"mapping_fit_low:{mapping_fit:.2f}")
    return {
        "pass": passed,
        "sibling_fit": sibling_fit,
        "age_fit": age_fit,
        "conflict_usable": conflict_usable,
        "mapping_fit": mapping_fit,
        "reject_reasons": reasons,
        "audit_notes": str(data.get("audit_notes") or "").strip(),
    }
