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


_THEMES_SCIENCE_CHILD = IntroTheme(
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
    )

THEMES: dict[str, IntroTheme] = {
    "百科": _THEMES_SCIENCE_CHILD,
    "童趣日常": IntroTheme(
        bg_top=_THEMES_SCIENCE_CHILD.bg_top,
        bg_bottom=_THEMES_SCIENCE_CHILD.bg_bottom,
        title_fill=_THEMES_SCIENCE_CHILD.title_fill,
        title_stroke=_THEMES_SCIENCE_CHILD.title_stroke,
        brand_fill=_THEMES_SCIENCE_CHILD.brand_fill,
        brand_stroke=_THEMES_SCIENCE_CHILD.brand_stroke,
        title_circle_top=_THEMES_SCIENCE_CHILD.title_circle_top,
        title_circle_bottom=_THEMES_SCIENCE_CHILD.title_circle_bottom,
        badge_text="日常",
        badge_bg=_THEMES_SCIENCE_CHILD.badge_bg,
        badge_fg=_THEMES_SCIENCE_CHILD.badge_fg,
        accent=_THEMES_SCIENCE_CHILD.accent,
        particle=_THEMES_SCIENCE_CHILD.particle,
    ),
    "历史悬案": IntroTheme(
        bg_top=(15, 8, 5),
        bg_bottom=(50, 30, 20),
        title_fill=(220, 170, 100, 255),
        title_stroke=(60, 30, 15, 255),
        brand_fill=(255, 255, 255, 255),
        brand_stroke=(60, 30, 15, 255),
        title_circle_top=(80, 40, 20, 255),
        title_circle_bottom=(20, 10, 5, 40),
        badge_text="谜案",
        badge_bg=(40, 20, 10, 220),
        badge_fg=(220, 170, 100, 255),
        accent=(180, 100, 40, 255),
        particle=(200, 150, 80, 30),
    ),
}


def get_intro_theme(category: str | None = None) -> IntroTheme:
    key = (category or DEFAULT_CATEGORY).strip()
    return THEMES.get(key, THEMES[DEFAULT_CATEGORY])
