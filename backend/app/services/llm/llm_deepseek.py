from __future__ import annotations

import json
import re
from typing import Any

from app.config import get_settings
from app.services.llm.llm_mgr import LLMClient
from app.services.llm.llm_script_description import parse_video_description_payload
from app.services.llm.llm_script_prompts import (
    MIN_IMAGE_PROMPT_CHARS,
    build_image_prompts_prompts,
    build_material_script_prompts,
    build_narration_expand_prompts,
    build_storyboard_prompts,
    build_title_optimize_prompts,
    build_video_description_prompts,
)
from app.services.llm.llm_script_timeline import narration_range_for_timeline, parse_video_timeline
from app.services.llm.llm_script_title import parse_title_optimize_payload
from app.services.llm.llm_topics import (
    build_topic_system_prompt,
    build_topic_user_prompt,
    parse_topics_payload,
)
from app.utils.media import default_narration_target_words, min_narration_chars_for_target

__all__ = ["DeepSeekClient", "MIN_IMAGE_PROMPT_CHARS"]

_NARRATION_LENGTH_RETRY_ATTEMPTS = 5
_NARRATION_EXPAND_ATTEMPTS = 2


def _narration_char_count(text: str) -> int:
    return len(re.sub(r"\s+", "", text or ""))


def _narration_length_feedback(chars: int, min_chars: int, *, prefix: str | None = None) -> str:
    deficit = max(1, min_chars - chars)
    msg = (
        f"narration 仅 {chars} 字，硬性下限 {min_chars} 字，还差 {deficit} 字。"
        "请增加 segments 段数并扩写每段 text（每层补具体细节/案例/步骤），"
        "先写 segments 再拼接 narration，核对 word_count 后再输出 JSON。"
    )
    if prefix:
        return f"{prefix}\n{msg}"
    return msg


def _merge_expanded_storyboard(original: dict[str, Any], expanded: dict[str, Any]) -> dict[str, Any]:
    if not expanded.get("visual_style"):
        expanded["visual_style"] = original.get("visual_style")
    orig_by_index = {
        int(seg["segment_index"]): seg
        for seg in original.get("segments") or []
        if seg.get("segment_index") is not None
    }
    for seg in expanded.get("segments") or []:
        idx = seg.get("segment_index")
        if idx is None:
            continue
        orig = orig_by_index.get(int(idx))
        if not orig:
            continue
        for key in ("visual_brief", "visual_mode", "image_prompt", "motion_prompt"):
            if not (seg.get(key) or "").strip() and (orig.get(key) or "").strip():
                seg[key] = orig[key]
    return expanded


def _min_narration_chars_for_script(
    *,
    narration_target_words: int | None,
    video_timeline: str | None = None,
) -> int:
    timeline = parse_video_timeline(video_timeline)
    if timeline:
        lo, _ = narration_range_for_timeline(timeline)
        return lo
    target = narration_target_words or default_narration_target_words()
    return min_narration_chars_for_target(target)


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
                "max_tokens": 8192,
            },
            timeout=180,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    def _expand_narration_if_needed(
        self,
        data: dict[str, Any],
        *,
        min_chars: int,
        mode: str,
    ) -> dict[str, Any]:
        chars = _narration_char_count(str(data.get("narration") or ""))
        if chars >= min_chars or chars < int(min_chars * 0.5):
            return data
        current = data
        segments = current.get("segments") or []
        default_mode = segments[0].get("visual_mode", "static_motion") if segments else "static_motion"
        for _ in range(_NARRATION_EXPAND_ATTEMPTS):
            prompts = build_narration_expand_prompts(current, min_chars=min_chars, mode=mode)
            expanded = json.loads(self._chat(prompts["system"], prompts["user"]))
            if "segments" not in expanded:
                break
            if mode == "storyboard":
                expanded = _merge_expanded_storyboard(current, expanded)
                if not expanded.get("visual_style"):
                    break
            for seg in expanded.get("segments") or []:
                seg.setdefault("visual_mode", default_mode)
            new_chars = _narration_char_count(str(expanded.get("narration") or ""))
            if new_chars > chars:
                current = expanded
                chars = new_chars
            if chars >= min_chars:
                break
        return current

    def _generate_storyboard(
        self,
        title: str,
        *,
        feedback: str | None = None,
        segment_target_sec: float | None = None,
        max_title_length: int | None = None,
        narration_target_words: int | None = None,
        supplementary_info: str | None = None,
        job: dict | None = None,
    ) -> dict[str, Any]:
        min_chars = _min_narration_chars_for_script(
            narration_target_words=narration_target_words,
        )
        length_feedback: str | None = feedback
        data: dict[str, Any] | None = None
        for attempt in range(_NARRATION_LENGTH_RETRY_ATTEMPTS):
            prompts = build_storyboard_prompts(
                title,
                feedback=length_feedback,
                segment_target_sec=segment_target_sec,
                max_title_length=max_title_length,
                narration_target_words=narration_target_words,
                supplementary_info=supplementary_info,
                job=job,
            )
            data = json.loads(self._chat(prompts["system"], prompts["user"]))
            if "segments" not in data:
                raise ValueError("LLM storyboard response missing segments")
            if not data.get("visual_style"):
                raise ValueError("LLM storyboard response missing visual_style")
            chars = _narration_char_count(str(data.get("narration") or ""))
            if chars >= min_chars:
                return data
            length_feedback = _narration_length_feedback(
                chars,
                min_chars,
                prefix=feedback if attempt == 0 and feedback else None,
            )
        if data is not None:
            data = self._expand_narration_if_needed(data, min_chars=min_chars, mode="storyboard")
        return data

    def _generate_image_prompts(
        self,
        script: dict[str, Any],
        *,
        feedback: str | None = None,
        supplementary_info: str | None = None,
        job: dict | None = None,
    ) -> dict[str, Any]:
        prompts = build_image_prompts_prompts(
            script,
            feedback=feedback,
            supplementary_info=supplementary_info,
            job=job,
        )
        raw = json.loads(self._chat(prompts["system"], prompts["user"]))
        if isinstance(raw, list):
            prompt_items = raw
        elif isinstance(raw, dict):
            prompt_items = raw.get("image_prompts")
        else:
            raise ValueError("LLM image prompt response has unexpected shape")
        if not prompt_items:
            raise ValueError("LLM image prompt response missing image_prompts")
        return {"image_prompts": prompt_items}

    def _merge_image_prompts(self, script: dict[str, Any], prompts: list[dict]) -> None:
        by_index: dict[int, dict] = {
            int(item["segment_index"]): item
            for item in prompts
            if item.get("image_prompt")
        }
        missing = [
            seg["segment_index"]
            for seg in script["segments"]
            if seg["segment_index"] not in by_index
        ]
        if missing:
            raise ValueError(f"image_prompts missing segments: {missing}")
        for seg in script["segments"]:
            item = by_index[seg["segment_index"]]
            seg["image_prompt"] = item["image_prompt"]
            seg["motion_prompt"] = item.get("motion_prompt", "")

    def generate_script(
        self,
        title: str,
        *,
        feedback: str | None = None,
        segment_target_sec: float | None = None,
        max_title_length: int | None = None,
        narration_target_words: int | None = None,
        supplementary_info: str | None = None,
        job: dict | None = None,
    ) -> dict[str, Any]:
        data = self._generate_storyboard(
            title,
            feedback=feedback,
            segment_target_sec=segment_target_sec,
            max_title_length=max_title_length,
            narration_target_words=narration_target_words,
            supplementary_info=supplementary_info,
            job=job,
        )

        prompt_feedback: str | None = None
        for attempt in range(4):
            prompt_data = self._generate_image_prompts(
                data,
                feedback=prompt_feedback,
                supplementary_info=supplementary_info,
                job=job,
            )
            self._merge_image_prompts(data, prompt_data["image_prompts"])
            short = [
                (seg["segment_index"], len(seg["image_prompt"]))
                for seg in data["segments"]
                if len(seg["image_prompt"]) < MIN_IMAGE_PROMPT_CHARS
            ]
            if not short:
                break
            prompt_feedback = (
                f"image_prompt too short: {short}; "
                f"need >={MIN_IMAGE_PROMPT_CHARS} chars each; "
                "expand all six layers (composition, subject, environment, lighting, color, scope)"
            )
        return data

    def generate_material_script(
        self,
        title: str,
        *,
        feedback: str | None = None,
        max_title_length: int | None = None,
        narration_target_words: int | None = None,
        supplementary_info: str | None = None,
        video_timeline: str | None = None,
    ) -> dict[str, Any]:
        min_chars = _min_narration_chars_for_script(
            narration_target_words=narration_target_words,
            video_timeline=video_timeline,
        )
        length_feedback: str | None = feedback
        data: dict[str, Any] | None = None
        for attempt in range(_NARRATION_LENGTH_RETRY_ATTEMPTS):
            prompts = build_material_script_prompts(
                title,
                feedback=length_feedback,
                max_title_length=max_title_length,
                narration_target_words=narration_target_words,
                supplementary_info=supplementary_info,
                video_timeline=video_timeline,
            )
            data = json.loads(self._chat(prompts["system"], prompts["user"]))
            if "segments" not in data:
                raise ValueError("LLM material script response missing segments")
            for seg in data["segments"]:
                seg.setdefault("visual_mode", "material")
            chars = _narration_char_count(str(data.get("narration") or ""))
            if chars >= min_chars:
                return data
            length_feedback = _narration_length_feedback(
                chars,
                min_chars,
                prefix=feedback if attempt == 0 and feedback else None,
            )
        if data is not None:
            data = self._expand_narration_if_needed(data, min_chars=min_chars, mode="material")
        return data

    def optimize_script_title(
        self,
        draft_title: str,
        narration: str,
        *,
        max_title_length: int | None = None,
    ) -> str:
        prompts = build_title_optimize_prompts(
            draft_title,
            narration,
            max_title_length=max_title_length,
        )
        raw = json.loads(self._chat(prompts["system"], prompts["user"]))
        settings = get_settings()
        max_len = settings.max_title_length if max_title_length is None else max_title_length
        return parse_title_optimize_payload(raw, max_title_len=max_len)

    def generate_video_description(
        self,
        title: str,
        narration: str,
    ) -> str:
        prompts = build_video_description_prompts(title, narration)
        raw = json.loads(self._chat(prompts["system"], prompts["user"]))
        return parse_video_description_payload(raw)

    def generate_topics(
        self,
        theme: str,
        *,
        count: int = 10,
        system_prompt: str | None = None,
        user_prompt: str | None = None,
    ) -> list[dict[str, str]]:
        settings = get_settings()
        count = max(1, min(count, 20))
        system = system_prompt or build_topic_system_prompt(max_title_len=settings.max_title_length)
        user = user_prompt.strip() if user_prompt else build_topic_user_prompt(theme=theme, count=count)
        raw = json.loads(self._chat(system, user))
        topics = parse_topics_payload(raw, max_title_len=settings.max_title_length)
        return topics[:count]
