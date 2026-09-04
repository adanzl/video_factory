"""金故事 M 机制与 A–E/F/J/K 结构映射。"""

from __future__ import annotations

import pytest

from app.services.daily_story.gold_story.types import (
    GOLD_STORY_MECHANISM_CODES,
    GOLD_STORY_STRUCTURE_CODES,
    MECHANISM_STRUCTURE_MAP,
    allowed_structure_types,
    catalog_entry,
    is_injectable_structure_type,
    mechanism_label,
    normalize_mechanism,
    normalize_structure_type,
    structure_type_for_mechanism,
    structure_type_label,
    validate_mechanism_structure_pair,
)


@pytest.mark.parametrize(
    ("mechanism", "structure"),
    sorted(MECHANISM_STRUCTURE_MAP.items()),
)
def test_mechanism_structure_map(mechanism: str, structure: str):
    assert structure_type_for_mechanism(mechanism) == structure
    validate_mechanism_structure_pair(mechanism, structure)


def test_normalize_mechanism_ok():
    assert normalize_mechanism("m2") == "M2"
    assert mechanism_label("M2") == "自私包装公平"


def test_normalize_mechanism_rejects_type_codes():
    with pytest.raises(ValueError, match="mechanism must be"):
        normalize_mechanism("C")


def test_normalize_structure_type_extended_f():
    assert normalize_structure_type("f") == "F"
    assert structure_type_label("F") == "互呛加码"
    assert catalog_entry("F") is not None


def test_m3_maps_to_f_not_injectable():
    assert structure_type_for_mechanism("M3") == "F"
    assert not is_injectable_structure_type("F")


def test_m2_injectable_c():
    assert structure_type_for_mechanism("M2") == "C"
    assert is_injectable_structure_type("C")


def test_m4_maps_to_g_injectable():
    assert structure_type_for_mechanism("M4") == "G"
    assert is_injectable_structure_type("G")


def test_g_structure_label():
    assert structure_type_label("G") == "嘴硬心软"
    assert catalog_entry("G") is not None


def test_h_structure_label():
    assert structure_type_label("H") == "第三方化解"
    assert catalog_entry("H") is not None
    assert not is_injectable_structure_type("H")


def test_m11_maps_to_i_not_injectable():
    assert normalize_mechanism("M11") == "M11"
    assert mechanism_label("M11") == "灵魂拷问"
    assert structure_type_for_mechanism("M11") == "I"
    assert structure_type_label("I") == "问倒收束"
    assert catalog_entry("I") is not None
    assert not is_injectable_structure_type("I")
    validate_mechanism_structure_pair("M11", "I")


def test_m5_allows_a_g_h_or_j():
    assert allowed_structure_types("M5") == frozenset({"A", "G", "H", "J"})
    validate_mechanism_structure_pair("M5", "A")
    validate_mechanism_structure_pair("M5", "G")
    validate_mechanism_structure_pair("M5", "H")
    validate_mechanism_structure_pair("M5", "J")


def test_m8_allows_a_or_j():
    assert allowed_structure_types("M8") == frozenset({"A", "J"})
    validate_mechanism_structure_pair("M8", "A")
    validate_mechanism_structure_pair("M8", "J")
    assert structure_type_for_mechanism("M8") == "A"
    assert structure_type_label("J") == "权威压住"
    assert catalog_entry("J") is not None
    assert not is_injectable_structure_type("J")


def test_m12_maps_to_k_not_injectable():
    assert normalize_mechanism("M12") == "M12"
    assert mechanism_label("M12") == "家长旁观"
    assert structure_type_for_mechanism("M12") == "K"
    assert structure_type_label("K") == "家长看戏"
    assert catalog_entry("K") is not None
    assert not is_injectable_structure_type("K")
    validate_mechanism_structure_pair("M12", "K")
    with pytest.raises(ValueError, match="M12 对应 structure_type"):
        validate_mechanism_structure_pair("M12", "H")


def test_m6_maps_to_n_not_injectable():
    assert normalize_mechanism("M6") == "M6"
    assert mechanism_label("M6") == "正经胡说"
    assert structure_type_for_mechanism("M6") == "N"
    assert structure_type_label("N") == "正经胡说"
    assert catalog_entry("N") is not None
    assert not is_injectable_structure_type("N")
    assert allowed_structure_types("M6") == frozenset({"N", "A", "E"})
    validate_mechanism_structure_pair("M6", "N")
    validate_mechanism_structure_pair("M6", "A")


def test_m13_maps_to_o_not_injectable():
    assert normalize_mechanism("M13") == "M13"
    assert mechanism_label("M13") == "顾赛不顾奖"
    assert structure_type_for_mechanism("M13") == "O"
    assert structure_type_label("O") == "目标错位"
    assert catalog_entry("O") is not None
    assert not is_injectable_structure_type("O")
    assert allowed_structure_types("M13") == frozenset({"O"})
    validate_mechanism_structure_pair("M13", "O")
    with pytest.raises(ValueError, match="M13 对应 structure_type"):
        validate_mechanism_structure_pair("M13", "C")


def test_pair_mismatch_raises():
    with pytest.raises(ValueError, match="M2 对应 structure_type"):
        validate_mechanism_structure_pair("M2", "A")


def test_all_mechanisms_mapped():
    assert set(MECHANISM_STRUCTURE_MAP) == GOLD_STORY_MECHANISM_CODES
    for letter in MECHANISM_STRUCTURE_MAP.values():
        assert letter in GOLD_STORY_STRUCTURE_CODES
