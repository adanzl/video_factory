"""gold_chat / daily_story setting 地点映射与限制。

站外金稿常见「车内/户外」等不可拍或不宜成片场景，须映射到
ALLOWED_SETTING_PLACES 内的室内（默认卧室/客厅等）。
"""

from __future__ import annotations

import re

# 与 OPENING_PLACE_RE / 文生图 S2 锚点一致的允许地点
ALLOWED_SETTING_PLACES: frozenset[str] = frozenset(
    {
        "客厅",
        "卧室",
        "厨房",
        "餐厅",
        "餐桌",
        "书桌",
        "卫生间",
        "浴室",
        "门口",
        "玄关",
        "阳台",
        "沙发",
        "床边",
        "床上",
        "被窝",
        "灶台",
        "洗手台",
        "水槽",
        "地板",
        "抽屉",
        "书包",
        "冰箱",
        "挂钟",
        "茶几",
    }
)

# 站外/不可成片 location → 允许的室内地点（用户定：车内→卧室）
RESTRICTED_LOCATION_MAP: dict[str, str] = {
    "车内": "卧室",
    "车上": "卧室",
    "汽车": "卧室",
    "后座": "卧室",
    "驾驶": "卧室",
    "马路": "门口",
    "室外": "阳台",
    "户外": "阳台",
    "公园": "阳台",
    "操场": "阳台",
}

_RE_RESTRICTED = re.compile(
    "|".join(
        re.escape(k)
        for k in sorted(RESTRICTED_LOCATION_MAP, key=len, reverse=True)
    )
)

# setting 中须剔除的不可拍动作/状态（与地点映射配套）
_SETTING_STRIP_RE = re.compile(
    r"妈妈开车|开车|驾驶|行驶|高速|停车|安全带|导航"
)

_DEFAULT_CHARACTERS = ("灿灿", "昭昭")


def detect_restricted_location(text: str) -> str | None:
    """识别受限地点词；无则 None。"""
    m = _RE_RESTRICTED.search(str(text or ""))
    return m.group(0) if m else None


def resolve_target_location(raw: str, *, default: str = "客厅") -> str:
    """将任意 location/setting 映射到允许地点。"""
    text = str(raw or "").strip()
    hit = detect_restricted_location(text)
    if hit:
        return RESTRICTED_LOCATION_MAP[hit]
    for place in sorted(ALLOWED_SETTING_PLACES, key=len, reverse=True):
        if place in text:
            return place
    return default


def has_allowed_place(text: str) -> bool:
    return any(p in str(text or "") for p in ALLOWED_SETTING_PLACES)


def setting_location_violations(setting: str) -> list[str]:
    """校验 setting 是否仍含受限地点或未在允许列表内。"""
    text = str(setting or "").strip()
    if not text:
        return ["setting 为空"]
    hit = detect_restricted_location(text)
    if hit:
        return [f"setting 含受限地点「{hit}」（须映射为室内）"]
    if not has_allowed_place(text):
        return ["setting 缺允许地点（须为客厅/卧室等室内）"]
    return []


def _infer_activity_hint(*texts: str | None) -> str:
    blob = " ".join(str(t or "") for t in texts)
    if any(k in blob for k in ("作业", "学习", "写")):
        return "因为作业吵起来"
    if any(k in blob for k in ("画", "橡皮", "玩具")):
        return "在抢东西"
    return "在吵架"


def build_setting_line(
    place: str,
    *,
    characters: tuple[str, ...] = _DEFAULT_CHARACTERS,
    activity_hint: str = "",
) -> str:
    """生成可拍 setting 一句。"""
    p = place.strip()
    if p not in ALLOWED_SETTING_PLACES:
        p = resolve_target_location(p)
    names = "和".join(characters[:2]) if len(characters) >= 2 else "灿灿和昭昭"
    act = (activity_hint or "在吵架").strip()
    if act.startswith("在") or act.startswith("因为"):
        return f"{p}里，{names}{act}"
    return f"{p}里，{names}{act}"


def normalize_gold_chat_setting(
    setting: str,
    *,
    scene_contract_location: str | None = None,
    characters: tuple[str, ...] = _DEFAULT_CHARACTERS,
) -> tuple[str, list[str]]:
    """受限/不可拍地点 → 允许室内；返回 (新 setting, 备注)。"""
    notes: list[str] = []
    raw_setting = str(setting or "").strip()
    raw_loc = str(scene_contract_location or "").strip()
    combined = f"{raw_setting} {raw_loc}".strip()

    restricted = detect_restricted_location(combined)
    if not restricted and has_allowed_place(raw_setting):
        cleaned = _SETTING_STRIP_RE.sub("", raw_setting).strip(" ，,")
        if cleaned and cleaned != raw_setting:
            notes.append("setting 剔除不可拍行车描述")
            return cleaned, notes
        return raw_setting, notes

    target = resolve_target_location(combined)
    activity = _infer_activity_hint(raw_setting, raw_loc)
    new_setting = build_setting_line(
        target,
        characters=characters,
        activity_hint=activity,
    )
    src = restricted or raw_loc or raw_setting[:12] or "受限场景"
    notes.append(f"setting 地点映射：{src}→{target}")
    return new_setting, notes


def normalize_scene_contract_location(
    contract: dict,
    *,
    characters: tuple[str, ...] = _DEFAULT_CHARACTERS,
) -> tuple[dict, list[str]]:
    """同步 scene_contract.location 到允许地点。"""
    if not isinstance(contract, dict):
        return contract, []
    notes: list[str] = []
    loc = str(contract.get("location") or "").strip()
    if not loc:
        return contract, notes
    if detect_restricted_location(loc) or not has_allowed_place(loc):
        target = resolve_target_location(loc)
        out = dict(contract)
        out["location"] = target
        notes.append(f"scene_contract.location 映射：{loc}→{target}")
        return out, notes
    return contract, notes
