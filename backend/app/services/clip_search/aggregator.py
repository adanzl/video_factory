"""多源视频片段搜索聚合。"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from app.config import Config, get_settings
from app.services.clip_search.language import pexels_locale, pixabay_lang
from app.services.clip_search.models import ClipSearchResponse, ProviderSearchResult, StockClip
from app.services.clip_search.providers import search_nasa, search_pexels, search_pixabay

logger = logging.getLogger(__name__)

_ALL_PROVIDERS = ("pexels", "pixabay", "nasa")


def _clip_sort_key(clip: StockClip) -> tuple[int, float]:
    duration = clip.duration_sec
    if duration is None:
        return (0, 999.0)
    if 5 <= duration <= 20:
        tier = 3
    elif duration <= 30:
        tier = 2
    else:
        tier = 1
    return (-tier, abs(duration - 12))


def _merge_clips(provider_results: list[ProviderSearchResult]) -> list[StockClip]:
    buckets: list[list[StockClip]] = []
    for row in provider_results:
        if row.status == "ok" and row.clips:
            buckets.append(list(row.clips))
    if not buckets:
        return []

    merged: list[StockClip] = []
    seen: set[str] = set()
    max_len = max(len(bucket) for bucket in buckets)
    for idx in range(max_len):
        for bucket in buckets:
            if idx >= len(bucket):
                continue
            clip = bucket[idx]
            if clip.id in seen:
                continue
            seen.add(clip.id)
            merged.append(clip)
    merged.sort(key=_clip_sort_key)
    return merged


def _search_one(
    provider: str,
    query: str,
    *,
    settings: Config,
    per_provider: int,
    orientation: str | None,
    language: str | None,
) -> ProviderSearchResult:
    timeout = settings.clip_search_timeout_sec
    if provider == "pexels":
        if not settings.pexels_api_key:
            return ProviderSearchResult(
                provider=provider,
                status="skipped",
                reason="PEXELS_API_KEY not configured",
            )
        try:
            clips = tuple(
                search_pexels(
                    query,
                    api_key=settings.pexels_api_key,
                    per_page=per_provider,
                    orientation=orientation,
                    locale=pexels_locale(language),
                    timeout=timeout,
                )
            )
            return ProviderSearchResult(provider=provider, status="ok", count=len(clips), clips=clips)
        except Exception as exc:
            logger.warning("pexels search failed: %s", exc)
            return ProviderSearchResult(provider=provider, status="error", reason=str(exc))

    if provider == "pixabay":
        if not settings.pixabay_api_key:
            return ProviderSearchResult(
                provider=provider,
                status="skipped",
                reason="PIXABAY_API_KEY not configured",
            )
        try:
            clips = tuple(
                search_pixabay(
                    query,
                    api_key=settings.pixabay_api_key,
                    per_page=per_provider,
                    lang=pixabay_lang(language),
                    timeout=timeout,
                )
            )
            return ProviderSearchResult(provider=provider, status="ok", count=len(clips), clips=clips)
        except Exception as exc:
            logger.warning("pixabay search failed: %s", exc)
            return ProviderSearchResult(provider=provider, status="error", reason=str(exc))

    if provider == "nasa":
        try:
            clips = tuple(
                search_nasa(
                    query,
                    per_page=per_provider,
                    timeout=timeout,
                )
            )
            return ProviderSearchResult(provider=provider, status="ok", count=len(clips), clips=clips)
        except Exception as exc:
            logger.warning("nasa search failed: %s", exc)
            return ProviderSearchResult(provider=provider, status="error", reason=str(exc))

    return ProviderSearchResult(provider=provider, status="skipped", reason="unknown provider")


def list_provider_status(settings: Config | None = None) -> list[dict]:
    settings = settings or get_settings()
    rows: list[dict] = []
    for name in _ALL_PROVIDERS:
        if name == "pexels":
            available = bool(settings.pexels_api_key)
            reason = None if available else "PEXELS_API_KEY not configured"
        elif name == "pixabay":
            available = bool(settings.pixabay_api_key)
            reason = None if available else "PIXABAY_API_KEY not configured"
        else:
            available = True
            reason = None
        rows.append(
            {
                "provider": name,
                "available": available,
                "requires_api_key": name != "nasa",
                "reason": reason,
            }
        )
    return rows


def search_clips(
    query: str,
    *,
    per_page: int = 24,
    providers: tuple[str, ...] | None = None,
    orientation: str | None = None,
    language: str | None = None,
    settings: Config | None = None,
) -> ClipSearchResponse:
    settings = settings or get_settings()
    cleaned = query.strip()
    if not cleaned:
        raise ValueError("query is required")

    selected = providers or _ALL_PROVIDERS
    unknown = [name for name in selected if name not in _ALL_PROVIDERS]
    if unknown:
        raise ValueError(f"unknown providers: {', '.join(unknown)}")

    per_provider = max(3, min(20, (per_page + len(selected) - 1) // len(selected)))
    provider_results: list[ProviderSearchResult] = []

    with ThreadPoolExecutor(max_workers=len(selected)) as pool:
        futures = {
            pool.submit(
                _search_one,
                name,
                cleaned,
                settings=settings,
                per_provider=per_provider,
                orientation=orientation,
                language=language,
            ): name
            for name in selected
        }
        for future in as_completed(futures):
            try:
                provider_results.append(future.result())
            except Exception as exc:
                name = futures[future]
                provider_results.append(
                    ProviderSearchResult(provider=name, status="error", reason=str(exc))
                )

    provider_results.sort(key=lambda row: _ALL_PROVIDERS.index(row.provider))
    merged = _merge_clips(provider_results)[:per_page]
    return ClipSearchResponse(
        query=cleaned,
        clips=tuple(merged),
        providers=tuple(provider_results),
    )
