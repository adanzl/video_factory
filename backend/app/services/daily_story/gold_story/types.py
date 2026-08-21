"""金故事机制 M1–M10 与结构类型 A–E/F/G 映射。"""

from __future__ import annotations

from app.services.daily_story.story_types import STORY_TYPE_LABELS

GOLD_STORY_MECHANISM_CODES: frozenset[str] = frozenset(
    f"M{i}" for i in range(1, 11)
)

GOLD_STORY_MECHANISM_LABELS: dict[str, str] = {
    "M1": "回旋镖扣原话",
    "M2": "自私包装公平",
    "M3": "Threat 互升级",
    "M4": "递台词",
    "M5": "拒和加码",
    "M6": "成人概念童化",
    "M7": "字面执行跑偏",
    "M8": "一锤可拍",
    "M9": "结盟甩锅",
    "M10": "假帮腔讽刺",
}

# M → 结构字母：能落 A–E 的落 A–E；否则用扩展字母（F/G…）
MECHANISM_STRUCTURE_MAP: dict[str, str] = {
    "M1": "C",  # 回旋镖：主落 C 公平执念收束
    "M2": "C",  # 自私包装公平
    "M3": "F",  # Threat 链式互升级，暂无 A–E 标准收束
    "M4": "C",  # 吵架递台词 escalation
    "M5": "A",  # 拒和解 / 嘴硬加码
    "M6": "A",  # 成人概念童化歪问
    "M7": "D",  # 字面执行跑偏
    "M8": "A",  # 一锤可拍（A 类中段不变量）
    "M9": "B",  # 结盟甩锅
    "M10": "E",  # 假帮腔讽刺（E 类帮腔）
}

# 金故事扩展结构类型（尚未进入 daily_story validate；F 已由 M3 启用）
GOLD_STORY_EXTENDED_TYPE_LABELS: dict[str, str] = {
    "F": "Threat 互升级",
    "G": "待立项",
}

GOLD_STORY_STRUCTURE_LABELS: dict[str, str] = {
    **STORY_TYPE_LABELS,
    **GOLD_STORY_EXTENDED_TYPE_LABELS,
}

GOLD_STORY_STRUCTURE_CODES: frozenset[str] = frozenset(
    GOLD_STORY_STRUCTURE_LABELS.keys()
)

# daily_story 已落地类型（H5 可注入任务）
GOLD_STORY_INJECTABLE_CODES: frozenset[str] = frozenset(STORY_TYPE_LABELS.keys())

# 与 docs/日常故事-类型.md §3 一致（A–E）
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
        "name": "Threat 互升级",
        "formula": "互相威胁→加码→僵持/露怯",
        "closing": "无 A–E 标准收束（暂不入 A–E 任务注入）",
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
    expected = structure_type_for_mechanism(mech)
    actual = normalize_structure_type(structure_type)
    if actual != expected:
        raise ValueError(
            f"{mech} 对应 structure_type={expected}（"
            f"{structure_type_label(expected)}），当前为 {actual}"
        )


def is_injectable_structure_type(structure_type: str) -> bool:
    return normalize_structure_type(structure_type) in GOLD_STORY_INJECTABLE_CODES
