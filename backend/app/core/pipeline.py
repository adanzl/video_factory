"""成片流水线 stage 顺序与跳转。

业务顺序（与 worker/stages 一一对应）：

  title   → 标题确认（薄 stage，新 job 通常从 script 起跑）
  script  → 文案 + 分镜剧本（内含 copy / storyboard 质检）
  intro   → 片头 MP4
  cover   → 封面 JPG（由 intro.png 导出，不用 AI）
  tts     → 配音 + 句级字幕时间轴 + SRT（内含 tts 质检）
  segment → 分镜：ImageProvider 出图 → ClipProvider 片段（内含 visual / clip 质检）
  host    → 讲解人叠图（占位，HOST_ENABLED 未开时跳过）
  merge   → 合并正文 + 配音 + 片头 → final.mp4（内含 final 质检）
  publish → 投稿
  done

质检不单独占 stage，由各步骤完成后调用 app/quality 写入 quality_report。
"""

from __future__ import annotations

STAGES: tuple[str, ...] = (
    "title",
    "script",
    "intro",
    "cover",
    "tts",
    "segment",
    "host",
    "merge",
    "publish",
    "done",
)


def next_stage(current: str) -> str:
    try:
        idx = STAGES.index(current)
    except ValueError as exc:
        raise ValueError(f"unknown stage: {current}") from exc
    if idx >= len(STAGES) - 1:
        return "done"
    return STAGES[idx + 1]


def stage_index(stage: str) -> int:
    return STAGES.index(stage)


def should_stop_before_publish(job: dict) -> bool:
    return bool(job.get("skip_publish"))
