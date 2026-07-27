"""日常故事 B 类线路（提示词片段）。"""

from app.services.daily_story.story_types.model import (
    STORY_TYPE_KEYWORDS,
    StoryTypeLine,
    compile_layers,
)

LINE_B = StoryTypeLine(
    code="B",
    label="结盟翻车",
    keywords=STORY_TYPE_KEYWORDS["B"],
    quality_ready=False,
    punchline_example="B类结盟翻车，姐弟瞒妈计划互相甩锅一起露馅",
    prompt_block="""\
【本次类型：B 结盟翻车 — 专属线路（初版）】
- 公式：姐弟联手瞒妈妈/钻空子→执行中露馅→互相甩锅→一起暴露。
- 主戏仍是姐弟；妈妈可在末段撞见，禁止妈妈长篇讲理。

【节奏】1 结盟约定 → 2 执行走样 → 3 互相甩锅 → 4 露馅收场
""",
    user_closing="""\
9. 【B类收束】末 3–4 句：互相「都怪你」后同时露馅（妈妈撞见或证据落地），
   末句一方嘴硬仍想甩锅。
""",
    layer_patterns=compile_layers(
        [
            ("B1_结盟", r"一起|咱俩|别告诉|瞒|约定|联手|暗号"),
            ("B2_走样", r"怎么|不对|坏了|露馅|看见|听到了"),
            ("B3_甩锅", r"都怪你|是你|你先|不是我|你答应"),
            ("B4_露馅", r"妈妈|完了|糟糕|抓到了|露馅"),
        ],
    ),
    escalation_revision_hint="【B·升级】加一轮执行走样与互相甩锅，别只吵联盟分工。",
    closing_revision_hint="【B·收束】露馅后一方仍嘴硬甩锅，末句破功方说。",
)

