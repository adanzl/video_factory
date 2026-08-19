"""B 站粉丝动态文案。"""

from __future__ import annotations

from app.services.publish.bilibili.tid import CHAT_PIPELINE


def build_fan_dynamic(title: str, *, pipeline: str | None = None) -> str:
    """生成投稿时的粉丝动态文字。"""
    clean = str(title or "").strip()
    if (pipeline or "").strip() == CHAT_PIPELINE:
        if clean:
            return f"{clean}｜姐弟日常小剧场，昭昭灿灿又整活了。"
        return "姐弟日常小剧场更新啦，昭昭灿灿的日常对话。"
    if clean:
        return f"{clean}｜新视频已发布，欢迎收看。"
    return ""
