from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from app.services.llm.llm_agnes import AgnesApiKey
from app.services.segment.image.image_agnes import (
    AgnesImageProvider,
    AgnesImageVerifyFailed,
    _VERIFY_MAX_ATTEMPTS,
    _to_agnes_size,
)


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


def test_generate_retries_verify_until_pass(tmp_path: Path) -> None:
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
    assert _VERIFY_MAX_ATTEMPTS == 3


def test_generate_raises_after_verify_exhausted(tmp_path: Path) -> None:
    provider = AgnesImageProvider()
    output = tmp_path / "1.png"
    output.write_bytes(b"png")

    with (
        patch(
            "app.services.segment.image.image_agnes.agnes_api_keys",
            return_value=[AgnesApiKey("primary", "test-key")],
        ),
        patch.object(provider, "_generate_with_key", return_value=output),
        patch.object(provider, "_verify_image", return_value=False),
    ):
        try:
            provider.generate("prompt", output, content_style="daily_story")
            raise AssertionError("expected AgnesImageVerifyFailed")
        except AgnesImageVerifyFailed as exc:
            assert exc.output_path == output


def test_generate_verify_retry_rotates_keys(tmp_path: Path) -> None:
    provider = AgnesImageProvider()
    output = tmp_path / "1.png"
    output.write_bytes(b"png")
    free = AgnesApiKey("free", "free-key")
    primary = AgnesApiKey("primary", "main-key")

    with (
        patch(
            "app.services.segment.image.image_agnes.agnes_api_keys",
            return_value=[primary, free],
        ),
        patch.object(provider, "_generate_with_key", return_value=output) as mock_gen,
        patch.object(
            provider, "_verify_image", side_effect=[False, False, True]
        ),
    ):
        result = provider.generate("prompt", output)

    assert result == output
    assert mock_gen.call_count == 3
    used = [c.args[0].label for c in mock_gen.call_args_list]
    assert used == ["primary", "free", "primary"]


def test_parse_item_answer_handles_bu_shi() -> None:
    assert AgnesImageProvider._parse_item_answer("不是") == "no"
    assert AgnesImageProvider._parse_item_answer("否") == "no"
    assert AgnesImageProvider._parse_item_answer("是") == "yes"
    assert AgnesImageProvider._parse_item_answer("是的，基本一致") == "yes"
    assert AgnesImageProvider._parse_item_answer("无昭昭") == "na_zhao"
    assert AgnesImageProvider._parse_item_answer("无灿灿") == "na_can"
    assert AgnesImageProvider._parse_item_answer("无妈妈") == "na_mom"


def test_evaluate_verify_response_zhao_hair_and_cast() -> None:
    ids = ["scene", "zhao_hair", "can_hair", "mom_adult", "extra_arms", "cast_count"]
    ok = "项1: 是\n项2: 是\n项3: 是\n项4: 是\n项5: 是\n项6: 是\n"
    assert AgnesImageProvider._evaluate_verify_response(ok, ids)

    bad_zhao = "项1: 是\n项2: 否\n项3: 是\n项4: 是\n项5: 是\n项6: 是\n"
    assert not AgnesImageProvider._evaluate_verify_response(bad_zhao, ids)

    bad_can = "项1: 是\n项2: 是\n项3: 否\n项4: 是\n项5: 是\n项6: 是\n"
    assert not AgnesImageProvider._evaluate_verify_response(bad_can, ids)

    bad_mom = "项1: 是\n项2: 是\n项3: 是\n项4: 否\n项5: 是\n项6: 是\n"
    assert not AgnesImageProvider._evaluate_verify_response(bad_mom, ids)

    bad_arms = "项1: 是\n项2: 是\n项3: 是\n项4: 是\n项5: 否\n项6: 是\n"
    assert not AgnesImageProvider._evaluate_verify_response(bad_arms, ids)

    # 「不是」= 否 → 短发项失败
    bu_shi = "项1: 是\n项2: 不是\n项3: 是\n"
    assert not AgnesImageProvider._evaluate_verify_response(
        bu_shi, ["scene", "zhao_hair", "extra_arms"]
    )

    # 无昭昭 / 无灿灿 / 无妈妈 → 对应项放行
    na = "项1: 是\n项2: 无昭昭\n项3: 无灿灿\n项4: 无妈妈\n项5: 是\n项6: 是\n"
    assert AgnesImageProvider._evaluate_verify_response(na, ids)


def test_allowed_cast_for_verify() -> None:
    assert AgnesImageProvider._allowed_cast_for_verify(
        speakers=["昭昭", "灿灿"],
        content_style="daily_story",
    ) == ["昭昭", "灿灿"]
    assert AgnesImageProvider._allowed_cast_for_verify(
        speakers=["灿灿"],
        content_style="daily_story",
    ) == ["昭昭", "灿灿"]
    assert AgnesImageProvider._allowed_cast_for_verify(
        speakers=["妈妈"],
        content_style="daily_story",
    ) == ["昭昭", "灿灿", "妈妈"]
    assert AgnesImageProvider._allowed_cast_for_verify(
        speakers=["妈妈", "昭昭", "灿灿"],
        content_style="daily_story",
    ) == ["昭昭", "灿灿", "妈妈"]
    assert AgnesImageProvider._allowed_cast_for_verify(
        speakers=["旁白"],
        content_style="science_child",
    ) == ["旁白"]


def test_build_verify_checklist_daily_includes_zhao() -> None:
    items, user = AgnesImageProvider._build_verify_checklist(
        prompt="客厅对峙",
        expected_speakers=["昭昭", "灿灿", "妈妈"],
        content_style="daily_story",
    )
    ids = [cid for cid, _ in items]
    assert ids == [
        "scene",
        "zhao_hair",
        "can_hair",
        "mom_adult",
        "extra_arms",
        "cast_count",
    ]
    assert "昭昭" in user
    assert "灿灿" in user
    assert "成年女性" in user
    assert "不超过 3 个" in user
    assert "只数人头" in user
    assert "只能是：" not in user
    assert "禁止路人" not in user
    assert "恰好" not in user
    assert "蓝衣" not in user
    assert "短发男孩即昭昭" in user
    assert "男孩超短发" in user
    assert "波波头" in user
    assert "扎马尾的女孩即灿灿" in user
    assert "单侧高马尾" in user
    assert "最多 2 条" in user
    assert "照片墙" in user

    items_one, user_one = AgnesImageProvider._build_verify_checklist(
        prompt="只有昭昭",
        expected_speakers=["昭昭"],
        content_style="daily_story",
    )
    assert "zhao_hair" in [cid for cid, _ in items_one]
    assert "can_hair" not in [cid for cid, _ in items_one]
    assert "mom_adult" not in [cid for cid, _ in items_one]
    assert "cast_count" in [cid for cid, _ in items_one]
    assert "不超过 2 个" in user_one
    assert "只数人头" in user_one
    assert "只能是：" not in user_one

    # 无昭昭发言时不做短发项；有灿灿则检单马尾；人数按姐弟上限 2
    items_can, user_can = AgnesImageProvider._build_verify_checklist(
        prompt="只有灿灿",
        expected_speakers=["灿灿"],
        content_style="daily_story",
    )
    assert "zhao_hair" not in [cid for cid, _ in items_can]
    assert "can_hair" in [cid for cid, _ in items_can]
    assert "mom_adult" not in [cid for cid, _ in items_can]
    assert "cast_count" in [cid for cid, _ in items_can]
    assert "不超过 2 个" in user_can
    assert "只数人头" in user_can
    assert "单侧高马尾" in user_can

    items_mom, user_mom = AgnesImageProvider._build_verify_checklist(
        prompt="只有妈妈",
        expected_speakers=["妈妈"],
        content_style="daily_story",
    )
    assert "mom_adult" in [cid for cid, _ in items_mom]
    assert "成年女性" in user_mom
    assert "不超过 3 个" in user_mom
    assert "只数人头" in user_mom
    assert "只能是：" not in user_mom

    items2, user2 = AgnesImageProvider._build_verify_checklist(
        prompt="电池剖面",
        expected_speakers=None,
        content_style="science_child",
    )
    assert [cid for cid, _ in items2] == ["scene", "extra_arms"]
    assert "昭昭" not in user2


def test_strip_prompt_for_verify_drops_daily_wrap() -> None:
    wrapped = (
        "基于参考图调整人物动作，保留昭昭：7岁男孩。"
        "儿童情绪涂鸦风格，孩子气的构图。"
        "客厅地板上昭昭举手。"
    )
    assert AgnesImageProvider._strip_prompt_for_verify(wrapped) == "客厅地板上昭昭举手。"

    items, user = AgnesImageProvider._build_verify_checklist(
        prompt=wrapped,
        expected_speakers=["昭昭"],
        content_style="daily_story",
    )
    assert "基于参考图" not in user
    assert "客厅地板上昭昭举手" in user
    assert [cid for cid, _ in items][0] == "scene"


def test_generate_switches_to_backup_key_on_quota(tmp_path: Path) -> None:
    provider = AgnesImageProvider()
    output = tmp_path / "1.png"
    output.write_bytes(b"png")

    from app.services.llm.llm_agnes import AgnesQuotaExceeded

    with (
        patch(
            "app.services.segment.image.image_agnes.agnes_api_keys",
            return_value=[
                AgnesApiKey("primary", "main-key"),
                AgnesApiKey("free", "free-key"),
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
    assert mock_generate.call_args_list[0].args[0].value == "main-key"
    assert mock_generate.call_args_list[1].args[0].value == "free-key"


def test_generate_switches_to_backup_key_on_5xx(tmp_path: Path) -> None:
    provider = AgnesImageProvider()
    output = tmp_path / "1.png"
    output.write_bytes(b"png")
    from app.services.segment.image.image_agnes import _AgnesImageKeyFailover

    five_xx = _AgnesImageKeyFailover(
        "agnes request failed (after 1 retries; url=https://x; last_status=503)"
    )

    with (
        patch(
            "app.services.segment.image.image_agnes.agnes_api_keys",
            return_value=[
                AgnesApiKey("primary", "main-key"),
                AgnesApiKey("free", "free-key"),
            ],
        ),
        patch.object(
            provider,
            "_generate_with_key",
            side_effect=[five_xx, output],
        ) as mock_generate,
        patch.object(provider, "_verify_image", return_value=True),
    ):
        provider.generate("测试 prompt", output, size="720*1280")

    assert mock_generate.call_count == 2
    assert mock_generate.call_args_list[0].args[0].value == "main-key"
    assert mock_generate.call_args_list[1].args[0].value == "free-key"
    # 有备用 Key 时付费侧只打 1 次，503 即切 free
    assert mock_generate.call_args_list[0].kwargs.get("max_retries") == 1
    assert mock_generate.call_args_list[1].kwargs.get("max_retries") is None


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
