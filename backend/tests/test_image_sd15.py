from unittest.mock import patch

from app.services.visual.image_sd15 import (
    _fallback_business,
    _fallback_prompt_en,
    _prepare_sd15_prompt,
    parse_image_size,
)
from app.services.llm.llm_sd15_prompt import pick_business_by_keywords, pick_lora_by_keywords


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
        "app.services.visual.image_sd15.llm_mgr.prepare_sd15_image_prompt",
        return_value={
            "prompt_en": "lab bench, microscope, soft light",
            "business": "science",
            "lora": "Textbook_Line_Art",
        },
    ):
        prep = _prepare_sd15_prompt("实验室显微镜特写，柔和顶光", size_hint="640*360")

    assert prep.business == "science"
    assert prep.lora == "Textbook_Line_Art"
    assert prep.prompt_en == "lab bench, microscope, soft light"


def test_generate_uses_job_size_not_business(monkeypatch, tmp_path):
    from app.services.visual.image_sd15 import Sd15ImageProvider

    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.delenv("MOCK_MODE", raising=False)

    from app.config import config

    monkeypatch.setattr(config, "deepseek_api_key", "test-key", raising=False)
    monkeypatch.setattr(config, "mock_mode", False, raising=False)
    monkeypatch.setattr(config, "sd_api_url", "http://127.0.0.1:9101", raising=False)

    captured: dict = {}

    def fake_post(url, json=None, timeout=None):
        if url.endswith("/sdapi/v1/txt2img"):
            captured["payload"] = json
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
        "app.services.visual.image_sd15.llm_mgr.prepare_sd15_image_prompt",
        return_value={
            "prompt_en": "cell diagram",
            "business": "science",
            "lora": "Textbook_Line_Art",
        },
    ), patch("app.services.visual.image_sd15.requests.post", side_effect=fake_post):
        provider = Sd15ImageProvider()
        out = tmp_path / "seg.png"
        provider.generate("细胞结构示意图", out, size="640*360")

    assert captured["payload"]["width"] == 640
    assert captured["payload"]["height"] == 360
    assert out.exists()
