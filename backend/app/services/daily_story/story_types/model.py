"""日常故事矛盾类型（A–H）各自写作线路与观感打分特征。"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass
from typing import Sequence

STORY_TYPE_LABELS: dict[str, str] = {
    "A": "权威翻车",
    "C": "公平执念",
    "D": "字面执行",
    "B": "结盟翻车",
    "E": "妈妈破功",
    "F": "互呛加码",
    "G": "嘴硬心软",
    "H": "第三方化解",
    "I": "问倒收束",
    "J": "权威压住",
    "K": "家长看戏",
    "L": "退让点破",
}

STORY_TYPE_KEYWORDS: dict[str, frozenset[str]] = {
    "A": frozenset(
        {
            "管", "教", "作业", "不许", "应该", "必须", "听我的", "你小", "大人",
            "谁怕", "写错", "管教", "指正", "功课", "练琴", "手机", "规矩",
            "辈分", "姐姐说", "得听", "批评", "顶嘴", "磨蹭",
        },
    ),
    "C": frozenset(
        {
            "争", "抢", "分", "谁先", "最后一", "平分", "归谁", "哪个",
            "大战", "之战", "马桶", "抱枕", "酸奶", "蛋糕", "橡皮",
        },
    ),
    "D": frozenset(
        {"弄", "撒", "碎", "掉了", "帮忙", "收拾", "照做", "叮嘱", "按", "照", "叠", "鞋带"},
    ),
    "B": frozenset(
        {"一起", "偷偷", "瞒", "藏", "约定", "联手", "别告诉", "俩", "暗号", "零食"},
    ),
    "E": frozenset({"妈妈", "问妈", "告状", "跟妈", "叫妈妈", "讲理"}),
    "F": frozenset(
        {
            "再说", "试试", "你敢", "讨厌", "吼", "别吵", "互呛", "加码",
            "不跟你", "不理你", "僵持", "偷拍", "镜头", "尴尬",
        },
    ),
    "G": frozenset(
        {
            "嘴硬", "心软", "护", "护短", "护姐", "撑腰", "数落", "骂",
            "丢人", "破防", "愣", "擦药", "真心", "拼命", "姐弟",
        },
    ),
    "H": frozenset(
        {
            "劝和", "调解", "和好", "拉手", "不打了", "都错", "原谅",
            "道歉", "别打", "妈妈劝", "定责", "互毁", "打架",
        },
    ),
    "I": frozenset(
        {
            "灵魂", "拷问", "你爱吗", "你爱", "相同", "凭什么", "语塞",
            "一招", "问倒", "不爱学习", "标准", "高地",
        },
    ),
    "J": frozenset(
        {
            "说了算", "否决", "权威", "压住", "镇住", "不同意", "不准",
            "听我的", "霸道", "放行", "妈妈同意", "妈妈答应", "绝对",
        },
    ),
    "K": frozenset(
        {
            "看戏", "劝不动", "越劝越", "互骂", "互打", "僵持", "不和好",
            "躲", "叹气", "管不了", "别打了", "劝失败", "大人",
        },
    ),
    "L": frozenset(
        {
            "偏心", "退让", "不想喝", "不想要", "给你", "给他", "给她",
            "公平陷阱", "假公平", "向着", "语塞", "拒收", "让给",
        },
    ),
}

TYPE_CATALOG_LINE = (
    "【矛盾类型一览】A权威翻车 / C公平执念 / D字面执行 / "
    "B结盟翻车 / E妈妈破功 / F互呛加码 / G嘴硬心软 / H第三方化解 / "
    "I问倒收束 / J权威压住 / K家长看戏 / L退让点破；"
    "生成时会锁定其中一种并走该类型专属线路。"
)


@dataclass(frozen=True)
class StoryTypeLine:
    code: str
    label: str
    keywords: frozenset[str]
    prompt_block: str
    user_closing: str
    punchline_example: str
    layer_patterns: tuple[tuple[str, re.Pattern[str]], ...]
    quality_ready: bool
    escalation_revision_hint: str
    closing_revision_hint: str
    body_user_anchor: str = ""
    opening_system_append: str = ""
    opening_user_append: str = ""
    theme_user_append: str = ""
    retry_soft_close_hint: str = ""
    body_lines_min: int = 0
    body_lines_max: int = 0
    # 格式示例里的单句行宽提示（共享模板默认 A 类 ≤18字，各类型可覆盖）
    line_format_hint: str = "≤18字"
    # 格式要求之后的幽默强化块（可选，类型专属；D 类用于拉满好笑分）
    humor_pack: str = ""


def compile_layers(
    pairs: Sequence[tuple[str, str]],
) -> tuple[tuple[str, re.Pattern[str]], ...]:
    return tuple((label, re.compile(pat)) for label, pat in pairs)


def format_story_type_brief(code: str | None) -> str:
    """任务信息栏用：A权威翻车。无效码返回空。"""
    c = str(code or "").strip().upper()[:1]
    label = STORY_TYPE_LABELS.get(c)
    return f"{c}{label}" if label else ""


def chat_type_info_message(code: str | None, *, success: bool = False) -> str | None:
    """chat 任务 error_message：`[A权威翻车]`，成功则追加 SUCCESS。"""
    brief = format_story_type_brief(code)
    if not brief:
        return None
    tag = f"[{brief}]"
    return f"{tag} SUCCESS" if success else tag


