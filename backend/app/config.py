"""统一配置：环境变量、路径、服务参数。"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = Path(__file__).resolve().parents[1]
load_dotenv(ROOT_DIR / ".env")


def _bool(key: str, default: bool = False) -> bool:
    val = os.getenv(key)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


def _opt(key: str) -> str | None:
    return os.getenv(key) or None


def _first(*keys: str, default: str = "") -> str:
    for key in keys:
        val = os.getenv(key)
        if val:
            return val
    return default


def _path(key: str, default: Path, *, root: Path = ROOT_DIR) -> Path:
    val = Path(os.getenv(key, str(default)))
    return val if val.is_absolute() else (root / val).resolve()


def _parse_size(value: str) -> tuple[int, int]:
    normalized = value.strip().lower().replace("x", "*")
    width, height = normalized.split("*", 1)
    return int(width.strip()), int(height.strip())


def _size(prefix: str, default_w: int, default_h: int) -> tuple[int, int]:
    combined = os.getenv(f"{prefix}_SIZE")
    if combined:
        return _parse_size(combined)
    return int(os.getenv(f"{prefix}_WIDTH", str(default_w))), int(
        os.getenv(f"{prefix}_HEIGHT", str(default_h))
    )


def _size_str(width: int, height: int) -> str:
    return f"{width}*{height}"


_RES_DIR = _path("RES_DIR", BACKEND_DIR / "res")
_VIDEO_W, _VIDEO_H = _size("VIDEO", 1080, 1920)
_COVER_W, _COVER_H = _size("COVER", 1280, 720)
_WAN_IMAGE_SIZE = os.getenv("WAN_IMAGE_SIZE", "720*1280")
_DEEPSEEK_KEY = _opt("DEEPSEEK_API_KEY")
_DASHSCOPE_KEY = _opt("DASHSCOPE_API_KEY")
_TTS_KEY = _DASHSCOPE_KEY or _opt("TTS_API_KEY")
_FINAL_STRICT = _bool("FINAL_DURATION_STRICT")
_FFMPEG_CRF = int(os.getenv("FFMPEG_CRF", "20"))
_FFMPEG_SUBTITLE_CRF_RAW = os.getenv("FFMPEG_SUBTITLE_CRF")


class Config:
    """应用配置。"""

    # ========== 服务器 ==========
    env: str = os.getenv("ENV", "development").strip().lower()
    is_production: bool = env == "production"
    host: str = os.getenv("HOST", "0.0.0.0")
    port: int = int(os.getenv("PORT", "9002"))
    cors_origins: str = os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5175,http://127.0.0.1:5175",
    )

    # ========== 路径 ==========
    root_dir: Path = ROOT_DIR
    res_dir: Path = _RES_DIR
    font_path: Path = _path("FONT_PATH", _RES_DIR / "font/SourceHanSansCN-Medium.otf")
    intro_bg_path: Path = _path("INTRO_BG_PATH", _RES_DIR / "bg/bg1.png")
    sqlite_path: Path = _path("SQLITE_PATH", ROOT_DIR / "data/data.db")
    video_data_dir: Path = _path("VIDEO_DATA_DIR", ROOT_DIR / "data/media")
    material_data_dir: Path = _path("MATERIAL_DATA_DIR", ROOT_DIR / "data/materials")
    allowed_dir: str = os.getenv("ALLOWED_DIR", "/mnt").strip()
    log_dir: Path = _path("LOG_DIR", ROOT_DIR / "logs")
    log_retention_days: int = int(os.getenv("LOG_RETENTION_DAYS", "3"))
    host_intro_path: Path = _path("HOST_INTRO_PATH", _RES_DIR / "host/intro.png")
    host_boy_path: Path = _path("HOST_BOY_PATH", _RES_DIR / "host/boy.png")
    host_girl_path: Path = _path("HOST_GIRL_PATH", _RES_DIR / "host/girl.png")
    intro_moon_path: Path = _path("INTRO_MOON_PATH", _RES_DIR / "host/moon.png")
    intro_shout_path: Path = _path("INTRO_SHOUT_PATH", _RES_DIR / "audio/intro_shout.mp3")

    # ========== 运行模式 ==========
    redis_url: str | None = _opt("REDIS_URL")
    mock_mode: bool = _bool("MOCK_MODE") or not (_DEEPSEEK_KEY and _DASHSCOPE_KEY and _TTS_KEY)
    skip_publish_default: bool = _bool("SKIP_PUBLISH_DEFAULT", True)
    host_enabled: bool = _bool("HOST_ENABLED")
    kling_upgrade_enabled: bool = _bool("KLING_UPGRADE_ENABLED")
    enable_scheduler: bool = _bool("ENABLE_SCHEDULER")
    brand_name: str = os.getenv("BRAND_NAME", "昭墨百科")

    # ========== 视频 / 封面尺寸 ==========
    video_width: int = _VIDEO_W
    video_height: int = _VIDEO_H
    cover_width: int = _COVER_W
    cover_height: int = _COVER_H
    motion_preset: str = os.getenv("MOTION_PRESET", "ken_burns_slow")
    clip_provider: str = os.getenv("CLIP_PROVIDER", "ffmpeg")
    # FFmpeg 编码：preset 越快体积略增；CRF 越大越快、画质略降
    ffmpeg_preset: str = os.getenv("FFMPEG_PRESET", "veryfast")
    ffmpeg_crf: int = _FFMPEG_CRF
    ffmpeg_subtitle_crf: int = (
        int(_FFMPEG_SUBTITLE_CRF_RAW) if _FFMPEG_SUBTITLE_CRF_RAW else _FFMPEG_CRF
    )
    clip_submit_interval_sec: float = float(
        os.getenv("CLIP_SUBMIT_INTERVAL_SEC", os.getenv("IMAGE_SUBMIT_INTERVAL_SEC", "3"))
    )
    wan_i2v_model: str = os.getenv("WAN_I2V_MODEL", "wanx2.1-i2v-turbo")  # cSpell: disable-line
    wan_i2v_resolution: str = os.getenv("WAN_I2V_RESOLUTION", "720P")
    wan_i2v_prompt_extend: bool = _bool("WAN_I2V_PROMPT_EXTEND", True)
    dashscope_http_max_retries: int = int(os.getenv("DASHSCOPE_HTTP_MAX_RETRIES", "2"))
    wan_i2v_task_max_retries: int = int(os.getenv("WAN_I2V_TASK_MAX_RETRIES", "1"))
    wan_i2v_poll_max_attempts: int = int(os.getenv("WAN_I2V_POLL_MAX_ATTEMPTS", "60"))
    wan_t2i_poll_max_attempts: int = int(os.getenv("WAN_T2I_POLL_MAX_ATTEMPTS", "45"))
    max_title_length: int = int(os.getenv("MAX_TITLE_LENGTH", "24"))
    segment_target_sec: float = float(os.getenv("SEGMENT_TARGET_SEC", "12"))
    final_min_duration_sec: float = float(
        os.getenv("FINAL_MIN_DURATION_SEC", str(260 if _FINAL_STRICT else 30))
    )
    final_max_duration_sec: float = float(
        os.getenv("FINAL_MAX_DURATION_SEC", str(320 if _FINAL_STRICT else 900))
    )

    # ========== 图像生成 ==========
    image_provider: str = os.getenv("IMAGE_PROVIDER", "z_image_t2i")
    image_max_workers: int = int(os.getenv("IMAGE_MAX_WORKERS", "1"))
    image_submit_interval_sec: float = float(os.getenv("IMAGE_SUBMIT_INTERVAL_SEC", "3"))
    wan_model: str = os.getenv("WAN_MODEL", "wanx2.1-t2i-turbo")  # cSpell: disable-line
    wan_image_size: str = _WAN_IMAGE_SIZE
    wan_cover_size: str = os.getenv("WAN_COVER_SIZE", _size_str(_COVER_W, _COVER_H))
    wan_prompt_extend: bool = _bool("WAN_PROMPT_EXTEND")
    z_image_model: str = os.getenv("Z_IMAGE_MODEL", "z-image-turbo")
    z_image_size: str = os.getenv("Z_IMAGE_SIZE", _WAN_IMAGE_SIZE)
    z_image_prompt_extend: bool = _bool("Z_IMAGE_PROMPT_EXTEND")

    # ========== LLM ==========
    deepseek_api_key: str | None = _DEEPSEEK_KEY
    deepseek_base_url: str = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    deepseek_model: str = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

    # ========== TTS / CosyVoice ==========
    dashscope_api_key: str | None = _DASHSCOPE_KEY
    tts_api_key: str | None = _TTS_KEY
    tts_base_url: str | None = _opt("TTS_BASE_URL")
    dashscope_ws_uri: str = os.getenv(
        "DASHSCOPE_WS_URI",
        "wss://dashscope.aliyuncs.com/api-ws/v1/inference/",  # cSpell: disable-line
    )
    tts_voice: str = _first("TTS_VOICE", "COSYVOICE_VOICE", default="longwan_v3")  # cSpell: disable-line
    tts_model: str | None = _first("TTS_MODEL", "COSYVOICE_MODEL") or None
    tts_speech_rate: float = float(
        _first("TTS_SPEECH_RATE", "COSYVOICE_SPEECH_RATE", default="1.0")
    )
    tts_volume: int = int(_first("TTS_VOLUME", "COSYVOICE_VOLUME", default="50"))
    tts_instruction: str | None = _opt("TTS_INSTRUCTION")
    tts_instruct_preset: str | None = _opt("TTS_INSTRUCT_PRESET")

    # ========== 音频质检 / 归一化 ==========
    audio_target_lufs: float = float(os.getenv("AUDIO_TARGET_LUFS", "-16"))
    audio_true_peak: float = float(os.getenv("AUDIO_TRUE_PEAK", "-1.5"))
    audio_silence_noise_db: float = float(os.getenv("AUDIO_SILENCE_NOISE_DB", "-40"))
    audio_max_silence_gap_sec: float = float(os.getenv("AUDIO_MAX_SILENCE_GAP_SEC", "1.5"))
    audio_max_edge_silence_sec: float = float(os.getenv("AUDIO_MAX_EDGE_SILENCE_SEC", "0.8"))
    tts_cue_duration_tolerance_sec: float = float(
        os.getenv("TTS_CUE_DURATION_TOLERANCE_SEC", "0.8")
    )
    audio_loudness_tolerance_lu: float = float(os.getenv("AUDIO_LOUDNESS_TOLERANCE_LU", "2.5"))

    # ========== 片头 ==========
    intro_moon_tint: str = os.getenv("INTRO_MOON_TINT", "natural").strip().lower()
    intro_tts_rate: float = float(os.getenv("INTRO_TTS_RATE", "1.25"))
    intro_tts_pitch: float = float(os.getenv("INTRO_TTS_PITCH", "1.15"))

    # ========== B 站投稿 ==========
    bili_client_id: str | None = _opt("BILI_CLIENT_ID")
    bili_client_secret: str | None = _opt("BILI_CLIENT_SECRET")
    bili_access_token: str | None = _opt("BILI_ACCESS_TOKEN")

    def video_size(self) -> str:
        return _size_str(self.video_width, self.video_height)

    def cover_size(self) -> str:
        return _size_str(self.cover_width, self.cover_height)

    def get_cors_origins(self) -> list[str]:
        if self.cors_origins.strip() == "*":
            return ["*"]
        return [origin.strip() for origin in self.cors_origins.split(",")]


config = Config()
Settings = Config  # 兼容旧类型名


def get_settings() -> Config:
    return config
