"""文生图提示词质检阈值与重试文案。"""

from __future__ import annotations

MIN_IMAGE_PROMPT_CHARS = 50
IMAGE_PROMPT_TARGET_CHARS = 200
MIN_IMAGE_PROMPT_CHARS_SD15 = 20
IMAGE_PROMPT_TARGET_CHARS_SD15 = 60
MIN_SD15_PROMPT_EN_WORDS = 8
TARGET_SD15_PROMPT_EN_WORDS = 12


def image_prompt_min_chars(*, sd15_mode: bool = False) -> int:
    return MIN_IMAGE_PROMPT_CHARS_SD15 if sd15_mode else MIN_IMAGE_PROMPT_CHARS


def image_prompt_target_chars(*, sd15_mode: bool = False) -> int:
    return IMAGE_PROMPT_TARGET_CHARS_SD15 if sd15_mode else IMAGE_PROMPT_TARGET_CHARS


def sd15_prompt_en_word_count(value: object) -> int:
    if not isinstance(value, str):
        return 0
    text = value.strip()
    if not text:
        return 0
    return len(text.split())


def sd15_prompt_en_ok(value: object) -> bool:
    return sd15_prompt_en_word_count(value) >= MIN_SD15_PROMPT_EN_WORDS


def image_prompt_threshold_label(*, sd15_mode: bool = False) -> str:
    min_chars = image_prompt_min_chars(sd15_mode=sd15_mode)
    target_chars = image_prompt_target_chars(sd15_mode=sd15_mode)
    label = f"image_prompt>={min_chars}chars(target{target_chars})"
    if sd15_mode:
        label += (
            f" sd15_prompt_en>={MIN_SD15_PROMPT_EN_WORDS}words"
            f"(target{TARGET_SD15_PROMPT_EN_WORDS})"
        )
    return label


def format_image_prompt_retry_segments(segments: list[dict]) -> str:
    parts: list[str] = []
    for item in segments:
        idx = item.get("segment_index")
        metrics: list[str] = []
        if "chars" in item:
            metrics.append(f"{item['chars']}chars")
        if "words" in item:
            metrics.append(f"{item['words']}words")
        if metrics:
            parts.append(f"#{idx}({','.join(metrics)})")
        else:
            parts.append(f"#{idx}")
    return ", ".join(parts)


def format_image_prompt_retry_warning(
    *,
    attempt: int,
    reason: str,
    segments: list[dict],
    sd15_mode: bool = False,
) -> str:
    return (
        f"[SCRIPT] image_prompt retry attempt={attempt} reason={reason} "
        f"threshold={image_prompt_threshold_label(sd15_mode=sd15_mode)} "
        f"segments=[{format_image_prompt_retry_segments(segments)}]"
    )
