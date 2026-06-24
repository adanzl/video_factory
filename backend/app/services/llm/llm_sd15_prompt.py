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
        "weight": 0.55,
        "keywords": (
            "线稿", "结构", "解剖", "标注", "教科书", "白底", "讲解", "细胞", "器官",
            "line art", "diagram", "labeled", "textbook", "structure", "cross section",
        ),
    },
    "Simple_Diagram": {
        "weight": 0.55,
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
_PROMPT_EN_MAX_WORDS = 55

_SCIENCE_SUFFIX = "white background, line art, clean composition, no text"
_LIFE_SUFFIX = "natural light, realistic photo"

_SCIENCE_LORAS = frozenset({"Textbook_Line_Art", "Simple_Diagram"})

_SCIENCE_FORBIDDEN = re.compile(
    r"\b("
    r"hyper[- ]?realistic|ultra[- ]?realistic|photorealistic|photo[- ]?realistic|"
    r"3d render(?:ing)?|cgi render|realistic medical illustration|medical photography|"
    r"realistic photography|dslr|octane render|unreal engine"
    r")\b",
    re.IGNORECASE,
)

_LORA_STYLE_ANCHORS: dict[str, str] = {}

_SCIENCE_SUBJECT_STRIP = re.compile(
    r"\b("
    r"white background|line art|clean composition|no text|"
    r"dark gray background|black background|gradient background"
    r")\b",
    re.IGNORECASE,
)


def _word_count(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9']+", text))


def _truncate_prompt_en(text: str, max_words: int = _PROMPT_EN_MAX_WORDS) -> str:
    parts = [part.strip() for part in text.split(",") if part.strip()]
    if not parts:
        return text.strip()
    kept: list[str] = []
    count = 0
    for part in parts:
        part_words = _word_count(part)
        if count + part_words > max_words and kept:
            break
        kept.append(part)
        count += part_words
    return ", ".join(kept)


def _strip_science_forbidden(text: str) -> str:
    cleaned = _SCIENCE_FORBIDDEN.sub("", text)
    cleaned = _SCIENCE_SUBJECT_STRIP.sub("", cleaned)
    cleaned = re.sub(r",\s*,+", ", ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,")
    return cleaned


_SCIENCE_CHARACTER = re.compile(
    r"\b("
    r"person|people|human|man|woman|girl|boy|child|character|portrait|face|head|"
    r"hair|eyes|glowing|superhero|anime|dizziness|hypoxia"
    r")\b[^,]*",
    re.IGNORECASE,
)


def normalize_sd15_prompt_en(prompt_en: str, *, business: str, lora: str) -> str:
    """按 business / LoRA 约束清洗并截断英文 subject（不含 LoRA 标签与固定后缀）。"""
    cleaned = re.sub(r"\s+", " ", prompt_en.strip()).strip("\"'`")
    if not cleaned:
        raise ValueError("prompt_en is empty")
    if business == "science":
        cleaned = _strip_science_forbidden(cleaned)
        cleaned = _SCIENCE_CHARACTER.sub("", cleaned)
        cleaned = re.sub(r",\s*,+", ", ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,")
    cleaned = _truncate_prompt_en(cleaned)
    if not cleaned:
        raise ValueError("prompt_en is empty after normalization")
    return cleaned


def build_sd15_full_prompt(*, subject: str, business: str, lora: str) -> str:
    """按 SD15 部署约定拼接 LoRA 标签与 business 固定后缀。"""
    weight = weight_for_lora(lora)
    cleaned = normalize_sd15_prompt_en(subject, business=business, lora=lora)
    if business == "science":
        return f"<lora:{lora}:{weight}> {cleaned}, {_SCIENCE_SUFFIX}"
    return f"<lora:{lora}:{weight}> {cleaned}, {_LIFE_SUFFIX}"


_ANIME_KEYWORDS = (
    "动漫", "二次元", "卡通风格", "日系动漫", "anime", "manga", "chibi", "toon style",
    "cartoon style", "anime style",
)


def science_wants_anime(prompt: str) -> bool:
    """仅当原文明确要求动漫风时 science 才用 ToonYou。"""
    text = prompt.casefold()
    return any(kw.casefold() in text for kw in _ANIME_KEYWORDS)


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
        "输入常为 200～500 字中文 image_prompt（为云端大模型撰写），"
        "你必须提炼为 SD1.5 在 640×360 低分辨率下可画的单一画面。\n\n"
        "输出 JSON 字段：\n"
        "1. prompt_en：仅写 subject 主体描述（英文、逗号分隔），25～55 词；"
        "不写 lora 标签，不写 white background / line art / no text（系统会自动追加）。"
        "禁止逐句翻译长文；禁止左右分屏多场景堆砌；最多 2 个可视化主体。"
        "science 时禁止 person/head/face/human/hair/eyes 等人物词，"
        "改用 molecule/icon/cross-section/diagram 等无人物示意。\n"
        "2. business：life=写实摄影；science=科普插画示意（默认非动漫底模）。\n"
        "3. lora：按关键词独立选择；左右对比/流程/多概念优先 Simple_Diagram，"
        "单一结构解剖优先 Textbook_Line_Art。\n"
        f"{_lora_catalog_text()}\n\n"
        "science 禁词：hyper-realistic, photorealistic, 3d render, photo, "
        "person, human, face, head, glowing eyes。\n"
        "life 禁词：line art, cartoon, diagram。\n\n"
        'science 示例：{"prompt_en": "comparison diagram, red CO molecule passing '
        'blue wet cloth mesh on left, lung alveoli cross-section icon on right", '
        '"business": "science", "lora": "Simple_Diagram"}\n'
        'life 示例：{"prompt_en": "home cooking scene, steaming pot, window light", '
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
        lines.append(f"画幅：{orient}，分辨率低，务必简化为单一示意画面。")
    lines.append(
        "请输出 prompt_en（25～55 词 subject）、business、lora。"
        "science 勿写人物；对比/流程场景优先 Simple_Diagram。"
    )
    return "\n\n".join(lines)


def parse_sd15_prompt_payload(
    raw: dict[str, Any],
    *,
    business_override: str | None = None,
) -> dict[str, str]:
    prompt_en = raw.get("prompt_en")
    if not isinstance(prompt_en, str) or not prompt_en.strip():
        raise ValueError("LLM response missing prompt_en")

    lora = raw.get("lora")
    if not isinstance(lora, str) or lora not in SD15_LORAS:
        raise ValueError(f"LLM response invalid lora: {lora!r}")

    if business_override in _VALID_BUSINESS:
        business = business_override
    else:
        business = raw.get("business")
        if not isinstance(business, str) or business not in _VALID_BUSINESS:
            raise ValueError(f"LLM response invalid business: {business!r}")

    cleaned = normalize_sd15_prompt_en(prompt_en, business=business, lora=lora)
    return {"prompt_en": cleaned, "business": business, "lora": lora}
