from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from app.services.llm.llm_agnes import AgnesApiKey
from app.services.segment.image.image_agnes import AgnesImageProvider, _to_agnes_size


def test_to_agnes_size() -> None:
    assert _to_agnes_size("720*1280") == "720x1280"
    assert _to_agnes_size("1920x1080") == "1920x1080"


def test_generate_downloads_url(tmp_path: Path) -> None:
    provider = AgnesImageProvider()
    output = tmp_path / "1.png"

    mock_post = MagicMock()
    mock_post.json.return_value = {"data": [{"url": "https://example.com/out.png"}]}
    mock_post.raise_for_status = MagicMock()

    mock_img = MagicMock()
    mock_img.content = b"png-bytes"
    mock_img.raise_for_status = MagicMock()

    with (
        patch(
            "app.services.segment.image.image_agnes.agnes_api_keys",
            return_value=[AgnesApiKey("primary", "test-key")],
        ),
        patch.object(provider, "_request", return_value=mock_post) as mock_request,
        patch("app.services.segment.image.image_agnes.requests.get", return_value=mock_img),
        patch.object(provider, "_verify_image", return_value=True),
    ):
        provider.generate("测试 prompt", output, size="720*1280")

    mock_request.assert_called_once()
    assert mock_request.call_args.kwargs["api_key"] == "test-key"
    payload = mock_request.call_args.kwargs["json"]
    assert payload["model"] == provider._model  # noqa: SLF001
    assert payload["size"] == "720x1280"
    assert payload["extra_body"] == {"response_format": "url"}
    assert output.read_bytes() == b"png-bytes"


def test_generate_retries_verify_up_to_three_times(tmp_path: Path) -> None:
    provider = AgnesImageProvider()
    output = tmp_path / "1.png"
    output.write_bytes(b"png")

    with (
        patch(
            "app.services.segment.image.image_agnes.agnes_api_keys",
            return_value=[AgnesApiKey("primary", "test-key")],
        ),
        patch.object(provider, "_generate_with_key", return_value=output) as mock_gen,
        patch.object(provider, "_verify_image", side_effect=[False, False, True]) as mock_verify,
    ):
        result = provider.generate(
            "prompt",
            output,
            expected_speakers=["昭昭", "灿灿"],
            content_style="daily_story",
        )

    assert result == output
    assert mock_gen.call_count == 3
    assert mock_verify.call_count == 3
    assert mock_verify.call_args.kwargs["content_style"] == "daily_story"


def test_parse_item_answer_handles_bu_shi() -> None:
    assert AgnesImageProvider._parse_item_answer("不是") == "no"
    assert AgnesImageProvider._parse_item_answer("否") == "no"
    assert AgnesImageProvider._parse_item_answer("是") == "yes"
    assert AgnesImageProvider._parse_item_answer("是的，基本一致") == "yes"
    assert AgnesImageProvider._parse_item_answer("无昭昭") == "na_zhao"


def test_evaluate_verify_response_zhao_braid_and_cast() -> None:
    ok = (
        "项1: 是\n"
        "项2: 否\n"
        "项3: 否\n"
        "项4: 是\n"
    )
    assert AgnesImageProvider._evaluate_verify_response(
        ok, ["scene", "zhao_braid", "extra_arms", "cast_count"]
    )
    bad_braid = "项1: 是\n项2: 是\n项3: 否\n项4: 是\n"
    assert not AgnesImageProvider._evaluate_verify_response(
        bad_braid, ["scene", "zhao_braid", "extra_arms", "cast_count"]
    )
    # 「不是」不得当成「是」
    bu_shi = "项1: 是\n项2: 不是\n项3: 否\n"
    assert AgnesImageProvider._evaluate_verify_response(
        bu_shi, ["scene", "zhao_braid", "extra_arms"]
    )


def test_build_verify_checklist_daily_includes_zhao() -> None:
    items, user = AgnesImageProvider._build_verify_checklist(
        prompt="客厅对峙",
        expected_speakers=["昭昭", "灿灿"],
        content_style="daily_story",
    )
    ids = [cid for cid, _ in items]
    assert ids == ["scene", "zhao_braid", "extra_arms", "cast_count"]
    assert "昭昭" in user
    assert "发言角色" in user

    items2, user2 = AgnesImageProvider._build_verify_checklist(
        prompt="电池剖面",
        expected_speakers=None,
        content_style="science_child",
    )
    assert [cid for cid, _ in items2] == ["scene", "extra_arms"]
    assert "昭昭" not in user2


def test_generate_switches_to_backup_key_on_quota(tmp_path: Path) -> None:
    provider = AgnesImageProvider()
    output = tmp_path / "1.png"
    output.write_bytes(b"png")

    from app.services.llm.llm_agnes import AgnesQuotaExceeded

    with (
        patch(
            "app.services.segment.image.image_agnes.agnes_api_keys",
            return_value=[
                AgnesApiKey("free", "free-key"),
                AgnesApiKey("primary", "main-key"),
            ],
        ),
        patch.object(
            provider,
            "_generate_with_key",
            side_effect=[AgnesQuotaExceeded("429"), output],
        ) as mock_generate,
        patch.object(provider, "_verify_image", return_value=True),
    ):
        provider.generate("测试 prompt", output, size="720*1280")

    assert mock_generate.call_count == 2
    assert mock_generate.call_args_list[0].args[0].value == "free-key"
    assert mock_generate.call_args_list[1].args[0].value == "main-key"


def test_generate_without_keys_raises_unless_mock(tmp_path: Path, monkeypatch) -> None:
    provider = AgnesImageProvider()
    output = tmp_path / "1.png"
    monkeypatch.setattr(
        "app.services.segment.image.image_agnes.get_settings",
        lambda: MagicMock(mock_mode=False),
    )
    with (
        patch(
            "app.services.segment.image.image_agnes.agnes_api_keys",
            return_value=[],
        ),
        patch.object(provider, "_fallback") as mock_fallback,
    ):
        try:
            provider.generate("测试", output)
            raise AssertionError("expected RuntimeError")
        except RuntimeError as exc:
            assert "未配置" in str(exc)
        mock_fallback.generate.assert_not_called()


def test_generate_without_keys_uses_fallback_in_mock(
    tmp_path: Path, monkeypatch
) -> None:
    provider = AgnesImageProvider()
    output = tmp_path / "1.png"
    monkeypatch.setattr(
        "app.services.segment.image.image_agnes.get_settings",
        lambda: MagicMock(mock_mode=True),
    )
    with (
        patch(
            "app.services.segment.image.image_agnes.agnes_api_keys",
            return_value=[],
        ),
        patch.object(
            provider,
            "_fallback",
            MagicMock(generate=MagicMock(return_value=output)),
        ) as mock_fallback,
    ):
        result = provider.generate("测试", output)
    assert result == output
    mock_fallback.generate.assert_called_once()


def test_concurrent_submit_staggered() -> None:
    import time

    import gevent

    from app.config import get_settings

    settings = get_settings()
    workers = max(2, settings.image_max_workers)
    stagger = max(0.5, settings.image_submit_interval_sec)

    AgnesImageProvider._inflight = None  # noqa: SLF001
    with (
        patch.object(get_settings(), "image_max_workers", workers),
        patch.object(get_settings(), "image_submit_interval_sec", stagger),
    ):
        provider = AgnesImageProvider()
        starts: list[float] = []

        def worker() -> None:
            provider._acquire_submit_slot()  # noqa: SLF001
            starts.append(time.monotonic())
            gevent.sleep(0.05)
            provider._release_submit_slot()  # noqa: SLF001

        green_lets = [gevent.spawn(worker) for _ in range(workers)]
        gevent.joinall(green_lets)

    assert len(starts) == workers
    starts.sort()
    for i in range(1, workers):
        gap = starts[i] - starts[i - 1]
        assert gap >= stagger * 0.8, f"expected stagger ~{stagger}s, got {gap:.2f}s"
