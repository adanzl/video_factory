"""分镜出图总入口：ImageProvider 工厂与批量出图。"""
from __future__ import annotations
import logging
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from contextlib import nullcontext
from pathlib import Path
from typing import Any
from app.config import get_settings
from app.utils.job_cancel import job_cancel
from app.repositories.database import get_app
from app.repositories.sql_exec import atomic
logger = logging.getLogger(__name__)
__all__ = ['ImageMgr', 'ImageProvider', 'image_mgr']

def _greenlet_app_context():
    """greenlet 不继承父协程的 Flask app context，访问 DB 前须自行推入。"""
    try:
        return get_app().app_context()
    except RuntimeError:
        return nullcontext()

def _verify_prompt_regen_feedback(speakers: list[str]) -> str:
    look: list[str] = []
    if '灿灿' in speakers:
        look.append('灿灿黑色头发黑色单侧高马尾，头发通体纯黑')
    if '昭昭' in speakers:
        look.append('昭昭男孩超短发，露出双耳与后颈')
    if '妈妈' in speakers:
        look.append('妈妈须为成年女性黑长发米色上衣牛仔裤，禁止画成小孩')
    look_clause = f"；仍须保持：{'；'.join(look)}" if look else ''
    cast = '、'.join(speakers) if speakers else '本段对白角色'
    return (
        f'出图质检连续未通过（发型/人数/肢体/场景等），请改写本段 image_prompt：'
        f'换姿势与构图、冲突道具用台词已有物件放大，禁止新编陈设{look_clause}。'
        f'画面人物只能是：{cast}；禁止新增未出场角色。'
    )

def _verify_visual_brief_regen_feedback(speakers: list[str]) -> str:
    cast = '、'.join(speakers) if speakers else '本段可入画角色'
    return (
        f'出图质检连续未通过，请改写本段 visual_brief：换姿势与构图、'
        f'冲突道具用台词已有物件放大，禁止新编陈设；'
        f'站位与台词事实保持一致；禁止写发型/服装/鞋帽；'
        f'画面人物必须含：{cast}（同场粘性角色不可漏画）；禁止新增未授权角色。'
    )

def _content_policy_prompt_regen_feedback(speakers: list[str]) -> str:
    cast = '、'.join(speakers) if speakers else '本段对白角色'
    return (
        '出图被内容策略拦截（content_policy_violation），请改写本段 image_prompt：'
        '去掉可能敏感/暴力/惊吓/不当暗示，改用温和日常表述，换姿势与构图、'
        '冲突道具用台词已有物件放大，禁止新编陈设；'
        f'画面人物只能是：{cast}；禁止新增未出场角色。'
    )

def _content_policy_visual_brief_regen_feedback(speakers: list[str]) -> str:
    cast = '、'.join(speakers) if speakers else '本段可入画角色'
    return (
        '出图被内容策略拦截（content_policy_violation），请改写本段 visual_brief：'
        '去掉可能敏感/暴力/惊吓/不当暗示，改用温和日常冲突与道具；换姿势与构图；'
        f'站位与台词事实保持一致；禁止写发型/服装/鞋帽；画面人物必须含：{cast}'
        '（同场粘性角色不可漏画）；禁止新增未授权角色。'
    )

def _speakers_for_regen(seg: dict) -> list[str]:
    from app.services.script.image_prompt import _daily_speakers_of
    return _daily_speakers_of(seg)

class ImageProvider(ABC):
    max_workers: int | None = None
    """批量出图并发上限；None 表示跟随 IMAGE_MAX_WORKERS。本地推理类 provider 独占显存，须覆写为 1。"""

    @abstractmethod
    def generate(self, prompt: str, output_path: Path, *, size: str | None=None, ref_images: list[Path | str] | None=None, expected_speakers: list[str] | None=None, content_style: str | None=None) -> Path:
        ...

    def describe_params(self, *, size: str | None=None) -> str:
        return 'provider=unknown'

class ImageMgr:
    """分镜出图管理器。"""

    def _get_image_provider(self, provider_name: str | None=None) -> ImageProvider:
        from app.services.segment.image.image_agnes import AgnesImageProvider
        from app.services.segment.image.image_mock import MockImageProvider
        from app.services.segment.image.image_sd15 import Sd15ImageProvider
        from app.services.segment.image.image_wan import WanImageProvider
        from app.services.segment.image.image_zimage import ZImageProvider
        if get_settings().mock_mode:
            return MockImageProvider()
        provider = provider_name or get_settings().image_provider
        if provider == 'z_image_t2i':
            return ZImageProvider()
        if provider == 'wan_t2i':
            return WanImageProvider()
        if provider == 'sd15_t2i':
            return Sd15ImageProvider()
        if provider == 'agnes_t2i':
            return AgnesImageProvider()
        raise ValueError(f'unknown IMAGE_PROVIDER: {provider}')

    @staticmethod
    def _resolve_max_workers(provider: ImageProvider) -> int:
        """并发度以 provider 自身能力为准，仅云端 provider 跟随 IMAGE_MAX_WORKERS。"""
        settings = get_settings()
        if settings.mock_mode:
            return 1
        cap = getattr(provider, 'max_workers', None)
        if isinstance(cap, int) and cap > 0:
            return cap
        return max(1, settings.image_max_workers)

    @staticmethod
    def _regen_segment_image_prompt(
        seg: dict,
        *,
        job: dict[str, Any] | None,
        content_style: str | None,
        reason: str = 'verify',
    ) -> str:
        """质检耗尽 / 内容策略拦截后，按单段重写 image_prompt（含 daily 规则拼装）。"""
        from app.services.llm.llm_mgr import llm_mgr
        from app.services.script.image_prompt import wrap_image_prompts
        from app.utils.job_info import CONTENT_STYLE_DAILY_STORY, resolve_include_sd15_prompt
        if not job:
            raise RuntimeError('missing job for image_prompt regen')
        script = job.get('script_json')
        if not isinstance(script, dict):
            raise RuntimeError('job.script_json missing for image_prompt regen')
        index = int(seg['segment_index'])
        script_segments = list(script.get('segments') or [])
        by_index = {int(s.get('segment_index') or 0): s for s in script_segments if s}
        target = dict(by_index.get(index) or {})
        for key in ('segment_index', 'text', 'visual_brief', 'dialogue', 'shot_type', 'info', 'motion_prompt', 'visual_mode'):
            if seg.get(key) is not None:
                target[key] = seg[key]
        target['segment_index'] = index
        by_index[index] = target
        script['segments'] = sorted(by_index.values(), key=lambda s: int(s.get('segment_index') or 0))
        if content_style == CONTENT_STYLE_DAILY_STORY:
            from app.services.daily_story.speaker import annotate_sticky_stage_speakers

            annotate_sticky_stage_speakers(
                script.get('segments') or [],
                setting=str(script.get('setting') or '').strip() or None,
            )
            target = next(
                (
                    s
                    for s in (script.get('segments') or [])
                    if int(s.get('segment_index') or 0) == index
                ),
                target,
            )
        speakers = _speakers_for_regen(target)
        if reason == 'content_policy':
            vb_feedback = _content_policy_visual_brief_regen_feedback(speakers)
            ip_feedback = _content_policy_prompt_regen_feedback(speakers)
        else:
            vb_feedback = _verify_visual_brief_regen_feedback(speakers)
            ip_feedback = _verify_prompt_regen_feedback(speakers)
        old_brief = str(target.get('visual_brief') or '')
        if content_style == CONTENT_STYLE_DAILY_STORY:
            from app.services.script.visual_brief import (
                daily_locked_inventory,
                held_prop_owners,
            )

            locked = daily_locked_inventory(
                script.get('segments') or [],
                str(script.get('setting') or '').strip() or None,
            )
            if locked:
                names = '、'.join(sorted(locked, key=len, reverse=True))
                lock_note = (
                    f'本片锁定物品：{names}。禁止新增未锁定的家具/文具/第二件同款。'
                )
                vb_feedback = f'{vb_feedback}{lock_note}'
                ip_feedback = f'{ip_feedback}{lock_note}'
            vb_feedback = (
                f'{vb_feedback}'
                '左右已写「画面左边/右边是谁」时只改姿势，'
                '禁止再写「站在她右侧/他左侧」等相对站位。'
            )
            owners = held_prop_owners(old_brief)
            if owners:
                bits = [f'{holder}持{prop}' for prop, holder in owners.items()]
                vb_feedback = (
                    f'{vb_feedback}'
                    f'本镜持物锁定：{"、".join(bits)}。'
                    '禁止换人；未持物角色写空手。'
                    '已持物不要再写桌上/纸旁还有该物；'
                    '非持物人看人，不要盯着物。'
                )
        if content_style == CONTENT_STYLE_DAILY_STORY:
            llm_mgr.fill_visual_briefs(script, feedback=vb_feedback, job=job, segment_indices=[index])
            from app.services.script.visual_brief import (
                restore_held_prop_owners,
                scrub_daily_visual_brief,
            )

            for item in script.get('segments') or []:
                if int(item.get('segment_index') or 0) != index:
                    continue
                item['visual_brief'] = scrub_daily_visual_brief(
                    restore_held_prop_owners(
                        str(item.get('visual_brief') or ''),
                        old_brief,
                    )
                )
                break
            llm_mgr.fill_image_prompts(script, job=job, segment_indices=[index], include_sd15_prompt=resolve_include_sd15_prompt(job))
        else:
            llm_mgr.fill_image_prompts(script, feedback=ip_feedback, job=job, segment_indices=[index], include_sd15_prompt=resolve_include_sd15_prompt(job))
        refreshed = next((s for s in script.get('segments') or [] if int(s.get('segment_index') or 0) == index), None)
        if refreshed is None:
            raise RuntimeError(f'image_prompt regen missing segment {index}')
        wrap_image_prompts(
            script.get('segments') or [],
            content_style=content_style,
            setting=str(script.get('setting') or '').strip() or None,
            segment_indices=[index],
        )
        refreshed = next((s for s in script.get('segments') or [] if int(s.get('segment_index') or 0) == index), None) or refreshed
        new_prompt = str(refreshed.get('image_prompt') or '').strip()
        if not new_prompt:
            raise RuntimeError(f'image_prompt regen empty for segment {index}')
        if '出图质检连续未通过' in new_prompt or '出图被内容策略拦截' in new_prompt:
            raise RuntimeError(f'image_prompt regen leaked feedback into T2I for segment {index}')
        if refreshed.get('visual_brief') is not None:
            seg['visual_brief'] = refreshed.get('visual_brief')
            if job is not None and job.get('id') is not None:
                from app.repositories import repo_job
                from app.repositories.sql_exec import atomic
                with atomic():
                    repo_job.update_job(int(job['id']), script_json=script)
        if refreshed.get('motion_prompt') is not None:
            seg['motion_prompt'] = refreshed.get('motion_prompt')
            ImageMgr._inject_speaking_times_for_segment(seg, job=job)
        if refreshed.get('sd15_prompt_en') is not None:
            seg['sd15_prompt_en'] = refreshed.get('sd15_prompt_en')
        seg['image_prompt'] = new_prompt
        return new_prompt

    @staticmethod
    def _inject_speaking_times_for_segment(
        seg: dict,
        *,
        job: dict[str, Any] | None,
    ) -> None:
        """质检重生 motion 后按 TTS cues 写回说话时间轴（无 cues 则字数估时）。"""
        motion = str(seg.get('motion_prompt') or '').strip()
        if not motion or '说话，同时' not in motion:
            return
        job_id = None
        if job is not None and job.get('id') is not None:
            job_id = int(job['id'])
        elif seg.get('job_id') is not None:
            job_id = int(seg['job_id'])
        index = int(seg.get('segment_index') or 0)
        if index <= 0:
            return
        from app.services.media.media_mgr import inject_speaking_times_into_motion_prompts
        from app.services.tts.tts_mgr import tts_mgr
        cues: list = []
        if job_id is not None:
            media_dir = get_settings().video_data_dir / str(job_id)
            cues_path = tts_mgr.subtitle_cues_path_for(media_dir / 'audio')
            if cues_path.exists():
                cues = tts_mgr.load_subtitle_cues(cues_path)
        n = inject_speaking_times_into_motion_prompts(
            [seg],
            cues,
            segment_indices={index},
            estimate_cues_without_tts=not cues,
        )
        if n:
            logger.info(
                'image segment %s: reinjected speaking times into motion_prompt after prompt regen',
                index,
            )

    @staticmethod
    def _persist_segment_prompt(seg: dict) -> None:
        seg_id = seg.get('id')
        if seg_id is None:
            return
        from app.repositories import repo_segment
        from app.repositories.sql_exec import atomic
        payload: dict[str, Any] = {'image_prompt': seg.get('image_prompt')}
        if seg.get('motion_prompt') is not None:
            payload['motion_prompt'] = seg.get('motion_prompt')
        if seg.get('sd15_prompt_en') is not None:
            payload['sd15_prompt_en'] = seg.get('sd15_prompt_en')
        with atomic():
            repo_segment.update_segment(int(seg_id), **payload)

    def generate_segment_images(self, segments: list[dict], images_dir: Path, *, size: str | None=None, image_provider: str | None=None, on_image_done: Callable[[int, Path, float], None] | None=None, job_id: int | None=None, job: dict[str, Any] | None=None, ref_images: list[Path | str] | None=None, content_style: str | None=None) -> list[tuple[int, Path]]:
        images_dir.mkdir(parents=True, exist_ok=True)
        provider = self._get_image_provider(image_provider)
        max_workers = self._resolve_max_workers(provider)
        total = len(segments)
        started = 0
        done = 0
        start = time.time()
        params_desc = provider.describe_params(size=size)
        logger.info('image batch start: count=%s, workers=%s, %s', total, max_workers, params_desc)
        if hasattr(provider, '_active_job_id'):
            provider._active_job_id = job_id

        from app.utils.job_info import CONTENT_STYLE_DAILY_STORY, content_style_from_job
        style = content_style or (content_style_from_job(job) if job else None)
        if style == CONTENT_STYLE_DAILY_STORY:
            from app.services.daily_story.speaker import annotate_sticky_stage_speakers

            setting = None
            full_segs = segments
            if isinstance(job, dict):
                sj = job.get('script_json')
                if isinstance(sj, dict):
                    setting = str(sj.get('setting') or '').strip() or None
                    raw = sj.get('segments')
                    if isinstance(raw, list) and raw:
                        full_segs = raw
            annotate_sticky_stage_speakers(full_segs, setting=setting)
            by_idx = {
                int(s.get('segment_index') or 0): s
                for s in full_segs
                if isinstance(s, dict)
            }
            for seg in segments:
                src = by_idx.get(int(seg.get('segment_index') or 0))
                if src and isinstance(src.get('speakers'), list) and src.get('speakers'):
                    seg['speakers'] = list(src['speakers'])

        def _build_prompt(seg: dict) -> str:
            if type(provider).__name__ == 'Sd15ImageProvider':
                prompt = seg.get('sd15_prompt_en') or seg.get('image_prompt') or seg['text']
            else:
                prompt = seg.get('image_prompt') or seg['text']
            from app.services.intro.cover_layout import _subject_has_map_keyword
            from app.services.script.image_prompt import strip_verify_regen_leak
            prompt = strip_verify_regen_leak(str(prompt))
            raw_ip = str(seg.get('image_prompt') or '').strip()
            if raw_ip and prompt != raw_ip and (
                '出图质检连续未通过' in raw_ip or '出图被内容策略拦截' in raw_ip
            ):
                seg['image_prompt'] = prompt
                self._persist_segment_prompt(seg)
            if _subject_has_map_keyword(prompt):
                prompt = f'若包含世界地图，不得显示中国部分。任何地图不得出现中国领土、藏南地区、阿克赛钦地区。{prompt}'
            return prompt

        def _speakers(seg: dict) -> list[str] | None:
            from app.services.script.image_prompt import _daily_speakers_of
            cast = _daily_speakers_of(seg)
            if cast:
                return cast
            dialogue = seg.get('dialogue') or []
            speakers = sorted(set((d.get('speaker', '') for d in dialogue if d.get('speaker'))))
            return speakers if speakers else None

        def render(seg: dict) -> tuple[int, Path, float] | None:
            with _greenlet_app_context():
                return _render_one(seg)

        def _render_one(seg: dict) -> tuple[int, Path, float] | None:
            from app.services.llm.llm_agnes import AgnesContentPolicyError
            from app.services.segment.image.image_agnes import AgnesImageVerifyFailed
            from app.utils.job_cancel import JobCancelledError
            _regen_exc = (AgnesImageVerifyFailed, AgnesContentPolicyError)
            nonlocal started
            if job_id is not None:
                job_cancel.raise_if_cancelled(job_id)
            started += 1
            seq = started
            index = seg['segment_index']
            t0 = time.time()
            out = images_dir / f'{index}.png'
            prompt = _build_prompt(seg)
            expected_speakers = _speakers(seg)
            logger.info('image %s/%s generating segment %s | %s | prompt_chars=%s | speakers=%s | out=%s', seq, total, index, params_desc, len(prompt), expected_speakers, out.name)
            try:
                try:
                    provider.generate(prompt, out, size=size, ref_images=ref_images, expected_speakers=expected_speakers, content_style=content_style)
                except _regen_exc as first_fail:
                    regen_reason = (
                        'content_policy'
                        if isinstance(first_fail, AgnesContentPolicyError)
                        else 'verify'
                    )
                    logger.warning(
                        'image segment %s %s on current prompt; regenerating image_prompt then retry',
                        index,
                        'content_policy_violation'
                        if regen_reason == 'content_policy'
                        else 'verify exhausted',
                    )
                    try:
                        new_prompt = self._regen_segment_image_prompt(
                            seg,
                            job=job,
                            content_style=content_style,
                            reason=regen_reason,
                        )
                        self._persist_segment_prompt(seg)
                        prompt = _build_prompt(seg)
                        logger.info(
                            'image segment %s prompt regenerated chars=%s; retry generate',
                            index,
                            len(new_prompt),
                        )
                    except Exception as regen_exc:
                        logger.error('image segment %s prompt regen failed: %s', index, regen_exc)
                        raise first_fail from regen_exc
                    provider.generate(prompt, out, size=size, ref_images=ref_images, expected_speakers=expected_speakers, content_style=content_style)
            except _regen_exc as exc:
                kind = (
                    'content_policy'
                    if isinstance(exc, AgnesContentPolicyError)
                    else 'verify'
                )
                logger.error(
                    'image %s/%s SKIP segment %s after %s fail (%.1fs) | %s | %s',
                    seq,
                    total,
                    index,
                    kind,
                    time.time() - t0,
                    params_desc,
                    exc,
                )
                if out.exists():
                    try:
                        out.unlink()
                    except OSError:
                        pass
                return None
            except JobCancelledError:
                raise
            except Exception as exc:
                logger.error('image %s/%s FAILED segment %s after %.1fs | %s | err=%s', seq, total, index, time.time() - t0, params_desc, exc)
                raise
            elapsed = time.time() - t0
            logger.info('image %s/%s done segment %s in %.1fs | %s | bytes=%s', seq, total, index, elapsed, params_desc, out.stat().st_size if out.exists() else 0)
            return (seg['id'], out, elapsed)
        results: list[tuple[int, Path]] = []
        skipped = 0
        from gevent import iwait
        from gevent.lock import Semaphore
        from gevent.pool import Group

        # Pool.spawn 在池满时会阻塞。若用列表推导一次性 spawn 全部任务，
        # iwait/on_image_done 要等 (n - workers) 张完成后才能开始，DB 长时间不更新。
        # Group + Semaphore：spawn 不阻塞，信号量限并发，完成即回调落库。
        sem = Semaphore(max_workers)
        group = Group()

        def limited_render(seg: dict) -> tuple[int, Path, float] | None:
            with sem:
                return render(seg)

        green_lets = [group.spawn(limited_render, seg) for seg in segments]
        try:
            for g in iwait(green_lets):
                if job_id is not None:
                    job_cancel.raise_if_cancelled(job_id)
                item = g.get()
                done += 1
                if item is None:
                    skipped += 1
                    continue
                seg_id, path, gen_sec = item
                results.append((seg_id, path))
                if on_image_done is not None:
                    on_image_done(seg_id, path, gen_sec)
        finally:
            group.kill(block=False)
            if hasattr(provider, '_active_job_id'):
                provider._active_job_id = None
        elapsed = time.time() - start
        logger.info('image batch done: %s/%s ok, skipped=%s in %.1fs | %s', len(results), total, skipped, elapsed, params_desc)
        return results

    def generate_cover(self, title: str, output_path: Path, *, base_prompt: str | None=None) -> Path:
        from app.services.intro.cover_layout import _resolve_cover_subject, _subject_has_map_keyword
        resolved_title = _resolve_cover_subject(title)
        if base_prompt:
            prompt = base_prompt
        else:
            prompt = f'B站科普视频封面，16:9，信息图风格，标题文字区域留白，'
            if _subject_has_map_keyword(title):
                prompt += '若包含世界地图，不得显示中国部分。任何地图不得出现中国领土、藏南地区、阿克赛钦地区，'
            prompt += f'主题：{resolved_title}'
        return self._get_image_provider().generate(prompt, output_path, size=get_settings().wan_cover_size)
image_mgr = ImageMgr()
