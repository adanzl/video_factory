"""Stage 名称工具（无 worker 依赖，避免循环 import）。"""

from __future__ import annotations

# cover 已并入 intro；兼容旧 job.stage / API action
LEGACY_STAGE_ALIASES: dict[str, str] = {"cover": "intro"}


def normalize_stage(stage: str) -> str:
    return LEGACY_STAGE_ALIASES.get(stage, stage)
