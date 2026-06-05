from __future__ import annotations

from abc import ABC, abstractmethod

from worker.context import JobContext


class StageExecutor(ABC):
    name: str

    @abstractmethod
    def run(self, ctx: JobContext) -> None:
        ...
