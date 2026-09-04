"""F–N 扩展类型：均已注册独立观感 profile，不回落 C。"""

from __future__ import annotations

import pytest

from app.services.daily_story.story_types import STORY_TYPE_LINES
from app.services.daily_story.story_types.quality import quality_profile_for_code


@pytest.mark.parametrize("code", ["F", "G", "H", "I", "J", "K", "L", "N", "O"])
def test_extended_type_registered(code: str):
    assert code in STORY_TYPE_LINES
    assert STORY_TYPE_LINES[code].code == code


@pytest.mark.parametrize("code", ["F", "G", "H", "I", "J", "K", "L", "N", "O"])
def test_extended_quality_profile_not_c(code: str):
    assert quality_profile_for_code(code).code == code
