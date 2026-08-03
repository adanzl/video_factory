"""E 类可核对事实：占位（待校准后补齐）。

E 类可能的可核对事实（后续校准实现）：
- 挑食顺序：妈妈先训孩子不能挑食 → 孩子再抓现行
- 闭环扣开场原词（不许挑食 → 不能挑食 → 不许挑食）
- 钓鱼开场句指向核心规矩本身
"""

from __future__ import annotations


def collect_fact_issues(story: dict) -> list[str]:
    """观感层事实硬伤收集（待 E 类校准后补齐）。"""
    # E 尚未校准 (quality_ready=False)，保留空实现
    return []


def fact_revision_hint(issue: str) -> str | None:
    """E 类事实修订 hint（待校准后补齐）。"""
    return None
