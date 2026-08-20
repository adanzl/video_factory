"""B 站分区 tid。

稿件默认公开（审核通过后开放浏览），不走「仅自己可见」。
"""

from __future__ import annotations

from typing import Any

CHAT_PIPELINE = "chat"
DEFAULT_TID = 201  # 知识 → 科学科普（旧 tid，与 human_type2 配合）
CHAT_TID = 201  # chat 旧 tid 占位；分区展示靠 human_type2
CHAT_HUMAN_TYPE2 = 1025  # 新分区 → 亲子
# 创作声明（mark_list id，勿把 label 塞进 neutral_mark）
CHAT_CONTENT_MARK_ID = 2
CHAT_CONTENT_MARK_LABEL = "含虚构演绎内容"

# 新分区 human_type2（投稿页展示用）
HUMAN_TYPE2_LABELS: dict[int, str] = {
    1025: "亲子",
    2176: "亲子互动",
    1010: "知识",
}

# 旧 tid（无 human_type2 时回退展示）
TID_LABELS: dict[int, str] = {
    201: "科学科普",
    254: "亲子",
}


def resolve_tid(pipeline: str | None, *, settings: Any | None = None) -> int:
    """chat 与默认均用 201 旧 tid；实际分区由 human_type2 决定。"""
    from app.config import get_settings

    cfg = settings or get_settings()
    if (pipeline or "").strip() == CHAT_PIPELINE:
        return int(cfg.bili_tid_chat)
    return int(cfg.bili_tid)


def resolve_human_type2(pipeline: str | None, *, settings: Any | None = None) -> int | None:
    """chat 走新分区亲子（1025）；其余流水线暂不指定。"""
    from app.config import get_settings

    if (pipeline or "").strip() != CHAT_PIPELINE:
        return None
    cfg = settings or get_settings()
    return int(cfg.bili_human_type2_chat)


def resolve_content_mark_id(pipeline: str | None) -> int | None:
    if (pipeline or "").strip() == CHAT_PIPELINE:
        return CHAT_CONTENT_MARK_ID
    return None


def resolve_content_mark_label(pipeline: str | None) -> str | None:
    if (pipeline or "").strip() == CHAT_PIPELINE:
        return CHAT_CONTENT_MARK_LABEL
    return None


def resolve_neutral_mark(pipeline: str | None) -> str | None:
    """展示用创作声明文案（submit 走 mark_id）。"""
    return resolve_content_mark_label(pipeline)


def describe_publish_partition(
    pipeline: str | None,
    *,
    settings: Any | None = None,
) -> dict[str, Any]:
    """返回投稿将使用的分区（展示名 + tid / human_type2）。"""
    tid = resolve_tid(pipeline, settings=settings)
    human_type2 = resolve_human_type2(pipeline, settings=settings)
    if human_type2 is not None:
        label = HUMAN_TYPE2_LABELS.get(human_type2, f"新分区 {human_type2}")
        return {
            "tid": tid,
            "human_type2": human_type2,
            "label": label,
            "display": label,
        }
    label = TID_LABELS.get(tid, f"分区 {tid}")
    return {
        "tid": tid,
        "human_type2": None,
        "label": label,
        "display": label,
    }
