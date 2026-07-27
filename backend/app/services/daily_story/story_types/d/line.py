"""日常故事 D 类线路（提示词片段）。"""

from app.services.daily_story.story_types.model import (
    STORY_TYPE_KEYWORDS,
    StoryTypeLine,
    compile_layers,
)

LINE_D = StoryTypeLine(
    code="D",
    label="字面执行",
    keywords=STORY_TYPE_KEYWORDS["D"],
    quality_ready=False,
    punchline_example="D类字面执行，叮嘱方为补救违反自己立的规矩被回旋镖",
    prompt_block="""\
【本次类型：D 字面执行 — 专属线路（初版）】
- 公式：一方立叮嘱/规矩→另一方按字面严格执行→后果跑偏
  →原叮嘱方为收拾残局被迫违反自己的规矩→执行方用其规则回旋镖收束。
- 关键：不能只写到「搞砸了傻眼」，须叮嘱方自陷矛盾后再被反堵。

【节奏·升级路线（D 专用）】
1 立规矩 → 2 字面执行 → 3 后果跑偏 → 4 叮嘱方违规补救 → 5 回旋镖收束

【收束】执行方用对方原话点破「你自己说的，你现在也破了」；末句叮嘱方嘴硬。
""",
    user_closing="""\
9. 【D类收束模板】末尾 3–4 句：点出叮嘱方为补救而违反自己立的规矩，
   末句叮嘱方（灿灿或妈妈，视谁立的规）嘴硬收场。
""",
    layer_patterns=compile_layers(
        [
            ("D1_立规矩", r"不许|别碰|不能|应该|要|得|规矩|叮嘱|说了"),
            ("D2_字面执行", r"照做|按你说的|你不是说|字面|打开|碰了|动了"),
            ("D3_后果跑偏", r"掉了|滑|洒|乱|坏|打不开|饿着|够不着"),
            ("D4_违规补救", r"我来|我捡|我弄|只好|只能|没办法"),
            ("D5_回旋镖", r"你自己说|你刚才|你现在|你也|不算吗"),
        ],
    ),
    escalation_revision_hint="【D·升级】补一层「字面执行搞砸现场」再让叮嘱方被迫破规。",
    closing_revision_hint="【D·收束】用叮嘱方原话回旋镖，末句叮嘱方嘴硬。",
)

