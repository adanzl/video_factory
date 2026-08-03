"""D 类可核对事实：占位（D1.5 story_plan 覆盖事实与骨架）。

D 类的定量约束（规矩词、歪读点、必然后果）落在
`punchline_blueprint`，由 D1.5 笑点骨架统一校验，
因此本模块保持空实现。
"""

from __future__ import annotations


def collect_fact_issues(story: dict) -> list[str]:
    """观感层事实硬伤收集（当前由 D1.5 骨架覆盖）。"""
    # D 已调通，事实线走 story_plan / punchline_blueprint
    return []


def fact_revision_hint(issue: str) -> str | None:
    """D 类事实修订 hint（D1.5 重试已覆盖）。"""
    return None
