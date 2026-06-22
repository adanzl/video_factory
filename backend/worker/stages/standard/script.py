from __future__ import annotations

import re
import time

from app.config import get_settings
from app.quality.checkers import (
    check_copy,
    check_image_prompts,
    check_storyboard,
    skipped_image_prompts_check,
)
from app.quality.gate import apply_quality_checks
from app.repositories import job_log_repo, job_repo, segment_repo
from app.repositories.connection import connection
from app.services.llm.llm_mgr import llm_mgr
from app.services.llm.llm_script_prompts import IMAGE_PROMPT_TARGET_CHARS, MIN_IMAGE_PROMPT_CHARS
from app.utils.job_info import content_style_from_job
from app.utils.media import (
    default_narration_target_words,
    min_narration_chars_for_target,
    narration_accept_min_chars,
    narration_soft_min_chars,
    segment_text_char_cap,
)
from worker.context import JobContext
from worker.stages.base import StageExecutor

# 低于此比例视为「主题撑不满」，不再重试，直接沿用当前文案继续。
MIN_ACCEPT_NARRATION_CHARS = 200


def _min_narration_chars(narration_target_words: int | None) -> int:
    return min_narration_chars_for_target(narration_target_words)


def _accept_narration_chars(narration_target_words: int) -> int:
    return narration_accept_min_chars(narration_target_words)


def _narration_retry_min_chars(narration_target_words: int) -> int:
    return int(_min_narration_chars(narration_target_words) * 0.8)


class ScriptValidationError(ValueError):
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
) -> None:
    script["title"] = _resolve_script_title(
        source_title=source_title,
        llm_title=str(script.get("title") or ""),
        max_len=max_len,
    )
    if skip_optimize:
        return
    try:
        optimized_title = llm_mgr.optimize_script_title(
            script["title"],
            script.get("narration", ""),
            max_title_length=max_len,
        )
        script["draft_title"] = script["title"]
        script["title"] = _title_chars(optimized_title)
        if len(script["title"]) > max_len:
            raise ScriptValidationError(
                f"optimized title too long: {len(script['title'])} chars (need <= {max_len})"
            )
    except Exception as exc:
        with connection() as conn:
            job_log_repo.append_log(
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
            job_log_repo.append_log(
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


def _validation_retry_scope(exc: ScriptValidationError) -> str:
    msg = str(exc)
    if "image_prompt too short" in msg:
        return "image_prompts"
    if any(
        key in msg
        for key in (
            "narration too short",
            "segment text exceeds",
            "too few segments",
            "missing visual_brief",
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
        job_log_repo.append_log(
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
) -> str:
    msg = str(exc)
    if "narration too short" in msg:
        return _narration_short_feedback(exc, min_chars=accept_chars)
    if segment_target_sec and segment_target_sec > 0:
        if "segment text exceeds" in msg or "too few segments" in msg:
            cap = segment_text_char_cap(segment_target_sec)
            hard_cap = int(cap * 1.15)
            needed = max(1, (narration_target_words + cap - 1) // cap)
            return (
                f"{msg}。"
                f"单镜上限 {segment_target_sec}s，每段 text 不得超过 {cap} 字（硬上限 {hard_cap} 字）。"
                f"口播目标 {narration_target_words} 字须至少拆成 {needed} 段；"
                "超长段必须按自然断句拆成多段，禁止 3～5 个长段堆叠。"
                "先规划段数与每段字数，再写 segments，最后拼接 narration。"
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


def _validate_script(
    script: dict,
    *,
    segment_target_sec: float | None = None,
    max_title_length: int | None = None,
    min_narration_chars: int | None = None,
    accept_narration_chars: int | None = None,
    narration_target_words: int | None = None,
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
        if chars >= accept_min:
            pass
        elif narration_target_words is not None and chars >= _narration_retry_min_chars(
            narration_target_words
        ):
            raise ScriptValidationError(
                f"narration too short: {chars} chars (need >= {accept_min})",
                retryable=True,
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
        if require_image_prompt:
            prompt = seg.get("image_prompt") or ""
            prompt_len = len(prompt)
            if prompt_len < MIN_IMAGE_PROMPT_CHARS:
                raise ScriptValidationError(
                    f"segment {seg.get('segment_index')} image_prompt too short: "
                    f"{prompt_len} chars (need >= {MIN_IMAGE_PROMPT_CHARS})",
                    retryable=True,
                )
            if prompt_len < IMAGE_PROMPT_TARGET_CHARS:
                warnings.append(
                    f"segment {seg.get('segment_index')} image_prompt slightly short "
                    f"({prompt_len} < {IMAGE_PROMPT_TARGET_CHARS}), continuing"
                )
    if seg_target > 0:
        cap = segment_text_char_cap(seg_target)
        hard_cap = int(cap * 1.15)
        overflow: list[tuple[int, int]] = []
        for seg in segments:
            seg_chars = _narration_chars(seg.get("text") or "")
            if seg_chars > hard_cap:
                overflow.append((seg.get("segment_index", -1), seg_chars))
        if overflow:
            raise ScriptValidationError(
                f"segment text exceeds {seg_target}s cap (~{cap} chars): "
                f"{overflow}",
                retryable=True,
            )
        needed = max(1, (narration_target_words + cap - 1) // cap) if narration_target_words else max(1, (chars + cap - 1) // cap)
        if len(segments) < needed:
            raise ScriptValidationError(
                f"too few segments: {len(segments)} (need >= {needed} for "
                f"{seg_target}s/segment cap, target {narration_target_words or chars} chars narration)",
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
        supplementary_info = (
            ctx.script_supplementary_info.strip()
            if ctx.script_supplementary_info and ctx.script_supplementary_info.strip()
            else None
        )
        if narration_target_words is None:
            narration_target_words = default_narration_target_words()
            with connection() as conn:
                job_log_repo.append_log(
                    conn,
                    ctx.job["id"],
                    self.name,
                    f"auto narration target: {narration_target_words} chars "
                    f"(from target_final={get_settings().target_final_duration_sec}s)",
                )
        min_narration_chars = _min_narration_chars(narration_target_words)
        accept_narration_chars = _accept_narration_chars(narration_target_words)
        content_style = content_style_from_job(ctx.job)
        last_exc: Exception | None = None
        script: dict | None = None
        feedback: str | None = None
        retry_scope: str | None = None
        accept_warnings: list[str] = []
        generate_image_prompts = bool(ctx.script_generate_image_prompts)
        for attempt in range(6):
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
            _log_llm_timing(ctx.job["id"], self.name, script)
            try:
                accept_warnings = _validate_script(
                    script,
                    segment_target_sec=segment_target_sec,
                    max_title_length=max_title_length,
                    min_narration_chars=min_narration_chars,
                    accept_narration_chars=accept_narration_chars,
                    narration_target_words=narration_target_words,
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
                )
                script = None
                with connection() as conn:
                    job_log_repo.append_log(
                        conn,
                        ctx.job["id"],
                        self.name,
                        f"script rejected (attempt {attempt + 1}, retry={retry_scope}): {exc}",
                        level="warning",
                    )
        if script is None:
            raise last_exc or RuntimeError("script generation failed")

        if generate_image_prompts:
            prompt_feedback: str | None = None
            for attempt in range(4):
                try:
                    if attempt == 0:
                        llm_mgr.fill_image_prompts(
                            script,
                            supplementary_info=supplementary_info,
                            job=ctx.job,
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
                        )
                    _validate_script(
                        script,
                        segment_target_sec=segment_target_sec,
                        max_title_length=max_title_length,
                        min_narration_chars=min_narration_chars,
                        accept_narration_chars=accept_narration_chars,
                        narration_target_words=narration_target_words,
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
                        job_log_repo.append_log(
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
        )
        _apply_video_description(
            script,
            job_id=ctx.job["id"],
            stage_name=self.name,
        )

        from app.services.llm.llm_script_prompts import attach_llm_prompts_to_script

        attach_llm_prompts_to_script(
            script,
            ctx.job,
            title,
            segment_target_sec=segment_target_sec,
            max_title_length=max_title_length,
            narration_target_words=narration_target_words,
            supplementary_info=supplementary_info,
            skip_title_optimize=bool(ctx.script_skip_title_optimize),
        )

        if supplementary_info:
            script["supplementary_info"] = supplementary_info
        else:
            script.pop("supplementary_info", None)

        script["word_count"] = _narration_chars(script.get("narration", ""))
        script["narration_target_words"] = narration_target_words
        resolved_seg_target = (
            segment_target_sec
            if segment_target_sec is not None
            else get_settings().segment_target_sec
        )
        script["segment_target_sec"] = resolved_seg_target
        script["max_title_length"] = max_len
        script["generate_image_prompts"] = generate_image_prompts
        if not generate_image_prompts:
            _strip_image_prompt_fields(script)
        script.pop("_llm_timing", None)
        script["cost_time"] = round(time.perf_counter() - started, 1)
        display_title = script["title"]
        with connection() as conn:
            for warning in accept_warnings:
                job_log_repo.append_log(
                    conn,
                    ctx.job["id"],
                    self.name,
                    warning,
                    level="warning",
                )
            job_repo.update_job(
                conn,
                ctx.job["id"],
                title=display_title,
                script_json=script,
            )
            segment_repo.insert_segments(conn, ctx.job["id"], script["segments"])
            job_log_repo.append_log(
                conn,
                ctx.job["id"],
                self.name,
                f"script ready, segments={len(script['segments'])}, "
                f"words={script['word_count']}, "
                f"title={script['title']}, "
                f"cost_time={script['cost_time']}s",
            )
            apply_quality_checks(
                conn,
                ctx.job["id"],
                self.name,
                {
                    "copy": check_copy(script),
                    "storyboard": check_storyboard(
                        script,
                        segment_target_sec=segment_target_sec,
                        max_title_length=max_len,
                    ),
                    "image_prompts": (
                        check_image_prompts(script)
                        if generate_image_prompts
                        else skipped_image_prompts_check()
                    ),
                },
                existing_report=ctx.job.get("quality_report"),
            )
