"""日常故事 H 类线路（第三方化解）。"""

from app.services.daily_story.story_types.model import (
    STORY_TYPE_KEYWORDS,
    StoryTypeLine,
    compile_layers,
)

LINE_H = StoryTypeLine(
    code="H",
    label="第三方化解",
    keywords=STORY_TYPE_KEYWORDS["H"],
    quality_ready=False,
    body_lines_min=16,
    body_lines_max=24,
    line_format_hint="12–18字，升级/定责/和好各一句信息",
    punchline_example="H类第三方化解，僵持后妈妈定责劝和，仪式性和好",
    prompt_block="""\
【本次类型：H 第三方化解 — 专属线路】
- 核心：姐弟冲突 **升级或僵持** → **妈妈（第三方）定责劝和**
  → **仪式性和好**（道歉/拉手/齐声承诺等）。
- **不是** G 嘴硬心软：不靠姐弟内部 pivot/护短破防，靠第三方介入收束。
- **不是** E 妈妈破功：妈妈不当立论主角，只做调解定责。
- **不是** A 权威翻车：勿写末四拍引话/那不一样/破功链。

【四段链（顺序固定；M5+H 见 gold_chat 保真 checklist）】
1 **冲突升级**（4–8 句）：互毁须**双向**（谁先弄坏谁→报复），勿用「抢秘密」替代争物/互毁。
2 **M5 拒和+加码**（2–4 句）：立规+不原谅；妈妈介入前至少 1 句仍嘴硬。
3 **第三方调解**（2–4 句）：妈妈**分层**——先问谁先动手，再定责劝和（勿一句都错了）。
4 **仪式性和好**（2–4 句）：拉手/齐声不打了；story_raw 有碘伏/发圈则收场可写。

【硬约束】
- 妈妈台词 2–4 句；末句宜姐弟。
- **禁止**自编 story_raw 未出现的暖收（彩虹/交换/拉钩等）。
""",
    user_closing="""\
收束须仪式性和好（拉手/齐声承诺/表演性道歉）；
勿 G 内部 pivot，勿 A 末四拍。""",
    body_user_anchor="先写升级/僵持，再写妈妈定责劝和，最后仪式性和好。",
    opening_system_append="""\
H 类开场：姐弟当场冲突（抢/毁/推），勿写成 C 公平赛规首句。""",
    opening_user_append="开场到「刚吵起来/刚互毁」，妈妈调解留正文。",
    theme_user_append="主题宜姐弟冲突升级后第三方调解，非争物回旋镖。",
    retry_soft_close_hint="补妈妈问谁先动手 + 定责劝和，末段齐声不打了/碘伏涂药；勿自编彩虹交换。",
    escalation_revision_hint="中段须明显升级或僵持，调解前勿提前和好。",
    closing_revision_hint="收束须仪式性和好；末句宜姐弟，勿妈妈独白总结。",
    layer_patterns=compile_layers(
        (
            ("升级", r"打|推|抢|弄坏|不原谅|生气|互毁"),
            ("调解", r"别打|和好|道歉|原谅|都错|拉手"),
            ("和好", r"不打了|对不起|没关系|说好了|齐声"),
        ),
    ),
)
