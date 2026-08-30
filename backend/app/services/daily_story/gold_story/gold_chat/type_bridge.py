"""gold_chat ↔ daily_story 类型流水线桥接（统一抽象）。

金故事 gold_chat 与日常故事生成共用同一套类型 patch / 收束 / 质检口径；
本模块是唯一桥接入口，避免在 gold_chat_convert 里按类型 if/else 分叉。
"""

from __future__ import annotations

import copy
import re
from typing import Any

from app.services.daily_story.gold_story.types import (
    allowed_structure_types,
    catalog_entry,
    mechanism_label,
    normalize_structure_type,
)
from app.services.daily_story.story_types import (
    STORY_TYPE_LINES,
    revision_hints_for_type,
    story_line_for_code,
)

# 结构类型默认扩写链（无 mechanism 特化时的 fallback）
_STRUCTURE_TYPE_CHAINS: dict[str, tuple[str, ...]] = {
    "A": (
        "立规/亮权威",
        "追问/顶回",
        "一锤可拍（可拍画面）",
        "埋可引用原话（全文一次）",
        "末四拍：引话→那不一样→哪里不一样→破功",
    ),
    "B": (
        "结盟/密谋",
        "走样/露馅",
        "甩锅",
        "末句仍嘴硬甩锅",
    ),
    "C": (
        "争同一资源：占有/护住争点物",
        "立赛规/双规则（每轮一句新判据）",
        "三轮升级：占有→定义→加码",
        "末四拍：可见动作→喊不算→回旋镖引原话→立规方嘴硬收场",
    ),
    "D": (
        "合理规矩",
        "歪读/字面执行",
        "跑偏",
        "叮嘱方破规",
        "执行方原话回旋镖收束",
    ),
    "E": (
        "妈妈立论/立规",
        "追问",
        "改口",
        "妈妈破功闭环",
    ),
    "F": (
        "互相威胁",
        "加码",
        "僵持/露怯",
    ),
    "G": (
        "互怼/数落 escalating",
        "真情 pivot/护短一句",
        "愣住 beat",
        "暖收或嘴硬里带软",
    ),
    "H": (
        "冲突升级/互毁",
        "僵持/拒和",
        "第三方定责劝和（分层）",
        "仪式性和好",
    ),
    "I": (
        "争锋/互怼",
        "价值高地/标准一句",
        "灵魂拷问（不可答/不可接）",
        "对方语塞",
        "赢家嘴硬总结（无 A 式反噬）",
    ),
    "J": (
        "闹/求放行",
        "一锤/否决压住",
        "对方怂/不敢再顶",
        "家长旁观或感叹（非 A 反噬、非 H 劝和）",
    ),
    "K": (
        "互打互骂升级",
        "大人躲/叹/劝失败",
        "僵持（不和好；禁止套 H）",
    ),
    "L": (
        "争物短（勿拖成规则战）",
        "成人表演公平催让渡（给他/给她）",
        "被偏袒方拒收退让",
        "点破偏心",
        "成人语塞（禁止第二轮争夺）",
    ),
}

# mechanism + structure 特化扩写链（优先于 _STRUCTURE_TYPE_CHAINS）
_MECH_STRUCTURE_CHAINS: dict[tuple[str, str], tuple[str, ...]] = {
    ("M1", "C"): (
        "争点物占有/护住",
        "引用对方原话堵截（回旋镖扣原话）",
        "三轮规则升级（占有→定义→加码）",
        "末四拍回旋镖收束",
    ),
    ("M2", "C"): (
        "护住/占有争点物（肉/物须可拍）",
        "堵截1：引用对方刚说过的话",
        "堵截2：搬出第三方规矩（妈妈说…）",
        "三轮升级：占有→定义→加码（勿中段车轱辘）",
        "对方语塞/败北 beat",
        "末四拍回旋镖引原话收束",
    ),
    ("M2", "L"): (
        "争物短（可拍，勿双规则拉锯）",
        "成人催让渡：表演公平（给他/给她）",
        "被偏袒方拒收退让（不想要了/你们喝吧）",
        "点破偏心（哪门子公平/向着）",
        "成人语塞；点题后禁止第二轮争夺",
    ),
    ("M3", "F"): (
        "互相威胁",
        "互呛加码",
        "僵持/露怯（无 A–E 标准收束）",
    ),
    ("M4", "G"): (
        "互怼/数落 escalating",
        "pivot：护短/真心一句",
        "愣住 beat",
        "暖收或半暖",
    ),
    ("M5", "G"): (
        "数落/互损 escalating（翻旧账：咬人没记性/丢人，弟弟不服顶嘴）",
        "拒和/加码：立规不许再咬 + 亮旧痕/旧账（嘴硬不原谅）",
        "pivot：真心一句（你重要/舍不得/怕你疼），不提前软化",
        "愣住 beat（你说啥/……）",
        "暖收或嘴硬里带软（哼，算你识相/过来，给你揉揉）",
    ),
    ("M5", "A"): (
        "立规/拒和 escalating",
        "加码：嘴硬不原谅",
        "A 末四拍或等价收束（引话/破功）",
    ),
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
    ("M5", "J"): (
        "互打/求放过/试探规矩",
        "否决权/拒放行压住",
        "对方怂/不敢再顶",
        "家长旁观或感叹（非 H 劝和）",
    ),
    ("M6", "A"): (
        "成人概念童化/歪问",
        "立规/一锤",
        "埋句→末四拍反噬",
    ),
    ("M7", "D"): (
        "合理规矩",
        "歪读字面执行",
        "跑偏",
        "叮嘱方破规→执行方回旋镖",
    ),
    ("M8", "A"): (
        "一锤可拍",
        "埋句",
        "末四拍反噬/破功",
    ),
    ("M8", "J"): (
        "闹/求放行/试探权威",
        "一锤定音威慑（镇住，不翻车）",
        "对方怂/不敢再顶",
        "家长旁观或感叹（非 A 反噬）",
    ),
    ("M9", "B"): (
        "结盟/密谋",
        "走样/露馅",
        "甩锅",
        "末句仍嘴硬",
    ),
    ("M10", "E"): (
        "妈妈立论",
        "假帮腔/讽刺",
        "追问→妈妈改口破功",
    ),
    ("M11", "I"): (
        "争锋/互怼 escalating（可含双规则拉扯）",
        "立价值标准/道德高地（须可拍一句）",
        "灵魂拷问：抛出不可答/不可接问题",
        "对方语塞/败北 beat",
        "赢家嘴硬总结（无反噬；禁 narration/meta）",
    ),
    ("M12", "K"): (
        "互打互骂升级",
        "大人躲/叹/劝失败",
        "僵持（不和好；禁止套 H）",
    ),
}

# mechanism 特化 prompt 追加（保留原 gold_chat_convert 里 H/I/J/K 细节）
_MECH_HINT_APPEND: dict[tuple[str, str], str] = {
    ("M5", "H"): (
        "\n- **M5+H**：互毁须双向且受害方须**当场动手**撕/弄坏对方画（写撕了/撕啦），"
        "禁仅口头「那我也撕」；推/扭打后**须写伤情一句**（额/头/蹭破/疼），"
        "再写昭昭哭腔道歉 → 灿灿立规 → 拒和 → 加码 → 妈妈问谁先动手；"
        "昭昭须承认先弄画/先推/先动手；"
        "先动手方与受害方分工：服软/道歉≠拒和/加码，禁止同一 speaker；"
        "scene conflict 受害方须在前 2 句 establish 持有/创作，先毁物者≠受害方；"
        "禁止「秘密画/抢看秘密」偏题，须写捣乱毁画→互毁→扭打；"
        "「还打不打架」须 closing_intent 指定角色问（常为灿灿），禁止妈妈代问；"
        "齐声「不打了」=姐弟各一句（昭昭+灿灿），勿合并舞台说明；"
        "story_raw 有碘伏/涂药须写妈妈拿碘伏收场，**禁止发朋友圈/录视频** invent；"
        "碘伏后禁止新剧情（一起画/续写承诺）；句尾禁叠「呢呢」"
    ),
    ("M3", "F"): (
        "\n- **M3+F**：互呛链须双向顶嘴/加码（你再说/试试/还…呢镜像），"
        "至少两轮升级；收束可为僵持/露怯，或 seed 有则外部打断"
        "（偷拍/镜头/闭嘴/尴尬微笑）；"
        "外部打断后**≤5句**收场：僵住/互看/小声闭嘴/干笑或一句「闹着玩呢」/"
        "茄子/快走，**禁商量应对镜头**（瞪他/摆笑脸/数三二一/满意了吧）；"
        "禁半句省略号糊弄（呵呵…你听着…/嘿嘿…好不好…）；"
        "外部打断后宜尴尬收束或装闹着玩，**禁 B 式一伙/团结表演、禁 H 式和好/别吵了**；"
        "禁 seed 外零食分物 invent（薯片等）；禁 G pivot 暖收；禁 C/A 末四拍；"
        "punchline_explain 须以「F类：」开头"
    ),
    ("M11", "I"): (
        "\n- **M11+I**：中段须写清价值高地/标准一句（如爱学习你爱吗）；"
        "灵魂拷问须不可答/不可接；对方语塞后赢家嘴硬总结；"
        "语塞须可机读（说不过/哑口/我……/服了/接不上等）；"
        "**篇幅前置**：争锋+拷问+语塞须写满全文≥240字；"
        "对方服软或赢家口语制敌（看你还嘴硬/别跟我吵）落在末 1–2 句即停；"
        "**禁止**念类型标签作台词（勿说「一招制敌」「问倒」「语塞」）；"
        "**禁止**服软后再用作业监督/你等着/你别得意拉扯凑字；"
        "禁止 A 末四拍反噬/破功；可含双规则拉扯但收束须问倒；"
        "收束须姐弟现场口语，禁长段旁白评点"
    ),
    ("M8", "J"): (
        "\n- **M8+J**：一锤威慑须镇住对方，收束对方怂/不敢再顶；"
        "家长可旁观或感叹一句；禁止 A 末四拍反噬/破功"
    ),
    ("M5", "J"): (
        "\n- **M5+J**：否决权/拒放行压住（家规不许、不放行）；"
        "对方怂；家长可旁观或感叹；禁止写成调解和好（勿套 H），"
        "禁止 A 末四拍反噬"
    ),
    ("M12", "K"): (
        "\n- **M12+K**：主戏是姐弟互打互骂升级；大人躲/叹/劝失败；"
        "收束僵持不和好；禁止套 H 定责劝和+仪式性和好"
    ),
    ("M2", "C"): (
        "\n- **M2+C**：自私包装公平——用对方原话+第三方规矩双重堵截；"
        "严格按 beat_chain/dialogue_seed 顺序，禁止中段 8+ 句重复同一质问；"
        "seed 全部拍写完即收束，**禁止另起第二轮争夺**（角色分工不得反转）；"
        "点题句（scene_title/key）或 closing_intent 落实后**禁止续写**；"
        "**C 层触发词（须字面出现）**：C1 争归属（凭什么/谁先/归谁）；"
        "C2 挑战规则（你刚说/规矩）；C3 挑战权威（凭什么你/你说了算）；"
        "C4 新证据（妈妈说过）；末 5 句须含你刚说/你说的回旋镖；"
        "非整件物：三轮为「原话堵截→妈妈说过→我说了算」，勿写谁先拿到归谁；"
        "句尾语气词每句最多一个，禁了呢了呀/着呢了呀；"
        "判据/自证只用占有系（拿到/抢到/攥手里），禁碰/摸/搭/吃到当胜出词；"
        "punchline_explain 须以「C类：」开头"
    ),
    ("M2", "L"): (
        "\n- **M2+L**：表演公平被拒领点破——成人催让渡后被偏袒方拒收；"
        "赢点是退让揭穿偏心，**禁止**套 C 双规则/回旋镖/吃商收束；"
        "妈妈台词≤1；点题（我不喝了/偏心）后**禁止第二轮要/不要**；"
        "对白须可说出口，禁分镜/心理旁白；"
        "punchline_explain 须以「L类：」开头"
    ),
    ("M1", "C"): (
        "\n- **M1+C**：回旋镖扣原话——收束须引正文真出现过的对方原话"
    ),
}


_RE_MAPPING_G = re.compile(r"G\s*型|G\s*类|符合\s*G")
_RE_SEED_PIVOT = re.compile(
    r"护|撑腰|重要|舍不得|在乎|心疼|真心|动你|管你|认真的|我怕",
)
_RE_SEED_SOFT = re.compile(
    r"识相|暖|嘴硬|原谅|饶|擦|药|说好了|行了|撑腰|嗯|笑",
)


def _dialogue_seed_blob(seed: list[Any] | None) -> str:
    parts: list[str] = []
    for item in seed or []:
        if not isinstance(item, dict):
            continue
        parts.append(str(item.get("intent") or item.get("beat") or ""))
    return "\n".join(parts)


def _mapping_note_suggests_g(note: str) -> bool:
    return bool(_RE_MAPPING_G.search(str(note or "")))


def _seed_suggests_g(seed: list[Any] | None) -> bool:
    blob = _dialogue_seed_blob(seed)
    if not blob.strip():
        return False
    return bool(_RE_SEED_PIVOT.search(blob) and _RE_SEED_SOFT.search(blob))


def resolve_gold_chat_structure_row(row: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """gold_chat 入口纠偏 structure_type（mapping_note + seed 强信号）。"""
    notes: list[str] = []
    out = dict(row)
    payload = out.get("payload") if isinstance(out.get("payload"), dict) else {}
    payload = copy.deepcopy(payload)
    mechanism = str(out.get("mechanism") or "").strip().upper()
    current = str(out.get("structure_type") or "").strip().upper()
    mapping_note = str(payload.get("structure_mapping_note") or "")
    seed = payload.get("dialogue_seed")
    if not isinstance(seed, list):
        seed = []

    target = "G"
    if current == target:
        out["payload"] = payload
        return out, notes
    if not _mapping_note_suggests_g(mapping_note) or not _seed_suggests_g(seed):
        out["payload"] = payload
        return out, notes
    if mechanism and target not in allowed_structure_types(mechanism):
        out["payload"] = payload
        return out, notes

    normalize_structure_type(target)
    out["structure_type"] = target
    notes.append(f"structure_type:{current}→{target}(mapping+seed)")

    sc = payload.get("scene_contract")
    if isinstance(sc, dict):
        sc = copy.deepcopy(sc)
        sc_type = str(sc.get("story_type") or "").strip().upper()
        if sc_type and sc_type != target:
            sc["story_type"] = target
            notes.append(f"scene_contract.story_type:{sc_type}→{target}")
        payload["scene_contract"] = sc
    out["payload"] = payload
    return out, notes


def type_align_chain(
    *,
    structure_type: str,
    mechanism: str = "",
) -> tuple[str, ...]:
    """金稿对齐扩写链：mechanism+structure 特化 > 结构类型默认。"""
    st = str(structure_type or "").strip().upper()
    mech = str(mechanism or "").strip().upper()
    if mech and st:
        chain = _MECH_STRUCTURE_CHAINS.get((mech, st))
        if chain:
            return chain
    return _STRUCTURE_TYPE_CHAINS.get(st, ())


def structure_type_hint(
    *,
    structure_type: str,
    mechanism: str = "",
) -> str:
    """注入 gold_chat LLM prompt：类型公式 + 成熟流水线修订 hint + 扩写链。"""
    st = str(structure_type or "").strip().upper()
    mech = str(mechanism or "").strip().upper()
    if not st:
        return ""

    entry = catalog_entry(st)
    name = entry["name"] if entry else st
    mech_label = mechanism_label(mech) if mech else "?"
    header = f"【{st} {name} · 机制 {mech or '?'}（{mech_label}）】"

    parts: list[str] = [header]
    if entry:
        parts.append(f"- 公式：{entry['formula']}")
        parts.append(f"- 收束：{entry['closing']}")

    if st in STORY_TYPE_LINES:
        esc, close = revision_hints_for_type(st)
        line = story_line_for_code(st)
        if esc:
            parts.append(f"- 冲突升级：{esc}")
        if close:
            parts.append(f"- 收束修订：{close}")
        anchor = str(line.body_user_anchor or "").strip()
        if anchor:
            parts.append(f"- 正文锚：{anchor}")

    chain = type_align_chain(structure_type=st, mechanism=mech)
    if chain:
        parts.append("- 扩写链（逐步落实，禁止跳步）：")
        parts.extend(f"  · {step}" for step in chain)

    extra = _MECH_HINT_APPEND.get((mech, st), "")
    if extra:
        parts.append(extra.strip())

    parts.append("- 详拍亦见下方「金稿对齐 checklist」与 beat_chain")
    return "\n".join(parts)


def apply_type_body_pipeline(
    chat: dict[str, Any],
    *,
    structure_type: str,
) -> tuple[dict[str, Any], list[str]]:
    """跑日常故事成熟 patch 链（patch_type_body + try_local_patch）。"""
    st = str(structure_type or "").strip().upper()
    if not st or not isinstance(chat, dict):
        return chat, []

    from app.services.daily_story.prompts import try_local_patch_daily_story_body

    out = dict(chat)
    out["story_type"] = st
    patched, notes = try_local_patch_daily_story_body(out)
    return patched, notes
