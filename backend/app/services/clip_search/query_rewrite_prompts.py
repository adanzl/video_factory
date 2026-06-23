"""Pixabay 素材搜索关键词：提示词与解析。"""

from __future__ import annotations

import re
from typing import Any


def build_pixabay_query_system_prompt() -> str:
    return (
        "你是免版权视频库 Pixabay 的搜索关键词优化师。"
        "Pixabay 以英文标签为主，用户常输入中文画面描述、口播片段或运动提示词，"
        "你需要将其转为在该平台命中率高的英文搜索词。\n\n"
        "输出要求：\n"
        "1. 只输出 JSON，字段 search_query（字符串）。\n"
        "2. search_query 为 2～6 个英文单词，空格分隔，描述可拍摄的具象画面。\n"
        "3. 优先物体、动作、场景、自然现象等 stock 视频常见题材；"
        "去掉字幕、文案、旁白、品牌名等无法在素材库里直接找到的内容。\n"
        "4. 避免抽象词（如 truth、concept、idea）和过长短语；"
        "必要时选同义但更具体的词（如「磁铁实验」→ magnet experiment）。\n"
        "5. 若输入已是合适的英文关键词，可微调或直接保留。\n"
        "6. 不要输出中文、解释、引号或标点。\n\n"
        '示例：{"search_query": "magnet experiment"}'
    )


def build_pixabay_query_user_prompt(*, query: str, language: str | None) -> str:
    lang_hint = {
        "zh": "中文",
        "en": "英文",
    }.get(language or "", "不限")
    trimmed = query.strip()
    if len(trimmed) > 500:
        trimmed = trimmed[:500] + "…"
    return (
        f"用户语言偏好：{lang_hint}\n"
        f"用户输入：\n{trimmed}\n\n"
        "请输出适合 Pixabay 视频搜索的 search_query。"
    )


def parse_pixabay_query_payload(raw: dict[str, Any]) -> str:
    value = raw.get("search_query")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("LLM response missing search_query")
    cleaned = re.sub(r"\s+", " ", value.strip())
    cleaned = cleaned.strip("\"'`")
    if not cleaned:
        raise ValueError("search_query is empty")
    if len(cleaned) > 120:
        cleaned = cleaned[:120].rsplit(" ", 1)[0] or cleaned[:120]
    return cleaned
