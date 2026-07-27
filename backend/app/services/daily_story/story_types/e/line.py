"""日常故事 E 类线路（提示词片段）。"""

from app.services.daily_story.story_types.model import (
    STORY_TYPE_KEYWORDS,
    StoryTypeLine,
    compile_layers,
)

LINE_E = StoryTypeLine(
    code="E",
    label="妈妈破功",
    keywords=STORY_TYPE_KEYWORDS["E"],
    quality_ready=False,
    punchline_example="E类妈妈破功，妈妈讲理被孩子字面追问绕进去",
    prompt_block="""\
【本次类型：E 妈妈破功 — 专属线路（初版）】
- 公式：妈妈想讲道理/立规矩→孩子字面追问或连环反例→妈妈自己先破功。
- 妈妈台词可略多（建议≤5句），但笑点须在妈妈逻辑自相矛盾。

【节奏】1 妈妈立论 → 2 孩子追问 → 3 妈妈改口 → 4 孩子闭环 → 5 妈妈破功
""",
    user_closing="""\
9. 【E类收束】末 3–4 句：孩子用妈妈刚说的话反问，末句妈妈破功（……唉/……行行行）。
""",
    layer_patterns=compile_layers(
        [
            ("E1_妈妈立论", r"妈妈|应该|必须|规矩|听我的|我说"),
            ("E2_孩子追问", r"为什么|凭什么|那你|你也|上次"),
            ("E3_妈妈改口", r"不是|不一样|那是|总之|反正"),
            ("E4_闭环", r"你自己说|你刚才|那你也是"),
            ("E5_妈妈破功", r"唉|行了|好吧|随便|说不通"),
        ],
    ),
    escalation_revision_hint="【E·升级】加连环追问，逼妈妈改口一次。",
    closing_revision_hint="【E·收束】孩子闭环反问，末句妈妈破功。",
)
