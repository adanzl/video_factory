"""成片流水线辅助（多流水线注册见 app.core.pipelines）。"""

from __future__ import annotations

from app.core.pipelines import STAGES, stage_index, stages_for

__all__ = ["STAGES", "stage_index", "stages_for", "should_stop_before_publish"]


def should_stop_before_publish(job: dict) -> bool:
    return bool(job.get("skip_publish"))
