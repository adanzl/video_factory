"""片段搜索语言选项（Pexels locale / Pixabay lang）。"""

from __future__ import annotations

_VALID_LANGUAGES = frozenset({"zh", "en"})


def normalize_search_language(raw: str | None) -> str | None:
    if raw is None:
        return None
    value = raw.strip().lower()
    if not value:
        return None
    if value in {"zh", "zh-cn", "zh-tw", "chinese", "中文"}:
        return "zh"
    if value in {"en", "en-us", "english", "英文"}:
        return "en"
    if value not in _VALID_LANGUAGES:
        raise ValueError("language must be zh, en, or empty")
    return value


def pexels_locale(language: str | None) -> str | None:
    if language == "zh":
        return "zh-CN"
    if language == "en":
        return "en-US"
    return None


def pixabay_lang(language: str | None) -> str | None:
    if language in {"zh", "en"}:
        return language
    return None
