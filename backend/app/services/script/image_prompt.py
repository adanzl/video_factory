"""文生图提示词相关规则（质量、格式、维度、风格规则、motion、SD15）与构建。"""

from __future__ import annotations

import re
from typing import Any

from app.utils.job_info import (
    CONTENT_STYLE_DAILY_STORY,
    CONTENT_STYLE_HISTORICAL_MYSTERY,
    CONTENT_STYLE_LIFE_EXPERIENCE,
    CONTENT_STYLE_SCIENCE_CHILD,
    CONTENT_STYLE_TECH_SCIENCE,
    ORIENTATION_LANDSCAPE,
)

# ══════════════════════════════════════════════════════════════════════
#  daily_story 规则拼装 T2I（不再二次 LLM 扩写 visual_brief）
#
#  结构: 风格 + visual_brief + 角色外貌 + 光照 + 构图
# ══════════════════════════════════════════════════════════════════════

_DAILY_T2I_STYLE = (
    "儿童情绪涂鸦风格，彩铅和蜡笔混合笔触，线条用力不均，"
    "高饱和色彩，涂色出界，橡皮擦拭痕迹，手工感。"
)

_DAILY_CHAR_ZHAO = (
    "昭昭：7岁男孩，黑色超短发露耳露后颈，圆脸，"
    "蓝色短袖T恤，深蓝色短裤，两侧同色蓝白运动鞋。"
)
# 地垫系带场面：「两侧」易被 T2I 画成额外鞋，改明确写脚上那一双
_DAILY_CHAR_ZHAO_FLOOR = (
    "昭昭：7岁男孩，黑色超短发露耳露后颈，圆脸，"
    "蓝色短袖T恤，深蓝色短裤，双脚均已穿好一双蓝白运动鞋。"
)
# 地垫粉鞋：T2I 把「穿进鞋眼」理解成往脚上套鞋，统一用「穿过」
_FLOOR_SHOE_EYELET_RE = re.compile(r"穿进(.{0,4}鞋眼)")
_FLOOR_SHOE_MAT_ANTI_PICKUP = (
    "地垫粉鞋是灿灿刚脱下的唯一一双，两只始终平放接触地垫，鞋帮贴地，"
    "无人拿在手中，无人往脚上套粉鞋，全画面仅这两只粉鞋。"
)
_FLOOR_SHOE_ANTI_EXTRA = "全画面地垫上仅此一双粉红运动鞋共两只，禁止第三只鞋或第二双粉鞋。"
# brief 里「指鞋/伸手向鞋带/托鞋帮」与硬锁打架，会诱发第三只鞋或套鞋
_FLOOR_SHOE_HAND_SCRUB_RE = re.compile(
    r"(?:，|^)"
    r"(?:"
    r"双手(?:伸向|各握|用力向外抽紧|握着|捏着)[^，。；]{0,20}|"
    r"(?:右手|左手)[^，。；]{0,8}(?:捏|握|托|抽|穿)[^，。；]{0,20}|"
    r"正(?:把|将)[^，。；]{0,20}鞋带[^，。；]{0,16}|"
    r"准备系带|托着鞋帮"
    r")"
)
_DAILY_CHAR_CANCAN = (
    "灿灿：10岁女孩，黑色头发，黑色单侧高马尾，"
    "粉色卫衣，蓝色长裤，两侧同色粉红运动鞋。"
)
_DAILY_CHAR_CANCAN_SOCKS = (
    "灿灿：10岁女孩，黑色头发，黑色单侧高马尾，"
    "粉色卫衣，蓝色长裤，赤脚仅穿白袜子。"
)
# 涂鸦高饱和易把马尾画成彩色；发色硬锁紧跟角色块（句末权重最低）。
# 必须纯正面表述——图像模型把否定词当生成指令，
# "禁止…挑染/彩色"会诱发彩虹发（实测），故不写任何颜色禁止词。
_DAILY_CANCAN_HAIR_LOCK = (
    "灿灿头发通体纯黑，头顶到马尾同一黑色。"
)
_DAILY_CHAR_MOM = (
    "妈妈：成年女性，黑色长发，米色上衣，蓝色牛仔裤，深色平底鞋。"
)
_DAILY_CHAR_HEIGHT = "昭昭比灿灿矮约半个头。"
_DAILY_CHAR_HEIGHT_3 = "妈妈最高，灿灿次之，昭昭最矮（约差半个头）。"

_DAILY_CHAR_MAP: dict[str, str] = {
    "昭昭": _DAILY_CHAR_ZHAO,
    "灿灿": _DAILY_CHAR_CANCAN,
    "妈妈": _DAILY_CHAR_MOM,
}

_FLOOR_SHOE_SETTING_RE = re.compile(
    r"地垫.{0,24}鞋|鞋.{0,16}地垫|鞋边.*系带|鞋带散开摆着"
)


def _daily_cancan_lifts_floor_shoes(vb: str) -> bool:
    """本镜是否为灿灿双手拎起死结串在一起的地垫粉鞋。"""
    text = vb or ""
    if "灿灿" not in text:
        return False
    return bool(
        re.search(r"灿灿[^。；]{0,32}(?:拎|提|拎起)", text)
        or ("双手拎起" in text and text.find("灿灿") < text.find("双手拎起"))
    )


def _daily_setting_floor_shoe_scene(setting: str | None) -> bool:
    """全片设定是否为「地垫上无人穿着的鞋、昭昭蹲旁系带」类场面。"""
    if not setting:
        return False
    return bool(_FLOOR_SHOE_SETTING_RE.search(setting))


def _daily_floor_shoe_mat_clause(vb: str) -> str:
    """按本镜剧情写地垫上一双粉鞋的状态（始终共两只，禁止第三只）。"""
    text = vb or ""
    anti_extra = _FLOOR_SHOE_ANTI_EXTRA
    if _daily_cancan_lifts_floor_shoes(text):
        flip = "，鞋子翻了个个儿" if any(k in text for k in ("翻", "哗啦")) else ""
        return (
            "全画面仅有一双粉红运动鞋共两只，鞋带系成死结串在一起，"
            f"被灿灿双手拎离地面{flip}，两只鞋底贴在一起；"
            f"{anti_extra}"
        )
    if any(k in text for k in ("拎", "提起", "翻过去", "哗啦")):
        return (
            "地垫中央仅有一双粉红运动鞋共两只，鞋带已系成死结串在一起，"
            f"正被拎起或翻倒；{anti_extra}"
        )
    if any(
        k in text
        for k in ("死结", "系成死", "贴一块", "串一块", "串在一", "鞋底贴", "鞋底紧紧")
    ):
        return (
            "地垫中央仅有一双粉红运动鞋共两只，鞋带系成死结，"
            f"两只鞋底紧紧贴在一起；{_FLOOR_SHOE_MAT_ANTI_PICKUP}{anti_extra}"
        )
    if any(k in text for k in ("连环扣", "缠绕", "勒出印", "勒出")):
        return (
            "地垫中央仅有一双粉红运动鞋共两只，鞋带相互缠绕成连环扣；"
            f"{_FLOOR_SHOE_MAT_ANTI_PICKUP}{anti_extra}"
        )
    if any(k in text for k in ("交叉", "鞋眼")) or "穿过" in text:
        return (
            "地垫中央仅有一双粉红运动鞋共两只，两只鞋带在平放的粉鞋上交叉穿过鞋眼；"
            f"{_FLOOR_SHOE_MAT_ANTI_PICKUP}{anti_extra}"
        )
    if _daily_floor_shoe_aftermath(text):
        return (
            "地垫中央仅有一双粉红运动鞋共两只，左右并排平放接触地垫，"
            f"鞋带纠缠散乱打结难解；{_FLOOR_SHOE_MAT_ANTI_PICKUP}{anti_extra}"
        )
    return (
        "地垫中央仅有一双粉红运动鞋共两只，左右并排平放接触地垫，鞋带散开；"
        f"{_FLOOR_SHOE_MAT_ANTI_PICKUP}{anti_extra}"
    )


def _daily_floor_shoe_aftermath(vb: str) -> bool:
    """系带失败/放弃镜：鞋在垫上纠缠，无人操作。"""
    text = vb or ""
    if _daily_cancan_lifts_floor_shoes(text):
        return False
    return any(k in text for k in ("白系", "彻底", "沮丧", "叹气", "散乱"))


def _scrub_floor_shoe_wear_verbs(text: str) -> str:
    """「穿进鞋眼」易被画成往脚上套鞋，改为「穿过鞋眼」。"""
    return _FLOOR_SHOE_EYELET_RE.sub(r"穿过\1", text or "")


def _scrub_floor_shoe_hand_actions(vb: str) -> str:
    """地垫系带场面：手部动作由硬锁统一写，去掉 brief 里会诱发拿鞋/套鞋的描写。"""
    text = (vb or "").strip()
    if not text:
        return text
    text = text.replace("昭昭蹲在鞋边准备系带", "昭昭蹲在地垫旁")
    text = text.replace("昭昭蹲在鞋前", "昭昭蹲在地垫旁")
    text = text.replace("昭昭蹲在鞋边", "昭昭蹲在地垫旁")
    text = re.sub(r"指向地面上的鞋", "指向地垫上的鞋带", text)
    text = re.sub(r"指向地垫上的鞋(?!带)", "指向地垫上的鞋带", text)
    text = re.sub(r"指着鞋(?!带)", "指向地垫上的鞋带", text)
    text = re.sub(r"看向鞋(?!带)", "看向地垫上的粉鞋", text)
    text = re.sub(r"看着鞋(?!带)", "看着地垫上的粉鞋", text)
    # 指鞋/指鞋带易诱发拿鞋或套鞋，一律剥掉
    text = re.sub(
        r"(?:右手|左手)[^，。；]{0,12}(?:指向|指着)[^，。；]{0,24}",
        "",
        text,
    )
    text = re.sub(r"，左手自然下垂", "", text)
    text = re.sub(r"左手自然下垂，", "", text)
    text = _FLOOR_SHOE_HAND_SCRUB_RE.sub("", text)
    text = re.sub(r"[，,]{2,}", "，", text)
    text = re.sub(r"，(?=[；;。]|$)", "", text)
    return text.strip("，,；;。 ")


def _scrub_floor_shoe_vb_redundancy(vb: str) -> str:
    """地垫系带场面：鞋位/鞋数由硬锁统一写，去掉 brief 里重复的垫鞋描述。"""
    text = _scrub_floor_shoe_wear_verbs((vb or "").strip())
    if not text:
        return text
    for pat in (
        r"客厅地垫上，灿灿脱下的(?:粉红)?运动鞋[^，。；]*[，。；]",
        r"地垫(?:上|中央|旁)[^。；]*?(?:一双|两只)(?:粉红)?运动鞋[^。；]*[。；]",
        r"[^。；]*?灿灿脱下的(?:粉红)?运动鞋[^。；]*[。；]",
        r"[^。；]*?一双(?:粉红)?运动鞋(?:左右)?(?:两只)?并排[^。；]*[。；]",
        r"地垫上(?:只有|仅有)?(?:那双|一双)[^。；]*[。；]",
        r"[^。；]*?两只(?:粉红)?运动鞋(?:并排|串在一|贴在一)[^。；]*[。；]",
    ):
        text = re.sub(pat, "", text)
    text = re.sub(r"[，,]{2,}", "，", text)
    text = re.sub(r"[；;]{2,}", "；", text)
    text = re.sub(r"。{2,}", "。", text)
    return text.strip("，,；;。 ")


def _scrub_floor_shoe_state_conflicts(vb: str) -> str:
    """死结/拎鞋镜：去掉与鞋态矛盾的 brief（散开鞋带、重复拎鞋描写）。"""
    text = (vb or "").strip()
    if not text:
        return text
    if any(k in text for k in ("死结", "系在一起", "串在一起", "系成死", "贴在一起", "拎", "提", "翻")):
        text = re.sub(r"地垫上散落着散开的鞋带[^，。；]*[，。；]?", "", text)
        text = re.sub(r"鞋带松散(?:摇晃)?[^，。；]*[，。；]?", "", text)
    if _daily_cancan_lifts_floor_shoes(text):
        text = re.sub(
            r"灿灿[^。；]{0,16}(?:弯腰)?(?:用(?:右|左)手)?[^。；]{0,8}(?:拎|提|拎起)[^。；]{0,48}[，。；]?",
            "灿灿在地垫上，",
            text,
        )
        text = re.sub(
            r"灿灿[^。；]{0,12}双手拎起[^。；]{0,48}[，。；]?",
            "灿灿在地垫上，",
            text,
        )
        text = re.sub(r"费力地拎着鞋带[，。；]?", "", text)
        text = re.sub(r"鞋子翻了个个儿[^，。；]*[，。；]?", "", text)
        text = re.sub(
            r"两只串在一起的(?:粉红)?鞋[^，。；]*[，。；]?",
            "",
            text,
        )
        text = re.sub(
            r"两只系在一起的(?:粉红)?运动鞋[^，。；]*[，。；]?",
            "",
            text,
        )
        text = re.sub(r"鞋底紧紧贴在一起[^，。；]*[，。；]?", "", text)
        text = re.sub(r"鞋带勒出深深的印痕[^，。；]*[，。；]?", "", text)
        text = re.sub(
            r"昭昭[^。；]{0,16}蹲(?:在|于)[^，。；]{0,12}[，。；]?",
            "",
            text,
        )
        text = re.sub(
            r"昭昭[^。；]{0,20}双手(?:叉腰|摊开)[^，。；]*[，。；]?",
            "",
            text,
        )
        text = re.sub(r"抬头看着[^，。；]{0,16}[，。；]?", "", text)
        text = re.sub(r"表情惊讶[^，。；]*[，。；]?", "", text)
    text = re.sub(r"[，,]{2,}", "，", text)
    return text.strip("，,；;。 ")


def _scrub_floor_shoe_idle_actions(vb: str) -> str:
    """旁观/沮丧镜：手部与看鞋动作由硬锁写，去掉 brief 重复描写。"""
    text = (vb or "").strip()
    if not text or _daily_cancan_lifts_floor_shoes(text):
        return text
    if _daily_zhao_handles_floor_shoelaces(text):
        return text
    text = re.sub(
        r"昭昭[^。；]{0,24}双手垂在身侧[^，。；]*[，。；]?",
        "昭昭蹲在地垫旁，",
        text,
    )
    text = re.sub(r"昭昭[^。；]{0,16}低头看着[^，。；]*[，。；]?", "", text)
    text = re.sub(r"表情沮丧[^，。；]*[，。；]?", "", text)
    text = re.sub(
        r"灿灿[^。；]{0,16}站在旁边[^，。；]*[，。；]?",
        "灿灿站在地垫旁，",
        text,
    )
    text = re.sub(r"灿灿[^。；]{0,24}双手叉腰[^，。；]*[，。；]?", "", text)
    text = re.sub(r"低头看着[^，。；]*[，。；]?", "", text)
    text = re.sub(r"叹了口气[^，。；]*[，。；]?", "", text)
    text = re.sub(r"[，,]{2,}", "，", text)
    return text.strip("，,；;。 ")


def _daily_zhao_floor_shoe_watch_action(vb: str, zhao_feet: str) -> str:
    """灿灿拎鞋镜：昭昭旁观，按 brief 写叉腰/摊手/观望。"""
    text = vb or ""
    if re.search(r"昭昭[^。；]{0,24}双手摊开", text):
        return (
            f"{zhao_feet}昭昭蹲在一旁，双手摊开，表情惊讶，"
            "不碰粉鞋、不拿粉鞋、不往脚上套粉鞋。"
        )
    if re.search(r"昭昭[^。；]{0,24}双手叉腰", text):
        return (
            f"{zhao_feet}昭昭蹲在灿灿对面，双手叉腰，"
            "不碰粉鞋、不拿粉鞋、不往脚上套粉鞋。"
        )
    return (
        f"{zhao_feet}昭昭蹲在一旁抬头看着被拎起的粉鞋，"
        "双手不碰粉鞋、不拿粉鞋。"
    )


def _daily_zhao_floor_shoe_idle_action(vb: str, zhao_feet: str) -> str:
    """地垫旁观/沮丧镜：昭昭不碰鞋带，按 brief 写垂手或叉腰。"""
    text = vb or ""
    if re.search(r"昭昭[^。；]{0,24}双手垂", text):
        return (
            f"{zhao_feet}昭昭蹲在地垫旁，双手垂在身侧，"
            "低头看着地垫上的粉鞋，表情沮丧，不碰粉鞋、不拿粉鞋。"
        )
    if re.search(r"昭昭[^。；]{0,24}双手叉腰", text):
        return (
            f"{zhao_feet}昭昭蹲在地垫旁，双手叉腰，"
            "低头看着地垫上的粉鞋，不碰粉鞋、不拿粉鞋。"
        )
    return (
        f"{zhao_feet}昭昭蹲在地垫旁看着地垫上的粉鞋，"
        "双手不碰粉鞋、不拿粉鞋。"
    )


def _daily_cancan_floor_shoe_idle_clause(vb: str) -> str:
    """地垫旁观镜：灿灿站一旁，按 brief 写叉腰或垂手。"""
    text = vb or ""
    base = "灿灿赤脚仅穿白袜子站在地垫旁，脚上不穿粉运动鞋；"
    if re.search(r"灿灿[^。；]{0,24}双手叉腰", text):
        tail = "灿灿双手叉腰，低头看着地垫上的粉鞋"
        if "叹" in text:
            tail += "叹了口气"
        return base + tail + "，不拿粉鞋、不往脚上套粉鞋。"
    return base + "灿灿双手自然下垂，不拿粉鞋、不往脚上套粉鞋。"


def _daily_floor_shoe_lock(vb: str, speakers: list[str]) -> str | None:
    """地垫系带场面：灿灿粉鞋在垫上、昭昭蓝白鞋在脚上，硬锁鞋数与动作。"""
    cancan_lift = _daily_cancan_lifts_floor_shoes(vb)
    tying = _daily_zhao_handles_floor_shoelaces(vb)
    zhao_feet = "昭昭双脚均已穿好蓝白运动鞋，与地垫粉鞋是不同的一双。"
    if "昭昭" in speakers and cancan_lift:
        action = _daily_zhao_floor_shoe_watch_action(vb, zhao_feet)
    elif "昭昭" in speakers and tying:
        action = (
            f"{zhao_feet}昭昭蹲在地垫旁，双膝弯曲，"
            "双手手指只捏地垫上一双粉鞋的鞋带结；"
            "粉鞋平放垫上、鞋帮贴地，昭昭不拿起粉鞋、不往自己脚上套。"
        )
    elif "昭昭" in speakers:
        action = _daily_zhao_floor_shoe_idle_action(vb, zhao_feet)
    else:
        action = ""
    if "灿灿" in speakers and cancan_lift:
        flip = "，鞋子翻了个个儿" if any(k in vb for k in ("翻", "哗啦")) else ""
        cancan = (
            "灿灿赤脚仅穿白袜子蹲在地垫上，"
            f"双手拎着系成死结串在一起的一双粉鞋（共两只）{flip}，"
            "两只鞋底贴在一起；不往脚上套粉鞋。"
        )
    elif "灿灿" in speakers:
        cancan = _daily_cancan_floor_shoe_idle_clause(vb)
    else:
        cancan = ""
    return f"{_daily_floor_shoe_mat_clause(vb)}{action}{cancan}"


def _daily_zhao_handles_floor_shoelaces(vb: str) -> bool:
    """本镜昭昭是否在操作鞋带（非仅旁观）。"""
    text = vb or ""
    if "昭昭" not in text:
        return False
    if _daily_cancan_lifts_floor_shoes(text):
        return False
    if re.search(r"昭昭[^。；]{0,24}双手叉腰", text):
        return False
    if re.search(r"昭昭[^。；]{0,24}双手垂", text):
        return False
    if re.search(
        r"昭昭[^。；]{0,20}(?:系|穿|打|抽|捏|握|伸|抠|穿过)[^。；]{0,16}鞋带"
        r"|昭昭[^。；]{0,20}鞋眼"
        r"|昭昭[^。；]{0,12}系带"
        r"|双手伸向鞋带",
        text,
    ):
        return True
    if "握着鞋带" in text:
        head = text[: text.find("握着鞋带")]
        return "昭昭" in head[-40:]
    return False


def _daily_speakers_of(seg: dict) -> list[str]:
    """本段出场角色：发言 ∪ 台词写明在场 ∪ 粘性 speakers（优先 speakers 字段）。"""
    from app.services.daily_story.speaker import allowed_cast_from_segment

    names = allowed_cast_from_segment(seg)
    return [n for n in ("昭昭", "灿灿", "妈妈") if n in names]


def _daily_first_speaker(seg: dict) -> str | None:
    """本段第一句台词的说话角色；无台词返回 None。"""
    for d in seg.get("dialogue") or []:
        name = str(d.get("speaker") or "").strip()
        if name:
            return name
    return None


_DAILY_LR_RE = re.compile(
    r"画面左边是\s*(昭昭|灿灿|妈妈)\s*[，,；;]?\s*右边是\s*(昭昭|灿灿|妈妈)"
)
_DAILY_LCR_RE = re.compile(
    r"(?:画面)?从左到右是\s*(昭昭|灿灿|妈妈)\s*[、,，]\s*"
    r"(昭昭|灿灿|妈妈)\s*[、,，]\s*(昭昭|灿灿|妈妈)"
    r"|左边是\s*(昭昭|灿灿|妈妈)\s*[，,；;]?\s*"
    r"中间是\s*(昭昭|灿灿|妈妈)\s*[，,；;]?\s*"
    r"右边是\s*(昭昭|灿灿|妈妈)"
)


def _daily_layout_speakers(seg: dict, vb: str) -> list[str]:
    """站位：优先 visual_brief 明示；三人默认左昭中妈右灿；两人左昭右灿。

    站位角色必须 ⊆ 本段可入画 cast，避免 vb 写了三人却 cast 只有两人时
    把未授权角色拼进构图句触发质检泄漏。
    """
    allowed = set(_daily_speakers_of(seg))

    def _keep(names: list[str]) -> list[str]:
        return [n for n in names if n in allowed]

    m3 = _DAILY_LCR_RE.search(vb or "")
    if m3:
        names = _keep([g for g in m3.groups() if g])
        if len(names) == 3 and len(set(names)) == 3:
            return names
    m = _DAILY_LR_RE.search(vb or "")
    if m:
        left, right = m.group(1), m.group(2)
        pair = _keep([left, right])
        # 妈妈须离场（躲着/别让看见）或本段根本没有妈妈时，才尊重二人 brief。
        # E 类粘性三人：台词可以少、画面不能缺席，勿因 vb 只写左右把妈妈挤出构图。
        from app.services.daily_story.speaker import mom_should_stay_offscreen

        hide_mom = mom_should_stay_offscreen(seg.get("dialogue"))
        if (
            len(pair) == 2
            and pair[0] != pair[1]
            and ("妈妈" not in allowed or hide_mom)
        ):
            return pair
    speakers = _daily_speakers_of(seg)
    if set(speakers) >= {"昭昭", "灿灿", "妈妈"}:
        return ["昭昭", "妈妈", "灿灿"]
    if "昭昭" in speakers and "灿灿" in speakers:
        rest = [s for s in speakers if s not in ("昭昭", "灿灿")]
        return ["昭昭", "灿灿", *rest]
    return speakers


def _strip_style_suffix(vb: str) -> str:
    """去掉 visual_brief 末尾画风句（含风格/线条/笔触等）。"""
    vb = vb.rstrip("。，, ")
    last_period = vb.rfind("。")
    tail = vb[last_period + 1 :] if last_period >= 0 else vb
    style_context = any(w in tail for w in ("风格", "线条", "笔触", "质感", "画风"))
    if not style_context:
        return vb + "。" if vb else ""
    style_keywords = ["彩铅", "涂鸦", "蜡笔", "水彩", "油画", "扁平", "写实风", "绘本"]
    if any(kw in tail for kw in style_keywords):
        pre = vb[:last_period].rstrip("。，, ") if last_period >= 0 else ""
        if pre:
            return pre + "。"
    return vb + "。" if vb else ""


def _daily_lighting(vb: str) -> str:
    outdoor = any(
        w in vb for w in ("室外", "户外", "院子", "阳台", "楼下", "公园", "小区", "马路")
    )
    if outdoor:
        return "室外自然光，柔和散射，画面明亮。"
    return "窗光从一侧斜照，在墙面和地面投下柔和光影。"


def _daily_composition(
    shot_type: str,
    speakers: list[str],
    *,
    vb: str = "",
) -> str:
    names = [s for s in speakers if s in _DAILY_CHAR_MAP]
    look = {
        "昭昭": "蓝T恤深蓝短裤短发男孩昭昭",
        "灿灿": "粉卫衣蓝裤黑马尾女孩灿灿",
        "妈妈": "米色上衣牛仔裤黑长发妈妈",
    }
    has_lr = bool(_DAILY_LR_RE.search(vb or ""))
    has_lcr = bool(_DAILY_LCR_RE.search(vb or ""))
    if len(names) >= 3:
        a, b, c = names[0], names[1], names[2]
        lr = "" if has_lcr else f"画面从左到右是{a}、{b}、{c}。"
        if shot_type == "特写":
            return (
                f"{lr}"
                f"中近景三人特写，严格左{look.get(a, a)}、"
                f"中{look.get(b, b)}、右{look.get(c, c)}，左右位置固定不变。"
            )
        return (
            f"{lr}"
            f"中景三人同框，严格左{look.get(a, a)}、"
            f"中{look.get(b, b)}、右{look.get(c, c)}，"
            f"三人全部在场、左右位置固定不变，全身可见。"
        )
    if shot_type == "特写":
        if len(names) == 2:
            a, b = names[0], names[1]
            lr = "" if has_lr else f"画面左边是{a}，右边是{b}。"
            return (
                f"{lr}"
                f"中近景特写，严格左侧{look.get(a, a)}占左半、"
                f"右侧{look.get(b, b)}占右半，左右位置固定不变，"
                f"每人只显示2条手臂。"
            )
        return "面部特写，占画面主体，背景虚化。"
    if shot_type == "中景":
        if len(names) == 2:
            a, b = names[0], names[1]
            lr = "" if has_lr else f"画面左边是{a}，右边是{b}。"
            return (
                f"{lr}"
                f"中景，严格左{look.get(a, a)}、右{look.get(b, b)}，"
                f"左右位置固定不变，全身可见，每人只显示2条手臂。"
            )
        return "中景，人物全身，环境可见。"
    return "根据画面自然构图。"


def strip_verify_regen_leak(prompt: str) -> str:
    """去掉误拼进 T2I 的质检/内容策略改写元指令（历史污染 / 兜底）。"""
    text = (prompt or "").strip()
    cut = -1
    for marker in ("出图质检连续未通过", "出图被内容策略拦截"):
        idx = text.find(marker)
        if idx >= 0 and (cut < 0 or idx < cut):
            cut = idx
    if cut < 0:
        return text
    return text[:cut].rstrip(" \n\t")


def _strip_vb_narrative_continuity(vb: str) -> str:
    """去掉会诱导模型画多格/多角色的叙事延续词，只留当前单幅画面。"""
    text = (vb or "").strip()
    for phrase in (
        "接上一镜，场景同前",
        "接上一镜",
        "场景同前",
        "背景同分镜1",
        "背景同设定",
        "同上",
        "全片为同一场景连续发生的同一故事",
        "仅动作、表情与道具状态变化",
    ):
        text = text.replace(phrase, "")
    text = re.sub(r"[，,]\s*[。.]", "。", text)
    text = re.sub(r"，\s*，", "，", text)
    return text.strip("，,。. ")


def assemble_daily_t2i_prompt(
    seg: dict,
    *,
    extra: str | None = None,
    scene_anchor: str | None = None,
    fixed_furniture: tuple[str, ...] | None = None,
    setting: str | None = None,
) -> str:
    """规则拼装 daily_story image_prompt。

    风格 + visual_brief + 出场角色外貌 + 光照 + 构图。
    extra 仅用于显式附加的出图正文（勿传入质检/改写元指令）。
    """
    vb = str(seg.get("visual_brief") or "").strip()
    idx = int(seg.get("segment_index") or 0)
    has_scene_anchor = False
    speakers = _daily_speakers_of(seg)
    if vb:
        from app.services.daily_story.speaker import (
            scrub_leaked_speaker_names,
            scrub_offscreen_doorway_cues,
        )
        from app.services.script.visual_brief import scrub_daily_visual_brief

        vb = scrub_daily_visual_brief(vb)
        vb = strip_verify_regen_leak(vb)
        vb = scrub_leaked_speaker_names(vb, set(speakers))
        vb = scrub_offscreen_doorway_cues(vb, allowed=set(speakers))
        # 默认陈设只在首镜保留：非首镜去除重复的「茶几上放着遥控器和空水杯」
        if int(seg.get("segment_index") or 0) > 1:
            vb = re.sub(r"[，,]\s*茶几上放着遥控器和空水杯\s*", "", vb)
            vb = vb.replace("茶几上放着遥控器和空水杯", "").strip("，, ")
        vb = _strip_vb_narrative_continuity(vb)
        # LLM 已写「场景定稿」时去掉标签；代码只在缺失时兜底注入
        has_scene_anchor = "场景定稿" in vb
        if has_scene_anchor:
            vb = vb.replace("场景定稿：", "").strip("，,。. ")
    else:
        vb = strip_verify_regen_leak(vb)
    shot = str(seg.get("shot_type") or "").strip()
    floor_shoe_scene = _daily_setting_floor_shoe_scene(setting)
    vb_for_shoe_lock = vb
    if floor_shoe_scene and vb:
        vb = _scrub_floor_shoe_vb_redundancy(vb)
        vb = _scrub_floor_shoe_state_conflicts(vb)
        vb = _scrub_floor_shoe_hand_actions(vb)
        vb = _scrub_floor_shoe_idle_actions(vb)

    parts = [_DAILY_T2I_STYLE]
    if vb:
        parts.append(_strip_style_suffix(vb))
        # 拼装硬锁：门只允许单扇（单开门），风吹头发必须连着头皮，
        # 不依赖 LLM 是否照写规则，防止双开门/独立飘发进入最终提示词
        if "门" in vb and "完整门板" not in vb:
            parts.append(
                "画面中的门是一扇单开门，只有一块完整门板，没有分成两扇。"
            )
        if ("风" in vb or "吹" in vb) and ("头发" in vb or "马尾" in vb):
            if "连着头皮" not in vb:
                parts.append("发丝连着头皮。")
            if "门" in vb and not any(
                w in vb for w in ("背离", "飘离门口", "远离门")
            ):
                parts.append("风从门口吹向室内，头发顺风飘离门口。")

    # 场景定稿：分镜1定义地点/陈设/样式，后续镜缺省时原样注入；
    # LLM 已重复场景时（含花盆/托盘/背景）不再重复注入
    has_scene = all(k in vb for k in ("花盆", "托盘", "背景"))
    if scene_anchor and idx > 1 and not has_scene_anchor and not has_scene:
        parts.append(scene_anchor)

    # 固定陈设强制在场：分镜1 出现过的家具/常驻道具，本镜缺失时补回，
    # 防出图质检兜底重写 visual_brief 时把沙发/茶几等固定家具写丢
    if fixed_furniture:
        missing = [f for f in fixed_furniture if f not in vb]
        if missing:
            parts.append("画面中有" + "、".join(missing) + "。")

    char_parts: list[str] = []
    for name in speakers:
        if name == "昭昭" and floor_shoe_scene:
            char_parts.append(_DAILY_CHAR_ZHAO_FLOOR)
        elif name == "灿灿" and floor_shoe_scene:
            char_parts.append(_DAILY_CHAR_CANCAN_SOCKS)
        elif name in _DAILY_CHAR_MAP:
            char_parts.append(_DAILY_CHAR_MAP[name])
    if set(speakers) >= {"昭昭", "灿灿", "妈妈"}:
        char_parts.append(_DAILY_CHAR_HEIGHT_3)
    elif "昭昭" in speakers and "灿灿" in speakers:
        char_parts.append(_DAILY_CHAR_HEIGHT)
    if char_parts:
        parts.append("".join(char_parts))

    # 发色硬锁紧跟角色块：句末权重最低，写在末尾等于没写（实测彩色化）
    if "灿灿" in speakers:
        parts.append(_DAILY_CANCAN_HAIR_LOCK)

    if floor_shoe_scene and speakers:
        lock = _daily_floor_shoe_lock(vb_for_shoe_lock, speakers)
        if lock:
            parts.append(lock)

    # 嘴型锁定：先开口说话的孩子在静帧里必须处于说话状态，
    # 其余人完全闭嘴，防止 I2V 说话人反转
    first = _daily_first_speaker(seg)
    if first and first in speakers:
        others = [n for n in speakers if n != first]
        mouth = f"{first}正在开口说话"
        if others:
            mouth += (
                f"；{'、'.join(others)}嘴巴自然闭合，情绪通过眉眼和肢体表达"
            )
        parts.append(mouth + "。")

    parts.append(_daily_lighting(vb))
    layout = _daily_layout_speakers(seg, vb)
    parts.append(_daily_composition(shot, layout, vb=vb))
    # 妈妈未入画时硬锁人数+空门口，压住「妈出来了/盯门口」诱出的路人
    if speakers and "妈妈" not in speakers:
        n = len(speakers)
        if n == 2:
            parts.append(f"画面主体为{'、'.join(speakers)}两人。")
        elif n == 1:
            parts.append(f"画面主体为{speakers[0]}一人。")
        else:
            parts.append(f"画面主体为{'、'.join(speakers)}。")
    if extra and extra.strip():
        # 禁止把质检元指令当出图正文
        cleaned = strip_verify_regen_leak(extra.strip())
        if cleaned and cleaned != extra.strip():
            cleaned = ""
        if cleaned:
            parts.append(cleaned)
    from app.services.script.visual_brief import strip_held_prop_from_surface

    return strip_held_prop_from_surface("".join(parts))


def assemble_daily_image_prompts(
    segments: list[dict],
    *,
    segment_indices: list[int] | None = None,
    extra: str | None = None,
    setting: str | None = None,
) -> list[dict]:
    """原地为 daily 分镜写入规则拼装的 image_prompt。"""
    from app.services.daily_story.speaker import annotate_sticky_stage_speakers

    annotate_sticky_stage_speakers(segments, setting=setting)
    from app.services.script.visual_brief import (
        _daily_fixed_furniture,
        _resolve_prop_state_regression,
        daily_locked_inventory,
        scrub_daily_visual_brief,
        strip_unlocked_inventory,
    )

    # 跨镜状态保护：已落地的冲突道具不得在后续镜写回家具台面
    # （覆盖出图质检兜底重写 visual_brief 的路径）
    _resolve_prop_state_regression(segments)
    locked = daily_locked_inventory(segments, setting)
    for seg in segments:
        vb = str(seg.get("visual_brief") or "")
        cleaned = strip_unlocked_inventory(scrub_daily_visual_brief(vb), locked)
        if cleaned != vb:
            seg["visual_brief"] = cleaned
    fixed_furniture = _daily_fixed_furniture(segments)
    # 分镜1 的场景定稿句：含花盆/托盘/背景/阳台且不含角色的句子
    scene_anchor = ""
    for seg in segments:
        if int(seg.get("segment_index") or 0) != 1:
            continue
        vb1 = str(seg.get("visual_brief") or "")
        sentences = [
            s.strip()
            for s in re.split(r"(?<=[。；;])", vb1)
            if s.strip()
        ]
        anchor_sents = [
            s
            for s in sentences
            if any(k in s for k in ("花盆", "托盘", "背景", "阳台"))
            and not any(n in s for n in ("昭昭", "灿灿", "妈妈"))
        ]
        scene_anchor = "".join(anchor_sents).replace(
            "场景定稿：", ""
        ).strip("，,。. ")
        break
    wanted = (
        {int(i) for i in segment_indices} if segment_indices is not None else None
    )
    for seg in segments:
        idx = int(seg.get("segment_index") or 0)
        if wanted is not None and idx not in wanted:
            continue
        seg["image_prompt"] = assemble_daily_t2i_prompt(
            seg,
            extra=extra,
            scene_anchor=scene_anchor,
            fixed_furniture=fixed_furniture,
            setting=setting,
        )
    return segments


def wrap_image_prompts(
    segments: list[dict],
    *,
    content_style: str | None = None,
    extra: str | None = None,
    setting: str | None = None,
    segment_indices: list[int] | None = None,
) -> list[dict]:
    """按 content_style 定稿 image_prompt。

    daily_story：规则拼装（风格+visual_brief+外貌+光照+构图），不依赖 LLM 扩写。
    setting 须从 script 带入，供同场粘性入画；勿只传 segments。
    其他风格：无额外 wrap。
    """
    if content_style == CONTENT_STYLE_DAILY_STORY:
        return assemble_daily_image_prompts(
            segments,
            extra=extra,
            setting=setting,
            segment_indices=segment_indices,
        )
    return segments


_IMAGE_PROMPT_DIMENSIONS_FULL = (
    "篇幅150-300字，连贯中文，禁用维度标签。"
    "按风格→主体→场景→光照→构图→一致性→质量顺序："
    "①视觉风格（遵循 visual_style 定调，置于句首）；"
    "②主体（角色须写年龄/发型/脸型/服装/身高体型等外貌特征，与 visual_style 主角描述一致；表情扩张力、姿态、动作，至少2句细节）；"
    "③场景（前景/中景/背景，写至少 2 个具体物品；"
    "画面含门时须写明「一扇单开门」（单扇门：只有一块完整门板，没有分成两扇），"
    "门外是柔和的白色亮光）；"
    "④光照（主辅光方向、冷暖色调、明暗对比）；⑤构图（景别、占比、留白）；"
    "⑥视觉连续性（同场景多镜时，主体外貌/服装/发型须与相邻镜一致，"
    "场景主要陈设与空间位置不跳变，光照方向与色温保持统一；"
    "仅根据本镜景别调整构图与细节重点，不改变已建立的视觉元素）；"
    "⑦写材质纹理光影层次，禁4K/8K/分辨率套话与空话。"
    "【约束】仅单帧静态，禁连续运动/时间推移，动态只放 motion_prompt；"
    "仅表达本段 text 与 visual_brief，但须与相邻镜共享的背景元素保持一致。"
    "【时间约束】禁止使用「先是…接着…」「然后」「镜头切至」等描述时间推移或镜头切换的词语；整段仅描述一帧静态画面。"
    "【逐段自检】每段 image_prompt 须独立覆盖全部七维，逐段对照七维清单自查，缺则补写，禁止省略任何维度。"
    "其中⑥视觉连续性须对照邻镜检查主体外貌/场景陈设/光照是否统一。"
    "【长度】若不足 150 字，需补充主体细节（外貌/姿态）、场景陈设、光照方向/色温或构图说明；不凑字数，按画面复杂度自然充分描述。"
)

# 各风格正文：画风细节只跟 visual_style；规则只写约束与结构，用 {orientation} 占位
_IMAGE_PROMPT_RULE_SCIENCE = (
    "image_prompt须严格遵循 visual_style 字段中已定义的全片画风定调，"
    "不修改、不替换 visual_style 的内容，直接按其原文描述生成；"
    "非绘本水彩、非电影级写实摄影，适配{orientation}构图。"
    + _IMAGE_PROMPT_DIMENSIONS_FULL
)

_IMAGE_PROMPT_RULE_REALISTIC = (
    "image_prompt须严格遵循 visual_style 字段中已定义的全片画风定调，"
    "不修改、不替换 visual_style 的内容，直接按其原文描述生成，适配{orientation}构图。"
    + _IMAGE_PROMPT_DIMENSIONS_FULL
)

_IMAGE_PROMPT_RULE_LIFE = (
    "image_prompt须严格遵循 visual_style 字段中已定义的全片画风定调，"
    "不修改、不替换 visual_style 的内容，直接按其原文描述生成，适配{orientation}构图。"
    + _IMAGE_PROMPT_DIMENSIONS_FULL
    + "另禁可读大段文字/水印/品牌Logo。"
)

# daily_story：image_prompt 由规则拼装，LLM 只写 motion
_IMAGE_PROMPT_RULE_DAILY_STORY_MOTION = (
    "适配{orientation}构图。"
    "image_prompt 已由系统按「风格+visual_brief+角色外貌+光照+构图」规则拼装，"
    "禁止改写、禁止再输出 image_prompt 字段。"
    "仅为每段编写 motion_prompt，须紧扣已给出的 image_prompt。"
)


# 与 quality.image_prompt / user 一致：禁人物主动作，只写环境/物体微动
_IMAGE_PROMPT_MOTION_TAIL = (
    "【motion_prompt】中文，40-200字，上限 600 字，紧扣 image_prompt 已出现的具体物体与场景。"
    "只写画面内无生命元素在约10秒内的细微物理变化（烟、水、光影、尘埃、火焰、布料等），"
    "须有方向、速度、幅度等细节，禁模糊词；末尾说明哪些主体保持稳定。"
    "镜头仅可极缓推近/拉远/平移。"
    "禁止写人物或任何有生命主体的动作/神态；"
    "禁抽象特效词（光效、光晕、粒子、能量、光圈、脉动、闪电、闪烁、图标、UI元素等）与镜头套话。"
    "正例：丹炉炉盖被蒸汽顶起又落下，缝隙中白烟成股涌出向右飘散，丹炉整体位置与造型保持不变。"
    "反例：小偷手指微微弯曲。（人物肢体动作，禁止）"
)

_IMAGE_PROMPT_MOTION_TAIL_DAILY_AMBIENT = (
    "【ambient】40-200字，上限 600 字，只能从本段 image_prompt 已明确出现的无生命物体中"
    "选 1-2 个写微动（如纱帘、遥控器、空水杯、蛋糕奶油高光）；"
    "禁止新造画面外物体（如蛋糕盒、丝带、蜡笔屑、灰尘、水渍）；"
    "须写方向、速度、幅度细节，但幅度用「轻微/极小」等相对词，禁止写具体厘米/角度数字；"
    "禁人物/有生命体动作；末尾须写「人物姿势保持不变」。"
    "正例：窗边纱帘被风轻轻掀起又落下，窗帘下摆轻微向右飘动后回摆，人物姿势保持不变。"
)

_IMAGE_PROMPT_MOTION_TAIL_DAILY_KEYFRAME = (
    "【keyframe】按以下模板输出 motion_prompt（120-280 字）：\n"
    "【站位】必须与本段 image_prompt 构图句一致，禁止自行改成两人：\n"
    "若 image_prompt 有「画面从左到右是A、B、C」或"
    "「左边是A，中间是B，右边是C」，开头必须抄这句三人站位；"
    "未说话的中间人（常为妈妈）也要写进站位，并补"
    "「{中间人}保持静图姿势，全程在画面内，不消失」。\n"
    "若只有「画面左边是A，右边是B」，则抄二人站位：画面左边是{角色A}，右边是{角色B}。\n"
    "【说话句】必须按本段 dialogue 顺序，每一句台词各写一行"
    "「{该句说话人}说话，同时{微动作}后停止」；"
    "句间格式完全相同，微动作须贴合本镜画面；"
    "同人说多句就要写多行，禁止合并、漏句或打乱对白顺序。"
    "禁止写「后定格」（末句由系统在 TTS 后改为定格）。\n"
    "【动作限幅】说话人只动嘴+一个幅度极小（不超过手指长度）的手部/头部微动作；"
    "身体姿态、站姿、头部朝向保持不变；"
    "禁止写具体厘米/角度数字，禁止「身体前倾幅度增大」「双手叉腰撑开」「大幅耸肩」等动作；"
    "非说话方保持静图姿势，不写主动作。\n"
    "站位左右/中间禁止与 image_prompt 对调。\n"
    "【时间轴】禁止自编起止秒数；写成「{角色}说话，同时…」即可，"
    "出片前系统按 TTS 句时长自动写入「X.X-Y.Y秒」。\n"
    "有台词角色必须含「说话，同时」；无台词角色可不写「说话，同时」，只写微动作。\n"
    "【收束表情】可选。若写，以「两人说话后面部表情恢复与静图一致：」起头；"
    "每位角色的神态须贴合本镜剧情与 visual_brief（如质问、委屈、赌气），"
    "两人可不同，禁止无差别套「无辜状」；第二人可用「表情不变」表相对静图。"
    "若不写收束段，须保证 image_prompt 已定格表情，motion 侧重说话与肢体即可。\n"
    "【锁定】服装发型稳定，身高比例（{角色B}比{角色A}矮半个头）不变。\n"
    "镜头固定，不推近不拉远，画面只有人物和场景，无任何文字叠加。\n"
    "禁止镜头推近/推进/拉远/变焦/放大；禁止大位移换位、全身换姿势、多人齐跑、抽象光效。\n"
    "出片前系统按 TTS 将说话句改为"
    "「X.X-Y.Y秒左侧女孩/右侧男孩开口说话，口型自然开合，说完即闭嘴…"
    "此时…嘴巴闭合不动」，并把收束表情段替换为嘴唇锁定句。\n"
    "正例（dialogue 三句：灿灿→昭昭→灿灿）：\n"
    "画面左边是灿灿，右边是昭昭。"
    "灿灿说话，同时右手食指微微向下点动约2厘米后停止；"
    "昭昭说话，同时肩膀轻轻耸起约3厘米后停止；"
    "灿灿说话，同时下巴微微抬起约1厘米后停止。"
    "两人说话后面部表情恢复与静图一致："
    "灿灿瞪圆眼睛嘴巴大张（惊讶质问状），不微笑；"
    "昭昭撇着嘴角耸肩（无辜状），表情不变。"
    "服装发型稳定，身高比例（昭昭比灿灿矮半个头）不变。"
    "镜头固定，不推近不拉远，画面只有人物和场景，无任何文字叠加。\n"
    "反例：0.0-1.5秒灿灿说话…（禁止自编秒数）；"
    "只写两句说话但 dialogue 有三句（漏句）；"
    "灿灿右手点动持续0.5秒（缺「说话，同时」，系统无法注入时间）；"
    "静图三人同框却只写「画面左边是昭昭，右边是灿灿」（漏中间人，出片易把边上人吃掉）。\n"
)

_IMAGE_PROMPT_MOTION_TAIL_DAILY = (
    "【motion_prompt 分流】按该段 motion_mode 选择规则："
    "motion_mode=ambient（默认）→"
    + _IMAGE_PROMPT_MOTION_TAIL_DAILY_AMBIENT
    + "motion_mode=keyframe（特写/i2v 关键帧）→"
    + _IMAGE_PROMPT_MOTION_TAIL_DAILY_KEYFRAME
)

_IMAGE_PROMPT_RULE_SD15 = (
    "【SD1.5】另输出 sd15_prompt_en：篇幅精简的英文提示（20～40词），"
    "实际 SD1.5 出图以 sd15_prompt_en 为准；image_prompt 仍用中文保留六维信息供校对。"
)

_IMAGE_PROMPT_RULE_MYSTERY = (
    "image_prompt须严格遵循 visual_style 字段中已定义的全片画风定调，"
    "不修改、不替换 visual_style 的内容，直接按其原文描述生成，适配{orientation}构图；"
    "禁止卡通/绘本/扁平插画风。"
    + _IMAGE_PROMPT_DIMENSIONS_FULL
    + "另禁可读文字、奏折、诏书等文字元素。"
)

_SD15_PROMPT_EN_RULE = (
    "同时为每段输出 sd15_prompt_en：专为 Stable Diffusion 1.5 优化的英文提示词（20～40 词），"
    "格式为「[核心主体] [动作/状态], [场景类型], [一个关键视觉特征]」；"
    "根据 visual_brief 画面描述确定主体方向，再提炼主体；"
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


# ── JSON 样例 ─────────────────────────────────────────────────────

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
      "image_prompt": """ + _IMAGE_PROMPT_JSON_EXAMPLE_TEXT + """,
      "motion_prompt": "炉口青烟缓缓上升，火光轻闪，镜头极缓推进",
      "sd15_prompt_en": "bronze alchemy furnace with green flame, close-up, dark workshop"
    }
  ]
}"""

_IMAGE_PROMPTS_JSON_EXAMPLE_NO_SD15 = """{
  "image_prompts": [
    {
      "segment_index": 1,
      "image_prompt": """ + _IMAGE_PROMPT_JSON_EXAMPLE_TEXT + """,
      "motion_prompt": "炉口青烟缓缓上升，火光轻闪，镜头极缓推进"
    }
  ]
}"""

_IMAGE_PROMPTS_JSON_EXAMPLE_DAILY_MOTION = """{
  "image_prompts": [
    {
      "segment_index": 1,
      "motion_prompt": "窗边纱帘被微风掀起下摆向右飘动约10厘米后缓缓回摆，沙发靠垫绒面光影随帘动明暗交替，地毯蜡笔屑被气流吹动向前翻滚半圈停下，人物姿势保持不变"
    },
    {
      "segment_index": 2,
      "motion_prompt": "画面左边是灿灿，右边是昭昭。灿灿说话，同时右手食指微微向下点动约2厘米后停止；昭昭说话，同时肩膀轻轻耸起约3厘米后停止。两人说话后面部表情恢复与静图一致：灿灿瞪圆眼睛嘴巴大张（惊讶质问状），不微笑；昭昭撇着嘴角耸肩（委屈不服状），表情不变。服装发型稳定，身高比例（昭昭比灿灿矮半个头）不变。镜头固定，不推近不拉远，画面只有人物和场景，无任何文字叠加。"
    }
  ]
}"""


# ── builders（常量须在上方）───────────────────────────────────────

from app.services.script.prompt_common import (  # noqa: E402
    append_supplementary_to_user,
    json_output_clause,
    prompt_step,
    resolve_script_profile,
)


def _orientation_label(orientation: str) -> str:
    """横竖屏文案统一：9:16竖屏 / 16:9横屏。"""
    if orientation == ORIENTATION_LANDSCAPE:
        return "16:9横屏"
    return "9:16竖屏"


def _with_orientation(template: str, orientation: str) -> str:
    return template.format(orientation=_orientation_label(orientation))


_IMAGE_PROMPT_ROLES: dict[str, str] = {
    CONTENT_STYLE_HISTORICAL_MYSTERY: "你是历史悬案视频文生图与运动提示词专家。",
    CONTENT_STYLE_SCIENCE_CHILD: "你是童趣科普视频文生图与运动提示词专家。",
    CONTENT_STYLE_TECH_SCIENCE: "你是科技/产业科普视频文生图与运动提示词专家。",
    CONTENT_STYLE_LIFE_EXPERIENCE: "你是生活避坑/经验类视频文生图与运动提示词专家。",
    CONTENT_STYLE_DAILY_STORY: "你是儿童日常故事视频文生图与运动提示词专家。",
}

_IMAGE_PROMPT_STYLE_BODIES: dict[str, str] = {
    CONTENT_STYLE_DAILY_STORY: _IMAGE_PROMPT_RULE_DAILY_STORY_MOTION,
    CONTENT_STYLE_HISTORICAL_MYSTERY: _IMAGE_PROMPT_RULE_MYSTERY,
    CONTENT_STYLE_LIFE_EXPERIENCE: _IMAGE_PROMPT_RULE_LIFE,
    CONTENT_STYLE_SCIENCE_CHILD: _IMAGE_PROMPT_RULE_SCIENCE,
}

_MAP_COMPLIANCE = (
    "【地图合规】image_prompt禁止出现「世界地图」「全球地图」字样；"
    "地图场景必须限定为局部区域地图（如中东地图、非洲地图），"
    "不得出现完整世界地图或包含东亚/中国部分的画面。"
)

_MOTION_USER_RULE = (
    "motion_prompt 必须紧扣本段 image_prompt 中已出现的具体物体，从中选 1-2 个写其细微动态，"
    "禁止写人物或任何有生命主体的动作，禁止脱离画面编造元素，各段互不重复，禁止套话。"
)

_MOTION_USER_RULE_DAILY = (
    "motion_prompt 须按该段 motion_mode："
    "ambient 只能从本镜 image_prompt 已出现的无生命物体中选 1-2 个写微动，"
    "禁止新造画面外物体，末尾写人物姿势保持不变；"
    "keyframe 写成「{角色}说话，同时…」微动作并锁住面部表情与静图一致（不微笑），"
    "说话人身体姿态/站姿/头部朝向保持不变，动作幅度极小，禁止写具体厘米/角度；"
    "禁止自编起止秒数（系统按 TTS 注入），"
    "末尾镜头固定不推近不拉远（禁止变焦放大），禁大位移、禁纯环境晃动套话；"
    "各段互不重复，禁止套话。"
)


def _image_prompt_role(content_style: str) -> str:
    return _IMAGE_PROMPT_ROLES.get(
        content_style,
        "你是视频文生图与运动提示词专家。",
    )


def image_prompt_rule(*, orientation: str, content_style: str, sd15_mode: bool = False) -> str:
    """按 content_style / orientation 选择文生图规则；sd15 仅附加，不替换风格正文。"""
    if content_style == CONTENT_STYLE_DAILY_STORY:
        # daily：image_prompt 规则拼装，LLM 只写 motion
        text = (
            "根据每段已拼装的 image_prompt 与口播，仅为 video 编写 motion_prompt。"
            + _with_orientation(_IMAGE_PROMPT_RULE_DAILY_STORY_MOTION, orientation)
            + _IMAGE_PROMPT_MOTION_TAIL_DAILY
        )
        return text
    head = (
        "根据每段口播text、visual_brief与全片visual_style，扩写为文生图用的image_prompt"
        "和video用的motion_prompt。"
    )
    # tech_science 等未单独列出的风格走电影级写实
    body = _IMAGE_PROMPT_STYLE_BODIES.get(content_style, _IMAGE_PROMPT_RULE_REALISTIC)
    motion = _IMAGE_PROMPT_MOTION_TAIL
    text = head + _with_orientation(body, orientation) + motion
    if sd15_mode:
        text += _IMAGE_PROMPT_RULE_SD15
    return text


def _format_segment_brief(
    seg: dict,
    *,
    prefix: str = "",
    include_speakers: bool = False,
    mark_motion_mode: bool = False,
    include_image_prompt: bool = False,
) -> str:
    line = (
        f"{prefix}segment {seg.get('segment_index')}: "
        f"text={seg.get('text', '')!r}; visual_brief={seg.get('visual_brief', '')!r}"
    )
    if include_speakers:
        speakers = sorted(
            {
                str(d.get("speaker") or "").strip()
                for d in (seg.get("dialogue") or [])
                if str(d.get("speaker") or "").strip()
            }
        )
        line += f"; speakers={speakers!r}"
    if include_image_prompt:
        line += f"; image_prompt={seg.get('image_prompt', '')!r}"
    if mark_motion_mode:
        from app.utils.job_info import is_keyframe_segment

        mode = "keyframe" if is_keyframe_segment(seg) else "ambient"
        line += f"; motion_mode={mode}"
        dur = seg.get("duration_sec")
        if dur is not None:
            try:
                line += f"; duration_sec={float(dur):.1f}"
            except (TypeError, ValueError):
                pass
    return line


def _collect_segment_prompt_lines(
    segments: list[dict],
    segment_indices: list[int] | None,
    *,
    include_speakers: bool = False,
    mark_motion_mode: bool = False,
    include_image_prompt: bool = False,
) -> tuple[list[str], set[int] | None]:
    """拼装分镜行；返回 (lines, wanted)。wanted 为 None 表示全量生成。"""
    if segment_indices is None:
        return [
            _format_segment_brief(
                seg,
                include_speakers=include_speakers,
                mark_motion_mode=mark_motion_mode,
                include_image_prompt=include_image_prompt,
            )
            for seg in segments
        ], None

    wanted = {int(idx) for idx in segment_indices}
    # 目标段前后各留一段作上下文，便于 LLM 把握连贯性
    extra: set[int] = set()
    for idx in wanted:
        if idx - 1 >= 1:
            extra.add(idx - 1)
        if idx + 1 <= len(segments):
            extra.add(idx + 1)
    extra -= wanted
    shown = wanted | extra

    lines: list[str] = []
    for seg in segments:
        idx = int(seg.get("segment_index", 0))
        if idx not in shown:
            continue
        tag = "【仅上下文】" if idx in extra else "【需生成】"
        lines.append(
            _format_segment_brief(
                seg,
                prefix=tag,
                include_speakers=include_speakers,
                mark_motion_mode=mark_motion_mode,
                include_image_prompt=include_image_prompt,
            )
        )
    return lines, wanted


def _has_mom_speaker(segments: list[dict], wanted: set[int] | None) -> bool:
    for seg in segments:
        idx = int(seg.get("segment_index", 0))
        if wanted is not None and idx not in wanted:
            continue
        if any(d.get("speaker") == "妈妈" for d in (seg.get("dialogue") or [])):
            return True
    return False


def _coverage_clause(*, partial: bool) -> str:
    if partial:
        return (
            "image_prompts仅需输出标记为【需生成】的segment，"
            "【仅上下文】分段无需输出。"
        )
    return "image_prompts须覆盖输入的每一段，segment_index一一对应，不得遗漏。"


def _user_tail(*, include_sd15_prompt: bool, content_style: str | None = None) -> str:
    if content_style == CONTENT_STYLE_DAILY_STORY:
        return (
            "\n\n请仅为每段编写 motion_prompt，不要输出 image_prompt。"
            + _MOTION_USER_RULE_DAILY
        )
    motion_rule = _MOTION_USER_RULE
    if include_sd15_prompt:
        head = (
            "请为每段编写 image_prompt 与 motion_prompt。"
            "image_prompt 按本风格规则写成一段连贯中文，勿用维度标签，不写分辨率套话。"
        )
        tail = "同时为每段输出准确的 sd15_prompt_en。"
    else:
        head = (
            "请为每段扩写 image_prompt 与 motion_prompt。"
            "image_prompt 按本风格规则写成一段连贯中文（勿用「主体：」等标签），"
            "篇幅按画面复杂度充分写，不凑字数、不写4K/8K/分辨率等规格套话。"
        )
        tail = ""
    return "\n\n" + head + motion_rule + tail


def _build_system_prompt(
    *,
    content_style: str,
    orientation: str,
    include_sd15_prompt: bool,
    has_mom: bool,
    partial: bool,
) -> str:
    _ = has_mom  # daily 外貌已在规则拼装；其它风格不再注入妈妈补充例
    is_daily = content_style == CONTENT_STYLE_DAILY_STORY
    if is_daily:
        fields = "、motion_prompt"
        role = "你是儿童日常故事视频运动提示词专家。"
    elif include_sd15_prompt:
        fields = "、image_prompt、motion_prompt 与 sd15_prompt_en"
        role = _image_prompt_role(content_style)
    else:
        fields = "、image_prompt 与 motion_prompt"
        role = _image_prompt_role(content_style)
    parts = [
        f"{role}输出JSON，字段：image_prompts。",
        f"image_prompts为数组，每项含segment_index{fields}。",
    ]
    if not is_daily:
        parts.append(
            "【全局视觉锚点】生成前先通读全片 visual_style 与 setting，"
            "确定贯穿全片的视觉常量，确保相邻分镜画面衔接自然、视觉元素统一：\n"
            "A. 主角标准外貌（年龄/发型/脸型/服装/身高体型），各镜人物描述保持一致；\n"
            "B. 场景空间关系（房间布局、门窗位置、主要家具陈设），"
            "同场景连续镜中背景元素不跳变、不凭空出现或消失；\n"
            "C. 主光源方向与色调（窗光/顶灯/自然光及其方向、冷暖基调），"
            "同场景光照逻辑统一。\n"
            "每段 image_prompt 在七维展开时须以此为基准，"
            "多镜同场景时仅根据景别变化调整构图与细节重点，"
            "不改变已建立的视觉元素。"
        )
    parts.append(
        image_prompt_rule(
            orientation=orientation,
            content_style=content_style,
            sd15_mode=include_sd15_prompt and not is_daily,
        ),
    )
    if include_sd15_prompt and not is_daily:
        parts.append(_SD15_PROMPT_EN_RULE)
    parts.append(_coverage_clause(partial=partial))
    if content_style != CONTENT_STYLE_DAILY_STORY:
        parts.append(_MAP_COMPLIANCE)
    if is_daily:
        json_example = _IMAGE_PROMPTS_JSON_EXAMPLE_DAILY_MOTION
    elif include_sd15_prompt:
        json_example = _IMAGE_PROMPTS_JSON_EXAMPLE
    else:
        json_example = _IMAGE_PROMPTS_JSON_EXAMPLE_NO_SD15
    parts.append(json_output_clause(json_example))
    return "".join(parts)


def _build_user_prompt(
    script: dict[str, Any],
    *,
    lines: list[str],
    include_sd15_prompt: bool,
    supplementary_info: str | None,
    feedback: str | None,
    content_style: str | None = None,
) -> str:
    setting = str(script.get("setting") or "").strip()
    setting_line = f"全片地点 setting：{setting}\n" if setting else ""
    is_daily = content_style == CONTENT_STYLE_DAILY_STORY
    anchor_hint = (
        ""
        if is_daily
        else (
            "【视觉一致性要求】同场景相邻分镜须保持主体外貌/场景陈设/光照方向一致，"
            "仅根据景别调整构图与细节重点。请先生成全片视觉锚点（主角标准外貌、场景空间关系、主光源），"
            "再逐镜以此展开。\n\n"
        )
    )
    user = append_supplementary_to_user(
        (
            f"视频标题：{script.get('title', '')}\n"
            f"{setting_line}"
            f"全片画风定调 visual_style：{script.get('visual_style', '')}\n"
            f"{anchor_hint}"
            "各分镜口播与画面描述：\n"
            + "\n".join(lines)
            + _user_tail(
                include_sd15_prompt=include_sd15_prompt,
                content_style=content_style,
            )
        ),
        supplementary_info or script.get("supplementary_info"),
    )
    if feedback:
        user += f"\n\n上次不合格：{feedback}。请按要求重写。"
    return user


def build_image_prompts(
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
    profile_orientation, profile_style = resolve_script_profile(
        job,
        orientation=orientation,
        content_style=content_style,
    )
    segments = script.get("segments") or []
    is_daily = profile_style == CONTENT_STYLE_DAILY_STORY
    lines, wanted = _collect_segment_prompt_lines(
        segments,
        segment_indices,
        include_speakers=is_daily,
        mark_motion_mode=is_daily,
        include_image_prompt=is_daily,
    )
    system = _build_system_prompt(
        content_style=profile_style,
        orientation=profile_orientation,
        include_sd15_prompt=include_sd15_prompt,
        has_mom=_has_mom_speaker(segments, wanted),
        partial=wanted is not None,
    )
    user = _build_user_prompt(
        script,
        lines=lines,
        include_sd15_prompt=include_sd15_prompt,
        supplementary_info=supplementary_info,
        feedback=feedback,
        content_style=profile_style,
    )
    return prompt_step("image_prompts", system, user)
