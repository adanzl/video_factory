"""日常故事 K 类线路（家长看戏）。"""

from app.services.daily_story.story_types.model import (
    STORY_TYPE_KEYWORDS,
    StoryTypeLine,
    compile_layers,
)

LINE_K = StoryTypeLine(
    code="K",
    label="家长看戏",
    keywords=STORY_TYPE_KEYWORDS["K"],
    quality_ready=False,
    body_lines_min=12,
    body_lines_max=20,
    line_format_hint="12–18字，互骂/劝失败/僵持各一句",
    punchline_example="K类家长看戏，姐弟互骂升级，大人劝失败僵持不和好",
    prompt_block="""\
【本次类型：K 家长看戏 — 专属线路】
- 核心：姐弟**互打互骂升级** → 大人**躲/叹/劝失败**
  → **僵持不和好**（禁止 H 式仪式性和好）。
- **不是** H 第三方化解——大人不定责劝成、不拉手和好。
- **不是** A/J——主戏是互骂互打，不是权威一锤或否决压住。
- **不是** F 互呛加码——K 笑点在大人**劝不动/看戏**，不是外部打断熄火。

【三段链（M12+K）】
1 **互骂升级**（5–8 句）：互怼/推搡/哭喊 escalating。
2 **大人劝失败**（2–4 句）：躲/叹气/劝不了/别打了没用。
3 **僵持收场**（2–3 句）：姐弟仍不对付，**不和好**。

【硬约束】
- 妈妈/爸爸台词 1–3 句，宜劝失败或旁观感叹。
- **禁止** H 式拉手/齐声不打了/道歉和好。
""",
    user_closing="""\
收束须僵持不和好；大人劝失败；勿 H 仪式性和好。""",
    body_user_anchor="先写互骂升级，再写大人劝失败，最后僵持收场。",
    opening_system_append="""\
K 类开场：姐弟当场互骂/互打，勿写成 H 调解或 A 立规首句。""",
    opening_user_append="开场到「刚吵起来」，大人劝失败与僵持留正文。",
    theme_user_append="主题宜姐弟互骂、大人劝不动，非第三方和好。",
    retry_soft_close_hint="补大人劝失败+僵持；勿拉手/不打了/和好。",
    escalation_revision_hint="中段须明显互骂升级，劝失败前勿提前和好。",
    closing_revision_hint="收束须僵持不和好；勿 H 劝和，勿 A 破功。",
    layer_patterns=compile_layers(
        (
            ("互骂", r"打|骂|推|吵|互骂|别吵|讨厌|滚"),
            ("升级", r"还打|还骂|更凶|越劝越|哭|吼"),
            ("劝失败", r"躲|叹气|劝不了|管不了|别打了|你们别|看你们"),
            ("僵持", r"不和好|僵持|哼|不理|别理|谁怕谁"),
        ),
    ),
)
