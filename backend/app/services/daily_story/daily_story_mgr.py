"""日常故事业务管理。"""
from __future__ import annotations
from difflib import SequenceMatcher
import logging
import re
from typing import Any

from app.repositories import repo_daily_story, repo_job, repo_job_log
from app.repositories.sql_exec import atomic
from app.services.daily_story.story_types import quality_ready_codes
from app.services.daily_story.story_types.model import STORY_TYPE_LABELS
from app.services.llm.llm_mgr import llm_mgr
from app.utils.async_util import run_in_background
from app.utils.job_info import merge_job_info, merge_job_script_params

_VALID_STORY_TYPES = frozenset(STORY_TYPE_LABELS.keys())
_GENERATABLE_STORY_TYPES = frozenset(quality_ready_codes())

logger = logging.getLogger(__name__)
_STATUS_PROCESSING = 'processing'
_STATUS_ACTIVE = 'active'
_STATUS_REVIEW_PENDING = 'review_pending'
_STATUS_FAILED = 'failed'

def _story_has_content(story: dict[str, Any] | None) -> bool:
    if not isinstance(story, dict):
        return False
    return bool(story.get('dialogue') or [])


def _story_dialogue_text(story: dict[str, Any] | None) -> str:
    if not isinstance(story, dict):
        return ""
    return "".join(
        re.sub(r"\s+", "", str(item.get("line") or ""))
        for item in (story.get("dialogue") or [])
        if isinstance(item, dict)
    )


def _recent_story_avoids(rows: list[dict], *, limit: int = 20) -> list[str]:
    avoids: list[str] = []
    for row in rows[:limit]:
        story = row.get("story")
        if not isinstance(story, dict):
            continue
        parts = [
            str(story.get("key") or row.get("key") or "").strip(),
            str(story.get("conflict_core") or "").strip(),
        ]
        dialogue = story.get("dialogue") or []
        if isinstance(dialogue, list):
            ending = " / ".join(
                str(item.get("line") or "").strip()
                for item in dialogue[-3:]
                if isinstance(item, dict)
            )
            parts.append(ending)
        avoid = "；".join(part for part in parts if part)
        if avoid:
            avoids.append(avoid)
    return avoids


def _find_similar_story(
    story: dict[str, Any],
    rows: list[dict],
    *,
    threshold: float = 0.82,
) -> tuple[int, float] | None:
    text = _story_dialogue_text(story)
    if not text:
        return None
    story_type = str(story.get("story_type") or "").strip().upper()[:1]
    for row in rows:
        old = row.get("story")
        if not isinstance(old, dict):
            continue
        old_type = str(
            old.get("story_type") or row.get("story_type") or ""
        ).strip().upper()[:1]
        if story_type and old_type and story_type != old_type:
            continue
        old_text = _story_dialogue_text(old)
        if not old_text:
            continue
        ratio = SequenceMatcher(None, text, old_text).ratio()
        if ratio >= threshold:
            return int(row.get("id") or 0), ratio
    return None


def _validate_story_hard(
    story: dict[str, Any],
    *,
    gold_chat_row: dict[str, Any] | None = None,
) -> None:
    if gold_chat_row is not None:
        from app.services.gold_story.gold_chat.import_story import (
            validate_gold_chat_story_for_row,
        )

        validate_gold_chat_story_for_row(story, gold_chat_row)
        return
    from app.services.daily_story.prompts import (
        validate_daily_story_body_part_chars,
        validate_daily_story_json,
    )

    validate_daily_story_body_part_chars(story)
    validate_daily_story_json(story, phase='full')


def _gold_chat_source_row(story_id: int) -> dict[str, Any] | None:
    from app.repositories import repo_gold_story

    return repo_gold_story.get_by_gold_chat_daily_story_id(story_id)


def _ensure_story_quality(row: dict, *, persist: bool=False) -> dict:
    """旧稿无 quality 时补打分；persist=True 时写回 DB。"""
    from app.services.daily_story.quality import attach_daily_story_quality
    story = row.get('story')
    if not isinstance(story, dict):
        return row
    if not (story.get('dialogue') or []):
        return row
    quality = story.get('quality')
    if isinstance(quality, dict) and quality.get('grade'):
        return row
    attach_daily_story_quality(story)
    row['story'] = story
    if persist and row.get('id') is not None:
        repo_daily_story.update_story(int(row['id']), story=story)
    return row

class DailyStoryMgr:

    def _queue_story_generation(
        self,
        story_id: int,
        theme: str,
        *,
        is_regenerate: bool,
        story_type: str | None = None,
        previous_status: str | None = None,
    ) -> None:
        action = 'regenerate' if is_regenerate else 'generate'
        locked_type = (story_type or '').strip().upper()[:1] or None
        if locked_type and locked_type not in _VALID_STORY_TYPES:
            locked_type = None
        if locked_type and locked_type not in _GENERATABLE_STORY_TYPES:
            with atomic():
                repo_daily_story.update_story(story_id, status=_STATUS_FAILED)
            logger.error(
                '[DAILY_STORY] %s rejected unsupported direct type=%s story_id=%d',
                action,
                locked_type,
                story_id,
            )
            return

        def _worker() -> None:
            from app.repositories.database import get_app
            from app.services.daily_story.story_types import (
                parse_story_type_code,
                story_type_tag,
            )

            with get_app().app_context():
                try:
                    recent_rows = [
                        row
                        for row in repo_daily_story.list_stories(limit=40)
                        if int(row.get("id") or 0) != story_id
                    ]
                    gen_type = (
                        story_type_tag(locked_type) if locked_type else None
                    )
                    story = llm_mgr.generate_daily_story(
                        theme,
                        story_type=gen_type,
                        avoid=_recent_story_avoids(recent_rows),
                    )
                    type_code = locked_type or parse_story_type_code(
                        punchline=str(story.get("punchline_explain") or ""),
                    )
                    story["story_type"] = type_code
                    review_pending = (
                        story.get("_review_status") == "hard_card_failed"
                    )
                    similar = _find_similar_story(story, recent_rows)
                    if similar:
                        matched_id, ratio = similar
                        raise ValueError(
                            "故事正文与库内故事过于相似："
                            f"story_id={matched_id}, similarity={ratio:.3f}"
                        )
                    new_score = story.get('quality', {}).get('score', 0)
                    with atomic():
                        old_row = repo_daily_story.get_story(story_id)
                        old_story = old_row.get('story') if old_row else None
                        old_score = (
                            old_story.get('quality', {}).get('score', 0)
                            if isinstance(old_story, dict)
                            else 0
                        )
                        if (
                            (review_pending and _story_has_content(old_story))
                            or (old_score > new_score and not review_pending)
                        ):
                            logger.info(
                                '[DAILY_STORY] async %s keeping old (score %d > new %d) story_id=%d theme=%r',
                                action,
                                old_score,
                                new_score,
                                story_id,
                                theme,
                            )
                            retained_status = str(previous_status or '').strip()
                            if retained_status not in {
                                _STATUS_ACTIVE,
                                _STATUS_REVIEW_PENDING,
                                _STATUS_FAILED,
                            }:
                                retained_status = (
                                    _STATUS_REVIEW_PENDING
                                    if _story_has_content(old_story)
                                    else _STATUS_FAILED
                                )
                            repo_daily_story.update_story(
                                story_id,
                                status=retained_status,
                            )
                        else:
                            repo_daily_story.update_story(
                                story_id,
                                story=story,
                                status=(
                                    _STATUS_REVIEW_PENDING
                                    if review_pending
                                    else _STATUS_ACTIVE
                                ),
                                story_type=type_code,
                            )
                    logger.info(
                        '[DAILY_STORY] async %s done story_id=%d theme=%r score=%d',
                        action,
                        story_id,
                        theme,
                        new_score,
                    )
                except Exception as exc:
                    logger.error(
                        '[DAILY_STORY] async %s failed story_id=%d theme=%r: %s',
                        action,
                        story_id,
                        theme,
                        exc,
                    )
                    with atomic():
                        repo_daily_story.update_story(story_id, status=_STATUS_FAILED)
        run_in_background(_worker)
        logger.info('[DAILY_STORY] async %s queued story_id=%d theme=%r', action, story_id, theme)

    def recover_processing_stories(self) -> int:
        """服务重启后恢复卡在 processing 的日常故事生成。"""
        with atomic():
            rows = repo_daily_story.list_stories(status=_STATUS_PROCESSING, limit=200, offset=0)
        if not rows:
            logger.info('no stuck daily stories to recover')
            return 0
        for row in rows:
            story_id = int(row['id'])
            theme = str(row.get('theme') or '').strip()
            if not theme:
                logger.warning('[DAILY_STORY] recovery skipped story_id=%d: empty theme', story_id)
                with atomic():
                    repo_daily_story.update_story(story_id, status=_STATUS_FAILED)
                continue
            is_regenerate = _story_has_content(row.get('story'))
            locked = str(row.get('story_type') or '').strip().upper()[:1] or None
            logger.warning('[DAILY_STORY] recovering stuck story_id=%d theme=%r regenerate=%s', story_id, theme, is_regenerate)
            self._queue_story_generation(
                story_id,
                theme,
                is_regenerate=is_regenerate,
                story_type=locked,
                previous_status=(
                    _STATUS_REVIEW_PENDING if is_regenerate else None
                ),
            )
        logger.warning('recovered %d stuck daily story/stories', len(rows))
        return len(rows)

    def list_stories(
        self,
        *,
        status: str | None = None,
        story_type: str | None = None,
        key: str | None = None,
        has_job: bool | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict:
        """返回 {items: [...], total: N}。"""
        with atomic():
            items = repo_daily_story.list_stories(
                status=status,
                story_type=story_type,
                key=key,
                has_job=has_job,
                limit=limit,
                offset=offset,
            )
            total = repo_daily_story.count_stories(
                status=status,
                story_type=story_type,
                key=key,
                has_job=has_job,
            )
            items = [_ensure_story_quality(item) for item in items]
            return {'items': items, 'total': total}

    def get_story(self, story_id: int) -> dict:
        row = repo_daily_story.get_story(story_id)
        return _ensure_story_quality(row, persist=True)

    def generate_and_save(
        self,
        theme: str,
        *,
        story_type: str | None = None,
    ) -> dict[str, Any]:
        """异步生成：先落 processing 占位，立刻返回，后台写结果。"""
        theme = (theme or '').strip()
        if not theme:
            raise ValueError('theme is empty')
        locked = (story_type or '').strip().upper()[:1] or None
        if locked and locked not in _VALID_STORY_TYPES:
            raise ValueError(f'story_type 无效: {locked}')
        if locked and locked not in _GENERATABLE_STORY_TYPES:
            raise ValueError(f'{locked} 类尚未开放直接生成，仅支持金故事改编')
        with atomic():
            story_id = repo_daily_story.insert_story(
                theme=theme,
                story={},
                status=_STATUS_PROCESSING,
                story_type=locked,
            )
            row = repo_daily_story.get_story(story_id)
        self._queue_story_generation(
            story_id,
            theme,
            is_regenerate=False,
            story_type=locked,
        )
        return row

    def delete_stories(self, ids: list[int]) -> dict[str, Any]:
        with atomic():
            deleted = repo_daily_story.delete_stories(ids)
        return {'deleted': deleted, 'ids': ids}

    def generate_themes(
        self,
        count: int = 15,
        *,
        exclude: list[str] | None = None,
    ) -> list[dict]:
        return llm_mgr.generate_daily_story_themes(count, avoid=exclude)

    def create_job(self, story_id: int, *, skip_publish: bool=True, speech_chars_per_sec: float | None=None, phrase_gap_sec: float | None=None) -> dict:
        """基于日常故事创建视频任务（pipeline=daily_story）。"""
        from app.repositories import repo_job, repo_job_log
        from app.utils.job_info import (
            DEFAULT_BGM_VOLUME_DB,
            DEFAULT_DAILY_STORY_BGM_MATERIAL_ID,
            DEFAULT_DAILY_STORY_PHRASE_GAP_SEC,
            DEFAULT_DAILY_STORY_SPEECH_CHARS_PER_SEC,
            INTRO_CATEGORY_DAILY,
        )
        from worker.stages.daily_story.tts import DEFAULT_DAILY_SPEAKER_CONFIGS
        with atomic():
            story = repo_daily_story.get_story(story_id)
            status = str(story.get('status') or '')
            if status == _STATUS_PROCESSING:
                raise ValueError('故事正在生成中，请稍后再创建任务')
            if status != _STATUS_ACTIVE:
                raise ValueError(f'故事状态为 {status or "unknown"}，审核通过后才能创建任务')
            story_content = story.get('story') or {}
            if not (story_content.get('dialogue') or []):
                raise ValueError('故事内容为空，无法创建任务')
            _validate_story_hard(
                story_content,
                gold_chat_row=_gold_chat_source_row(story_id),
            )
            title = (story_content.get('scene_title') or '').strip()
            if not title:
                title = story.get('theme', f'日常故事-{story_id}')
            cps = float(speech_chars_per_sec) if speech_chars_per_sec is not None else DEFAULT_DAILY_STORY_SPEECH_CHARS_PER_SEC
            gap = float(phrase_gap_sec) if phrase_gap_sec is not None else DEFAULT_DAILY_STORY_PHRASE_GAP_SEC
            info = merge_job_info(
                merge_job_script_params(None, speech_chars_per_sec=cps),
                daily_story_id=story_id,
                orientation='landscape',
                intro_category=INTRO_CATEGORY_DAILY,
                video_provider='ffmpeg',
                bgm={'enabled': True, 'material_id': DEFAULT_DAILY_STORY_BGM_MATERIAL_ID, 'volume_db': DEFAULT_BGM_VOLUME_DB},
                subtitle={'enabled': True},
            )
            speaker_configs: dict[str, Any] = {
                name: dict(cfg) for name, cfg in DEFAULT_DAILY_SPEAKER_CONFIGS.items()
            }
            speaker_configs['phrase_gap_sec'] = gap
            info['tts'] = {'speaker_configs': speaker_configs}
            from app.services.daily_story.story_types import chat_type_info_message
            type_info = chat_type_info_message(story.get('story_type'))
            job = repo_job.create_job(
                title,
                skip_publish=skip_publish,
                stage='script',
                status='pending',
                pipeline='chat',
                material_id=story_id,
                info=info,
                error_message=type_info,
            )
            repo_job_log.append_log(job['id'], 'api', f'created daily story job: story_id={story_id}, title={title!r}')
            repo_daily_story.set_job_id(story_id, job['id'])
            return job

    def update_story(self, story_id: int, *, story: dict[str, Any]) -> dict:
        """更新日常故事内容（保存时重算观感分）。"""
        from app.services.daily_story.prompts import (
            sync_discovery_opening_from_dialogue,
            try_local_patch_daily_story_body,
        )
        from app.services.daily_story.quality import attach_daily_story_quality
        if isinstance(story, dict):
            sync_discovery_opening_from_dialogue(story)
            story, _ = try_local_patch_daily_story_body(story)
            story.pop('_review_status', None)
            _validate_story_hard(
                story,
                gold_chat_row=_gold_chat_source_row(story_id),
            )
            attach_daily_story_quality(story)
        return repo_daily_story.update_story(
            story_id,
            story=story,
            status=_STATUS_ACTIVE,
        )

    def regenerate_story(self, story_id: int) -> dict:
        """异步重新生成：立刻标 processing 返回，后台替换内容。"""
        with atomic():
            old = repo_daily_story.get_story(story_id)
            old_status = str(old.get('status') or '')
            if old_status == _STATUS_PROCESSING:
                return old
            theme = str(old.get('theme') or '').strip()
            if not theme:
                raise ValueError('theme is empty')
            locked = str(old.get('story_type') or '').strip().upper()[:1] or None
            if locked and locked not in _GENERATABLE_STORY_TYPES:
                raise ValueError(f'{locked} 类尚未开放直接生成，仅支持金故事改编')
            row = repo_daily_story.update_story(story_id, status=_STATUS_PROCESSING)
        self._queue_story_generation(
            story_id,
            theme,
            is_regenerate=True,
            story_type=locked,
            previous_status=old_status,
        )
        return row

    def sync_to_job(self, story_id: int, *, story: dict[str, Any] | None=None) -> dict:
        """更新故事内容并同步到已有任务，重置脚本阶段使其重新生成。"""
        old = repo_daily_story.get_story(story_id)
        job_id = old.get('job_id')
        if not job_id:
            raise ValueError('该故事尚未创建任务，无法同步')

        from app.services.job.job_mgr import job_mgr

        def _sync(job: dict) -> dict:
            current = repo_daily_story.get_story(story_id)
            if story is None and current.get('status') != _STATUS_ACTIVE:
                raise ValueError('故事尚未审核通过，无法同步到任务')
            target_story = story or current.get('story') or {}
            if not isinstance(target_story, dict):
                raise ValueError('故事内容无效，无法同步')
            from app.services.daily_story.prompts import (
                sync_discovery_opening_from_dialogue,
            )
            from app.services.daily_story.quality import attach_daily_story_quality
            sync_discovery_opening_from_dialogue(target_story)
            target_story.pop('_review_status', None)
            _validate_story_hard(
                target_story,
                gold_chat_row=_gold_chat_source_row(story_id),
            )
            attach_daily_story_quality(target_story)
            with atomic():
                if story is not None:
                    repo_daily_story.update_story(
                        story_id,
                        story=target_story,
                        status=_STATUS_ACTIVE,
                    )
            job_mgr.prepare_rerun(int(job_id), 'script')
            title = (
                str(target_story.get('scene_title') or '').strip()
                or str(job.get('title') or '')
            )
            from app.services.daily_story.story_types import chat_type_info_message
            type_info = chat_type_info_message(current.get('story_type'))
            with atomic():
                repo_job.update_job(
                    job_id,
                    title=title,
                    error_message=type_info,
                )
                repo_job_log.append_log(
                    job_id,
                    'api',
                    f'synced daily story #{story_id} to job #{job_id}, '
                    'stage reset to script',
                )
                return repo_job.get_job(job_id)

        return job_mgr.run_if_idle(int(job_id), _sync)
daily_story_mgr = DailyStoryMgr()
