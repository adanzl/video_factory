"""跨风格共用的口播规则与 JSON 样例。"""

from __future__ import annotations

SEGMENT_LAYER_HINT = (
    "三层每层只用一句短话（各 10～25 字），单段总长须遵守单镜字数上限；"
    "总字数不足时增加 segments 段数，总字数超标时删例子/删并列知识点，禁止把多句堆进同一段。"
)

ANTI_MEMOIR = (
    "【禁止伪亲历体】不得出现：「我当…时」「我在…干活/下井/上班」「老XX教我」"
    "「班长拉着我跑」「我条件反射」「我后来查资料才知道」「评论区聊聊你平时怎么做」"
    "等编造第一人称从业经历或互动话术；"
    "不得扮演矿工、医护、司机等具体职业身份，不得写成暗访/卧底/一线亲历报道；"
    "产业、科技类须客观第三人称科普，用「很多人/业内/数据显示」表述即可。"
)

NO_JSON = (
    "【禁止JSON混入】narration 必须是纯口播文本，禁止出现 JSON 花括号 {}、"
    "禁止出现 {\"text\":...} 等结构化片段；"
    "后端会按标点自动切分分镜，不要在口播里写分镜标签。"
)

MATERIAL_LENGTH_RULE = (
    "【口播字数】每段口播须含三层——"
    "①童趣感叹或「你看」式互动；②一个准确科普点；③比喻/拟声/生活联想。"
    "禁止整段仅一句短感叹（如「哇，好厉害呀」）。"
    f"{SEGMENT_LAYER_HINT}"
    "【生成顺序】先逐段写 segments，再原样拼接为 narration，最后统计 word_count；"
    "不足下限可当场扩写，超过上限须当场删繁就简，禁止先输出再指望后处理。"
    "【输出前自检】逐段核对：每段 text 是否含三层、是否非空、是否未超单镜上限；"
    "各段 text 字数之和是否落在验收区间内（超标与不足均不合格）；"
    "word_count 是否等于 narration 实际字数（不含空格换行）；"
    "narration 与 segments 按序拼接是否完全一致，不一致须重写。"
)

STORYBOARD_JSON_EXAMPLE = """{
  "title": "标题示例",
  "narration": "（各段 text 按序拼接的全文，须达到【字数预算】写作目标）",
  "word_count": 1252,
  "segments": [
    {"segment_index": 1, "text": "（本段口播，须写满该段字数下限，勿照抄此短句）", "visual_brief": "画面主旨", "visual_mode": "static_motion"},
    {"segment_index": 2, "text": "（第二段同样写满预算）", "visual_brief": "画面主旨", "visual_mode": "static_motion"}
  ]
}

注意：样例仅 2 段且 word_count 仅为字段示意；实际段数须 ≥【字数预算】段数下限，word_count 须为 narration 真实字数且 ≥ 写作目标，禁止照抄样例短句长度。"""

NARRATION_ONLY_JSON_EXAMPLE = """{
  "title": "标题示例",
  "narration": "（连贯口播全文，须达到【字数预算】写作目标，用句号自然断句）",
  "word_count": 1282
}

注意：不要输出 segments 字段；word_count 须为 narration 真实字数且 ≥ 写作目标。"""

MATERIAL_SCRIPT_JSON_EXAMPLE = """{
  "title": "标题示例",
  "narration": "（各段 text 按序拼接的全文，须达到【字数预算】写作目标）",
  "segments": [
    {"segment_index": 1, "text": "（本段口播，须写满该段字数下限，用具体细节撑开）"},
    {"segment_index": 2, "text": "（第二段同样写满预算，补比喻或步骤后再接下一段）"}
  ]
}"""
