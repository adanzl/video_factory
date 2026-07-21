from app.services.segment.image.image_sd15 import (
    build_sd15_full_prompt,
    fallback_split_panel_prompts,
    normalize_sd15_prompt_en,
    parse_sd15_prompt_payload,
    pick_business_by_keywords,
    pick_lora_by_keywords,
    resolve_split_axis,
    wants_science_dna_lora,
    wants_split_panel,
    weight_for_lora,
)


def test_parse_sd15_prompt_payload():
    raw = {
        "layout": "single",
        "prompt_en": "cell diagram, labeled parts",
        "business": "science",
        "lora": "Textbook_Line_Art",
    }
    assert parse_sd15_prompt_payload(raw) == {
        "layout": "single",
        "prompt_en": "cell diagram, labeled parts",
        "business": "science",
        "lora": "Textbook_Line_Art",
    }


def test_parse_sd15_prompt_payload_split():
    raw = {
        "layout": "split",
        "left_en": "blue wet fabric fiber mesh, red CO molecules passing through gaps",
        "right_en": "lung alveoli air sacs, red blood cells turning dark",
        "business": "science",
        "lora": "Simple_Diagram",
    }
    result = parse_sd15_prompt_payload(raw)
    assert result["layout"] == "split"
    assert result["business"] == "science"
    assert result["lora"] == "Simple_Diagram"
    assert "fiber mesh" in result["left_en"]
    assert "alveoli" in result["right_en"]


def test_parse_sd15_prompt_payload_rejects_invalid_lora():
    raw = {
        "prompt_en": "test scene",
        "business": "science",
        "lora": "Not_A_Real_Lora",
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
        "layout": "single",
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
    assert weight_for_lora("Science_DNA_Style") == 0.7


def test_pick_lora_by_keywords_molecules():
    assert pick_lora_by_keywords("一氧化碳分子穿过湿布纤维网") == "Science_DNA_Style"


def test_wants_split_panel():
    assert wants_split_panel(
        prompt="左侧湿布纤维，右侧肺泡截面，左右对比",
        width=640,
        height=360,
        business="science",
    )
    assert wants_split_panel(
        prompt="细胞结构示意图",
        width=640,
        height=360,
        business="science",
    )
    assert wants_split_panel(
        prompt="上方分子穿过湿布，下方肺泡截面，上下对比",
        width=360,
        height=640,
        business="science",
    )
    assert not wants_split_panel(
        prompt="细胞结构示意图",
        width=360,
        height=640,
        business="science",
    )
    assert not wants_split_panel(
        prompt="左右对比示意图",
        width=640,
        height=360,
        business="life",
    )


def test_resolve_split_axis():
    assert (
        resolve_split_axis(
            prompt="细胞结构",
            width=640,
            height=360,
            business="science",
        )
        == "horizontal"
    )
    assert (
        resolve_split_axis(
            prompt="上下对比，上方分子下方器官",
            width=360,
            height=640,
            business="science",
        )
        == "vertical"
    )
    assert (
        resolve_split_axis(
            prompt="单细胞结构",
            width=360,
            height=640,
            business="science",
        )
        is None
    )


def test_fallback_split_panel_prompts_co():
    left, right = fallback_split_panel_prompts("一氧化碳穿过湿布，右侧展示肺泡与血红蛋白变化")
    assert "carbon monoxide" in left.casefold() or "molecules" in left.casefold()
    assert "alveoli" in right.casefold() or "lung" in right.casefold()


def test_normalize_left_panel_keeps_glowing():
    from app.services.segment.image.image_sd15 import normalize_sd15_panel_prompt_en

    cleaned = normalize_sd15_panel_prompt_en(
        "red glowing carbon monoxide molecules, blue mesh",
        panel="left",
        business="science",
        lora="Simple_Diagram",
    )
    assert "glowing" in cleaned.casefold()


def test_wants_science_dna_lora():
    assert wants_science_dna_lora(
        prompt="一氧化碳科普",
        subject="red CO molecules passing mesh",
    )
    assert not wants_science_dna_lora(prompt="厨房美食", subject="steaming pot")


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
    # single 面板保留 glowing；仅 right 面板剥离
    assert "glowing" in lower
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
    from app.services.segment.image.image_sd15 import science_wants_anime

    assert science_wants_anime("日系动漫风格科普插图") is True
    assert science_wants_anime("写实科普插画，一氧化碳分子示意图") is False


def test_build_sd15_full_prompt_science_suffix():
    full = build_sd15_full_prompt(
        subject="CO molecule passing wet cloth mesh, lung alveoli icon",
        business="science",
        lora="Simple_Diagram",
    )
    assert full.startswith("<lora:Simple_Diagram:0.65>")
    assert "clean light background" in full
    assert "educational illustration" in full
    assert "person" not in full.casefold()


def test_build_sd15_full_prompt_split_panels():
    left = build_sd15_full_prompt(
        subject="blue wet fabric fiber mesh, red CO molecules",
        business="science",
        lora="Simple_Diagram",
        layout="split",
        panel="left",
        source_prompt="一氧化碳分子穿过湿布，右侧肺泡",
    )
    right = build_sd15_full_prompt(
        subject="lung alveoli air sacs, red blood cells turning dark",
        business="science",
        lora="Simple_Diagram",
        layout="split",
        panel="right",
        source_prompt="一氧化碳分子穿过湿布，右侧肺泡",
    )
    assert "<lora:Simple_Diagram:0.65>" in left
    assert "<lora:Science_DNA_Style:0.7>" in left
    assert "ScienceDNAStyle" in left
    assert "macro scientific illustration" in left
    assert "medical cross-section illustration" in right
    assert "lung" not in left.casefold()
    assert "Science_DNA_Style" not in right


def test_build_sd15_full_prompt_science_dna_single():
    full = build_sd15_full_prompt(
        subject="red glowing carbon monoxide molecules, blue mesh",
        business="science",
        lora="Science_DNA_Style",
    )
    assert full.startswith("<lora:Science_DNA_Style:0.7> ScienceDNAStyle,")
    assert "glowing" in full.casefold()


def _word_count(text: str) -> int:
    import re

    return len(re.findall(r"[A-Za-z0-9']+", text))
