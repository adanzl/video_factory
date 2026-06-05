from __future__ import annotations

STAGES: tuple[str, ...] = (
    "title",
    "script",
    "image",
    "intro",
    "tts",
    "quality",
    "ffmpeg",
    "cover",
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
