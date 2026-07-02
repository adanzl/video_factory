from unittest.mock import patch

from app.services.segment.image.image_sd15 import (
    _fallback_business,
    _fallback_prompt_en,
    _prepare_sd15_prompt,
    _stitch_horizontal,
    parse_image_size,
)
from app.services.segment.image.image_sd15 import pick_business_by_keywords, pick_lora_by_keywords


def test_parse_image_size():
    assert parse_image_size("720*1280") == (720, 1280)
    assert parse_image_size("1280x720") == (1280, 720)


def test_fallback_business_from_prompt():
    assert _fallback_business(prompt="厨房美食写实摄影", business_override=None) == "life"
    assert _fallback_business(prompt="细胞结构科普示意图", business_override=None) == "science"


def test_fallback_business_override():
    assert _fallback_business(prompt="厨房美食", business_override="science") == "science"


def test_fallback_lora_by_keywords():
    lora = pick_lora_by_keywords("厨房美食特写")
    assert lora == "Food_Photo"


def test_pick_business_independent_of_lora():
    business = pick_business_by_keywords("实验室显微镜特写，柔和顶光")
    lora = pick_lora_by_keywords("实验室显微镜特写，柔和顶光")
    assert business == "science"
    assert lora == "Casual_Life"


def test_fallback_prompt_en_chinese_generic():
    result = _fallback_prompt_en("厨房里的妈妈正在切菜，暖色窗光")
    assert "illustration" in result


def test_prepare_sd15_prompt_uses_llm(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.delenv("MOCK_MODE", raising=False)

    from app.config import config

    monkeypatch.setattr(config, "deepseek_api_key", "test-key", raising=False)
    monkeypatch.setattr(config, "mock_mode", False, raising=False)

    with patch(
        "app.services.segment.image.image_sd15.llm_mgr.prepare_sd15_image_prompt",
        return_value={
            "layout": "single",
            "prompt_en": "lab bench, microscope, soft light",
            "business": "science",
            "lora": "Textbook_Line_Art",
        },
    ):
        prep = _prepare_sd15_prompt("实验室显微镜特写，柔和顶光", size_hint="360*640")

    assert prep.layout == "single"
    assert prep.business == "science"
    assert prep.lora == "Textbook_Line_Art"
    assert prep.prompt_en == "lab bench, microscope, soft light"


def test_prepare_sd15_prompt_landscape_science_forces_split(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.delenv("MOCK_MODE", raising=False)

    from app.config import config

    monkeypatch.setattr(config, "deepseek_api_key", "test-key", raising=False)
    monkeypatch.setattr(config, "mock_mode", False, raising=False)

    with patch(
        "app.services.segment.image.image_sd15.llm_mgr.prepare_sd15_image_prompt",
        return_value={
            "layout": "single",
            "prompt_en": "lab bench, microscope, soft light",
            "business": "science",
            "lora": "Textbook_Line_Art",
        },
    ):
        prep = _prepare_sd15_prompt("实验室显微镜特写，柔和顶光", size_hint="640*360")

    assert prep.layout == "split"
    assert prep.split_axis == "horizontal"


def test_prepare_sd15_prompt_split_from_llm(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.delenv("MOCK_MODE", raising=False)

    from app.config import config

    monkeypatch.setattr(config, "deepseek_api_key", "test-key", raising=False)
    monkeypatch.setattr(config, "mock_mode", False, raising=False)

    with patch(
        "app.services.segment.image.image_sd15.llm_mgr.prepare_sd15_image_prompt",
        return_value={
            "layout": "split",
            "left_en": "wet cloth fiber mesh, CO molecules",
            "right_en": "lung alveoli, blood cells",
            "business": "science",
            "lora": "Simple_Diagram",
        },
    ):
        prep = _prepare_sd15_prompt("左侧湿布右侧肺泡对比", size_hint="640*360")

    assert prep.layout == "split"
    assert "fiber mesh" in prep.left_en
    assert "alveoli" in prep.right_en


def test_resolve_checkpoint_defaults():
    from app.services.segment.image.image_sd15 import _resolve_checkpoint

    assert (
        _resolve_checkpoint(business="science", prompt="写实科普插画，细胞结构示意图")
        == "Deliberate_v6_SFW.safetensors"
    )
    assert (
        _resolve_checkpoint(business="science", prompt="写实科普插画", panel="right")
        == "RealisticVisionV51.safetensors"
    )
    assert (
        _resolve_checkpoint(business="science", prompt="日系动漫风格科普")
        == "ToonYouBeta6.safetensors"
    )


def test_stitch_horizontal():
    from PIL import Image
    import io

    left = Image.new("RGB", (320, 360), color=(255, 0, 0))
    right = Image.new("RGB", (320, 360), color=(0, 0, 255))
    left_buf = io.BytesIO()
    right_buf = io.BytesIO()
    left.save(left_buf, format="PNG")
    right.save(right_buf, format="PNG")
    stitched = _stitch_horizontal(left_buf.getvalue(), right_buf.getvalue())
    out = Image.open(io.BytesIO(stitched))
    assert out.size == (640, 360)
    assert out.getpixel((0, 0)) == (255, 0, 0)
    assert out.getpixel((400, 0)) == (0, 0, 255)


def test_generate_single_uses_job_size(monkeypatch, tmp_path):
    from app.services.segment.image.image_sd15 import Sd15ImageProvider

    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.delenv("MOCK_MODE", raising=False)

    from app.config import config

    monkeypatch.setattr(config, "deepseek_api_key", "test-key", raising=False)
    monkeypatch.setattr(config, "mock_mode", False, raising=False)
    monkeypatch.setattr(config, "sd_api_url", "http://127.0.0.1:9101", raising=False)

    captured: dict = {}

    def fake_post(url, json=None, timeout=None):
        if url.endswith("/sdapi/v1/options"):
            captured.setdefault("checkpoints", []).append(json.get("sd_model_checkpoint"))
            class Resp:
                def raise_for_status(self):
                    return None

            return Resp()
        if url.endswith("/sdapi/v1/txt2img"):
            captured.setdefault("payloads", []).append(json)
            class Resp:
                def raise_for_status(self):
                    return None

                def json(self):
                    import base64

                    return {"images": [base64.b64encode(b"png").decode()]}

            return Resp()
        class Resp:
            def raise_for_status(self):
                return None

        return Resp()

    with patch(
        "app.services.segment.image.image_sd15.llm_mgr.prepare_sd15_image_prompt",
        return_value={
            "layout": "single",
            "prompt_en": "cell diagram",
            "business": "science",
            "lora": "Textbook_Line_Art",
        },
    ), patch("app.services.segment.image.image_sd15.requests.post", side_effect=fake_post):
        provider = Sd15ImageProvider()
        out = tmp_path / "seg.png"
        provider.generate("细胞结构示意图", out, size="360*640")

    payload = captured["payloads"][0]
    assert payload["width"] == 360
    assert payload["height"] == 640
    assert captured["checkpoints"][0] == "Deliberate_v6_SFW.safetensors"
    assert "white background, line art" in payload["prompt"]
    assert payload["steps"] == 25
    assert out.exists()


def test_stitch_vertical():
    from PIL import Image
    import io

    from app.services.segment.image.image_sd15 import _stitch_vertical

    top = Image.new("RGB", (360, 320), color=(255, 0, 0))
    bottom = Image.new("RGB", (360, 320), color=(0, 0, 255))
    top_buf = io.BytesIO()
    bottom_buf = io.BytesIO()
    top.save(top_buf, format="PNG")
    bottom.save(bottom_buf, format="PNG")
    stitched = _stitch_vertical(top_buf.getvalue(), bottom_buf.getvalue())
    out = Image.open(io.BytesIO(stitched))
    assert out.size == (360, 640)
    assert out.getpixel((0, 0)) == (255, 0, 0)
    assert out.getpixel((0, 400)) == (0, 0, 255)


def test_generate_split_stitches_panels_vertical(monkeypatch, tmp_path):
    from app.services.segment.image.image_sd15 import Sd15ImageProvider

    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.delenv("MOCK_MODE", raising=False)

    from app.config import config

    monkeypatch.setattr(config, "deepseek_api_key", "test-key", raising=False)
    monkeypatch.setattr(config, "mock_mode", False, raising=False)
    monkeypatch.setattr(config, "sd_api_url", "http://127.0.0.1:9101", raising=False)

    captured: dict = {}

    def fake_post(url, json=None, timeout=None):
        if url.endswith("/sdapi/v1/options"):
            captured.setdefault("checkpoints", []).append(json.get("sd_model_checkpoint"))
            class Resp:
                def raise_for_status(self):
                    return None

            return Resp()
        if url.endswith("/sdapi/v1/txt2img"):
            captured.setdefault("payloads", []).append(json)
            from PIL import Image
            import base64
            import io

            height = json["height"]
            color = (255, 0, 0) if height == 320 and len(captured["payloads"]) == 1 else (0, 0, 255)
            img = Image.new("RGB", (json["width"], height), color=color)
            buf = io.BytesIO()
            img.save(buf, format="PNG")

            class Resp:
                def raise_for_status(self):
                    return None

                def json(self):
                    return {"images": [base64.b64encode(buf.getvalue()).decode()]}

            return Resp()
        class Resp:
            def raise_for_status(self):
                return None

        return Resp()

    with patch(
        "app.services.segment.image.image_sd15.llm_mgr.prepare_sd15_image_prompt",
        return_value={
            "layout": "split",
            "left_en": "wet cloth fiber mesh, CO molecules",
            "right_en": "lung alveoli, blood cells",
            "business": "science",
            "lora": "Simple_Diagram",
        },
    ), patch("app.services.segment.image.image_sd15.requests.post", side_effect=fake_post):
        provider = Sd15ImageProvider()
        out = tmp_path / "seg.png"
        provider.generate("上方湿布下方肺泡，上下对比", out, size="360*640")

    assert len(captured["payloads"]) == 2
    assert captured["payloads"][0]["height"] == 320
    assert captured["payloads"][1]["height"] == 320
    assert out.exists()

    from PIL import Image

    stitched = Image.open(out)
    assert stitched.size == (360, 640)


def test_generate_split_stitches_panels(monkeypatch, tmp_path):
    from app.services.segment.image.image_sd15 import Sd15ImageProvider

    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.delenv("MOCK_MODE", raising=False)

    from app.config import config

    monkeypatch.setattr(config, "deepseek_api_key", "test-key", raising=False)
    monkeypatch.setattr(config, "mock_mode", False, raising=False)
    monkeypatch.setattr(config, "sd_api_url", "http://127.0.0.1:9101", raising=False)

    captured: dict = {}

    def fake_post(url, json=None, timeout=None):
        if url.endswith("/sdapi/v1/options"):
            captured.setdefault("checkpoints", []).append(json.get("sd_model_checkpoint"))
            class Resp:
                def raise_for_status(self):
                    return None

            return Resp()
        if url.endswith("/sdapi/v1/txt2img"):
            captured.setdefault("payloads", []).append(json)
            from PIL import Image
            import base64
            import io

            width = json["width"]
            color = (255, 0, 0) if width == 320 and len(captured["payloads"]) == 1 else (0, 0, 255)
            img = Image.new("RGB", (width, json["height"]), color=color)
            buf = io.BytesIO()
            img.save(buf, format="PNG")

            class Resp:
                def raise_for_status(self):
                    return None

                def json(self):
                    return {"images": [base64.b64encode(buf.getvalue()).decode()]}

            return Resp()
        class Resp:
            def raise_for_status(self):
                return None

        return Resp()

    with patch(
        "app.services.segment.image.image_sd15.llm_mgr.prepare_sd15_image_prompt",
        return_value={
            "layout": "split",
            "left_en": "wet cloth fiber mesh, CO molecules",
            "right_en": "lung alveoli, blood cells",
            "business": "science",
            "lora": "Simple_Diagram",
        },
    ), patch("app.services.segment.image.image_sd15.requests.post", side_effect=fake_post):
        provider = Sd15ImageProvider()
        out = tmp_path / "seg.png"
        provider.generate("左侧湿布右侧肺泡对比", out, size="640*360")

    assert len(captured["payloads"]) == 2
    assert captured["payloads"][0]["width"] == 320
    assert captured["payloads"][1]["width"] == 320
    assert captured["checkpoints"] == [
        "Deliberate_v6_SFW.safetensors",
        "RealisticVisionV51.safetensors",
    ]
    assert "macro scientific illustration" in captured["payloads"][0]["prompt"]
    assert "<lora:Science_DNA_Style:0.7>" in captured["payloads"][0]["prompt"]
    assert "ScienceDNAStyle" in captured["payloads"][0]["prompt"]
    assert "medical cross-section illustration" in captured["payloads"][1]["prompt"]
    assert out.exists()

    from PIL import Image

    stitched = Image.open(out)
    assert stitched.size == (640, 360)
