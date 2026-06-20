"""Extract voice_id -> preview audio URL mapping from Aliyun CosyVoice docs."""
from __future__ import annotations

import json
import re
import urllib.request
from pathlib import Path

URL = "https://help.aliyun.com/zh/model-studio/cosyvoice-voice-list"
OUTPUT = Path(__file__).resolve().parents[1] / "frontend" / "src" / "constants" / "cosyvoice-voice-previews.json"

VOICE_ID_RE = re.compile(
    r"voice(?:<[^>]+>)*参数(?:<[^>]+>)*[：:]\s*(long[a-z0-9_]+|loong[a-z0-9_]+)",
    re.I,
)
AUDIO_SRC_RE = re.compile(
    r'src="(https?://[^"]+\.(?:mp3|wav|m4a|ogg))"',
    re.I,
)


def extract_mapping(html: str) -> dict[str, str]:
    mapping: dict[str, str] = {}

    for match in VOICE_ID_RE.finditer(html):
        voice_id = match.group(1).lower()
        window = html[match.start() : match.start() + 15000]
        audio_match = AUDIO_SRC_RE.search(window)
        if audio_match:
            mapping[voice_id] = audio_match.group(1)

    return mapping


def main() -> None:
    html = urllib.request.urlopen(URL, timeout=30).read().decode("utf-8", errors="ignore")
    mapping = extract_mapping(html)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"mapped {len(mapping)} voices -> {OUTPUT}")


if __name__ == "__main__":
    main()
