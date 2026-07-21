"""系统配置：Config 字段元数据、.env 持久化与 API 载荷。"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from app.config import ROOT_DIR, config

ConfigFieldType = Literal["string", "secret", "bool", "number", "select"]

_ENV_LINE_RE = re.compile(
    r"^(\s*)(#?\s*)([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$"
)

# env 键别名：写入时优先保留 .env 中已有键名
_ENV_ALIASES: dict[str, tuple[str, ...]] = {
    "TTS_VOICE": ("COSYVOICE_VOICE",),
    "TTS_MODEL": ("COSYVOICE_MODEL",),
    "TTS_SPEECH_RATE": ("COSYVOICE_SPEECH_RATE",),
    "TTS_VOLUME": ("COSYVOICE_VOLUME",),
}


def _f(
    attr: str,
    env_key: str,
    label: str,
    field_type: ConfigFieldType = "string",
    *,
    description: str = "",
    options: tuple[str, ...] = (),
    min_value: float | None = None,
    max_value: float | None = None,
    readonly: bool = False,
) -> "ConfigFieldDef":
    return ConfigFieldDef(
        attr=attr,
        env_key=env_key,
        label=label,
        field_type=field_type,
        description=description,
        options=options,
        min_value=min_value,
        max_value=max_value,
        readonly=readonly,
    )


@dataclass(frozen=True)
class ConfigFieldDef:
    attr: str
    env_key: str
    label: str
    field_type: ConfigFieldType = "string"
    description: str = ""
    options: tuple[str, ...] = ()
    min_value: float | None = None
    max_value: float | None = None
    readonly: bool = False


@dataclass(frozen=True)
class ConfigGroupDef:
    id: str
    label: str
    items: tuple[ConfigFieldDef, ...]


CONFIG_GROUPS: tuple[ConfigGroupDef, ...] = (
    ConfigGroupDef(
        id="server",
        label="服务器",
        items=(
            _f("env", "ENV", "运行环境", "select", options=("development", "production")),
            _f("host", "HOST", "监听地址"),
            _f("port", "PORT", "端口", "number", min_value=1, max_value=65535),
            _f("cors_origins", "CORS_ORIGINS", "跨域来源", description="逗号分隔"),
            _f("redis_url", "REDIS_URL", "Redis URL"),
            _f("enable_scheduler", "ENABLE_SCHEDULER", "定时调度", "bool"),
        ),
    ),
    ConfigGroupDef(
        id="paths",
        label="路径",
        items=(
            _f("sqlite_path", "SQLITE_PATH", "SQLite 路径"),
            _f("video_data_dir", "VIDEO_DATA_DIR", "媒体目录"),
            _f("material_data_dir", "MATERIAL_DATA_DIR", "素材目录"),
            _f("allowed_dir", "ALLOWED_DIR", "额外媒体根目录"),
            _f("log_dir", "LOG_DIR", "日志目录"),
            _f("log_retention_days", "LOG_RETENTION_DAYS", "日志保留天数", "number", min_value=1, max_value=30),
            _f("media_public_base_url", "MEDIA_PUBLIC_BASE_URL", "媒体公网基址"),
            _f("res_dir", "RES_DIR", "资源根目录"),
            _f("font_path", "FONT_PATH", "字体路径"),
            _f("intro_bg_path", "INTRO_BG_PATH", "片头背景"),
            _f("host_intro_path", "HOST_INTRO_PATH", "讲解人片头"),
            _f("host_intro_crayon_path", "HOST_INTRO_CRAYON_PATH", "讲解人片头(crayon)"),
            _f("host_boy_path", "HOST_BOY_PATH", "讲解人男孩"),
            _f("host_girl_path", "HOST_GIRL_PATH", "讲解人女孩"),
            _f("intro_moon_path", "INTRO_MOON_PATH", "片头月亮"),
            _f("intro_sun_crayon_path", "INTRO_SUN_CRAYON_PATH", "片头太阳(crayon)"),
            _f("intro_crayon_bg_path", "INTRO_CRAYON_BG_PATH", "片头背景(crayon)"),
            _f("intro_shout_path", "INTRO_SHOUT_PATH", "片头喊声"),
            _f("intro_shout_daily_path", "INTRO_SHOUT_DAILY_PATH", "片头喊声(chat)"),
        ),
    ),
    ConfigGroupDef(
        id="runtime",
        label="运行模式",
        items=(
            _f(
                "mock_mode",
                "MOCK_MODE",
                "Mock 模式",
                "bool",
                description="仅显式 true 才 mock；缺 Key 不会自动开启",
            ),
            _f("skip_publish_default", "SKIP_PUBLISH_DEFAULT", "默认跳过投稿", "bool"),
            _f("skip_script_quality_check", "SKIP_SCRIPT_QUALITY_CHECK", "跳过脚本质检", "bool"),
            _f("host_enabled", "HOST_ENABLED", "讲解人 IP", "bool"),
            _f("kling_upgrade_enabled", "KLING_UPGRADE_ENABLED", "可灵升级", "bool"),
            _f("script_qa_max_attempts", "SCRIPT_QA_MAX_ATTEMPTS", "质检重试次数", "number", min_value=1, max_value=5),
            _f("brand_name", "BRAND_NAME", "品牌名"),
            _f("max_title_length", "MAX_TITLE_LENGTH", "标题最大字数", "number", min_value=8, max_value=40),
            _f("segment_target_sec", "SEGMENT_TARGET_SEC", "单镜口播上限 (秒)", "number", min_value=0, max_value=60),
            _f("final_min_duration_sec", "FINAL_MIN_DURATION_SEC", "成片最短 (秒)", "number", min_value=10, max_value=300),
            _f("final_max_duration_sec", "FINAL_MAX_DURATION_SEC", "成片最长 (秒)", "number", min_value=60, max_value=1800),
        ),
    ),
    ConfigGroupDef(
        id="video",
        label="视频 / FFmpeg",
        items=(
            _f("video_width", "VIDEO_WIDTH", "成片宽度", "number", min_value=360, max_value=3840),
            _f("video_height", "VIDEO_HEIGHT", "成片高度", "number", min_value=360, max_value=3840),
            _f("cover_width", "COVER_WIDTH", "封面宽度", "number", min_value=360, max_value=3840),
            _f("cover_height", "COVER_HEIGHT", "封面高度", "number", min_value=360, max_value=3840),
            _f("motion_preset", "MOTION_PRESET", "Ken Burns 预设"),
            _f("ffmpeg_preset", "FFMPEG_PRESET", "编码 preset"),
            _f("ffmpeg_crf", "FFMPEG_CRF", "CRF", "number", min_value=0, max_value=51),
            _f("ffmpeg_subtitle_crf", "FFMPEG_SUBTITLE_CRF", "字幕 CRF", "number", min_value=0, max_value=51),
            _f("ffmpeg_hwaccel", "FFMPEG_HWACCEL", "硬件加速"),
            _f("ffmpeg_vaapi_device", "FFMPEG_VAAPI_DEVICE", "VAAPI 设备"),
            _f("ffmpeg_vaapi_codec", "FFMPEG_VAAPI_CODEC", "VAAPI 编码器"),
            _f(
                        "clip_provider",
                        "CLIP_PROVIDER",
                        "动效提供商",
                        "select",
                        options=("ffmpeg", "wan_i2v", "agnes_i2v"),
                    ),
            _f("wan_i2v_model", "WAN_I2V_MODEL", "万相 I2V 模型"),
            _f("wan_i2v_resolution", "WAN_I2V_RESOLUTION", "万相 I2V 分辨率"),
            _f("wan_i2v_prompt_extend", "WAN_I2V_PROMPT_EXTEND", "万相 I2V 扩写", "bool"),
            _f("clip_submit_interval_sec", "CLIP_SUBMIT_INTERVAL_SEC", "I2V 提交间隔 (秒)", "number", min_value=0, max_value=60),
            _f("video_max_workers", "VIDEO_MAX_WORKERS", "I2V 并发数", "number", min_value=1, max_value=8),
            _f("agnes_submit_interval_sec", "AGNES_SUBMIT_INTERVAL_SEC", "Agnes 提交间隔 (秒)", "number", min_value=0, max_value=120),
            _f("dashscope_http_max_retries", "DASHSCOPE_HTTP_MAX_RETRIES", "百炼 HTTP 重试", "number", min_value=0, max_value=10),
            _f("wan_i2v_task_max_retries", "WAN_I2V_TASK_MAX_RETRIES", "I2V 任务重试", "number", min_value=0, max_value=5),
            _f("wan_i2v_poll_max_attempts", "WAN_I2V_POLL_MAX_ATTEMPTS", "I2V 轮询上限", "number", min_value=10, max_value=300),
            _f("wan_t2i_poll_max_attempts", "WAN_T2I_POLL_MAX_ATTEMPTS", "T2I 轮询上限", "number", min_value=10, max_value=300),
            _f("agnes_video_model", "AGNES_VIDEO_MODEL", "视频模型"),
            _f("agnes_video_width", "AGNES_VIDEO_WIDTH", "视频宽度", "number", min_value=360, max_value=3840),
            _f("agnes_video_height", "AGNES_VIDEO_HEIGHT", "视频高度", "number", min_value=360, max_value=3840),
            _f("agnes_video_frame_rate", "AGNES_VIDEO_FRAME_RATE", "帧率", "number", min_value=12, max_value=60),
            _f("agnes_video_poll_interval_sec", "AGNES_VIDEO_POLL_INTERVAL_SEC", "轮询间隔 (秒)", "number", min_value=1, max_value=60),
            _f("agnes_video_poll_max_attempts", "AGNES_VIDEO_POLL_MAX_ATTEMPTS", "轮询上限", "number", min_value=10, max_value=300),
            _f("agnes_video_task_max_retries", "AGNES_VIDEO_TASK_MAX_RETRIES", "任务重试", "number", min_value=0, max_value=5),
            _f("agnes_video_submit_max_retries", "AGNES_VIDEO_SUBMIT_MAX_RETRIES", "提交重试", "number", min_value=0, max_value=5),
            _f("agnes_video_download_timeout_sec", "AGNES_VIDEO_DOWNLOAD_TIMEOUT_SEC", "下载超时 (秒)", "number", min_value=30, max_value=1800),
        ),
    ),
    ConfigGroupDef(
        id="image",
        label="图像生成",
        items=(
            _f(
                        "image_provider",
                        "IMAGE_PROVIDER",
                        "图像提供商",
                        "select",
                        options=("agnes_t2i", "wan_t2i", "z_image_t2i", "sd15_t2i"),
                    ),
            _f("image_max_workers", "IMAGE_MAX_WORKERS", "并发数", "number", min_value=1, max_value=8),
            _f("image_submit_interval_sec", "IMAGE_SUBMIT_INTERVAL_SEC", "提交间隔 (秒)", "number", min_value=0, max_value=120),
            _f("agnes_api_key", "AGNES_API_KEY", "付费 Key", "secret"),
            _f("agnes_free_api_key", "AGNES_FREE_API_KEY", "免费 Key（备用）", "secret"),
            _f("agnes_api_base_url", "AGNES_API_BASE_URL", "API 地址"),
            _f("agnes_image_model", "AGNES_IMAGE_MODEL", "图像模型"),
            _f("agnes_image_size", "AGNES_IMAGE_SIZE", "出图尺寸"),
            _f("agnes_http_max_retries", "AGNES_HTTP_MAX_RETRIES", "HTTP 重试", "number", min_value=0, max_value=10),
            _f("agnes_http_connect_timeout_sec", "AGNES_HTTP_CONNECT_TIMEOUT_SEC", "连接超时 (秒)", "number", min_value=5, max_value=120),
            _f("agnes_http_submit_read_timeout_sec", "AGNES_HTTP_SUBMIT_READ_TIMEOUT_SEC", "提交读超时 (秒)", "number", min_value=10, max_value=600),
            _f("agnes_http_poll_read_timeout_sec", "AGNES_HTTP_POLL_READ_TIMEOUT_SEC", "轮询读超时 (秒)", "number", min_value=5, max_value=300),
            _f("wan_model", "WAN_MODEL", "文生图模型"),
            _f("wan_image_size", "WAN_IMAGE_SIZE", "出图尺寸"),
            _f("wan_cover_size", "WAN_COVER_SIZE", "封面尺寸"),
            _f("wan_prompt_extend", "WAN_PROMPT_EXTEND", "提示词扩写", "bool"),
            _f("z_image_model", "Z_IMAGE_MODEL", "模型"),
            _f("z_image_size", "Z_IMAGE_SIZE", "出图尺寸"),
            _f("z_image_prompt_extend", "Z_IMAGE_PROMPT_EXTEND", "提示词扩写", "bool"),
            _f("sd_api_url", "SD_API_URL", "WebUI 地址"),
            _f("sd_business", "SD_BUSINESS", "业务线"),
            _f("sd_image_size", "SD_IMAGE_SIZE", "出图尺寸"),
            _f("sd_timeout_sec", "SD_TIMEOUT_SEC", "超时 (秒)", "number", min_value=30, max_value=3600),
        ),
    ),
    ConfigGroupDef(
        id="llm",
        label="LLM",
        items=(
            _f("llm_provider", "LLM_PROVIDER", "提供商", "select", options=("deepseek", "agnes")),
            _f("llm_image_prompt_batch_size", "LLM_IMAGE_PROMPT_BATCH_SIZE", "文生图提示词批大小", "number", min_value=1, max_value=20),
            _f("deepseek_api_key", "DEEPSEEK_API_KEY", "API Key", "secret"),
            _f("deepseek_base_url", "DEEPSEEK_BASE_URL", "API 地址"),
            _f("deepseek_model", "DEEPSEEK_MODEL", "模型"),
            _f("deepseek_max_tokens", "DEEPSEEK_MAX_TOKENS", "最大 Token", "number", min_value=1024, max_value=65536),
            _f("deepseek_thinking_enabled", "DEEPSEEK_THINKING", "思考模式", "bool"),
            _f("agnes_llm_model", "AGNES_LLM_MODEL", "模型"),
            _f("agnes_llm_max_tokens", "AGNES_LLM_MAX_TOKENS", "最大 Token", "number", min_value=1024, max_value=65536),
        ),
    ),
    ConfigGroupDef(
        id="tts",
        label="TTS",
        items=(
            _f("dashscope_api_key", "DASHSCOPE_API_KEY", "百炼 API Key", "secret"),
            _f("tts_api_key", "TTS_API_KEY", "TTS 专用 Key", "secret", description="未设则使用百炼 Key"),
            _f("tts_base_url", "TTS_BASE_URL", "TTS Base URL"),
            _f("dashscope_ws_uri", "DASHSCOPE_WS_URI", "WebSocket URI"),
            _f("tts_voice", "TTS_VOICE", "音色 ID"),
            _f("tts_model", "TTS_MODEL", "模型"),
            _f("tts_speech_rate", "TTS_SPEECH_RATE", "语速", "number", min_value=0.5, max_value=2.0),
            _f("tts_volume", "TTS_VOLUME", "音量", "number", min_value=0, max_value=100),
            _f("tts_instruction", "TTS_INSTRUCTION", "Instruct 文本"),
            _f("tts_instruct_preset", "TTS_INSTRUCT_PRESET", "Instruct 预设"),
            _f("tts_max_workers", "TTS_MAX_WORKERS", "并发数", "number", min_value=1, max_value=10),
            _f("tts_trim_edges", "TTS_TRIM_EDGES", "气口裁切", "bool"),
            _f("tts_audio_format", "TTS_AUDIO_FORMAT", "音频格式"),
        ),
    ),
    ConfigGroupDef(
        id="audio",
        label="音频",
        items=(
            _f("audio_target_lufs", "AUDIO_TARGET_LUFS", "目标 LUFS", "number", min_value=-30, max_value=0),
            _f("audio_true_peak", "AUDIO_TRUE_PEAK", "真峰值 dBTP", "number", min_value=-10, max_value=0),
            _f("audio_silence_noise_db", "AUDIO_SILENCE_NOISE_DB", "静音噪声阈值", "number", min_value=-60, max_value=-20),
            _f("audio_max_silence_gap_sec", "AUDIO_MAX_SILENCE_GAP_SEC", "最大静音间隔 (秒)", "number", min_value=0, max_value=5),
            _f("audio_max_edge_silence_sec", "AUDIO_MAX_EDGE_SILENCE_SEC", "边缘静音上限 (秒)", "number", min_value=0, max_value=3),
            _f("tts_cue_duration_tolerance_sec", "TTS_CUE_DURATION_TOLERANCE_SEC", "时长容差 (秒)", "number", min_value=0, max_value=3),
            _f("audio_loudness_tolerance_lu", "AUDIO_LOUDNESS_TOLERANCE_LU", "响度容差 LU", "number", min_value=0, max_value=10),
            _f("intro_moon_tint", "INTRO_MOON_TINT", "月亮色调"),
            _f("intro_tts_rate", "INTRO_TTS_RATE", "片头语速", "number", min_value=0.5, max_value=2.0),
            _f("intro_tts_pitch", "INTRO_TTS_PITCH", "片头音调", "number", min_value=0.5, max_value=2.0),
        ),
    ),
    ConfigGroupDef(
        id="clips",
        label="素材片段搜索",
        items=(
            _f("pexels_api_key", "PEXELS_API_KEY", "Pexels Key", "secret"),
            _f("pixabay_api_key", "PIXABAY_API_KEY", "Pixabay Key", "secret"),
            _f("clip_search_timeout_sec", "CLIP_SEARCH_TIMEOUT_SEC", "搜索超时 (秒)", "number", min_value=3, max_value=60),
        ),
    ),
)
_FIELD_BY_ATTR: dict[str, ConfigFieldDef] = {
    field.attr: field for group in CONFIG_GROUPS for field in group.items
}


def env_file_path() -> Path:
    return ROOT_DIR / ".env"


def _env_keys_for(env_key: str) -> list[str]:
    return [env_key, *list(_ENV_ALIASES.get(env_key, ()))]


def _resolve_env_key(env_key: str, file_keys: set[str]) -> str:
    for key in _env_keys_for(env_key):
        if key in file_keys:
            return key
    return env_key


def _format_env_value(value: str) -> str:
    if not value:
        return ""
    if re.search(r"[\s#\"'\\]", value):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return value


def _unquote_env_value(raw: str) -> str:
    value = raw.strip()
    if not value:
        return ""
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        inner = value[1:-1]
        if value.startswith('"'):
            return inner.replace('\\"', '"').replace("\\\\", "\\")
        return inner
    return value


def parse_env_file(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = _ENV_LINE_RE.match(line)
        if not match:
            continue
        if match.group(2).strip().startswith("#"):
            continue
        key = match.group(3)
        values[key] = _unquote_env_value(match.group(4))
    return values


def write_env_updates(updates: dict[str, str], *, env_path: Path | None = None) -> list[str]:
    """按 env 键名写入 .env，返回已更新键列表。"""
    path = env_path or env_file_path()
    existing = parse_env_file(path) if path.is_file() else {}
    file_keys = set(existing)
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True) if path.is_file() else []

    updated: list[str] = []
    pending = dict(updates)
    new_lines: list[str] = []

    alias_to_canonical: dict[str, str] = {}
    for canonical, aliases in _ENV_ALIASES.items():
        for alias in aliases:
            alias_to_canonical[alias] = canonical

    for line in lines:
        match = _ENV_LINE_RE.match(line.rstrip("\n"))
        if not match:
            new_lines.append(line)
            continue

        key = match.group(3)
        canonical = alias_to_canonical.get(key, key)
        if canonical in pending:
            value = pending.pop(canonical)
            env_key = _resolve_env_key(canonical, file_keys | {key})
            prefix = match.group(1)
            new_lines.append(f"{prefix}{env_key}={_format_env_value(value)}\n")
            updated.append(canonical)
            continue

        new_lines.append(line)

    for canonical, value in pending.items():
        env_key = _resolve_env_key(canonical, file_keys)
        if new_lines and not new_lines[-1].endswith("\n"):
            new_lines.append("\n")
        elif not new_lines:
            pass
        else:
            new_lines.append("\n")
        new_lines.append(f"{env_key}={_format_env_value(value)}\n")
        updated.append(canonical)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(new_lines), encoding="utf-8")
    return updated


def _serialize_runtime_value(value: Any, field: ConfigFieldDef) -> Any:
    if field.field_type == "bool":
        return bool(value)
    if value is None:
        return ""
    if isinstance(value, Path):
        return str(value)
    if field.field_type == "number":
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value) if value.is_integer() else value
    return value


def mask_secret(value: str, *, visible_tail: int = 4) -> str:
    """脱敏密钥：保留末尾若干字符，其余用 • 替代。

    空字符串返回空；过短则全部掩码。
    """
    text = value or ""
    if not text:
        return ""
    if len(text) <= visible_tail:
        return "•" * len(text)
    return ("•" * (len(text) - visible_tail)) + text[-visible_tail:]


def _validate_field(field: ConfigFieldDef, raw: Any) -> str:
    if field.readonly:
        raise ValueError(f"{field.attr} is readonly")

    if field.field_type == "bool":
        if isinstance(raw, bool):
            return "true" if raw else "false"
        text = str(raw).strip().lower()
        if text in {"1", "true", "yes", "on", "0", "false", "no", "off"}:
            return "true" if text in {"1", "true", "yes", "on"} else "false"
        raise ValueError(f"{field.attr} must be boolean")

    text = str(raw).strip()
    if field.field_type == "number":
        try:
            number = float(text)
        except ValueError as exc:
            raise ValueError(f"{field.attr} must be number") from exc
        if field.min_value is not None and number < field.min_value:
            raise ValueError(f"{field.attr} must be >= {field.min_value}")
        if field.max_value is not None and number > field.max_value:
            raise ValueError(f"{field.attr} must be <= {field.max_value}")
        if number.is_integer():
            return str(int(number))
        return str(number)

    if field.field_type == "select" and field.options and text not in field.options:
        raise ValueError(f"{field.attr} must be one of: {', '.join(field.options)}")

    return text


def _field_payload(field: ConfigFieldDef) -> dict[str, Any]:
    runtime = getattr(config, field.attr)
    file_values = parse_env_file(env_file_path())
    env_key = _resolve_env_key(field.env_key, set(file_values))
    raw_value = _serialize_runtime_value(runtime, field)
    if field.field_type == "secret":
        text = "" if raw_value is None else str(raw_value)
        return {
            "attr": field.attr,
            "env_key": env_key,
            "label": field.label,
            "type": field.field_type,
            "value": mask_secret(text),
            "configured": bool(text.strip()),
            "description": field.description,
            "options": list(field.options),
            "min": field.min_value,
            "max": field.max_value,
            "readonly": field.readonly,
        }
    return {
        "attr": field.attr,
        "env_key": env_key,
        "label": field.label,
        "type": field.field_type,
        "value": raw_value,
        "configured": None,
        "description": field.description,
        "options": list(field.options),
        "min": field.min_value,
        "max": field.max_value,
        "readonly": field.readonly,
    }


def get_config_payload() -> dict[str, Any]:
    return {
        "env_path": str(env_file_path()),
        "groups": [
            {
                "id": group.id,
                "label": group.label,
                "items": [_field_payload(item) for item in group.items],
            }
            for group in CONFIG_GROUPS
        ],
    }


def apply_config_updates(raw_updates: dict[str, Any]) -> dict[str, Any]:
    if not raw_updates:
        raise ValueError("updates is required")

    env_updates: dict[str, str] = {}
    updated_attrs: list[str] = []
    skipped_attrs: list[str] = []

    for attr, raw in raw_updates.items():
        field = _FIELD_BY_ATTR.get(attr)
        if field is None:
            raise ValueError(f"unknown config attr: {attr}")
        if field.readonly:
            raise ValueError(f"{attr} is readonly")

        # 前端若未改密钥，可能把脱敏后的 value 原样提交；跳过以免写坏 .env
        if field.field_type == "secret":
            current = _serialize_runtime_value(getattr(config, field.attr), field)
            current_text = "" if current is None else str(current)
            incoming = "" if raw is None else str(raw)
            if incoming == mask_secret(current_text):
                skipped_attrs.append(attr)
                continue

        env_updates[field.env_key] = _validate_field(field, raw)
        updated_attrs.append(attr)

    if not env_updates:
        return {
            "updated": [],
            "env_keys": [],
            "skipped": skipped_attrs,
            "count": 0,
        }

    updated_env_keys = write_env_updates(env_updates)
    for env_key, value in env_updates.items():
        resolved = _resolve_env_key(env_key, set(parse_env_file(env_file_path())))
        os.environ[resolved] = value

    config.reload()
    return {
        "updated": updated_attrs,
        "env_keys": updated_env_keys,
        "skipped": skipped_attrs,
        "count": len(updated_attrs),
    }
