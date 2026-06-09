"""CosyVoice Instruct 文案：须与音色严格匹配，见百炼音色列表文档。"""

from __future__ import annotations

# 文档：https://help.aliyun.com/zh/model-studio/cosyvoice-voice-list
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


def resolve_instruction(
    voice: str,
    *,
    explicit: str | None = None,
    preset: str | None = None,
) -> str | None:
    if explicit and explicit.strip():
        return explicit.strip()
    if not preset:
        return None
    by_voice = VOICE_INSTRUCT_PRESETS.get(preset.strip().lower())
    if not by_voice:
        return None
    return by_voice.get(voice)
