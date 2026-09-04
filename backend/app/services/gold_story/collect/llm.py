"""H0c/H2/H3/H3b：金故事 LLM 结构化。"""

from __future__ import annotations

import json
from typing import Any

from app.services.gold_story.types import (
    GOLD_STORY_MECHANISM_CODES,
    GOLD_STORY_MECHANISM_LABELS,
    GOLD_STORY_TYPE_CATALOG,
    allowed_structure_types,
    normalize_structure_type,
    structure_type_for_mechanism,
)
from app.services.gold_story.scene import (
    SEED_MIN,
    sanitize_banned_literals,
    seed_from_beat_chain,
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

_H0C_SYSTEM = (
    "你是短视频口播逐字稿修复师。输入为 faster-whisper 自动转写："
    "有错字、断句乱、分不清说话人。\n"
    "结合标题/简介推断角色，修正同音错字，按对话拆行并标注说话人。\n"
    "不要编造视频中未出现的情节；听不清处用 [听不清]。\n"
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
    {{"speaker": "妈妈", "text": "修正后的这一句"}},
    {{"speaker": "宝宝", "text": "…"}}
  ],
  "repair_confidence": 0.0,
  "repair_notes": "一句说明推断依据"
}}

规则：
- speaker 用简短称谓：妈妈、爸爸、宝宝、女孩、男孩、哥哥、妹妹等；
  无法判断时用 角色1/角色2，并在 repair_notes 说明
- 合并 ASR 误切的碎句；修正明显同音错字（结合语境，勿脑补新剧情）
- **合并连续重复的同一短语**，只保留 1–2 次
- 相邻同一 speaker 可合并为一条 line
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
- 角色只允许昭昭、灿灿、妈妈；爸爸/陌生小孩须映射或删除，不得保留在 story_raw
- 优先选热评里 **整段复述**（有然后/最后/被问/嘴硬）的完整微型故事
- has_complete_arc=false 或 extract_confidence<0.5 即失败
- 不要输出 quote 字段；引号对白保留在 story_raw 内
"""


_H3_SYSTEM = (
    "你是金故事结构化师。输入 story_raw，输出机制 M 码 + 结构类型 + beat。\n"
    "mechanism 必须是 M1–M13 之一；structure_type 必须是 A–E、F、G、H、I、J、K、L、N 或 O。\n"
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
    "M2 双规则/自私包装公平：须双方各执公平判据且同场回旋镖引原话→C；"
    "若收束为拒领点破表演公平→L；若收束为灵魂拷问问倒→M11+I。\n"
    "禁止把 M2+C 用于武力扭打/一锤 KO：仅有「谁赢了谁说了算」单方定规、"
    "对方认输/怂、或「长大再算账」延后不服→M8+J（镇住不翻车，非双规则回旋镖）。\n"
    "beat 4–6 步，禁止贴 story_raw 原文。\n"
    "只输出 JSON。"
)

_H3_USER = """视频标题：{title}

story_raw：
{story_raw}

机制表（M 码）：
{mechanism_table}

结构类型 A–E / F / G / H / I / J / K / L / N / O：
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
    "characters 只允许昭昭/灿灿/妈妈；beat_chain 至少 4 拍。\n"
    "只输出 JSON。"
)

_H3A_USER = """H3 结构化：
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
  "beat_chain": [
    {{"beat": 1, "speaker": "灿灿|昭昭|妈妈", "intent": "立规/占物/…"}}
  ],
  "closing_intent": "末句嘴硬/反转",
  "mom_lines_max": 0,
  "remap_note": "站外角色如何映射",
  "banned_literals": ["…"],
  "contract_confidence": 0.0
}}

banned_literals：同 H3，仅 remap 称谓与站外真名；禁止填画画/碘伏/朋友圈等场景与笑点词。

规则：
- object/conflict/mechanism **须能在 story_raw 找到依据**；禁止发明 story_raw 没有的物品/仪式/场景
- object：争的具体物品或话题；双方各持一物时两件都写入 object
- location：须为允许地点表中的 place；站外场景选最接近的一项（如车内→卧室，午休垫→地板）
- 禁止无依据套用站内仪式模板（举过头顶/三秒/单脚站/金鸡独立等）
- C类 beat_chain：争资源→双规则（每轮新判据）→三轮升级→同场回旋镖→嘴硬（至少4拍）；
  **禁止**把单方「谁赢了谁说了算」+武力压制+认输标 C
- J类与 C 边界：J=一锤镇住对方怂/不敢再顶；C=双规则同场回旋镖引原话
- I类 beat_chain（**须 4–6 拍**）：争锋/互怼→立价值标准→灵魂拷问→对方语塞→赢家嘴硬总结；
  禁止 A 末四拍反噬/破功；closing 须赢家一招制敌
- J类 beat_chain（**须 4–5 拍**）：闹/求放行/试探权威→一锤威慑或否决压住
  →对方怂/不敢再顶→家长旁观或感叹（可无）；禁止 A 末四拍反噬/破功
- K类 beat_chain（**须 4–6 拍**）：互打互骂升级→大人躲/叹/劝失败→僵持；
  禁止写成第三方和好（勿套 H 定责劝和+仪式性和好）
- H类 beat_chain（**须 6–8 拍**，逐步写清，禁止合并跳步）：
  1 抢看/占物 → 2 拒看/推搡 → 3 **双向互毁**（谁先弄坏谁+报复，须对称）
  → 4 伤情可拍 → 5 哭腔道歉 → 6 M5拒和+加码（不原谅，妈妈介入前）
  → 7 妈妈问谁先动手+定责劝和 → 8 仪式性和好/碘伏/收场
  M5+H 时 object 须是 story_raw 争物（如画作），勿改成「抢秘密」替代互毁
- **正例只允许上方金稿原文**；本稿须按 story_raw 写，禁止把金稿场景套到本稿
- mom_lines_max：H 类 2–3；K 类 1–2（旁观叹气）；其余默认 0，最多 1
- 禁止 characters/beat_chain 出现爸爸/陌生小孩/对方
- tutorial 源禁止 mechanism/conflict 含「四招/方法/应该/告诉」
"""


_H3B_SYSTEM = (
    "你是金故事对话化师。根据 scene_contract.beat_chain 展开 dialogue_seed。\n"
    "intent 必须是第一人称现场动作/台词意图，禁止转述式 intent。\n"
    "dialogue_seed 至少 4 条，建议 12–20 条短 intent；只输出 JSON。"
)

_H3B_USER = """scene_contract：
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
    {{"speaker": "昭昭|灿灿|妈妈", "intent": "…"}}
  ],
  "closing_intent": "与 scene_contract 一致",
  "speaker_map_note": "映射说明",
  "dialogue_confidence": 0.0
}}

规则：
- setting 须含地点与冲突物持有（谁面前/谁端着哪件），与 object 对齐；勿只写地点
- 严格按 beat_chain 顺序展开；每拍 1–3 条 seed
- M5+H：seed 须含「双向互毁」「拒和/不原谅」「妈妈问谁先动手」分拍，勿合并
- intent 须来自 scene_contract + story_raw
- **正例只允许上方金稿原文**；本稿禁止照抄金稿 intent 到不同场景
- speaker 只允许昭昭/灿灿/妈妈；妈妈 seed 条数 ≤ scene_contract.mom_lines_max
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
    for row in lines:
        if not isinstance(row, dict):
            continue
        speaker = str(row.get("speaker") or "").strip() or "未知"
        text = str(row.get("text") or "").strip()
        if text:
            cleaned.append({"speaker": speaker, "text": text})
    if len(cleaned) < 2:
        raise ValueError("H0c cleaned lines too short")
    confidence = float(data.get("repair_confidence") or 0.0)
    if confidence < 0.35:
        raise ValueError(f"H0c low repair_confidence={confidence:.2f}")
    speakers = data.get("speakers") or []
    if not isinstance(speakers, list):
        speakers = []
    return {
        "lines": cleaned,
        "speakers": [str(s).strip() for s in speakers if str(s).strip()],
        "repair_confidence": confidence,
        "repair_notes": str(data.get("repair_notes") or "").strip(),
    }


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
    default_type = structure_type_for_mechanism(mechanism)
    llm_type = str(data.get("structure_type") or "").strip().upper()
    if llm_type:
        try:
            normalized = normalize_structure_type(llm_type)
            if normalized in allowed_structure_types(mechanism):
                data["structure_type"] = normalized
            else:
                data["structure_type"] = default_type
        except ValueError:
            data["structure_type"] = default_type
    else:
        data["structure_type"] = default_type
    data["mechanism"] = mechanism
    beat = data.get("beat") or []
    if not isinstance(beat, list) or len(beat) < 4:
        raise ValueError("H3 beat must have 4–6 steps")
    confidence = float(data.get("structure_confidence") or 0.0)
    if confidence < 0.5:
        raise ValueError(f"H3 low structure_confidence={confidence:.2f}")
    data["banned_literals"] = sanitize_banned_literals(
        data.get("banned_literals") if isinstance(data.get("banned_literals"), list) else [],
        beat=data.get("beat") if isinstance(data.get("beat"), list) else [],
    )
    data, resolve_notes = resolve_h3_structure(data, story_raw=story_raw)
    if resolve_notes:
        note = str(data.get("structure_mapping_note") or "").strip()
        suffix = ";".join(resolve_notes)
        data["structure_mapping_note"] = f"{note};{suffix}".strip(";") if note else suffix
    return data


def build_scene_contract(
    *,
    story_raw: str,
    h3: dict[str, Any],
    source_type: str = "field",
) -> dict[str, Any]:
    """H3a：story_raw → 可拍场景契约。"""
    user = _H3A_USER.format(
        h3_json=json.dumps(h3, ensure_ascii=False, indent=2),
        story_raw=story_raw[:4000],
        source_type=source_type or "field",
        gold_scene_snippet=GOLD_H3A_SCENE_SNIPPET,
        place_catalog=format_place_catalog_for_prompt(),
    )
    data = _chat_json(_H3A_SYSTEM, user)
    data.setdefault("story_type", str(h3.get("structure_type") or "C"))
    data["source_type"] = str(data.get("source_type") or source_type or "field").lower()
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
    if data.get("mom_lines_max") is None:
        st = str(h3.get("structure_type") or "C").upper()
        data["mom_lines_max"] = 3 if st == "H" else 0
    errors = validate_scene(data)
    if errors:
        raise ValueError(f"H3a scene_contract invalid: {'; '.join(errors[:5])}")
    confidence = float(data.get("contract_confidence") or 0.0)
    if confidence < 0.35:
        raise ValueError(f"H3a low contract_confidence={confidence:.2f}")
    return data


def build_dialogue_seed(
    *,
    story_raw: str,
    h3: dict[str, Any],
    scene_contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """H3b：scene_contract → dialogue_seed。"""
    contract = scene_contract or {}
    user = _H3B_USER.format(
        scene_contract_json=json.dumps(contract, ensure_ascii=False, indent=2),
        h3_json=json.dumps(h3, ensure_ascii=False, indent=2),
        story_raw=story_raw[:4000],
        gold_seed_snippet=GOLD_H3B_SEED_SNIPPET,
    )
    data = _chat_json(_H3B_SYSTEM, user)
    seed = data.get("dialogue_seed") or []
    if not isinstance(seed, list):
        seed = []
    if len(seed) < SEED_MIN:
        seed = seed_from_beat_chain(contract.get("beat_chain") or [])
        data["dialogue_seed"] = seed
    if len(seed) < SEED_MIN:
        raise ValueError("H3b dialogue_seed too short")
    mom_max = int(contract.get("mom_lines_max") or 0)
    mom_in_seed = sum(
        1 for r in seed if isinstance(r, dict) and str(r.get("speaker") or "") == "妈妈"
    )
    if mom_in_seed > max(1, mom_max):
        raise ValueError(f"H3b mother-heavy seed: {mom_in_seed}>{mom_max}")
    confidence = float(data.get("dialogue_confidence") or 0.0)
    if confidence < 0.35:
        raise ValueError(f"H3b low dialogue_confidence={confidence:.2f}")
    if not str(data.get("closing_intent") or "").strip():
        data["closing_intent"] = str(contract.get("closing_intent") or "")
    if not str(data.get("speaker_map_note") or "").strip():
        data["speaker_map_note"] = str(contract.get("remap_note") or "")
    return data


_H4A_SYSTEM = (
    "你是金故事机审员。判断站外微型故事能否迁移为"
    "昭昭(7岁弟)+灿灿(10岁姐)姐弟日常冲突短视频。\n"
    "采集词可以宽，但你须严格卡掉：母子/婴儿婴语为主、"
    "冲突太短、映射距离太远、家长当唯一主角的稿子。\n"
    "站外爸爸/父亲/宝爸可等位映射为妈妈（少出场），不算硬伤。\n"
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
- sibling_fit：是否姐弟/兄妹/两孩冲突，而非母子育儿/纯可爱
- age_fit：能否自然落到 7 岁弟 + 10 岁姐（拒绝婴语、过小）
- conflict_usable：是否有可拍争/抢/歪理/互呛链，不是温馨旁白
- mapping_fit：映射到昭昭/灿灿是否牵强（家长当第三主角应降分；爸爸→妈妈视为可接受）

pass=true 仅当四维均 ≥0.55 且无硬伤；否则 pass=false 并列出 reject_reasons。
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
