"""TTS 包对外仅暴露 tts_mgr。"""

from app.services.tts import tts_mgr

__all__ = ["tts_mgr"]
