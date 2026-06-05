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

    def generate_script(self, title: str, *, feedback: str | None = None) -> dict[str, Any]:
        settings = get_settings()
        target = settings.segment_target_sec
        if target > 0:
            seg_rule = (
                f"segments必须12-14段，每段含segment_index,text,image_prompt,visual_mode=static_motion；"
                f"每段text约80-95字（约{int(target)}秒口播）；"
                f"image_prompt为竖屏9:16卡通插画/扁平信息图，非必要禁止画面内出现文字、数字、水印。"
            )
        else:
            seg_rule = (
                "segments为6-8段，每段含segment_index,text,image_prompt,visual_mode=static_motion；"
                "image_prompt为竖屏9:16卡通插画，非必要禁止画面内出现文字、数字、水印。"
            )
        max_title = settings.max_title_length
        system = (
            "你是科普视频编剧。输出JSON，字段：title, narration, word_count, segments。"
            f"title为精简后的视频标题，保留原标题核心意思，"
            f"不含空格换行，字数不超过{max_title}，适合封面最多三行展示。"
            f"{seg_rule}"
            "narration为完整口播，总字数950-1150（不含空格换行），口语化，结构完整有开头结尾。"
            "word_count必须等于narration实际字数，不得虚报。"
        )
        user = (
            f"原标题：{title}\n"
            f"请输出精简 title（≤{max_title}字）与完整口播，并拆成12-14个分镜。"
        )
        if feedback:
            user += f"\n\n上次不合格：{feedback}。请按字数与段数要求重写。"
        raw = self._chat(system, user)
        data = json.loads(raw)
        if "segments" not in data:
            raise ValueError("LLM response missing segments")
        return data
