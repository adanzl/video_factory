from __future__ import annotations

import json
from typing import Any

from app.config import get_settings
from app.services.llm.llm_mgr import LLMClient


class DeepSeekClient(LLMClient):
    def __init__(self) -> None:
        import requests

        self._requests = requests
        settings = get_settings()
        self._api_key = settings.deepseek_api_key
        self._base_url = settings.deepseek_base_url.rstrip("/")
        self._model = settings.deepseek_model

    def _chat(self, system: str, user: str) -> str:
        resp = self._requests.post(
            f"{self._base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self._model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "response_format": {"type": "json_object"},
            },
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    def generate_script(self, title: str) -> dict[str, Any]:
        system = (
            "你是B站科普视频编剧。输出JSON，字段：title, narration, word_count, segments。"
            "segments为6-8段，每段含segment_index,text,image_prompt,visual_mode=static_motion。"
            "narration为完整口播，总字数950-1150，口语化。"
        )
        raw = self._chat(system, f"标题：{title}")
        data = json.loads(raw)
        if "segments" not in data:
            raise ValueError("LLM response missing segments")
        return data
