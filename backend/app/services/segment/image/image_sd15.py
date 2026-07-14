"""本地 SD1.5（A1111 WebUI API）文生图、LoRA 目录与提示词解析。"""

from __future__ import annotations

import base64
import io
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from gevent.lock import Semaphore
import requests
from PIL import Image

from app.config import get_settings
from app.services.llm.llm_mgr import llm_mgr
from app.services.segment.image.image_mock import MockImageProvider
from app.services.segment.image.image_mgr import ImageProvider

logger = logging.getLogger(__name__)

# LoRA 目录；分图左半在分子场景可叠 Science_DNA_Style（最多 2 个）
SD15_LORAS: dict[str, dict[str, Any]] = {
    "Food_Photo": {
        "weight": 0.6,
        "keywords": (
            "美食", "餐饮", "厨房", "烹饪", "料理", "餐桌", "食物", "饭菜", "小吃",
            "food", "cook", "cooking", "kitchen", "meal", "dish", "restaurant",
            "dining", "cuisine", "chef", "baking", "stove", "recipe",
        ),
    },
    "Home_Interior": {
        "weight": 0.65,
        "keywords": (
            "家居", "室内", "客厅", "卧室", "家装", "房间", "沙发", "窗户",
            "interior", "home", "living room", "bedroom", "furniture", "house",
            "indoor", "decoration", "decor", "curtain", "wall",
        ),
    },
    "Casual_Life": {
        "weight": 0.6,
        "keywords": (
            "日常", "生活", "人物", "街景", "户外", "散步", "纪实", "vlog",
            "daily", "street", "people", "casual", "lifestyle", "walk",
            "close-up", "portrait", "portrait photography",
            "outdoor", "person", "documentary", "candid", "snapshot",
        ),
    },
    "Product_Shot": {
        "weight": 0.7,
        "keywords": (
            "产品", "商品", "包装", "静物", "物件", "桌面", "展示",
            "product", "package", "still life", "object", "merchandise",
            "display", "showcase", "commercial", "advertising",
        ),
    },
    "Textbook_Line_Art": {
        "weight": 0.55,
        "keywords": (
            "线稿", "结构", "解剖", "标注", "教科书", "白底", "讲解", "细胞", "器官",
            "line art", "diagram", "labeled", "textbook", "structure", "cross section",
            "white background", "scientific illustration", "educational",
        ),
    },
    "Simple_Diagram": {
        "weight": 0.65,
        "keywords": (
            "信息图", "流程图", "示意图", "对比图", "扁平", "科普图", "箭头", "步骤",
            "infographic", "flowchart", "chart", "schematic", "comparison", "steps",
            "arrow", "simple", "flat design", "visualization",
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
    "Anatomica_Scientifica": {
        "weight": 0.7,
        "keywords": (
            "解剖", "医学截面", "器官", "组织", "病理", "肺", "心脏", "肾脏",
            "细胞截面", "血管", "anatomy", "medical", "cross-section", "tissue",
            "organ", "liver", "kidney", "pathology", "histology",
            "blood vessel", "artery", "lung", "heart", "cellular",
        ),
    },
    "Laboratory_Scene": {
        "weight": 0.65,
        "keywords": (
            "实验室", "实验台", "试管", "烧杯", "科研", "化学", "生物实验", "显微镜",
            "lab", "laboratory", "experiment", "chemistry", "beaker",
            "test tube", "research", "scientist", "microscope",
        ),
    },
    "Scientific_Equipment": {
        "weight": 0.6,
        "keywords": (
            "仪器", "设备", "装置", "机械", "器材", "工具", "检测", "测量",
            "equipment", "instrument", "device", "apparatus", "machine",
            "measurement", "detector", "sensor", "tool",
        ),
    },
    "detail_tweaker": {
        "weight": 0.5,
        "keywords": (
            "细节", "画质增强", "高清", "清晰", "精细",
            "detail", "enhance", "quality", "crisp", "sharp", "clarity",
            "high definition", "HD",
        ),
    },
    "picture_book_illustration": {
        "weight": 0.7,
        "keywords": (
            "绘本", "儿童画", "童话", "手绘温馨", "幼儿", "卡通",
            "children", "storybook", "illustration", "cartoon",
            "fairy tale", "cute", "picture book",
            "child", "kid", "drawing", "hand-drawn", "sketch",
        ),
    },
    "blueprint_xianyu": {
        "weight": 0.65,
        "keywords": (
            "图纸", "蓝图", "工程图", "结构图", "分解图", "机械图",
            "blueprint", "blue print", "technical drawing", "schematic",
            "disassembly", "exploded view", "engineering",
        ),
    },
    "vintage_old_shanghai": {
        "weight": 0.65,
        "keywords": (
            "复古", "老照片", "历史", "民国", "怀旧", "旧时代",
            "vintage", "old photo", "historical", "retro", "antique",
            "nostalgic", "old fashioned",
        ),
    },
    "LowRA": {
        "weight": 0.3,
        "keywords": (),  # 仅自动叠加，不作为主 LoRA 被选中
    },
    "bold_flat_color": {
        "weight": 0.6,
        "keywords": (
            "扁平", "色块", "清亮", "简约", "明亮", "干净",
            "flat", "bold color", "clean", "bright", "minimal",
            "vector", "geometric",
        ),
    },
}

SD15_BUSINESS_KEYWORDS: dict[str, tuple[str, ...]] = {
    "life": (
        "写实", "摄影", "纪实", "vlog", "生活", "日常", "人物", "街景", "户外",
        "美食", "餐饮", "厨房", "烹饪", "家居", "室内", "客厅", "产品", "商品",
        "realistic", "photo", "photography", "lifestyle", "street", "cooking",
        "interior", "product", "daily", "people",
        "close-up", "portrait", "expression", "face", "lighting",
        "scene", "atmosphere", "mood", "person",
    ),
    "science": (
        "科普", "原理", "讲解", "教科书", "教育", "细胞", "器官", "结构", "解剖",
        "线稿", "白底", "标注", "信息图", "流程图", "示意图", "对比图", "扁平",
        "diagram", "textbook", "infographic", "flowchart", "schematic",
        "educational", "labeled", "science", "chart",
        "cross-section", "mechanism", "principle", "white background",
        "molecule", "molecules", "molecular",
    ),
}

_VALID_BUSINESS = frozenset({"life", "science"})
_DEFAULT_LORA = "Casual_Life"
_DEFAULT_BUSINESS = "science"
_PROMPT_EN_MAX_WORDS = 55

_SCIENCE_SUFFIX = "white background, line art, clean composition, no text"
_SCIENCE_DIAGRAM_SUFFIX = "clean light background, educational illustration, no text"
_SCIENCE_SPLIT_SUFFIX = "clean background, no text"
_LIFE_SUFFIX = "natural light, realistic photo"
_LIFE_DIM_SUFFIX = "realistic photo, low-key lighting"
_LIFE_DARK_SUFFIX = "realistic photo, dimly lit, atmospheric"

_DIM_KEYWORDS = (
    "dim", "dark", "underground", "dungeon", "night",
    "shadow", "shadows", "dimly", "darkness",
)

_SCIENCE_LORAS = frozenset({
    "Textbook_Line_Art", "Simple_Diagram", "Science_DNA_Style",
    "Anatomica_Scientifica", "Laboratory_Scene", "Scientific_Equipment",
    "blueprint_xianyu",
})

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
    r"hair|eyes|superhero|anime|dizziness|hypoxia"
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
    business: str = "",
) -> tuple[str, ...]:
    """分子/科学微观场景叠加 Science_DNA_Style；science 暗色背景自动叠 LowRA。"""
    extra: list[str] = []
    if lora != "Science_DNA_Style" and wants_science_dna_lora(prompt=source_prompt, subject=subject):
        if layout == "single":
            extra.append("Science_DNA_Style")
        elif layout == "split" and panel == "left":
            extra.append("Science_DNA_Style")
    if business == "science" and lora != "LowRA":
        extra.append("LowRA")
    return tuple(extra)


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
            business=business,
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
            return f"{lora_prefix} masterpiece, best quality, {style}, {cleaned}, {suffix}"
        return f"{lora_prefix} masterpiece, best quality, {cleaned}, {suffix}"
    return f"{lora_prefix} masterpiece, best quality, {cleaned}, {_resolve_life_suffix(cleaned)}"


def _resolve_life_suffix(subject: str) -> str:
    lower = subject.casefold()
    if any(kw.casefold() in lower for kw in _DIM_KEYWORDS):
        return _LIFE_DIM_SUFFIX
    return _LIFE_SUFFIX


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
        "你必须提炼为 SD1.5 在低分辨率下能准确呈现的画面。\n\n"
        "【第一步：锚定核心主体】\n"
        "先在内心回答（不输出）：「这张图的核心主体是什么？」\n"
        "常见类型参考（十一选一）：\n"
        "  A. 写实场景——有具体物体/人物/空间的真实画面（如厨房操作、户外环境）\n"
        "  B. 结构示意图——单一物体内部结构/流程步骤（如细胞分裂、电路图）\n"
        "  C. 对比图——两个事物/状态并排（如正确 vs 错误、前 vs 后）\n"
        "  D. 线稿解剖图——医学/教科书白底标注线稿（如器官截面、骨骼）\n"
        "  E. 微观分子图——分子/细胞/微观粒子发光科学感（如 CO 分子、蛋白质）\n"
        "  F. 医学截面图——器官/组织解剖横截（如肺气泡、血管截面）\n"
        "  G. 实验室场景——实验台、仪器、科研环境\n"
        "  H. 设备特写——机械装置、仪器特写、检测器材\n"
        "  I. 蓝图工程图——机械分解图、工程结构图、技术图纸\n"
        "  J. 儿童绘本风——温馨手绘、童话卡通、幼儿科普画面\n"
        "  K. 老照片复古——历史场景、旧时代画面、怀旧纪实\n"
        "锚定主体类型后，再决定 layout/lora——不要先选风格再凑主体。\n\n"
        "【第二步：输出 JSON 字段】\n"
        "1. layout：C/E 类型默认 split；A/B/D 类型用 single；"
        "life 内容始终 single。"
        "split 时写 left_en、right_en——横屏对应左/右半，竖屏对应上/下半；"
        "竖屏单主体无对比语义用 single。\n"
        "2. 当 layout=single：prompt_en 为 subject（英文、逗号分隔，30～55 词）；\n"
        "必须忠实保留原文中每个可画出的视觉元素——人物动作、物体状态、光影颜色；\n"
        "抽象情绪（痛苦/压抑）要翻译成具体视觉词（frowning/fogged/purple/bluish）；\n"
        "不堆砌修饰词，不写 lora 标签，不写背景后缀（系统自动追加）。\n"
        "science 时禁止 person/face/head 等人物词。\n"
        "3. 当 layout=split：left_en、right_en 各 15～30 词，各自聚焦单一主体；"
        "left_en 侧重宏观/分子/介质；right_en 侧重医学截面/器官/细胞；"
        "均禁止文字、人物肖像，不写方位词。\n"
        "4. business：life=写实摄影；science=科普插画示意（默认非动漫底模）。\n"
        "5. lora：A 类按主体选 Food_Photo/Home_Interior/Casual_Life/Product_Shot；\n"
        "B 类视内容选 Simple_Diagram 或 Textbook_Line_Art；\n"
        "C 类优先 Simple_Diagram；D 类优先 Textbook_Line_Art；\n"
        "E 类优先 Science_DNA_Style；F 类优先 Anatomica_Scientifica；\n"
        "G 类优先 Laboratory_Scene；H 类优先 Scientific_Equipment；\n"
        "I 类优先 blueprint_xianyu；J 类优先 picture_book_illustration；\n"
        "K 类优先 vintage_old_shanghai。\n"
        "如果画面主体和任何 LoRA 都不明显匹配，life 默认 Casual_Life，science 默认 Simple_Diagram。\n"
        "所有 science 示意图可选叠 bold_flat_color（扁平清亮风格），让画面更干净明亮。\n"
        f"{_lora_catalog_text()}\n\n"
        "science 禁词：hyper-realistic, photorealistic, 3d render, photo, "
        "person, portrait, face, head, glowing eyes。\n"
        "life 禁词：line art, cartoon, diagram。\n\n"
        "【SD1.5 画不出来的东西——必须避开】\n"
        "任何包含具体数字、文字、百分比、仪表读数、数码屏幕、UI 界面、表格的数据可视化；\n"
        "需渲染为无文字、无数字的纯视觉画面，用颜色/大小/位置代替数据。\n\n"
        "【正确 vs 错误示例】\n"
        "❌ 错误（主体堆砌）：\"stainless steel pot, magnet, kitchen counter, "
        "sunlight, reflection, rust, science concept, comparison\"\n"
        "✅ 正确（单主体聚焦）：\"stainless steel pot with magnet attached, "
        "close-up surface detail, metallic sheen\"\n\n"
        "❌ 错误（风格替代主体）：\"educational infographic, colorful diagram, "
        "science poster, clean layout, modern design\"\n"
        "✅ 正确（结构示意图）：\"cross-section diagram of stainless steel alloy layers, "
        "chromium oxide layer highlighted, labeled structure\"\n\n"
        'split 示例：{"layout": "split", '
        '"left_en": "blue wet fabric fiber mesh, red CO molecules passing through gaps", '
        '"right_en": "lung alveoli air sacs, red blood cells turning dark, moist tissue", '
        '"business": "science", "lora": "Simple_Diagram"}\n'
        'single 示例：{"layout": "single", "prompt_en": "labeled cell diagram, nucleus and membrane, white background", '
        '"business": "science", "lora": "Textbook_Line_Art"}\n'
        'life 示例：{"layout": "single", "prompt_en": "home cooking scene, steaming pot on stove, warm window light", '
        '"business": "life", "lora": "Food_Photo"}\n'
        'anatomy 示例：{"layout": "single", "prompt_en": "lung alveoli cross-section, thin tissue walls, capillary network", '
        '"business": "science", "lora": "Anatomica_Scientifica"}\n'
        'lab 示例：{"layout": "single", "prompt_en": "scientific laboratory bench, glass beakers and test tubes, bright white light", '
        '"business": "science", "lora": "Laboratory_Scene"}\n'
        'equipment 示例：{"layout": "single", "prompt_en": "precision measurement instrument close-up, metallic dial, lab setting", '
        '"business": "science", "lora": "Scientific_Equipment"}\n'
        'blueprint 示例：{"layout": "single", "prompt_en": "exploded view diagram of engine cylinder, mechanical parts labeled, white background", '
        '"business": "science", "lora": "blueprint_xianyu"}\n'
        'picture_book 示例：{"layout": "single", "prompt_en": "cute cartoon illustration of a magnet attracting iron nails, bright happy colors, simple shapes", '
        '"business": "science", "lora": "picture_book_illustration"}\n'
        'vintage 示例：{"layout": "single", "prompt_en": "old black and white photograph of 1920s street scene, vintage grain, historical documentary style", '
        '"business": "life", "lora": "vintage_old_shanghai"}\n'
        'portrait 示例：{"layout": "single", "prompt_en": "close-up portrait, coal miner face smudged with dust, wet cloth covering mouth and nose, fogged glasses, purple lips, pained expression, dim claustrophobic lighting", '
        '"business": "life", "lora": "Casual_Life"}'
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
        "请先（在 JSON 外）用一句话说明核心画面主体是什么，列出原文中需要保留的视觉元素清单，"
        "再输出 JSON，字段：layout、prompt_en 或 left_en+right_en、business、lora。\n"
        "prompt_en 包含清单中所有视觉元素（30～55 词）；\n"
        "最显眼的物体或特征放在句子最前面（如 wet cloth over mouth 比 face 更显著则先写 cloth）；\n"
        "不堆砌修饰词；"
        "science 优先 split（对比/分子类），竖屏单主体可 single。"
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

_ANIME_CHECKPOINT = "Counterfeit-V3.0.safetensors"
_LIFE_CHECKPOINT = "DreamShaper_8.safetensors"
# Deliberate v6 SFW：对科普插画/线稿/示意图 LoRA 亲和性比 DreamShaper 好，背景更干净
_SCIENCE_ILLUSTRATION_CHECKPOINT = "Deliberate_v6_SFW.safetensors"
# 分镜右半（医学截面）继续用 RealisticVision，写实解剖效果更好
_SCIENCE_MEDICAL_CHECKPOINT = "RealisticVisionV51.safetensors"

_BUSINESS_CONFIG = {
    "life": {
        "checkpoint": _LIFE_CHECKPOINT,
        "steps": 20,
        "cfg_scale": 7.5,
        "negative": (
            "(worst quality:1.4), (low quality:1.4), lowres, bad anatomy, bad hands, "
            "cartoon, anime, illustration, painting, blurry, deformed, ugly, "
            "watermark, text, logo, oversaturated, "
            "jpeg artifacts, compression artifacts, duplicate, extra fingers, mutated hands"
        ),
    },
    "science": {
        "checkpoint": _SCIENCE_ILLUSTRATION_CHECKPOINT,
        "steps": 25,
        "cfg_scale": 8,
        "negative": (
            "(worst quality:1.4), (low quality:1.4), lowres, "
            "anime, cartoon, manga, chibi, girl, boy, woman, man, face, portrait, "
            "hair, eyes, glowing eyes, superhero, deformed, ugly, watermark, text, "
            "logo, blurry, cluttered, busy background, cluttered background, "
            "low contrast, out of frame, cropped, bad anatomy, landscape"
        ),
    },
}

_SCIENCE_LORA_CFG: dict[str, dict] = {
    "Anatomica_Scientifica": {
        "checkpoint": _SCIENCE_MEDICAL_CHECKPOINT,
        "cfg_scale": 8.5,
        "negative": (
            "(worst quality:1.4), (low quality:1.4), lowres, "
            "text, words, letters, watermark, caption, typography, "
            "landscape, blurry, deformed, anime, cartoon, "
            "busy background, out of frame, oversaturated"
        ),
    },
    "Science_DNA_Style": {
        "cfg_scale": 8.5,
        "negative": (
            "(worst quality:1.4), (low quality:1.4), lowres, "
            "person, face, portrait, landscape, watermark, text, logo, "
            "blurry, deformed, cluttered, out of frame"
        ),
    },
    "Simple_Diagram": {
        "cfg_scale": 7.5,
        "negative": (
            "(worst quality:1.4), (low quality:1.4), lowres, "
            "anime, cartoon, photorealistic, 3d render, "
            "watermark, blurry, deformed, cluttered, out of frame"
        ),
    },
    "Textbook_Line_Art": {
        "cfg_scale": 7.5,
        "negative": (
            "(worst quality:1.4), (low quality:1.4), lowres, "
            "anime, cartoon, photorealistic, 3d render, "
            "watermark, blurry, deformed, cluttered, out of frame"
        ),
    },
    "blueprint_xianyu": {
        "checkpoint": _SCIENCE_ILLUSTRATION_CHECKPOINT,
        "cfg_scale": 7.5,
        "negative": (
            "(worst quality:1.4), (low quality:1.4), lowres, "
            "anime, cartoon, person, face, portrait, landscape, "
            "photorealistic, 3d render, watermark, text, blurry"
        ),
    },
    "picture_book_illustration": {
        "checkpoint": _SCIENCE_ILLUSTRATION_CHECKPOINT,
        "cfg_scale": 7,
        "negative": (
            "(worst quality:1.4), (low quality:1.4), lowres, "
            "photorealistic, hyper-realistic, 3d render, watermark, text, "
            "blurry, deformed, ugly, scary, dark, gloomy"
        ),
    },
    "vintage_old_shanghai": {
        "cfg_scale": 7.5,
        "negative": (
            "(worst quality:1.4), (low quality:1.4), lowres, "
            "modern, digital art, 3d render, cartoon, anime, "
            "watermark, text, logo, oversaturated, hdr"
        ),
    },
}

_SCIENCE_SPLIT_PANELS = {
    "left": {
        "checkpoint": _SCIENCE_ILLUSTRATION_CHECKPOINT,
        "negative": (
            "(worst quality:1.4), (low quality:1.4), lowres, "
            "text, words, letters, lung, anatomy, organ, person, face, portrait, "
            "landscape, blurry, watermark, deformed, "
            "busy background, out of frame"
        ),
    },
    "right": {
        "checkpoint": _SCIENCE_MEDICAL_CHECKPOINT,
        "negative": (
            "(worst quality:1.4), (low quality:1.4), lowres, "
            "text, words, letters, watermark, caption, typography, cloth, fabric, "
            "landscape, blurry, deformed, anime, cartoon, "
            "busy background, out of frame, oversaturated"
        ),
    },
}


def _resolve_checkpoint(*, business: str, prompt: str, lora: str = "", panel: str = "single") -> str:
    if business == "life":
        return _LIFE_CHECKPOINT
    if business == "science" and science_wants_anime(prompt):
        return _ANIME_CHECKPOINT
    if panel == "right":
        return _SCIENCE_SPLIT_PANELS["right"]["checkpoint"]
    if panel == "left":
        return _SCIENCE_SPLIT_PANELS["left"]["checkpoint"]
    if lora in _SCIENCE_LORA_CFG and "checkpoint" in _SCIENCE_LORA_CFG[lora]:
        return _SCIENCE_LORA_CFG[lora]["checkpoint"]
    return _BUSINESS_CONFIG[business]["checkpoint"]


def parse_image_size(size: str) -> tuple[int, int]:
    normalized = size.strip().lower().replace("x", "*")
    w_str, h_str = normalized.split("*", 1)
    return int(w_str.strip()), int(h_str.strip())


@dataclass(frozen=True)
class _Sd15PromptPrep:
    business: str
    lora: str
    layout: str
    split_axis: str = "horizontal"
    prompt_en: str = ""
    left_en: str = ""
    right_en: str = ""


def _fallback_prompt_en(prompt: str) -> str:
    cleaned = prompt.strip()
    if not cleaned:
        return "illustration, soft lighting"
    if not re.search(r"[\u3400-\u9fff]", cleaned):
        return cleaned
    return "illustration, educational scene, soft lighting, clean composition"


def _fallback_business(*, prompt: str, business_override: str | None) -> str:
    if business_override in _BUSINESS_CONFIG:
        return business_override
    return pick_business_by_keywords(prompt)


def _is_sd15_ready_prompt(text: str) -> bool:
    """判断是否为预处理过的英文短 prompt（无中文、词数 ≤ 60）。
    此类 prompt 来自 sd15_prompt_en 字段，已在脚本阶段由 LLM 生成，可跳过二次翻译。
    """
    if re.search(r"[㐀-鿿一-鿿]", text):
        return False
    word_count = len(text.split())
    return 0 < word_count <= 60


def _resolve_layout(
    *,
    result: dict[str, str] | None,
    prompt: str,
    business: str,
    width: int,
    height: int,
) -> tuple[str, str]:
    return resolve_split_layout(
        result=result,
        prompt=prompt,
        business=business,
        width=width,
        height=height,
    )


def _try_parse_split_prompt(cleaned: str) -> tuple[str, str, bool]:
    """从已缓存的 sd15_prompt_en 中检测分图标记并解析。"""
    import re as _re
    # comparison: xxx, yyy → 按逗号拆两半
    for prefix in ("comparison", "vs", "compare"):
        m = _re.match(rf'(?i){prefix}\s*[:：]\s*(.+)', cleaned)
        if m:
            tail = m.group(1)
            comma = tail.find(",")
            if comma > 0 and comma < len(tail) - 3:
                return tail[:comma].strip(), tail[comma + 1:].strip(), True
    # left: xxx, right: yyy
    m = _re.match(r'(?i)left\s*[:：]\s*(.+?)\s*,?\s*right\s*[:：]\s*(.+)', cleaned)
    if m:
        return m.group(1).strip(), m.group(2).strip(), True
    return "", "", False


def _prepare_sd15_prompt(
    prompt: str,
    *,
    size_hint: str | None = None,
    business_override: str | None = None,
) -> _Sd15PromptPrep:
    cleaned = prompt.strip()
    if not cleaned:
        raise ValueError("prompt is required")

    width, height = parse_image_size(size_hint) if size_hint else (0, 0)
    settings = get_settings()

    # ── 快速通道：传入已是英文短 prompt（来自 sd15_prompt_en），跳过 LLM 翻译 ──
    if _is_sd15_ready_prompt(cleaned):
        business = _fallback_business(prompt=cleaned, business_override=business_override)
        lora = pick_lora_by_keywords(cleaned)
        left_en, right_en, is_split = _try_parse_split_prompt(cleaned)
        if is_split:
            left_en = normalize_sd15_panel_prompt_en(left_en, panel="left", business=business, lora=lora)
            right_en = normalize_sd15_panel_prompt_en(right_en, panel="right", business=business, lora=lora)
            layout, split_axis = _resolve_layout(
                result={"layout": "split", "left_en": left_en, "right_en": right_en},
                prompt=cleaned,
                business=business,
                width=width,
                height=height,
            )
            logger.info(
                "sd15 prompt prep fast-path split: business=%s lora=%s left=%s right=%s",
                business, lora, left_en, right_en,
            )
            return _Sd15PromptPrep(
                business=business, lora=lora, layout=layout,
                split_axis=split_axis, left_en=left_en, right_en=right_en,
            )
        prompt_en = normalize_sd15_prompt_en(cleaned, business=business, lora=lora)
        logger.info(
            "sd15 prompt prep fast-path (sd15_prompt_en): business=%s lora=%s prompt_en=%s",
            business,
            lora,
            prompt_en,
        )
        return _Sd15PromptPrep(
            business=business,
            lora=lora,
            layout="single",
            prompt_en=prompt_en,
        )

    llm_result: dict[str, str] | None = None

    if settings.deepseek_api_key:
        try:
            llm_result = llm_mgr.prepare_sd15_image_prompt(
                cleaned,
                size_hint=size_hint,
                business_override=business_override,
            )
            logger.info(
                "sd15 prompt prep llm: layout=%s business=%s lora=%s payload=%s",
                llm_result.get("layout", "single"),
                llm_result["business"],
                llm_result["lora"],
                llm_result,
            )
        except Exception as exc:
            logger.warning("sd15 prompt prep llm failed, using fallback: %s", exc)

    if llm_result:
        business = llm_result["business"]
        lora = llm_result["lora"]
        layout, split_axis = _resolve_layout(
            result=llm_result,
            prompt=cleaned,
            business=business,
            width=width,
            height=height,
        )
        if layout == "split":
            left_en = llm_result.get("left_en", "")
            right_en = llm_result.get("right_en", "")
            if not left_en or not right_en:
                left_en, right_en = fallback_split_panel_prompts(cleaned)
            return _Sd15PromptPrep(
                business=business,
                lora=lora,
                layout="split",
                split_axis=split_axis,
                left_en=left_en,
                right_en=right_en,
            )
        return _Sd15PromptPrep(
            business=business,
            lora=lora,
            layout="single",
            prompt_en=llm_result.get("prompt_en", ""),
        )

    lora = pick_lora_by_keywords(cleaned)
    business = _fallback_business(prompt=cleaned, business_override=business_override)
    layout, split_axis = _resolve_layout(
        result=None,
        prompt=cleaned,
        business=business,
        width=width,
        height=height,
    )
    if layout == "split":
        left_en, right_en = fallback_split_panel_prompts(cleaned)
        logger.info(
            "sd15 prompt prep fallback split: axis=%s business=%s lora=%s left=%s right=%s",
            split_axis,
            business,
            lora,
            left_en,
            right_en,
        )
        return _Sd15PromptPrep(
            business=business,
            lora=lora,
            layout="split",
            split_axis=split_axis,
            left_en=left_en,
            right_en=right_en,
        )

    prompt_en = normalize_sd15_prompt_en(
        _fallback_prompt_en(cleaned),
        business=business,
        lora=lora,
    )
    logger.info(
        "sd15 prompt prep fallback: business=%s lora=%s prompt_en=%s",
        business,
        lora,
        prompt_en,
    )
    return _Sd15PromptPrep(
        business=business,
        lora=lora,
        layout="single",
        prompt_en=prompt_en,
    )


def _stitch_vertical(top_bytes: bytes, bottom_bytes: bytes) -> bytes:
    top_img = Image.open(io.BytesIO(top_bytes)).convert("RGB")
    bottom_img = Image.open(io.BytesIO(bottom_bytes)).convert("RGB")
    width = max(top_img.width, bottom_img.width)
    total_h = top_img.height + bottom_img.height
    canvas = Image.new("RGB", (width, total_h))
    canvas.paste(top_img, (0, 0))
    canvas.paste(bottom_img, (0, top_img.height))
    buf = io.BytesIO()
    canvas.save(buf, format="PNG")
    return buf.getvalue()


def _stitch_horizontal(left_bytes: bytes, right_bytes: bytes) -> bytes:
    left_img = Image.open(io.BytesIO(left_bytes)).convert("RGB")
    right_img = Image.open(io.BytesIO(right_bytes)).convert("RGB")
    total_w = left_img.width + right_img.width
    height = max(left_img.height, right_img.height)
    canvas = Image.new("RGB", (total_w, height))
    canvas.paste(left_img, (0, 0))
    canvas.paste(right_img, (left_img.width, 0))
    buf = io.BytesIO()
    canvas.save(buf, format="PNG")
    return buf.getvalue()


class Sd15ImageProvider(ImageProvider):
    _checkpoint_lock = Semaphore(value=1)

    def __init__(self) -> None:
        settings = get_settings()
        self._api_url = settings.sd_api_url.rstrip("/")
        self._business_override = settings.sd_business
        self._default_size = settings.sd_image_size
        self._timeout_sec = settings.sd_timeout_sec
        self._fallback = MockImageProvider()
        self._current_checkpoint: str | None = None

    def describe_params(self, *, size: str | None = None) -> str:
        business = self._business_override or "prompt_infer"
        lora_hint = "llm_pick|" + "|".join(SD15_LORAS)
        resolved_size = size or self._default_size
        return (
            f"provider=sd15_t2i, api={self._api_url}, business={business}, "
            f"lora={lora_hint}, checkpoints=life:{_LIFE_CHECKPOINT}|"
            f"science:{_SCIENCE_ILLUSTRATION_CHECKPOINT}|"
            f"anatomy:{_SCIENCE_MEDICAL_CHECKPOINT}|anime:{_ANIME_CHECKPOINT}, "
            f"layout=split_science, size={resolved_size}"
        )

    def _cfg_for_business(self, business: str, lora: str = "") -> dict:
        if business not in _BUSINESS_CONFIG:
            raise ValueError(f"unknown sd15 business: {business}")
        base = dict(_BUSINESS_CONFIG[business])
        if lora in _SCIENCE_LORA_CFG:
            override = _SCIENCE_LORA_CFG[lora]
            base.update({k: v for k, v in override.items() if v is not None})
        return base

    def _switch_checkpoint(self, checkpoint: str) -> None:
        with self._checkpoint_lock:
            if self._current_checkpoint == checkpoint:
                return
            resp = requests.post(
                f"{self._api_url}/sdapi/v1/options",
                json={"sd_model_checkpoint": checkpoint},
                timeout=60,
            )
            resp.raise_for_status()
            self._current_checkpoint = checkpoint

    def _txt2img(
        self,
        *,
        full_prompt: str,
        negative_prompt: str,
        checkpoint: str,
        width: int,
        height: int,
        steps: int,
        cfg_scale: float,
        seed: int = -1,
    ) -> bytes:
        self._switch_checkpoint(checkpoint)
        payload: dict = {
            "prompt": full_prompt,
            "negative_prompt": negative_prompt,
            "steps": steps,
            "cfg_scale": cfg_scale,
            "width": width,
            "height": height,
            "sampler_name": "DPM++ 2M",
            "scheduler": "Karras",
            "batch_size": 1,
            "n_iter": 1,
            "seed": seed,
            "enable_hr": False,
            "override_settings": {"CLIP_stop_at_last_layers": 2},
        }
        resp = requests.post(
            f"{self._api_url}/sdapi/v1/txt2img",
            json=payload,
            timeout=self._timeout_sec,
        )
        resp.raise_for_status()
        data = resp.json()
        return base64.b64decode(data["images"][0])

    def _generate_split(
        self,
        prep: _Sd15PromptPrep,
        *,
        width: int,
        height: int,
        cfg: dict,
        prompt: str,
    ) -> bytes:
        first_prompt = build_sd15_full_prompt(
            subject=prep.left_en,
            business=prep.business,
            lora=prep.lora,
            layout="split",
            panel="left",
            source_prompt=prompt,
        )
        second_prompt = build_sd15_full_prompt(
            subject=prep.right_en,
            business=prep.business,
            lora=prep.lora,
            layout="split",
            panel="right",
            source_prompt=prompt,
        )
        first_cfg = _SCIENCE_SPLIT_PANELS["left"]
        second_cfg = _SCIENCE_SPLIT_PANELS["right"]
        vertical = prep.split_axis == "vertical"

        if vertical:
            panel_w, panel_h = width, height // 2
        else:
            panel_w, panel_h = width // 2, height
        max_dim = max(panel_w, panel_h)
        if max_dim < 512:
            scale = 512 / max_dim
            panel_w = int(panel_w * scale)
            panel_h = int(panel_h * scale)

        logger.info(
            "sd15 split request: axis=%s lora=%s panel=%s*%s "
            "first_checkpoint=%s second_checkpoint=%s first_prompt=%s second_prompt=%s",
            prep.split_axis,
            prep.lora,
            panel_w,
            panel_h,
            first_cfg["checkpoint"],
            second_cfg["checkpoint"],
            first_prompt,
            second_prompt,
        )
        first_bytes = self._txt2img(
            full_prompt=first_prompt,
            negative_prompt=first_cfg["negative"],
            checkpoint=_resolve_checkpoint(business=prep.business, prompt=prompt, lora=prep.lora, panel="left"),
            width=panel_w,
            height=panel_h,
            steps=cfg["steps"],
            cfg_scale=cfg["cfg_scale"],
            seed=42,
        )
        second_bytes = self._txt2img(
            full_prompt=second_prompt,
            negative_prompt=second_cfg["negative"],
            checkpoint=_resolve_checkpoint(business=prep.business, prompt=prompt, lora=prep.lora, panel="right"),
            width=panel_w,
            height=panel_h,
            steps=cfg["steps"],
            cfg_scale=cfg["cfg_scale"],
            seed=99,
        )
        if vertical:
            result = _stitch_vertical(first_bytes, second_bytes)
        else:
            result = _stitch_horizontal(first_bytes, second_bytes)
        img = Image.open(io.BytesIO(result))
        img = img.resize((width, height), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    def generate(self, prompt: str, output_path: Path, *, size: str | None = None, ref_images: list[Path] | None = None) -> Path:
        size = size or self._default_size
        prep = _prepare_sd15_prompt(
            prompt,
            size_hint=size,
            business_override=self._business_override,
        )
        business = prep.business
        lora = prep.lora
        cfg = self._cfg_for_business(business, lora=lora)
        api_width, api_height = parse_image_size(size)

        logger.info(
            "sd15 request: layout=%s axis=%s business=%s lora=%s checkpoint=%s cfg_scale=%s job_size=%s api=%s*%s",
            prep.layout,
            prep.split_axis,
            business,
            lora,
            cfg.get("checkpoint", "?"),
            cfg["cfg_scale"],
            size,
            api_width,
            api_height,
        )
        try:
            if prep.layout == "split":
                img_bytes = self._generate_split(
                    prep,
                    width=api_width,
                    height=api_height,
                    cfg=cfg,
                    prompt=prompt,
                )
            else:
                checkpoint = _resolve_checkpoint(business=business, prompt=prompt, lora=lora)
                full_prompt = build_sd15_full_prompt(
                    subject=prep.prompt_en,
                    business=business,
                    lora=lora,
                    source_prompt=prompt,
                )
                logger.info(
                    "sd15 single request: checkpoint=%s lora=%s prompt_en=%s full_prompt=%s",
                    checkpoint,
                    lora,
                    prep.prompt_en,
                    full_prompt,
                )
                img_bytes = self._txt2img(
                    full_prompt=full_prompt,
                    negative_prompt=cfg["negative"],
                    checkpoint=checkpoint,
                    width=api_width,
                    height=api_height,
                    steps=cfg["steps"],
                    cfg_scale=cfg["cfg_scale"],
                )
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(img_bytes)
            return output_path
        except Exception as exc:
            logger.error("sd15 generate failed: %s", exc)
            if get_settings().mock_mode:
                return self._fallback.generate(prompt, output_path, size=size)
            raise