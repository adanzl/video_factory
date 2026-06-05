from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal


@dataclass
class QualityReport:
    level: Literal["pass", "minor", "major"]
    fail_stage: str | None = None
    bad_segment_ids: list[int] = field(default_factory=list)
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)
