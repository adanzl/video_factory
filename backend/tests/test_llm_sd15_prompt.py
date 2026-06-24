from app.services.llm.llm_sd15_prompt import (
    parse_sd15_prompt_payload,
    pick_business_by_keywords,
    pick_lora_by_keywords,
    weight_for_lora,
)


def test_parse_sd15_prompt_payload():
    raw = {
        "prompt_en": "cell diagram, labeled parts, white background",
        "business": "science",
        "lora": "Textbook_Line_Art",
    }
    assert parse_sd15_prompt_payload(raw) == {
        "prompt_en": "cell diagram, labeled parts, white background",
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
    assert weight_for_lora("Simple_Diagram") == 0.65
