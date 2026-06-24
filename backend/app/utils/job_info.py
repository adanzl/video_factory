"""video_job.info JSON 字段解析与合并。"""

from __future__ import annotations

import json
from typing import Any

ORIENTATION_AUTO = "auto"
ORIENTATION_PORTRAIT = "portrait"
ORIENTATION_LANDSCAPE = "landscape"

CONTENT_STYLE_SCIENCE_CHILD = "science_child"
CONTENT_STYLE_LIFE_EXPERIENCE = "life_experience"

_VALID_CONTENT_STYLES = frozenset(
    {CONTENT_STYLE_SCIENCE_CHILD, CONTENT_STYLE_LIFE_EXPERIENCE}
)

_VALID_IMAGE_PROVIDERS = frozenset({"z_image_t2i", "wan_t2i", "sd15_t2i"})
_VALID_VIDEO_PROVIDERS = frozenset({"ffmpeg", "wan_i2v"})


def parse_job_info(raw: str | dict | None) -> dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return dict(raw)
    if not isinstance(raw, str):
        return {}
    text = raw.strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return dict(parsed) if isinstance(parsed, dict) else {}


def normalize_orientation(value: str | None) -> str | None:
    """将 orientation 规范为 auto / portrait / landscape。"""
    if value is None:
        return None
    normalized = value.strip().lower()
    if not normalized or normalized in {"auto", "自动", "default"}:
        return ORIENTATION_AUTO
    if normalized in {ORIENTATION_PORTRAIT, "竖屏", "vertical", "9:16", "9x16"}:
        return ORIENTATION_PORTRAIT
    if normalized in {ORIENTATION_LANDSCAPE, "横屏", "horizontal", "16:9", "16x9"}:
        return ORIENTATION_LANDSCAPE
    return None


def orientation_from_dimensions(width: int, height: int) -> str:
    if width > height:
        return ORIENTATION_LANDSCAPE
    return ORIENTATION_PORTRAIT


def orientation_for_resolve(job: dict) -> str | None:
    """读取 job.info.orientation，供片头尺寸解析（auto 返回 None）。"""
    raw = parse_job_info(job.get("info")).get("orientation")
    if not isinstance(raw, str):
        return None
    normalized = normalize_orientation(raw)
    if normalized in {ORIENTATION_PORTRAIT, ORIENTATION_LANDSCAPE}:
        return normalized
    return None


def default_orientation_for_pipeline(pipeline: str | None) -> str:
    if (pipeline or "standard").strip() == "material":
        return ORIENTATION_AUTO
    return ORIENTATION_PORTRAIT


def normalize_content_style(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    aliases = {
        "science": CONTENT_STYLE_SCIENCE_CHILD,
        "科普": CONTENT_STYLE_SCIENCE_CHILD,
        "童趣科普": CONTENT_STYLE_SCIENCE_CHILD,
        "life": CONTENT_STYLE_LIFE_EXPERIENCE,
        "生活": CONTENT_STYLE_LIFE_EXPERIENCE,
        "生活经验": CONTENT_STYLE_LIFE_EXPERIENCE,
        "vlog": CONTENT_STYLE_LIFE_EXPERIENCE,
    }
    if normalized in aliases:
        return aliases[normalized]
    if normalized in _VALID_CONTENT_STYLES:
        return normalized
    return None


def content_style_from_job(job: dict) -> str:
    raw = parse_job_info(job.get("info")).get("content_style")
    if isinstance(raw, str):
        normalized = normalize_content_style(raw)
        if normalized:
            return normalized
    return CONTENT_STYLE_SCIENCE_CHILD


def is_landscape_job(job: dict) -> bool:
    return orientation_for_resolve(job) == ORIENTATION_LANDSCAPE


def resolve_segment_image_size(job: dict | None = None, *, settings: Any | None = None) -> str:
    """按 job orientation 解析分镜静图尺寸（Wan/Z-Image 格式 width*height）。"""
    from app.config import get_settings

    cfg = settings or get_settings()
    provider = resolve_image_provider(job, settings=cfg)
    default = (
        cfg.z_image_size
        if provider == "z_image_t2i"
        else cfg.sd_image_size
        if provider == "sd15_t2i"
        else cfg.wan_image_size
    )
    normalized = default.strip().lower().replace("x", "*")
    w_str, h_str = normalized.split("*", 1)
    width, height = int(w_str.strip()), int(h_str.strip())

    orient = orientation_for_resolve(job or {})
    if orient == ORIENTATION_LANDSCAPE:
        if width < height:
            width, height = height, width
    elif width > height:
        width, height = height, width
    return f"{width}*{height}"


def resolve_segment_video_size(job: dict | None = None, *, settings: Any | None = None) -> tuple[int, int]:
    """按 job orientation 解析分镜 clip 输出尺寸（width, height）。"""
    from app.config import get_settings
    from app.services.intro.size import landscape_size, portrait_size

    cfg = settings or get_settings()
    orient = orientation_for_resolve(job or {})
    if orient == ORIENTATION_LANDSCAPE:
        return landscape_size(cfg)
    return portrait_size(cfg)


def default_content_style_for_pipeline(pipeline: str | None) -> str:
    return CONTENT_STYLE_SCIENCE_CHILD


def normalize_image_provider(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if normalized in _VALID_IMAGE_PROVIDERS:
        return normalized
    return None


def resolve_image_provider(job: dict | None = None, *, settings: Any | None = None) -> str:
    """job.info.image_provider 优先，否则全局 IMAGE_PROVIDER。"""
    from app.config import get_settings

    cfg = settings or get_settings()
    override = normalize_image_provider(parse_job_info((job or {}).get("info")).get("image_provider"))
    if override:
        return override
    return cfg.image_provider


def normalize_video_provider(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if normalized in _VALID_VIDEO_PROVIDERS:
        return normalized
    return None


def resolve_video_provider(
    job: dict | None = None,
    *,
    visual_mode: str | None = None,
    settings: Any | None = None,
) -> str:
    """job.info.video_provider 优先；否则按 visual_mode 与 CLIP_PROVIDER。"""
    from app.config import get_settings

    cfg = settings or get_settings()
    override = normalize_video_provider(parse_job_info((job or {}).get("info")).get("video_provider"))
    if override:
        return override
    if visual_mode == "wan_i2v":
        return "wan_i2v"
    return cfg.clip_provider


def merge_job_info(existing: str | dict | None, **updates: Any) -> dict[str, Any]:
    merged = parse_job_info(existing)
    for key, value in updates.items():
        if value is None:
            merged.pop(key, None)
        else:
            merged[key] = value
    return merged


_SCRIPT_PARAM_KEYS = (
    "segment_target_sec",
    "max_title_length",
    "narration_target_words",
    "skip_title_optimize",
    "generate_image_prompts",
    "supplementary_info",
    "video_timeline",
)


def _migrate_flat_script_params(info: dict[str, Any]) -> None:
    """将旧版平铺在 info 顶层的 script 参数迁入 info.script。"""
    script = info.get("script")
    script_node = dict(script) if isinstance(script, dict) else {}
    migrated = False
    for key in _SCRIPT_PARAM_KEYS:
        if key in info:
            script_node.setdefault(key, info.pop(key))
            migrated = True
    if migrated or script_node:
        info["script"] = script_node


def script_params_from_info(raw: str | dict | None) -> dict[str, Any]:
    info = parse_job_info(raw)
    _migrate_flat_script_params(info)
    script = info.get("script")
    return dict(script) if isinstance(script, dict) else {}


def build_script_params(
    *,
    segment_target_sec: float | None = None,
    max_title_length: int | None = None,
    narration_target_words: int | None = None,
    skip_title_optimize: bool = False,
    generate_image_prompts: bool = False,
    supplementary_info: str | None = None,
    video_timeline: str | None = None,
) -> dict[str, Any]:
    """组装脚本生成参数（info.script 子节点内容）。"""
    params: dict[str, Any] = {
        "skip_title_optimize": skip_title_optimize,
        "generate_image_prompts": generate_image_prompts,
    }
    if segment_target_sec is not None:
        params["segment_target_sec"] = segment_target_sec
    if max_title_length is not None:
        params["max_title_length"] = max_title_length
    if narration_target_words is not None:
        params["narration_target_words"] = narration_target_words
    if supplementary_info is not None:
        stripped = supplementary_info.strip()
        params["supplementary_info"] = stripped or None
    if video_timeline is not None:
        stripped = video_timeline.strip()
        params["video_timeline"] = stripped or None
    return params


def merge_job_script_params(
    existing: str | dict | None,
    *,
    segment_target_sec: float | None = None,
    max_title_length: int | None = None,
    narration_target_words: int | None = None,
    skip_title_optimize: bool = False,
    generate_image_prompts: bool = False,
    supplementary_info: str | None = None,
    video_timeline: str | None = None,
    orientation: str | None = None,
    content_style: str | None = None,
) -> dict[str, Any]:
    """合并脚本生成参数到 info.script，并更新 job 级 orientation/content_style。"""
    merged = parse_job_info(existing)
    _migrate_flat_script_params(merged)
    script_node = dict(merged.get("script") or {})
    updates = build_script_params(
        segment_target_sec=segment_target_sec,
        max_title_length=max_title_length,
        narration_target_words=narration_target_words,
        skip_title_optimize=skip_title_optimize,
        generate_image_prompts=generate_image_prompts,
        supplementary_info=supplementary_info,
        video_timeline=video_timeline,
    )
    for key, value in updates.items():
        if value is None:
            script_node.pop(key, None)
        else:
            script_node[key] = value
    if script_node:
        merged["script"] = script_node
    else:
        merged.pop("script", None)
    if orientation is not None:
        merged["orientation"] = orientation
    if content_style is not None:
        merged["content_style"] = content_style
    return merged
