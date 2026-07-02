"""script 阶段：文生图提示词质检与长度阈值。"""

from __future__ import annotations

from app.quality.models import QualityReport

MIN_IMAGE_PROMPT_CHARS = 50
IMAGE_PROMPT_TARGET_CHARS = 200
MIN_IMAGE_PROMPT_CHARS_SD15 = 20
IMAGE_PROMPT_TARGET_CHARS_SD15 = 60
MIN_SD15_PROMPT_EN_WORDS = 8
TARGET_SD15_PROMPT_EN_WORDS = 12

__all__ = [
    "IMAGE_PROMPT_TARGET_CHARS",
    "MIN_IMAGE_PROMPT_CHARS",
    "MIN_SD15_PROMPT_EN_WORDS",
    "TARGET_SD15_PROMPT_EN_WORDS",
    "check_image_prompt",
    "format_image_prompt_retry_warning",
    "image_prompt_min_chars",
    "image_prompt_target_chars",
    "sd15_prompt_en_ok",
    "sd15_prompt_en_word_count",
    "skip_image_prompt_check",
]


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


def _image_prompt_threshold_label(*, sd15_mode: bool = False) -> str:
    min_chars = image_prompt_min_chars(sd15_mode=sd15_mode)
    target_chars = image_prompt_target_chars(sd15_mode=sd15_mode)
    label = f"image_prompt>={min_chars}chars(target{target_chars})"
    if sd15_mode:
        label += (
            f" sd15_prompt_en>={MIN_SD15_PROMPT_EN_WORDS}words"
            f"(target{TARGET_SD15_PROMPT_EN_WORDS})"
        )
    return label


def _format_image_prompt_retry_segments(segments: list[dict]) -> str:
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
        f"threshold={_image_prompt_threshold_label(sd15_mode=sd15_mode)} "
        f"segments=[{_format_image_prompt_retry_segments(segments)}]"
    )


def check_image_prompt(
    script: dict,
    *,
    sd15_mode: bool | None = None,
    segment_indices: list[int] | None = None,
) -> QualityReport:
    """各段 image_prompt 长度；SD15 模式另校验 sd15_prompt_en。"""
    if sd15_mode is None:
        sd15_mode = bool(script.get("include_sd15_prompt"))
    min_chars = image_prompt_min_chars(sd15_mode=sd15_mode)
    target_chars = image_prompt_target_chars(sd15_mode=sd15_mode)
    segments = script.get("segments") or []
    if segment_indices is not None:
        wanted = {int(idx) for idx in segment_indices}
        segments = [
            seg
            for seg in segments
            if int(seg.get("segment_index", -1)) in wanted
        ]
    if not segments:
        return QualityReport(
            level="major",
            step="image_prompts",
            fail_stage="script",
            details={"reason": "no segments"},
        )

    too_short: list[dict] = []
    slightly_short: list[dict] = []
    missing_sd15: list[dict] = []
    bad_sd15: list[dict] = []
    weak_sd15: list[dict] = []
    for seg in segments:
        idx = seg.get("segment_index")
        prompt_len = len(str(seg.get("image_prompt") or ""))
        if prompt_len < min_chars:
            too_short.append(
                {
                    "segment_index": idx,
                    "chars": prompt_len,
                    "min_chars": min_chars,
                }
            )
        elif prompt_len < target_chars:
            slightly_short.append(
                {
                    "segment_index": idx,
                    "chars": prompt_len,
                    "target_chars": target_chars,
                }
            )
        if sd15_mode:
            words = sd15_prompt_en_word_count(seg.get("sd15_prompt_en"))
            if words == 0:
                missing_sd15.append({"segment_index": idx, "words": 0})
            elif words < MIN_SD15_PROMPT_EN_WORDS:
                bad_sd15.append({"segment_index": idx, "words": words})
            elif words < TARGET_SD15_PROMPT_EN_WORDS:
                weak_sd15.append({"segment_index": idx, "words": words})

    if bad_sd15:
        return QualityReport(
            level="major",
            step="image_prompts",
            fail_stage="script",
            details={
                "reason": "sd15_prompt_en too short",
                "segments": bad_sd15,
            },
        )
    if too_short:
        return QualityReport(
            level="major",
            step="image_prompts",
            fail_stage="script",
            details={"reason": "image_prompt too short", "segments": too_short},
        )
    if missing_sd15:
        return QualityReport(
            level="minor",
            step="image_prompts",
            details={
                "reason": "sd15_prompt_en missing, fallback at image gen",
                "segments": missing_sd15,
            },
        )
    if weak_sd15:
        return QualityReport(
            level="minor",
            step="image_prompts",
            details={
                "reason": "sd15_prompt_en slightly short",
                "segments": weak_sd15,
                "target_words": TARGET_SD15_PROMPT_EN_WORDS,
            },
        )
    if slightly_short:
        return QualityReport(
            level="minor",
            step="image_prompts",
            details={
                "reason": "image_prompt slightly short",
                "segments": slightly_short,
            },
        )
    return QualityReport(
        level="pass",
        step="image_prompts",
        details={"segment_count": len(segments)},
    )


def skip_image_prompt_check() -> QualityReport:
    """未勾选生成文生图提示词时，跳过相关质检。"""
    return QualityReport(
        level="pass",
        step="image_prompts",
        details={"reason": "skipped", "generate_image_prompts": False},
    )
