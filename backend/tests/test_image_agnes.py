from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import json
import pytest
import requests
from PIL import Image as PILImage

from app.services.llm.llm_agnes import AgnesApiKey
from app.services.segment.image.image_agnes import (
    AgnesImageProvider,
    AgnesImageVerifyFailed,
    AgnesImageVerificationUnavailable,
    _VERIFY_MAX_ATTEMPTS,
    _to_agnes_size,
)


@pytest.mark.parametrize("holder,other", [("灿灿", "昭昭"), ("昭昭", "灿灿"), ("妈妈", "爸爸"), ("爸爸", "妈妈")])
@pytest.mark.parametrize("relation", ["比{other}高一点", "看向{other}", "站在{other}旁边"])
def test_prop_holder_uses_subject_not_referenced_character(holder, other, relation):
    prompt = f"画面左边是{other}，右手指向{holder}。画面右边是{holder}，{relation.format(other=other)}，右手在胸前握着遥控器。"
    items, _, _ = AgnesImageProvider._build_verify_checklist(
        prompt=prompt, expected_speakers=[holder, other], content_style="daily_story",
    )
    question = dict(items)["prop_holder"]
    assert f"（{holder}）的右手里" in question
    assert f"（{other}）的右手里" not in question
    assert "明显在其他人手里时答「否」" in question


@pytest.mark.parametrize("prefix", [
    "昭昭看向灿灿，灿灿", "画面左边是昭昭，右边是灿灿，", "灿灿站在昭昭旁边，",
    "灿灿比昭昭高，灿灿", "灿灿，比昭昭高一点，",
    "灿灿的", "灿灿看向昭昭，昭昭的旁边有桌子，",
])
def test_prop_holder_tracks_explicit_subject_change(prefix):
    items, _, _ = AgnesImageProvider._build_verify_checklist(
        prompt=prefix + "左手握着杯子。", expected_speakers=["昭昭", "灿灿"], content_style="daily_story",
    )
    assert "（灿灿）的左手里" in dict(items)["prop_holder"]


@pytest.fixture(autouse=True)
def block_real_http(monkeypatch):
    """单元测试不得读取本机凭据后意外请求真实接口。"""
    def reject(*args, **kwargs):
        raise AssertionError("Real HTTP is forbidden in image unit tests")

    monkeypatch.setattr(requests.sessions.Session, "request", reject)


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


def test_base64_generation_discards_previous_attempt_source_url(tmp_path: Path) -> None:
    import base64

    provider = AgnesImageProvider()
    output = tmp_path / "1.pending.png"
    sidecar = output.with_name(output.name + ".agnes_source_url")
    sidecar.write_text("https://example.test/previous-failed-image.png")
    response = MagicMock()
    response.json.return_value = {"data": [{"b64_json": base64.b64encode(b"new-image").decode()}]}
    with (
        patch.object(provider, "_request", return_value=response),
        patch.object(provider, "_acquire_submit_slot"),
        patch.object(provider, "_release_submit_slot"),
    ):
        provider._generate_with_key(AgnesApiKey("cn_free", "test-key"), "test", output, size="1K")
    assert output.read_bytes() == b"new-image"
    assert not sidecar.exists()


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


def test_generate_puts_http_ref_into_image_not_ref_images(tmp_path: Path) -> None:
    """参考图 URL 先内联成 Data URI 再进 extra_body.image；ref_images 已失效。"""
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
    assert extra["image"][0].startswith("data:image/png;base64,")
    assert ref_url not in extra["image"]
    assert "ref_images" not in extra
    mock_request.assert_called_once()


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

    # 身高硬卡：昭昭等高/更高 → 失败；缺其一放行
    ids_h = ["scene", "height_can", "cast_count"]
    assert AgnesImageProvider._evaluate_verify_response(
        "项1: 是\n项2: 是\n项3: 2\n", ids_h, cast_max=2
    )
    assert not AgnesImageProvider._evaluate_verify_response(
        "项1: 是\n项2: 否\n项3: 2\n", ids_h, cast_max=2
    )
    assert AgnesImageProvider._evaluate_verify_response(
        "项1: 是\n项2: 无昭昭\n项3: 2\n", ids_h, cast_max=2
    )
    assert AgnesImageProvider._evaluate_verify_response(
        "项1: 是\n项2: 无灿灿\n项3: 2\n", ids_h, cast_max=2
    )

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
        "people",
        "scene",
        "zhao_count",
        "zhao_clothes",
        "can_count",
        "can_clothes",
        "mom_count",
        "mom_clothes",
        "zhao_hair",
        "can_hair",
        "can_one",
        "height_can",
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
    assert "是否明显比" in user
    assert "高约半个头" in user
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
    assert "height_can" not in [cid for cid, _ in items_one]
    assert "mom_adult" not in [cid for cid, _ in items_one]
    assert "cast_count" in [cid for cid, _ in items_one]
    assert "zhao_arms" in [cid for cid, _ in items_one]
    assert "zhao_legs" in [cid for cid, _ in items_one]
    assert max_one == 2
    assert "上限参考" not in user_one
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
    assert "height_can" not in [cid for cid, _ in items_can]
    assert "mom_adult" not in [cid for cid, _ in items_can]
    assert "cast_count" in [cid for cid, _ in items_can]
    assert max_can == 2
    assert "上限参考" not in user_can
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
    assert "上限参考" not in user_mom
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
    assert [cid for cid, _ in items][0] == "people"


def test_parse_hardfail_arm_answer() -> None:
    # 正常：2 手 + 无多手
    assert AgnesImageProvider._parse_hardfail_arm_answer(
        "项1: 2\n项2: 否"
    ) == (2, False)
    # 多手：3 手 + 是
    assert AgnesImageProvider._parse_hardfail_arm_answer(
        "项1: 3\n项2: 是"
    ) == (3, True)
    # 数字项解析不出（例如 VL 答「无该角色」），返回 None 不误杀
    assert AgnesImageProvider._parse_hardfail_arm_answer(
        "项1: 无该角色\n项2: 否"
    ) == (None, False)
    # 项2 答案无法解析为是/否
    assert AgnesImageProvider._parse_hardfail_arm_answer(
        "项1: 2\n项2: 不清楚"
    ) == (2, None)


def test_verify_image_uses_base64_even_with_sidecar(tmp_path: Path) -> None:
    provider = AgnesImageProvider()
    img = PILImage.new("RGB", (64, 64), "red")
    path = tmp_path / "1.png"
    img.save(path)
    cdn = "https://platform-outputs.agnes-ai.space/images/out.png"
    path.with_name(path.name + ".agnes_source_url").write_text(cdn, encoding="utf-8")

    resp_ok = MagicMock()
    resp_ok.status_code = 200
    resp_ok.ok = True
    resp_ok.json = MagicMock(
        return_value={
            "choices": [{"message": {"content": "项1: 是\n项2: 是\n项3: 是"}}]
        }
    )
    posted_urls: list[str] = []

    def fake_post(_url, *, headers, json, timeout):  # noqa: ANN001, ARG001
        posted_urls.append(json["messages"][1]["content"][1]["image_url"]["url"])
        return resp_ok

    with (
        patch(
            "app.services.segment.image.image_agnes.agnes_api_keys",
            return_value=[AgnesApiKey("primary", "k")],
        ),
        patch("app.services.segment.image.image_agnes.requests.post", side_effect=fake_post),
        patch.object(provider, "_run_blocking_cancellable", side_effect=lambda fn: fn()),
        patch.object(
            AgnesImageProvider,
            "_evaluate_verify_response",
            return_value=True,
        ),
    ):
        ok = provider._verify_image(  # noqa: SLF001
            "客厅昭昭",
            path,
            expected_speakers=["昭昭"],
        )

    assert ok is True
    assert len(posted_urls) == 1
    assert posted_urls[0].startswith("data:image/jpeg;base64,")
    assert cdn not in posted_urls[0]


def test_crop_zone_data_url_zooms(tmp_path: Path) -> None:
    img = PILImage.new("RGB", (1000, 600), "white")
    for x in (100, 600, 800):
        for y in (100, 300):
            img.putpixel((x, y), (0, 0, 0))
    path = tmp_path / "crop.png"
    img.save(path)

    left = AgnesImageProvider._crop_zone_data_url(path, "left")
    right = AgnesImageProvider._crop_zone_data_url(path, "right")
    center = AgnesImageProvider._crop_zone_data_url(path, "center")
    assert left.startswith("data:image/jpeg;base64,")
    assert right.startswith("data:image/jpeg;base64,")
    assert center.startswith("data:image/jpeg;base64,")
    import base64 as b64_mod

    for b64 in (left, right, center):
        raw = b64_mod.b64decode(b64.split(",", 1)[1])
        assert raw[:2] == b"\xff\xd8"  # JPEG magic


def test_verify_hardfail_limbs_passes_normal(tmp_path: Path) -> None:
    provider = AgnesImageProvider()
    img = PILImage.new("RGB", (1000, 600), "white")
    path = tmp_path / "ok.png"
    img.save(path)

    with (
        patch.object(provider, "_ask_hardfail_vl", return_value="项1: 2\n项2: 否"),
        patch(
            "app.services.segment.image.image_agnes.agnes_api_keys",
            return_value=[AgnesApiKey("primary", "k")],
        ),
        patch.object(provider, "_allowed_cast_for_verify", return_value=["昭昭", "灿灿"]),
    ):
        ok = provider._verify_hardfail_limbs(
            path,
            expected_speakers=["昭昭", "灿灿"],
            content_style="daily_story",
        )
    assert ok is True


def test_verify_hardfail_limbs_fails_on_third_arm(tmp_path: Path) -> None:
    provider = AgnesImageProvider()
    img = PILImage.new("RGB", (1000, 600), "white")
    path = tmp_path / "bad.png"
    img.save(path)

    with (
        patch.object(
            provider, "_ask_hardfail_vl", return_value="项1: 3\n项2: 是"
        ),
        patch(
            "app.services.segment.image.image_agnes.agnes_api_keys",
            return_value=[AgnesApiKey("primary", "k")],
        ),
        patch.object(provider, "_allowed_cast_for_verify", return_value=["灿灿"]),
    ):
        ok = provider._verify_hardfail_limbs(
            path,
            expected_speakers=["灿灿"],
            content_style="daily_story",
        )
    assert ok is False


@pytest.mark.parametrize("answer", [None, "", "无法识别图片"])
def test_verify_hardfail_limbs_reports_incomplete_on_vl_failure(tmp_path: Path, answer) -> None:
    """VL 网络失败/无法解析不能算作质检完成。"""
    provider = AgnesImageProvider()
    img = PILImage.new("RGB", (1000, 600), "white")
    path = tmp_path / "skip.png"
    img.save(path)

    with (
        patch.object(provider, "_ask_hardfail_vl", return_value=answer),
        patch(
            "app.services.segment.image.image_agnes.agnes_api_keys",
            return_value=[AgnesApiKey("primary", "k")],
        ),
        patch.object(provider, "_allowed_cast_for_verify", return_value=["灿灿"]),
        pytest.raises(AgnesImageVerificationUnavailable, match="肢体质检未完成"),
    ):
        provider._verify_hardfail_limbs(
            path,
            expected_speakers=["灿灿"],
            content_style="daily_story",
        )


def test_verify_hardfail_limbs_non_daily_skips(tmp_path: Path) -> None:
    provider = AgnesImageProvider()
    path = tmp_path / "any.png"
    path.write_bytes(b"png")
    ok = provider._verify_hardfail_limbs(
        path,
        expected_speakers=["昭昭"],
        content_style="science",
    )
    assert ok is True


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
    stagger = max(0.5, settings.agnes_image_submit_interval_sec)

    AgnesImageProvider._inflight = None  # noqa: SLF001
    with (
        patch.object(get_settings(), "image_max_workers", workers),
        patch.object(get_settings(), "agnes_image_submit_interval_sec", stagger),
    ):
        provider = AgnesImageProvider()
        starts: list[float] = []

        def worker() -> None:
            provider._acquire_submit_slot("primary")  # noqa: SLF001
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


def test_image_submit_gate_is_pool_aware() -> None:
    """图片按密钥池计时：付费池 1s、免费池 6s，四个池各算各的。"""
    provider = AgnesImageProvider()
    provider._paid_interval_sec = 1.0  # noqa: SLF001
    provider._free_interval_sec = 6.0  # noqa: SLF001
    provider._free_pool_shared = True  # noqa: SLF001
    AgnesImageProvider._next_submit_at_by_pool = {}

    assert provider._pool_for_key("primary") == "paid_intl"  # noqa: SLF001
    assert provider._pool_for_key("cn_paid") == "paid_cn"  # noqa: SLF001
    assert provider._pool_for_key("free") == "free_intl"  # noqa: SLF001
    # 跨站点恒分池：国内免费不再与国际免费共用池
    assert provider._pool_for_key("cn_free") == "free_cn"  # noqa: SLF001
    assert provider._interval_for_pool("paid_intl") == 1.0  # noqa: SLF001
    assert provider._interval_for_pool("paid_cn") == 1.0  # noqa: SLF001
    assert provider._interval_for_pool("free_cn") == 6.0  # noqa: SLF001

    clock = {"now": 1000.0}
    sleeps: list[float] = []

    def _fake_sleep(sec: float) -> None:
        sleeps.append(sec)

    with (
        patch(
            "app.services.segment.image.image_agnes.time.monotonic",
            side_effect=lambda: clock["now"],
        ),
        patch(
            "app.services.segment.image.image_agnes.time.sleep",
            side_effect=_fake_sleep,
        ),
    ):
        # 两个池首次都不等（池间互相独立）
        assert provider._submit_gate_wait("primary") == 0.0  # noqa: SLF001
        provider._advance_submit_gate("primary")  # noqa: SLF001
        assert provider._submit_gate_wait("free") == 0.0  # noqa: SLF001
        provider._advance_submit_gate("free")  # noqa: SLF001
        # 国内池与国外池无关，仍是全新计时
        assert provider._submit_gate_wait("cn_free") == 0.0  # noqa: SLF001

        clock["now"] = 1000.5
        # 付费池还需 0.5s
        assert abs(provider._submit_gate_wait("primary") - 0.5) < 0.01  # noqa: SLF001
        # 免费池还需 5.5s
        assert abs(provider._submit_gate_wait("free") - 5.5) < 0.01  # noqa: SLF001
    assert sleeps == []


def test_image_free_pools_split_across_sites() -> None:
    """跨站点两把免费 key 恒为两池（仅同站点多把才看 AGNES_FREE_POOL_SHARED）。"""
    provider = AgnesImageProvider()
    for shared in (False, True):
        provider._free_pool_shared = shared  # noqa: SLF001
        assert provider._pool_for_key("free") == "free_intl"  # noqa: SLF001
        assert provider._pool_for_key("cn_free") == "free_cn"  # noqa: SLF001


def test_generate_acquires_slot_with_its_key_pool() -> None:
    """出图走闸门时须带本次 key，才能按该 key 所属池计时。"""
    import gevent

    provider = AgnesImageProvider()
    seen: list[str] = []

    def _fake_acquire(key_label: str = "primary") -> None:
        seen.append(key_label)

    with (
        patch.object(provider, "_acquire_submit_slot", side_effect=_fake_acquire),
        patch.object(provider, "_release_submit_slot"),
        patch.object(provider, "_request", side_effect=RuntimeError("stop")),
        patch(
            "app.services.segment.image.image_agnes.agnes_api_keys",
            return_value=[AgnesApiKey("cn_free", "k-cn")],
        ),
    ):
        import pytest as _pytest

        with _pytest.raises(RuntimeError, match="stop"):
            provider.generate("测试", Path("/tmp/never.png"))
    del gevent
    assert seen == ["cn_free"]


def _cast_reply(*, people: int = 3, boys: int = 1, clothes: str | None = None, count: int = 3) -> str:
    inventory = [
        {"position": f"位置{i}", "appearance": "实际衣服和发型", "posture": "坐着"}
        for i in range(people)
    ]
    if clothes is None:
        clothes = json.dumps({"upper_color": "pink", "upper_style": "hoodie", "lower_color": "blue", "lower_style": "trousers"})
    return (
        f"项1: {json.dumps(inventory, ensure_ascii=False)}\n"
        f"项2: {boys}\n项3: 1\n项4: {clothes}\n项5: {count}\n"
    )


@pytest.mark.parametrize("reply", [
    _cast_reply(people=4),  # 即使模型最后仍报三人，逐人清单四人也必须拦截。
    _cast_reply(boys=2),  # 总数未超限也不能用两个男孩替代缺失角色。
    _cast_reply(boys=0),
    _cast_reply(clothes="否，蓝色短袖T恤和深蓝短裤"),
    _cast_reply(clothes="无法辨认"),
    _cast_reply(count=2),  # 汇总与清单矛盾。
    "\n".join(line for line in _cast_reply().splitlines() if not line.startswith("项4:")),
    _cast_reply().split("\n", 1)[1],
    _cast_reply().replace("项5: 3\n", ""),
    "项1: []\n项2: 1\n项3: 1\n项4: 是\n项5: 3",
    '项1: [{"position":"左"}]\n项2: 1\n项3: 1\n项4: 是\n项5: 3',
])
def test_verify_rejects_duplicate_cast_wrong_clothes_and_incomplete_evidence(reply: str) -> None:
    assert not AgnesImageProvider._evaluate_verify_response(
        reply, ["people", "zhao_count", "can_count", "can_clothes", "cast_count"], cast_max=3,
    )


def test_verify_accepts_consistent_cast_and_clothes() -> None:
    assert AgnesImageProvider._evaluate_verify_response(
        _cast_reply(), ["people", "zhao_count", "can_count", "can_clothes", "cast_count"], cast_max=3,
    )


def test_verify_checklist_counts_people_without_filtering_wrong_clothes() -> None:
    items, user, _ = AgnesImageProvider._build_verify_checklist(
        prompt="昭昭躺在沙发上，灿灿站在右侧。",
        expected_speakers=["昭昭", "灿灿"], content_style="daily_story",
    )
    questions = dict(items)
    assert "不按角色名字合并" in questions["people"]
    assert "衣服串色也要计入" in questions["can_count"]
    assert "实际穿的衣服" in questions["can_clothes"]
    assert "upper_color" in questions["can_clothes"]
    assert "上限参考" not in user
    assert "例如「3」" not in user


def test_verify_image_missing_credentials_or_local_image_fails_closed(tmp_path: Path) -> None:
    provider = AgnesImageProvider()
    path = tmp_path / "1.png"
    assert not provider._verify_image("客厅", path)
    PILImage.new("RGB", (64, 64), "white").save(path)
    with patch("app.services.segment.image.image_agnes.agnes_api_keys", return_value=[]):
        assert not provider._verify_image("客厅", path)
    with patch.object(AgnesImageProvider, "_encode_verify_image_data_url", side_effect=ValueError("bad image")):
        assert not provider._verify_image("客厅", path)


@pytest.mark.parametrize("color,style", [("blue", "short_sleeve"), ("pink", "short_sleeve"), ("other", "hoodie")])
def test_verify_compares_observed_clothes_in_code(color: str, style: str) -> None:
    clothes = json.dumps({"upper_color": color, "upper_style": style, "lower_color": "blue", "lower_style": "shorts"})
    assert not AgnesImageProvider._evaluate_verify_response(
        _cast_reply(clothes=clothes),
        ["people", "zhao_count", "can_count", "can_clothes", "cast_count"], cast_max=3,
    )


def test_verify_clothes_allows_cropped_lower_body_but_not_empty_observation() -> None:
    clothes = {"upper_color": "pink", "upper_style": "hoodie", "lower_color": "hidden", "lower_style": "hidden"}
    assert AgnesImageProvider._evaluate_verify_response(
        f"项1: {json.dumps(clothes)}", ["can_clothes"],
    )
    clothes.update(upper_color="hidden", upper_style="hidden")
    assert not AgnesImageProvider._evaluate_verify_response(
        f"项1: {json.dumps(clothes)}", ["can_clothes"],
    )


@pytest.mark.parametrize(('cid', 'answer', 'expected'), [
    ('zhao_count', '2', '"zhao_count": 2'),
    ('can_count', '2', '"can_count": 2'),
    ('mom_count', '2', '"mom_count": 2'),
    ('can_clothes', '{"upper_color":"blue","upper_style":"short_sleeve","lower_color":"blue","lower_style":"shorts"}', '"upper_color": "blue"'),
])
def test_verify_observations_reach_feedback(tmp_path: Path, cid, answer, expected) -> None:
    provider = AgnesImageProvider()
    path = tmp_path / 'rejected.png'
    PILImage.new('RGB', (16, 16), 'white').save(path)
    response = MagicMock(status_code=200, ok=True)
    response.json.return_value = {'choices': [{'message': {'content': f'项1: {answer}'}}]}
    feedback: list[str] = []
    with (
        patch('app.services.segment.image.image_agnes.agnes_api_keys', return_value=[AgnesApiKey('free', 'test')]),
        patch('app.services.segment.image.image_agnes.requests.post', return_value=response),
        patch.object(provider, '_run_blocking_cancellable', side_effect=lambda fn: fn()),
        patch.object(AgnesImageProvider, '_build_verify_checklist', return_value=([(cid, '检查项')], '检查图片', 3)),
    ):
        assert not provider._verify_image('原提示词', path, expected_speakers=['昭昭','灿灿','妈妈'], feedback=feedback)
    assert len(feedback) == 1
    assert expected in feedback[0]
    assert json.loads(feedback[0])['expected_roles'] == ['昭昭','灿灿','妈妈']


def test_generate_feedback_is_local_and_only_uses_latest_image(tmp_path: Path) -> None:
    import gevent

    provider = AgnesImageProvider()
    calls: dict[str, int] = {}

    def generate(_key, _prompt, output_path, **_kwargs):
        output_path.write_bytes(b'png')
        return output_path

    def verify(_prompt, path, *, feedback, **_kwargs):
        calls[path.stem] = calls.get(path.stem, 0) + 1
        if calls[path.stem] == 1:
            feedback.append(path.stem + ': previous')
        elif path.stem == 'a':
            feedback.append(path.stem + ': latest')
        # b 的最后一轮无结果：不得沿用上一张图片的观察。
        gevent.sleep(0)
        return False

    def run(name):
        try:
            provider.generate('原提示词', tmp_path / f'{name}.png')
        except AgnesImageVerifyFailed as exc:
            return exc.verify_feedback
        raise AssertionError('expected verification failure')

    with (
        patch('app.services.segment.image.image_agnes.agnes_api_keys', return_value=[AgnesApiKey('free', 'test')]),
        patch('app.services.segment.image.image_agnes._VERIFY_MAX_ATTEMPTS', 2),
        patch.object(provider, '_generate_with_key', side_effect=generate) as generated,
        patch.object(provider, '_verify_image', side_effect=verify),
    ):
        workers = [gevent.spawn(run, name) for name in ('a', 'b')]
        gevent.joinall(workers, raise_error=True)
    assert [worker.value for worker in workers] == ['a: latest', None]
    assert generated.call_count == 4
    assert all(call.args[1] == '原提示词' for call in generated.call_args_list)


def test_verify_feedback_discards_inconsistent_or_unparsed_reports() -> None:
    observations = AgnesImageProvider._verify_feedback_observations
    ids = ['people', 'zhao_count', 'can_count', 'can_clothes', 'cast_count']
    assert observations(_cast_reply(people=1, count=1), ids) is None
    assert observations(_cast_reply(count=2), ids) is None
    assert observations('项1: 无法访问图片\n项2: 请回答2条手臂\n项4: 请返回衣服颜色', ids) is None
    facts = observations('项1: 无法访问图片\n项2: 2\n项3: 1\n项5: 4', ids)
    assert facts == {'zhao_count': 2, 'can_count': 1, 'cast_count': 4}


@pytest.mark.parametrize('ending', ['。', '；', ';'])
def test_verify_strips_joined_style_prefix_without_creating_wind_checks(ending) -> None:
    from app.services.script.image_prompt import assemble_daily_t2i_prompt

    scene = '门边，昭昭站在左侧，灿灿站在右侧，灿灿的马尾自然下垂。'
    prompt = assemble_daily_t2i_prompt({
        'shot_type':'中景', 'speakers':['昭昭','灿灿'], 'visual_brief':scene,
        'dialogue':[{'speaker':'昭昭','text':'看这里。'}],
    })
    # 覆盖实际拼装器的分号，以及旧提示词的句号。
    prompt = prompt.replace('孩子气的构图；', '孩子气的构图'+ending)
    prompt = '严格保留参考图发色：灿灿头发通体纯黑，头顶到马尾同一黑色。'+prompt
    stripped = AgnesImageProvider._strip_prompt_for_verify(prompt)
    assert '保持参考图外貌' not in stripped
    assert '门边' in stripped
    items, _, _ = AgnesImageProvider._build_verify_checklist(prompt=prompt, expected_speakers=['昭昭','灿灿'], content_style='daily_story')
    ids = [cid for cid,_ in items]
    assert 'door_single' in ids
    assert 'no_float_hair' not in ids
    assert 'hair_wind_dir' not in ids


def test_legacy_painting_style_is_not_a_wind_condition() -> None:
    items,_,_=AgnesImageProvider._build_verify_checklist(
        prompt='蜡笔画风、手绘风格。门边灿灿的黑色马尾自然下垂。',
        expected_speakers=['昭昭','灿灿'],content_style='daily_story',
    )
    assert not {'no_float_hair','hair_wind_dir'} & {cid for cid,_ in items}


@pytest.mark.parametrize("field", ["content", "reasoning_content"])
def test_multiline_people_json_is_preserved_from_vl_message(field):
    text = '项1: [\n {"position":"左边","appearance":"蓝衣男孩","posture":"坐着"}\n]\n项2: 1'
    normalized = AgnesImageProvider._vl_message_text({field: text})
    assert AgnesImageProvider._evaluate_verify_response(normalized, ["people", "cast_count"], cast_max=1)
    observations = AgnesImageProvider._verify_feedback_observations(normalized, ["people", "cast_count"])
    assert observations["people"][0]["posture"] == "坐着"
    malformed = AgnesImageProvider._vl_message_text({field: text.replace('\n]', '')})
    assert not AgnesImageProvider._evaluate_verify_response(malformed, ["people", "cast_count"], cast_max=1)


@pytest.mark.parametrize("edit_passes", [True, False])
def test_excess_people_edit_uses_failed_image_but_keeps_original_qc(tmp_path, edit_passes):
    provider = AgnesImageProvider()
    output = tmp_path / "frame.png"
    refs = [tmp_path / "hosts.png"]
    feedback = json.dumps({"observations": {
        "cast_count": 3, "people": [{"position": str(i), "appearance": "人物", "posture": "站着"} for i in range(3)]
    }})
    generated = []
    verified = []

    def generate(key, prompt, path, **kwargs):
        generated.append((prompt, kwargs["ref_images"]))
        path.write_bytes(b"image")
        return path

    def verify(prompt, path, **kwargs):
        verified.append(prompt)
        if len(verified) == 1 or (not edit_passes and len(verified) == 2):
            kwargs["feedback"].append(feedback)
            return False
        return edit_passes or len(verified) == 3

    with (
        patch("app.services.segment.image.image_agnes.agnes_api_keys", return_value=[AgnesApiKey("cn_free", "test-key")]),
        patch.object(provider, "_generate_with_key", side_effect=generate),
        patch.object(provider, "_verify_image", side_effect=verify),
        patch.object(provider, "_plan_excess_people_edit", return_value=("只删除多余人物", "data:image/png;base64,aW1hZ2U=")) as plan,
    ):
        assert provider.generate("原剧情动作", output, ref_images=refs, expected_speakers=["昭昭", "灿灿"], content_style="daily_story") == output
    plan.assert_called_once()
    assert generated[1] == ("只删除多余人物", ["data:image/png;base64,aW1hZ2U="])
    assert len(set(verified)) == 1
    assert "原剧情动作" in verified[0]
    if not edit_passes:
        assert generated[2] == generated[0]
    assert refs == [tmp_path / "hosts.png"]


@pytest.mark.parametrize("observations", [
    {"cast_count": 2, "zhao_arms": 3},
    {"cast_count": 3},
    {"cast_count": 3, "people": [{"position":"左", "appearance":"男孩", "posture":"躺着"}]},
    {"cast_count": 3, "people": [{}, {}, {}]},
])
def test_people_edit_gate_rejects_limbs_or_uncertain_counts(observations):
    assert not AgnesImageProvider._has_excess_people(json.dumps({"observations": observations}), 2)


@pytest.mark.parametrize("plan", [
    {"confident": False, "remaining_count": 2, "keep_description": "保留", "remove_description": "删除"},
    {"confident": True, "remaining_count": 1, "keep_description": "保留", "remove_description": "删除"},
    {"confident": True, "remaining_count": 2, "remove_description": "删除"},
    {"confident": True, "remaining_count": 2, "keep_description": "", "remove_description": "删除"},
])
def test_people_edit_plan_rejects_ambiguous_or_incomplete_plan(tmp_path, plan):
    provider = AgnesImageProvider()
    source = tmp_path / "source.png"
    PILImage.new("RGB", (8,8)).save(source)
    response = MagicMock()
    response.json.return_value = {"choices": [{"message": {"content": json.dumps(plan)}}]}
    with patch.object(provider, "_run_blocking_cancellable", side_effect=lambda fn: fn()), patch("requests.post", return_value=response):
        assert provider._plan_excess_people_edit("原稿", source, expected_speakers=["昭昭", "灿灿"], feedback="观察", api_key=AgnesApiKey("cn_free", "test-key")) is None


@pytest.mark.parametrize("attempt_budget", [1, 3])
def test_uncertain_people_edit_keeps_original_retry_budget(tmp_path, attempt_budget):
    provider = AgnesImageProvider()
    output = tmp_path / "frame.png"
    output.write_bytes(b"image")
    refs = [tmp_path / "hosts.png"]
    observation = json.dumps({"observations": {
        "cast_count": 3,
        "people": [{"position": str(i), "appearance": "人物", "posture": "站着"} for i in range(3)],
    }})

    def verify(_prompt, _path, *, feedback, **_kwargs):
        feedback.append(observation)
        return False

    with (
        patch("app.services.segment.image.image_agnes.agnes_api_keys", return_value=[AgnesApiKey("cn_free", "test-key")]),
        patch("app.services.segment.image.image_agnes._VERIFY_MAX_ATTEMPTS", attempt_budget),
        patch.object(provider, "_generate_with_key", return_value=output) as generate,
        patch.object(provider, "_verify_image", side_effect=verify),
        patch.object(provider, "_plan_excess_people_edit", return_value=None) as plan,
        pytest.raises(AgnesImageVerifyFailed),
    ):
        provider.generate("原剧情", output, ref_images=refs, expected_speakers=["昭昭", "灿灿"], content_style="daily_story")
    assert generate.call_count == attempt_budget
    assert plan.call_count == (1 if attempt_budget > 1 else 0)
    assert all(call.kwargs["ref_images"] == refs for call in generate.call_args_list)
    assert len({call.args[1] for call in generate.call_args_list}) == 1


@pytest.mark.parametrize("noun", ["冰箱门", "衣柜门", "烤箱门", "车门", "电梯门"])
def test_object_doors_do_not_trigger_room_door_rules(noun):
    from app.services.script.image_prompt import assemble_daily_t2i_prompt

    prompt = assemble_daily_t2i_prompt({"speakers":["昭昭","灿灿"], "visual_brief":f"昭昭站在{noun}旁边，灿灿叉腰。", "shot_type":"中景"})
    assert "一扇单开门" not in prompt
    items,_,_=AgnesImageProvider._build_verify_checklist(prompt=prompt, expected_speakers=["昭昭","灿灿"], content_style="daily_story")
    assert "door_single" not in dict(items)
    items,_,_=AgnesImageProvider._build_verify_checklist(prompt=prompt+"房门半掩。", expected_speakers=["昭昭","灿灿"], content_style="daily_story")
    assert "door_single" in dict(items)


def test_ambiguous_door_word_checks_room_entrances_only():
    items, _, _ = AgnesImageProvider._build_verify_checklist(
        prompt="客厅角落放着双门冰箱，关着门。", expected_speakers=["昭昭", "灿灿"],
        content_style="daily_story",
    )
    question = dict(items)["door_single"]
    assert "仅检查房间出入口" in question
    assert "不包括家电、柜体、车辆或电梯门" in question


def test_limb_api_failure_preserves_image_without_redrawing(tmp_path):
    provider = AgnesImageProvider()
    output = tmp_path / "frame.png"
    PILImage.new("RGB", (32, 32), "white").save(output)
    original = output.read_bytes()
    response = MagicMock(status_code=200, ok=True)
    response.json.return_value = {"choices": [{"message": {"content": "项1: 是"}}]}
    with (
        patch("app.services.segment.image.image_agnes.agnes_api_keys", return_value=[AgnesApiKey("cn_free", "test-key")]),
        patch.object(provider, "_generate_with_key", return_value=output) as generate,
        patch.object(AgnesImageProvider, "_build_verify_checklist", return_value=([("scene", "场景一致吗")], "检查图像", None)),
        patch.object(provider, "_run_blocking_cancellable", side_effect=lambda fn: fn()),
        patch("requests.post", return_value=response),
        patch.object(provider, "_ask_hardfail_vl", return_value=None),
        patch.object(provider, "_plan_excess_people_edit") as plan,
        pytest.raises(AgnesImageVerificationUnavailable, match="肢体质检未完成"),
    ):
        provider.generate("原剧情", output, expected_speakers=["昭昭", "灿灿"], content_style="daily_story")
    generate.assert_called_once()
    plan.assert_not_called()
    assert output.read_bytes() == original
