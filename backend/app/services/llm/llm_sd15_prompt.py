"""SD1.5 出图：LLM 提示词模板、LoRA 目录与解析。"""

from __future__ import annotations

import re
from typing import Any

# LoRA 目录；分图左半在分子场景可叠 Science_DNA_Style（最多 2 个）
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
        "weight": 0.65,
        "keywords": (
            "信息图", "流程图", "示意图", "对比图", "扁平", "科普图", "箭头", "步骤",
            "infographic", "flowchart", "chart", "schematic", "comparison", "steps",
        ),
    },
    "Science_DNA_Style": {
        "weight": 0.7,
        "trigger": "ScienceDNAStyle",
        "keywords": (
            "分子", "一氧化碳", "蛋白", "DNA", "RNA", "微观", "发光", "科学感",
            "molecule", "molecules", "carbon monoxide", "protein", "proteins",
            "wireframe", "glowing", "science", "microscopic", "sci-fi",
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
_SCIENCE_DIAGRAM_SUFFIX = "dark gray background, clean composition, no text"
_SCIENCE_SPLIT_SUFFIX = "dark gray background, no text"
_LIFE_SUFFIX = "natural light, realistic photo"

_SCIENCE_LORAS = frozenset({"Textbook_Line_Art", "Simple_Diagram", "Science_DNA_Style"})

_SCIENCE_DNA_KEYWORDS = SD15_LORAS["Science_DNA_Style"]["keywords"]

_SPLIT_KEYWORDS = (
    "对比", "左右", "上下", "一侧", "另一侧", "左边", "右边", "上边", "下边", "上方", "下方",
    "左半", "右半", "上半", "下半", "分屏", "双场景",
    "comparison", "left side", "right side", "top", "bottom", "above", "below",
    "on the left", "on the right", "split",
)

_SCIENCE_LEFT_STRIP = re.compile(
    r"\b("
    r"lung|lungs|alveoli|anatomy|organ|organs|blood cell|hemoglobin|tissue cross[- ]section"
    r")\b[^,]*",
    re.IGNORECASE,
)

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
    r"person|people|character|portrait|face|head|"
    r"hair|eyes|glowing|superhero|anime|dizziness|hypoxia"
    r")\b[^,]*",
    re.IGNORECASE,
)

_SCIENCE_LEFT_CHARACTER = re.compile(
    r"\b("
    r"person|people|character|portrait|face|head|"
    r"hair|eyes|superhero|anime|dizziness|hypoxia"
    r")\b[^,]*",
    re.IGNORECASE,
)

_SCIENCE_RIGHT_CHARACTER = re.compile(
    r"\b("
    r"person|people|character|portrait|face|head|"
    r"hair|eyes|glowing|superhero|anime|dizziness|hypoxia"
    r")\b[^,]*",
    re.IGNORECASE,
)


def normalize_sd15_prompt_en(prompt_en: str, *, business: str, lora: str) -> str:
    """按 business / LoRA 约束清洗并截断英文 subject（不含 LoRA 标签与固定后缀）。"""
    return normalize_sd15_panel_prompt_en(
        prompt_en,
        panel="single",
        business=business,
        lora=lora,
    )


def normalize_sd15_panel_prompt_en(
    prompt_en: str,
    *,
    panel: str,
    business: str,
    lora: str,
) -> str:
    """按 panel（single / left / right）清洗英文 subject。"""
    cleaned = re.sub(r"\s+", " ", prompt_en.strip()).strip("\"'`")
    if not cleaned:
        raise ValueError("prompt_en is empty")
    if business == "science":
        if panel == "left":
            cleaned = _strip_science_forbidden(cleaned)
            cleaned = _SCIENCE_LEFT_STRIP.sub("", cleaned)
            cleaned = _SCIENCE_LEFT_CHARACTER.sub("", cleaned)
        elif panel == "right":
            cleaned = _SCIENCE_FORBIDDEN.sub("", cleaned)
            cleaned = _SCIENCE_SUBJECT_STRIP.sub("", cleaned)
            cleaned = _SCIENCE_RIGHT_CHARACTER.sub("", cleaned)
        elif lora == "Science_DNA_Style":
            cleaned = _SCIENCE_FORBIDDEN.sub("", cleaned)
            cleaned = _SCIENCE_SUBJECT_STRIP.sub("", cleaned)
            cleaned = _SCIENCE_LEFT_CHARACTER.sub("", cleaned)
        else:
            cleaned = _strip_science_forbidden(cleaned)
            cleaned = _SCIENCE_CHARACTER.sub("", cleaned)
        cleaned = re.sub(r",\s*,+", ", ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,")
    cleaned = _truncate_prompt_en(cleaned)
    if not cleaned:
        raise ValueError("prompt_en is empty after normalization")
    return cleaned


def _science_style_suffix(*, lora: str, layout: str) -> str:
    if layout == "split":
        return _SCIENCE_SPLIT_SUFFIX
    if lora == "Textbook_Line_Art":
        return _SCIENCE_SUFFIX
    return _SCIENCE_DIAGRAM_SUFFIX


def wants_science_dna_lora(*, prompt: str, subject: str = "") -> bool:
    """分子/科学微观语义时叠加 Science_DNA_Style。"""
    text = f"{prompt} {subject}".casefold()
    return any(kw.casefold() in text for kw in _SCIENCE_DNA_KEYWORDS)


def resolve_extra_loras(
    *,
    lora: str,
    layout: str,
    panel: str,
    subject: str,
    source_prompt: str,
) -> tuple[str, ...]:
    """分图左半在分子场景叠加 Science_DNA_Style（与主 LoRA 并用）。"""
    if layout != "split" or panel != "left":
        return ()
    if lora == "Science_DNA_Style":
        return ()
    if wants_science_dna_lora(prompt=source_prompt, subject=subject):
        return ("Science_DNA_Style",)
    return ()


def lora_trigger_for(name: str) -> str:
    meta = SD15_LORAS.get(name, {})
    trigger = meta.get("trigger")
    return str(trigger) if trigger else ""


def build_lora_prefix(lora: str, extra_loras: tuple[str, ...] = ()) -> str:
    tags: list[str] = []
    triggers: list[str] = []
    seen: set[str] = set()
    for name in (lora, *extra_loras):
        if name in seen or name not in SD15_LORAS:
            continue
        seen.add(name)
        tags.append(f"<lora:{name}:{weight_for_lora(name)}>")
        trigger = lora_trigger_for(name)
        if trigger:
            triggers.append(trigger)
    if not tags:
        return ""
    prefix = " ".join(tags)
    if triggers:
        return f"{prefix} {', '.join(triggers)},"
    return prefix


def build_sd15_full_prompt(
    *,
    subject: str,
    business: str,
    lora: str,
    layout: str = "single",
    panel: str = "single",
    extra_loras: tuple[str, ...] = (),
    source_prompt: str = "",
) -> str:
    """按 SD15 部署约定拼接 LoRA 标签与 business 固定后缀。"""
    if not extra_loras and source_prompt:
        extra_loras = resolve_extra_loras(
            lora=lora,
            layout=layout,
            panel=panel,
            subject=subject,
            source_prompt=source_prompt,
        )
    cleaned = normalize_sd15_panel_prompt_en(
        subject,
        panel=panel if layout == "split" else "single",
        business=business,
        lora=lora,
    )
    lora_prefix = build_lora_prefix(lora, extra_loras)
    if business == "science":
        if layout == "split" and panel == "left":
            style = "macro scientific illustration"
        elif layout == "split" and panel == "right":
            style = "medical cross-section illustration"
        else:
            style = None
        suffix = _science_style_suffix(lora=lora, layout=layout)
        if style:
            return f"{lora_prefix} {style}, {cleaned}, {suffix}"
        return f"{lora_prefix} {cleaned}, {suffix}"
    return f"{lora_prefix} {cleaned}, {_LIFE_SUFFIX}"


def has_comparison_semantics(prompt: str) -> bool:
    """原文是否含对比 / 双场景 / 方位语义。"""
    text = prompt.casefold()
    return any(kw.casefold() in text for kw in _SPLIT_KEYWORDS)


def resolve_split_axis(
    *,
    prompt: str,
    width: int,
    height: int,
    business: str,
    llm_wants_split: bool = False,
) -> str | None:
    """science 分图轴向：横屏/方形默认左右拼；竖屏仅对比语义（或 LLM 指定 split）时上下拼。"""
    if business != "science" or width <= 0 or height <= 0:
        return None
    if width >= height:
        return "horizontal"
    if has_comparison_semantics(prompt) or llm_wants_split:
        return "vertical"
    return None


def resolve_split_layout(
    *,
    result: dict[str, str] | None,
    prompt: str,
    business: str,
    width: int,
    height: int,
) -> tuple[str, str]:
    """返回 (layout, split_axis)。split_axis 为 horizontal | vertical。"""
    llm_split = bool(result and result.get("layout") == "split")
    axis = resolve_split_axis(
        prompt=prompt,
        width=width,
        height=height,
        business=business,
        llm_wants_split=llm_split,
    )
    if axis:
        return "split", axis
    return "single", "horizontal"


def wants_split_panel(
    *,
    prompt: str,
    width: int,
    height: int,
    business: str,
) -> bool:
    """是否走分图拼接（兼容旧调用）。"""
    return (
        resolve_split_axis(
            prompt=prompt,
            width=width,
            height=height,
            business=business,
        )
        is not None
    )


def fallback_split_panel_prompts(prompt: str) -> tuple[str, str]:
    """LLM 不可用时的左右分图 subject 兜底（英文）。"""
    text = prompt.casefold()
    left = (
        "macro scientific illustration, abstract mesh or fiber structure, "
        "small highlighted molecules passing through gaps"
    )
    right = (
        "medical cross-section illustration, internal organ tissue structure, "
        "air sacs and cells diagram"
    )
    if any(kw in text for kw in ("co", "一氧化碳", "carbon monoxide", "分子")):
        left = (
            "red glowing carbon monoxide molecules passing through blue wet fabric mesh, "
            "molecules, science, semi-transparent cloth weave"
        )
    if any(kw in text for kw in ("肺", "lung", "alveoli", "血", "blood", "血红蛋白")):
        right = (
            "medical cross-section illustration, lung alveoli air sacs, "
            "red blood cells turning dark, moist tissue"
        )
    return left, right


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
        "你必须提炼为 SD1.5 在 640×360 低分辨率下可画的画面。\n\n"
        "输出 JSON 字段：\n"
        "1. layout：science 默认 split（系统按画幅拼接）；life 用 single。"
        "split 时写 left_en、right_en——横屏对应左/右半，竖屏对应上/下半；"
        "竖屏无对比/双场景语义时可 single。\n"
        "2. 当 layout=single：prompt_en 为 subject（英文、逗号分隔，25～55 词）；"
        "不写 lora 标签，不写背景后缀（系统会自动追加）。"
        "science 时禁止 person/face/head 等人物词。\n"
        "3. 当 layout=split：left_en、right_en 各 15～35 词 subject。"
        "left_en 侧重宏观/分子/介质（如湿布纤维、分子穿过，可用 molecules/glowing/science）；"
        "right_en 侧重医学截面/器官/细胞（如肺泡、血红蛋白）；"
        "均禁止文字、人物肖像；不要写 left/right/top/bottom 等方位词。\n"
        "4. business：life=写实摄影；science=科普插画示意（默认非动漫底模）。\n"
        "5. lora：分子/微观/CO 优先 Science_DNA_Style；"
        "对比/流程/多概念优先 Simple_Diagram（分图左半可与 Science_DNA_Style 叠加）；"
        "单一结构解剖优先 Textbook_Line_Art。\n"
        f"{_lora_catalog_text()}\n\n"
        "science 禁词：hyper-realistic, photorealistic, 3d render, photo, "
        "person, portrait, face, head, glowing eyes。\n"
        "life 禁词：line art, cartoon, diagram。\n\n"
        'split 示例：{"layout": "split", '
        '"left_en": "blue wet fabric fiber mesh, red CO molecules passing through gaps", '
        '"right_en": "lung alveoli air sacs, red blood cells turning dark, moist tissue", '
        '"business": "science", "lora": "Simple_Diagram"}\n'
        'single 示例：{"layout": "single", "prompt_en": "labeled cell diagram, nucleus and membrane", '
        '"business": "science", "lora": "Textbook_Line_Art"}\n'
        'life 示例：{"layout": "single", "prompt_en": "home cooking scene, steaming pot, window light", '
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
        lines.append(
            f"画幅：{orient}。"
            "science 横屏默认 split（左右拼）；竖屏有对比/双场景语义时用 split（上下拼）。"
        )
    lines.append(
        "请输出 layout、prompt_en 或 left_en+right_en、business、lora。"
        "science 优先 split；竖屏单主体可 single。"
    )
    return "\n\n".join(lines)


def parse_sd15_prompt_payload(
    raw: dict[str, Any],
    *,
    business_override: str | None = None,
) -> dict[str, str]:
    lora = raw.get("lora")
    if not isinstance(lora, str) or lora not in SD15_LORAS:
        raise ValueError(f"LLM response invalid lora: {lora!r}")

    if business_override in _VALID_BUSINESS:
        business = business_override
    else:
        business = raw.get("business")
        if not isinstance(business, str) or business not in _VALID_BUSINESS:
            raise ValueError(f"LLM response invalid business: {business!r}")

    layout = raw.get("layout", "single")
    if layout == "split":
        left_en = raw.get("left_en")
        right_en = raw.get("right_en")
        if not isinstance(left_en, str) or not left_en.strip():
            raise ValueError("LLM response missing left_en")
        if not isinstance(right_en, str) or not right_en.strip():
            raise ValueError("LLM response missing right_en")
        return {
            "layout": "split",
            "left_en": normalize_sd15_panel_prompt_en(
                left_en, panel="left", business=business, lora=lora
            ),
            "right_en": normalize_sd15_panel_prompt_en(
                right_en, panel="right", business=business, lora=lora
            ),
            "business": business,
            "lora": lora,
        }

    prompt_en = raw.get("prompt_en")
    if not isinstance(prompt_en, str) or not prompt_en.strip():
        raise ValueError("LLM response missing prompt_en")
    cleaned = normalize_sd15_panel_prompt_en(
        prompt_en, panel="single", business=business, lora=lora
    )
    return {
        "layout": "single",
        "prompt_en": cleaned,
        "business": business,
        "lora": lora,
    }
