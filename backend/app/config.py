from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[2]
load_dotenv(ROOT_DIR / ".env")


def _bool(name: str, default: bool = False) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


def _parse_size(value: str) -> tuple[int, int]:
    """解析宽*高，如 1080*1920。"""
    normalized = value.strip().lower().replace("x", "*")
    width, height = normalized.split("*", 1)
    return int(width.strip()), int(height.strip())


def _size_str(width: int, height: int) -> str:
    return f"{width}*{height}"


@dataclass(frozen=True)
class Settings:
    root_dir: Path
    res_dir: Path
    font_path: Path
    intro_bg_path: Path
    sqlite_path: Path
    video_data_dir: Path
    redis_url: str | None
    mock_mode: bool
    skip_publish_default: bool
    host_enabled: bool
    kling_upgrade_enabled: bool
    image_provider: str
    image_max_workers: int
    image_submit_interval_sec: float
    # 成片（竖屏 9:16）：片头 / 字幕 / FFmpeg 合成
    video_width: int
    video_height: int
    # 投稿封面（横屏 16:9）：与成片分辨率独立
    cover_width: int
    cover_height: int
    wan_model: str
    # 万相 API 出图尺寸（可与上面不同）
    wan_image_size: str
    wan_cover_size: str
    z_image_model: str
    z_image_size: str
    z_image_prompt_extend: bool
    motion_preset: str
    deepseek_api_key: str | None
    deepseek_base_url: str
    deepseek_model: str
    dashscope_api_key: str | None
    tts_api_key: str | None
    tts_base_url: str | None
    dashscope_ws_uri: str
    tts_voice: str
    tts_model: str | None
    tts_speech_rate: float
    tts_volume: int
    bili_client_id: str | None
    bili_client_secret: str | None
    bili_access_token: str | None
    enable_scheduler: bool
    brand_name: str
    host_intro_path: Path
    host_boy_path: Path
    host_girl_path: Path
    intro_moon_path: Path
    intro_moon_tint: str
    intro_shout_path: Path
    intro_tts_rate: float
    intro_tts_pitch: float
    max_title_length: int
    segment_target_sec: float

    def video_size(self) -> str:
        return _size_str(self.video_width, self.video_height)

    def cover_size(self) -> str:
        return _size_str(self.cover_width, self.cover_height)


def get_settings() -> Settings:
    root = ROOT_DIR
    backend_dir = Path(__file__).resolve().parents[1]
    res_dir = Path(os.getenv("RES_DIR", backend_dir / "res"))
    data_dir = Path(os.getenv("VIDEO_DATA_DIR", root / "data" / "media"))
    sqlite = Path(os.getenv("SQLITE_PATH", root / "data" / "data.db"))
    if not res_dir.is_absolute():
        res_dir = (root / res_dir).resolve()
    font_path = Path(
        os.getenv("FONT_PATH", res_dir / "font" / "SourceHanSansCN-Medium.otf"),
    )
    if not font_path.is_absolute():
        font_path = (root / font_path).resolve()
    intro_bg_path = Path(os.getenv("INTRO_BG_PATH", res_dir / "bg" / "bg1.png"))
    if not intro_bg_path.is_absolute():
        intro_bg_path = (root / intro_bg_path).resolve()
    host_intro_path = Path(os.getenv("HOST_INTRO_PATH", res_dir / "host" / "intro.png"))
    if not host_intro_path.is_absolute():
        host_intro_path = (root / host_intro_path).resolve()
    host_boy_path = Path(os.getenv("HOST_BOY_PATH", res_dir / "host" / "boy.png"))
    if not host_boy_path.is_absolute():
        host_boy_path = (root / host_boy_path).resolve()
    host_girl_path = Path(os.getenv("HOST_GIRL_PATH", res_dir / "host" / "girl.png"))
    if not host_girl_path.is_absolute():
        host_girl_path = (root / host_girl_path).resolve()
    intro_moon_path = Path(os.getenv("INTRO_MOON_PATH", res_dir / "host" / "moon.png"))
    if not intro_moon_path.is_absolute():
        intro_moon_path = (root / intro_moon_path).resolve()
    intro_shout_path = Path(os.getenv("INTRO_SHOUT_PATH", res_dir / "audio" / "intro_shout.mp3"))
    if not intro_shout_path.is_absolute():
        intro_shout_path = (root / intro_shout_path).resolve()
    if not data_dir.is_absolute():
        data_dir = (root / data_dir).resolve()
    if not sqlite.is_absolute():
        sqlite = (root / sqlite).resolve()

    if os.getenv("VIDEO_SIZE"):
        video_width, video_height = _parse_size(os.environ["VIDEO_SIZE"])
    else:
        video_width = int(os.getenv("VIDEO_WIDTH", "1080"))
        video_height = int(os.getenv("VIDEO_HEIGHT", "1920"))

    if os.getenv("COVER_SIZE"):
        cover_width, cover_height = _parse_size(os.environ["COVER_SIZE"])
    else:
        cover_width = int(os.getenv("COVER_WIDTH", "1280"))
        cover_height = int(os.getenv("COVER_HEIGHT", "720"))

    wan_image_size = os.getenv("WAN_IMAGE_SIZE", "720*1280")
    wan_cover_size = os.getenv("WAN_COVER_SIZE", _size_str(cover_width, cover_height))

    deepseek_key = os.getenv("DEEPSEEK_API_KEY") or None
    dashscope_key = os.getenv("DASHSCOPE_API_KEY") or None
    tts_key = os.getenv("TTS_API_KEY") or dashscope_key
    mock = _bool("MOCK_MODE", False)
    if not mock and not (deepseek_key and dashscope_key and tts_key):
        mock = True
    return Settings(
        root_dir=root,
        res_dir=res_dir,
        font_path=font_path,
        intro_bg_path=intro_bg_path,
        sqlite_path=sqlite,
        video_data_dir=data_dir,
        redis_url=os.getenv("REDIS_URL"),
        mock_mode=mock,
        skip_publish_default=_bool("SKIP_PUBLISH_DEFAULT", True),
        host_enabled=_bool("HOST_ENABLED", False),
        kling_upgrade_enabled=_bool("KLING_UPGRADE_ENABLED", False),
        image_provider=os.getenv("IMAGE_PROVIDER", "z_image_t2i"),
        z_image_model=os.getenv("Z_IMAGE_MODEL", "z-image-turbo"),
        z_image_size=os.getenv("Z_IMAGE_SIZE", os.getenv("WAN_IMAGE_SIZE", "720*1280")),
        z_image_prompt_extend=_bool("Z_IMAGE_PROMPT_EXTEND", False),
        image_max_workers=int(os.getenv("IMAGE_MAX_WORKERS", "1")),
        image_submit_interval_sec=float(os.getenv("IMAGE_SUBMIT_INTERVAL_SEC", "3")),
        video_width=video_width,
        video_height=video_height,
        cover_width=cover_width,
        cover_height=cover_height,
        wan_model=os.getenv("WAN_MODEL", "wanx2.1-t2i-turbo"),  # cSpell: disable-line
        wan_image_size=wan_image_size,
        wan_cover_size=wan_cover_size,
        motion_preset=os.getenv("MOTION_PRESET", "ken_burns_slow"),
        deepseek_api_key=deepseek_key,
        deepseek_base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        deepseek_model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
        dashscope_api_key=dashscope_key,
        tts_api_key=tts_key,
        tts_base_url=os.getenv("TTS_BASE_URL"),
        dashscope_ws_uri=os.getenv(
            "DASHSCOPE_WS_URI",
            "wss://dashscope.aliyuncs.com/api-ws/v1/inference/", # cSpell: disable-line
        ),
        tts_voice=os.getenv("TTS_VOICE") or os.getenv("COSYVOICE_VOICE", "longwan_v3"),  # cSpell: disable-line
        tts_model=os.getenv("TTS_MODEL") or os.getenv("COSYVOICE_MODEL") or None,
        tts_speech_rate=float(
            os.getenv("TTS_SPEECH_RATE") or os.getenv("COSYVOICE_SPEECH_RATE", "1.0")
        ),
        tts_volume=int(os.getenv("TTS_VOLUME") or os.getenv("COSYVOICE_VOLUME", "50")),
        bili_client_id=os.getenv("BILI_CLIENT_ID") or None,
        bili_client_secret=os.getenv("BILI_CLIENT_SECRET") or None,
        bili_access_token=os.getenv("BILI_ACCESS_TOKEN") or None,
        enable_scheduler=_bool("ENABLE_SCHEDULER", False),
        brand_name=os.getenv("BRAND_NAME", "昭墨百科"),
        host_intro_path=host_intro_path,
        host_boy_path=host_boy_path,
        host_girl_path=host_girl_path,
        intro_moon_path=intro_moon_path,
        intro_moon_tint=os.getenv("INTRO_MOON_TINT", "natural").strip().lower(),
        intro_shout_path=intro_shout_path,
        intro_tts_rate=float(os.getenv("INTRO_TTS_RATE", "1.25")),
        intro_tts_pitch=float(os.getenv("INTRO_TTS_PITCH", "1.15")),
        max_title_length=int(os.getenv("MAX_TITLE_LENGTH", "24")),
        segment_target_sec=float(os.getenv("SEGMENT_TARGET_SEC", "12")),
    )
