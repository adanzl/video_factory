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


_DEFAULT_TTS_VOICE = "cosyvoice-v3.5-flash-leo-60621bdce780434ab0734555e5196d7d"  # cSpell: disable-line


class Config:
    """应用配置。"""

    def __init__(self) -> None:
        self.reload()

    def reload(self) -> None:
        load_dotenv(ROOT_DIR / ".env", override=True)

        res_dir = _path("RES_DIR", BACKEND_DIR / "res")
        video_w, video_h = _size("VIDEO", 1080, 1920)
        cover_w, cover_h = _size("COVER", 1280, 720)
        wan_image_size = os.getenv("WAN_IMAGE_SIZE", "720*1280")
        deepseek_key = _opt("DEEPSEEK_API_KEY")
        dashscope_key = _opt("DASHSCOPE_API_KEY")
        tts_key = dashscope_key or _opt("TTS_API_KEY")
        final_strict = _bool("FINAL_DURATION_STRICT")
        ffmpeg_crf = int(os.getenv("FFMPEG_CRF", "20"))
        ffmpeg_subtitle_crf_raw = os.getenv("FFMPEG_SUBTITLE_CRF")

        self.env: str = os.getenv("ENV", "development").strip().lower()
        self.is_production: bool = self.env == "production"
        self.host: str = os.getenv("HOST", "0.0.0.0")
        self.port: int = int(os.getenv("PORT", "9002"))
        self.cors_origins: str = os.getenv(
            "CORS_ORIGINS",
            "http://localhost:5175,http://127.0.0.1:5175",
        )

        self.root_dir: Path = ROOT_DIR
        self.res_dir: Path = res_dir
        self.font_path: Path = _path("FONT_PATH", res_dir / "font/SourceHanSansCN-Medium.otf")
        self.intro_bg_path: Path = _path("INTRO_BG_PATH", res_dir / "bg/bg1.png")
        self.sqlite_path: Path = _path("SQLITE_PATH", ROOT_DIR / "data/data.db")
        self.video_data_dir: Path = _path("VIDEO_DATA_DIR", ROOT_DIR / "data/media")
        self.material_data_dir: Path = _path("MATERIAL_DATA_DIR", ROOT_DIR / "data/materials")
        self.allowed_dir: str = os.getenv("ALLOWED_DIR", "/mnt").strip()
        self.log_dir: Path = _path("LOG_DIR", ROOT_DIR / "logs")
        self.log_retention_days: int = int(os.getenv("LOG_RETENTION_DAYS", "3"))
        self.host_intro_path: Path = _path("HOST_INTRO_PATH", res_dir / "host/intro.png")
        self.host_boy_path: Path = _path("HOST_BOY_PATH", res_dir / "host/boy.png")
        self.host_girl_path: Path = _path("HOST_GIRL_PATH", res_dir / "host/girl.png")
        self.intro_moon_path: Path = _path("INTRO_MOON_PATH", res_dir / "host/moon.png")
        self.intro_shout_path: Path = _path("INTRO_SHOUT_PATH", res_dir / "audio/intro_shout.mp3")

        self.redis_url: str | None = _opt("REDIS_URL")
        self.mock_mode: bool = _bool("MOCK_MODE") or not (
            deepseek_key and dashscope_key and tts_key
        )
        self.skip_publish_default: bool = _bool("SKIP_PUBLISH_DEFAULT", True)
        self.skip_script_quality_check: bool = _bool("SKIP_SCRIPT_QUALITY_CHECK", False)
        self.script_qa_max_attempts: int = int(os.getenv("SCRIPT_QA_MAX_ATTEMPTS", "2"))
        self.host_enabled: bool = _bool("HOST_ENABLED")
        self.kling_upgrade_enabled: bool = _bool("KLING_UPGRADE_ENABLED")
        self.enable_scheduler: bool = _bool("ENABLE_SCHEDULER")
        self.brand_name: str = os.getenv("BRAND_NAME", "昭墨百科")

        self.video_width: int = video_w
        self.video_height: int = video_h
        self.cover_width: int = cover_w
        self.cover_height: int = cover_h
        self.motion_preset: str = os.getenv("MOTION_PRESET", "ken_burns_slow")
        self.clip_provider: str = os.getenv("CLIP_PROVIDER", "ffmpeg")
        self.ffmpeg_preset: str = os.getenv("FFMPEG_PRESET", "veryfast")
        self.ffmpeg_crf: int = ffmpeg_crf
        self.ffmpeg_subtitle_crf: int = (
            int(ffmpeg_subtitle_crf_raw) if ffmpeg_subtitle_crf_raw else ffmpeg_crf
        )
        self.ffmpeg_hwaccel: str = os.getenv("FFMPEG_HWACCEL", "none").strip().lower()
        self.ffmpeg_vaapi_device: str = os.getenv("FFMPEG_VAAPI_DEVICE", "/dev/dri/renderD128")
        self.ffmpeg_vaapi_codec: str = os.getenv("FFMPEG_VAAPI_CODEC", "h264_vaapi")
        self.clip_submit_interval_sec: float = float(
            os.getenv("CLIP_SUBMIT_INTERVAL_SEC", os.getenv("IMAGE_SUBMIT_INTERVAL_SEC", "3"))
        )
        self.agnes_submit_interval_sec: float = float(os.getenv("AGNES_SUBMIT_INTERVAL_SEC", "12"))
        self.wan_i2v_model: str = os.getenv("WAN_I2V_MODEL", "wanx2.1-i2v-turbo")  # cSpell: disable-line
        self.wan_i2v_resolution: str = os.getenv("WAN_I2V_RESOLUTION", "720P")
        self.wan_i2v_prompt_extend: bool = _bool("WAN_I2V_PROMPT_EXTEND", True)
        self.dashscope_http_max_retries: int = int(os.getenv("DASHSCOPE_HTTP_MAX_RETRIES", "2"))
        self.wan_i2v_task_max_retries: int = int(os.getenv("WAN_I2V_TASK_MAX_RETRIES", "1"))
        self.wan_i2v_poll_max_attempts: int = int(os.getenv("WAN_I2V_POLL_MAX_ATTEMPTS", "60"))
        self.wan_t2i_poll_max_attempts: int = int(os.getenv("WAN_T2I_POLL_MAX_ATTEMPTS", "45"))
        self.max_title_length: int = int(os.getenv("MAX_TITLE_LENGTH", "16"))
        self.segment_target_sec: float = float(os.getenv("SEGMENT_TARGET_SEC", "16"))
        self.final_min_duration_sec: float = float(
            os.getenv("FINAL_MIN_DURATION_SEC", str(55 if final_strict else 55))
        )
        self.final_max_duration_sec: float = float(
            os.getenv("FINAL_MAX_DURATION_SEC", str(130 if final_strict else 900))
        )

        self.image_provider: str = os.getenv("IMAGE_PROVIDER", "agnes_t2i")
        self.image_max_workers: int = int(os.getenv("IMAGE_MAX_WORKERS", "3"))
        self.image_submit_interval_sec: float = float(os.getenv("IMAGE_SUBMIT_INTERVAL_SEC", "20"))
        self.wan_model: str = os.getenv("WAN_MODEL", "wanx2.1-t2i-turbo")  # cSpell: disable-line
        self.wan_image_size: str = wan_image_size
        self.wan_cover_size: str = os.getenv("WAN_COVER_SIZE", _size_str(cover_w, cover_h))
        self.wan_prompt_extend: bool = _bool("WAN_PROMPT_EXTEND")
        self.z_image_model: str = os.getenv("Z_IMAGE_MODEL", "z-image-turbo")
        self.z_image_size: str = os.getenv("Z_IMAGE_SIZE", wan_image_size)
        self.z_image_prompt_extend: bool = _bool("Z_IMAGE_PROMPT_EXTEND")
        self.agnes_api_key: str | None = _opt("AGNES_API_KEY")
        self.agnes_free_api_key: str | None = _opt("AGNES_FREE_API_KEY")
        self.agnes_api_base_url: str = os.getenv("AGNES_API_BASE_URL", "https://apihub.agnes-ai.com/v1")
        self.agnes_image_model: str = os.getenv("AGNES_IMAGE_MODEL", "agnes-image-2.1-flash")
        self.agnes_image_size: str = os.getenv("AGNES_IMAGE_SIZE", wan_image_size)
        self.agnes_http_max_retries: int = int(os.getenv("AGNES_HTTP_MAX_RETRIES", "5"))
        self.agnes_http_connect_timeout_sec: float = float(
            os.getenv("AGNES_HTTP_CONNECT_TIMEOUT_SEC", "15")
        )
        self.agnes_http_submit_read_timeout_sec: float = float(
            os.getenv("AGNES_HTTP_SUBMIT_READ_TIMEOUT_SEC", "120")
        )
        self.agnes_http_poll_read_timeout_sec: float = float(
            os.getenv("AGNES_HTTP_POLL_READ_TIMEOUT_SEC", "30")
        )
        self.agnes_video_download_timeout_sec: float = float(
            os.getenv("AGNES_VIDEO_DOWNLOAD_TIMEOUT_SEC", "300")
        )
        self.agnes_video_model: str = os.getenv("AGNES_VIDEO_MODEL", "agnes-video-v2.0")
        self.agnes_video_width: int = int(os.getenv("AGNES_VIDEO_WIDTH", "1280"))
        self.agnes_video_height: int = int(os.getenv("AGNES_VIDEO_HEIGHT", "720"))
        self.agnes_video_frame_rate: int = int(os.getenv("AGNES_VIDEO_FRAME_RATE", "24"))
        self.agnes_video_poll_interval_sec: float = float(
            os.getenv("AGNES_VIDEO_POLL_INTERVAL_SEC", "5")
        )
        self.agnes_video_poll_max_attempts: int = int(os.getenv("AGNES_VIDEO_POLL_MAX_ATTEMPTS", "120"))
        self.agnes_video_task_max_retries: int = int(os.getenv("AGNES_VIDEO_TASK_MAX_RETRIES", "2"))
        self.agnes_video_submit_max_retries: int = int(
            os.getenv("AGNES_VIDEO_SUBMIT_MAX_RETRIES", "2")
        )
        self.media_public_base_url: str | None = _opt("MEDIA_PUBLIC_BASE_URL")
        self.sd_api_url: str = os.getenv("SD_API_URL", "http://127.0.0.1:9101").rstrip("/")
        self.sd_business: str | None = _opt("SD_BUSINESS")
        self.sd_image_size: str = os.getenv("SD_IMAGE_SIZE", "360*640")
        self.sd_timeout_sec: float = float(os.getenv("SD_TIMEOUT_SEC", "600"))

        self.llm_provider: str = os.getenv("LLM_PROVIDER", "deepseek").strip().lower()
        self.deepseek_api_key: str | None = deepseek_key
        self.deepseek_base_url: str = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        self.deepseek_model: str = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
        self.deepseek_max_tokens: int = int(os.getenv("DEEPSEEK_MAX_TOKENS", "32768"))
        self.deepseek_thinking_enabled: bool = _bool("DEEPSEEK_THINKING", default=True)
        self.agnes_llm_model: str = os.getenv("AGNES_LLM_MODEL", "agnes-2.0-flash")
        self.agnes_llm_max_tokens: int = int(os.getenv("AGNES_LLM_MAX_TOKENS", "32768"))
        self.agnes_vl_model: str = os.getenv("AGNES_VL_MODEL", "gpt-4o-mini")
        self.llm_image_prompt_batch_size: int = int(os.getenv("LLM_IMAGE_PROMPT_BATCH_SIZE", "4"))

        self.dashscope_api_key: str | None = dashscope_key
        self.tts_api_key: str | None = tts_key
        self.tts_base_url: str | None = _opt("TTS_BASE_URL")
        self.dashscope_ws_uri: str = os.getenv(
            "DASHSCOPE_WS_URI",
            "wss://dashscope.aliyuncs.com/api-ws/v1/inference/",  # cSpell: disable-line
        )
        self.tts_voice: str = _first("TTS_VOICE", "COSYVOICE_VOICE", default=_DEFAULT_TTS_VOICE)  # cSpell: disable-line
        self.tts_model: str | None = _first("TTS_MODEL", "COSYVOICE_MODEL") or None
        self.tts_speech_rate: float = float(
            _first("TTS_SPEECH_RATE", "COSYVOICE_SPEECH_RATE", default="1.20")
        )
        self.tts_volume: int = int(_first("TTS_VOLUME", "COSYVOICE_VOLUME", default="50"))
        self.tts_instruction: str | None = _opt("TTS_INSTRUCTION")
        self.tts_instruct_preset: str | None = _opt("TTS_INSTRUCT_PRESET")
        self.tts_max_workers: int = int(os.getenv("TTS_MAX_WORKERS", "5"))
        self.tts_trim_edges: bool = _bool("TTS_TRIM_EDGES", default=True)
        self.tts_audio_format: str = os.getenv("TTS_AUDIO_FORMAT", "mp3").strip().lower()

        self.audio_target_lufs: float = float(os.getenv("AUDIO_TARGET_LUFS", "-16"))
        self.audio_true_peak: float = float(os.getenv("AUDIO_TRUE_PEAK", "-1.5"))
        self.audio_silence_noise_db: float = float(os.getenv("AUDIO_SILENCE_NOISE_DB", "-40"))
        self.audio_max_silence_gap_sec: float = float(os.getenv("AUDIO_MAX_SILENCE_GAP_SEC", "1.5"))
        self.audio_max_edge_silence_sec: float = float(os.getenv("AUDIO_MAX_EDGE_SILENCE_SEC", "0.8"))
        self.tts_cue_duration_tolerance_sec: float = float(
            os.getenv("TTS_CUE_DURATION_TOLERANCE_SEC", "0.8")
        )
        self.audio_loudness_tolerance_lu: float = float(os.getenv("AUDIO_LOUDNESS_TOLERANCE_LU", "2.5"))

        self.intro_moon_tint: str = os.getenv("INTRO_MOON_TINT", "natural").strip().lower()
        self.intro_tts_rate: float = float(os.getenv("INTRO_TTS_RATE", "1.25"))
        self.intro_tts_pitch: float = float(os.getenv("INTRO_TTS_PITCH", "1.15"))

        self.bili_client_id: str | None = _opt("BILI_CLIENT_ID")
        self.bili_client_secret: str | None = _opt("BILI_CLIENT_SECRET")
        self.bili_access_token: str | None = _opt("BILI_ACCESS_TOKEN")

        self.pexels_api_key: str | None = _opt("PEXELS_API_KEY")
        self.pixabay_api_key: str | None = _opt("PIXABAY_API_KEY")
        self.clip_search_timeout_sec: float = float(os.getenv("CLIP_SEARCH_TIMEOUT_SEC", "12"))

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
