from __future__ import annotations
import logging
import re
from pathlib import Path
from app.repositories import repo_job_log, repo_job, repo_segment
from app.services.intro import generate_intro
from app.services.intro.cover_layout import build_cover_image_prompt, compose_cover_image, cover_canvas_size
from app.services.intro.size import is_material_job, resolve_intro_size
from app.utils.job_info import ORIENTATION_AUTO, ORIENTATION_PORTRAIT, intro_category_from_job, intro_generate_category, is_keyframe_segment, orientation_for_resolve
from app.utils.title_text import prefer_source_punctuation
from worker.context import JobContext
from worker.stages.base import StageExecutor
from app.repositories.sql_exec import atomic
logger = logging.getLogger(__name__)

def _normalize_title(title: str) -> str:
    return re.sub('\\s+', '', (title or '').strip())

def resolve_intro_title(job: dict) -> str:
    """优先 script_json 定稿标题；若优化仅去掉标点则用 draft_title。"""
    script = job.get('script_json')
    if isinstance(script, dict):
        script_title = _normalize_title(str(script.get('title') or ''))
        draft_title = _normalize_title(str(script.get('draft_title') or ''))
        if script_title:
            if draft_title:
                return prefer_source_punctuation(draft_title, script_title)
            return script_title
    job_title = _normalize_title(str(job.get('title') or ''))
    return job_title or '未命名'

def _orientation_label(job: dict, *, intro_orientation: str | None, effective_orientation: str | None) -> str:
    if intro_orientation:
        return intro_orientation
    if effective_orientation:
        return effective_orientation
    if is_material_job(job):
        return ORIENTATION_AUTO
    return f'{ORIENTATION_PORTRAIT}(default)'

def _generate_cover_subject_from_narration(title: str, narration: str) -> str:
    """用 LLM 根据标题和口播内容生成封面画面描述。"""
    import logging
    from app.config import get_settings
    from app.services.llm.llm_deepseek import DeepSeekClient
    logger = logging.getLogger(__name__)
    settings = get_settings()
    if not settings.deepseek_api_key:
        logger.warning('no deepseek_api_key, fallback to title for cover subject')
        return title
    system = '你是一个视频封面画面设计师。根据视频标题和口播内容，用一段话描述封面底图应该呈现的画面。\n要求：\n1. 描述具体的视觉场景：主体、环境、光照、色调、构图\n2. 不要出现文字、标题、字幕等元素\n3. 画面要有冲击力，适合作为视频封面吸引点击\n4. 风格为写实插画或电影质感\n5. 80-150字以内\n仅输出画面描述，不要额外解释。'
    user = f'标题：{title}\n口播内容：{narration}'
    try:
        client = DeepSeekClient()
        result, _ = client._chat(system, user, json_mode=False, thinking_enabled=False, temperature=0.5)
        desc = result.strip()
        if desc and len(desc) >= 20:
            logger.info("cover subject generated from narration: '%s'", desc[:80])
            return desc
    except Exception as exc:
        logger.warning('cover subject generation failed: %s', exc)
    logger.warning('cover subject generation returned empty/short result, fallback to title')
    return title

def _cover_subject_from_job(job: dict) -> str:
    """封面底图画面描述：首镜 image_prompt > visual_style > LLM 生成 > 标题。"""
    script = job.get('script_json') or {}
    title = resolve_intro_title(job)
    visual_style = (script.get('visual_style') or '').strip()
    for seg in script.get('segments') or []:
        ip = (seg.get('image_prompt') or '').strip()
        if ip:
            return ip
    if visual_style:
        return visual_style
    narration_parts = []
    for seg in script.get('segments') or []:
        text = (seg.get('text') or '').strip()
        if text:
            narration_parts.append(text)
    narration = script.get('narration') or '\n'.join(narration_parts)
    if narration and narration.strip():
        return _generate_cover_subject_from_narration(title, narration.strip())
    return title

def pick_cover_image(job: dict, segments: list[dict]) -> tuple[Path | None, str]:
    """选择封面底图。

    chat：优先特写 → 非开场关键帧 → 分镜 1；其它流水线：分镜 1。
    """
    by_index = {int(seg['segment_index']): seg for seg in segments if seg.get('segment_index') is not None}

    def _existing(seg: dict | None) -> Path | None:
        if not seg:
            return None
        raw = str(seg.get('image_path') or '').strip()
        if not raw:
            return None
        path = Path(raw)
        return path if path.is_file() else None
    if (job.get('pipeline') or '').strip() == 'chat':
        shots: dict[int, str] = {}
        script = job.get('script_json')
        if isinstance(script, dict):
            for seg in script.get('segments') or []:
                if not isinstance(seg, dict):
                    continue
                try:
                    index = int(seg.get('segment_index') or 0)
                except (TypeError, ValueError):
                    continue
                shot = str(seg.get('shot_type') or '').strip()
                if index > 0 and shot:
                    shots[index] = shot
        for index in sorted(by_index):
            if shots.get(index) != '特写':
                continue
            path = _existing(by_index[index])
            if path is not None:
                return (path, f'closeup seg{index}')
        for index in sorted(by_index):
            if index == 1 or not is_keyframe_segment(by_index[index]):
                continue
            path = _existing(by_index[index])
            if path is not None:
                return (path, f'keyframe seg{index}')
    path = _existing(by_index.get(1))
    if path is not None:
        return (path, 'seg1')
    return (None, 'none')

def _generate_cover(job: dict, cover_path: Path, width: int, height: int) -> None:
    """intro 阶段：选分镜图做封面；没有可用图再 Agnes 生图。"""
    import tempfile
    from PIL import Image
    from app.config import get_settings
    from app.services.segment.image.image_agnes import AgnesImageProvider
    settings = get_settings()
    title = resolve_intro_title(job)
    job_id = int(job['id'])
    cw, ch, _ = cover_canvas_size(width, height)
    pipeline = job.get('pipeline')
    host_intro_path = settings.get_host_intro_path(pipeline)
    brand = '昭墨日常' if pipeline == 'chat' else settings.brand_name
    with atomic():
        segs = repo_segment.list_segments(job_id)
    source, reason = pick_cover_image(job, segs)
    if source is not None:
        img = Image.open(source).convert('RGBA')
        img = img.resize((cw, ch), Image.LANCZOS)
        composed = compose_cover_image(img, title, brand_name=brand, host_intro_path=host_intro_path)
        composed.convert('RGB').save(cover_path, quality=92)
        logger.info('job %s cover: using %s (%s)', job_id, reason, source)
        return
    subject = _cover_subject_from_job(job)
    cover_prompt = build_cover_image_prompt(cw=cw, ch=ch, subject=subject)
    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        AgnesImageProvider().generate(cover_prompt, tmp_path, size=f'{cw}x{ch}')
        img = Image.open(tmp_path)
        composed = compose_cover_image(img, title, brand_name=brand, host_intro_path=host_intro_path)
        composed.convert('RGB').save(cover_path, quality=92)
        logger.info('job %s cover: agnes generated (no segment image)', job_id)
    finally:
        tmp_path.unlink(missing_ok=True)

def run_intro_for_category(ctx: JobContext, job: dict, *, stage: StageExecutor) -> None:
    intro_path = ctx.rel('intro.mp4')
    title = resolve_intro_title(job)
    category_label = intro_category_from_job(job)
    gen_category = intro_generate_category(job)
    effective_orientation = ctx.intro_orientation
    if effective_orientation is None:
        effective_orientation = orientation_for_resolve(job)
    width, height = resolve_intro_size(settings=ctx.settings, orientation=effective_orientation, job=job, media_dir=ctx.media_dir)
    orient_label = _orientation_label(job, intro_orientation=ctx.intro_orientation, effective_orientation=effective_orientation)
    generate_intro(title, intro_path, category=gen_category, hold_tail_sec=ctx.intro_hold_tail_sec, width=width, height=height, pipeline=job.get('pipeline'))
    cover_path = ctx.rel('cover.jpg')
    _generate_cover(job, cover_path, width, height)
    end_path = None
    if job.get('pipeline') == 'chat':
        from app.services.end_card import generate_end_card
        end_path = ctx.rel('end.mp4')
        generate_end_card(end_path, width=width, height=height)
    with atomic():
        updates: dict = {'intro_path': str(intro_path.resolve()), 'cover_path': str(cover_path.resolve())}
        if end_path is not None:
            updates['end_path'] = str(end_path.resolve())
        if _normalize_title(str(job.get('title') or '')) != title:
            updates['title'] = title
        repo_job.update_job(ctx.job['id'], **updates)
        detail = f'intro at {intro_path}, cover at {cover_path}, title={title}, size={width}x{height}, orientation={orient_label}, category={category_label}'
        if ctx.intro_hold_tail_sec is not None:
            detail += f', hold_tail_sec={ctx.intro_hold_tail_sec:.2f}'
        if end_path is not None:
            detail += f', end at {end_path}'
        repo_job_log.append_log(ctx.job['id'], stage.name, detail)
