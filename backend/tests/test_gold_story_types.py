"""金故事 M 机制与结构类型映射（去重后只留主路径）。"""

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


def test_normalize_helpers():
    assert normalize_mechanism("m2") == "M2"
    assert mechanism_label("M2") == "自私包装公平"
    assert normalize_structure_type("f") == "F"
    assert structure_type_label("F") == "互呛加码"
    assert catalog_entry("F") is not None
    with pytest.raises(ValueError, match="mechanism must be"):
        normalize_mechanism("C")


def test_injectable_vs_extended():
    assert is_injectable_structure_type("C")
    assert not is_injectable_structure_type("F")
    assert not is_injectable_structure_type("J")
    assert not is_injectable_structure_type("O")


def test_multi_allow_sets():
    assert allowed_structure_types("M5") == frozenset({"A", "G", "H", "J"})
    assert allowed_structure_types("M8") == frozenset({"A", "J"})
    assert allowed_structure_types("M6") == frozenset({"N", "A", "E"})
    assert allowed_structure_types("M13") == frozenset({"O"})
    validate_mechanism_structure_pair("M5", "J")
    validate_mechanism_structure_pair("M8", "J")
    validate_mechanism_structure_pair("M6", "A")
    with pytest.raises(ValueError, match="M13 对应 structure_type"):
        validate_mechanism_structure_pair("M13", "C")


def test_pair_mismatch_raises():
    with pytest.raises(ValueError, match="M2 对应 structure_type"):
        validate_mechanism_structure_pair("M2", "A")


def test_all_mechanisms_mapped():
    assert set(MECHANISM_STRUCTURE_MAP) == GOLD_STORY_MECHANISM_CODES
    for letter in MECHANISM_STRUCTURE_MAP.values():
        assert letter in GOLD_STORY_STRUCTURE_CODES
