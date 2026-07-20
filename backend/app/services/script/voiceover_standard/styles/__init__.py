"""按 content_style 选择口播风格规则。"""

from __future__ import annotations

from dataclasses import dataclass

from app.utils.job_info import (
    CONTENT_STYLE_HISTORICAL_MYSTERY,
    CONTENT_STYLE_LIFE_EXPERIENCE,
    CONTENT_STYLE_TECH_SCIENCE,
)

from . import history_mystery, life_experience, science_child, tech_science
from .common import MATERIAL_LENGTH_RULE


@dataclass(frozen=True)
class StyleRules:
    role: str
    voice: str
    structure: str
    anti_rep: str
    layer_style: str
    length_rule: str


def resolve_style_rules(content_style: str) -> StyleRules:
    if content_style == CONTENT_STYLE_LIFE_EXPERIENCE:
        return StyleRules(
            role=life_experience.ROLE,
            voice=life_experience.VOICE,
            structure=life_experience.STRUCTURE,
            anti_rep=life_experience.ANTI_REPETITION,
            layer_style=life_experience.LAYER_STYLE,
            length_rule=life_experience.LENGTH_RULE,
        )
    if content_style == CONTENT_STYLE_HISTORICAL_MYSTERY:
        return StyleRules(
            role=history_mystery.ROLE,
            voice=history_mystery.VOICE,
            structure=history_mystery.STRUCTURE,
            anti_rep=history_mystery.ANTI_REPETITION,
            layer_style=history_mystery.LAYER_STYLE,
            length_rule=history_mystery.LENGTH_RULE,
        )
    if content_style == CONTENT_STYLE_TECH_SCIENCE:
        return StyleRules(
            role=tech_science.ROLE,
            voice=tech_science.VOICE,
            structure=tech_science.STRUCTURE,
            anti_rep=tech_science.ANTI_REPETITION,
            layer_style=tech_science.LAYER_STYLE,
            length_rule=MATERIAL_LENGTH_RULE,
        )
    return StyleRules(
        role=science_child.ROLE,
        voice=science_child.VOICE,
        structure=science_child.STRUCTURE,
        anti_rep=science_child.ANTI_REPETITION,
        layer_style=science_child.LAYER_STYLE,
        length_rule=MATERIAL_LENGTH_RULE,
    )


__all__ = ["StyleRules", "resolve_style_rules"]
