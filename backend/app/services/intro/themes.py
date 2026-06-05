"""片头分类色系（MVP：百科）。"""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_CATEGORY = "百科"


@dataclass(frozen=True)
class IntroTheme:
    bg_top: tuple[int, int, int]
    bg_bottom: tuple[int, int, int]
    title_fill: tuple[int, int, int, int]
    title_stroke: tuple[int, int, int, int]
    brand_fill: tuple[int, int, int, int]
    brand_stroke: tuple[int, int, int, int]
    title_circle_top: tuple[int, int, int, int]
    title_circle_bottom: tuple[int, int, int, int]
    badge_text: str
    badge_bg: tuple[int, int, int, int]
    badge_fg: tuple[int, int, int, int]
    accent: tuple[int, int, int, int]
    particle: tuple[int, int, int, int]


THEMES: dict[str, IntroTheme] = {
    "百科": IntroTheme(
        bg_top=(26, 58, 110),
        bg_bottom=(196, 218, 245),
        title_fill=(255, 214, 64, 255),
        title_stroke=(18, 48, 92, 255),
        brand_fill=(220, 38, 38, 255),
        brand_stroke=(255, 255, 255, 255),
        title_circle_top=(8, 18, 40, 255),
        title_circle_bottom=(8, 18, 40, 40),
        badge_text="百科",
        badge_bg=(255, 255, 255, 220),
        badge_fg=(26, 58, 110, 255),
        accent=(255, 214, 64, 255),
        particle=(255, 255, 255, 40),
    ),
    # 预留：生活 / 历史 / 科技 …
}


def get_intro_theme(category: str | None = None) -> IntroTheme:
    key = (category or DEFAULT_CATEGORY).strip()
    return THEMES.get(key, THEMES[DEFAULT_CATEGORY])
