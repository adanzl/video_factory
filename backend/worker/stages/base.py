from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar

from worker.context import JobContext


class StageExecutor(ABC):
    name: ClassVar[str]
    next_stage: ClassVar[type[StageExecutor] | None] = None

    def next_stage_name(self) -> str:
        nxt = type(self).next_stage
        return nxt.name if nxt is not None else "done"

    @abstractmethod
    def run(self, ctx: JobContext) -> None:
        ...
