from __future__ import annotations

import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from app.config import get_settings
from app.services.llm.deepseek_request import build_deepseek_chat_payload
from app.services.llm.llm_mgr import LLMClient
from app.services.llm.llm_script_description import parse_video_description_payload
from app.services.llm.llm_script_prompts import (
    MIN_IMAGE_PROMPT_CHARS,
    IMAGE_PROMPT_TARGET_CHARS,
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
from app.utils.media import (
    default_narration_target_words,
    min_narration_chars_for_target,
    narration_accept_min_chars,
    narration_writing_plan,
    storyboard_compact_output,
)

__all__ = ["DeepSeekClient", "MIN_IMAGE_PROMPT_CHARS"]

logger = logging.getLogger(__name__)

_NARRATION_LENGTH_RETRY_ATTEMPTS = 5
_NARRATION_EXPAND_ATTEMPTS = 2
_TRUNCATION_RETRY_ATTEMPTS = 3


def _narration_char_count(text: str) -> int:
    return len(re.sub(r"\s+", "", text or ""))


def _narration_length_feedback(
    chars: int,
    min_chars: int,
    *,
    prefix: str | None = None,
    plan: dict[str, int] | None = None,
    seg_count: int | None = None,
) -> str:
    deficit = max(1, min_chars - chars)
    parts = [
        f"narration 仅 {chars} 字，验收下限 {min_chars} 字，还差 {deficit} 字。",
    ]
    if plan and seg_count is not None and seg_count < plan["seg_count_min"]:
        need = plan["seg_count_min"] - seg_count
        parts.insert(
            0,
            f"segments 仅 {seg_count} 段，须至少 {plan['seg_count_min']} 段（还差 {need} 段）；"
            f"每段 text 至少 {plan['per_seg_min']} 字。",
        )
    parts.append(
        "请增加 segments 段数并扩写每段 text（每层补具体细节/案例/步骤），"
        "先写 segments 再拼接 narration，核对 word_count 后再输出 JSON。"
    )
    msg = "".join(parts)
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
    return narration_accept_min_chars(target)


def _storyboard_max_tokens(
    narration_target_words: int | None,
    *,
    compact: bool,
) -> int:
    """分镜 JSON 输出 token 预算（受 DEEPSEEK_MAX_TOKENS 上限约束）。"""
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
        for variant in (candidate, _escape_control_chars_in_json_strings(candidate)):
            try:
                parsed = json.loads(variant)
            except json.JSONDecodeError as exc:
                last_exc = exc
                continue
            if isinstance(parsed, dict):
                return parsed
    raise ValueError(f"LLM returned invalid JSON: {last_exc}") from last_exc


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


def _truncation_feedback(*, compact: bool) -> str:
    if compact:
        return (
            "上次 JSON 输出被截断（token 用尽）。"
            "务必省略 narration/word_count，只输出 title、visual_style、segments；"
            "每段 visual_brief 严格 30-50 字，确保 JSON 完整闭合。"
        )
    return (
        "上次 JSON 输出被截断（token 用尽）。"
        "请省略 narration/word_count 字段，只写 segments 内 text 与 visual_brief（每段 brief≤50字），"
        "后端会自动拼接 narration。"
    )


def _empty_json_feedback() -> str:
    return (
        "上次 JSON Output 返回了空 content（DeepSeek 已知偶发问题，见官方 JSON Output 文档）。"
        "请严格按 system 中的 JSON 样例输出完整对象，不要 markdown 代码块或解释文字。"
    )


def _parse_failure_feedback(exc: ValueError, *, compact: bool) -> str:
    msg = str(exc)
    if "empty response" in msg:
        return _empty_json_feedback()
    if "invalid JSON" in msg:
        return (
            "上次返回的不是合法 JSON。"
            "请严格按 JSON 样例输出，确保括号闭合，不要 markdown 代码块。"
        )
    return _truncation_feedback(compact=compact)


def _chunk_indices(indices: list[int], batch_size: int) -> list[list[int]]:
    size = max(1, batch_size)
    ordered = sorted({int(idx) for idx in indices})
    return [ordered[i : i + size] for i in range(0, len(ordered), size)]


def _short_image_prompt_indices(script: dict[str, Any]) -> list[int]:
    return [
        int(seg["segment_index"])
        for seg in script.get("segments") or []
        if len(str(seg.get("image_prompt") or "")) < IMAGE_PROMPT_TARGET_CHARS
    ]


class DeepSeekClient(LLMClient):
    def __init__(self) -> None:
        import requests

        self._requests = requests
        settings = get_settings()
        self._api_key = settings.deepseek_api_key
        self._base_url = settings.deepseek_base_url.rstrip("/")
        self._model = settings.deepseek_model

    def _chat(self, system: str, user: str, *, max_tokens: int | None = None) -> tuple[str, str | None]:
        settings = get_settings()
        limit = settings.deepseek_max_tokens if max_tokens is None else max_tokens
        resp = self._requests.post(
            f"{self._base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            json=build_deepseek_chat_payload(
                model=self._model,
                system=system,
                user=user,
                max_tokens=limit,
                thinking_enabled=settings.deepseek_thinking_enabled,
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
    ) -> tuple[dict[str, Any], str | None]:
        content, finish = self._chat(system, user, max_tokens=max_tokens)
        if not content.strip():
            raise ValueError("LLM returned empty response")
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
    ) -> dict[str, Any]:
        chars = _narration_char_count(str(data.get("narration") or ""))
        if chars >= min_chars or chars < int(min_chars * 0.5):
            return data
        current = data
        segments = current.get("segments") or []
        default_mode = segments[0].get("visual_mode", "static_motion") if segments else "static_motion"
        for _ in range(_NARRATION_EXPAND_ATTEMPTS):
            prompts = build_narration_expand_prompts(current, min_chars=min_chars, mode=mode)
            expanded, _ = self._chat_json(prompts["system"], prompts["user"])
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
        seg_target = (
            get_settings().segment_target_sec
            if segment_target_sec is None
            else segment_target_sec
        )
        target_words = narration_target_words or default_narration_target_words()
        compact = storyboard_compact_output(target_words, seg_target)
        max_tokens = _storyboard_max_tokens(narration_target_words, compact=compact)
        length_feedback: str | None = feedback
        data: dict[str, Any] | None = None
        truncation_attempts = 0
        for attempt in range(_NARRATION_LENGTH_RETRY_ATTEMPTS):
            prompts = build_storyboard_prompts(
                title,
                feedback=length_feedback,
                segment_target_sec=segment_target_sec,
                max_title_length=max_title_length,
                narration_target_words=narration_target_words,
                supplementary_info=supplementary_info,
                job=job,
                compact_output=compact,
            )
            try:
                data, finish = self._chat_json(
                    prompts["system"],
                    prompts["user"],
                    max_tokens=max_tokens,
                )
            except ValueError as exc:
                truncation_attempts += 1
                if truncation_attempts > _TRUNCATION_RETRY_ATTEMPTS:
                    raise
                compact = True
                max_tokens = get_settings().deepseek_max_tokens
                length_feedback = _parse_failure_feedback(exc, compact=compact)
                if feedback and truncation_attempts == 1:
                    length_feedback = f"{feedback}\n{length_feedback}"
                logger.warning("storyboard parse failed (attempt %d): %s", truncation_attempts, exc)
                continue
            if finish == "length":
                truncation_attempts += 1
                if truncation_attempts > _TRUNCATION_RETRY_ATTEMPTS:
                    raise ValueError("LLM storyboard response truncated after retries")
                compact = True
                max_tokens = get_settings().deepseek_max_tokens
                length_feedback = _truncation_feedback(compact=True)
                if feedback and truncation_attempts == 1:
                    length_feedback = f"{feedback}\n{length_feedback}"
                data = None
                continue
            data = _assemble_storyboard_narration(data)
            if "segments" not in data:
                raise ValueError("LLM storyboard response missing segments")
            if not data.get("visual_style"):
                raise ValueError("LLM storyboard response missing visual_style")
            plan = narration_writing_plan(target_words, seg_target)
            seg_count = len(data.get("segments") or [])
            chars = _narration_char_count(str(data.get("narration") or ""))
            if chars >= min_chars and seg_count >= plan["seg_count_min"]:
                return data
            length_feedback = _narration_length_feedback(
                chars,
                min_chars,
                prefix=feedback if attempt == 0 and feedback else None,
                plan=plan,
                seg_count=seg_count,
            )
        if data is not None:
            data = _assemble_storyboard_narration(data)
            data = self._expand_narration_if_needed(data, min_chars=min_chars, mode="storyboard")
            data = _assemble_storyboard_narration(data)
        return data

    def _generate_image_prompts(
        self,
        script: dict[str, Any],
        *,
        feedback: str | None = None,
        supplementary_info: str | None = None,
        job: dict | None = None,
        segment_indices: list[int] | None = None,
    ) -> dict[str, Any]:
        prompts = build_image_prompts_prompts(
            script,
            feedback=feedback,
            supplementary_info=supplementary_info,
            job=job,
            segment_indices=segment_indices,
        )
        raw, _ = self._chat_json(prompts["system"], prompts["user"])
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

    def fill_image_prompts(
        self,
        script: dict[str, Any],
        *,
        feedback: str | None = None,
        supplementary_info: str | None = None,
        job: dict | None = None,
        segment_indices: list[int] | None = None,
    ) -> dict[str, Any]:
        settings = get_settings()
        segments = script.get("segments") or []
        if not segments:
            raise ValueError("script has no segments")
        all_indices = segment_indices or [int(seg["segment_index"]) for seg in segments]
        batches = _chunk_indices(all_indices, settings.llm_image_prompt_batch_size)
        started = time.perf_counter()

        def _run_batch(batch_indices: list[int]) -> list[dict]:
            result = self._generate_image_prompts(
                script,
                feedback=feedback,
                supplementary_info=supplementary_info,
                job=job,
                segment_indices=batch_indices,
            )
            return result["image_prompts"]

        prompt_items: list[dict] = []
        if len(batches) <= 1:
            prompt_items = _run_batch(batches[0])
        else:
            with ThreadPoolExecutor(max_workers=len(batches)) as pool:
                futures = {pool.submit(_run_batch, batch): batch for batch in batches}
                for future in as_completed(futures):
                    prompt_items.extend(future.result())

        self._merge_image_prompts(script, prompt_items, required_indices=all_indices)
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
    ) -> dict[str, Any]:
        prompt_feedback = feedback
        target_indices = segment_indices
        for attempt in range(4):
            self.fill_image_prompts(
                script,
                feedback=prompt_feedback,
                supplementary_info=supplementary_info,
                job=job,
                segment_indices=target_indices,
            )
            short = _short_image_prompt_indices(script)
            if not short:
                return script
            target_indices = short
            prompt_feedback = (
                f"image_prompt too short: {short}; "
                f"need >={IMAGE_PROMPT_TARGET_CHARS} chars each; "
                "expand all six layers (composition, subject, environment, lighting, color, scope)"
            )
            logger.warning(
                "[SCRIPT] image_prompt retry attempt=%d short=%s",
                attempt + 1,
                short,
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
    ) -> dict[str, Any]:
        if retry_scope == "image_prompts" and existing_script is not None:
            data = existing_script
            self._fill_image_prompts_with_retries(
                data,
                supplementary_info=supplementary_info,
                job=job,
                feedback=feedback,
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
            data, _ = self._chat_json(prompts["system"], prompts["user"])
            if "segments" not in data:
                raise ValueError("LLM material script response missing segments")
            for seg in data["segments"]:
                seg.setdefault("visual_mode", "material")
            chars = _narration_char_count(str(data.get("narration") or ""))
            seg_count = len(data.get("segments") or [])
            plan: dict[str, int] | None = None
            if not video_timeline:
                target = narration_target_words or 800
                plan = narration_writing_plan(target, 0)
            seg_ok = plan is None or seg_count >= plan["seg_count_min"]
            if chars >= min_chars and seg_ok:
                return data
            length_feedback = _narration_length_feedback(
                chars,
                min_chars,
                prefix=feedback if attempt == 0 and feedback else None,
                plan=plan,
                seg_count=seg_count,
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
        raw, _ = self._chat_json(prompts["system"], prompts["user"])
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
        raw, _ = self._chat_json(prompts_system, prompts_user, max_tokens=256)
        return parse_pixabay_query_payload(raw)

    def prepare_sd15_image_prompt(
        self,
        prompt: str,
        *,
        size_hint: str | None = None,
        business_override: str | None = None,
    ) -> dict[str, str]:
        from app.services.llm.llm_sd15_prompt import (
            build_sd15_prompt_system,
            build_sd15_prompt_user,
            parse_sd15_prompt_payload,
        )
        from app.services.visual.image_sd15 import parse_image_size

        raw, _ = self._chat_json(
            build_sd15_prompt_system(business_override=business_override),
            build_sd15_prompt_user(
                prompt=prompt,
                size_hint=size_hint,
                parse_size=parse_image_size,
            ),
            max_tokens=512,
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
    ) -> list[dict[str, str]]:
        settings = get_settings()
        count = max(1, min(count, 20))
        system = system_prompt or build_topic_system_prompt(max_title_len=settings.max_title_length)
        user = user_prompt.strip() if user_prompt else build_topic_user_prompt(theme=theme, count=count)
        raw, _ = self._chat_json(system, user)
        topics = parse_topics_payload(raw, max_title_len=settings.max_title_length)
        return topics[:count]
