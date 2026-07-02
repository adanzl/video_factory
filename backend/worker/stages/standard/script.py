from __future__ import annotations

import json
import re
import time

from app.config import get_settings
from app.exceptions import JobStageFailureError
from app.quality.quality_mgr import (
    apply_quality_checks,
    check_board,
    check_image_prompt,
    check_narration,
    detect_narration_repetition,
    merge_quality_report,
    skip_board_check,
    skip_image_prompt_check,
    skip_narration_check,
)
from app.quality.image_prompt import MIN_SD15_PROMPT_EN_WORDS, image_prompt_target_chars
from app.repositories import repo_job_log, repo_job, repo_segment
from app.repositories.connection import connection
from app.services.llm.llm_mgr import llm_mgr
from app.services.script.script_mgr import script_mgr
from app.utils.job_cancel import job_cancel
from app.utils.job_info import (
    content_style_from_job,
    resolve_estimated_duration_min,
    resolve_narration_target_words,
    script_params_from_info,
)
from app.utils.media import (
    assign_segment_timings,
    min_narration_chars_for_target,
    narration_accept_max_chars,
    narration_accept_min_chars,
    NARRATION_ABS_MIN_CHARS,
    narration_soft_min_chars,
    segment_text_char_cap,
    segment_text_hard_cap,
    segment_text_shrink_max,
)
from app.utils.title_text import prefer_source_punctuation
from worker.context import JobContext
from worker.stages.base import StageExecutor

# 低于此字数视为明显过短，不再重试，直接沿用当前文案继续。
MIN_ACCEPT_NARRATION_CHARS = NARRATION_ABS_MIN_CHARS


def _min_narration_chars(narration_target_words: int | None) -> int:
    return min_narration_chars_for_target(narration_target_words)


def _accept_narration_chars(narration_target_words: int) -> int:
    return narration_accept_min_chars(narration_target_words)


_SEGMENT_SHRINK_MAX_ROUNDS = 2


def _narration_retry_min_chars(narration_target_words: int) -> int:
    return int(_min_narration_chars(narration_target_words) * 0.8)


class ScriptValidationError(ValueError, JobStageFailureError):
    def __init__(self, message: str, *, retryable: bool = True) -> None:
        super().__init__(message)
        self.retryable = retryable


def _narration_chars(narration: str) -> int:
    return len(re.sub(r"\s+", "", narration))


def _title_chars(title: str) -> str:
    return re.sub(r"\s+", "", title.strip())


def _resolve_script_title(*, source_title: str, llm_title: str, max_len: int) -> str:
    """原标题未超长则沿用；否则采用 LLM 精简结果。"""
    source = _title_chars(source_title)
    if len(source) <= max_len:
        return source
    candidate = _title_chars(llm_title)
    if not candidate:
        raise ScriptValidationError(
            f"title too long: {len(source)} chars (need <= {max_len})",
            retryable=True,
        )
    if len(candidate) > max_len:
        raise ScriptValidationError(
            f"title too long: {len(candidate)} chars (need <= {max_len})",
            retryable=True,
        )
    return candidate


def _apply_script_title(
    script: dict,
    *,
    source_title: str,
    max_len: int,
    skip_optimize: bool,
    job_id: int,
    stage_name: str,
    content_style: str = "",
) -> None:
    script["title"] = _resolve_script_title(
        source_title=source_title,
        llm_title=str(script.get("title") or ""),
        max_len=max_len,
    )
    if skip_optimize or content_style == "history_mystery":
        return
    # 如果标题已是「事件？嘲讽回应」格式，跳过优化避免改写后半句
    if "？" in script["title"] or "?" in script["title"]:
        if any(kw in script["title"] for kw in ("堆", "等", "笑", "慌", "满", "怕", "够", "管")):
            return
    try:
        optimized_title = llm_mgr.optimize_script_title(
            script["title"],
            script.get("narration", ""),
            max_title_length=max_len,
        )
        script["draft_title"] = script["title"]
        script["title"] = prefer_source_punctuation(
            script["draft_title"],
            _title_chars(optimized_title),
        )
        if len(script["title"]) > max_len:
            raise ScriptValidationError(
                f"optimized title too long: {len(script['title'])} chars (need <= {max_len})"
            )
    except Exception as exc:
        with connection() as conn:
            repo_job_log.append_log(
                conn,
                job_id,
                stage_name,
                f"title optimize failed, keep draft: {exc}",
                level="warning",
            )


def _apply_video_description(
    script: dict,
    *,
    job_id: int,
    stage_name: str,
) -> None:
    title = str(script.get("title") or "").strip()
    narration = str(script.get("narration") or "").strip()
    if not title or not narration:
        return
    try:
        script["video_description"] = llm_mgr.generate_video_description(title, narration)
    except Exception as exc:
        with connection() as conn:
            repo_job_log.append_log(
                conn,
                job_id,
                stage_name,
                f"video description failed: {exc}",
                level="warning",
            )


def _narration_short_feedback(exc: ScriptValidationError, *, min_chars: int) -> str:
    msg = str(exc)
    if "narration too short" not in msg:
        return msg
    return (
        f"{msg}。"
        f"请扩写 narration 至至少 {min_chars} 字（不含空格换行）："
        "各段 text 用「童趣感叹+准确科普点+比喻/拟声/生活联想」三层写法；"
        "先逐段写满 segments，再原样拼接为 narration，最后统计 word_count；"
        "禁止整段仅一句短感叹，禁止先输出短稿再指望后处理。"
    )


def _narration_long_feedback(exc: ScriptValidationError, *, max_chars: int) -> str:
    msg = str(exc)
    if "narration too long" not in msg:
        return msg
    return (
        f"{msg}。"
        f"请删繁就简，将总字数压至 ≤ {max_chars} 字（不含空格换行）："
        "删重复例子、合并并列知识点、缩短每层句子；"
        "总字数靠删内容不靠堆段，禁止加长单段或新增话题；"
        "先写 segments 再拼接 narration，输出前逐段核对字数。"
    )


def _validation_retry_scope(exc: ScriptValidationError) -> str:
    msg = str(exc)
    if "image_prompt too short" in msg:
        return "image_prompts"
    if any(
        key in msg
        for key in (
            "narration too short",
            "narration too long",
            "narration repetition",
            "segment text exceeds",
            "missing visual_brief",
            "text is empty",
            "visual_style is empty",
            "no segments",
        )
    ):
        return "storyboard"
    return "full"


def _log_llm_timing(job_id: int, stage_name: str, script: dict) -> None:
    timing = script.get("_llm_timing")
    if not isinstance(timing, dict):
        return
    parts = []
    if "storyboard_sec" in timing:
        parts.append(f"storyboard={timing['storyboard_sec']}s")
    if "segment_shrink_sec" in timing:
        parts.append(f"segment_shrink={timing['segment_shrink_sec']}s")
    if "image_prompts_sec" in timing:
        batches = timing.get("image_prompt_batches")
        if batches:
            parts.append(
                f"image_prompts={timing['image_prompts_sec']}s({batches} batches)"
            )
        else:
            parts.append(f"image_prompts={timing['image_prompts_sec']}s")
    if not parts:
        return
    with connection() as conn:
        repo_job_log.append_log(
            conn,
            job_id,
            stage_name,
            "llm timing: " + ", ".join(parts),
        )


def _validation_feedback(
    exc: ScriptValidationError,
    *,
    min_chars: int,
    accept_chars: int,
    segment_target_sec: float | None,
    narration_target_words: int,
    content_style: str,
    speech_chars_per_sec: float,
) -> str:
    msg = str(exc)
    if "narration too short" in msg:
        return _narration_short_feedback(exc, min_chars=accept_chars)
    if "narration too long" in msg:
        return _narration_long_feedback(
            exc,
            max_chars=narration_accept_max_chars(narration_target_words),
        )
    if "narration repetition" in msg:
        return (
            f"{msg}。"
            "请删去重复比喻、重复数字对比与重复避震步骤；"
            "相邻两段不得复述同一句或同一意象；"
            "「你看」全文最多 3～4 次，后段换用「其实呀」「关键是」等不同引子；"
            "同一科普点只讲一次，段数多时每段只推进一小步。"
        )
    if segment_target_sec and segment_target_sec > 0:
        if "segment text exceeds" in msg:
            cap = segment_text_char_cap(
                segment_target_sec, chars_per_sec=speech_chars_per_sec
            )
            hard_cap = segment_text_hard_cap(
                segment_target_sec, chars_per_sec=speech_chars_per_sec
            )
            shrink_max = segment_text_shrink_max(
                segment_target_sec, chars_per_sec=speech_chars_per_sec
            )
            return (
                f"{msg}。"
                f"单镜上限 {segment_target_sec}s，每段 text 不得超过 {cap} 字（硬上限 {hard_cap} 字，"
                f"缩字可处理至 {shrink_max} 字）。"
                "超长段须按自然断句拆成多段，禁止少数超长段堆叠。"
                "先写 segments 再拼接 narration，输出前逐段核对字数。"
            )
    return msg


def _narration_short_retryable(chars: int, *, narration_target_words: int) -> bool:
    return chars >= _narration_retry_min_chars(narration_target_words)


def _normalize_segments(segments: list[dict]) -> list[dict]:
    out: list[dict] = []
    for i, seg in enumerate(segments, start=1):
        row = dict(seg)
        if "segment_index" not in row:
            row["segment_index"] = row.get("index", i)
        out.append(row)
    return out


def _sync_narration_from_segments(script: dict) -> None:
    ordered = sorted(
        script.get("segments") or [],
        key=lambda seg: int(seg.get("segment_index") or seg.get("index") or 0),
    )
    script["narration"] = "".join(str(seg.get("text") or "") for seg in ordered)
    script["word_count"] = _narration_chars(script["narration"])


def _classify_segment_overflow(
    segments: list[dict],
    segment_target_sec: float,
    *,
    speech_chars_per_sec: float,
) -> tuple[list[int], list[tuple[int, int]]]:
    """返回 (可缩字分镜序号, 严重超长列表)。"""
    cap = segment_text_char_cap(
        segment_target_sec, chars_per_sec=speech_chars_per_sec
    )
    shrink_max = segment_text_shrink_max(
        segment_target_sec, chars_per_sec=speech_chars_per_sec
    )
    shrinkable: list[int] = []
    severe: list[tuple[int, int]] = []
    for seg in segments:
        chars = _narration_chars(seg.get("text") or "")
        if chars <= cap:
            continue
        idx = int(seg.get("segment_index", -1))
        if chars <= shrink_max:
            shrinkable.append(idx)
        else:
            severe.append((idx, chars))
    return shrinkable, severe


def _repair_segment_overflow_via_shrink(
    script: dict,
    *,
    segment_target_sec: float | None,
    speech_chars_per_sec: float,
    job_id: int,
    stage_name: str,
    job: dict | None,
) -> bool:
    if not segment_target_sec or segment_target_sec <= 0:
        return False
    repaired = False
    cap = segment_text_char_cap(segment_target_sec, chars_per_sec=speech_chars_per_sec)
    for _ in range(_SEGMENT_SHRINK_MAX_ROUNDS):
        shrinkable, severe = _classify_segment_overflow(
            script.get("segments") or [],
            segment_target_sec,
            speech_chars_per_sec=speech_chars_per_sec,
        )
        if severe or not shrinkable:
            break
        llm_mgr.shrink_segment_texts(
            script,
            segment_indices=shrinkable,
            segment_target_sec=segment_target_sec,
            job=job,
        )
        _sync_narration_from_segments(script)
        repaired = True
        with connection() as conn:
            repo_job_log.append_log(
                conn,
                job_id,
                stage_name,
                f"segment shrink: indices={shrinkable}, target<={cap} chars",
                level="info",
            )
        shrinkable_after, severe_after = _classify_segment_overflow(
            script.get("segments") or [],
            segment_target_sec,
            speech_chars_per_sec=speech_chars_per_sec,
        )
        if not shrinkable_after and not severe_after:
            break
        if severe_after:
            break
    return repaired


def _validate_script(
    script: dict,
    *,
    segment_target_sec: float | None = None,
    max_title_length: int | None = None,
    min_narration_chars: int | None = None,
    accept_narration_chars: int | None = None,
    narration_target_words: int | None = None,
    speech_chars_per_sec: float | None = None,
    content_style: str | None = None,
    require_image_prompt: bool = True,
    check_narration: bool = True,
) -> list[str]:
    settings = get_settings()
    seg_target = (
        settings.segment_target_sec if segment_target_sec is None else segment_target_sec
    )
    max_len = settings.max_title_length if max_title_length is None else max_title_length
    hard_floor = (
        _min_narration_chars(None) if min_narration_chars is None else min_narration_chars
    )
    accept_min = accept_narration_chars if accept_narration_chars is not None else hard_floor
    narration = script.get("narration", "")
    segments = script.get("segments") or []
    warnings: list[str] = []
    chars = _narration_chars(narration)
    if check_narration:
        if narration_target_words is not None:
            accept_max = narration_accept_max_chars(narration_target_words)
            if chars > accept_max:
                raise ScriptValidationError(
                    f"narration too long: {chars} chars (need <= {accept_max})",
                    retryable=True,
                )
        if chars >= accept_min:
            pass
        elif narration_target_words is not None and chars >= _narration_retry_min_chars(
            narration_target_words
        ):
            raise ScriptValidationError(
                f"narration too short: {chars} chars (need >= {accept_min})",
                retryable=True,
            )
        elif narration_target_words is not None:
            raise ScriptValidationError(
                f"narration too short: {chars} chars (need >= {accept_min})",
                retryable=chars >= MIN_ACCEPT_NARRATION_CHARS,
            )
        elif narration_target_words is None and chars >= int(hard_floor * 0.8):
            raise ScriptValidationError(
                f"narration too short: {chars} chars (need >= {accept_min})",
                retryable=True,
            )
        elif chars >= narration_soft_min_chars(hard_floor):
            warnings.append(
                f"narration below target ({chars} < {accept_min}), continuing"
            )
        elif chars >= MIN_ACCEPT_NARRATION_CHARS:
            warnings.append(
                f"cannot reach {accept_min} chars ({chars} got), continuing with shorter copy"
            )
        elif chars < MIN_ACCEPT_NARRATION_CHARS:
            raise ScriptValidationError(
                f"narration too short: {chars} chars (need >= {MIN_ACCEPT_NARRATION_CHARS})",
                retryable=False,
            )
        repeat_issue = detect_narration_repetition(narration, segments)
        if repeat_issue:
            raise ScriptValidationError(
                f"narration repetition: {repeat_issue}",
                retryable=True,
            )
    if not segments:
        raise ScriptValidationError("no segments", retryable=False)
    if not (script.get("visual_style") or "").strip():
        raise ScriptValidationError("visual_style is empty", retryable=True)
    for seg in segments:
        if not (seg.get("visual_brief") or "").strip():
            raise ScriptValidationError(
                f"segment {seg.get('segment_index')} missing visual_brief",
                retryable=True,
            )
        if not (seg.get("text") or "").strip():
            raise ScriptValidationError(
                f"segment {seg.get('segment_index')} text is empty",
                retryable=True,
            )
        if require_image_prompt:
            sd15_mode = bool(script.get("include_sd15_prompt"))
            min_prompt_chars = script_mgr.image_prompt_min_chars(sd15_mode=sd15_mode)
            target_prompt_chars = image_prompt_target_chars(sd15_mode=sd15_mode)
            prompt = seg.get("image_prompt") or ""
            prompt_len = len(prompt)
            if prompt_len < min_prompt_chars:
                raise ScriptValidationError(
                    f"segment {seg.get('segment_index')} image_prompt too short: "
                    f"{prompt_len} chars (need >= {min_prompt_chars})",
                    retryable=True,
                )
            if prompt_len < target_prompt_chars:
                warnings.append(
                    f"segment {seg.get('segment_index')} image_prompt slightly short "
                    f"({prompt_len} < {target_prompt_chars}), continuing"
                )
            if sd15_mode and not script_mgr.sd15_prompt_en_ok(seg.get("sd15_prompt_en")):
                words = script_mgr.sd15_prompt_en_word_count(seg.get("sd15_prompt_en"))
                if words > 0:
                    raise ScriptValidationError(
                        f"segment {seg.get('segment_index')} sd15_prompt_en too short "
                        f"({words} words, need >= {MIN_SD15_PROMPT_EN_WORDS})",
                        retryable=True,
                    )
    if seg_target > 0:
        from app.utils.media import DEFAULT_SPEECH_CHARS_PER_SEC

        rate = speech_chars_per_sec or DEFAULT_SPEECH_CHARS_PER_SEC
        cap = segment_text_char_cap(seg_target, chars_per_sec=rate)
        hard_cap = segment_text_hard_cap(seg_target, chars_per_sec=rate)
        shrink_max = segment_text_shrink_max(seg_target, chars_per_sec=rate)
        overflow: list[tuple[int, int]] = []
        for seg in segments:
            seg_chars = _narration_chars(seg.get("text") or "")
            if seg_chars > hard_cap:
                overflow.append((seg.get("segment_index", -1), seg_chars))
        if overflow:
            raise ScriptValidationError(
                f"segment text exceeds {seg_target}s cap (~{cap} chars, "
                f"shrink up to {shrink_max}): {overflow}",
                retryable=True,
            )
    title = _title_chars(script.get("title") or "")
    if not title:
        raise ScriptValidationError("title is empty")
    if len(title) > max_len:
        raise ScriptValidationError(
            f"title too long: {len(title)} chars (need <= {max_len})"
        )
    script["title"] = title
    script["segments"] = _normalize_segments(segments)
    return warnings


def _strip_image_prompt_fields(script: dict) -> None:
    for seg in script.get("segments") or []:
        seg.pop("image_prompt", None)
        seg.pop("motion_prompt", None)


class ScriptStage(StageExecutor):
    name = "script"

    def run(self, ctx: JobContext) -> None:
        started = time.perf_counter()
        title = ctx.job["title"]
        segment_target_sec = ctx.script_segment_target_sec
        max_title_length = ctx.script_max_title_length
        narration_target_words = ctx.script_narration_target_words
        speech_chars_per_sec = ctx.script_speech_chars_per_sec
        supplementary_info = (
            ctx.script_supplementary_info.strip()
            if ctx.script_supplementary_info and ctx.script_supplementary_info.strip()
            else None
        )
        saved_script = script_params_from_info(ctx.job.get("info"))
        content_style = content_style_from_job(ctx.job)
        if narration_target_words is None:
            narration_target_words = resolve_narration_target_words(
                saved_script,
                content_style=content_style,
            )
            estimated_min = resolve_estimated_duration_min(
                saved_script,
                content_style=content_style,
            )
            with connection() as conn:
                repo_job_log.append_log(
                    conn,
                    ctx.job["id"],
                    self.name,
                    f"auto narration target: {narration_target_words} chars "
                    f"(estimated_duration_min={estimated_min})",
                )
        min_narration_chars = _min_narration_chars(narration_target_words)
        accept_narration_chars = _accept_narration_chars(narration_target_words)
        last_exc: Exception | None = None
        script: dict | None = None
        feedback: str | None = None
        retry_scope: str | None = None
        accept_warnings: list[str] = []
        generate_image_prompts = bool(ctx.script_generate_image_prompts)
        job_id = ctx.job["id"]
        max_attempts = get_settings().script_qa_max_attempts
        for attempt in range(max_attempts):
            job_cancel.raise_if_cancelled(job_id)
            script = llm_mgr.generate_script(
                title,
                feedback=feedback,
                segment_target_sec=segment_target_sec,
                max_title_length=max_title_length,
                narration_target_words=narration_target_words,
                supplementary_info=supplementary_info,
                job=ctx.job,
                existing_script=script,
                retry_scope=retry_scope,
                generate_image_prompts=False,
            )
            job_cancel.raise_if_cancelled(job_id)
            _log_llm_timing(ctx.job["id"], self.name, script)
            _repair_segment_overflow_via_shrink(
                script,
                segment_target_sec=segment_target_sec,
                speech_chars_per_sec=speech_chars_per_sec,
                job_id=job_id,
                stage_name=self.name,
                job=ctx.job,
            )
            try:
                accept_warnings = _validate_script(
                    script,
                    segment_target_sec=segment_target_sec,
                    max_title_length=max_title_length,
                    min_narration_chars=min_narration_chars,
                    accept_narration_chars=accept_narration_chars,
                    narration_target_words=narration_target_words,
                    speech_chars_per_sec=speech_chars_per_sec,
                    content_style=content_style,
                    require_image_prompt=False,
                )
                break
            except ScriptValidationError as exc:
                last_exc = exc
                retry_scope = _validation_retry_scope(exc)
                feedback = _validation_feedback(
                    exc,
                    min_chars=min_narration_chars,
                    accept_chars=accept_narration_chars,
                    segment_target_sec=segment_target_sec,
                    narration_target_words=narration_target_words,
                    content_style=content_style,
                    speech_chars_per_sec=speech_chars_per_sec,
                )
                script = None
                with connection() as conn:
                    repo_job_log.append_log(
                        conn,
                        ctx.job["id"],
                        self.name,
                        f"script rejected (attempt {attempt + 1}, retry={retry_scope}): {exc}",
                        level="warning",
                    )
        if script is None:
            raise last_exc or RuntimeError("script generation failed")

        if generate_image_prompts:
            from app.utils.job_info import resolve_include_sd15_prompt

            use_sd15 = resolve_include_sd15_prompt(ctx.job)
            script["include_sd15_prompt"] = use_sd15
            prompt_feedback: str | None = None
            prompt_max_attempts = get_settings().script_qa_max_attempts
            for attempt in range(prompt_max_attempts):
                job_cancel.raise_if_cancelled(job_id)
                try:
                    if attempt == 0:
                        llm_mgr.fill_image_prompts(
                            script,
                            supplementary_info=supplementary_info,
                            job=ctx.job,
                            include_sd15_prompt=use_sd15,
                        )
                    else:
                        llm_mgr.generate_script(
                            title,
                            feedback=prompt_feedback,
                            supplementary_info=supplementary_info,
                            job=ctx.job,
                            existing_script=script,
                            retry_scope="image_prompts",
                            generate_image_prompts=True,
                            include_sd15_prompt=use_sd15,
                        )
                    _validate_script(
                        script,
                        segment_target_sec=segment_target_sec,
                        max_title_length=max_title_length,
                        min_narration_chars=min_narration_chars,
                        accept_narration_chars=accept_narration_chars,
                        narration_target_words=narration_target_words,
                        speech_chars_per_sec=speech_chars_per_sec,
                        content_style=content_style,
                        require_image_prompt=True,
                        check_narration=False,
                    )
                    break
                except ScriptValidationError as exc:
                    last_exc = exc
                    if "image_prompt" not in str(exc):
                        raise
                    prompt_feedback = str(exc)
                    with connection() as conn:
                        repo_job_log.append_log(
                            conn,
                            ctx.job["id"],
                            self.name,
                            f"image_prompt rejected (attempt {attempt + 1}): {exc}",
                            level="warning",
                        )
            else:
                raise last_exc or RuntimeError("image prompt generation failed")

        max_len = (
            max_title_length
            if max_title_length is not None
            else get_settings().max_title_length
        )
        _apply_script_title(
            script,
            source_title=title,
            max_len=max_len,
            skip_optimize=bool(ctx.script_skip_title_optimize),
            job_id=ctx.job["id"],
            stage_name=self.name,
            content_style=content_style_from_job(ctx.job),
        )
        _apply_video_description(
            script,
            job_id=ctx.job["id"],
            stage_name=self.name,
        )

        script_mgr.attach_prompts(
            script,
            ctx.job,
            title,
            segment_target_sec=segment_target_sec,
            max_title_length=max_title_length,
            narration_target_words=narration_target_words,
            supplementary_info=supplementary_info,
            skip_title_optimize=bool(ctx.script_skip_title_optimize),
        )

        resolved_seg_target = (
            segment_target_sec
            if segment_target_sec is not None
            else get_settings().segment_target_sec
        )
        from app.utils.media import assign_segment_timings

        assign_segment_timings(
            script,
            segment_target_sec=resolved_seg_target,
            chars_per_sec=speech_chars_per_sec,
        )

        if supplementary_info:
            script["supplementary_info"] = supplementary_info
        else:
            script.pop("supplementary_info", None)

        script["word_count"] = _narration_chars(script.get("narration", ""))
        script["narration_target_words"] = narration_target_words
        script["speech_chars_per_sec"] = speech_chars_per_sec
        script["segment_target_sec"] = resolved_seg_target
        script["max_title_length"] = max_len
        script["generate_image_prompts"] = generate_image_prompts
        assign_segment_timings(
            script,
            segment_target_sec=resolved_seg_target,
            chars_per_sec=speech_chars_per_sec,
        )
        if not generate_image_prompts:
            _strip_image_prompt_fields(script)
        script.pop("_llm_timing", None)
        script["cost_time"] = round(time.perf_counter() - started, 1)
        display_title = script["title"]
        job_cancel.raise_if_cancelled(job_id)
        with connection() as conn:
            for warning in accept_warnings:
                repo_job_log.append_log(
                    conn,
                    ctx.job["id"],
                    self.name,
                    warning,
                    level="warning",
                )
            repo_job.update_job(
                conn,
                ctx.job["id"],
                title=display_title,
                script_json=script,
            )
            repo_segment.insert_segments(conn, ctx.job["id"], script["segments"])
            repo_job_log.append_log(
                conn,
                ctx.job["id"],
                self.name,
                f"script ready, segments={len(script['segments'])}, "
                f"words={script['word_count']}, "
                f"title={script['title']}, "
                f"cost_time={script['cost_time']}s",
            )
            repo_job_log.append_log(
                conn,
                ctx.job["id"],
                self.name,
                f"script_json={json.dumps(script, ensure_ascii=False, default=str)}",
            )
            if get_settings().skip_script_quality_check:
                merged = merge_quality_report(
                    ctx.job.get("quality_report"),
                    "copy",
                    skip_narration_check(),
                )
                merged = merge_quality_report(merged, "storyboard", skip_board_check())
                merged = merge_quality_report(
                    merged,
                    "image_prompts",
                    skip_image_prompt_check(),
                )
                repo_job_log.append_log(
                    conn,
                    ctx.job["id"],
                    self.name,
                    "script quality checks skipped (SKIP_SCRIPT_QUALITY_CHECK)",
                    level="warning",
                )
                repo_job.update_job(conn, ctx.job["id"], quality_report=merged)
            else:
                apply_quality_checks(
                    conn,
                    ctx.job["id"],
                    self.name,
                    {
                        "copy": check_narration(script),
                        "storyboard": check_board(
                            script,
                            segment_target_sec=segment_target_sec,
                            max_title_length=max_len,
                        ),
                        "image_prompts": (
                            check_image_prompt(script)
                            if generate_image_prompts
                            else skip_image_prompt_check()
                        ),
                    },
                    existing_report=ctx.job.get("quality_report"),
                )
