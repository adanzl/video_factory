"""CosyVoice Instruct 文案：须与音色严格匹配，见百炼音色列表文档。"""

from __future__ import annotations

# 文档：https://help.aliyun.com/zh/model-studio/cosyvoice-voice-list
# 系统音色 preset（固定句式，见音色列表文档）
VOICE_INSTRUCT_PRESETS: dict[str, dict[str, str]] = {
    "science_adult": {
        "longanhuan": "你正在进行科普知识推广，你说话的情感是neutral。",  # cSpell: disable-line
        "longanhuan_v3": "你说话的情感是neutral。请用普通话表达。",  # cSpell: disable-line
    },
    "science_child": {
        "longhuhu_v3": "你说话的角色是可爱孩童，你说话的情感是neutral。",  # cSpell: disable-line
        "longhuhu": "你说话的角色是可爱孩童，你说话的情感是neutral。",  # cSpell: disable-line
    },
}

# 复刻 / 自定义 voice ID → 自然语言 instruction（v3.5-flash 复刻音色适用）
# 新增复刻音色时在此追加；任务页选中的 voice 会优先匹配本表
VOICE_INSTRUCTIONS: dict[str, str] = {
    "cosyvoice-v3.5-flash-leo-60621bdce780434ab0734555e5196d7d": (
        "语速适中，吐字清晰，语气亲切，适合儿童科普短视频。"
    ),  # cSpell: disable-line cancan
}


def resolve_instruction(
    voice: str,
    *,
    explicit: str | None = None,
    preset: str | None = None,
) -> str | None:
    """解析 instruction，优先级：TTS_INSTRUCTION > VOICE_INSTRUCTIONS > preset。"""
    if explicit and explicit.strip():
        return explicit.strip()
    by_voice = VOICE_INSTRUCTIONS.get(voice)
    if by_voice:
        return by_voice
    if not preset:
        return None
    by_preset = VOICE_INSTRUCT_PRESETS.get(preset.strip().lower())
    if not by_preset:
        return None
    return by_preset.get(voice)
