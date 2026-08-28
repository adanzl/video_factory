"""金故事机制 M1–M12 与结构类型 A–E/F/G/H/I/J/K/L 映射。"""

from __future__ import annotations

from app.services.daily_story.story_types import STORY_TYPE_LABELS

GOLD_STORY_MECHANISM_CODES: frozenset[str] = frozenset(
    f"M{i}" for i in range(1, 13)
)

GOLD_STORY_MECHANISM_LABELS: dict[str, str] = {
    "M1": "回旋镖扣原话",
    "M2": "自私包装公平",
    "M3": "互呛加码",
    "M4": "递台词",
    "M5": "拒和加码",
    "M6": "成人概念童化",
    "M7": "字面执行跑偏",
    "M8": "一锤可拍",
    "M9": "结盟甩锅",
    "M10": "假帮腔讽刺",
    "M11": "灵魂拷问",
    "M12": "家长旁观",
}

# M → 结构字母：能落 A–E 的落 A–E；否则用扩展字母（F/G/H…）
MECHANISM_STRUCTURE_MAP: dict[str, str] = {
    "M1": "C",  # 回旋镖：主落 C 公平执念收束
    "M2": "C",  # 自私包装公平（退让点破偏心→L）
    "M3": "F",  # 互呛链式加码，暂无 A–E 标准收束
    "M4": "G",  # 递台词 escalation → 嘴硬心软（争物/双规则用 M1/M2→C）
    "M5": "A",  # 拒和解 / 嘴硬加码（调解→H；否决压住→J）
    "M6": "A",  # 成人概念童化歪问
    "M7": "D",  # 字面执行跑偏
    "M8": "A",  # 一锤可拍（有反噬→A；镇住不翻→J）
    "M9": "B",  # 结盟甩锅
    "M10": "E",  # 假帮腔讽刺（E 类帮腔）
    "M11": "I",  # 价值高地灵魂拷问 → 问倒收束
    "M12": "K",  # 家长旁观不劝和 → 家长看戏
}

# mechanism 默认映射外的合法 structure_type（防 H3 误判入库失败）
MECHANISM_STRUCTURE_ALTERNATIVES: dict[str, frozenset[str]] = {
    "M2": frozenset({"L"}),  # 表演公平被拒领点破 → L（非双规则回旋镖）
    "M5": frozenset({"G", "H", "J"}),  # G 拒和后 pivot 暖收；H 调解；J 否决压住
    "M8": frozenset({"J"}),  # 一锤镇住、不翻车
}

# 金故事扩展结构类型（尚未进入 daily_story validate；F 已由 M3 启用）
GOLD_STORY_EXTENDED_TYPE_LABELS: dict[str, str] = {
    "F": "互呛加码",
    "G": "嘴硬心软",
    "H": "第三方化解",
    "I": "问倒收束",
    "J": "权威压住",
    "K": "家长看戏",
    "L": "退让点破",
}

GOLD_STORY_STRUCTURE_LABELS: dict[str, str] = {
    **STORY_TYPE_LABELS,
    **GOLD_STORY_EXTENDED_TYPE_LABELS,
}

GOLD_STORY_STRUCTURE_CODES: frozenset[str] = frozenset(
    GOLD_STORY_STRUCTURE_LABELS.keys()
)

# daily_story 已落地类型（H5 可注入任务）；H/I/J/K/L 暂仅 gold_story 侧
_GOLD_STORY_NON_INJECTABLE = frozenset({"F", "H", "I", "J", "K", "L"})
GOLD_STORY_INJECTABLE_CODES: frozenset[str] = frozenset(
    k for k in STORY_TYPE_LABELS if k not in _GOLD_STORY_NON_INJECTABLE
)

# 与 docs/日常故事-类型.md §3 一致（含金故事扩展 F–L）
GOLD_STORY_TYPE_CATALOG: tuple[dict[str, str], ...] = (
    {
        "code": "A",
        "name": "权威翻车",
        "formula": "立规→一锤可拍→埋句→反噬",
        "closing": "末四拍（引话/那不一样/哪里不一样/破功）",
    },
    {
        "code": "B",
        "name": "结盟翻车",
        "formula": "结盟→走样→甩锅→露馅",
        "closing": "露馅后仍嘴硬甩锅",
    },
    {
        "code": "C",
        "name": "公平执念",
        "formula": "争同一资源→双规则→回旋镖",
        "closing": "被戳穿方末句嘴硬",
    },
    {
        "code": "D",
        "name": "字面执行",
        "formula": "合理规矩→歪读执行→跑偏→叮嘱方破规",
        "closing": "执行方用原话回旋镖",
    },
    {
        "code": "E",
        "name": "妈妈破功",
        "formula": "妈妈立论→追问→改口→闭环",
        "closing": "妈妈破功",
    },
    {
        "code": "F",
        "name": "互呛加码",
        "formula": "互相顶嘴→加码→僵持/露怯",
        "closing": "无 A–E 标准收束（暂不入 A–E 任务注入）",
    },
    {
        "code": "G",
        "name": "嘴硬心软",
        "formula": "互怼/数落→真情 pivot→愣住→暖收",
        "closing": "暖收或嘴硬里带软（多样，不锁模板）",
    },
    {
        "code": "H",
        "name": "第三方化解",
        "formula": "升级/僵持→第三方定责劝和→仪式性和好",
        "closing": "表演性道歉/拒和/拉手/齐声承诺；非 G 内部 pivot",
    },
    {
        "code": "I",
        "name": "问倒收束",
        "formula": "争锋→价值高地→灵魂拷问→语塞→赢家嘴硬",
        "closing": "赢家一招制敌总结；无 A 式反噬/破功",
    },
    {
        "code": "J",
        "name": "权威压住",
        "formula": "闹/求放行→一锤或否决压住→对方怂→家长旁观",
        "closing": "镇住不翻车；禁止 A 末四拍反噬",
    },
    {
        "code": "K",
        "name": "家长看戏",
        "formula": "互打互骂升级→大人躲/叹/劝失败→僵持",
        "closing": "不和好；禁止套 H 第三方化解",
    },
    {
        "code": "L",
        "name": "退让点破",
        "formula": "争物短→成人表演公平催让渡→拒收退让→点破偏心→语塞",
        "closing": "点破偏心/成人语塞；禁止 C 回旋镖、A 破功",
    },
)


def normalize_mechanism(value: str) -> str:
    code = str(value or "").strip().upper()
    if code not in GOLD_STORY_MECHANISM_CODES:
        allowed = ", ".join(sorted(GOLD_STORY_MECHANISM_CODES))
        raise ValueError(f"mechanism must be one of {allowed}, got {value!r}")
    return code


def mechanism_label(code: str) -> str:
    return GOLD_STORY_MECHANISM_LABELS[normalize_mechanism(code)]


def allowed_structure_types(mechanism: str) -> frozenset[str]:
    mech = normalize_mechanism(mechanism)
    allowed = {MECHANISM_STRUCTURE_MAP[mech]}
    allowed |= MECHANISM_STRUCTURE_ALTERNATIVES.get(mech, frozenset())
    return frozenset(allowed)


def structure_type_for_mechanism(mechanism: str) -> str:
    mech = normalize_mechanism(mechanism)
    return MECHANISM_STRUCTURE_MAP[mech]


def normalize_structure_type(value: str) -> str:
    code = str(value or "").strip().upper()
    if code not in GOLD_STORY_STRUCTURE_CODES:
        allowed = ", ".join(sorted(GOLD_STORY_STRUCTURE_CODES))
        raise ValueError(f"structure_type must be one of {allowed}, got {value!r}")
    return code


def structure_type_label(code: str) -> str:
    return GOLD_STORY_STRUCTURE_LABELS[normalize_structure_type(code)]


def catalog_entry(code: str) -> dict[str, str] | None:
    normalized = normalize_structure_type(code)
    for row in GOLD_STORY_TYPE_CATALOG:
        if row["code"] == normalized:
            return row
    return None


def validate_mechanism_structure_pair(mechanism: str, structure_type: str) -> None:
    mech = normalize_mechanism(mechanism)
    actual = normalize_structure_type(structure_type)
    allowed = allowed_structure_types(mech)
    if actual not in allowed:
        default = MECHANISM_STRUCTURE_MAP[mech]
        alt = ", ".join(sorted(allowed))
        raise ValueError(
            f"{mech} 对应 structure_type 须为 {alt} 之一"
            f"（默认 {default}·{structure_type_label(default)}），"
            f"当前为 {actual}"
        )


def is_injectable_structure_type(structure_type: str) -> bool:
    return normalize_structure_type(structure_type) in GOLD_STORY_INJECTABLE_CODES
