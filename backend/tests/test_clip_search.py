"""聚合视频片段搜索单元测试。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.clip_search.aggregator import list_provider_status, search_clips
from app.services.clip_search.providers.pexels import search_pexels
from app.services.clip_search.providers.pixabay import search_pixabay


@pytest.fixture
def settings():
    return SimpleNamespace(
        pexels_api_key="pexels-key",
        pixabay_api_key="pixabay-key",
        clip_search_timeout_sec=8.0,
    )


def test_list_provider_status(settings):
    rows = list_provider_status(settings)
    names = {row["provider"] for row in rows}
    assert names == {"pexels", "pixabay", "nasa"}
    nasa = next(row for row in rows if row["provider"] == "nasa")
    assert nasa["available"] is True


def test_search_clips_requires_query(settings):
    with pytest.raises(ValueError, match="query"):
        search_clips("  ", settings=settings)


def test_search_clips_merges_providers(monkeypatch, settings):
    def fake_pexels(query, **kwargs):
        from app.services.clip_search.models import StockClip

        return [
            StockClip(
                id="pexels:1",
                provider="pexels",
                title="magnet pexels",
                preview_url="https://example.com/p.jpg",
                video_url="https://example.com/p.mp4",
                page_url="https://pexels.com/v/1",
                license="Pexels License",
                duration_sec=12,
            )
        ]

    def fake_pixabay(query, **kwargs):
        from app.services.clip_search.models import StockClip

        return [
            StockClip(
                id="pixabay:2",
                provider="pixabay",
                title="magnet pixabay",
                preview_url="https://example.com/x.jpg",
                video_url="https://example.com/x.mp4",
                page_url="https://pixabay.com/v/2",
                license="Pixabay License",
                duration_sec=10,
            )
        ]

    def fake_nasa(query, **kwargs):
        return []

    monkeypatch.setattr("app.services.clip_search.aggregator.search_pexels", fake_pexels)
    monkeypatch.setattr("app.services.clip_search.aggregator.search_pixabay", fake_pixabay)
    monkeypatch.setattr("app.services.clip_search.aggregator.search_nasa", fake_nasa)

    result = search_clips("magnet", per_page=10, settings=settings)
    assert result.query == "magnet"
    assert len(result.clips) == 2
    assert {clip.provider for clip in result.clips} == {"pexels", "pixabay"}


def test_search_pexels_parses_response(monkeypatch):
    def fake_get_json(url, **kwargs):
        return {
            "videos": [
                {
                    "id": 99,
                    "duration": 8,
                    "url": "https://www.pexels.com/video/99/",
                    "image": "https://images.pexels.com/videos/99/preview.jpg",
                    "video_files": [
                        {"width": 1280, "height": 720, "link": "https://cdn.example/99-hd.mp4", "quality": "hd"}
                    ],
                    "user": {"name": "Alice"},
                }
            ]
        }

    monkeypatch.setattr("app.services.clip_search.providers.pexels.get_json", fake_get_json)
    clips = search_pexels("test", api_key="k", per_page=5, orientation=None, timeout=5)
    assert len(clips) == 1
    assert clips[0].id == "pexels:99"
    assert clips[0].video_url.endswith("99-hd.mp4")
    assert clips[0].author == "Alice"


def test_search_pexels_prefers_sd_over_uhd(monkeypatch):
    def fake_get_json(url, **kwargs):
        return {
            "videos": [
                {
                    "id": 1,
                    "duration": 5,
                    "url": "https://www.pexels.com/video/1/",
                    "image": "https://images.pexels.com/videos/1/preview.jpg",
                    "video_files": [
                        {
                            "width": 3840,
                            "height": 2160,
                            "link": "https://cdn.example/1-uhd.mp4",
                            "quality": "uhd",
                            "file_type": "video/mp4",
                        },
                        {
                            "width": 1280,
                            "height": 720,
                            "link": "https://cdn.example/1-hd.mp4",
                            "quality": "hd",
                            "file_type": "video/mp4",
                        },
                        {
                            "width": 640,
                            "height": 360,
                            "link": "https://cdn.example/1-sd.mp4",
                            "quality": "sd",
                            "file_type": "video/mp4",
                        },
                    ],
                }
            ]
        }

    monkeypatch.setattr("app.services.clip_search.providers.pexels.get_json", fake_get_json)
    clips = search_pexels("test", api_key="k", per_page=5, orientation=None, timeout=5)
    assert clips[0].video_url.endswith("1-sd.mp4")


def test_validate_preview_url():
    from app.services.clip_search.preview_proxy import validate_preview_url

    ok = validate_preview_url("https://videos.pexels.com/video-files/abc/abc.mp4")
    assert ok.startswith("https://videos.pexels.com")

    with pytest.raises(ValueError, match="not allowed"):
        validate_preview_url("https://evil.example/video.mp4")


def test_search_pixabay_parses_response(monkeypatch):
    def fake_get_json(url, **kwargs):
        return {
            "hits": [
                {
                    "id": 7,
                    "tags": "water, drop",
                    "duration": 11,
                    "pageURL": "https://pixabay.com/videos/id-7/",
                    "user": "bob",
                    "videos": {
                        "medium": {
                            "url": "https://cdn.example/7.mp4",
                            "width": 1280,
                            "height": 720,
                        }
                    },
                }
            ]
        }

    monkeypatch.setattr("app.services.clip_search.providers.pixabay.get_json", fake_get_json)
    clips = search_pixabay("water", api_key="k", per_page=5, timeout=5)
    assert len(clips) == 1
    assert clips[0].title == "water"
    assert clips[0].provider == "pixabay"
