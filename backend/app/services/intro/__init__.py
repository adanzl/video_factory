"""片头模块：主题色系、帧动画合成、品牌喊声。"""

from app.services.intro.generator import generate_intro
from app.services.intro.themes import DEFAULT_CATEGORY, IntroTheme, get_intro_theme

__all__ = ["DEFAULT_CATEGORY", "IntroTheme", "generate_intro", "get_intro_theme"]
