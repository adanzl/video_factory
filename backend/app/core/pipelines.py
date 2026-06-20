"""双流水线注册：standard（AI 分镜）与 material（视频素材基底）。"""

from __future__ import annotations

from worker.stages.base import StageExecutor
from worker.stages.common.cover import CoverStage
from worker.stages.common.intro import IntroStage
from worker.stages.common.publish import PublishStage
from worker.stages.common.tts import TTSStage
from worker.stages.standard.host import HostStage
from worker.stages.standard.merge import MergeStage
from worker.stages.standard.script import ScriptStage
from worker.stages.standard.segment import SegmentStage
from worker.stages.standard.title import TitleStage

PIPELINE_STANDARD = "standard"
PIPELINE_MATERIAL = "material"

STANDARD_CHAIN: tuple[type[StageExecutor], ...] = (
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


def _material_chain() -> tuple[type[StageExecutor], ...]:
    from worker.stages.material.merge import MaterialMergeStage
    from worker.stages.material.prepare import MaterialPrepareStage
    from worker.stages.material.script import MaterialScriptStage

    return (
        MaterialPrepareStage,
        MaterialScriptStage,
        IntroStage,
        CoverStage,
        TTSStage,
        MaterialMergeStage,
        PublishStage,
    )


PIPELINES: dict[str, tuple[type[StageExecutor], ...]] = {
    PIPELINE_STANDARD: STANDARD_CHAIN,
    PIPELINE_MATERIAL: _material_chain(),
}

STAGES_BY_PIPELINE: dict[str, tuple[str, ...]] = {}
STAGE_CLASS_BY_KEY: dict[tuple[str, str], type[StageExecutor]] = {}
EXECUTORS: dict[tuple[str, str], StageExecutor] = {}

# 兼容旧代码：默认标准流水线 stage 名列表
STAGES: tuple[str, ...] = ()


def _build_registry() -> None:
    global STAGES
    STAGES_BY_PIPELINE.clear()
    STAGE_CLASS_BY_KEY.clear()
    EXECUTORS.clear()

    for pipeline_name, chain in PIPELINES.items():
        stage_names = tuple(stage_cls.name for stage_cls in chain) + ("done",)
        STAGES_BY_PIPELINE[pipeline_name] = stage_names
        for stage_cls in chain:
            key = (pipeline_name, stage_cls.name)
            STAGE_CLASS_BY_KEY[key] = stage_cls
            EXECUTORS[key] = stage_cls()

    STAGES = STAGES_BY_PIPELINE[PIPELINE_STANDARD]


_build_registry()


def resolve_pipeline(job: dict) -> str:
    name = (job.get("pipeline") or PIPELINE_STANDARD).strip()
    if name not in PIPELINES:
        return PIPELINE_STANDARD
    return name


def stages_for(job: dict | None = None, *, pipeline: str | None = None) -> tuple[str, ...]:
    if pipeline is not None:
        return STAGES_BY_PIPELINE.get(pipeline, STAGES_BY_PIPELINE[PIPELINE_STANDARD])
    if job is None:
        return STAGES_BY_PIPELINE[PIPELINE_STANDARD]
    return STAGES_BY_PIPELINE[resolve_pipeline(job)]


def stage_index(stage: str, job: dict | None = None, *, pipeline: str | None = None) -> int:
    return stages_for(job, pipeline=pipeline).index(stage)


def stage_class_for(
    stage_name: str,
    job: dict | None = None,
    *,
    pipeline: str | None = None,
) -> type[StageExecutor]:
    pipe = pipeline or (resolve_pipeline(job) if job is not None else PIPELINE_STANDARD)
    key = (pipe, stage_name)
    try:
        return STAGE_CLASS_BY_KEY[key]
    except KeyError as exc:
        raise ValueError(f"unknown stage {stage_name!r} for pipeline {pipe!r}") from exc


def executor_for_stage(
    stage_name: str,
    job: dict | None = None,
    *,
    pipeline: str | None = None,
) -> StageExecutor:
    pipe = pipeline or (resolve_pipeline(job) if job is not None else PIPELINE_STANDARD)
    key = (pipe, stage_name)
    try:
        return EXECUTORS[key]
    except KeyError as exc:
        raise ValueError(f"unknown stage {stage_name!r} for pipeline {pipe!r}") from exc


def first_stage_class(job: dict | None = None, *, pipeline: str | None = None) -> type[StageExecutor]:
    pipe = pipeline or (resolve_pipeline(job) if job is not None else PIPELINE_STANDARD)
    return PIPELINES[pipe][0]


def next_stage_class(
    current: type[StageExecutor],
    job: dict | None = None,
    *,
    pipeline: str | None = None,
) -> type[StageExecutor] | None:
    pipe = pipeline or (resolve_pipeline(job) if job is not None else PIPELINE_STANDARD)
    chain = PIPELINES[pipe]
    try:
        index = chain.index(current)
    except ValueError as exc:
        raise ValueError(f"{current.name} not in pipeline {pipe!r}") from exc
    if index + 1 >= len(chain):
        return None
    return chain[index + 1]


def is_material_job(job: dict) -> bool:
    return resolve_pipeline(job) == PIPELINE_MATERIAL


__all__ = [
    "EXECUTORS",
    "MATERIAL_CHAIN",
    "PIPELINE_MATERIAL",
    "PIPELINE_STANDARD",
    "PIPELINES",
    "STAGE_CLASS_BY_KEY",
    "STAGES",
    "STAGES_BY_PIPELINE",
    "STANDARD_CHAIN",
    "executor_for_stage",
    "first_stage_class",
    "is_material_job",
    "next_stage_class",
    "resolve_pipeline",
    "stage_class_for",
    "stage_index",
    "stages_for",
]

# 延迟导出 MATERIAL_CHAIN，避免循环 import 时未构建
MATERIAL_CHAIN = PIPELINES[PIPELINE_MATERIAL]
