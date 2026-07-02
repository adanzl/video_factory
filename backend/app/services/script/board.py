"""口播分镜（board）、素材口播、扩写缩字等提示词构建。"""

from __future__ import annotations

import json
import re
from typing import Any

from app.config import get_settings
from app.utils.job_info import (
    CONTENT_STYLE_HISTORICAL_MYSTERY,
    CONTENT_STYLE_LIFE_EXPERIENCE,
    CONTENT_STYLE_SCIENCE_CHILD,
    ORIENTATION_LANDSCAPE,
    ORIENTATION_PORTRAIT,
    content_style_from_job,
    orientation_for_resolve,
)
from app.utils.media import (
    NARRATION_WRITING_TARGET_RATIO,
    default_narration_target_words,
    effective_segment_narration_sec,
    min_narration_chars_for_target,
    narration_accept_min_chars,
    narration_accept_max_chars,
    narration_word_range,
    narration_writing_plan,
    narration_writing_target_chars,
    segment_comfort_chars,
    segment_text_char_cap,
    segment_text_hard_cap,
)
from app.quality.image_prompt import (
    MIN_SD15_PROMPT_EN_WORDS,
    TARGET_SD15_PROMPT_EN_WORDS,
    format_image_prompt_retry_warning,
    image_prompt_min_chars,
    image_prompt_target_chars,
    sd15_prompt_en_ok,
    sd15_prompt_en_word_count,
)
from app.services.script.board_timeline import (
    VideoTimeline,
    append_timeline_to_user,
    narration_range_for_timeline,
    parse_video_timeline,
    timeline_system_clause,
)

# DeepSeek JSON Output 要求 prompt 含 json 字样并给出样例：
# https://api-docs.deepseek.com/zh-cn/guides/json_mode
_STORYBOARD_JSON_EXAMPLE = """{
  "title": "标题示例",
  "narration": "（各段 text 按序拼接的全文，须达到【字数预算】写作目标）",
  "word_count": 1252,
  "visual_style": "画风定调一句话",
  "segments": [
    {"segment_index": 1, "text": "（本段口播，须写满该段字数下限，勿照抄此短句）", "visual_brief": "画面主旨", "visual_mode": "static_motion"},
    {"segment_index": 2, "text": "（第二段同样写满预算）", "visual_brief": "画面主旨", "visual_mode": "static_motion"}
  ]
}

注意：样例仅 2 段且 word_count 仅为字段示意；实际段数须 ≥【字数预算】段数下限，word_count 须为 narration 真实字数且 ≥ 写作目标，禁止照抄样例短句长度。"""

_STORYBOARD_JSON_EXAMPLE_COMPACT = """{
  "title": "标题示例",
  "visual_style": "画风定调一句话",
  "segments": [
    {"segment_index": 1, "text": "（本段口播，须写满该段字数下限）", "visual_brief": "画面主旨", "visual_mode": "static_motion"},
    {"segment_index": 2, "text": "（第二段同样写满预算）", "visual_brief": "画面主旨", "visual_mode": "static_motion"}
  ]
}

注意：样例仅 2 段示意字段结构；实际段数须 ≥【字数预算】段数下限，各段 text 须写满，禁止照抄样例短句。"""

_NARRATION_ONLY_JSON_EXAMPLE = """{
  "title": "标题示例",
  "narration": "（连贯口播全文，须达到【字数预算】写作目标，用句号自然断句）",
  "word_count": 1282,
  "visual_style": "画风定调一句话（画风+主色调+跨镜统一元素）"
}

注意：不要输出 segments 字段；word_count 须为 narration 真实字数且 ≥ 写作目标。"""

_VISUAL_BRIEF_JSON_EXAMPLE = """{
  "visual_style": "画风定调一句话（可与输入一致或微调）",
  "segments": [
    {"segment_index": 1, "visual_brief": "画面主旨与关键视觉（80-150字）（写实场景）", "visual_mode": "static_motion"},
    {"segment_index": 2, "visual_brief": "画面主旨（结构示意图）", "visual_mode": "static_motion"}
  ]
}

注意：segments 须覆盖输入的每一段，segment_index 一一对应；不要修改各段 text。"""

_IMAGE_PROMPT_JSON_EXAMPLE_TEXT = (
    "古老的青铜丹炉占据画面左侧，炉内青绿色火焰与绿烟向上弥漫，炉壁锈迹与烟熏清晰；"
    "前景散落赤色丹药与药渣，背景昏暗炼丹房内木质药柜虚化。"
    "清宫写实风格，暗调青灰主色，炉口底光为主、侧面炭火余烬为辅。"
    "极近景特写，丹炉占左侧三分之二，右侧丹药清晰，略低角度。"
    "金属、火焰与烟雾质感真实，细节层次清楚。"
)

_IMAGE_PROMPTS_JSON_EXAMPLE = """{
  "image_prompts": [
    {
      "segment_index": 1,
      "image_prompt": \"""" + _IMAGE_PROMPT_JSON_EXAMPLE_TEXT + """\",
      "motion_prompt": "轻微镜头推进",
      "sd15_prompt_en": "cross-section diagram of lung alveoli, air sacs highlighted, medical illustration"
    }
  ]
}"""

_IMAGE_PROMPTS_JSON_EXAMPLE_NO_SD15 = """{
  "image_prompts": [
    {
      "segment_index": 1,
      "image_prompt": \"""" + _IMAGE_PROMPT_JSON_EXAMPLE_TEXT + """\",
      "motion_prompt": "轻微镜头推进"
    }
  ]
}"""

_MATERIAL_SCRIPT_JSON_EXAMPLE = """{
  "title": "标题示例",
  "narration": "（各段 text 按序拼接的全文，须达到【字数预算】写作目标）",
  "word_count": 800,
  "segments": [
    {"segment_index": 1, "text": "（本段口播，须写满该段字数下限，用具体细节撑开）"},
    {"segment_index": 2, "text": "（第二段同样写满预算，补比喻或步骤后再接下一段）"}
  ]
}"""


def _json_output_clause(example: str) -> str:
    return (
        "请仅输出合法 JSON 对象（不要 markdown 代码块，不要解释文字）。"
        "JSON 输出样例（字段名须一致，内容为示意）：\n"
        f"{example}\n"
    )

_VISUAL_BRIEF_RULE = (
    "各段含segment_index,text,visual_brief,visual_mode=static_motion；"
    "各段text按顺序拼接须与narration全文一致。"
    "visual_brief为该镜画面描述（80-150字）：写清视觉主旨、关键动作或对比关系、"
    "场景类型与情绪，帮助后续扩写文生图提示词；不写镜头焦距、光线方向、材质参数等细节。"
    "visual_brief末尾须用括号标注SD15画面类型（五选一）："
    "（写实场景）/（结构示意图）/（对比图）/（线稿解剖图）/（微观分子图）。"
    "另须输出visual_style：全片画风定调一句话（画风+主色调+跨镜统一元素如道具造型）。"
)

_IMAGE_PROMPT_QUALITY_RULE = (
    "⑥质量要求：写可见的材质、纹理、光影过渡与层次是否清楚，画面信息是否充实（如「高视觉密度」「细节层次清楚」）；"
    "禁止写4K/8K/分辨率/像素/超高清等规格套话（出图尺寸由系统控制）；"
    "「电影级写实」仅可在③风格维使用，勿在⑥重复堆砌；"
    "禁止空话凑字数（如「极致细节」「大师之作」）。"
)

_IMAGE_PROMPT_FORMAT_RULE = (
    "输出为一段连贯中文，不要用「主体：」「场景/环境：」等维度标签；"
    "六维按自然语序融入，围绕一个视觉焦点展开。"
)

_IMAGE_PROMPT_DIMENSIONS_FULL = (
    "篇幅按画面复杂度充分展开（目标约180字，至少150字），不凑字数。"
    + _IMAGE_PROMPT_FORMAT_RULE
    + "须逐层写清可见细节，禁止空泛形容词："
    + "①主体（主要主体、姿态、关键动作或互动）；"
    + "②场景/环境（前景/中景/背景、空间纵深）；"
    + "③视觉风格（严格遵循 visual_style 全片定调）；"
    + "④光照（主光与辅光方向、明暗氛围）；"
    + "⑤构图（景别、主体位置与占比、相机角度、留白）；"
    + _IMAGE_PROMPT_QUALITY_RULE
    + "另遵守语义边界：仅表达本段 text 与 visual_brief，禁止提前画后续段落内容。"
)

_IMAGE_PROMPT_DIMENSIONS_COMPACT = (
    "篇幅精简、能说明白即可，但须逐点覆盖六维："
    + "①主体；②场景/环境；③视觉风格；④光照；⑤构图；⑥质量要求；"
    + _IMAGE_PROMPT_FORMAT_RULE
    + _IMAGE_PROMPT_QUALITY_RULE
    + "并遵守语义边界（仅本段内容）。"
    + "实际 SD1.5 出图以 sd15_prompt_en 为准。"
    + "image_prompt 和 sd15_prompt_en 都必须使用中文和英文分别写，禁止 image_prompt 出现英文。"
)

_IMAGE_PROMPT_RULE_SCIENCE_PORTRAIT = (
    "image_prompt须严格遵循visual_style画风定调，全片统一：电影级写实科普视觉，布光考究、"
    "景深自然、材质细节真实可辨，色彩明快有层次，适配9:16竖屏构图。"
    + _IMAGE_PROMPT_DIMENSIONS_FULL
)

_IMAGE_PROMPT_RULE_LIFE_LANDSCAPE = (
    "image_prompt须严格遵循visual_style画风定调，全片统一：生活Vlog质感写实画面，"
    "自然光或室内暖光、浅景深、色彩真实不过度滤镜，适配16:9横屏构图。"
    + _IMAGE_PROMPT_DIMENSIONS_FULL.replace(
        "禁止提前画后续段落内容。",
        "禁止可读大段文字/水印/品牌Logo。",
    )
)

_IMAGE_PROMPT_MOTION_TAIL = (
    "围绕一个视觉焦点展开，避免要素平铺罗列。"
    "每段motion_prompt须30-80字，描述画面如何运动；优先「镜头固定」或「极轻微缓慢推进/拉远」，"
    "禁止快速运镜、跟拍、环绕、甩镜等易产生抖动的描述。"
    "若无明显运动，写「镜头固定，主体稳定，画面平滑」。"
)


_IMAGE_PROMPT_RULE_SD15 = _IMAGE_PROMPT_DIMENSIONS_COMPACT

_IMAGE_PROMPT_RULE_MYSTERY_PORTRAIT = (
    "每段image_prompt须严格遵循visual_style画风定调，全片统一：电影级写实历史再现，"
    "光影考究、暗部有层次、低饱和古风色调，适配9:16竖屏构图。"
    + _IMAGE_PROMPT_DIMENSIONS_FULL.replace(
        "禁止提前画后续段落内容。",
        "禁止可读文字、奏折、诏书等文字元素。",
    )
)

_IMAGE_PROMPT_RULE_MYSTERY_LANDSCAPE = _IMAGE_PROMPT_RULE_MYSTERY_PORTRAIT.replace(
    "适配9:16竖屏构图", "适配16:9横屏构图"
)


def _image_prompt_rule(*, orientation: str, content_style: str, sd15_mode: bool = False) -> str:
    head = (
        "根据每段口播text、visual_brief与全片visual_style，扩写为文生图用的image_prompt"
        "和video用的motion_prompt。"
    )
    if sd15_mode:
        return head + _IMAGE_PROMPT_RULE_SD15 + _IMAGE_PROMPT_MOTION_TAIL
    if content_style == CONTENT_STYLE_HISTORICAL_MYSTERY:
        body = _IMAGE_PROMPT_RULE_MYSTERY_LANDSCAPE if orientation == ORIENTATION_LANDSCAPE else _IMAGE_PROMPT_RULE_MYSTERY_PORTRAIT
        return head + body + _IMAGE_PROMPT_MOTION_TAIL
    if content_style == CONTENT_STYLE_LIFE_EXPERIENCE:
        body = _IMAGE_PROMPT_RULE_LIFE_LANDSCAPE
    elif orientation == ORIENTATION_LANDSCAPE:
        body = _IMAGE_PROMPT_RULE_LIFE_LANDSCAPE.replace(
            "生活Vlog质感写实画面",
            "电影级写实视觉",
        )
    else:
        body = _IMAGE_PROMPT_RULE_SCIENCE_PORTRAIT
    return head + body + _IMAGE_PROMPT_MOTION_TAIL


_STEP_LABELS = {
    "storyboard": "口播分镜",
    "narration": "口播文案",
    "visual_brief": "分镜画面概述",
    "image_prompts": "文生图提示词",
    "material_script": "口播文案",
    "title_optimize": "标题优化",
    "video_description": "视频介绍",
}

_NARRATION_VOICE_RULE = (
    "口播口吻须像一个小孩子在讲给同伴听：略带稚嫩、天真，有一点童趣；"
    "可用「哇」「你看」「原来是这样呀」等儿童感感叹，句子偏短、好懂；"
    "偶尔用拟声词或简单比喻（像积木、像气球那样），但不要装婴儿语、不要刻意错别字；"
    "科普事实须准确，童趣服务于理解，不牺牲科学内容。"
)

_TECH_SCIENCE_VOICE_RULE = (
    "口播口吻须像B站硬核科技UP主：客观、冷静、信息密度高；"
    "优先用「你可能不知道」「很多人以为…但…」「关键在这个数据…」等分析式表达；"
    "句子偏简洁，每句都有信息量，不废话不卖萌；"
    "技术概念须准确，用比喻简化但不失真。"
)

_SEGMENT_LAYER_HINT = (
    "三层每层只用一句短话（各 10～25 字），单段总长须遵守单镜字数上限；"
    "总字数不足时增加 segments 段数，总字数超标时删例子/删并列知识点，禁止把多句堆进同一段。"
)

_MATERIAL_NARRATION_LENGTH_RULE = (
    "【口播字数】每段口播须含三层——"
    "①童趣感叹或「你看」式互动；②一个准确科普点；③比喻/拟声/生活联想。"
    "禁止整段仅一句短感叹（如「哇，好厉害呀」）。"
    f"{_SEGMENT_LAYER_HINT}"
    "【生成顺序】先逐段写 segments，再原样拼接为 narration，最后统计 word_count；"
    "不足下限可当场扩写，超过上限须当场删繁就简，禁止先输出再指望后处理。"
    "【输出前自检】逐段核对：每段 text 是否含三层、是否非空、是否未超单镜上限；"
    "各段 text 字数之和是否落在验收区间内（超标与不足均不合格）；"
    "word_count 是否等于 narration 实际字数（不含空格换行）；"
    "narration 与 segments 按序拼接是否完全一致，不一致须重写。"
)

_MYSTERY_NARRATION_VOICE_RULE = (
    "口播口吻须沉稳、有磁性，像一个深夜讲述历史秘闻的说书人。"
    "语速偏慢，句与句之间有空气感。"
    "开头几句要有钩子感，能立刻抓住注意力。"
    "中间不时抛出反问——「但真的这么简单吗？」「那他为什么要这么做？」——引导观众跟着思考。"
    "语气克制，不煽情不夸张，用陈述事实的方式讲悬疑感。"
)

_MYSTERY_NARRATION_LENGTH_RULE = (
    "【口播字数】每段口播须含三层——"
    "①一个历史事实或背景细节；②一个「但」字转折（矛盾/疑点/反常）；③一个反问或悬念收尾。"
    "禁止整段仅一句概括。"
    f"{_SEGMENT_LAYER_HINT}"
    "【生成顺序】先逐段写 segments，再原样拼接为 narration，最后统计 word_count；"
    "不足下限可当场扩写，超过上限须当场删繁就简，禁止先输出再指望后处理。"
)

_MYSTERY_STRUCTURE_RULE = (
    "【结构规范】须依次包含以下五部分：\n"
    "1. 开场钩子（一段话抓住好奇心，直接抛出核心谜案）\n"
    "2. 背景铺陈（人物关系、时间线、历史背景）\n"
    "3. 谜案核心（关键细节、冲突点、反常之处）\n"
    "4. 推理与分析（多角度列举各种可能，每段分析一个方向）\n"
    "5. 收束与悬停（用一段话总结谜案的矛盾之处，然后留一句让观众去琢磨的话收尾，禁止以问句突然结束）\n"
    "禁止用倒叙手法。讲完一个完整故事，最后必须有一段收束语，不能戛然而止。"
)

_LIFE_NARRATION_VOICE_RULE = (
    "口播口吻须像B站生活避坑/经验科普讲解：客观、口语化、像在帮观众纠错；"
    "优先用「很多人以为…其实…」「正确做法是…」「常见误区是…」；"
    "禁止整篇伪装成某一职业的亲历者（矿工、医生、司机等），禁止编造「我当时在一线」类故事。"
)

_LIFE_NARRATION_LENGTH_RULE = (
    "【口播字数】每段口播须含三层——"
    "①常见误区或错误做法；②原因/风险（为什么错）；③正确步骤或可操作结论。"
    "禁止整段仅一句空泛感叹；禁止用长篇第一人称回忆录凑字数。"
    f"{_SEGMENT_LAYER_HINT}"
    "【生成顺序】先逐段写 segments，再原样拼接为 narration，最后统计 word_count；"
    "不足下限可当场扩写，超过上限须当场删繁就简，禁止先输出再指望后处理。"
)

_LIFE_EXPERIENCE_STRUCTURE_RULE = (
    "本片为生活避坑/经验科普：只围绕一个明确主题（避坑/流程/工具/选择），"
    "禁止多点罗列成「十条技巧」清单，禁止抖音式伪亲历回忆录。"
    "开头30秒内点明「大家常踩的坑是什么、这条视频纠正什么误区」，"
    "禁止「我当XX时」「跟班长在XX干活」等编造一线故事开场。"
    "正文按「误区→为什么错→正确做法→注意事项」展开；"
    "举例最多1句泛化案例（如「有人曾…差点…」），不得通篇第一人称扮演从业者。"
    "结尾给1条可行动建议 + 轻量互动，禁止「我一生都忘不了」类煽情收束。"
)

# 全风格口播禁用：伪亲历/职业角色扮演（生活区误区视频高发）
_NARRATION_ANTI_MEMOIR_RULE = (
    "【禁止伪亲历体】不得出现：「我当…时」「我在…干活/下井/上班」「老XX教我」"
    "「班长拉着我跑」「我条件反射」「我后来查资料才知道」「评论区聊聊你平时怎么做」"
    "等编造第一人称从业经历或互动话术；"
    "不得扮演矿工、医护、司机等具体职业身份，不得写成暗访/卧底/一线亲历报道；"
    "产业、科技类须客观第三人称科普，用「很多人/业内/数据显示」表述即可。"
)

_NARRATION_ANTI_REPETITION_RULE = (
    "【禁止复读】同一比喻/类比、同一组数字对比、同一操作步骤全文只讲一次；"
    "相邻两段不得复述刚讲过的句子或意象；"
    "「你看」全文最多 3～4 次，禁止连续两段都以「你看」起句；"
    "段数多时后段换用「其实呀」「关键是」「想一想」等不同引子，"
    "禁止每段机械套用相同三层模板。"
)

_SCIENCE_STRUCTURE_RULE = (
    "【结构规范】须依次包含以下四部分：\n"
    "1. 开场钩子（3 秒内抛出反常识现象或「咦，这是怎么回事呀？」式疑问，禁止「大家好」开场）\n"
    "2. 背景铺垫（是什么、在哪里、和我们有什么关系，用孩子能懂的话讲清）\n"
    "3. 机制拆解（核心原理、因果链条、关键对比或简单实验，只讲一层不贪多）\n"
    "4. 收束与回味（一句童趣总结，可留轻量思考，禁止清单式连读多知识点）\n"
    "长稿须在同一主题下加深细节与比喻，禁止为凑时长新增并列知识点或换题；"
    "段数多时每段只推进一小步，不要每段开一个全新话题；"
    "禁止用不同措辞重复讲同一机制（如电波与地震波速度对比只讲一次）。"
    "禁止倒叙；讲完一个完整因果，最后一句可轻量引导互动。"
)


def _format_segment_target_sec(target: float) -> str | float:
    return int(target) if target == int(target) else target


def _resolve_script_profile(
    job: dict | None,
    *,
    orientation: str | None = None,
    content_style: str | None = None,
) -> tuple[str, str]:
    resolved_orientation = orientation or (
        orientation_for_resolve(job) if job else None
    ) or ORIENTATION_PORTRAIT
    resolved_style = content_style or (
        content_style_from_job(job) if job else CONTENT_STYLE_SCIENCE_CHILD
    )
    return resolved_orientation, resolved_style


def _narration_voice_rule(content_style: str) -> str:
    if content_style == CONTENT_STYLE_LIFE_EXPERIENCE:
        return _LIFE_NARRATION_VOICE_RULE
    if content_style == CONTENT_STYLE_HISTORICAL_MYSTERY:
        return _MYSTERY_NARRATION_VOICE_RULE
    return _NARRATION_VOICE_RULE


def _narration_length_rule(content_style: str) -> str:
    if content_style == CONTENT_STYLE_LIFE_EXPERIENCE:
        return _LIFE_NARRATION_LENGTH_RULE
    if content_style == CONTENT_STYLE_HISTORICAL_MYSTERY:
        return _MYSTERY_NARRATION_LENGTH_RULE
    return _MATERIAL_NARRATION_LENGTH_RULE


def _structure_rule(*, orientation: str, content_style: str) -> str:
    if content_style == CONTENT_STYLE_LIFE_EXPERIENCE:
        return _LIFE_EXPERIENCE_STRUCTURE_RULE
    if content_style == CONTENT_STYLE_HISTORICAL_MYSTERY:
        return _MYSTERY_STRUCTURE_RULE
    return _SCIENCE_STRUCTURE_RULE


def _storyboard_role(content_style: str) -> str:
    if content_style == CONTENT_STYLE_LIFE_EXPERIENCE:
        return "你是B站生活避坑/经验科普的内容编剧。"
    if content_style == CONTENT_STYLE_HISTORICAL_MYSTERY:
        return "你是B站历史悬案视频的编剧兼讲述者，擅长把历史谜案用悬疑节奏讲出来。"
    return "你是给小朋友讲科普的视频编剧。"


def _narration_word_range(target: int) -> tuple[int, int]:
    """口播字数区间：下限与验收阈值一致，上限为目标 + 余量。"""
    return narration_word_range(target)


def _writing_target_clause(narration_target: int) -> str:
    writing_target = narration_writing_target_chars(narration_target)
    lo, hi = narration_word_range(narration_target)
    pct = int(NARRATION_WRITING_TARGET_RATIO * 100)
    return (
        f"写作目标约 {writing_target} 字（总目标 {narration_target} 字的 {pct}%），"
        f"验收硬区间 {lo}-{hi} 字：低于下限可补细节，超过上限须删繁就简，超标与不足均作废"
    )


def _visual_brief_types(profile_style: str) -> str:
    if profile_style == CONTENT_STYLE_HISTORICAL_MYSTERY:
        return "（历史场景再现）/（人物肖像）/（关键物件特写）/（空间环境）"
    return "（写实场景）/（结构示意图）/（对比图）/（线稿解剖图）/（微观分子图）"


def _storyboard_layer_style(content_style: str) -> str:
    if content_style == CONTENT_STYLE_LIFE_EXPERIENCE:
        return "误区+原因+正确做法"
    if content_style == CONTENT_STYLE_HISTORICAL_MYSTERY:
        return "事实+转折+反问"
    return "感叹+科普点+比喻/拟声"


def _storyboard_execution_headline(
    *,
    narration_target: int,
    segment_target_sec: float,
    content_style: str,
) -> str:
    """user 首行：用具体数字强调一次写满，避免模型照抄 JSON 短样例。"""
    plan = narration_writing_plan(narration_target, segment_target_sec)
    writing_target = plan["writing_target"]
    hard_min = plan["hard_min"]
    hard_max = narration_accept_max_chars(narration_target)
    seg_count = plan["seg_count_min"]
    per_min = plan["per_seg_min"]
    per_lo = plan["per_seg_lo"]
    per_hi = plan["per_seg_hi"]
    layers = _storyboard_layer_style(content_style)
    seg_floor = seg_count * per_min
    if segment_target_sec > 0:
        cap = plan["segment_cap"]
        hard_cap = segment_text_hard_cap(segment_target_sec)
        sec = _format_segment_target_sec(effective_segment_narration_sec(segment_target_sec))
        return (
            f"【总字数·硬上限】须在 {hard_min}-{hard_max} 字之间（写作目标约 {writing_target} 字），"
            f"超过 {hard_max} 字整稿作废，优先删例子/删并列知识点，禁止加长单段。"
            f"【单段上限·优先】单镜 {sec}s，每段 text 目标 ≤ {per_hi} 字、绝对不得超过 {cap} 字"
            f"（硬上限 {hard_cap} 字，超限整稿无效）。"
            f"「{layers}」三层各一句短话，禁止把多句堆进同一段；超长须拆段。"
            f"至少 {seg_count} 段；每段建议 {per_lo}-{per_hi} 字。"
            "总字数不足时增加 segments 段数，总字数超标时删内容而非堆段。"
            f"（{seg_count}×{per_min}={seg_floor} 字仅为段数底限，总字数须落在 {hard_min}-{hard_max} 字区间内）。"
            "输出前逐段统计 text 字数并核对总和，任一单段超限或总和超标须重写后再提交。"
        )
    return (
        f"【首要任务】口播总字数须落在 {hard_min}-{hard_max} 字硬区间内（写作目标约 {writing_target} 字），"
        f"超过 {hard_max} 字整稿作废。"
        f"至少 {seg_count} 段 segments，每段 text 建议 {per_lo}-{per_hi} 字、单段下限 {per_min} 字"
        f"（{seg_count}×{per_min}={seg_floor} 字仅为段数底限，总字数须落在 {hard_min}-{hard_max} 字区间内）。"
        f"每段用「{layers}」三层写法，每层一句短话。"
        "常见失误：只写 3～4 段短句导致总字数不足；或堆叠并列知识点导致总字数超标。"
        "不足可扩写细节，超标须删繁就简，禁止照抄 JSON 样例短句。"
    )


def _storyboard_length_budget(
    *,
    narration_target: int,
    segment_target_sec: float,
    content_style: str,
) -> str:
    plan = narration_writing_plan(narration_target, segment_target_sec)
    hard_min = plan["hard_min"]
    writing_target = plan["writing_target"]
    hard_max = narration_accept_max_chars(narration_target)
    per_min = plan["per_seg_min"]
    seg_count_min = plan["seg_count_min"]
    pct = int(NARRATION_WRITING_TARGET_RATIO * 100)
    layers = _storyboard_layer_style(content_style)
    cap_clause = ""
    if segment_target_sec > 0:
        cap = plan["segment_cap"]
        hard_cap = segment_text_hard_cap(segment_target_sec)
        cap_clause = (
            f"②逐段 text ≤ {cap} 字（硬上限 {hard_cap} 字，任一超限须拆段）；"
        )
    else:
        cap_clause = "②逐段统计 text 字数，任一超过单段上限须拆段；"
    self_check = (
        "【输出前硬性自检，任一项不满足须当场重写后再输出 JSON】"
        f"①segments 数量 ≥ {seg_count_min}；"
        f"{cap_clause}"
        f"③各段 text 字数之和在 {hard_min}-{hard_max} 字之间（目标约 {writing_target} 字，"
        f"超过 {hard_max} 字须删内容后重写）；"
        "④word_count 等于 narration 实际字数；"
        "⑤narration 与 segments 按序拼接完全一致；"
        "⑥口播无伪亲历/第一人称从业叙事。"
    )
    if segment_target_sec <= 0:
        return (
            f"【字数预算】总目标 {narration_target} 字；"
            f"写作目标约 {writing_target} 字（总目标 {narration_target} 字的 {pct}%）；"
            f"验收区间 {hard_min}-{hard_max} 字（超出即不合格）。\n"
            f"每段至少 {per_min} 字，段数由口播内容逻辑决定；"
            f"各段 text 字数之和须在 {hard_min}-{hard_max} 字之间。\n"
            f"每段用「{layers}」三层写法，每层一句短话，禁止整段一句带过。\n"
            "【生成顺序】先按预算写满各段 segments，再拼接 narration，最后核对 word_count。\n"
            f"{self_check}"
        )
    cap = plan["segment_cap"]
    hard_cap = segment_text_hard_cap(segment_target_sec)
    per_target_lo = plan["per_seg_lo"]
    per_target_hi = plan["per_seg_hi"]
    sec = int(segment_target_sec) if segment_target_sec == int(segment_target_sec) else segment_target_sec
    return (
        f"【字数预算】总目标 {narration_target} 字；"
        f"写作目标约 {writing_target} 字（总目标的 {pct}%）；"
        f"验收区间 {hard_min}-{hard_max} 字（超出或不足均不合格）。\n"
        f"单镜上限 {sec}s，每段 text 目标 ≤ {per_target_hi} 字、绝对不得超过 {cap} 字"
        f"（硬上限 {hard_cap} 字，超限必须拆段）。\n"
        f"须至少 {seg_count_min} 个 segments（按 {writing_target} 字与单段 {per_target_hi} 字估算）；"
        f"每段建议 {per_target_lo}-{per_target_hi} 字、下限 {per_min} 字；"
        f"各段 text 字数之和须在 {hard_min}-{hard_max} 字之间。\n"
        f"每段用「{layers}」三层写法，每层一句短话；总字数靠加段补不足，靠删内容防超标。\n"
        "【生成顺序】先按段数预算写满各段 segments，再拼接 narration，最后核对 word_count。\n"
        f"{self_check}"
    )


def _storyboard_compact_segment_budget(
    *,
    narration_target: int,
    segment_target_sec: float,
) -> str:
    """compact 模式 user 段数预算表，帮助模型心算总字数。"""
    plan = narration_writing_plan(narration_target, segment_target_sec)
    hard_max = narration_accept_max_chars(narration_target)
    seg_min = plan["seg_count_min"]
    per_hi = plan["per_seg_hi"]
    seg_max = max(seg_min, (hard_max + per_hi - 1) // per_hi)
    per_lo = plan["per_seg_lo"]
    return (
        f"【段数预算】须约 {seg_min}-{seg_max} 段，每段 {per_lo}-{per_hi} 字，"
        f"各段 text 之和不得超过 {hard_max} 字；超标须删例子/删并列点，禁止加长单段。"
    )


def _storyboard_length_system_clause(
    *,
    narration_target: int,
    segment_target_sec: float,
    compact_output: bool,
) -> str:
    plan = narration_writing_plan(narration_target, segment_target_sec)
    hard_min = plan["hard_min"]
    writing_target = plan["writing_target"]
    per_min = plan["per_seg_min"]
    seg_count_min = plan["seg_count_min"]
    pct = int(NARRATION_WRITING_TARGET_RATIO * 100)
    hard_max = narration_accept_max_chars(narration_target)
    if compact_output:
        budget_line = _storyboard_compact_segment_budget(
            narration_target=narration_target,
            segment_target_sec=segment_target_sec,
        )
        return (
            f"{budget_line}"
            f"各段 text 须落在单段上限内（每段至少 {per_min} 字），后端会拼接为 narration；"
            f"须至少 {seg_count_min} 个 segments；"
            f"拼接后总字数须在 {hard_min}-{hard_max} 字之间（目标约 {writing_target} 字）。"
            "输出前须自检：段数达标、各段非空且不超单段上限、总和在区间内、segments 与 narration 拼接一致。"
        )
    return (
        f"各段 text 按顺序拼接须与 narration 完全一致；"
        f"须至少 {seg_count_min} 个 segments；"
        f"narration 须在 {hard_min}-{hard_max} 字之间（目标约 {writing_target} 字）。"
        "输出前须自检：段数达标、各段非空且不超单段上限、字数在区间内、word_count 等于 narration 实际字数。"
    )


def _append_supplementary_to_user(user: str, supplementary_info: str | None) -> str:
    extra = (supplementary_info or "").strip()
    if not extra:
        return user
    return (
        f"{user}\n\n"
        "用户补充信息（须合理融入口播与分镜，勿编造与补充信息矛盾的内容；"
        "若与科普常识冲突，以科学事实为准）：\n"
        f"{extra}"
    )


def _supplementary_system_clause(supplementary_info: str | None) -> str:
    extra = (supplementary_info or "").strip()
    if not extra:
        return ""
    return (
        "用户会提供补充信息：须融入口播内容与表达风格，"
        "但不得与画面时间表冲突；若冲突以时间表为准。"
    )


def _resolve_video_timeline(
    video_timeline: str | None,
    *,
    script: dict | None = None,
) -> VideoTimeline | None:
    raw = (video_timeline or "").strip()
    if not raw and script:
        saved = script.get("video_timeline")
        if isinstance(saved, str) and saved.strip():
            raw = saved.strip()
    return parse_video_timeline(raw) if raw else None


def _title_rule(title: str, max_title: int) -> tuple[str, str]:
    cleaned = re.sub(r"\s+", "", title.strip())
    if len(cleaned) <= max_title:
        return (
            f"title 必须与原标题完全一致：{cleaned}，不要改写、精简或替换。",
            f"原标题：{title}\n请输出 title（与原标题一致）、完整口播",
        )
    return (
        f"title 为精简视频标题，保留原标题核心意思，不含空格换行，字数不超过 {max_title}。",
        f"原标题：{title}\n请输出精简 title（≤{max_title}字）、完整口播",
    )


def _storyboard_segment_rule(target: float, profile_style: str = "") -> str:
    types = _visual_brief_types(profile_style) if profile_style else "（写实场景）/（结构示意图）/（对比图）/（线稿解剖图）/（微观分子图）"
    common = (
        "segments为分镜数组；"
        "各段含segment_index,text,visual_brief,visual_mode=static_motion；"
        "各段text按顺序拼接须与narration全文一致。"
        "visual_brief为该镜画面描述（80-150字）：写清视觉主旨、关键动作或对比关系、"
        "场景类型与情绪，帮助后续扩写文生图提示词；不写镜头焦距、光线方向、材质参数等细节。"
        f"visual_brief末尾须用括号标注画面类型{types}。"
        "另须输出visual_style：全片画风定调一句话（画风+主色调+跨镜统一元素如道具造型）。"
    )
    if target <= 0:
        return common + "不约束单镜时长，按口播内容逻辑切分，段数由内容决定。"
    narration_sec = effective_segment_narration_sec(target)
    sec = _format_segment_target_sec(narration_sec)
    cap = segment_text_char_cap(target)
    hard_cap = segment_text_hard_cap(target)
    comfort = segment_comfort_chars(cap)
    lo = max(12, int(cap * 0.45))
    return (
        common
        + f"单镜口播上限{sec}秒；每段text建议{lo}-{comfort}字，绝对不得超过{cap}字（硬上限{hard_cap}字）；"
        "任一 segment 的 text 超过单段上限必须拆成多段，禁止合并成长段；"
        "三层写法每层只用一句短话，禁止把多句堆进同一段；"
        "按自然断句与口播节奏切分，段数宁多勿少。"
    )


def _prompt_step(step: str, system: str, user: str) -> dict[str, str]:
    return {
        "step": step,
        "label": _STEP_LABELS.get(step, step),
        "system": system,
        "user": user,
    }


def _narration_only_length_rule(content_style: str) -> str:
    layers = _storyboard_layer_style(content_style)
    return (
        f"【口播写法】全文连贯书写，按「{layers}」思路展开，用句号/问号/感叹号自然断句；"
        "不要输出 segments，后端会按单镜时长自动切分。"
        "word_count 必须等于 narration 实际字数（不含空格换行），禁止虚报。"
    )


def _narration_execution_headline(
    *,
    narration_target: int,
    content_style: str,
) -> str:
    hard_min = narration_accept_min_chars(narration_target)
    writing_target = narration_writing_target_chars(narration_target)
    hard_max = narration_accept_max_chars(narration_target)
    layers = _storyboard_layer_style(content_style)
    return (
        f"【首要任务】口播总字数须落在 {hard_min}-{hard_max} 字硬区间内（写作目标约 {writing_target} 字），"
        f"超过 {hard_max} 字整稿作废，优先删例子/删并列知识点。"
        f"全文用连贯口播书写，按「{layers}」思路展开，用句号自然断句；"
        "不要输出 segments 字段，分镜由后端按单镜时长自动切分。"
        "输出前统计 narration 字数并核对 word_count。"
    )


def _narration_only_length_budget(
    *,
    narration_target: int,
    content_style: str,
) -> str:
    hard_min = narration_accept_min_chars(narration_target)
    writing_target = narration_writing_target_chars(narration_target)
    hard_max = narration_accept_max_chars(narration_target)
    pct = int(NARRATION_WRITING_TARGET_RATIO * 100)
    layers = _storyboard_layer_style(content_style)
    return (
        f"【字数预算】总目标 {narration_target} 字；"
        f"写作目标约 {writing_target} 字（总目标 {narration_target} 字的 {pct}%）；"
        f"验收区间 {hard_min}-{hard_max} 字（超出或不足均不合格）。\n"
        f"全文用「{layers}」写法连贯展开，不足可补细节，超标须删繁就简。\n"
        "【生成顺序】只写 narration 与 word_count，不要写 segments。\n"
        "【输出前硬性自检】①narration 字数在验收区间内；"
        "②word_count 等于 narration 实际字数；"
        "③口播无伪亲历/第一人称从业叙事。"
    )


def build_narration_prompts(
    title: str,
    *,
    feedback: str | None = None,
    max_title_length: int | None = None,
    narration_target_words: int | None = None,
    supplementary_info: str | None = None,
    job: dict | None = None,
    orientation: str | None = None,
    content_style: str | None = None,
) -> dict[str, str]:
    """第一步：只生成口播全文与 visual_style（不含 segments）。"""
    settings = get_settings()
    profile_orientation, profile_style = _resolve_script_profile(
        job,
        orientation=orientation,
        content_style=content_style,
    )
    max_title = settings.max_title_length if max_title_length is None else max_title_length
    narration_word_target = (
        narration_target_words
        if narration_target_words is not None
        else default_narration_target_words(settings)
    )
    narration_word_min, narration_word_max = _narration_word_range(narration_word_target)
    title_rule, title_user_prefix = _title_rule(title, max_title)
    length_rule = (
        f"口播总目标 {narration_word_target} 字；{_writing_target_clause(narration_word_target)}；"
        f"验收区间 {narration_word_min}-{narration_word_max} 字（不含空格换行）；"
        f"低于 {narration_word_min} 字或高于 {narration_word_max} 字视为不合格；"
        f"{_narration_only_length_rule(profile_style)}"
    )
    system = (
        f"{_storyboard_role(profile_style)}输出 JSON，字段：title, narration, word_count, visual_style。"
        "口播总字数未落在验收硬区间内则整稿无效；禁止输出 segments 字段。"
        f"{title_rule}"
        f"{length_rule}"
        f"narration口吻：{_narration_voice_rule(profile_style)}"
        f"{_NARRATION_ANTI_MEMOIR_RULE}"
        f"{_NARRATION_ANTI_REPETITION_RULE}"
        f"{_structure_rule(orientation=profile_orientation, content_style=profile_style)}"
        "结构完整有开头结尾。"
        "禁止口播开头空泛自我介绍或冗长人设铺垫。"
        "visual_style 为全片画风定调一句话（画风+主色调+跨镜统一元素如道具造型）。"
        "本步只写口播与 visual_style，不写分镜与 image_prompt。"
        f"{_supplementary_system_clause(supplementary_info)}"
        f"{_json_output_clause(_NARRATION_ONLY_JSON_EXAMPLE)}"
    )
    user = _append_supplementary_to_user(
        (
            f"{_narration_execution_headline(narration_target=narration_word_target, content_style=profile_style)}\n\n"
            f"{_narration_only_length_budget(narration_target=narration_word_target, content_style=profile_style)}\n\n"
            f"{title_user_prefix}、visual_style 与完整口播 narration。"
        ),
        supplementary_info,
    )
    if feedback:
        user += f"\n\n上次不合格：{feedback}。请按要求重写。"
    return _prompt_step("narration", system, user)


def _format_visual_brief_segments_for_prompt(segments: list[dict]) -> str:
    ordered = sorted(
        segments,
        key=lambda seg: int(seg.get("segment_index") or seg.get("index") or 0),
    )
    lines: list[str] = []
    for seg in ordered:
        idx = seg.get("segment_index")
        text = str(seg.get("text") or "")
        lines.append(f"segment {idx}: text={text!r}")
    return "\n".join(lines)


def build_visual_brief_prompts(
    script: dict[str, Any],
    *,
    feedback: str | None = None,
    supplementary_info: str | None = None,
    job: dict | None = None,
    orientation: str | None = None,
    content_style: str | None = None,
) -> dict[str, str]:
    """第二步：基于已切分的 segments 与全文 narration 生成 visual_brief。"""
    profile_orientation, profile_style = _resolve_script_profile(
        job,
        orientation=orientation,
        content_style=content_style,
    )
    segments = script.get("segments") or []
    narration = str(script.get("narration") or "").strip()
    visual_style = str(script.get("visual_style") or "").strip()
    title = str(script.get("title") or "").strip()
    types = _visual_brief_types(profile_style)
    seg_rule = (
        "segments 为分镜数组，须与输入逐段一一对应；"
        "各段含 segment_index, visual_brief, visual_mode=static_motion；"
        "不要输出或修改各段 text。"
        f"visual_brief 为该镜画面描述（80-150 字）：写清视觉主旨、关键动作或对比关系、"
        f"场景类型与情绪；末尾须用括号标注画面类型{types}。"
        "须通读全文 narration，保证相邻分镜画面衔接自然、叙事节奏连贯，"
        "避免前后镜主体/场景毫无关联的跳跃；"
        "同时每镜 visual_brief 只表达本段 text 内容，禁止提前画后续段落情节。"
    )
    system = (
        f"{_storyboard_role(profile_style)}输出 JSON，字段：visual_style, segments。"
        f"{seg_rule}"
        "visual_style 可与输入一致，或在保持全片统一的前提下微调措辞。"
        f"{_supplementary_system_clause(supplementary_info)}"
        f"{_json_output_clause(_VISUAL_BRIEF_JSON_EXAMPLE)}"
    )
    user = _append_supplementary_to_user(
        (
            f"标题：{title}\n"
            f"全片 visual_style：{visual_style or '（待你输出）'}\n\n"
            f"【口播全文 narration】（供把握画面节奏与连贯性，勿改写）：\n{narration}\n\n"
            f"【各分镜口播 text】（已固定，须逐段生成 visual_brief）：\n"
            f"{_format_visual_brief_segments_for_prompt(segments)}"
        ),
        supplementary_info,
    )
    if feedback:
        user += f"\n\n上次不合格：{feedback}。请按要求重写。"
    return _prompt_step("visual_brief", system, user)


def build_board_prompts(
    title: str,
    *,
    feedback: str | None = None,
    segment_target_sec: float | None = None,
    max_title_length: int | None = None,
    narration_target_words: int | None = None,
    supplementary_info: str | None = None,
    job: dict | None = None,
    orientation: str | None = None,
    content_style: str | None = None,
    compact_output: bool = False,
) -> dict[str, str]:
    settings = get_settings()
    profile_orientation, profile_style = _resolve_script_profile(
        job,
        orientation=orientation,
        content_style=content_style,
    )
    target = settings.segment_target_sec if segment_target_sec is None else segment_target_sec
    seg_rule = _storyboard_segment_rule(target, profile_style=profile_style)
    max_title = settings.max_title_length if max_title_length is None else max_title_length
    narration_word_target = (
        narration_target_words
        if narration_target_words is not None
        else default_narration_target_words(settings)
    )
    narration_word_min, narration_word_max = _narration_word_range(narration_word_target)
    narration_hard_min = narration_word_min
    title_rule, title_user_prefix = _title_rule(title, max_title)
    length_rule = (
        f"口播总目标 {narration_word_target} 字；{_writing_target_clause(narration_word_target)}；"
        f"验收区间 {narration_hard_min}-{narration_word_max} 字（不含空格换行）；"
        f"低于 {narration_hard_min} 字或高于 {narration_word_max} 字视为不合格；"
        f"{_narration_length_rule(profile_style)}"
    )
    length_system = _storyboard_length_system_clause(
        narration_target=narration_word_target,
        segment_target_sec=target,
        compact_output=compact_output,
    )
    if compact_output:
        json_fields = "title, visual_style, segments"
        narration_clause = (
            "【紧凑输出】不要输出 narration 与 word_count 字段；"
            "各段 text 须按字数预算落在验收区间内，后端会自动拼接为 narration。"
            "每段 visual_brief 控制在 30-60 字，只写画面主旨，末尾用括号注明画面类型"
            "（写实场景）/（结构示意图）/（对比图）/（线稿解剖图）/（微观分子图），禁止冗长描写。"
        )
        word_count_clause = ""
    else:
        json_fields = "title, narration, word_count, visual_style, segments"
        narration_clause = ""
        word_count_clause = "word_count必须等于narration实际字数，不得虚报。"
    system = (
        f"{_storyboard_role(profile_style)}输出JSON，字段：{json_fields}。"
        "口播总字数未落在验收硬区间内则整稿无效；JSON 样例仅示字段结构，不代表篇幅，禁止照抄样例短句。"
        "任一段 text 超过单镜字数上限则整稿无效，须拆段而非加长单段。"
        f"{title_rule}"
        f"{seg_rule}"
        f"{length_rule}"
        f"{length_system}"
        f"{narration_clause}"
        f"narration口吻：{_narration_voice_rule(profile_style)}"
        f"{_NARRATION_ANTI_MEMOIR_RULE}"
        f"{_NARRATION_ANTI_REPETITION_RULE}"
        f"{_structure_rule(orientation=profile_orientation, content_style=profile_style)}"
        "结构完整有开头结尾。"
        "禁止口播开头空泛自我介绍或冗长人设铺垫。"
        "各段text须与narration口吻一致。"
        f"{word_count_clause}"
        "本步只写口播与画面描述visual_brief，不写image_prompt。"
        f"{_supplementary_system_clause(supplementary_info)}"
        f"{_json_output_clause(_STORYBOARD_JSON_EXAMPLE_COMPACT if compact_output else _STORYBOARD_JSON_EXAMPLE)}"
    )
    if target > 0:
        sec = _format_segment_target_sec(effective_segment_narration_sec(target))
        split_hint = f"并按单镜口播上限{sec}秒动态切分分镜"
    else:
        split_hint = "并按口播内容逻辑动态切分分镜"
    length_budget = _storyboard_length_budget(
        narration_target=narration_word_target,
        segment_target_sec=target,
        content_style=profile_style,
    )
    execution_headline = _storyboard_execution_headline(
        narration_target=narration_word_target,
        segment_target_sec=target,
        content_style=profile_style,
    )
    compact_budget = ""
    if compact_output and target > 0:
        compact_budget = (
            _storyboard_compact_segment_budget(
                narration_target=narration_word_target,
                segment_target_sec=target,
            )
            + "\n\n"
        )
    types = _visual_brief_types(profile_style)
    user = _append_supplementary_to_user(
        (
            f"{execution_headline}\n\n"
            f"{compact_budget}"
            f"{length_budget}\n\n"
            f"{title_user_prefix}、visual_style 与分镜，{split_hint}。\n\n"
            + (
                f"每段 visual_brief 30-60 字，写清画面主旨，末尾用括号注明画面类型{types}。"
                if compact_output
                else f"每段 visual_brief 写清该镜画面主旨并在末尾注明画面类型{types}，便于下一步扩写文生图提示词。"
            )
        ),
        supplementary_info,
    )
    if feedback:
        user += f"\n\n上次不合格：{feedback}。请按要求重写。"
    return _prompt_step("storyboard", system, user)


# 兼容旧名
build_storyboard_prompts = build_board_prompts


_SD15_PROMPT_EN_RULE = (
    "同时为每段输出 sd15_prompt_en：专为 Stable Diffusion 1.5 优化的英文提示词（20～40 词），"
    "格式为「[核心主体] [动作/状态], [场景类型], [一个关键视觉特征]」；"
    "先读 visual_brief 末尾的画面类型标签确定主体方向，再提炼主体；"
    "只写一个核心主体，禁止并列堆砌多个名词；"
    "禁止写 lora 标签、style 词和背景后缀（系统自动追加）；"
    "science 类禁止 person/face/head 等人物词。\n"
    "sd15_prompt_en 正确示例：\n"
    "  写实场景：\"stainless steel pot on stove, close-up surface detail, kitchen counter\"\n"
    "  结构示意图：\"cross-section diagram of battery cell, labeled anode cathode layers\"\n"
    "  对比图：\"healthy lung tissue vs damaged lung, side by side, medical illustration\"\n"
    "  线稿解剖图：\"line art diagram of human lung anatomy, labeled air sacs, white background\"\n"
    "  微观分子图：\"carbon monoxide molecules passing through wet fabric mesh, glowing science\"\n"
)


def build_image_prompts_prompts(
    script: dict[str, Any],
    *,
    feedback: str | None = None,
    supplementary_info: str | None = None,
    job: dict | None = None,
    orientation: str | None = None,
    content_style: str | None = None,
    segment_indices: list[int] | None = None,
    include_sd15_prompt: bool = False,
) -> dict[str, str]:
    profile_orientation, profile_style = _resolve_script_profile(
        job,
        orientation=orientation,
        content_style=content_style,
    )
    segments = script.get("segments") or []
    if segment_indices is not None:
        wanted = {int(idx) for idx in segment_indices}
        segments = [seg for seg in segments if int(seg.get("segment_index", -1)) in wanted]
    lines = [
        f"segment {seg['segment_index']}: "
        f"text={seg.get('text', '')!r}; visual_brief={seg.get('visual_brief', '')!r}"
        for seg in segments
    ]
    json_example = _IMAGE_PROMPTS_JSON_EXAMPLE if include_sd15_prompt else _IMAGE_PROMPTS_JSON_EXAMPLE_NO_SD15
    sd15_rule = _SD15_PROMPT_EN_RULE if include_sd15_prompt else ""
    sd15_fields = "、image_prompt、motion_prompt 与 sd15_prompt_en" if include_sd15_prompt else "、image_prompt 与 motion_prompt"
    role = (
        "你是历史悬案视频文生图与运动提示词专家。"
        if profile_style == CONTENT_STYLE_HISTORICAL_MYSTERY
        else "你是科普视频文生图与运动提示词专家。"
    )
    system = (
        f"{role}输出JSON，字段：image_prompts。"
        f"image_prompts为数组，每项含segment_index{sd15_fields}。"
        f"{_image_prompt_rule(orientation=profile_orientation, content_style=profile_style, sd15_mode=include_sd15_prompt)}"
        f"{sd15_rule}"
        "image_prompts须覆盖输入的每一段，segment_index一一对应，不得遗漏。"
        f"{_json_output_clause(json_example)}"
    )
    if include_sd15_prompt:
        user_tail = (
            "\n\n请为每段编写 image_prompt 与 motion_prompt。"
            "image_prompt 按六维思路写成一段连贯中文，勿用维度标签，不写分辨率套话。"
            "同时为每段输出准确的 sd15_prompt_en。"
        )
    else:
        user_tail = (
            "\n\n请为每段扩写 image_prompt 与 motion_prompt。"
            "image_prompt 按六维思路写成一段连贯中文（勿用「主体：」等标签），"
            "篇幅按画面复杂度充分写，不凑字数、不写4K/8K/分辨率等规格套话。"
        )
    user = _append_supplementary_to_user(
        (
            f"视频标题：{script.get('title', '')}\n"
            f"全片画风定调 visual_style：{script.get('visual_style', '')}\n\n"
            "各分镜口播与画面描述：\n"
            + "\n".join(lines)
            + user_tail
        ),
        supplementary_info or script.get("supplementary_info"),
    )
    if feedback:
        user += f"\n\n上次不合格：{feedback}。请按要求重写。"
    return _prompt_step("image_prompts", system, user)


def build_material_script_prompts(
    title: str,
    *,
    feedback: str | None = None,
    max_title_length: int | None = None,
    narration_target_words: int | None = None,
    supplementary_info: str | None = None,
    video_timeline: str | None = None,
    script: dict | None = None,
) -> dict[str, str]:
    settings = get_settings()
    max_title = settings.max_title_length if max_title_length is None else max_title_length
    timeline = _resolve_video_timeline(video_timeline, script=script)
    if timeline:
        narration_word_min, narration_word_max = narration_range_for_timeline(timeline)
        narration_hard_min = narration_word_min
        narration_word_target = (narration_word_min + narration_word_max) // 2
    else:
        narration_word_target = (
            narration_target_words if narration_target_words is not None else 800
        )
        narration_word_min, narration_word_max = _narration_word_range(narration_word_target)
        narration_hard_min = narration_word_min
    title_rule, title_user_prefix = _title_rule(title, max_title)
    segment_rule = (
        f"segments 必须恰好 {len(timeline.slots)} 条，与画面时间表逐段一一对应；"
        "每项含 segment_index 与 text，第 i 段只讲第 i 段画面；"
        "各段 text 按顺序拼接须与 narration 完全一致，口吻同样保持童趣。"
        if timeline
        else (
            "segments 为分句数组，每项含 segment_index 与 text；"
            "各段 text 按顺序拼接须与 narration 完全一致，口吻同样保持童趣；"
            "按自然断句切分，无需 visual 字段。"
        )
    )
    opening_rule = (
        "禁止开场钩子、悬念反问、自我介绍或全片总起；"
        "narration 第一句必须从时间表第 1 段画面内容直接讲起。"
        if timeline
        else "禁止开头自我介绍；第一句直接进入主题。"
    )
    length_rule = (
        f"narration 总目标 {narration_word_target} 字；{_writing_target_clause(narration_word_target)}；"
        f"验收区间 {narration_hard_min}-{narration_word_max} 字（不含空格换行）；"
        f"低于 {narration_hard_min} 字或高于 {narration_word_max} 字视为不合格；"
        f"{_MATERIAL_NARRATION_LENGTH_RULE}"
    )
    system = (
        "你是给小朋友讲科普的视频口播编剧。视频画面已由用户上传的基底视频提供，无需描述画面。"
        "输出 JSON，字段：title, narration, word_count, segments。"
        f"{title_rule}"
        f"{length_rule}"
        f"{_NARRATION_VOICE_RULE}"
        f"{_NARRATION_ANTI_MEMOIR_RULE}"
        f"{opening_rule}"
        f"{segment_rule}"
        "word_count 必须等于 narration 实际字数，禁止虚报。"
        f"{timeline_system_clause(timeline) if timeline else ''}"
        f"{_supplementary_system_clause(supplementary_info)}"
        f"{_json_output_clause(_MATERIAL_SCRIPT_JSON_EXAMPLE)}"
    )
    user_parts = [
        f"{title_user_prefix} narration 与分句 segments。",
    ]
    if not timeline:
        user_parts.append(
            _storyboard_length_budget(
                narration_target=narration_word_target,
                segment_target_sec=0,
                content_style=CONTENT_STYLE_SCIENCE_CHILD,
            )
        )
    user = _append_supplementary_to_user("\n\n".join(user_parts), supplementary_info)
    if timeline:
        user = append_timeline_to_user(user, timeline)
    if feedback:
        user += f"\n\n上次不合格：{feedback}。请按要求重写。"
    return _prompt_step("material_script", system, user)


def build_narration_expand_prompts(
    script: dict[str, Any],
    *,
    min_chars: int,
    mode: str = "storyboard",
) -> dict[str, str]:
    """在初稿字数不足时专用扩写（保留分镜与画面字段）。"""
    current = _narration_char_count_for_prompt(str(script.get("narration") or ""))
    deficit = max(1, min_chars - current)
    if mode == "narration_only":
        system = (
            "你是口播扩写编辑。用户在初稿字数不足，须在保持主题与结构的前提下扩写。"
            "输出 JSON，字段：title, narration, word_count, visual_style。"
            f"扩写后 narration 须至少 {min_chars} 字（不含空格换行），当前仅 {current} 字，还差约 {deficit} 字。"
            "规则：只扩写 narration，补具体细节、案例、步骤或结论，禁止删减已有核心信息；"
            "不要输出 segments；word_count 等于 narration 实际字数。"
            f"{_NARRATION_ANTI_MEMOIR_RULE}"
            f"{_json_output_clause(_NARRATION_ONLY_JSON_EXAMPLE)}"
        )
        draft = {
            "title": script.get("title"),
            "narration": script.get("narration"),
            "word_count": script.get("word_count"),
            "visual_style": script.get("visual_style"),
        }
        user = (
            "当前稿件（字数不足，请扩写 narration）：\n"
            f"{json.dumps(draft, ensure_ascii=False, indent=2)}"
        )
        return _prompt_step("narration_expand", system, user)
    keep_visual = mode == "storyboard"
    system = (
        "你是口播扩写编辑。用户在初稿字数不足，须在保持主题与分镜结构的前提下扩写。"
        "输出 JSON，字段与输入一致（title, narration, word_count, segments"
        + (", visual_style" if keep_visual else "")
        + "）。"
        f"扩写后 narration 须至少 {min_chars} 字（不含空格换行），当前仅 {current} 字，还差约 {deficit} 字。"
        "规则：segments 段数与 segment_index 不得减少、不得合并；"
        "每段 text 只能扩写（补具体细节、案例、步骤或结论），禁止删减已有核心信息；"
        "narration 为各段 text 按顺序原样拼接；word_count 等于 narration 实际字数。"
        f"{_NARRATION_ANTI_MEMOIR_RULE}"
    )
    if keep_visual:
        system += (
            "须保留 visual_style 与各段 visual_brief，仅扩写 text；"
            "禁止删除 visual_brief 或改成空字符串。"
        )
        system += _json_output_clause(_STORYBOARD_JSON_EXAMPLE)
    else:
        system += _json_output_clause(_MATERIAL_SCRIPT_JSON_EXAMPLE)
    draft = {
        "title": script.get("title"),
        "narration": script.get("narration"),
        "word_count": script.get("word_count"),
        "segments": script.get("segments"),
    }
    if keep_visual:
        draft["visual_style"] = script.get("visual_style")
    user = (
        "当前稿件（字数不足，请扩写）：\n"
        f"{json.dumps(draft, ensure_ascii=False)}\n\n"
        f"请扩写至至少 {min_chars} 字后输出完整 JSON。"
    )
    return _prompt_step(f"expand_{mode}", system, user)


def build_segment_shrink_prompts(
    script: dict[str, Any],
    *,
    segment_indices: list[int],
    cap: int,
    segment_target_sec: float,
    job: dict | None = None,
    content_style: str | None = None,
) -> dict[str, str]:
    """略超限分镜专用缩字（只改 text，保留 visual_brief 等字段）。"""
    _, profile_style = _resolve_script_profile(job, content_style=content_style)
    voice_rule = _narration_voice_rule(profile_style)
    by_idx = {
        int(seg["segment_index"]): seg
        for seg in script.get("segments") or []
        if seg.get("segment_index") is not None
    }
    targets: list[dict[str, Any]] = []
    for idx in segment_indices:
        seg = by_idx.get(idx)
        if not seg:
            continue
        text = str(seg.get("text") or "")
        targets.append(
            {
                "segment_index": idx,
                "text": text,
                "chars": _narration_char_count_for_prompt(text),
                "max_chars": cap,
            }
        )
    narration_sec = effective_segment_narration_sec(segment_target_sec)
    sec = int(narration_sec) if narration_sec == int(narration_sec) else narration_sec
    system = (
        "你是口播缩字编辑。指定分镜口播略超单镜时长上限，只做删字瘦身，禁止改写文风。"
        '输出 JSON：{"segments": [{"segment_index": 序号, "text": "缩短后的口播"}, ...]}。'
        f"每段 text 不得超过 {cap} 字（不含空格换行）。"
        "【文风·最高优先级】必须完整保留原句的语气、节奏、人称、童趣/悬疑/生活化口吻与修辞习惯；"
        "禁止把口语改成书面语、禁止换成另一种叙述风格、禁止增删感叹/拟声/比喻的类型。"
        f"当前口吻要求：{voice_rule}"
        "只允许删重复比喻、次要形容词和冗余连接词；禁止改变科学事实与核心信息；"
        "禁止增删 segment_index；不要输出 narration、visual_brief 等其他字段。"
        f"{_NARRATION_ANTI_MEMOIR_RULE}"
    )
    user = (
        f"单镜口播上限 {sec}s（每段 text 最多 {cap} 字）。"
        "在完全保持原文风与口吻的前提下缩短以下分镜 text，并输出 JSON：\n"
        f"{json.dumps(targets, ensure_ascii=False)}"
    )
    return _prompt_step("segment_shrink", system, user)


def _narration_char_count_for_prompt(text: str) -> int:
    return len(re.sub(r"\s+", "", text))
