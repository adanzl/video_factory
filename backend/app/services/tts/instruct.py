"""CosyVoice Instruct 文案：须与音色严格匹配，见百炼音色列表文档。"""

from __future__ import annotations

# 系统音色 preset（固定句式，见音色列表文档）
# 默认关闭；需要时在环境变量 TTS_INSTRUCTION 显式指定
VOICE_INSTRUCT_PRESETS: dict[str, dict[str, str]] = {}

# 复刻 / 自定义 voice ID → 自然语言 instruction（v3.5-flash 复刻音色适用）
VOICE_INSTRUCTIONS: dict[str, str] = {}


def resolve_instruction(
    voice: str,
    *,
    explicit: str | None = None,
    preset: str | None = None,
) -> str | None:
    """解析 instruction，优先级：TTS_INSTRUCTION > VOICE_INSTRUCTIONS > preset。"""
    _ = voice, preset
    if explicit and explicit.strip():
        return explicit.strip()
    return None
