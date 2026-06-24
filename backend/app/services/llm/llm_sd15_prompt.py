"""SD1.5 出图：LLM 提示词模板、LoRA 目录与解析。"""

from __future__ import annotations

import re
from typing import Any

# 与 docs/SD15部署.md §LoRA 与提示词 一致；单次仅 1 个 LoRA
SD15_LORAS: dict[str, dict[str, Any]] = {
    "Food_Photo": {
        "business": "life",
        "weight": 0.6,
        "keywords": (
            "美食", "餐饮", "厨房", "烹饪", "料理", "餐桌", "食物", "饭菜", "小吃",
            "food", "cook", "cooking", "kitchen", "meal", "dish", "restaurant",
        ),
    },
    "Home_Interior": {
        "business": "life",
        "weight": 0.65,
        "keywords": (
            "家居", "室内", "客厅", "卧室", "家装", "房间", "沙发", "窗户",
            "interior", "home", "living room", "bedroom", "furniture", "house",
        ),
    },
    "Casual_Life": {
        "business": "life",
        "weight": 0.6,
        "keywords": (
            "日常", "生活", "人物", "街景", "户外", "散步", "纪实", "vlog",
            "daily", "street", "people", "casual", "lifestyle", "walk",
        ),
    },
    "Product_Shot": {
        "business": "life",
        "weight": 0.7,
        "keywords": (
            "产品", "商品", "包装", "静物", "物件", "桌面", "展示",
            "product", "package", "still life", "object", "merchandise",
        ),
    },
    "Textbook_Line_Art": {
        "business": "science",
        "weight": 0.7,
        "keywords": (
            "线稿", "结构", "解剖", "标注", "教科书", "白底", "讲解", "细胞", "器官",
            "line art", "diagram", "labeled", "textbook", "structure", "cross section",
        ),
    },
    "Simple_Diagram": {
        "business": "science",
        "weight": 0.65,
        "keywords": (
            "信息图", "流程图", "示意图", "对比图", "扁平", "科普图", "箭头", "步骤",
            "infographic", "flowchart", "chart", "schematic", "comparison", "steps",
        ),
    },
}

_VALID_BUSINESS = frozenset({"life", "science"})
_DEFAULT_LORA = "Casual_Life"


def sd15_lora_names() -> list[str]:
    return list(SD15_LORAS)


def business_for_lora(lora: str) -> str:
    meta = SD15_LORAS.get(lora)
    if meta is None:
        raise ValueError(f"unknown sd15 lora: {lora}")
    return str(meta["business"])


def weight_for_lora(lora: str) -> float:
    meta = SD15_LORAS.get(lora)
    if meta is None:
        return 0.65
    return float(meta["weight"])


def pick_lora_by_keywords(prompt: str) -> str:
    """按提示词关键词命中数选 LoRA（与 business 无关）。"""
    text = prompt.casefold()
    best_name = _DEFAULT_LORA
    best_score = 0
    for name, meta in SD15_LORAS.items():
        score = sum(1 for kw in meta["keywords"] if kw.casefold() in text)
        if score > best_score:
            best_score = score
            best_name = name
    return best_name


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
    _ = business_override
    lora_rule = (
        "lora：根据画面描述中的主体/场景/动作关键词，与下列 LoRA 关键词表匹配，"
        "选最贴切的 1 个（文件名，含下划线；性能限制禁止多 LoRA）。"
        "禁止先判断 business 再选 LoRA，仅按关键词匹配：\n"
        f"{_lora_catalog_text()}"
    )
    return (
        "你是 Stable Diffusion 1.5 文生图提示词专家。"
        "输入多为中文长篇画面描述，需转为英文 SD 正向提示词，并按关键词选单个 LoRA。\n\n"
        "输出 JSON 字段：\n"
        "1. prompt_en：英文 SD 提示词，逗号分隔的具象描述，50～120 英文词；"
        "保留主体/动作/场景/光影/构图；去掉字幕、口播、品牌、水印、可读文字；"
        "若输入已是英文则精炼后保留；不要写 lora 标签。\n"
        f"2. {lora_rule}\n\n"
        '示例：{"prompt_en": "home cooking, natural window light", "lora": "Food_Photo"}'
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
    lines.append("请输出 prompt_en 与 lora（按关键词匹配，勿按 business 分组选）。")
    return "\n\n".join(lines)


def parse_sd15_prompt_payload(
    raw: dict[str, Any],
    *,
    business_override: str | None = None,
) -> dict[str, str]:
    _ = business_override
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

    business = business_for_lora(lora)
    return {"prompt_en": cleaned, "business": business, "lora": lora}
