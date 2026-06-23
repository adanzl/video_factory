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
                    "url": "https://www.pexels.com/video/discover-authentic-chinese-street-culture-36382074/",
                    "image": "https://images.pexels.com/videos/99/preview.jpg",
                    "video_files": [
                        {
                            "width": 1280,
                            "height": 720,
                            "link": "https://player.vimeo.com/external/342571552.hd.mp4?s=abc",
                            "quality": "hd",
                            "file_type": "video/mp4",
                        }
                    ],
                    "user": {"name": "Alice"},
                }
            ]
        }

    monkeypatch.setattr("app.services.clip_search.providers.pexels.get_json", fake_get_json)
    clips = search_pexels("test", api_key="k", per_page=5, orientation=None, timeout=5)
    assert len(clips) == 1
    assert clips[0].id == "pexels:99"
    assert clips[0].title == "discover authentic chinese street culture"
    assert clips[0].video_url.startswith("https://player.vimeo.com")
    assert clips[0].page_url.endswith("36382074/")
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


def test_search_pexels_prefers_vimeo_sd_over_pexels_uhd(monkeypatch):
    def fake_get_json(url, **kwargs):
        return {
            "videos": [
                {
                    "id": 36382074,
                    "duration": 10,
                    "url": "https://www.pexels.com/video/discover-authentic-chinese-street-culture-36382074/",
                    "image": "https://images.pexels.com/videos/36382074/preview.jpg",
                    "video_files": [
                        {
                            "width": 3840,
                            "height": 2160,
                            "link": "https://videos.pexels.com/video-files/36382074/15429717_3840_2160_25fps.mp4",
                            "quality": "uhd",
                            "file_type": "video/mp4",
                        },
                        {
                            "width": 1280,
                            "height": 720,
                            "link": "https://player.vimeo.com/external/123.sd.mp4?s=abc",
                            "quality": "sd",
                            "file_type": "video/mp4",
                        },
                    ],
                }
            ]
        }

    monkeypatch.setattr("app.services.clip_search.providers.pexels.get_json", fake_get_json)
    clips = search_pexels("test", api_key="k", per_page=5, orientation=None, timeout=5)
    assert clips[0].video_url.startswith("https://player.vimeo.com")


def test_preview_streams_video(monkeypatch):
    from app.services.clip_search.preview_proxy import proxy_clip_preview

    class FakeUpstream:
        status_code = 200
        headers = {"Content-Type": "video/mp4", "Content-Length": "5", "Accept-Ranges": "bytes"}

        def iter_content(self, chunk_size=0):
            _ = chunk_size
            yield b"12345"

        def close(self):
            return None

    monkeypatch.setattr(
        "app.services.clip_search.preview_proxy.requests.get",
        lambda *args, **kwargs: FakeUpstream(),
    )

    from flask import Flask

    app = Flask(__name__)
    with app.test_request_context("/preview"):
        response = proxy_clip_preview(
            "https://videos.pexels.com/video-files/36382074/15429717_3840_2160_25fps.mp4"
        )
        assert response.status_code == 200
        assert b"".join(response.response) == b"12345"
        assert response.headers["Content-Type"] == "video/mp4"


def test_preview_upstream_error(monkeypatch):
    from app.services.clip_search.preview_proxy import proxy_clip_preview

    class FakeUpstream:
        status_code = 403
        headers = {}

        def close(self):
            return None

    monkeypatch.setattr(
        "app.services.clip_search.preview_proxy.requests.get",
        lambda *args, **kwargs: FakeUpstream(),
    )

    from flask import Flask

    app = Flask(__name__)
    with app.test_request_context("/preview"):
        with pytest.raises(ValueError, match="403"):
            proxy_clip_preview(
                "https://videos.pexels.com/video-files/36382074/15429717_3840_2160_25fps.mp4"
            )


def test_validate_preview_url():
    from app.services.clip_search.preview_proxy import validate_preview_url

    ok = validate_preview_url("https://videos.pexels.com/video-files/abc/abc.mp4")
    assert ok.startswith("https://videos.pexels.com")

    vimeo = validate_preview_url(
        "https://player.vimeo.com/external/342571552.sd.mp4?s=abc&profile_id=165"
    )
    assert vimeo.startswith("https://player.vimeo.com")

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
                    "picture_id": "529927645",
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
    assert clips[0].video_url.endswith("7.mp4")
    assert clips[0].preview_url == "https://i.vimeocdn.com/video/529927645_640x360.jpg"


def test_download_stock_clip_to_segment(tmp_path, monkeypatch):
    from app.services.clip_search.download import download_stock_clip_to_segment

    media_dir = tmp_path / "42"
    segment = {"segment_index": 3, "duration_sec": 5.0}
    job = {"id": 42, "pipeline": "standard", "info": '{"orientation":"portrait"}'}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def iter_content(self, chunk_size=0):
            _ = chunk_size
            yield b"fake-video"

    monkeypatch.setattr(
        "app.services.clip_search.download.requests.get",
        lambda *args, **kwargs: FakeResponse(),
    )
    monkeypatch.setattr(
        "app.services.clip_search.download.probe_duration",
        lambda path: 8.0,
    )

    captured: dict[str, object] = {}

    def fake_fit(src, dst, duration, *, width, height):
        captured["duration"] = duration
        captured["size"] = (width, height)
        dst.write_bytes(b"normalized")
        return dst

    monkeypatch.setattr(
        "app.services.clip_search.download.fit_video_duration",
        fake_fit,
    )

    output = download_stock_clip_to_segment(
        job=job,
        media_dir=media_dir,
        segment=segment,
        video_url="https://videos.pexels.com/video-files/abc/abc.mp4",
    )

    assert output == media_dir / "segments" / "3.mp4"
    assert output.is_file()
    assert captured["duration"] == 5.0


def test_normalize_search_language():
    from app.services.clip_search.language import (
        normalize_search_language,
        pexels_locale,
        pixabay_lang,
    )

    assert normalize_search_language(None) is None
    assert normalize_search_language("") is None
    assert normalize_search_language("zh") == "zh"
    assert normalize_search_language("中文") == "zh"
    assert normalize_search_language("en") == "en"
    assert normalize_search_language("英文") == "en"
    assert pexels_locale("zh") == "zh-CN"
    assert pexels_locale("en") == "en-US"
    assert pexels_locale(None) is None
    assert pixabay_lang("zh") == "zh"
    assert pixabay_lang("en") == "en"


def test_parse_pixabay_query_payload():
    from app.services.clip_search.query_rewrite_prompts import parse_pixabay_query_payload

    assert parse_pixabay_query_payload({"search_query": "magnet experiment"}) == "magnet experiment"
    with pytest.raises(ValueError, match="missing"):
        parse_pixabay_query_payload({})


def test_rewrite_ai_search_query_uses_llm(monkeypatch):
    from app.services.clip_search.query_rewrite import rewrite_ai_search_query

    monkeypatch.setattr(
        "app.services.clip_search.query_rewrite.llm_mgr.rewrite_pixabay_query",
        lambda query, *, language=None: "magnet experiment",
    )
    assert rewrite_ai_search_query("磁铁实验", language="zh") == "magnet experiment"


def test_search_clips_original_mode(monkeypatch, settings):
    captured: dict[str, str] = {}

    def fail(*args, **kwargs):
        raise AssertionError("LLM should not be called in original mode")

    def fake_pexels(query, **kwargs):
        from app.services.clip_search.models import StockClip

        captured["pexels"] = query
        captured["pexels_lang"] = kwargs.get("locale")
        return [
            StockClip(
                id="pexels:1",
                provider="pexels",
                title="p",
                preview_url="https://example.com/p.jpg",
                video_url="https://example.com/p.mp4",
                page_url="https://pexels.com/v/1",
                license="Pexels License",
            )
        ]

    monkeypatch.setattr(
        "app.services.clip_search.aggregator.rewrite_ai_search_query",
        fail,
    )
    monkeypatch.setattr("app.services.clip_search.aggregator.search_pexels", fake_pexels)
    monkeypatch.setattr("app.services.clip_search.aggregator.search_pixabay", lambda *a, **k: [])
    monkeypatch.setattr("app.services.clip_search.aggregator.search_nasa", lambda *a, **k: [])

    result = search_clips("磁铁", language="zh", search_mode="original", per_page=10, settings=settings)
    assert captured["pexels"] == "磁铁"
    assert captured["pexels_lang"] == "zh-CN"
    assert result.search_mode == "original"
    assert result.resolved_query is None


def test_search_clips_ai_mode(monkeypatch, settings):
    captured: dict[str, str] = {}

    def fake_rewrite(query, *, language=None):
        captured["rewrite_input"] = query
        captured["rewrite_lang"] = language
        return "rewritten query"

    def fake_pexels(query, **kwargs):
        from app.services.clip_search.models import StockClip

        captured["pexels"] = query
        captured["pexels_lang"] = kwargs.get("locale")
        return [
            StockClip(
                id="pexels:1",
                provider="pexels",
                title="p",
                preview_url="https://example.com/p.jpg",
                video_url="https://example.com/p.mp4",
                page_url="https://pexels.com/v/1",
                license="Pexels License",
            )
        ]

    def fake_pixabay(query, **kwargs):
        from app.services.clip_search.models import StockClip

        captured["pixabay"] = query
        captured["pixabay_lang"] = kwargs.get("lang")
        return [
            StockClip(
                id="pixabay:2",
                provider="pixabay",
                title="x",
                preview_url="https://example.com/x.jpg",
                video_url="https://example.com/x.mp4",
                page_url="https://pixabay.com/v/2",
                license="Pixabay License",
            )
        ]

    monkeypatch.setattr(
        "app.services.clip_search.aggregator.rewrite_ai_search_query",
        fake_rewrite,
    )
    monkeypatch.setattr("app.services.clip_search.aggregator.search_pexels", fake_pexels)
    monkeypatch.setattr("app.services.clip_search.aggregator.search_pixabay", fake_pixabay)
    monkeypatch.setattr("app.services.clip_search.aggregator.search_nasa", lambda *a, **k: [])

    result = search_clips("磁铁实验", language="zh", search_mode="ai", per_page=10, settings=settings)
    assert captured["rewrite_input"] == "磁铁实验"
    assert captured["rewrite_lang"] == "zh"
    assert captured["pexels"] == "rewritten query"
    assert captured["pixabay"] == "rewritten query"
    assert captured["pexels_lang"] == "en-US"
    assert captured["pixabay_lang"] == "en"
    assert result.search_mode == "ai"
    assert result.resolved_query == "rewritten query"


def test_search_pexels_passes_locale(monkeypatch):
    captured: dict[str, object] = {}

    def fake_get_json(url, **kwargs):
        captured["params"] = kwargs.get("params")
        return {"videos": []}

    monkeypatch.setattr("app.services.clip_search.providers.pexels.get_json", fake_get_json)
    search_pexels(
        "磁铁",
        api_key="k",
        per_page=5,
        orientation=None,
        locale="zh-CN",
        timeout=5,
    )
    assert captured["params"]["locale"] == "zh-CN"


def test_search_pixabay_passes_lang(monkeypatch):
    captured: dict[str, object] = {}

    def fake_get_json(url, **kwargs):
        captured["params"] = kwargs.get("params")
        return {"hits": []}

    monkeypatch.setattr("app.services.clip_search.providers.pixabay.get_json", fake_get_json)
    search_pixabay("magnet", api_key="k", per_page=5, lang="en", timeout=5)
    assert captured["params"]["lang"] == "en"
