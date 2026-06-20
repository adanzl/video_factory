"""Stage 注册表：从 app.core.pipelines 导出，兼容旧 import 路径。"""

from __future__ import annotations

from app.core.pipelines import (
    EXECUTORS,
    PIPELINE_STANDARD,
    STAGES,
    STAGE_CLASS_BY_KEY,
    executor_for_stage,
    stage_class_for,
)

__all__ = [
    "EXECUTORS",
    "STAGES",
    "STAGE_CLASS_BY_NAME",
    "executor_for",
    "stage_class",
]


# 标准流水线 stage 名 → class（兼容 loop / CLI）
STAGE_CLASS_BY_NAME: dict[str, type] = {
    name: cls for (pipe, name), cls in STAGE_CLASS_BY_KEY.items() if pipe == PIPELINE_STANDARD
}


def stage_class(name: str):
    return stage_class_for(name, pipeline=PIPELINE_STANDARD)


def executor_for(stage_cls: type) -> object:
    return executor_for_stage(stage_cls.name, pipeline=PIPELINE_STANDARD)
