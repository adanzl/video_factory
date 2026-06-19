"""成片流水线 stage 顺序与跳转。

顺序在 worker/stages/registry.py 的 STAGE_CHAIN 中显式注册。
"""

from __future__ import annotations

from worker.stages.registry import STAGES, stage_index

__all__ = ["STAGES", "stage_index", "should_stop_before_publish"]


def should_stop_before_publish(job: dict) -> bool:
    return bool(job.get("skip_publish"))
