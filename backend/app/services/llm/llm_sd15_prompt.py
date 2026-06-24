"""SD1.5 出图：LLM 提示词模板、LoRA 目录与解析。"""

from __future__ import annotations

import re
from typing import Any

# 与 docs/SD15部署.md §LoRA 与提示词 一致；单次仅 1 个 LoRA
SD15_LORAS: dict[str, dict[str, Any]] = {
    "Food_Photo": {
        "weight": 0.6,
        "keywords": (
            "美食", "餐饮", "厨房", "烹饪", "料理", "餐桌", "食物", "饭菜", "小吃",
            "food", "cook", "cooking", "kitchen", "meal", "dish", "restaurant",
        ),
    },
    "Home_Interior": {
        "weight": 0.65,
        "keywords": (
            "家居", "室内", "客厅", "卧室", "家装", "房间", "沙发", "窗户",
            "interior", "home", "living room", "bedroom", "furniture", "house",
        ),
    },
    "Casual_Life": {
        "weight": 0.6,
        "keywords": (
            "日常", "生活", "人物", "街景", "户外", "散步", "纪实", "vlog",
            "daily", "street", "people", "casual", "lifestyle", "walk",
        ),
    },
    "Product_Shot": {
        "weight": 0.7,
        "keywords": (
            "产品", "商品", "包装", "静物", "物件", "桌面", "展示",
            "product", "package", "still life", "object", "merchandise",
        ),
    },
    "Textbook_Line_Art": {
        "weight": 0.7,
        "keywords": (
            "线稿", "结构", "解剖", "标注", "教科书", "白底", "讲解", "细胞", "器官",
            "line art", "diagram", "labeled", "textbook", "structure", "cross section",
        ),
    },
    "Simple_Diagram": {
        "weight": 0.65,
        "keywords": (
            "信息图", "流程图", "示意图", "对比图", "扁平", "科普图", "箭头", "步骤",
            "infographic", "flowchart", "chart", "schematic", "comparison", "steps",
        ),
    },
}

SD15_BUSINESS_KEYWORDS: dict[str, tuple[str, ...]] = {
    "life": (
        "写实", "摄影", "纪实", "vlog", "生活", "日常", "人物", "街景", "户外",
        "美食", "餐饮", "厨房", "烹饪", "家居", "室内", "客厅", "产品", "商品",
        "realistic", "photo", "photography", "lifestyle", "street", "cooking",
        "interior", "product", "daily", "people",
    ),
    "science": (
        "科普", "原理", "讲解", "教科书", "教育", "细胞", "器官", "结构", "解剖",
        "线稿", "白底", "标注", "信息图", "流程图", "示意图", "对比图", "扁平",
        "diagram", "textbook", "infographic", "flowchart", "schematic",
        "educational", "labeled", "science", "chart",
    ),
}

_VALID_BUSINESS = frozenset({"life", "science"})
_DEFAULT_LORA = "Casual_Life"
_DEFAULT_BUSINESS = "science"


def sd15_lora_names() -> list[str]:
    return list(SD15_LORAS)


def weight_for_lora(lora: str) -> float:
    meta = SD15_LORAS.get(lora)
    if meta is None:
        return 0.65
    return float(meta["weight"])


def pick_lora_by_keywords(prompt: str) -> str:
    """按提示词关键词命中数选 LoRA。"""
    text = prompt.casefold()
    best_name = _DEFAULT_LORA
    best_score = 0
    for name, meta in SD15_LORAS.items():
        score = sum(1 for kw in meta["keywords"] if kw.casefold() in text)
        if score > best_score:
            best_score = score
            best_name = name
    return best_name


def pick_business_by_keywords(prompt: str) -> str:
    """按提示词关键词命中数选 business 管线（life / science）。"""
    text = prompt.casefold()
    scores = {
        business: sum(1 for kw in keywords if kw.casefold() in text)
        for business, keywords in SD15_BUSINESS_KEYWORDS.items()
    }
    best = max(scores, key=scores.get)
    if scores[best] == 0:
        return _DEFAULT_BUSINESS
    life_score = scores["life"]
    science_score = scores["science"]
    if science_score > life_score:
        return "science"
    if life_score > science_score:
        return "life"
    return _DEFAULT_BUSINESS


def _lora_catalog_text() -> str:
    lines: list[str] = []
    for name, meta in SD15_LORAS.items():
        kws = "、".join(str(k) for k in meta["keywords"][:12])
        if len(meta["keywords"]) > 12:
            kws += "…"
        lines.append(
            f'- "{name}"（权重 {meta["weight"]}）关键词：{kws}'
        )
    return "\n".join(lines)


def build_sd15_prompt_system(*, business_override: str | None = None) -> str:
    override_note = ""
    if business_override in _VALID_BUSINESS:
        override_note = f"\n\n固定 business={business_override}，lora 仍按画面关键词独立选择。"
    return (
        "你是 Stable Diffusion 1.5 文生图提示词专家。"
        "输入多为中文长篇画面描述，需转为英文 SD 正向提示词，"
        "并独立推理 business 与 lora。\n\n"
        "输出 JSON 字段：\n"
        "1. prompt_en：英文 SD 提示词，逗号分隔的具象描述，50～120 英文词；"
        "保留主体/动作/场景/光影/构图；去掉字幕、口播、品牌、水印、可读文字；"
        "若输入已是英文则精炼后保留；不要写 lora 标签。\n"
        "2. business：根据画面内容推理出图管线，"
        "life=写实摄影风（生活/美食/家居/人物/产品等），"
        "science=科普插画风（线稿/示意图/信息图/结构讲解等）；"
        "禁止根据所选 lora 反推 business。\n"
        "3. lora：根据画面描述中的主体/场景/动作关键词，与下列 LoRA 关键词表匹配，"
        "选最贴切的 1 个（文件名，含下划线；性能限制禁止多 LoRA）；"
        "禁止根据 business 反推 lora：\n"
        f"{_lora_catalog_text()}\n\n"
        '示例：{"prompt_en": "home cooking, natural window light", '
        '"business": "life", "lora": "Food_Photo"}'
        f"{override_note}"
    )


def build_sd15_prompt_user(
    *,
    prompt: str,
    size_hint: str | None = None,
    parse_size: Any = None,
) -> str:
    trimmed = prompt.strip()
    if len(trimmed) > 1200:
        trimmed = trimmed[:1200] + "…"
    orient = ""
    if size_hint and parse_size is not None:
        w, h = parse_size(size_hint)
        orient = "portrait" if h > w else "landscape" if w > h else "square"
    lines = [f"画面描述：\n{trimmed}"]
    if orient:
        lines.append(f"画幅参考（非决定性）：{orient}")
    lines.append("请输出 prompt_en、business 与 lora（均基于画面描述独立推理）。")
    return "\n\n".join(lines)


def parse_sd15_prompt_payload(
    raw: dict[str, Any],
    *,
    business_override: str | None = None,
) -> dict[str, str]:
    prompt_en = raw.get("prompt_en")
    if not isinstance(prompt_en, str) or not prompt_en.strip():
        raise ValueError("LLM response missing prompt_en")
    cleaned = re.sub(r"\s+", " ", prompt_en.strip()).strip("\"'`")
    if not cleaned:
        raise ValueError("prompt_en is empty")
    if len(cleaned) > 800:
        cleaned = cleaned[:800].rsplit(",", 1)[0] or cleaned[:800]

    lora = raw.get("lora")
    if not isinstance(lora, str) or lora not in SD15_LORAS:
        raise ValueError(f"LLM response invalid lora: {lora!r}")

    if business_override in _VALID_BUSINESS:
        business = business_override
    else:
        business = raw.get("business")
        if not isinstance(business, str) or business not in _VALID_BUSINESS:
            raise ValueError(f"LLM response invalid business: {business!r}")

    return {"prompt_en": cleaned, "business": business, "lora": lora}
