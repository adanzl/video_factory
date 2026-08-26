"""日常故事 F 类线路（互呛加码）。"""

from app.services.daily_story.story_types.model import (
    STORY_TYPE_KEYWORDS,
    StoryTypeLine,
    compile_layers,
)

LINE_F = StoryTypeLine(
    code="F",
    label="互呛加码",
    keywords=STORY_TYPE_KEYWORDS["F"],
    quality_ready=False,
    body_lines_min=18,
    body_lines_max=24,
    line_format_hint="8–14字，互呛/加码各一句，禁空慌",
    punchline_example="F类互呛加码，互顶嘴加码后僵持或外部打断收束",
    prompt_block="""\
【本次类型：F 互呛加码 — 专属线路】
- 核心：互相威胁/互呛 → **加码**（镜像回怼、音量/气势抬升）
  → **僵持/露怯**，或 **外部打断**（旁人/镜头/偷拍须有 seed 依据）。
- **不是** B 结盟翻车：无瞒妈密谋、无走样甩锅露馅链；末段勿「咱俩一伙」表演结盟。
- **不是** G 嘴硬心软：无 pivot 护短/擦药暖收。
- **不是** C 公平执念：不争同一物、不写双规则赛规、末句勿回旋镖戳穿。

【三段链（顺序固定；收束多样）】
1 **互呛/威胁**（3–6 句）：你再说/试试/你敢/还…呢 等可拍互损。
2 **加码**（3–6 句）：镜像回怼、吼叫、气势抬升，至少两轮升级。
3 **收束**（2–4 句，**多样**）：
   - 僵持：不跟你玩/不理你/谁也不让；
   - 露怯：怂了/不敢/算了；
   - 外部打断：发现镜头/旁人 → 尴尬收束或装和睦（须有依据）。
   禁止 B 末段甩锅露馅；禁止 G 暖收；禁止 C/A 末四拍。

【硬约束】
- 主戏姐弟；妈妈宜 0–1 句。
- 中段须**可见升级**，勿车轱辘同一句复读。
""",
    user_closing="""\
收束须僵持/露怯或外部打断；勿 B 甩锅露馅，勿 G 暖收，勿 C/A 标准末四拍。""",
    body_user_anchor="先写互呛威胁，再写两轮加码，最后僵持或外部打断收束。",
    opening_system_append="""\
F 类开场：互呛/生气现状，勿写成 C 争物公平战或 B 密谋分工。""",
    opening_user_append="开场到「刚吵起来/刚顶回去」，加码与收束留正文。",
    theme_user_append="主题宜互呛加码升级，非结盟瞒妈或争物赛规。",
    retry_soft_close_hint="补一轮加码后收束：僵持/露怯，或 seed 有则外部打断尴尬收。",
    escalation_revision_hint="中段须层层加码，收束前勿提前软化或结盟。",
    closing_revision_hint="收束勿 B 甩锅露馅、勿 G 暖收；外部打断后宜尴尬收束。",
    layer_patterns=compile_layers(
        (
            ("互呛", r"讨厌|再说|试试|你敢|哼|别吵"),
            ("加码", r"还.{0,4}呢|吼|啊{2,}|更|再来"),
            ("僵持", r"不跟你|不理你|谁也不|爱咋|算了|怂"),
            ("外部打断", r"拍|镜头|偷拍|闭嘴|尴尬|茄子|闹着玩"),
        ),
    ),
)
