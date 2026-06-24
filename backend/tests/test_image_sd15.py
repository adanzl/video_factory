from unittest.mock import patch

from app.services.visual.image_sd15 import (
    _fallback_business,
    _fallback_prompt_en,
    _prepare_sd15_prompt,
    business_from_size,
    parse_image_size,
)
from app.services.llm.llm_sd15_prompt import pick_lora_by_keywords


def test_parse_image_size():
    assert parse_image_size("720*1280") == (720, 1280)
    assert parse_image_size("1280x720") == (1280, 720)


def test_business_from_size():
    assert business_from_size(720, 1280) == "science"
    assert business_from_size(1280, 720) == "life"
    assert business_from_size(768, 768) == "life"


def test_fallback_business_from_lora():
    assert _fallback_business(lora="Food_Photo", business_override=None) == "life"
    assert _fallback_business(lora="Textbook_Line_Art", business_override=None) == "science"


def test_fallback_lora_by_keywords():
    lora = pick_lora_by_keywords("厨房美食特写")
    assert lora == "Food_Photo"


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
        prep = _prepare_sd15_prompt("实验室显微镜特写，柔和顶光", size_hint="576*768")

    assert prep.business == "science"
    assert prep.lora == "Textbook_Line_Art"
    assert prep.prompt_en == "lab bench, microscope, soft light"
