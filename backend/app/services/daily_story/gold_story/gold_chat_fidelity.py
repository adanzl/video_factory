"""gold_chat 金稿保真：按 structure_type / mechanism 生成扩写 checklist。"""

from __future__ import annotations

from typing import Any

# mechanism + structure 组合的扩写链（顺序不可跳步）
_MECH_STRUCTURE_CHAINS: dict[tuple[str, str], tuple[str, ...]] = {
    ("M5", "H"): (
        "升级：抢看/占物 → 拒看/推搡（object 须可拍）",
        "双向互毁：须写清谁先弄坏谁、谁报复；「也弄坏你的」须有前文",
        "伤情：story_raw 有则可拍一句（蹭破/头破/要涂碘伏）",
        "哭腔道歉：昭昭/弱势方先软",
        "M5 拒和：立规（如谁先动手谁道歉）+ 不原谅",
        "M5 加码：妈妈介入前至少 1 句仍嘴硬（道歉也没用/不原谅）",
        "H 调解①：妈妈问「谁先动手」",
        "H 调解②：定责劝和（分层，勿一句「都错了」了事）",
        "仪式性和好：拉手/勉强松口",
        "齐声承诺：以后还打不打架 → 不打了",
        "收场：story_raw 有碘伏/涂药则写；可选妈妈一句录下来/发圈",
    ),
    ("M5", "A"): (
        "立规/拒和 escalating",
        "加码：嘴硬不原谅",
        "A 末四拍或等价收束（引话/破功）",
    ),
    ("M4", "G"): (
        "互怼/数落 escalating",
        "pivot：护短/真心一句",
        "愣住 beat",
        "暖收或半暖",
    ),
}

_DEFAULT_H_CHAIN: tuple[str, ...] = (
    "冲突升级（4–8 句）",
    "僵持/拒和",
    "妈妈定责劝和（2–4 句）",
    "仪式性和好",
)

_BANNED_INVENTED_CLOSES: tuple[str, ...] = (
    "交换礼物/彩虹/酒窝/拉钩一百年",
    "站内模板暖梗（story_raw 未出现则禁）",
)


def fidelity_chain(
    *,
    structure_type: str,
    mechanism: str,
) -> tuple[str, ...]:
    st = str(structure_type or "").strip().upper()
    mech = str(mechanism or "").strip().upper()
    return _MECH_STRUCTURE_CHAINS.get((mech, st), _DEFAULT_H_CHAIN if st == "H" else ())


def format_story_beats(beat: list[Any] | None) -> str:
    lines: list[str] = []
    for i, item in enumerate(beat or [], start=1):
        text = str(item or "").strip()
        if text:
            lines.append(f"{i}. {text}")
    return "\n".join(lines) if lines else "（无 beat 摘要）"


def format_fidelity_block(
    *,
    structure_type: str,
    mechanism: str,
    beat: list[Any] | None,
    closing_intent: str = "",
    story_raw: str = "",
) -> str:
    """注入 gold_chat prompt：金稿关键拍 checklist。"""
    st = str(structure_type or "").strip().upper()
    mech = str(mechanism or "").strip().upper()
    chain = fidelity_chain(structure_type=st, mechanism=mech)

    parts = [
        "【金稿保真 checklist · 扩写时逐步落实，禁止跳步】",
        *([f"- {step}" for step in chain]),
    ]

    beat_text = format_story_beats(beat)
    parts.extend(
        [
            "",
            "【本稿 story beat 摘要（须在对白中体现）】",
            beat_text,
        ],
    )

    closing = str(closing_intent or "").strip()
    if closing:
        parts.extend(["", f"closing_intent（收束原意，优先于自编剧情）：{closing}"])

    raw = str(story_raw or "").strip()
    if raw:
        parts.extend(
            [
                "",
                "story_raw 对照：只取可拍现场拍，叙述/meta 可改为妈妈一句台词；",
                "勿用 story_raw 未出现的物品/仪式替换收束。",
            ],
        )

    parts.extend(
        [
            "",
            "【禁止 Invent】",
            *[f"- {x}" for x in _BANNED_INVENTED_CLOSES],
        ],
    )
    return "\n".join(parts)
