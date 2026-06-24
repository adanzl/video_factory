from app.services.llm.llm_sd15_prompt import (
    build_sd15_full_prompt,
    normalize_sd15_prompt_en,
    parse_sd15_prompt_payload,
    pick_business_by_keywords,
    pick_lora_by_keywords,
    weight_for_lora,
)


def test_parse_sd15_prompt_payload():
    raw = {
        "prompt_en": "cell diagram, labeled parts",
        "business": "science",
        "lora": "Textbook_Line_Art",
    }
    assert parse_sd15_prompt_payload(raw) == {
        "prompt_en": "cell diagram, labeled parts",
        "business": "science",
        "lora": "Textbook_Line_Art",
    }


def test_parse_sd15_prompt_payload_rejects_invalid_lora():
    raw = {
        "prompt_en": "test scene",
        "business": "science",
        "lora": "Laboratory_Scene",
    }
    try:
        parse_sd15_prompt_payload(raw)
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "invalid lora" in str(exc)


def test_parse_sd15_prompt_payload_rejects_missing_business():
    raw = {
        "prompt_en": "test scene",
        "lora": "Casual_Life",
    }
    try:
        parse_sd15_prompt_payload(raw)
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "invalid business" in str(exc)


def test_parse_sd15_prompt_payload_business_override():
    raw = {
        "prompt_en": "test scene",
        "business": "life",
        "lora": "Casual_Life",
    }
    assert parse_sd15_prompt_payload(raw, business_override="science") == {
        "prompt_en": "test scene",
        "business": "science",
        "lora": "Casual_Life",
    }


def test_pick_lora_by_keywords_food():
    assert pick_lora_by_keywords("妈妈在厨房烹饪晚餐，暖色窗光") == "Food_Photo"


def test_pick_lora_by_keywords_diagram():
    assert pick_lora_by_keywords("流程图展示三个步骤的对比示意图") == "Simple_Diagram"


def test_pick_lora_by_keywords_default():
    assert pick_lora_by_keywords("一个人在公园散步") == "Casual_Life"


def test_pick_business_by_keywords_life():
    assert pick_business_by_keywords("妈妈在厨房烹饪晚餐，写实摄影风") == "life"


def test_pick_business_by_keywords_science():
    assert pick_business_by_keywords("细胞结构示意图，科普讲解") == "science"


def test_weight_for_lora():
    assert weight_for_lora("Food_Photo") == 0.6
    assert weight_for_lora("Simple_Diagram") == 0.55


def test_normalize_sd15_prompt_en_strips_character_terms():
    raw = (
        "comparison diagram, CO molecule, lung alveoli, "
        "head of person drooping, glowing molecules"
    )
    cleaned = normalize_sd15_prompt_en(
        raw,
        business="science",
        lora="Simple_Diagram",
    )
    lower = cleaned.casefold()
    assert "person" not in lower
    assert "head" not in lower
    assert "glowing" not in lower
    assert "co molecule" in lower


def test_normalize_sd15_prompt_en_truncates_long_prompt():
    parts = [f"detail clause number {index} with extra descriptive words" for index in range(30)]
    raw = ", ".join(parts)
    cleaned = normalize_sd15_prompt_en(
        raw,
        business="science",
        lora="Simple_Diagram",
    )
    assert _word_count(cleaned) <= 55


def test_science_wants_anime():
    from app.services.llm.llm_sd15_prompt import science_wants_anime

    assert science_wants_anime("日系动漫风格科普插图") is True
    assert science_wants_anime("写实科普插画，一氧化碳分子示意图") is False


def test_build_sd15_full_prompt_science_suffix():
    full = build_sd15_full_prompt(
        subject="CO molecule passing wet cloth mesh, lung alveoli icon",
        business="science",
        lora="Simple_Diagram",
    )
    assert full.startswith("<lora:Simple_Diagram:0.55>")
    assert "white background, line art" in full
    assert "person" not in full.casefold()


def _word_count(text: str) -> int:
    import re

    return len(re.findall(r"[A-Za-z0-9']+", text))
