"""CosyVoice 声音复刻：用 base64 data URI 方式提交音频。

用法（项目根目录）:
  python backend/scripts/clone_voice.py <音频路径> [--prefix leo] [--model cosyvoice-v3.5-flash]
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.config import get_settings


def main() -> None:
    parser = argparse.ArgumentParser(description="CosyVoice 声音复刻")
    parser.add_argument("audio", help="音频文件路径 (WAV/MP3/M4A)")
    parser.add_argument("--prefix", default="leo", help="音色名称前缀 (默认: leo)")
    parser.add_argument("--model", default="cosyvoice-v3.5-flash", help="目标模型 (默认: cosyvoice-v3.5-flash)")
    args = parser.parse_args()

    audio_path = Path(args.audio)
    if not audio_path.exists():
        print(f"ERROR: 音频文件不存在: {audio_path}")
        sys.exit(1)

    settings = get_settings()
    api_key = settings.dashscope_api_key or settings.tts_api_key
    if not api_key:
        print("ERROR: DASHSCOPE_API_KEY 未配置")
        sys.exit(1)

    # 判断 MIME 类型
    suffix = audio_path.suffix.lower()
    mime_map = {".wav": "audio/wav", ".mp3": "audio/mpeg", ".m4a": "audio/mp4"}
    mime_type = mime_map.get(suffix, "audio/mp4")

    # Encode audio as base64 data URI
    b64_data = base64.b64encode(audio_path.read_bytes()).decode()
    data_uri = f"data:{mime_type};base64,{b64_data}"
    print(f"Audio: {audio_path} ({audio_path.stat().st_size} bytes, base64 length: {len(b64_data)})")

    # CosyVoice voice-enrollment API
    url = "https://dashscope.aliyuncs.com/api/v1/services/audio/tts/customization"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "voice-enrollment",
        "input": {
            "action": "create_voice",
            "target_model": args.model,
            "prefix": args.prefix,
            "url": data_uri,
        },
    }

    print(f"Calling CosyVoice voice-enrollment API (prefix={args.prefix}, model={args.model})...")
    resp = requests.post(url, json=payload, headers=headers, timeout=120)
    print(f"Status: {resp.status_code}")
    result = resp.json()
    print(json.dumps(result, ensure_ascii=False, indent=2))

    voice_id = result.get("output", {}).get("voice_id", "")
    if voice_id:
        print(f"\nvoice_id: {voice_id}")
        print(f"将 voice_id 添加到以下位置即可使用:")
        print(f"  1. backend/app/services/tts/tts_ali.py VOICE_MODEL_MAP")
        print(f"  2. frontend/src/constants/tts-voices.ts CLONED_VOICES")
        print(f"  3. .env TTS_VOICE={voice_id}")


if __name__ == "__main__":
    main()
