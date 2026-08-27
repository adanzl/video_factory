from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import requests

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


def test_request_failover_to_cn_on_503() -> None:
    provider = AgnesImageProvider()
    com_url = "https://apihub.agnes-ai.com/v1/images/generations"
    cn_url = "https://apihub.agnes-ai.cn/v1/images/generations"

    resp_503 = MagicMock()
    resp_503.status_code = 503
    resp_503.ok = False
    resp_503.content = b""
    resp_503.json = MagicMock(return_value={})

    resp_ok = MagicMock()
    resp_ok.status_code = 200
    resp_ok.ok = True
    resp_ok.content = b"{}"
    resp_ok.json = MagicMock(return_value={"data": [{"url": "https://example.com/x.png"}]})

    with patch(
        "app.services.segment.image.image_agnes.requests.request",
        side_effect=[resp_503, resp_ok],
    ) as mock_request:
        result = provider._request(  # noqa: SLF001
            "POST",
            com_url,
            api_key="k",
            json={"model": "m"},
            max_retries=2,
        )

    assert result is resp_ok
    assert mock_request.call_count == 2
    assert mock_request.call_args_list[0].args[1] == com_url
    assert mock_request.call_args_list[1].args[1] == cn_url
    assert provider._generation_url == cn_url  # noqa: SLF001


def test_request_failover_to_com_on_503() -> None:
    provider = AgnesImageProvider()
    provider._generation_url = "https://apihub.agnes-ai.cn/v1/images/generations"  # noqa: SLF001
    cn_url = provider._generation_url
    com_url = "https://apihub.agnes-ai.com/v1/images/generations"

    resp_503 = MagicMock()
    resp_503.status_code = 503
    resp_503.ok = False
    resp_503.content = b""
    resp_503.json = MagicMock(return_value={})

    resp_ok = MagicMock()
    resp_ok.status_code = 200
    resp_ok.ok = True
    resp_ok.content = b"{}"
    resp_ok.json = MagicMock(return_value={"data": [{"url": "https://example.com/x.png"}]})

    with patch(
        "app.services.segment.image.image_agnes.requests.request",
        side_effect=[resp_503, resp_ok],
    ) as mock_request:
        result = provider._request(  # noqa: SLF001
            "POST",
            cn_url,
            api_key="k",
            json={"model": "m"},
            max_retries=2,
        )

    assert result is resp_ok
    assert mock_request.call_count == 2
    assert mock_request.call_args_list[0].args[1] == cn_url
    assert mock_request.call_args_list[1].args[1] == com_url
    assert provider._generation_url == com_url  # noqa: SLF001


def test_request_failover_to_cn_on_timeout() -> None:
    provider = AgnesImageProvider()
    com_url = "https://apihub.agnes-ai.com/v1/images/generations"
    cn_url = "https://apihub.agnes-ai.cn/v1/images/generations"

    resp_ok = MagicMock()
    resp_ok.status_code = 200
    resp_ok.ok = True
    resp_ok.content = b"{}"
    resp_ok.json = MagicMock(return_value={"data": [{"url": "https://example.com/x.png"}]})

    with patch(
        "app.services.segment.image.image_agnes.requests.request",
        side_effect=[requests.Timeout("connect timed out"), resp_ok],
    ) as mock_request:
        result = provider._request(  # noqa: SLF001
            "POST",
            com_url,
            api_key="k",
            json={"model": "m"},
            max_retries=2,
        )

    assert result is resp_ok
    assert mock_request.call_count == 2
    assert mock_request.call_args_list[0].args[1] == com_url
    assert mock_request.call_args_list[1].args[1] == cn_url
    assert provider._generation_url == cn_url  # noqa: SLF001


def test_request_failover_to_com_on_timeout() -> None:
    provider = AgnesImageProvider()
    provider._generation_url = "https://apihub.agnes-ai.cn/v1/images/generations"  # noqa: SLF001
    cn_url = provider._generation_url
    com_url = "https://apihub.agnes-ai.com/v1/images/generations"

    resp_ok = MagicMock()
    resp_ok.status_code = 200
    resp_ok.ok = True
    resp_ok.content = b"{}"
    resp_ok.json = MagicMock(return_value={"data": [{"url": "https://example.com/x.png"}]})

    with patch(
        "app.services.segment.image.image_agnes.requests.request",
        side_effect=[requests.ReadTimeout("read timed out"), resp_ok],
    ) as mock_request:
        result = provider._request(  # noqa: SLF001
            "POST",
            cn_url,
            api_key="k",
            json={"model": "m"},
            max_retries=2,
        )

    assert result is resp_ok
    assert mock_request.call_count == 2
    assert mock_request.call_args_list[0].args[1] == cn_url
    assert mock_request.call_args_list[1].args[1] == com_url
    assert provider._generation_url == com_url  # noqa: SLF001


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
    # Agnes 默认 1K 档位 + 按请求尺寸推断比例
    assert payload["size"] == "1K"
    assert payload["ratio"] == "9:16"
    assert payload["extra_body"] == {"response_format": "url"}
    assert output.read_bytes() == b"png-bytes"


def test_generate_puts_http_ref_into_ref_images_not_image(tmp_path: Path) -> None:
    """GitHub URL 须进 ref_images（角色参考），禁止误入 image（i2i 底图）。"""
    provider = AgnesImageProvider()
    output = tmp_path / "1.png"
    ref_url = (
        "https://raw.githubusercontent.com/adanzl/video_factory/main/"
        "backend/res/host/crayon/hosts.png"
    )

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
        provider.generate(
            "测试 prompt",
            output,
            size="1280*720",
            ref_images=[ref_url],
        )

    payload = mock_request.call_args.kwargs["json"]
    extra = payload["extra_body"]
    assert extra["ref_images"] == [ref_url]
    assert "image" not in extra


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
    assert _VERIFY_MAX_ATTEMPTS == 5


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


def test_generate_verify_retry_keeps_same_key(tmp_path: Path) -> None:
    provider = AgnesImageProvider()
    output = tmp_path / "1.png"
    output.write_bytes(b"png")
    free = AgnesApiKey("free", "free-key", "https://apihub.agnes-ai.com/v1")
    primary = AgnesApiKey("primary", "main-key", "https://apihub.agnes-ai.com/v1")

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
    # 质检失败不换 Key，始终用 sticky 的 primary
    assert used == ["primary", "primary", "primary"]

def test_parse_item_answer_handles_bu_shi() -> None:
    assert AgnesImageProvider._parse_item_answer("不是") == "no"
    assert AgnesImageProvider._parse_item_answer("否") == "no"
    assert AgnesImageProvider._parse_item_answer("是") == "yes"
    assert AgnesImageProvider._parse_item_answer("是的，基本一致") == "yes"
    assert AgnesImageProvider._parse_item_answer("无昭昭") == "na_zhao"
    assert AgnesImageProvider._parse_item_answer("无灿灿") == "na_can"
    assert AgnesImageProvider._parse_item_answer("无妈妈") == "na_mom"


def test_evaluate_verify_response_zhao_hair_and_cast() -> None:
    ids = ["scene", "zhao_hair", "can_hair", "can_one", "mom_adult", "zhao_arms", "cast_count"]
    ok = "项1: 是\n项2: 是\n项3: 是\n项4: 是\n项5: 是\n项6: 2\n项7: 3\n"
    assert AgnesImageProvider._evaluate_verify_response(ok, ids, cast_max=3)

    bad_zhao = "项1: 是\n项2: 否\n项3: 是\n项4: 是\n项5: 是\n项6: 2\n项7: 3\n"
    assert not AgnesImageProvider._evaluate_verify_response(bad_zhao, ids, cast_max=3)

    bad_can = "项1: 是\n项2: 是\n项3: 否\n项4: 是\n项5: 是\n项6: 2\n项7: 3\n"
    assert not AgnesImageProvider._evaluate_verify_response(bad_can, ids, cast_max=3)

    bad_can_one = "项1: 是\n项2: 是\n项3: 是\n项4: 否\n项5: 是\n项6: 2\n项7: 3\n"
    assert not AgnesImageProvider._evaluate_verify_response(
        bad_can_one, ids, cast_max=3
    )

    bad_mom = "项1: 是\n项2: 是\n项3: 是\n项4: 是\n项5: 否\n项6: 2\n项7: 3\n"
    assert not AgnesImageProvider._evaluate_verify_response(bad_mom, ids, cast_max=3)

    bad_arms = "项1: 是\n项2: 是\n项3: 是\n项4: 是\n项5: 是\n项6: 3\n项7: 3\n"
    assert not AgnesImageProvider._evaluate_verify_response(bad_arms, ids, cast_max=3)

    arms_yes = "项1: 是\n项2: 是\n项3: 是\n项4: 是\n项5: 是\n项6: 是\n项7: 3\n"
    assert not AgnesImageProvider._evaluate_verify_response(arms_yes, ids, cast_max=3)

    ids_legs = [
        "scene",
        "zhao_hair",
        "can_hair",
        "can_one",
        "mom_adult",
        "zhao_legs",
        "cast_count",
    ]
    bad_legs = "项1: 是\n项2: 是\n项3: 是\n项4: 是\n项5: 是\n项6: 3\n项7: 3\n"
    assert not AgnesImageProvider._evaluate_verify_response(
        bad_legs, ids_legs, cast_max=3
    )
    legs_yes = "项1: 是\n项2: 是\n项3: 是\n项4: 是\n项5: 是\n项6: 是\n项7: 3\n"
    assert not AgnesImageProvider._evaluate_verify_response(
        legs_yes, ids_legs, cast_max=3
    )
    ok_legs = "项1: 是\n项2: 是\n项3: 是\n项4: 是\n项5: 是\n项6: 2\n项7: 3\n"
    assert AgnesImageProvider._evaluate_verify_response(ok_legs, ids_legs, cast_max=3)

    bad_cast = "项1: 是\n项2: 是\n项3: 是\n项4: 是\n项5: 是\n项6: 2\n项7: 4\n"
    assert not AgnesImageProvider._evaluate_verify_response(bad_cast, ids, cast_max=3)

    # 人数项答「是」不可靠 → 失败
    cast_yes = "项1: 是\n项2: 是\n项3: 是\n项4: 是\n项5: 是\n项6: 2\n项7: 是\n"
    assert not AgnesImageProvider._evaluate_verify_response(cast_yes, ids, cast_max=3)

    # 「不是」= 否 → 短发项失败
    bu_shi = "项1: 是\n项2: 不是\n项3: 是\n"
    assert not AgnesImageProvider._evaluate_verify_response(
        bu_shi, ["scene", "zhao_hair", "extra_arms"]
    )

    # 无昭昭 / 无灿灿 / 无妈妈 → 对应项放行
    na = "项1: 是\n项2: 无昭昭\n项3: 无灿灿\n项4: 是\n项5: 无妈妈\n项6: 2\n项7: 3\n"
    assert AgnesImageProvider._evaluate_verify_response(na, ids, cast_max=3)

    # 正文空 / 全项解析失败 → 质检失效，不得放行
    assert not AgnesImageProvider._evaluate_verify_response("", ids, cast_max=3)
    assert not AgnesImageProvider._evaluate_verify_response("思考中……", ids, cast_max=3)


def test_vl_message_text_falls_back_to_reasoning_items() -> None:
    """Agnes VL 把「项N」答案放进 reasoning_content 时须能抽出。"""
    msg = {
        "content": "",
        "reasoning_content": (
            "我先数人头……\n"
            "项1: 是\n项2: 是\n项3: 否\n"
            "项4: 是\n项5: 是\n项6: 4\n"
        ),
    }
    text = AgnesImageProvider._vl_message_text(msg)
    assert "项1: 是" in text
    assert "项6: 4" in text
    ids = ["scene", "zhao_hair", "can_hair", "mom_adult", "extra_arms", "cast_count"]
    assert not AgnesImageProvider._evaluate_verify_response(text, ids, cast_max=3)


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
    items, user, cast_max = AgnesImageProvider._build_verify_checklist(
        prompt="客厅对峙",
        expected_speakers=["昭昭", "灿灿", "妈妈"],
        content_style="daily_story",
    )
    ids = [cid for cid, _ in items]
    assert ids == [
        "scene",
        "zhao_hair",
        "can_hair",
        "can_one",
        "mom_adult",
        "zhao_arms",
        "can_arms",
        "mom_arms",
        "zhao_legs",
        "can_legs",
        "mom_legs",
        "cast_count",
    ]
    assert cast_max == 3
    assert "昭昭" in user
    assert "灿灿" in user
    assert "成年女性" in user
    assert "一共几个" in user
    assert "阿拉伯数字" in user
    assert "穿粉色卫衣的女孩是否恰好 1 个" in user
    assert "只数人头" in user
    assert "只能是：" not in user
    assert "禁止路人" not in user
    assert "蓝衣" not in user
    assert "短发男孩即昭昭" in user
    assert "男孩超短发" in user
    assert "波波头" in user
    assert "扎马尾的女孩即灿灿" in user
    assert "单侧高马尾" in user
    assert "霓虹条纹" in user
    assert "彩虹挑染" in user
    assert "末端呈人手形态的肢端都算一条手臂" in user
    assert "腋下、腰侧、胸口" in user
    assert "不要用「人只有两只胳膊」的常识改口" in user
    assert "末端呈人脚或鞋子形态的肢端都算一条腿" in user
    assert "桌腿、椅腿、裤褶不算" in user
    assert "不要用「人只有两条腿」的常识改口" in user
    assert "只回答阿拉伯数字" in user
    assert "照片墙" in user

    items_lr, user_lr, _ = AgnesImageProvider._build_verify_checklist(
        prompt="画面左边是灿灿，右边是昭昭。客厅对峙。",
        expected_speakers=["昭昭", "灿灿"],
        content_style="daily_story",
    )
    assert "lr_pos" in [cid for cid, _ in items_lr]
    assert "粉色卫衣的黑马尾女孩（灿灿）" in user_lr
    assert "蓝色短袖T恤的短发男孩（昭昭）" in user_lr
    assert "左右人物对调" in user_lr

    # 首个说话人张嘴标记 → 嘴型项：闭嘴硬失败，微张/张开算过
    items_mouth, user_mouth, _ = AgnesImageProvider._build_verify_checklist(
        prompt=(
            "画面左边是昭昭，右边是灿灿。"
            "灿灿微微张嘴正在开口说话；昭昭嘴巴闭合不露齿。客厅对峙。"
        ),
        expected_speakers=["昭昭", "灿灿"],
        content_style="daily_story",
    )
    assert "mouth_first" in [cid for cid, _ in items_mouth]
    assert "粉色卫衣的黑马尾女孩（灿灿）是否张着嘴" in user_mouth
    assert "其他人张嘴与否不影响本项" in user_mouth
    assert "嘴巴完全闭合才答「否」" in user_mouth

    items_hold, user_hold, _ = AgnesImageProvider._build_verify_checklist(
        prompt="画面左边是昭昭，右边是灿灿。灿灿右手握着剪刀。",
        expected_speakers=["昭昭", "灿灿"],
        content_style="daily_story",
    )
    assert "prop_holder" in [cid for cid, _ in items_hold]
    assert "身前桌面上" in user_hold
    assert "完全看不到" in user_hold
    assert "包裹剪刀柄" not in user_hold
    assert "单独放在桌面上" not in user_hold

    items_pass, user_pass, _ = AgnesImageProvider._build_verify_checklist(
        prompt="画面左边是昭昭，右边是灿灿。灿灿右手递出剪刀。",
        expected_speakers=["昭昭", "灿灿"],
        content_style="daily_story",
    )
    assert "prop_holder" in [cid for cid, _ in items_pass]
    assert "身前桌面上" in user_pass
    assert "mouth_first" not in [cid for cid, _ in items_lr]
    items_solo, _, _ = AgnesImageProvider._build_verify_checklist(
        prompt="灿灿微微张嘴正在开口说话。只有灿灿。",
        expected_speakers=["灿灿"],
        content_style="daily_story",
    )
    assert "mouth_first" in [cid for cid, _ in items_solo]

    items_one, user_one, max_one = AgnesImageProvider._build_verify_checklist(
        prompt="只有昭昭",
        expected_speakers=["昭昭"],
        content_style="daily_story",
    )
    assert "zhao_hair" in [cid for cid, _ in items_one]
    assert "can_hair" not in [cid for cid, _ in items_one]
    assert "can_one" not in [cid for cid, _ in items_one]
    assert "mom_adult" not in [cid for cid, _ in items_one]
    assert "cast_count" in [cid for cid, _ in items_one]
    assert "zhao_arms" in [cid for cid, _ in items_one]
    assert "zhao_legs" in [cid for cid, _ in items_one]
    assert max_one == 2
    assert "上限参考 2" in user_one
    assert "只数人头" in user_one
    assert "只能是：" not in user_one

    # 无昭昭发言时不做短发项；有灿灿则检单马尾+粉卫衣人数；人数按姐弟上限 2
    items_can, user_can, max_can = AgnesImageProvider._build_verify_checklist(
        prompt="只有灿灿",
        expected_speakers=["灿灿"],
        content_style="daily_story",
    )
    assert "zhao_hair" not in [cid for cid, _ in items_can]
    assert "can_hair" in [cid for cid, _ in items_can]
    assert "can_one" in [cid for cid, _ in items_can]
    assert "mom_adult" not in [cid for cid, _ in items_can]
    assert "cast_count" in [cid for cid, _ in items_can]
    assert max_can == 2
    assert "上限参考 2" in user_can
    assert "只数人头" in user_can
    assert "单侧高马尾" in user_can
    assert "彩虹挑染" in user_can
    assert "霓虹条纹" in user_can

    items_mom, user_mom, max_mom = AgnesImageProvider._build_verify_checklist(
        prompt="只有妈妈",
        expected_speakers=["妈妈"],
        content_style="daily_story",
    )
    assert "mom_adult" in [cid for cid, _ in items_mom]
    assert max_mom == 3
    assert "成年女性" in user_mom
    assert "上限参考 3" in user_mom
    assert "只数人头" in user_mom
    assert "只能是：" not in user_mom

    items2, user2, max2 = AgnesImageProvider._build_verify_checklist(
        prompt="电池剖面",
        expected_speakers=None,
        content_style="science_child",
    )
    assert [cid for cid, _ in items2] == ["scene", "extra_arms", "extra_legs"]
    assert max2 is None
    assert "昭昭" not in user2


def test_build_verify_checklist_door_and_float_hair() -> None:
    """提示词含门/风吹头发时，质检须加单扇门与无独立飘发检查项。"""
    items, user, _ = AgnesImageProvider._build_verify_checklist(
        prompt=(
            "客厅门边，门半掩着，风将灿灿的马尾吹起。"
            "画面左边是昭昭，右边是灿灿。"
        ),
        expected_speakers=["昭昭", "灿灿"],
        content_style="daily_story",
    )
    ids = [cid for cid, _ in items]
    assert "door_single" in ids
    assert "no_float_hair" in ids
    assert "hair_wind_dir" in ids
    assert "是否只有一个门扇" in user
    assert "双开门/对开门" in user
    assert "独立马尾/发束/一绺头发" in user
    assert "从门口/门缝飘入" in user
    assert "背离门口" in user

    items2, user2, _ = AgnesImageProvider._build_verify_checklist(
        prompt="客厅对峙",
        expected_speakers=["昭昭", "灿灿"],
        content_style="daily_story",
    )
    ids2 = [cid for cid, _ in items2]
    assert "door_single" not in ids2
    assert "no_float_hair" not in ids2
    assert "hair_wind_dir" not in ids2


def test_evaluate_verify_response_door_and_float_hair() -> None:
    """单扇门/无飘发/风向项答「否」时出图质检必须判失败。"""
    ids = [
        "scene",
        "door_single",
        "no_float_hair",
        "hair_wind_dir",
        "extra_arms",
        "cast_count",
    ]
    ok = "项1: 是\n项2: 是\n项3: 是\n项4: 是\n项5: 2\n项6: 2\n"
    assert AgnesImageProvider._evaluate_verify_response(ok, ids, cast_max=2)

    bad_door = "项1: 是\n项2: 否\n项3: 是\n项4: 是\n项5: 2\n项6: 2\n"
    assert not AgnesImageProvider._evaluate_verify_response(
        bad_door, ids, cast_max=2
    )

    bad_hair = "项1: 是\n项2: 是\n项3: 否\n项4: 是\n项5: 2\n项6: 2\n"
    assert not AgnesImageProvider._evaluate_verify_response(
        bad_hair, ids, cast_max=2
    )

    bad_dir = "项1: 是\n项2: 是\n项3: 是\n项4: 否\n项5: 2\n项6: 2\n"
    assert not AgnesImageProvider._evaluate_verify_response(
        bad_dir, ids, cast_max=2
    )


def test_strip_prompt_for_verify_drops_daily_wrap() -> None:
    wrapped = (
        "基于参考图调整人物动作，保留昭昭：7岁男孩。"
        "儿童情绪涂鸦风格，孩子气的构图。"
        "客厅地板上昭昭举手。"
    )
    assert AgnesImageProvider._strip_prompt_for_verify(wrapped) == "客厅地板上昭昭举手。"

    items, user, _ = AgnesImageProvider._build_verify_checklist(
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
