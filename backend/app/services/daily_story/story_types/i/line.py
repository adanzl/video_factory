"""日常故事 I 类线路（问倒收束）。"""

from app.services.daily_story.story_types.model import (
    STORY_TYPE_KEYWORDS,
    StoryTypeLine,
    compile_layers,
)

LINE_I = StoryTypeLine(
    code="I",
    label="问倒收束",
    keywords=STORY_TYPE_KEYWORDS["I"],
    quality_ready=False,
    body_lines_min=10,
    body_lines_max=18,
    line_format_hint="12–18字，争锋/拷问/语塞/一招制敌各一句",
    punchline_example="I类问倒收束，灵魂拷问问倒对方，赢家一招制敌收场",
    prompt_block="""\
【本次类型：I 问倒收束 — 专属线路】
- 核心：争锋/互怼 → 立价值标准/道德高地 → **灵魂拷问**（不可答问题）
  → 对方**语塞** → **赢家嘴硬总结**（一招制敌）。
- **不是** A 权威翻车：立规者全程占上风，**无反噬/破功**。
- **不是** C 公平执念：赢点不是回旋镖互戳，是**问倒**。
- **不是** G 嘴硬心软：无真情 pivot，收束是赢家嘴硬总结。

【五段链（顺序固定；M11+I 见 gold_chat 保真 checklist）】
1 **争锋**（2–4 句）：可含双规则拉扯/转移话题。
2 **价值高地**（1–2 句）：须可拍一句（如「我爱学习你爱吗」）。
3 **灵魂拷问**（1–2 句）：抛出不可答/不可接问题。
4 **语塞**（1–2 句）：对方败北（哑口/说不过/看窗外）。
5 **一招制敌**（1–2 句）：赢家嘴硬总结，**无 A 式破功**。

【硬约束】
- 妈妈宜旁观不出声（mom_lines_max=0 金稿常见）。
- **禁止**末四拍 A 式引话/那不一样/破功链。
""",
    user_closing="""\
收束须赢家一招制敌（嘴硬总结）；对方语塞后勿 A 式反噬/破功。""",
    body_user_anchor="先写争锋与价值高地，再灵魂拷问问倒，最后赢家一招制敌。",
    opening_system_append="""\
I 类开场：可直接灵魂拷问或争锋起句，勿写成 C 公平赛规首句。""",
    opening_user_append="开场到「刚吵起来/刚抛出拷问」，语塞与一招制敌留正文。",
    theme_user_append="主题宜灵魂拷问/价值高地问倒，非争物回旋镖。",
    retry_soft_close_hint="补灵魂拷问+语塞，末段赢家一招制敌；勿 A 破功/C 回旋镖。",
    escalation_revision_hint="中段须明显价值高地+灵魂拷问，语塞前勿提前一招制敌。",
    closing_revision_hint="收束须赢家一招制敌；勿 A 破功，勿 C 嘴硬被戳穿。",
    layer_patterns=compile_layers(
        (
            ("争锋", r"讲道理|别跟|凭啥|转移|更爱你|一个爸妈|吵"),
            ("价值高地", r"爱学习|公平|标准|应该|规矩|双标|相同"),
            ("灵魂拷问", r"你爱吗|你爱|灵魂|拷问|为啥|凭什么|咋不"),
            ("语塞", r"说不过|语塞|哑口|不说了|看窗外|服了|张了张嘴"),
            ("一招制敌", r"一招制敌|制敌|服不服|别跟我吵|不爱学习还|看你还说|还说啥|嘴硬"),
        ),
    ),
)
