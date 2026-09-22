"""K 类结构推进四层：K-A 与 K-B 分轨（k_close_mode）。"""

from __future__ import annotations

from typing import Any

from app.services.daily_story.story_types.k.close_mode import (
    K_A_PARENT_FAIL_STALEMATE,
    K_B_CHILD_SELF_RESOLVE,
    k_close_mode_from_story,
)
from app.services.daily_story.story_types.model import compile_layers

# K-A：互骂 → 升级 → 劝失败 → 僵持（与 LINE_K 一致）
K_A_ESCALATION_LAYERS = compile_layers(
    (
        ("互骂", r"打|骂|推|吵|互骂|别吵|讨厌|滚|抢|按|揪|抓|挠"),
        ("升级", r"还打|还骂|更凶|越劝越|哭|吼|还不"),
        ("劝失败", r"躲|叹气|劝不了|管不了|别打了|你们别|看你们|闹吧|我看着"),
        ("僵持", r"不和好|僵持|哼|不理|别理|谁怕谁"),
    ),
)

# K-B：互骂 → 挡回旁观 → 余怒僵持 → 自行恢复（勿要求劝失败）
K_B_ESCALATION_LAYERS = compile_layers(
    (
        ("互骂", r"打|骂|推|吵|互骂|别吵|讨厌|滚|抢|按|揪|抓|挠|踢|砸|枕头|抱枕"),
        (
            "挡回",
            r"不评理|不参与|不掺和|规矩|不能哭|挡回|不介入|"
            r"吃饭|吃我的|别找我|自己看|自己着",
        ),
        (
            "余怒",
            r"不让步|不服|认输|谁怕谁|僵|没完|也不让|偏不|你试试|再闹|恼了|活该",
        ),
        (
            "自行恢复",
            r"吃不吃|还玩|一起玩|一起走|要不要|行啊|要[！。]|冰棍|冰箱|一块儿|抹把脸",
        ),
    ),
)


def k_escalation_layers(story: dict[str, Any] | None) -> tuple[tuple[str, Any], ...]:
    """按 k_close_mode 返回结构分用的推进层 regex。"""
    if not isinstance(story, dict):
        return K_A_ESCALATION_LAYERS
    mode = k_close_mode_from_story(story)
    if mode == K_B_CHILD_SELF_RESOLVE:
        return K_B_ESCALATION_LAYERS
    if mode == K_A_PARENT_FAIL_STALEMATE:
        return K_A_ESCALATION_LAYERS
    return K_A_ESCALATION_LAYERS
