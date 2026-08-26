"""日常故事 G 类线路（嘴硬心软）。"""

from app.services.daily_story.story_types.model import (
    STORY_TYPE_KEYWORDS,
    StoryTypeLine,
    compile_layers,
)

LINE_G = StoryTypeLine(
    code="G",
    label="嘴硬心软",
    keywords=STORY_TYPE_KEYWORDS["G"],
    quality_ready=True,
    body_lines_min=18,
    body_lines_max=24,
    line_format_hint="12–18字，数落/护短/软化各一句信息",
    punchline_example="G类嘴硬心软，互怼中一句护短破防，暖收或嘴硬里带软",
    prompt_block="""\
【本次类型：G 嘴硬心软 — 专属线路】
- 核心：互怼/数落 escalating → **意外真情或护短一句（pivot）**
  → 对方愣住 → **暖收或嘴硬里带软**（收束多样，不锁单一模板）。
- **不是** C 公平执念：不争同一物、不写双规则赛规、末句勿回旋镖戳穿。
- **不是** F 互呛加码：可互损升级，但须**情感拐点 + 软化收束**，勿顶嘴僵持不收。
- pivot **谁说不限定**：姐大弟小/男女/当场强弱，谁身份合适谁来说。
  例：弟护姐、姐骂完自己先软、被数落方突然认怂护对方。

【四段链（顺序固定）】
1 **施压/数落**（3–6 句）：骂丢人、担心、恨铁不成钢等，可 escalating。
2 **pivot**（1–2 句）：护短/护姐/「谁敢动你」/「我怕你…」类**可拍真心**。
3 **愣住 beat**（1–2 句）：「你……你说啥？」/接不住/短沉默感。
4 **收束**（2–4 句，**多样**）：
   - 纯暖：擦药、约定、「那说好了」、相视而笑；
   - 半嘴硬：「撑腰呢！」「哼，小屁孩还管我」——壳硬里已软。
   禁止 C 式「引原话+那不一样+哼」末四拍；禁止 F 式「不跟你玩了」僵持。

【硬约束】
- 主戏姐弟；妈妈宜 0–1 句，非主角。
- pivot 须**可画**，不能只是继续对骂或互呛加码顶牛。
- 收束须体现**关系软化**（动作或语气），勿停在纯对骂。
""",
    user_closing="""\
收束须暖或半暖（擦药/撑腰/说好了/嘴硬里带软均可）；
勿 C 回旋镖末句，勿 F 威胁僵持。""",
    body_user_anchor="先写数落/互损 escalating，再写 pivot 护短或真心一句。",
    opening_system_append="""\
G 类开场：现状+担心/生气（手伤了/又闯祸/丢人），勿写成 C 争物公平战。""",
    opening_user_append="开场到「刚发现/刚骂起来」，pivot 留正文。",
    theme_user_append="主题宜姐弟互怼后情感拐点（护短/嘴硬心软），非抢物赛规。",
    retry_soft_close_hint="补 pivot 后愣住一拍，末段用擦药/撑腰/说好了等暖收。",
    escalation_revision_hint="中段数落须层层加码，pivot 前勿提前软化。",
    closing_revision_hint="收束体现软化；可纯暖可半嘴硬，勿回旋镖戳穿。",
    layer_patterns=compile_layers(
        (
            ("数落", r"丢人|嘴硬|怂|没记性|充|大侠|烦你"),
            ("pivot", r"护|撑腰|拼命|动你|心疼|管你|认真的|我怕"),
            ("愣住", r"你说啥|……|\.\.\.|愣|啥\？"),
            ("暖收", r"擦|药|说好了|行了|过来|撑腰|嗯|相视|笑"),
        ),
    ),
)
