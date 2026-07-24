"""质检统一入口。

子模块按流水线阶段划分：
- ``script`` — 口播 + 分镜
- ``image_prompt`` — 文生图提示词（含阈值）
- ``tts_audio`` — 配音
- ``segment`` — 出图 + clip
- ``final_video`` — 成片
"""
from __future__ import annotations
import logging
from app.exceptions import JobStageFailureError
from app.quality import final_video, image_prompt, script, segment, tts_audio
from app.quality.models import QualityReport, QualityStep
from app.repositories import repo_job_log, repo_job
logger = logging.getLogger(__name__)
__all__ = ['QualityMgr', 'QualityReport', 'QualityStep', 'apply_quality_checks', 'check_board', 'check_image_prompt', 'check_merged_video', 'check_narration', 'check_segment_clips', 'check_segment_images', 'check_tts_audio', 'detect_memoir_narration', 'detect_narration_repetition', 'format_quality_log_message', 'merge_quality_report', 'quality_mgr', 'skip_board_check', 'skip_image_prompt_check', 'skip_narration_check']
check_narration = script.check_narration
detect_memoir_narration = script.detect_memoir_narration
detect_narration_repetition = script.detect_narration_repetition
skip_narration_check = script.skip_narration_check
check_board = script.check_board
skip_board_check = script.skip_board_check
check_image_prompt = image_prompt.check_image_prompt
skip_image_prompt_check = image_prompt.skip_image_prompt_check
check_tts_audio = tts_audio.check_tts_audio
check_segment_images = segment.check_segment_images
check_segment_clips = segment.check_segment_clips
check_merged_video = final_video.check_merged_video

def _normalize_existing(existing: dict | None) -> dict:
    if not existing:
        return {}
    if 'level' in existing and 'step' not in existing:
        return {'legacy': existing}
    return dict(existing)

def merge_quality_report(existing: dict | None, step: QualityStep, report: QualityReport) -> dict:
    merged = _normalize_existing(existing)
    merged[step] = report.to_dict()
    return merged

def format_quality_log_message(step: str, report: QualityReport) -> str:
    """job_log 用质检一行摘要（含 reason / 关键 details）。"""
    parts = [f'quality[{step}]={report.level}']
    details = report.details or {}
    reason = details.get('reason')
    if isinstance(reason, str) and reason.strip():
        parts.append(f'reason={reason.strip()}')
    if report.level != 'pass':
        extras = ', '.join((f'{key}={value}' for key, value in details.items() if key != 'reason' and value not in (None, '', [], {})))
        if extras:
            parts.append(extras)
    elif step == 'copy':
        word_count = details.get('word_count')
        if word_count is not None:
            parts.append(f'word_count={word_count}')
    return ', '.join(parts)

def apply_quality_checks(job_id: int, log_stage: str, checks: dict[QualityStep, QualityReport], *, existing_report: dict | None=None) -> dict:
    """写入质检报告；major 时阻断流水线。"""
    merged = _normalize_existing(existing_report)
    for step, report in checks.items():
        merged = merge_quality_report(merged, step, report)
        repo_job_log.append_log(job_id, log_stage, format_quality_log_message(step, report), level='warning' if report.level in ('minor', 'major') else 'info')
        if report.level == 'major' and report.fail_stage:
            repo_job.update_job(job_id, quality_report=merged, fail_stage=report.fail_stage)
            msg = format_quality_log_message(step, report)
            logger.warning('quality check failed: %s', msg)
            raise JobStageFailureError(msg)
    repo_job.update_job(job_id, quality_report=merged)
    return merged

class QualityMgr:
    """质检管理器（对外统一收口）。"""
    check_narration = staticmethod(script.check_narration)
    detect_memoir_narration = staticmethod(script.detect_memoir_narration)
    detect_narration_repetition = staticmethod(script.detect_narration_repetition)
    skip_narration_check = staticmethod(script.skip_narration_check)
    check_board = staticmethod(script.check_board)
    skip_board_check = staticmethod(script.skip_board_check)
    check_image_prompt = staticmethod(image_prompt.check_image_prompt)
    skip_image_prompt_check = staticmethod(image_prompt.skip_image_prompt_check)
    image_prompt_min_chars = staticmethod(image_prompt.image_prompt_min_chars)
    image_prompt_pass_chars = staticmethod(image_prompt.image_prompt_pass_chars)
    image_prompt_target_chars = staticmethod(image_prompt.image_prompt_target_chars)
    sd15_prompt_en_word_count = staticmethod(image_prompt.sd15_prompt_en_word_count)
    sd15_prompt_en_ok = staticmethod(image_prompt.sd15_prompt_en_ok)
    format_image_prompt_retry_warning = staticmethod(image_prompt.format_image_prompt_retry_warning)
    check_tts_audio = staticmethod(tts_audio.check_tts_audio)
    check_segment_images = staticmethod(segment.check_segment_images)
    check_segment_clips = staticmethod(segment.check_segment_clips)
    check_merged_video = staticmethod(final_video.check_merged_video)
    apply_quality_checks = staticmethod(apply_quality_checks)
    merge_quality_report = staticmethod(merge_quality_report)
    format_quality_log_message = staticmethod(format_quality_log_message)
quality_mgr = QualityMgr()
