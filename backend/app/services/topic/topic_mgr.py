"""选题库业务管理。"""
from __future__ import annotations
import logging
import re
from app.config import get_settings
from app.repositories import repo_job, repo_title
from app.services.job.job_mgr import job_mgr
from app.utils.job_info import CONTENT_STYLE_HISTORICAL_MYSTERY, ORIENTATION_LANDSCAPE, merge_job_script_params
from app.services.llm.llm_mgr import TopicLlmOperation, llm_mgr
from app.utils.media import DEFAULT_HISTORY_VIDEO_MINUTES, DEFAULT_STANDARD_VIDEO_MINUTES
from app.services.topic.catalog import CATEGORY_HISTORY, normalize_category
from app.services.topic.prompts.builder import build_topic_optimize_system_prompt, build_topic_optimize_user_prompt
from app.services.topic.text import conversational_rewrite_example, normalize_title, topic_title_issue
from app.services.topic.scorers import SCORE_THRESHOLD, ScoreResult, score_title, status_from_score
from app.repositories.sql_exec import atomic
logger = logging.getLogger(__name__)
_RUN_MODES = frozenset({'none', 'script', 'full'})

def _extract_keyword(title: str) -> str:
    """从标题提取核心关键词（人名/地名/事件名），用于去重。"""
    text = re.sub('[？?！!，,。.、\\s\\"\\\'“”]', '', title)
    if not text:
        return text
    parts = re.split('[的与和被在让将给从以于对把到用打上出]', text, maxsplit=1)
    head = parts[0].strip()
    if 2 <= len(head) <= 8:
        return head
    if len(head) > 8 and head.endswith(('啦', '了', '的')):
        head = head[:-1]
    return head[:6]

def _existing_keywords() -> set[str]:
    result: set[str] = set()
    for raw in repo_title.list_all_keywords():
        for kw in raw.split(','):
            k = kw.strip()
            if k:
                result.add(k)
    return result

def _merge_optimize_hook(*, candidate_hook: str | None, original_hook: str | None) -> str | None:
    """优化结果 hook 为空时保留原 hook，避免 preview 打分偏低。"""
    hook = str(candidate_hook or '').strip()
    if hook:
        return hook
    orig = str(original_hook or '').strip()
    return orig or None

def _optimize_fallback_title(row: dict, *, max_title_len: int, category: str, template: str | None) -> tuple[str, str | None, dict] | None:
    """LLM 优化失败时，用规则改写示例作为兜底标题。"""
    if normalize_category(category) == CATEGORY_HISTORY:
        return None
    candidate = normalize_title(conversational_rewrite_example(str(row.get('title') or '')), max_len=max_title_len)
    if not candidate:
        return None
    resolved_template = template or '误区反问式'
    if '?' not in candidate and '？' not in candidate:
        resolved_template = '反差好奇式'
    if topic_title_issue(candidate, category=category, template=resolved_template):
        return None
    hook = _merge_optimize_hook(candidate_hook=None, original_hook=row.get('hook'))
    preview = score_title(candidate, category=category, template=resolved_template, hook=hook)
    if preview.total < SCORE_THRESHOLD:
        return None
    item = {'title': candidate, 'category': category, 'template': resolved_template, 'hook': hook}
    return (candidate, hook, item)

class TopicMgr:

    def list_titles(self, *, status: str | None=None, limit: int=50, offset: int=0) -> dict:
        """返回 {items: [...], total: N}。"""
        with atomic():
            items = repo_title.list_titles(status=status, limit=limit, offset=offset)
            total = repo_title.count_titles(status=status)
            return {'items': items, 'total': total}

    def update_title(self, title_id: int, *, title: str | None=None, category: str | None=None, template: str | None=None, hook: str | None=None) -> dict:
        fields: dict[str, str] = {}
        if title is not None:
            fields['title'] = title
        if category is not None:
            fields['category'] = category
        if template is not None:
            fields['template'] = template
        if hook is not None:
            fields['hook'] = hook
        return repo_title.update_title(title_id, **fields)

    def add_topics(self, items: list[dict], *, source: str='manual', deduplicate_keyword: bool=False) -> dict:
        settings = get_settings()
        max_len = settings.max_title_length
        added: list[dict] = []
        skipped = 0
        seen_keywords: set[str] = set()
        with atomic():
            if deduplicate_keyword:
                seen_keywords = _existing_keywords()
            for item in items:
                raw_title = str(item.get('title') or '').strip()
                if not raw_title:
                    skipped += 1
                    logger.warning('[TOPIC] skip add: empty title')
                    continue
                title = normalize_title(raw_title, max_len=max_len)
                if deduplicate_keyword:
                    raw_kw = item.get('keyword') or ''
                    keywords = [k.strip() for k in raw_kw.split(',') if k.strip()]
                    if not keywords:
                        kw = None
                    else:
                        hit = any((k in seen_keywords for k in keywords))
                        if hit:
                            skipped += 1
                            logger.warning('[TOPIC] skip add: keyword conflict title=%r keywords=%s', title, keywords)
                            continue
                        kw = raw_kw
                        for k in keywords:
                            seen_keywords.add(k)
                else:
                    kw = None
                row = repo_title.insert_title(title=title, category=item.get('category'), template=item.get('template'), hook=item.get('hook'), source=source, keyword=kw if deduplicate_keyword else None)
                if row is None:
                    skipped += 1
                    logger.warning('[TOPIC] skip add: duplicate title=%r', title)
                else:
                    added.append(row)
        return {'added': added, 'skipped': skipped, 'count': len(added)}

    def generate_topics(self, theme: str, *, count: int=10, category: str | None=None, keywords: str | list[str] | None=None, system_prompt: str | None=None, user_prompt: str | None=None, operation: TopicLlmOperation='generate') -> list[dict[str, str]]:
        return llm_mgr.generate_topics(theme, count=count, category=category, keywords=keywords, system_prompt=system_prompt, user_prompt=user_prompt, operation=operation)

    def generate_and_save(self, theme: str, *, count: int=10, category: str | None=None, keywords: str | list[str] | None=None, system_prompt: str | None=None, user_prompt: str | None=None) -> dict:
        resolved = normalize_category(category)
        logger.info('[TOPIC] save start theme=%r category=%s count=%d', theme, resolved, count)
        topics = self.generate_topics(theme, count=count, category=resolved, keywords=keywords, system_prompt=system_prompt, user_prompt=user_prompt, operation='save')
        result = self.add_topics(topics, source='llm', deduplicate_keyword=True)
        if result['added']:
            new_ids = [row['id'] for row in result['added']]
            self.score_titles(title_ids=new_ids)
        logger.info('[TOPIC] save done theme=%r generated=%d added=%d skipped=%d', theme, len(topics), result['count'], result['skipped'])
        return {'category': resolved, 'theme': theme, 'generated': len(topics), **result}

    def optimize_title(self, title_id: int, direction: str | None=None) -> dict:
        with atomic():
            row = repo_title.get_title(title_id)
        if row['status'] == 'enqueued':
            raise ValueError('enqueued title cannot be optimized')
        settings = get_settings()
        template = row.get('template')
        category = normalize_category(row.get('category'))
        system_prompt = build_topic_optimize_system_prompt(max_title_len=settings.max_title_length, category=category)
        user_prompt_base = build_topic_optimize_user_prompt(title=row['title'], category=category, template=template, hook=row.get('hook'), direction=direction)
        user_prompt = user_prompt_base
        logger.info('[TOPIC] optimize start id=%d title=%r category=%r', title_id, row['title'], category)
        item: dict | None = None
        new_title = ''
        resolved_hook: str | None = None
        last_exc: Exception | None = None
        llm_ok = False
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                topics = self.generate_topics('', count=1, category=category, system_prompt=system_prompt, user_prompt=user_prompt, operation='optimize')
            except ValueError as exc:
                last_exc = exc
                if attempt + 1 >= max_attempts:
                    break
                logger.warning('[TOPIC] optimize parse rejected id=%d attempt=%d/%d reason=%s', title_id, attempt + 1, max_attempts, exc)
                user_prompt = f'{user_prompt_base}\n\n【重试】上一轮 title 未通过校验，须有「认知+反转」结构，后半句必须有口语态度（了、明明、反而...），禁止说明书式陈述。\n{exc}'
                continue
            item = topics[0]
            item['category'] = category
            if template:
                item['template'] = template
            new_title = normalize_title(item['title'], max_len=settings.max_title_length)
            if not new_title:
                last_exc = ValueError('LLM returned empty title')
                continue
            resolved_template = template or item.get('template')
            resolved_hook = _merge_optimize_hook(candidate_hook=item.get('hook'), original_hook=row.get('hook'))
            preview = score_title(new_title, category=category, template=resolved_template, hook=resolved_hook)
            if preview.total >= SCORE_THRESHOLD:
                llm_ok = True
                break
            reason = preview.rejected_reason or f'总分 {preview.total} 低于阈值 {SCORE_THRESHOLD}'
            last_exc = ValueError(f'optimized title rejected: {reason}')
            if attempt + 1 >= max_attempts:
                break
            logger.warning('[TOPIC] optimize score rejected id=%d attempt=%d/%d title=%r score=%d', title_id, attempt + 1, max_attempts, new_title, preview.total)
            user_prompt = f'{user_prompt_base}\n\n【重试】标题「{new_title}」得分 {preview.total}，须≥{SCORE_THRESHOLD}。{reason} 须保持「认知+反转」结构后半句有态度；title 含可见载体与图解词（如油轮、规则）；若 hook 为空须输出 15-30 字点击动机。'
        if not llm_ok:
            fallback = _optimize_fallback_title(row, max_title_len=settings.max_title_length, category=category, template=template)
            if fallback:
                new_title, resolved_hook, item = fallback
                logger.info('[TOPIC] optimize fallback id=%d title=%r', title_id, new_title)
            elif last_exc is not None:
                raise last_exc
            else:
                raise ValueError('optimize failed')
        assert item is not None
        item['hook'] = resolved_hook
        with atomic():
            if new_title != row['title']:
                existing = repo_title.find_by_titles([new_title])
                if new_title in existing:
                    raise ValueError(f'title already exists: {new_title}')
            updated = repo_title.update_title(title_id, title=new_title, category=item.get('category'), template=item.get('template'), hook=resolved_hook, score=None, score_detail=None, status='pending')
        score_result = self.score_titles([title_id])
        scored = score_result['scored'][0] if score_result['scored'] else updated
        logger.info('[TOPIC] optimize done id=%d old=%r new=%r score=%s', title_id, row['title'], scored['title'], scored.get('score'))
        return {'title': scored, 'previous': row}

    def score_titles(self, title_ids: list[int] | None=None) -> dict:
        with atomic():
            if title_ids:
                rows = repo_title.list_by_ids(title_ids)
            else:
                rows = repo_title.list_pending_score()
        pending: list[tuple[int, object, str]] = []
        for row in rows:
            result = score_title(row['title'], category=row.get('category'), template=row.get('template'), hook=row.get('hook'))
            pending.append((int(row['id']), result, status_from_score(result)))
        scored: list[dict] = []
        with atomic():
            for title_id, result, status in pending:
                updated = repo_title.update_title(title_id, score=result.total, score_detail=result.to_dict(), status=status)
                scored.append(updated)
        return {'scored': scored, 'count': len(scored)}

    def delete_titles(self, title_ids: list[int]) -> dict:
        with atomic():
            deleted = repo_title.delete_titles(title_ids)
        return {'deleted': deleted, 'ids': title_ids}

    def delete_low_score_titles(self, max_score: int) -> dict:
        with atomic():
            ids = repo_title.list_ids_below_score(max_score)
            deleted = repo_title.delete_titles(ids)
        logger.info('[TOPIC] delete low score max_score=%d deleted=%d ids=%s', max_score, deleted, ids)
        return {'deleted': deleted, 'ids': ids, 'max_score': max_score}

    def enqueue_titles(self, title_ids: list[int] | None=None, *, skip_publish: bool=True, run_mode: str='script') -> dict:
        if run_mode not in _RUN_MODES:
            raise ValueError(f'run_mode must be one of {sorted(_RUN_MODES)}')
        with atomic():
            if title_ids:
                rows = repo_title.list_by_ids(title_ids)
            else:
                rows = repo_title.list_queued()
            jobs: list[dict] = []
            job_hooks: list[str | None] = []
            for row in rows:
                if row['status'] != 'queued':
                    continue
                if row.get('job_id'):
                    continue
                is_history = normalize_category(row.get('category')) == CATEGORY_HISTORY
                seg_sec = 15 if not is_history else 10
                hook = (row.get('hook') or '').strip() or None
                job = repo_job.create_job(row['title'], skip_publish=skip_publish, stage='script', status='pending', info=merge_job_script_params(None, orientation=ORIENTATION_LANDSCAPE, content_style=CONTENT_STYLE_HISTORICAL_MYSTERY if is_history else None, estimated_duration_min=DEFAULT_HISTORY_VIDEO_MINUTES if is_history else DEFAULT_STANDARD_VIDEO_MINUTES, segment_target_sec=seg_sec, skip_title_optimize=True, generate_image_prompts=True, supplementary_info=hook))
                repo_title.update_title(row['id'], status='enqueued', job_id=job['id'])
                jobs.append(job)
                job_hooks.append(hook)
        script_kwargs = {'skip_title_optimize': True, 'generate_image_prompts': True}
        if run_mode == 'script':
            for job, hook in zip(jobs, job_hooks):
                job_mgr.run_script(job['id'], to_end=False, supplementary_info=hook, **script_kwargs)
        elif run_mode == 'full':
            for job, hook in zip(jobs, job_hooks):
                job_mgr.run_script(job['id'], to_end=True, supplementary_info=hook, **script_kwargs)
        logger.info('[TOPIC] enqueue done count=%d run_mode=%s job_ids=%s', len(jobs), run_mode, [job['id'] for job in jobs])
        return {'jobs': jobs, 'count': len(jobs), 'run_mode': run_mode}
topic_mgr = TopicMgr()
__all__ = ['SCORE_THRESHOLD', 'ScoreResult', 'TopicMgr', 'score_title', 'status_from_score', 'topic_mgr']
