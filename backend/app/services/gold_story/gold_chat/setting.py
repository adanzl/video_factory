"""gold_chat / daily_story setting 地点映射与限制。

允许地点以表维护；站外场景不做同义词词表，由 LLM 归类到表中一项。
"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Any, Callable

# 与 OPENING_PLACE_RE / 文生图 S2 锚点一致；供 LLM 归类与程序校验
ALLOWED_SETTING_PLACE_CATALOG: tuple[dict[str, str], ...] = (
    {"place": "客厅", "hint": "沙发、电视、茶几，日常玩耍争吵"},
    {"place": "卧室", "hint": "床、被窝、床头，睡前晨起；车内后座可归此类"},
    {"place": "厨房", "hint": "灶台、冰箱、洗菜，做饭抢食"},
    {"place": "餐厅", "hint": "餐桌、吃饭，分菜抢碗"},
    {"place": "餐桌", "hint": "饭桌上争食、抢筷子"},
    {"place": "书桌", "hint": "写作业、抢文具"},
    {"place": "卫生间", "hint": "刷牙、洗手、抢毛巾"},
    {"place": "浴室", "hint": "洗澡、抢喷头"},
    {"place": "门口", "hint": "玄关换鞋、拦门出门"},
    {"place": "玄关", "hint": "进门换鞋、抢拖鞋"},
    {"place": "阳台", "hint": "晾衣、看窗外；户外院子可近似归此"},
    {"place": "沙发", "hint": "沙发上抢位、窝着"},
    {"place": "床边", "hint": "床沿穿鞋、抢被子"},
    {"place": "床上", "hint": "床上打滚、抢枕头"},
    {"place": "被窝", "hint": "钻被窝、抢被子"},
    {"place": "灶台", "hint": "锅边、炒菜抢铲子"},
    {"place": "洗手台", "hint": "刷牙、洗脸抢位置"},
    {"place": "水槽", "hint": "洗碗、抢水龙头"},
    {"place": "地板", "hint": "地垫、爬行垫、趴地上玩"},
    {"place": "抽屉", "hint": "翻抽屉、抢东西"},
    {"place": "书包", "hint": "翻书包、抢作业本"},
    {"place": "冰箱", "hint": "开冰箱、抢零食"},
    {"place": "挂钟", "hint": "看时间、抢遥控器旁"},
    {"place": "茶几", "hint": "茶几上零食、遥控器"},
)

ALLOWED_SETTING_PLACES: frozenset[str] = frozenset(
    row["place"] for row in ALLOWED_SETTING_PLACE_CATALOG
)

_SETTING_STRIP_RE = re.compile(
    r"妈妈开车|开车|驾驶|行驶|高速|停车|安全带|导航"
)

_DEFAULT_CHARACTERS = ("灿灿", "昭昭")
_DEFAULT_INDOOR_PLACE = "客厅"
_CLASSIFY_MIN_CONFIDENCE = 0.35

_LLM_CLASSIFY_HOOK: Callable[[str, str], dict[str, Any]] | None = None

_CLASSIFY_SYSTEM = (
    "你是场景地点归类师。把站外 location/setting 映射到允许地点表中的一条。\n"
    "只输出 JSON；place 必须是表内 place 字段之一。"
)

_CLASSIFY_USER = """允许地点表（只能选 place 列）：
{catalog}

站外场景描述：
{raw}

{context_block}

输出 JSON：
{{
  "place": "客厅",
  "confidence": 0.0,
  "reason": "一句说明"
}}

规则：
- 须选最接近、可拍的室内锚点；户外/车内/学校午休垫等映射到表中室内
- 禁止输出表外地点名
"""


def format_place_catalog_for_prompt() -> str:
    lines = [
        f"- {row['place']}：{row['hint']}"
        for row in ALLOWED_SETTING_PLACE_CATALOG
    ]
    return "\n".join(lines)


def set_place_classify_hook(
    hook: Callable[[str, str], dict[str, Any]] | None,
) -> None:
    """测试注入 LLM 归类结果。"""
    global _LLM_CLASSIFY_HOOK
    _LLM_CLASSIFY_HOOK = hook
    classify_setting_place.cache_clear()


def extract_allowed_place(text: str) -> str | None:
    """原文已含允许地点时直接抽取（免调 LLM）。"""
    blob = str(text or "")
    for place in sorted(ALLOWED_SETTING_PLACES, key=len, reverse=True):
        if place in blob:
            return place
    return None


def has_allowed_place(text: str) -> bool:
    return extract_allowed_place(text) is not None


def _parse_classify_result(data: dict[str, Any]) -> tuple[str, float, str]:
    place = str(data.get("place") or "").strip()
    if place not in ALLOWED_SETTING_PLACES:
        raise ValueError(f"invalid classified place: {place!r}")
    confidence = float(data.get("confidence") or 0.0)
    reason = str(data.get("reason") or "").strip()
    return place, confidence, reason


def _llm_classify_place(raw: str, *, context: str = "") -> dict[str, Any]:
    if _LLM_CLASSIFY_HOOK is not None:
        return _LLM_CLASSIFY_HOOK(raw, context)
    from app.services.llm.llm_mgr import llm_mgr

    context_block = f"补充上下文：\n{context[:800]}" if context.strip() else ""
    user = _CLASSIFY_USER.format(
        catalog=format_place_catalog_for_prompt(),
        raw=str(raw or "").strip()[:500] or "（空）",
        context_block=context_block,
    )
    data, _finish = llm_mgr._get_client()._chat_json(  # type: ignore[attr-defined]
        _CLASSIFY_SYSTEM,
        user,
        thinking_enabled=False,
        temperature=0.2,
    )
    if not isinstance(data, dict):
        raise ValueError("place classify JSON must be object")
    return data


@lru_cache(maxsize=256)
def classify_setting_place(raw: str, context: str = "") -> str:
    """LLM 把站外场景归类到允许地点表；失败回落默认。"""
    text = str(raw or "").strip()
    if not text and not str(context or "").strip():
        return _DEFAULT_INDOOR_PLACE
    hit = extract_allowed_place(text)
    if hit:
        return hit
    hit = extract_allowed_place(context)
    if hit:
        return hit
    try:
        place, confidence, _reason = _parse_classify_result(
            _llm_classify_place(text, context=context)
        )
        if confidence < _CLASSIFY_MIN_CONFIDENCE:
            return _DEFAULT_INDOOR_PLACE
        return place
    except Exception:
        return _DEFAULT_INDOOR_PLACE


def resolve_target_location(
    raw: str,
    *,
    context: str = "",
    default: str = _DEFAULT_INDOOR_PLACE,
) -> str:
    """抽取或 LLM 归类到允许地点。"""
    text = str(raw or "").strip()
    hit = extract_allowed_place(text)
    if hit:
        return hit
    if text:
        return classify_setting_place(text, context=context)
    hit = extract_allowed_place(context)
    return hit or default


def setting_location_violations(setting: str) -> list[str]:
    text = str(setting or "").strip()
    if not text:
        return ["setting 为空"]
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
    activity_context: str = "",
    characters: tuple[str, ...] = _DEFAULT_CHARACTERS,
) -> tuple[str, list[str]]:
    """无允许地点锚点 → LLM 归类并重写 setting。"""
    notes: list[str] = []
    raw_setting = str(setting or "").strip()
    raw_loc = str(scene_contract_location or "").strip()
    combined = f"{raw_setting} {raw_loc}".strip()
    ctx = " ".join(x for x in (activity_context, raw_loc, raw_setting) if x).strip()

    if has_allowed_place(raw_setting):
        cleaned = _SETTING_STRIP_RE.sub("", raw_setting).strip(" ，,")
        if cleaned and cleaned != raw_setting:
            notes.append("setting 剔除不可拍行车描述")
            return cleaned, notes
        return raw_setting, notes

    target = resolve_target_location(combined, context=ctx)
    activity = _infer_activity_hint(raw_setting, raw_loc, activity_context)
    new_setting = build_setting_line(
        target,
        characters=characters,
        activity_hint=activity,
    )
    src = raw_loc or raw_setting[:16] or "站外场景"
    notes.append(f"setting 地点归类：{src}→{target}")
    return new_setting, notes


def normalize_scene_contract_location(
    contract: dict,
    *,
    activity_context: str = "",
    characters: tuple[str, ...] = _DEFAULT_CHARACTERS,
) -> tuple[dict, list[str]]:
    if not isinstance(contract, dict):
        return contract, []
    notes: list[str] = []
    loc = str(contract.get("location") or "").strip()
    if not loc:
        return contract, notes
    if has_allowed_place(loc):
        return contract, notes
    ctx = " ".join(
        x
        for x in (
            activity_context,
            str(contract.get("object") or ""),
            str(contract.get("conflict") or ""),
        )
        if x
    ).strip()
    target = resolve_target_location(loc, context=ctx)
    out = dict(contract)
    out["location"] = target
    notes.append(f"scene_contract.location 归类：{loc}→{target}")
    return out, notes
