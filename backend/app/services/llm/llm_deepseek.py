from __future__ import annotations

import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from app.config import get_settings
from app.services.llm.llm_mgr import LLMClient
from app.services.script.description import (
    build_video_description_prompts,
    parse_video_description_payload,
)
from app.quality.image_prompt import MIN_IMAGE_PROMPT_CHARS, IMAGE_PROMPT_TARGET_CHARS
from app.services.script.board import (
    build_image_prompts_prompts,
    build_material_script_prompts,
    build_narration_expand_prompts,
    build_narration_prompts,
    build_segment_shrink_prompts,
    build_visual_brief_prompts,
)
from app.services.script.optimize_title import (
    build_title_optimize_prompts,
    parse_title_optimize_payload,
)
from app.services.script.board_timeline import narration_range_for_timeline, parse_video_timeline
from app.services.topic.parsers import (
    format_topic_parse_feedback,
    is_topic_parse_retryable,
    parse_topics_payload,
)
from app.services.topic.prompts.builder import (
    build_topic_system_prompt,
    build_topic_user_prompt,
)
from app.services.daily_story.prompts import (
    DAILY_STORY_CHARACTERS,
    build_daily_script_prompts,
    build_daily_story_prompts,
    build_daily_story_theme_prompts,
    validate_daily_story_json,
)
from app.utils.job_cancel import raise_if_job_cancelled
from app.utils.media import (
    default_narration_target_words,
    min_narration_chars_for_target,
    narration_accept_max_chars,
    narration_accept_min_chars,
    segment_text_char_cap,
    split_narration_to_segments,
)

__all__ = ["DeepSeekClient", "MIN_IMAGE_PROMPT_CHARS"]

logger = logging.getLogger(__name__)

_NARRATION_EXPAND_ATTEMPTS = 2
_TRUNCATION_RETRY_ATTEMPTS = 3


def _build_deepseek_chat_payload(
    *,
    model: str,
    system: str,
    user: str,
    max_tokens: int,
    thinking_enabled: bool,
    json_mode: bool = True,
    temperature: float | None = None,
) -> dict[str, Any]:
    """构建 chat/completions JSON；V4 默认 thinking=enabled，结构化输出须显式关闭。"""
    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": max_tokens,
        "thinking": {"type": "enabled" if thinking_enabled else "disabled"},
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    if temperature is not None:
        payload["temperature"] = temperature
    return payload


def _storyboard_length_max_attempts() -> int:
    return get_settings().script_qa_max_attempts


_VISUAL_STYLE_BY_CONTENT_STYLE = {
    "daily_story": (
        "儿童情绪涂鸦风格，彩铅和蜡笔混合笔触，用力不均的线条，"
        "主观夸张变形，高饱和色彩，涂色出界，"
        "橡皮擦拭痕迹，手工感，孩子气的构图。"
        "主角：" + DAILY_STORY_CHARACTERS
    ),
    "life_experience": "生活 Vlog 质感写实画面：自然光或室内暖光，色彩真实不过度滤镜。",
    "history_mystery": "电影级写实历史再现：光影考究、暗部有层次、低饱和古风色调。",
    "tech_science": "电影级写实科技视觉：布光考究、材质细节真实、信息感强。",
    "science_child": "卡通科普插画风：明快蓝橙主色调，轮廓清晰、色块分明，偏科普示意图质感。",
}


def _resolve_visual_style(job: dict | None) -> str:
    """按 job 的 content_style 返回硬编码 visual_style。"""
    from app.utils.job_info import content_style_from_job
    style = content_style_from_job(job) if job else "science_child"
    return _VISUAL_STYLE_BY_CONTENT_STYLE.get(
        style, _VISUAL_STYLE_BY_CONTENT_STYLE["science_child"]
    )


def _narration_char_count(text: str) -> int:
    return len(re.sub(r"\s+", "", text or ""))


def _narration_length_feedback(
    chars: int,
    min_chars: int,
    *,
    prefix: str | None = None,
    narration_only: bool = False,
) -> str:
    deficit = max(1, min_chars - chars)
    if narration_only:
        msg = (
            f"narration 仅 {chars} 字，验收下限 {min_chars} 字，还差 {deficit} 字。"
            "请扩写 narration（补具体细节/案例/步骤/比喻），"
            "输出前核对 word_count 后再输出 JSON。"
        )
    else:
        msg = (
            f"narration 仅 {chars} 字，验收下限 {min_chars} 字，还差 {deficit} 字。"
            "请扩写各段 text（每层补具体细节/案例/步骤），"
            "先写 segments 再拼接 narration，输出前核对 word_count 与拼接一致性后再输出 JSON。"
        )
    if prefix:
        return f"{prefix}\n{msg}"
    return msg


def _narration_too_long_feedback(
    chars: int,
    max_chars: int,
    *,
    prefix: str | None = None,
    narration_only: bool = False,
) -> str:
    excess = max(1, chars - max_chars)
    if narration_only:
        msg = (
            f"narration 达 {chars} 字，超过验收上限 {max_chars} 字（超出 {excess} 字）。"
            "请删繁就简：删重复例子、合并并列知识点、缩短句子；"
            "输出前核对 word_count 后再输出 JSON。"
        )
    else:
        msg = (
            f"narration 达 {chars} 字，超过验收上限 {max_chars} 字（超出 {excess} 字）。"
            "请删繁就简：删重复例子、合并并列知识点、缩短每层句子；"
            "总字数靠删内容不靠堆段，禁止加长单段或新增话题；"
            "先写 segments 再拼接 narration，输出前逐段核对字数与总和后再输出 JSON。"
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
    chars_per_sec: float | None = None,
) -> int:
    timeline = parse_video_timeline(video_timeline, chars_per_sec=chars_per_sec)
    if timeline:
        lo, _ = narration_range_for_timeline(timeline)
        return lo
    target = narration_target_words or default_narration_target_words()
    return narration_accept_min_chars(target)


def _storyboard_max_tokens(
    narration_target_words: int | None,
    *,
    compact: bool,
) -> int:
    settings = get_settings()
    target = narration_target_words or default_narration_target_words()
    ceiling = settings.deepseek_max_tokens
    if compact or target >= 900:
        return ceiling
    # 含 narration 重复字段时约 10 token/字
    estimated = int(target * 10 + 2500)
    return min(ceiling, max(4096, estimated))


def _strip_markdown_json_fence(content: str) -> str:
    text = content.strip()
    if not text.startswith("```"):
        return text
    text = re.sub(r"^```(?:json)?\s*", "", text, count=1, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text.rstrip())
    return text.strip()


def _extract_json_object(text: str) -> str:
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return text[start : end + 1]
    return text


def _escape_control_chars_in_json_strings(raw: str) -> str:
    """将 JSON 字符串字面量内未转义的控制字符转为 \\n / \\uXXXX。"""
    result: list[str] = []
    in_string = False
    escaped = False
    for ch in raw:
        if escaped:
            result.append(ch)
            escaped = False
            continue
        if ch == "\\":
            result.append(ch)
            escaped = True
            continue
        if ch == '"':
            in_string = not in_string
            result.append(ch)
            continue
        if in_string and ord(ch) < 0x20:
            if ch == "\n":
                result.append("\\n")
            elif ch == "\r":
                result.append("\\r")
            elif ch == "\t":
                result.append("\\t")
            else:
                result.append(f"\\u{ord(ch):04x}")
            continue
        result.append(ch)
    return "".join(result)


def _loads_llm_json(content: str) -> dict[str, Any]:
    text = _strip_markdown_json_fence(content)
    candidates = [text]
    extracted = _extract_json_object(text)
    if extracted != text:
        candidates.append(extracted)

    last_exc: json.JSONDecodeError | None = None
    for candidate in candidates:
        for variant in (candidate, _escape_control_chars_in_json_strings(candidate), _fix_trailing_commas(candidate)):
            try:
                parsed = json.loads(variant)
            except json.JSONDecodeError as exc:
                last_exc = exc
                continue
            if isinstance(parsed, dict):
                return parsed
    raise ValueError(f"LLM returned invalid JSON: {last_exc}") from last_exc


def _fix_trailing_commas(text: str) -> str:
    """移除 JSON 数组和对象中非法的尾部逗号。"""
    import re
    # 移除数组中 ] 前的尾部逗号
    text = re.sub(r',\s*]', ']', text)
    # 移除对象中 } 前的尾部逗号
    text = re.sub(r',\s*}', '}', text)
    return text


def _assemble_storyboard_narration(data: dict[str, Any]) -> dict[str, Any]:
    narration = str(data.get("narration") or "").strip()
    segments = data.get("segments") or []
    if not narration and segments:
        ordered = sorted(
            segments,
            key=lambda seg: int(seg.get("segment_index") or seg.get("index") or 0),
        )
        narration = "".join(str(seg.get("text") or "") for seg in ordered)
        data["narration"] = narration
    data["word_count"] = _narration_char_count(str(data.get("narration") or ""))
    return data


def _apply_segments_from_narration(
    data: dict[str, Any],
    *,
    segment_target_sec: float,
    chars_per_sec: float | None = None,
) -> dict[str, Any]:
    from app.utils.media import DEFAULT_SPEECH_CHARS_PER_SEC

    narration = str(data.get("narration") or "").strip()
    if not narration:
        raise ValueError("LLM narration response missing narration")
    rate = chars_per_sec or DEFAULT_SPEECH_CHARS_PER_SEC
    data["segments"] = split_narration_to_segments(
        narration,
        segment_target_sec,
        chars_per_sec=rate,
    )
    if not data["segments"]:
        raise ValueError("narration split produced no segments")
    return _assemble_storyboard_narration(data)


def _merge_visual_briefs(script: dict[str, Any], payload: dict[str, Any]) -> None:
    # visual_style 已由 _generate_storyboard 硬编码设置，忽略 LLM 输出
    by_index = {
        int(item["segment_index"]): item
        for item in payload.get("segments") or []
        if item.get("segment_index") is not None
    }
    required = [int(seg["segment_index"]) for seg in script.get("segments") or []]
    missing = [idx for idx in required if idx not in by_index]
    if missing:
        raise ValueError(f"visual_brief response missing segments: {missing}")
    for seg in script.get("segments") or []:
        idx = int(seg["segment_index"])
        item = by_index[idx]
        brief = str(item.get("visual_brief") or "").strip()
        if not brief:
            raise ValueError(f"visual_brief empty for segment {idx}")
        seg["visual_brief"] = brief
        seg["visual_mode"] = item.get("visual_mode") or seg.get("visual_mode") or "static_motion"


def _truncation_feedback(*, compact: bool) -> str:
    if compact:
        return (
            "上次 JSON 输出被截断（token 用尽）。"
            "务必省略 narration/word_count，只输出 title、segments；"
            "每段 visual_brief 严格 30-50 字，确保 JSON 完整闭合。"
        )
    return (
        "上次 JSON 输出被截断（token 用尽）。"
        "请省略 narration/word_count 字段，只写 segments 内 text 与 visual_brief（每段 brief≤50字），"
        "后端会自动拼接 narration。"
    )


def _chunk_indices(indices: list[int], batch_size: int) -> list[list[int]]:
    size = max(1, batch_size)
    ordered = sorted({int(idx) for idx in indices})
    return [ordered[i : i + size] for i in range(0, len(ordered), size)]


class DeepSeekClient(LLMClient):
    def __init__(self) -> None:
        import requests

        self._requests = requests
        settings = get_settings()
        self._api_key = settings.deepseek_api_key
        self._base_url = settings.deepseek_base_url.rstrip("/")
        self._model = settings.deepseek_model

    def _chat(self, system: str, user: str, *, max_tokens: int | None = None, json_mode: bool = True, thinking_enabled: bool | None = None, temperature: float | None = None) -> tuple[str, str | None]:
        settings = get_settings()
        limit = settings.deepseek_max_tokens if max_tokens is None else max_tokens
        use_thinking = settings.deepseek_thinking_enabled if thinking_enabled is None else thinking_enabled
        resp = self._requests.post(
            f"{self._base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            json=_build_deepseek_chat_payload(
                model=self._model,
                system=system,
                user=user,
                max_tokens=limit,
                thinking_enabled=use_thinking,
                json_mode=json_mode,
                temperature=temperature,
            ),
            timeout=180,
        )
        resp.raise_for_status()
        choice = resp.json()["choices"][0]
        finish = choice.get("finish_reason")
        content = choice.get("message", {}).get("content") or ""
        if finish == "length":
            logger.warning(
                "LLM response truncated (finish_reason=length), max_tokens=%d model=%s",
                limit,
                self._model,
            )
        return content, finish

    def _chat_json(
        self,
        system: str,
        user: str,
        *,
        max_tokens: int | None = None,
        thinking_enabled: bool | None = None,
        temperature: float | None = None,
    ) -> tuple[dict[str, Any], str | None]:
        _EMPTY_RETRIES = 3
        for _ in range(_EMPTY_RETRIES):
            content, finish = self._chat(system, user, max_tokens=max_tokens, thinking_enabled=thinking_enabled, temperature=temperature)
            if content.strip():
                break
            logger.warning(
                "LLM returned empty response, retrying (max=%d)",
                _EMPTY_RETRIES,
            )
            time.sleep(1)
        else:
            raise ValueError("LLM returned empty response after %d retries" % _EMPTY_RETRIES)
        try:
            parsed = _loads_llm_json(content)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc
        return parsed, finish

    def _expand_narration_if_needed(
        self,
        data: dict[str, Any],
        *,
        min_chars: int,
        mode: str,
        job: dict | None = None,
    ) -> dict[str, Any]:
        chars = _narration_char_count(str(data.get("narration") or ""))
        if chars >= min_chars or chars < int(min_chars * 0.5):
            return data
        current = data
        segments = current.get("segments") or []
        default_mode = segments[0].get("visual_mode", "static_motion") if segments else "static_motion"
        for _ in range(_NARRATION_EXPAND_ATTEMPTS):
            raise_if_job_cancelled(job)
            prompts = build_narration_expand_prompts(current, min_chars=min_chars, mode=mode)
            expanded, _ = self._chat_json(prompts["system"], prompts["user"], thinking_enabled=False)
            raise_if_job_cancelled(job)
            if mode == "narration_only":
                if not str(expanded.get("narration") or "").strip():
                    break
                if not expanded.get("visual_style"):
                    expanded["visual_style"] = current.get("visual_style")
                if not expanded.get("title"):
                    expanded["title"] = current.get("title")
            elif "segments" not in expanded:
                break
            else:
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

    def shrink_segment_texts(
        self,
        script: dict[str, Any],
        *,
        segment_indices: list[int],
        segment_target_sec: float,
        job: dict | None = None,
    ) -> dict[str, Any]:
        if not segment_indices:
            return script
        cap = segment_text_char_cap(segment_target_sec)
        started = time.perf_counter()
        prompts = build_segment_shrink_prompts(
            script,
            segment_indices=segment_indices,
            cap=cap,
            segment_target_sec=segment_target_sec,
            job=job,
        )
        raw, _ = self._chat_json(prompts["system"], prompts["user"], max_tokens=4096, thinking_enabled=False)
        raise_if_job_cancelled(job)
        items = raw.get("segments") if isinstance(raw, dict) else raw
        if not isinstance(items, list) or not items:
            raise ValueError("LLM segment shrink response missing segments")
        by_idx: dict[int, str] = {}
        for item in items:
            if not isinstance(item, dict):
                continue
            idx = item.get("segment_index")
            text = item.get("text")
            if idx is None or not isinstance(text, str) or not text.strip():
                continue
            by_idx[int(idx)] = text.strip()
        missing = [idx for idx in segment_indices if idx not in by_idx]
        if missing:
            raise ValueError(f"segment shrink missing indices: {missing}")
        for seg in script.get("segments") or []:
            idx = int(seg.get("segment_index", -1))
            if idx in by_idx:
                seg["text"] = by_idx[idx]
        elapsed = time.perf_counter() - started
        logger.info(
            "[SCRIPT] segment_shrink done indices=%s cap=%d elapsed=%.1fs",
            segment_indices,
            cap,
            elapsed,
        )
        timing = script.setdefault("_llm_timing", {})
        timing["segment_shrink_sec"] = round(
            float(timing.get("segment_shrink_sec") or 0) + elapsed, 1
        )
        return _assemble_storyboard_narration(script)

    def _generate_narration_only(
        self,
        title: str,
        *,
        feedback: str | None = None,
        max_title_length: int | None = None,
        narration_target_words: int | None = None,
        supplementary_info: str | None = None,
        job: dict | None = None,
    ) -> dict[str, Any]:
        min_chars = _min_narration_chars_for_script(
            narration_target_words=narration_target_words,
        )
        max_chars = narration_accept_max_chars(narration_target_words)
        length_feedback: str | None = feedback
        data: dict[str, Any] | None = None
        for attempt in range(_storyboard_length_max_attempts()):
            raise_if_job_cancelled(job)
            prompts = build_narration_prompts(
                title,
                feedback=length_feedback,
                max_title_length=max_title_length,
                narration_target_words=narration_target_words,
                supplementary_info=supplementary_info,
                job=job,
            )
            data, finish = self._chat_json(
                prompts["system"],
                prompts["user"],
                max_tokens=get_settings().deepseek_max_tokens,
            )
            raise_if_job_cancelled(job)
            if finish == "length":
                length_feedback = _truncation_feedback(compact=False)
                if feedback and attempt == 0:
                    length_feedback = f"{feedback}\n{length_feedback}"
                data = None
                continue
            narration = str(data.get("narration") or "").strip()
            if not narration:
                raise ValueError("LLM narration response missing narration")
            chars = _narration_char_count(narration)
            data["narration"] = narration
            data["word_count"] = chars
            if chars > max_chars:
                length_feedback = _narration_too_long_feedback(
                    chars,
                    max_chars,
                    prefix=feedback if attempt == 0 and feedback else None,
                    narration_only=True,
                )
                continue
            if chars >= min_chars:
                return data
            length_feedback = _narration_length_feedback(
                chars,
                min_chars,
                prefix=feedback if attempt == 0 and feedback else None,
                narration_only=True,
            )
        if data is not None:
            chars = _narration_char_count(str(data.get("narration") or ""))
            if chars <= max_chars:
                data = self._expand_narration_if_needed(
                    data,
                    min_chars=min_chars,
                    mode="narration_only",
                    job=job,
                )
                data["word_count"] = _narration_char_count(str(data.get("narration") or ""))
        if data is None:
            raise ValueError("LLM narration generation failed")
        raise_if_job_cancelled(job)
        return data

    def _fill_visual_briefs(
        self,
        script: dict[str, Any],
        *,
        feedback: str | None = None,
        supplementary_info: str | None = None,
        job: dict | None = None,
    ) -> dict[str, Any]:
        if not script.get("segments"):
            raise ValueError("script has no segments for visual_brief")
        started = time.perf_counter()
        prompts = build_visual_brief_prompts(
            script,
            feedback=feedback,
            supplementary_info=supplementary_info,
            job=job,
        )
        payload, finish = self._chat_json(
            prompts["system"],
            prompts["user"],
            max_tokens=get_settings().deepseek_max_tokens,
            thinking_enabled=False,
        )
        raise_if_job_cancelled(job)
        if finish == "length":
            raise ValueError("LLM visual_brief response truncated")
        _merge_visual_briefs(script, payload)
        elapsed = time.perf_counter() - started
        logger.info(
            "[SCRIPT] visual_brief done segments=%d elapsed=%.1fs",
            len(script.get("segments") or []),
            elapsed,
        )
        timing = script.setdefault("_llm_timing", {})
        timing["visual_brief_sec"] = round(elapsed, 1)
        return script

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
        seg_target = (
            get_settings().segment_target_sec
            if segment_target_sec is None
            else segment_target_sec
        )
        narration_started = time.perf_counter()
        data = self._generate_narration_only(
            title,
            feedback=feedback,
            max_title_length=max_title_length,
            narration_target_words=narration_target_words,
            supplementary_info=supplementary_info,
            job=job,
        )
        narration_elapsed = time.perf_counter() - narration_started
        data = _apply_segments_from_narration(data, segment_target_sec=seg_target)
        data = self._fill_visual_briefs(
            data,
            supplementary_info=supplementary_info,
            job=job,
        )
        # visual_style 始终走硬编码，不依赖 LLM 生成
        data["visual_style"] = _resolve_visual_style(job)
        timing = data.setdefault("_llm_timing", {})
        timing["narration_sec"] = round(narration_elapsed, 1)
        timing["storyboard_sec"] = round(
            narration_elapsed + float(timing.get("visual_brief_sec") or 0),
            1,
        )
        raise_if_job_cancelled(job)
        return data

    def _generate_image_prompts(
        self,
        script: dict[str, Any],
        *,
        feedback: str | None = None,
        supplementary_info: str | None = None,
        job: dict | None = None,
        segment_indices: list[int] | None = None,
        include_sd15_prompt: bool = False,
    ) -> dict[str, Any]:
        prompts = build_image_prompts_prompts(
            script,
            feedback=feedback,
            supplementary_info=supplementary_info,
            job=job,
            segment_indices=segment_indices,
            include_sd15_prompt=include_sd15_prompt,
        )
        raw, finish = self._chat_json(
            prompts["system"], prompts["user"], thinking_enabled=False,
        )
        raise_if_job_cancelled(job)
        if finish == "length":
            raise ValueError("LLM image_prompts 被截断 (finish_reason=length)")
        if isinstance(raw, list):
            prompt_items = raw
        elif isinstance(raw, dict):
            prompt_items = raw.get("image_prompts")
        else:
            raise ValueError("LLM image prompt response has unexpected shape")
        if not prompt_items:
            raise ValueError("LLM image prompt response missing image_prompts")
        return {"image_prompts": prompt_items}

    def _merge_image_prompts(
        self,
        script: dict[str, Any],
        prompts: list[dict],
        *,
        required_indices: list[int] | None = None,
    ) -> None:
        by_index: dict[int, dict] = {
            int(item["segment_index"]): item
            for item in prompts
            if item.get("image_prompt")
        }
        required = required_indices or [
            int(seg["segment_index"]) for seg in script.get("segments") or []
        ]
        missing = [idx for idx in required if idx not in by_index]
        if missing:
            raise ValueError(f"image_prompts missing segments: {missing}")
        index_set = set(required)
        for seg in script["segments"]:
            idx = int(seg["segment_index"])
            if idx not in index_set:
                continue
            item = by_index[idx]
            seg["image_prompt"] = item["image_prompt"]
            seg["motion_prompt"] = item.get("motion_prompt", "")
            # 存储 SD15 专用英文 prompt（仅当 LLM 输出了该字段时）
            sd15_en = item.get("sd15_prompt_en")
            if sd15_en and isinstance(sd15_en, str) and sd15_en.strip():
                seg["sd15_prompt_en"] = sd15_en.strip()

    def fill_image_prompts(
        self,
        script: dict[str, Any],
        *,
        feedback: str | None = None,
        supplementary_info: str | None = None,
        job: dict | None = None,
        segment_indices: list[int] | None = None,
        include_sd15_prompt: bool = False,
    ) -> dict[str, Any]:
        settings = get_settings()
        segments = script.get("segments") or []
        if not segments:
            raise ValueError("script has no segments")
        all_indices = segment_indices or [int(seg["segment_index"]) for seg in segments]
        batch_size = settings.llm_image_prompt_batch_size
        started = time.perf_counter()

        def _run_batch(batch_indices: list[int]) -> list[dict]:
            result = self._generate_image_prompts(
                script,
                feedback=feedback,
                supplementary_info=supplementary_info,
                job=job,
                segment_indices=batch_indices,
                include_sd15_prompt=include_sd15_prompt,
            )
            return result["image_prompts"]

        def _run_all(batches: list[list[int]]) -> list[dict]:
            items: list[dict] = []
            if len(batches) <= 1:
                items = _run_batch(batches[0])
            else:
                with ThreadPoolExecutor(max_workers=len(batches)) as pool:
                    futures = {pool.submit(_run_batch, batch): batch for batch in batches}
                    for future in as_completed(futures):
                        items.extend(future.result())
                        raise_if_job_cancelled(job)
            return items

        # 首次尝试
        batches = _chunk_indices(all_indices, batch_size)
        try:
            prompt_items = _run_all(batches)
        except ValueError as exc:
            if "被截断" not in str(exc) or batch_size <= 1:
                raise
            # 截断时缩小批次（逐段生成）重试一次
            logger.warning(
                "image_prompts truncated with batch_size=%d, retrying with batch_size=1",
                batch_size,
            )
            batches = _chunk_indices(all_indices, 1)
            prompt_items = _run_all(batches)

        self._merge_image_prompts(script, prompt_items, required_indices=all_indices)
        raise_if_job_cancelled(job)
        elapsed = time.perf_counter() - started
        logger.info(
            "[SCRIPT] image_prompts done segments=%d batches=%d elapsed=%.1fs",
            len(all_indices),
            len(batches),
            elapsed,
        )
        timing = script.setdefault("_llm_timing", {})
        timing["image_prompts_sec"] = round(elapsed, 1)
        timing["image_prompt_batches"] = len(batches)
        return script

    def _fill_image_prompts_with_retries(
        self,
        script: dict[str, Any],
        *,
        supplementary_info: str | None = None,
        job: dict | None = None,
        segment_indices: list[int] | None = None,
        feedback: str | None = None,
        include_sd15_prompt: bool = False,
    ) -> dict[str, Any]:
        self.fill_image_prompts(
            script,
            feedback=feedback,
            supplementary_info=supplementary_info,
            job=job,
            segment_indices=segment_indices,
            include_sd15_prompt=include_sd15_prompt,
        )
        return script

    def generate_storyboard(
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
        started = time.perf_counter()
        data = self._generate_storyboard(
            title,
            feedback=feedback,
            segment_target_sec=segment_target_sec,
            max_title_length=max_title_length,
            narration_target_words=narration_target_words,
            supplementary_info=supplementary_info,
            job=job,
        )
        raise_if_job_cancelled(job)
        elapsed = time.perf_counter() - started
        logger.info(
            "[SCRIPT] storyboard done segments=%d words=%d elapsed=%.1fs",
            len(data.get("segments") or []),
            _narration_char_count(str(data.get("narration") or "")),
            elapsed,
        )
        data["_llm_timing"] = {"storyboard_sec": round(elapsed, 1)}
        return data

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
        existing_script: dict[str, Any] | None = None,
        retry_scope: str | None = None,
        generate_image_prompts: bool = True,
        include_sd15_prompt: bool = False,
    ) -> dict[str, Any]:
        if retry_scope == "image_prompts" and existing_script is not None:
            data = existing_script
            self._fill_image_prompts_with_retries(
                data,
                supplementary_info=supplementary_info,
                job=job,
                feedback=feedback,
                include_sd15_prompt=include_sd15_prompt,
            )
            return data

        if retry_scope == "visual_brief" and existing_script is not None:
            data = existing_script
            self._fill_visual_briefs(
                data,
                feedback=feedback,
                supplementary_info=supplementary_info,
                job=job,
            )
            return data

        data = self.generate_storyboard(
            title,
            feedback=feedback,
            segment_target_sec=segment_target_sec,
            max_title_length=max_title_length,
            narration_target_words=narration_target_words,
            supplementary_info=supplementary_info,
            job=job,
        )
        if generate_image_prompts:
            self._fill_image_prompts_with_retries(
                data,
                supplementary_info=supplementary_info,
                job=job,
                include_sd15_prompt=include_sd15_prompt,
            )
        return data

    def _shrink_longest_segments_to_fit(
        self,
        data: dict[str, Any],
        max_chars: int,
    ) -> None:
        """总口播超长时，按长度降序缩句最长的 segments，直到总字数 <= max_chars。"""
        segments = data.get("segments") or []
        if not segments:
            return
        seg_texts = [str(s.get("text") or "") for s in segments]
        total = _narration_char_count("".join(seg_texts))
        excess = total - max_chars
        if excess <= 0:
            return
        # 按文本长度降序排列，优先缩最长的段
        indexed = sorted(
            enumerate(segments),
            key=lambda pair: _narration_char_count(str(pair[1].get("text") or "")),
            reverse=True,
        )
        for _orig_idx, seg in indexed:
            if excess <= 0:
                break
            text = str(seg.get("text") or "")
            cur_len = _narration_char_count(text)
            if cur_len <= 10:
                continue
            # 目标：至少砍掉 excess，但不低于 10 字
            target_len = max(10, cur_len - excess)
            system = (
                "将以下口播段落精简缩短，保留核心信息与自然口吻，"
                f"字数控制在 {target_len} 字以内（当前 {cur_len} 字）。"
                "直输出精简后的段落文本，不要 JSON、不要解释。"
            )
            user = f"口播段落：{text}"
            try:
                content, _ = self._chat(system, user, max_tokens=1024, thinking_enabled=False)
                fixed = content.strip()
                if fixed:
                    old_len = cur_len
                    seg["text"] = fixed
                    new_len = _narration_char_count(fixed)
                    excess -= (old_len - new_len)
                    logger.info(
                        "shrunk segment %s: %d -> %d chars (excess remaining: %d)",
                        seg.get("segment_index", _orig_idx), old_len, new_len, excess,
                    )
            except Exception as exc:
                logger.warning("shrink segment %s failed: %s", seg.get("segment_index", _orig_idx), exc)
        # 重新拼接 narration
        seg_texts = [str(s.get("text") or "") for s in segments]
        data["narration"] = "".join(seg_texts)
        data["word_count"] = _narration_char_count(data["narration"])

    def _fix_material_segments(
        self,
        data: dict[str, Any],
        segments: list[dict],
        mode: str,
        timeline: Any,
        chars_per_sec: float,
    ) -> None:
        """对超长/不足的 segments 逐段调 LLM 缩句或扩句，原地修改 data。"""
        from app.services.script.board_timeline import _max_chars_for_duration, slot_min_chars
        for seg in segments:
            idx = int(seg.get("segment_index", 0))
            slot = next((s for s in timeline.slots if s.index == idx), None)
            if not slot:
                continue
            mc = _max_chars_for_duration(slot.duration_sec, chars_per_sec)
            mn = slot_min_chars(mc)
            text = str(seg.get("text") or "")
            if mode == "shrink":
                system = (
                    "将以下口播段落精简缩短，保留核心科普信息与童趣口吻，"
                    f"字数控制在 {mn}-{mc} 字之间（当前 {_narration_char_count(text)} 字）。直输出精简后的段落文本，不要 JSON。"
                )
            else:
                system = (
                    "将以下口播段落扩充写长，补充更多科普细节、比喻或互动感叹，"
                    f"字数达到 {mn}-{mc} 字之间（当前 {_narration_char_count(text)} 字）。直输出扩充后的段落文本，不要 JSON。"
                )
            user = f"口播段落：{text}\n\n该段对应画面：{slot.scene}，{slot.description}"
            try:
                content, _ = self._chat(system, user, max_tokens=1024, thinking_enabled=False)
                fixed = content.strip()
                if fixed:
                    seg["text"] = fixed
            except Exception as exc:
                logger.warning("material segment %s failed for seg %s: %s", mode, idx, exc)

    def generate_material_script(
        self,
        title: str,
        *,
        feedback: str | None = None,
        max_title_length: int | None = None,
        narration_target_words: int | None = None,
        supplementary_info: str | None = None,
        video_timeline: str | None = None,
        job: dict | None = None,
    ) -> dict[str, Any]:
        from app.utils.job_info import resolve_speech_chars_per_sec

        _cps = resolve_speech_chars_per_sec(job.get("script") if job else None) if job else None
        _need_opening = bool(job.get("script", {}).get("need_opening")) if job else False

        min_chars = _min_narration_chars_for_script(
            narration_target_words=narration_target_words,
            video_timeline=video_timeline,
            chars_per_sec=_cps,
        )
        max_chars = narration_accept_max_chars(narration_target_words)
        length_feedback: str | None = feedback
        data: dict[str, Any] | None = None
        for attempt in range(_storyboard_length_max_attempts()):
            raise_if_job_cancelled(job)
            prompts = build_material_script_prompts(
                title,
                feedback=length_feedback,
                max_title_length=max_title_length,
                narration_target_words=narration_target_words,
                supplementary_info=supplementary_info,
                video_timeline=video_timeline,
                chars_per_sec=_cps,
                need_opening=_need_opening,
            )
            data, _ = self._chat_json(prompts["system"], prompts["user"])
            raise_if_job_cancelled(job)
            if "segments" not in data:
                raise ValueError("LLM material script response missing segments")
            for seg in data["segments"]:
                seg.setdefault("visual_mode", "material")
            # 重新拼接 narration 并计算 word_count
            seg_texts = [str(s.get("text") or "") for s in data["segments"]]
            data["narration"] = "".join(seg_texts)
            data["word_count"] = _narration_char_count(data["narration"])
            chars = data["word_count"]
            if chars > max_chars:
                length_feedback = _narration_too_long_feedback(
                    chars,
                    max_chars,
                    prefix=feedback if attempt == 0 and feedback else None,
                )
                logger.warning(
                    "material script narration too long (attempt %d): %d > %d",
                    attempt + 1,
                    chars,
                    max_chars,
                )
                continue
            if chars >= min_chars:
                return data
            length_feedback = _narration_length_feedback(
                chars,
                min_chars,
                prefix=feedback if attempt == 0 and feedback else None,
            )
        if data is not None:
            # 重新拼接 narration 并计算 word_count
            seg_texts = [str(s.get("text") or "") for s in (data.get("segments") or [])]
            data["narration"] = "".join(seg_texts)
            data["word_count"] = _narration_char_count(data["narration"])
            chars = data["word_count"]
            if chars <= max_chars:
                data = self._expand_narration_if_needed(
                    data, min_chars=min_chars, mode="material", job=job
                )
            # 有时间表时，逐段校验预算并扩/缩句
            if video_timeline and data.get("segments"):
                from app.services.script.board_timeline import parse_video_timeline, _max_chars_for_duration, slot_min_chars
                tl = parse_video_timeline(video_timeline, chars_per_sec=_cps)
                if tl and tl.slots:
                    cps = _cps or DEFAULT_SPEECH_CHARS_PER_SEC
                    expand_seg_lst: list[dict] = []
                    shrink_seg_lst: list[dict] = []
                    seg_idx_map: dict[int, dict] = {}
                    for seg in data["segments"]:
                        seg_idx_map[int(seg.get("segment_index", 0))] = seg
                    for slot in tl.slots:
                        seg = seg_idx_map.get(slot.index)
                        if not seg:
                            continue
                        mc = _max_chars_for_duration(slot.duration_sec, cps)
                        mn = slot_min_chars(mc)
                        text = str(seg.get("text") or "")
                        chars_seg = _narration_char_count(text)
                        if chars_seg < mn:
                            expand_seg_lst.append(seg)
                        elif chars_seg > mc:
                            shrink_seg_lst.append(seg)
                    # 缩句（超长段）
                    if shrink_seg_lst:
                        self._fix_material_segments(data, shrink_seg_lst, "shrink", tl, cps)
                    # 扩句（不足段）
                    if expand_seg_lst:
                        self._fix_material_segments(data, expand_seg_lst, "expand", tl, cps)
                    if shrink_seg_lst or expand_seg_lst:
                        seg_texts = [str(s.get("text") or "") for s in (data.get("segments") or [])]
                        data["narration"] = "".join(seg_texts)
                        data["word_count"] = _narration_char_count(data["narration"])
            # 最终兜底：如果总口播仍超长，按长度降序缩句最长段落
            final_chars = _narration_char_count(data.get("narration", ""))
            if final_chars > max_chars:
                logger.warning(
                    "material script still too long after retries (%d > %d), shrinking longest segments",
                    final_chars, max_chars,
                )
                self._shrink_longest_segments_to_fit(data, max_chars)
        raise_if_job_cancelled(job)
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
        raw, _ = self._chat_json(prompts["system"], prompts["user"])
        settings = get_settings()
        max_len = settings.max_title_length if max_title_length is None else max_title_length
        return parse_title_optimize_payload(raw, max_title_len=max_len)

    def generate_video_description(
        self,
        title: str,
        narration: str,
    ) -> str:
        prompts = build_video_description_prompts(title, narration)
        raw, _ = self._chat_json(prompts["system"], prompts["user"], thinking_enabled=False)
        return parse_video_description_payload(raw)

    def rewrite_pixabay_query(
        self,
        query: str,
        *,
        language: str | None = None,
    ) -> str:
        from app.services.clip_search.query_rewrite_prompts import (
            build_pixabay_query_system_prompt,
            build_pixabay_query_user_prompt,
            parse_pixabay_query_payload,
        )

        prompts_system = build_pixabay_query_system_prompt()
        prompts_user = build_pixabay_query_user_prompt(query=query, language=language)
        raw, _ = self._chat_json(prompts_system, prompts_user, max_tokens=256, thinking_enabled=False)
        return parse_pixabay_query_payload(raw)

    def prepare_sd15_image_prompt(
        self,
        prompt: str,
        *,
        size_hint: str | None = None,
        business_override: str | None = None,
    ) -> dict[str, str]:
        from app.services.segment.image.image_sd15 import (
            build_sd15_prompt_system,
            build_sd15_prompt_user,
            parse_image_size,
            parse_sd15_prompt_payload,
        )

        raw, _ = self._chat_json(
            build_sd15_prompt_system(business_override=business_override),
            build_sd15_prompt_user(
                prompt=prompt,
                size_hint=size_hint,
                parse_size=parse_image_size,
            ),
            max_tokens=900,
            thinking_enabled=False,
        )
        return parse_sd15_prompt_payload(
            raw,
            business_override=business_override,
        )

    def generate_topics(
        self,
        theme: str,
        *,
        count: int = 10,
        system_prompt: str | None = None,
        user_prompt: str | None = None,
        category: str | None = None,
        keywords: str | list[str] | None = None,
    ) -> list[dict[str, str]]:
        settings = get_settings()
        count = max(1, min(count, 20))
        system = system_prompt or build_topic_system_prompt(
            max_title_len=settings.max_title_length,
            category=category,
            keywords=keywords,
            count=count,
        )
        user = (
            user_prompt.strip()
            if user_prompt
            else build_topic_user_prompt(
                category=category,
                theme=theme,
                count=count,
                keywords=keywords,
            )
        )
        user_base = user
        last_exc: ValueError | None = None
        max_attempts = 3 if user_prompt else 2
        for attempt in range(max_attempts):
            raw, _ = self._chat_json(system, user)
            try:
                topics = parse_topics_payload(raw, max_title_len=settings.max_title_length)
                return topics[:count]
            except ValueError as exc:
                if not is_topic_parse_retryable(exc):
                    raise
                last_exc = exc
                if attempt + 1 >= max_attempts:
                    break
                feedback = format_topic_parse_feedback(
                    raw,
                    max_title_len=settings.max_title_length,
                )
                retry_extra_parts: list[str] = []
                if any(
                    token in feedback
                    for token in ("问号对话体", "问号后", "须为问号", "半句问法")
                ):
                    retry_extra_parts.append(
                        "【特别强调】title 必须包含中文问号「？」并写完整反驳半句；"
                        "禁止再次输出无问号的陈述句。"
                    )
                if "画面锚点" in feedback:
                    retry_extra_parts.append(
                        "【特别强调】title 须从本题主题提炼可见载体，"
                        "配合图解词（规则、能量、表…）；"
                        "禁止油路、备用道、命脉等抽象比喻。"
                        "但仍须保持「问句？反驳」一整句结构。"
                    )
                retry_extra = "\n".join(retry_extra_parts)
                logger.warning(
                    "[TOPIC] llm retry all entries filtered attempt=%d/%d",
                    attempt + 1,
                    max_attempts,
                )
                user = (
                    f"{user_base}\n\n"
                    "【重试】上一轮输出的标题均未通过规则，请严格按对话反转式重写："
                    "「误区问句？+一步反驳（够你跑路、真以为、压根等，勿句句明明开头）」，"
                    "禁止百科式提问、半句问法、仅语气词收尾。\n"
                    f"{feedback}"
                    + (f"\n{retry_extra}" if retry_extra else "")
                )
        assert last_exc is not None
        raise last_exc

    def generate_daily_script(
        self,
        dialogue_script: dict,
        *,
        job: dict | None = None,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        system, user = build_daily_script_prompts(dialogue_script)
        raw, _ = self._chat_json(
            system, user, max_tokens=4096, thinking_enabled=False, temperature=0.8,
        )
        raise_if_job_cancelled(job)
        elapsed = time.perf_counter() - started
        logger.info(
            "[DAILY_STORY] script done scenes=%d elapsed=%.1fs",
            len(raw.get("scenes") or []),
            elapsed,
        )
        return raw

    def generate_daily_story(
        self,
        theme: str,
    ) -> dict[str, Any]:
        system, user = build_daily_story_prompts(theme)
        raw, _ = self._chat_json(system, user, max_tokens=4096, thinking_enabled=False, temperature=0.95)
        validate_daily_story_json(raw)
        return raw

    def generate_daily_story_themes(
        self,
        count: int = 5,
    ) -> list[str]:
        system, user = build_daily_story_theme_prompts(count)
        content, _ = self._chat(system, user, max_tokens=512, json_mode=False, thinking_enabled=False, temperature=0.95)
        themes = [line.strip() for line in content.strip().split("\n") if line.strip()]
        return themes[:count]
