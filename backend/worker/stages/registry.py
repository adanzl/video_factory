"""Stage 注册表：显式声明流水线顺序与 next_stage 链接。"""

from __future__ import annotations

from worker.stages.base import StageExecutor
from worker.stages.cover import CoverStage
from worker.stages.host import HostStage
from worker.stages.intro import IntroStage
from worker.stages.merge import MergeStage
from worker.stages.publish import PublishStage
from worker.stages.script import ScriptStage
from worker.stages.segment import SegmentStage
from worker.stages.title import TitleStage
from worker.stages.tts import TTSStage

STAGE_CHAIN: tuple[type[StageExecutor], ...] = (
    TitleStage,
    ScriptStage,
    IntroStage,
    CoverStage,
    TTSStage,
    SegmentStage,
    HostStage,
    MergeStage,
    PublishStage,
)


def _link_next_stages() -> None:
    for index, stage_cls in enumerate(STAGE_CHAIN):
        stage_cls.next_stage = STAGE_CHAIN[index + 1] if index + 1 < len(STAGE_CHAIN) else None


_link_next_stages()

EXECUTORS: dict[str, StageExecutor] = {stage_cls.name: stage_cls() for stage_cls in STAGE_CHAIN}
STAGE_CLASS_BY_NAME: dict[str, type[StageExecutor]] = {stage_cls.name: stage_cls for stage_cls in STAGE_CHAIN}
STAGES: tuple[str, ...] = tuple(stage_cls.name for stage_cls in STAGE_CHAIN) + ("done",)


def stage_class(name: str) -> type[StageExecutor]:
    try:
        return STAGE_CLASS_BY_NAME[name]
    except KeyError as exc:
        raise ValueError(f"unknown stage: {name}") from exc


def executor_for(stage_cls: type[StageExecutor]) -> StageExecutor:
    return EXECUTORS[stage_cls.name]


def stage_index(stage: str) -> int:
    return STAGES.index(stage)
