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

# 有角色参考图时置于句首；结尾「孩子气的构图。」供质检剥离前缀
_DAILY_T2I_STYLE = (
    "基于参考图调整人物动作，保持参考图外貌，"
    "保留昭昭与灿灿的外貌、发型、服装与身高比例，"
    "只改本镜动作、表情与道具状态。"
    "儿童涂鸦蜡笔画风格，粗黑轮廓线，彩铅蜡笔涂色质感，"
    "涂色出界，手绘感，童真插画。"
    "孩子气的构图。"
)
# 风格只在末尾钉一次（正面表述，无负向禁词）
_DAILY_T2I_STYLE_LOCK_TAIL = (
    "儿童涂鸦蜡笔绘本风格，粗黑轮廓线，彩铅涂色出界，手绘童真，与参考图同质。"
)

_DAILY_CHAR_ZHAO = (
    "昭昭：7岁男孩，黑色超短发露耳露后颈，圆脸，"
    "蓝色短袖T恤深蓝色短裤，蓝白运动鞋。"
)
# 地垫系带场面：明确写脚上那一双，防 T2I 画成额外鞋
_DAILY_CHAR_ZHAO_FLOOR = (
    "昭昭：7岁男孩，黑色超短发露耳露后颈，圆脸，"
    "蓝色短袖T恤深蓝色短裤，双脚均已穿好一双蓝白运动鞋。"
)
# 地垫粉鞋：T2I 把「穿进鞋眼」理解成往脚上套鞋，统一用「穿过」
_FLOOR_SHOE_EYELET_RE = re.compile(r"穿进(.{0,4}鞋眼)")
_FLOOR_SHOE_MAT_ANTI_PICKUP = (
    "地垫粉鞋是灿灿刚脱下的同一双，两只平放接触地垫，鞋帮贴地，"
    "粉鞋全部在地垫上。"
)
_FLOOR_SHOE_ANTI_EXTRA = "全画面地垫上仅此一双粉红运动鞋共两只。"
_FLOOR_SHOE_COUNT_LEAD = (
    "全画面粉运动鞋恰好两只，是灿灿刚脱下的同一双；"
    "昭昭脚上穿着蓝白运动鞋。"
)
_FLOOR_SHOE_CAST_LOCK = "全画面仅有昭昭、灿灿两位儿童。"
# 三人同框人数硬锁：防止 T2I 在复杂多人镜里额外加路人（cast_count 超员）
_DAILY_CAST_LOCK_3 = "全画面仅有{}、{}、{}三人，不得出现其他任何人物。"
# form 已含位置词（背在背上/握在手中/挎在腰间…）时，渲染以 form 为准，
# 避免与 holder 渲染的「在X手中」并存成矛盾句（书包“手中+背上”同屏）
_FORM_POSITION_RE = re.compile(
    r"(?:背|扛|挂|挎|握|拿|提|捧|抱|叼|夹|举|拎|戴|穿|端|攥)在"
    r"(?:(?:昭昭|灿灿|妈妈)(?:的)?)?[^，,；;]{0,10}"
)
# brief 里「指鞋/伸手向鞋带/托鞋帮」与硬锁打架，会诱发第三只鞋或套鞋
_FLOOR_SHOE_HAND_SCRUB_RE = re.compile(
    r"(?:，|^)"
    r"(?:"
    r"双手(?:伸向|各握|各捏|各捏住|用力向外抽紧|握着|捏着)[^，。；]{0,20}|"
    r"(?:右手|左手)[^，。；]{0,8}(?:捏|握|托|抽|穿)[^，。；]{0,20}|"
    r"正(?:在)?(?:把|将)[^，。；]{0,20}鞋带[^，。；]{0,16}|"
    r"准备系带|托着鞋帮|手指包裹[^，。；]{0,10}|"
    r"手指关节[^，。；]{0,12}|青筋[^，。；]{0,10}|"
    r"另一只手自然下垂"
    r")"
)
_DAILY_CHAR_CANCAN = (
    "灿灿：10岁女孩，黑色单侧高马尾，粉色卫衣蓝色长裤，粉红运动鞋。"
)
_DAILY_CHAR_CANCAN_SOCKS = (
    "灿灿：10岁女孩，黑色单侧高马尾，粉色卫衣蓝色长裤，赤脚仅穿白袜子。"
)
# 涂鸦高饱和易把马尾画成彩色；发色硬锁紧跟角色块（句末权重最低）。
# 必须纯正面表述——图像模型把否定词当生成指令，
# "禁止…挑染/彩色"会诱发彩虹发（实测），故不写任何颜色禁止词。
_DAILY_CANCAN_HAIR_LOCK = (
    "灿灿头发通体纯黑。"
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

# ── S2 场景锚点：地点 + 硬锚点（面积从大到小），唯一可写家具/陈设处 ──
_SCENE_LOCATION_WORDS = (
    "小区公园", "公园", "厨房", "卧室", "客厅", "阳台", "院子",
    "操场", "餐厅", "书房", "浴室", "楼下", "户外",
)
_SCENE_OUTDOOR_WORDS = ("公园", "操场", "楼下", "马路", "户外", "院子", "阳台")
# 按面积/定位权重从大到小；地面锚点单独处理
_SCENE_ANCHOR_ORDER = (
    "沙发", "茶几", "餐桌", "书桌", "水槽", "窗户", "书架", "电视",
    "电视柜", "床", "衣柜", "冰箱", "灶台", "滑梯", "沙坑", "长椅",
)
# 台词/setting 出现这些词时，画面必须有一台电视（T2I 场景锚点补「电视」）
_TV_TRIGGER_WORDS = ("电视", "动画片", "看新闻", "霸占电视", "电视柜")


def _daily_scene_anchor(
    setting: str | None,
    seg1_vb: str,
    scene_anchors: list | None = None,
    *,
    dialogue_blob: str = "",
) -> str:
    """压缩版场景锚点：地点 + 硬锚点名词，室内≤3、户外≤5，只写一个辨识形容词。

    硬锚点优先取 LLM 输出的 scene_anchors（结构化），否则扫 setting/分镜1 vb。
    台词/setting 涉电视相关词时补「电视」，防止「指向电视方向」等动作落空。
    """
    blob = f"{setting or ''}{seg1_vb or ''}{dialogue_blob or ''}"
    # 场景地点/室内外只由设定与首镜画面决定；台词里的地点词仅是向往内容
    # （“我想去公园玩”“公园里有鸽子”），不能把画面场景拉到公园
    scene_blob = f"{setting or ''}{seg1_vb or ''}"
    loc = next((w for w in _SCENE_LOCATION_WORDS if w in scene_blob), None)
    if not loc:
        loc = (setting or "").strip("，。; ；")
        if len(loc) > 4:
            loc = loc[:4]
    if not loc:
        loc = "室内"
    outdoor = any(w in scene_blob for w in _SCENE_OUTDOOR_WORDS)
    anchors: list[str] = []
    # 地面锚点（地垫/地毯）优先，带辨识形容词
    if "圆形" in blob and "地垫" in blob:
        anchors.append("圆形地垫")
    elif "地垫" in blob or (scene_anchors and "地垫" in scene_anchors):
        anchors.append("地垫")
    elif "地毯" in blob or (scene_anchors and "地毯" in scene_anchors):
        anchors.append("地毯")
    if scene_anchors:
        for a in scene_anchors:
            a = str(a).strip()
            if a and a not in anchors and any(a in k or k in a for k in _SCENE_ANCHOR_ORDER):
                anchors.append(a)
    for k in _SCENE_ANCHOR_ORDER:
        if k in blob and k not in anchors:
            anchors.append(k)
    # 台词/画面涉电视相关词但锚点仍无电视时强制补「电视」（分镜5「指向电视方向」落空根因）
    if "电视" not in "".join(anchors) and any(w in blob for w in _TV_TRIGGER_WORDS):
        anchors.append("电视")
    cap = 5 if outdoor else 3
    parts = [loc] + anchors[:cap]
    return "，".join(p for p in parts if p)


def _join_slots(parts: list[str]) -> str:
    """槽位拼装：每个槽位去掉首尾标点，用「；」连接；完全相同槽位去重。"""
    out: list[str] = []
    seen: set[str] = set()
    for p in parts:
        p = (p or "").strip("，,；;。. ")
        if p and p not in seen:
            seen.add(p)
            out.append(p)
    return "；".join(out)


_SCENE_FURNITURE_OBJECTS = frozenset({"餐桌", "茶几", "沙发", "书桌", "床", "地垫"})


def _filter_scene_duplicate_object_states(
    states: list,
    *,
    scene_anchor: str | None,
    scene_anchors: list | None,
) -> list:
    """S2 已写场景硬锚点时，S5 不再重复渲染同名家具体。"""
    anchor_blob = (scene_anchor or "") + "、".join(
        str(a).strip() for a in (scene_anchors or []) if str(a).strip()
    )
    if not anchor_blob:
        return states
    out: list = []
    for st in states:
        if not isinstance(st, dict):
            continue
        obj = str(st.get("object") or "").strip()
        if obj in _SCENE_FURNITURE_OBJECTS and obj in anchor_blob:
            continue
        out.append(st)
    return out


def _strip_s4_redundant_scene_prefix(s4: str, s2: str) -> str:
    """S4 开头勿重复 S2 地点前缀（如 S2=餐桌旁… S4=餐桌旁，餐桌清晰可见…）。"""
    if not s4 or not s2:
        return s4
    s2_head = s2.split("，")[0].strip()
    for prefix in (s2_head + "，", s2 + "，", s2):
        if s4.startswith(prefix):
            return s4[len(prefix) :].lstrip("，")
    return s4


def _strip_s4_object_state_overlap(s4: str, states: list) -> str:
    """结构化路径：holder+道具状态句归 S5，从 S4 剔除同类描写。"""
    if not s4 or not states:
        return s4
    from app.services.script.visual_brief import (
        _collapse_object_aliases,
        is_body_part_object,
    )

    pairs: list[tuple[str, str]] = []
    for st in _collapse_object_aliases(states):
        if not isinstance(st, dict):
            continue
        obj = str(st.get("object") or "").strip()
        holder = str(st.get("holder") or "").strip()
        if not obj or is_body_part_object(obj):
            continue
        if holder and holder != "无":
            pairs.append((obj, holder))
    if not pairs:
        return s4
    kept: list[str] = []
    for part in re.split(r"(?<=[。；;])", s4):
        s = part.strip()
        if not s:
            continue
        drop = False
        for obj, holder in pairs:
            if obj not in s or holder not in s:
                continue
            if s.startswith("画面") and ("左边" in s or "右边" in s):
                continue
            if any(
                k in s
                for k in ("手中放着", "手里放着", "被" + holder, "被灿灿用", "被昭昭用")
            ):
                drop = True
                break
            if ("手中" in s or "手里" in s) and not s.startswith("画面"):
                drop = True
                break
        if not drop:
            kept.append(s)
    return "".join(kept).strip("，,；;。 ")


_SHARED_SINGLE_COUNT_RE = re.compile(
    r"^(一个|一只|一把|一根|一块|一枚|一张|一支|一条|一件|一册|一本|一台|一座)"
)


def _rewrite_shared_grip_to_ends_s4(s4: str, states: list) -> str:
    """两人共持单件道具时，把 S4 前两处「握{obj}」改写为「握{obj}一端/另一端」。

    object_states 已归一为 count=一个 + holder=两人（如「昭昭与灿灿」），
    S4 若写「左手握遥控器」「右手握遥控器」两处独立持物，T2I 会画成两个遥控器；
    改为「握遥控器一端」「握遥控器另一端」与 S5「两端被两人各握一端」对齐。
    S4 已写「一端/另一端」时跳过，避免二次改写。
    """
    if not s4 or not states:
        return s4
    from app.services.script.visual_brief import (
        _collapse_object_aliases,
        is_body_part_object,
    )

    roles = ("昭昭", "灿灿", "妈妈")
    result = s4
    for st in _collapse_object_aliases(states):
        if not isinstance(st, dict):
            continue
        obj = str(st.get("object") or "").strip()
        count = str(st.get("count") or "").strip()
        holder = str(st.get("holder") or "").strip()
        if not obj or is_body_part_object(obj):
            continue
        if not count or not _SHARED_SINGLE_COUNT_RE.match(count):
            continue
        if len([r for r in roles if r and r in holder]) < 2:
            continue
        if f"{obj}一端" in result or f"{obj}另一端" in result:
            continue
        # obj 可能是「电视遥控器」而 S4 写「握遥控器」（简写）；
        # 匹配「握/握住/握着 + 纯汉字名词」，名词与 obj 互相包含时视为同一道具
        pattern = re.compile(r"(握(?:住|着)?)([\u4e00-\u9fa5]{1,8})")
        counter = [0]

        def _repl(match: re.Match) -> str:
            verb, noun = match.group(1), match.group(2)
            if obj not in noun and noun not in obj:
                return match.group(0)
            counter[0] += 1
            if counter[0] == 1:
                return f"{verb}{obj}一端"
            if counter[0] == 2:
                return f"{verb}{obj}另一端"
            return match.group(0)

        result = pattern.sub(_repl, result)
    return result


def _scrub_hand_contradiction_s4(s4: str) -> str:
    """持物手与双手动作互斥兜底。

    同一角色「单手握物」又写「双手动作」（如「右手握遥控器，双手抱头」）
    时，把「双手动作」降为另一只手动作，保证每角色恒为 2 只手，
    从源头消除 T2I 三手/多手异常。
    """
    text = (s4 or "").strip()
    if not text:
        return text
    # 按角色名把文本切成片段：角色名到下一个角色名/句末
    parts = re.split(r"(?=昭昭|灿灿|妈妈)", text)
    rebuilt: list[str] = []
    for part in parts:
        role = next((r for r in ("昭昭", "灿灿", "妈妈") if part.startswith(r)), None)
        if role:
            part = _fix_role_hand_contradiction(part)
        rebuilt.append(part)
    return "".join(rebuilt).strip("，,；; ")


def _fix_role_hand_contradiction(chunk: str) -> str:
    """单个角色片段内：单手握物 + 双手动作 → 双手降为另一只手。"""
    grip = re.search(r"(?P<hand>左手|右手)握(?:住|着)?[\u4e00-\u9fa5]{1,8}", chunk)
    two = re.search(r"双手(?P<act>[\u4e00-\u9fa5]{1,5})", chunk)
    if not (grip and two):
        return chunk
    other = "右手" if grip.group("hand") == "左手" else "左手"
    return chunk.replace(two.group(0), f"{other}{two.group('act')}", 1)


def _render_object_states(
    states: list,
    *,
    setting: str | None = None,
    dialogue: list | None = None,
) -> str:
    """把结构化 object_states 渲染成道具状态句（S5）。"""
    from app.services.script.visual_brief import (
        _collapse_object_aliases,
        bowl_container_owners,
        is_body_part_object,
    )

    owners = bowl_container_owners(setting, dialogue)
    side_of = {"昭昭": "画面左边", "灿灿": "画面右边"}
    merged: dict[str, dict] = {}
    for st in _collapse_object_aliases(states):
        if not isinstance(st, dict):
            continue
        obj = str(st.get("object") or "").strip()
        if not obj or is_body_part_object(obj):
            continue
        merged[obj] = st

    def _bowl_clause(who: str, count: str, obj: str, form: str = "") -> str:
        side = side_of.get(who, "")
        if side:
            clause = f"{side}{who}面前的碗里是{count}{obj}"
        else:
            clause = f"{who}碗里有{count}{obj}"
        if form and "碗" not in form:
            clause += f"，{form}"
        return clause

    parts: list[str] = []
    meat_owner = owners.get("肉")
    veg_owner = owners.get("青菜")
    if meat_owner and veg_owner and meat_owner != veg_owner:
        veg_st = merged.pop("青菜", None) or {}
        meat_st = merged.pop("肉", None) or {}
        by_who = {
            veg_owner: _bowl_clause(
                veg_owner,
                str(veg_st.get("count") or "").strip(),
                "青菜",
            ),
            meat_owner: _bowl_clause(
                meat_owner,
                str(meat_st.get("count") or "").strip(),
                "肉",
                str(meat_st.get("form") or "").strip(),
            ),
        }
        for who in ("昭昭", "灿灿"):
            if who in by_who:
                parts.append(by_who[who])
        for who, clause in by_who.items():
            if who not in {"昭昭", "灿灿"}:
                parts.append(clause)
    for st in merged.values():
        obj = str(st.get("object") or "").strip()
        count = str(st.get("count") or "").strip()
        form = str(st.get("form") or "").strip()
        holder = str(st.get("holder") or "").strip()
        pos = str(st.get("position") or "").strip()
        who = owners.get(obj) or ""
        if who:
            parts.append(_bowl_clause(who, count, obj, form))
            continue
        if holder and holder != "无":
            clause = f"{count}{obj}在{holder}手中"
        elif pos:
            clause = f"{count}{obj}在{pos}"
        else:
            clause = f"{count}{obj}"
        if form:
            # form 已含位置词（背在昭昭背上/握在手中…）时以 form 为准，
            # 否则会拼出「书包在昭昭手中，背在昭昭背上」的矛盾句
            if holder and holder != "无" and _FORM_POSITION_RE.search(form):
                clause = f"{count}{obj}{form}"
            else:
                clause += f"，{form}"
        parts.append(clause)
    return "；".join(p for p in parts if p)


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


def _daily_floor_shoe_mat_clause(vb: str, seg: dict | None = None) -> str:
    """按本镜剧情写地垫上一双粉鞋的状态（始终共两只，禁止第三只）。"""
    text = vb or ""
    if _daily_cancan_lifts_floor_shoes(text):
        flip = "，鞋子翻了个个儿" if any(k in text for k in ("翻", "哗啦")) else ""
        return (
            "全画面仅有两只粉红运动鞋，均在灿灿双手中，"
            f"鞋带系成死结串在一起，被拎离地面{flip}，两只鞋底贴在一起。"
        )
    if any(k in text for k in ("拎", "提起", "翻过去", "哗啦")):
        return (
            "全画面仅有两只粉红运动鞋，均在灿灿双手中，鞋带已系成死结串在一起。"
        )
    if _daily_floor_shoe_aftermath(text, seg):
        return (
            "地垫中央仅有一双粉红运动鞋共两只，左右并排平放接触地垫，"
            f"鞋带纠缠散乱打结难解；{_FLOOR_SHOE_MAT_ANTI_PICKUP}"
        )
    if any(
        k in text
        for k in ("死结", "系成死", "贴一块", "串一块", "串在一", "鞋底贴", "鞋底紧紧")
    ):
        return (
            "地垫中央仅有一双粉红运动鞋共两只，鞋带系成死结，"
            f"两只鞋底紧紧贴在一起；{_FLOOR_SHOE_MAT_ANTI_PICKUP}"
        )
    if any(k in text for k in ("连环扣", "缠绕", "勒出印", "勒出")):
        return (
            "地垫中央仅有一双粉红运动鞋共两只，鞋带相互缠绕成连环扣；"
            f"{_FLOOR_SHOE_MAT_ANTI_PICKUP}"
        )
    if any(k in text for k in ("交叉", "鞋眼")) or "穿过" in text:
        return (
            "地垫中央仅有一双粉红运动鞋共两只，两只鞋带在平放的粉鞋上交叉穿过鞋眼；"
            f"{_FLOOR_SHOE_MAT_ANTI_PICKUP}"
        )
    return (
        "地垫中央仅有一双粉红运动鞋共两只，左右并排平放接触地垫，鞋带散开；"
        f"{_FLOOR_SHOE_MAT_ANTI_PICKUP}"
    )


def _daily_dialogue_line(item: dict) -> str:
    return str(item.get("line") or item.get("text") or "")


def _daily_floor_shoe_aftermath(vb: str, seg: dict | None = None) -> bool:
    """系带失败/放弃镜：鞋在垫上纠缠，无人操作。"""
    text = vb or ""
    if _daily_cancan_lifts_floor_shoes(text):
        return False
    if any(k in text for k in ("白系", "彻底", "沮丧", "叹气", "散乱")):
        return True
    if seg:
        for item in seg.get("dialogue") or []:
            line = _daily_dialogue_line(item)
            if any(k in line for k in ("白系", "彻底")):
                return True
    return False


def _daily_floor_shoe_lead_anchor(vb: str, seg: dict | None = None) -> str:
    """地垫鞋场：句首前置鞋数锚点（T2I 句首权重高）。"""
    text = vb or ""
    if _daily_cancan_lifts_floor_shoes(text):
        flip = "，鞋子翻了个个儿，" if any(k in text for k in ("翻", "哗啦")) else ""
        return (
            f"{_FLOOR_SHOE_COUNT_LEAD}{_FLOOR_SHOE_CAST_LOCK}"
            f"粉鞋两只都在灿灿双手里{flip}。"
        )
    if _daily_floor_shoe_aftermath(text, seg):
        return (
            f"{_FLOOR_SHOE_COUNT_LEAD}{_FLOOR_SHOE_CAST_LOCK}"
            "粉鞋两只平放地垫中央。"
        )
    return f"{_FLOOR_SHOE_COUNT_LEAD}{_FLOOR_SHOE_CAST_LOCK}"


def _daily_floor_shoe_tail_anchor(vb: str, seg: dict | None = None) -> str:
    """地垫鞋场：句末重申鞋数（与句首锚点呼应）。"""
    text = vb or ""
    if _daily_cancan_lifts_floor_shoes(text):
        return "重申：全画面仅两只粉运动鞋，均在灿灿双手中。"
    if _daily_floor_shoe_aftermath(text, seg):
        return "重申：全画面仅两只粉运动鞋，平放地垫中央。"
    return f"{_FLOOR_SHOE_CAST_LOCK}重申：全画面粉运动鞋恰好两只。"


def _scrub_floor_shoe_orphan_fragments(vb: str) -> str:
    """清洗 brief 里 scrub 后残留的断句（带/叉腰/勒痕等）。"""
    text = (vb or "").strip()
    if not text:
        return text
    text = re.sub(r"，带[，。；]?|^带[，。；]?", "，", text)
    text = re.sub(r"^双手(?:叉腰|摊开)[^，。；]{0,40}[，。；]?", "", text)
    text = re.sub(r"仰头看着灿灿[^，。；]{0,24}[，。；]?", "", text)
    text = re.sub(r"咧嘴得意[^，。；]{0,24}[，。；]?", "", text)
    text = re.sub(r"眼睛眯成缝[^，。；]*[，。；]?", "", text)
    text = re.sub(r"出深深的印痕[^，。；]*[，。；]?", "", text)
    if _daily_cancan_lifts_floor_shoes(text) and "画面左边是昭昭，右边是灿灿" in text:
        text = re.sub(
            r"(画面左边是昭昭，右边是灿灿。)[^。；]*(?=[。；]|$)",
            r"\1",
            text,
            count=1,
        )
    text = re.sub(r"[，,]{2,}", "，", text)
    text = re.sub(r"，(?=[；;。]|$)", "", text)
    return text.strip("，,；;。 ")


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
    text = re.sub(
        r"灿灿[^。；]{0,32}(?:各)?捏[^。；]{0,24}鞋带[^。；]*[，。；]?",
        "",
        text,
    )
    text = re.sub(
        r"灿灿[^。；]{0,16}蹲在地上[^。；]*[，。；]?",
        "",
        text,
    )
    text = re.sub(r"用力向外拉扯[^，。；]*[，。；]?", "", text)
    text = re.sub(r"散开的鞋带[^，。；]*[，。；]?", "", text)
    text = re.sub(r"地垫上散落着[^，。；]*[，。；]?", "", text)
    text = _FLOOR_SHOE_HAND_SCRUB_RE.sub("", text)
    text = re.sub(r"[，,]{2,}", "，", text)
    text = re.sub(r"，(?=[；;。]|$)", "", text)
    return text.strip("，,；;。 ")


_FLOOR_SHOE_BRIEF_ACTION_RE = re.compile(
    r"(?:拎|捏|扯|拉|叉腰|摊|系|穿|套|指|握|提|拎起|耸肩|撇嘴|皱眉|叹气|咧嘴|仰头|低头|垂在)"
)


def _scrub_floor_shoe_brief_actions(vb: str, seg: dict | None = None) -> str:
    """地垫鞋场：拎鞋/沮丧镜角色动作由硬锁写，brief 只保留布局与背景句。"""
    text = (vb or "").strip()
    if not text:
        return text
    if not _daily_cancan_lifts_floor_shoes(text) and not _daily_floor_shoe_aftermath(
        text, seg
    ) and not _daily_cancan_handles_floor_shoelaces(text, seg):
        return text
    kept: list[str] = []
    for part in re.split(r"(?<=[。；;])", text):
        sentence = part.strip()
        if not sentence:
            continue
        if "画面左边" in sentence and "画面右边" in sentence:
            layout = re.search(
                r"[^。；]*?画面左边是昭昭，右边是灿灿[^。；]*",
                sentence,
            )
            if layout:
                frag = layout.group(0).strip("，, ")
                if frag and not frag.endswith(("。", "；", ";")):
                    frag += "。"
                kept.append(frag)
            continue
        if any(k in sentence for k in ("昭昭", "灿灿")) and _FLOOR_SHOE_BRIEF_ACTION_RE.search(
            sentence
        ):
            continue
        if any(
            k in sentence
            for k in ("场景定稿", "背景", "沙发", "茶几", "靠垫", "客厅", "地垫旁")
        ):
            kept.append(sentence if sentence.endswith(("。", "；", ";")) else sentence + "。")
    return "".join(kept).strip("，,；;。 ")


def _scrub_floor_shoe_lr_and_background(vb: str) -> str:
    """地垫镜：统一左昭右灿；去掉背景自相矛盾（无物 vs 遥控器）。"""
    text = (vb or "").strip()
    if not text:
        return text
    text = re.sub(
        r"画面左边是灿灿，右边是昭昭",
        "画面左边是昭昭，右边是灿灿",
        text,
    )
    text = re.sub(
        r"左边是灿灿，右边是昭昭",
        "左边是昭昭，右边是灿灿",
        text,
    )
    if "没有任何物品" in text or "表面整洁" in text:
        text = re.sub(r"茶几上放着遥控器和空水杯[，。；]?", "", text)
        text = re.sub(r"沙发和茶几上没有任何物品[，。；]?", "", text)
        text = re.sub(r"[，,]\s*表面整洁", "", text)
    text = re.sub(r"[，,]{2,}", "，", text)
    return text.strip("，,；;。 ")


def _scrub_floor_shoe_vb_redundancy(vb: str) -> str:
    """地垫系带场面：鞋位/鞋数由硬锁统一写，去掉 brief 里重复的垫鞋描述。"""
    text = _scrub_floor_shoe_wear_verbs((vb or "").strip())
    text = _scrub_floor_shoe_lr_and_background(text)
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
    # 鞋状态由 S5 唯一负责：S4 不得写鞋帮翘起/扯起等与「鞋帮贴地」互斥的描述
    text = re.sub(r"鞋帮被扯得?[^，。；]*[，。；]?", "", text)
    text = re.sub(r"翘起[^，。；]*[，。；]?", "", text)
    if any(k in text for k in ("死结", "系在一起", "串在一起", "系成死", "贴在一起", "拎", "提", "翻")):
        text = re.sub(r"地垫上散落着散开的鞋带[^，。；]*[，。；]?", "", text)
        text = re.sub(r"鞋带松散(?:摇晃)?[^，。；]*[，。；]?", "", text)
    if _daily_cancan_lifts_floor_shoes(text):
        text = re.sub(
            r"灿灿[^。；]{0,16}双手拎起[^。；]+?[，。；]",
            "灿灿在地垫上，",
            text,
        )
        text = re.sub(
            r"灿灿[^。；]{0,16}(?:弯腰)?(?:用(?:右|左)手)?[^。；]{0,8}(?:拎|提|拎起)[^。；]+?[，。；]",
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
            "昭昭双手空着、只看灿灿手中的粉鞋。"
        )
    if re.search(r"昭昭[^。；]{0,24}双手叉腰", text):
        extra = ""
        if re.search(r"昭昭[^。；]{0,40}咧嘴得意", text):
            extra = "得意地笑，"
        return (
            f"{zhao_feet}昭昭蹲在画面左边，双手叉腰，{extra}"
            "昭昭双手空着、只看灿灿手中的粉鞋。"
        )
    return (
        f"{zhao_feet}昭昭蹲在一旁抬头看着被拎起的粉鞋，"
        "昭昭双手空着。"
    )


def _daily_zhao_floor_shoe_idle_action(
    vb: str, zhao_feet: str, seg: dict | None = None
) -> str:
    """地垫旁观/沮丧镜：昭昭不碰鞋带，按 brief 写垂手或叉腰。"""
    text = vb or ""
    if _daily_floor_shoe_aftermath(text, seg) or re.search(
        r"昭昭[^。；]{0,24}双手垂", text
    ):
        return (
            f"{zhao_feet}昭昭蹲在地垫旁，双手垂在身侧，"
            "低头看着地垫上的粉鞋，表情沮丧，昭昭双手空着。"
        )
    if re.search(r"昭昭[^。；]{0,24}双手叉腰", text):
        return (
            f"{zhao_feet}昭昭蹲在地垫旁，双手叉腰，"
            "低头看着地垫上的粉鞋，昭昭双手空着。"
        )
    return (
        f"{zhao_feet}昭昭蹲在地垫旁看着地垫上的粉鞋，"
        "昭昭双手空着。"
    )


def _daily_cancan_handles_floor_shoelaces(vb: str, seg: dict | None = None) -> bool:
    """本镜是否为灿灿蹲鞋旁抠/解鞋带死结（昭昭旁观）。"""
    text = vb or ""
    if _daily_floor_shoe_aftermath(text, seg):
        return False
    if "灿灿" not in text:
        return False
    if _daily_cancan_lifts_floor_shoes(text):
        return False
    if re.search(
        r"灿灿[^。；]{0,32}(?:抠|解|拉|扯|穿|捏|握)[^。；]{0,16}鞋带"
        r"|灿灿[^。；]{0,16}上手[^。；]{0,8}抠"
        # 禁止跨过「昭昭蹲…」误匹配：灿灿…昭昭蹲在鞋
        r"|灿灿[^。；昭]{0,12}蹲[^。；]{0,8}鞋",
        text,
    ):
        return True
    if "抠" in text and "鞋带" in text:
        head = text[: text.find("抠")]
        if "灿灿" in head[-40:]:
            return True
    if seg:
        for item in seg.get("dialogue") or []:
            if str(item.get("speaker") or "").strip() != "灿灿":
                continue
            line = _daily_dialogue_line(item)
            if "抠" in line and "死结" in line:
                return True
    return False


def _daily_zhao_floor_shoe_untie_watch(vb: str, zhao_feet: str) -> str:
    """灿灿抠鞋带镜：昭昭站一旁摊手旁观，不碰鞋。"""
    text = vb or ""
    if re.search(r"昭昭[^。；]{0,24}双手摊开", text):
        return (
            f"{zhao_feet}昭昭站在地垫旁，双手摊开耸肩，"
            "歪头看着灿灿，昭昭双手空着、只看灿灿。"
        )
    return (
        f"{zhao_feet}昭昭站在地垫旁看着灿灿，"
        "昭昭双手空着。"
    )


def _daily_cancan_floor_shoe_untie_clause(vb: str) -> str:
    """灿灿抠/解地垫粉鞋鞋带死结，鞋平放垫上。"""
    return (
        "灿灿赤脚仅穿白袜子蹲在地垫旁，"
        "灿灿双手用力抠地垫上一双粉鞋的鞋带死结，"
        "粉鞋平放垫上、鞋帮贴地，粉鞋全部在地垫上。"
    )


def _daily_floor_shoe_cast_poses(vb: str, speakers: list[str], seg: dict | None = None) -> str:
    """地垫系带场面的角色姿态（昭昭/灿灿），属 S4 画面而非道具状态。"""
    cancan_lift = _daily_cancan_lifts_floor_shoes(vb)
    cancan_untie = _daily_cancan_handles_floor_shoelaces(vb, seg)
    tying = _daily_zhao_handles_floor_shoelaces(vb)
    zhao_feet = "昭昭双脚穿着蓝白运动鞋。"
    if "昭昭" in speakers and cancan_lift:
        action = _daily_zhao_floor_shoe_watch_action(vb, zhao_feet)
    elif "昭昭" in speakers and cancan_untie:
        action = _daily_zhao_floor_shoe_untie_watch(vb, zhao_feet)
    elif "昭昭" in speakers and tying:
        action = (
            f"{zhao_feet}昭昭蹲在地垫旁，双膝弯曲，"
            "双手并拢拢住地垫上一双粉鞋的鞋带结；"
            "粉鞋平放垫上、鞋帮贴地，粉鞋全部在地垫上。"
        )
    elif "昭昭" in speakers:
        action = _daily_zhao_floor_shoe_idle_action(vb, zhao_feet, seg)
    else:
        action = ""
    if "灿灿" in speakers and cancan_lift:
        flip = "，鞋子翻了个个儿" if any(k in vb for k in ("翻", "哗啦")) else ""
        cancan = (
            "灿灿赤脚仅穿白袜子蹲在地垫上，"
            f"双手拎着系成死结串在一起的一双粉鞋（共两只）{flip}，"
            "两只鞋底贴在一起，粉鞋全部在灿灿双手中。"
        )
    elif "灿灿" in speakers and cancan_untie:
        cancan = _daily_cancan_floor_shoe_untie_clause(vb)
    elif "灿灿" in speakers:
        cancan = _daily_cancan_floor_shoe_idle_clause(vb, seg)
    else:
        cancan = ""
    return f"{action}{cancan}"


def _daily_floor_shoe_lock(vb: str, speakers: list[str], seg: dict | None = None) -> str | None:
    """地垫系带场面：道具状态（mat_clause）+ 角色姿态，硬锁鞋数与动作。"""
    return f"{_daily_floor_shoe_mat_clause(vb, seg)}{_daily_floor_shoe_cast_poses(vb, speakers, seg)}"


def _daily_cancan_floor_shoe_idle_clause(vb: str, seg: dict | None = None) -> str:
    """地垫旁观镜：灿灿站一旁，按 brief 写叉腰或垂手。"""
    text = vb or ""
    base = "灿灿赤脚仅穿白袜子站在地垫旁；"
    if _daily_floor_shoe_aftermath(text, seg) or re.search(
        r"灿灿[^。；]{0,24}双手叉腰", text
    ):
        tail = "灿灿双手叉腰，低头看着地垫上的粉鞋"
        if "叹" in text or any(
            "叹" in _daily_dialogue_line(d)
            for d in (seg or {}).get("dialogue") or []
        ):
            tail += "叹了口气"
        return base + tail + "，灿灿双手空着。"
    return base + "灿灿双手自然下垂，灿灿双手空着。"


def _daily_zhao_handles_floor_shoelaces(vb: str) -> bool:
    """本镜昭昭是否在操作鞋带（非仅旁观）。"""
    text = vb or ""
    if "昭昭" not in text:
        return False
    if _daily_cancan_lifts_floor_shoes(text):
        return False
    if _daily_cancan_handles_floor_shoelaces(text, None):
        return False
    if re.search(r"昭昭[^。；]{0,24}双手摊开", text):
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
    """本段出场角色：固定主角（昭昭/灿灿）默认每镜都在，妈妈按 cast 决定。

    优先读 LLM 输出的 seg["cast"]（额外在场且非常态，如妈妈），
    硬编码补入固定主角昭昭/灿灿；无 cast 时回退 speakers 粘性逻辑。
    """
    cast = seg.get("cast")
    if isinstance(cast, list):
        names: list[str] = ["昭昭", "灿灿"]
        for n in cast:
            n = str(n).strip()
            if n in ("昭昭", "灿灿", "妈妈") and n not in names:
                names.append(n)
        return names

    from app.services.daily_story.speaker import allowed_cast_from_segment

    allowed = allowed_cast_from_segment(seg)
    return [n for n in ("昭昭", "灿灿", "妈妈") if n in allowed]


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
            if pair == ["灿灿", "昭昭"]:
                pair = ["昭昭", "灿灿"]
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
        return "平涂明亮光照。"
    return "平涂光照。"


_DAILY_COMPOSITION_LOOK = {
    "昭昭": "蓝T恤深蓝短裤短发男孩昭昭",
    "灿灿": "粉卫衣蓝裤黑马尾女孩灿灿",
    "妈妈": "米色上衣牛仔裤黑长发妈妈",
}


def _daily_floor_shoe_background(vb: str) -> str:
    """地垫抠结短 prompt：只保留极简背景，避免 brief 矛盾句进入 T2I。"""
    text = vb or ""
    if any(k in text for k in ("圆形", "编织", "浅灰")):
        return "浅色木地板、米色圆形编织地垫，沙发一角背景虚化。"
    return "浅色木地板、米色地垫，沙发一角背景虚化。"


def _daily_floor_shoe_untie_compact_prompt(seg: dict, *, vb: str) -> str:
    """灿灿抠死结 + 昭昭摊手旁观：短 prompt，左昭昭右灿灿，正面表述。"""
    first = _daily_first_speaker(seg)
    zhao_mouth = "嘴唇微张正在说话" if first == "昭昭" else "嘴唇闭合"
    cancan_mouth = "嘴唇微张正在说话" if first == "灿灿" else "嘴唇闭合"
    zhao = _DAILY_COMPOSITION_LOOK["昭昭"]
    cancan = _DAILY_COMPOSITION_LOOK["灿灿"]
    parts = [
        _DAILY_T2I_STYLE,
        f"室内客厅中近景，{_daily_floor_shoe_background(vb)}",
        f"画面左侧{zhao}，蓝白运动鞋穿在脚上，站立，"
        f"双手掌心向上摊开，{zhao_mouth}。",
        f"画面右侧{cancan}，赤脚仅穿白袜子，"
        f"蹲在地垫旁，双手用力抠地垫中央一双粉红运动鞋的鞋带死结，"
        f"{cancan_mouth}。",
        "地垫中央平放两只粉红运动鞋，鞋带缠成死结，"
        "两只鞋底贴在一起，鞋帮贴地，粉鞋全部在地垫上。",
        _DAILY_CANCAN_HAIR_LOCK,
        _DAILY_CHAR_HEIGHT,
        _FLOOR_SHOE_CAST_LOCK,
        "中近景，严格左"
        f"{zhao}、右{cancan}，"
        "左右位置固定不变，全身可见，每人只显示2条手臂。",
    ]
    from app.services.script.visual_brief import strip_held_prop_from_surface

    return strip_held_prop_from_surface("".join(parts))


# 多人同框镜头中会破坏“三人全身同框”的位移动词。
# 仅中和“位移/离场/朝向变化”类动词（走向/转身/背对/离开/出画等）；
# 蹲/坐/站起/关门等叙事关键姿势不自动中和（避免把系鞋带/关门改成呆站）。
_DISPLACEMENT_RE = re.compile(
    r"(?:正?在)?(?:朝|向|往)?(?:画面[左中右]?[边侧]?)?"
    r"(?:走向|走进|转身|背对|背向|离开|出门|进屋|跑向|快步|出画|入画|"
    r"侧身离去|靠近|走近|走远|走开|跑开|离开房间|转身离开)[^，。；]*"
    r"|(?<![看望瞧指瞄瞟瞥盯视])(?:朝|向|往)(?:房间|门口|门外|屋内|屋外)[^，。；]*"
)


def neutralize_displacement(text: str, *, multi_body: bool) -> str:
    """多人同框时，把位移动词替换为静态站位，避免背影/出画/遮挡。

    仅当 multi_body=True（三人同框/全身可见）时生效；单人/特写不处理，
    保留叙事动作（如人物转身离开）。命中后记录替换（调用方日志）。
    注意：不匹配“看向/望门口”等视线词，避免误伤。
    """
    text = (text or "").strip()
    if not text or not multi_body:
        return text
    orig = text
    text = _DISPLACEMENT_RE.sub("站位稳定，脸朝镜头", text)
    text = re.sub(r"[，,]{2,}", "，", text)
    text = re.sub(r"，(?=[。；;]|$)", "", text)
    if text != orig:
        return text.strip("，,；;。. ")
    return text


def inject_role_completeness(
    text: str,
    speakers: list[str],
    *,
    shot_type: str = "",
) -> str:
    """多主体同框时，为每个必须出镜角色注入“硬主体完整性”描述。

    解决“妈妈旁观→被省略/只半身/虚化”等问题：
    把每个出镜角色从“可丢弃填充物”升级为“必须成型的硬主体”。
    """
    names = [s for s in speakers if s in _DAILY_CHAR_MAP]
    if len(names) < 2 or shot_type == "特写":
        return text
    full = "、".join(names)
    if "妈妈" in names:
        mom_clause = (
            f"{full}均为画面硬主体，全身从头到脚完整可见，"
            "妈妈作为独立完整主体入镜，面部清晰朝向镜头，"
            "不被门框/前景/其他角色遮挡，不虚化、不裁切、不背影。"
        )
    else:
        mom_clause = (
            f"{full}均为画面硬主体，全身从头到脚完整可见，"
            "面部清晰朝向镜头，不被遮挡、不虚化、不裁切、不背影。"
        )
    if not text:
        return mom_clause
    if mom_clause.split("，")[0] in text:
        return text
    # 拼接处补分隔：text 可能以人数硬锁结尾（…不得出现其他任何人物），
    # 直接拼接会与完整性子句粘连
    if text.rstrip().endswith(("。", "！", "？", "；")):
        return f"{text}{mom_clause}"
    return f"{text}。{mom_clause}"


def _daily_composition(
    shot_type: str,
    speakers: list[str],
    *,
    vb: str = "",
) -> str:
    names = [s for s in speakers if s in _DAILY_CHAR_MAP]
    vb_text = vb or ""
    has_lr = bool(_DAILY_LR_RE.search(vb_text)) or (
        "画面左边是" in vb_text and "画面右边是" in vb_text
    )
    has_lcr = bool(_DAILY_LCR_RE.search(vb_text))
    if len(names) >= 3:
        a, b, c = names[0], names[1], names[2]
        lr = "" if (has_lcr or has_lr) else f"画面从左到右是{a}、{b}、{c}。"
        return (
            f"{lr}中景三人同框，全身可见。"
            f"{_DAILY_CAST_LOCK_3.format(a, b, c)}"
        )
    if shot_type == "特写":
        if len(names) == 2:
            a, b = names[0], names[1]
            lr = "" if has_lr else f"画面左边是{a}，右边是{b}。"
            return f"{lr}中近景特写，全身可见，每人只显示2条手臂。"
        return "面部特写，占画面主体，背景虚化。"
    if shot_type == "中景":
        if len(names) == 2:
            a, b = names[0], names[1]
            lr = "" if has_lr else f"画面左边是{a}，右边是{b}。"
            return f"{lr}中景，全身可见，每人只显示2条手臂。"
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


_SCENE_SENTENCE_WORDS = (
    "背景", "客厅", "茶几", "沙发", "靠垫", "地垫", "餐桌", "书桌", "花盆",
    "托盘", "阳台", "厨房", "卧室", "遥控器", "空水杯", "场景定稿",
)

# S6 口型锁唯一负责嘴部状态：所有非 S6 层（S2/S3/S4/S5/S7/8）不得残留任何嘴部姿态词。
# 黑名单覆盖嘴部动作/口型/嘴部道具占用；删除后按语义补偿非嘴部表情，避免情绪空洞。
_MOUTH_TOKEN_RE = re.compile(
    r"(?:龇牙咧嘴|龇牙|露齿|咧开嘴|咧嘴|吐舌|张嘴|张口|大笑|抿嘴|撇嘴|撅嘴|噘嘴|嘟嘴|嘟着嘴|嘟起嘴|鼓腮|鼓着腮|鼓着腮帮子|腮帮子|咬唇|咬嘴唇|咬住嘴唇|嘴角|嘴唇|嘴巴|嘴形|口型|含[着住]?|叼着|嘴里|嘴边|唇边|亲吻|亲了|吹气|憋嘴|闭嘴|嘴一撇|瘪嘴|裂开嘴|张着嘴|微张着嘴|嘟囔|撇着嘴角|不说话|忍住笑|憋住笑|抿着嘴角)"
)
# 嘴部词 → 非嘴部情绪补偿（保证删除后情绪仍在，且不再诱发模型重画嘴部）
_MOUTH_EMOTION_COMPENSATION = (
    ("鼓着腮帮子", "眼睑微垂，神情气鼓鼓的"),
    ("鼓着腮", "眼睑微垂，神情气鼓鼓的"),
    ("鼓腮", "眼睑微垂，神情气鼓鼓的"),
    ("咬住嘴唇", "目光低垂，神情紧张"),
    ("咬嘴唇", "目光低垂，神情紧张"),
    ("咬唇", "目光低垂，神情紧张"),
    ("嘟着嘴", "眉头微抬，眼尾微垂，略带委屈"),
    ("嘟起嘴", "眉头微抬，眼尾微垂，略带委屈"),
    ("嘟嘴", "眉头微抬，眼尾微垂，略带委屈"),
    ("撇嘴", "眉心微蹙，目光下移，神情不悦"),
    ("撅嘴", "眉头微抬，眼尾微垂，略带委屈"),
    ("噘嘴", "眉头微抬，眼尾微垂，略带委屈"),
    ("抿嘴", "神情克制，目光坚定"),
    ("瘪嘴", "眉头微蹙，神情委屈"),
    ("龇牙咧嘴", "眼角弯起，目光明亮"),
    ("咧开嘴", "眼角弯起，目光明亮"),
    ("咧嘴", "眼角弯起，目光明亮"),
    ("龇牙", "眼角弯起，目光明亮"),
    ("露齿", "眼角弯起，目光明亮"),
    ("大笑", "眼尾弯起，目光明亮，脸颊微红"),
    ("吐舌", "俏皮的眼神"),
    ("吹气", "眉头微蹙"),
)
# 非嘴部安全表情白名单（供 verify/清洗时对照，不直接使用）
_MOUTH_SAFE_EXPRESSIONS = (
    "皱眉", "眉心", "眉头", "瞪眼", "眯眼", "眼睑", "目光", "眼尾", "眼含", "鼻翼", "脸颊", "眼神", "眼角", "眼弯", "眸光",
)


def scrub_mouth_tokens(text: str) -> str:
    """从任意非 S6 层文本中删除嘴部姿态词并做情绪补偿。

    口型由 S6 唯一负责；S2/S3/S4/S5/S7/8 出现任何嘴部词都会与口型锁打架。
    命中嘴部 token 时：若该 token 有情绪语义，先补偿一个非嘴部表情；
    再删除 token 本体，并清理因此产生的重复标点/空段。
    """
    text = (text or "").strip()
    if not text:
        return text
    for word, compensation in _MOUTH_EMOTION_COMPENSATION:
        if word in text:
            # 同句已带眉眼表情时不重复补偿，仅删除；否则补一个非嘴部表情
            sentence = text
            has_eye_expr = any(
                w in sentence for w in ("眉心", "眉头", "瞪眼", "眯眼", "眼睑", "目光", "眼尾", "眼神", "眼角", "皱眉")
            )
            if not has_eye_expr:
                text = text.replace(word, compensation, 1)
            else:
                text = text.replace(word, "", 1)
            break
    text = _MOUTH_TOKEN_RE.sub("", text)
    # 嘴部词删除后可能残留孤立的「笑/不说话/忍住」等嘴部上下文词
    def _strip_residual_mouth(m: re.Match) -> str:
        return m.group(1)

    text = re.sub(r"(目光明亮|眼尾弯起|脸颊微红|神情克制|目光坚定|略带委屈|神情委屈|神情不悦|目光低垂|神情紧张|气鼓鼓的|俏皮)笑", _strip_residual_mouth, text)
    text = re.sub(r"[，,]{2,}", "，", text)
    text = re.sub(r"，(?=[。；;]|$)", "", text)
    text = re.sub(r"[，,；;。. ]{2,}", "，", text)
    text = re.sub(r"(?<=委屈)委屈", "", text)
    text = text.strip("，,；;。. ")
    return text


def _scrub_vb_mouth_words(vb: str) -> str:
    """S4 禁写嘴部动作，口型由 S6 唯一负责（张嘴词与闭嘴锁矛盾）。"""
    return scrub_mouth_tokens(vb)


def _strip_vb_scene_anchor_sentences(vb: str) -> str:
    """S4 不得重复 S2 场景锚点：剔除无角色、只写场景陈设的句子。"""
    text = (vb or "").strip()
    if not text:
        return text
    kept: list[str] = []
    for part in re.split(r"(?<=[。；;])", text):
        sentence = part.strip()
        if not sentence:
            continue
        has_char = any(n in sentence for n in ("昭昭", "灿灿", "妈妈"))
        scene_hits = [w for w in _SCENE_SENTENCE_WORDS if w in sentence]
        if not has_char and len(scene_hits) >= 2:
            continue
        kept.append(sentence)
    return "".join(kept).strip("，,；;。. ")


def assemble_daily_t2i_prompt(
    seg: dict,
    *,
    extra: str | None = None,
    scene_anchor: str | None = None,
    setting: str | None = None,
) -> str:
    """规则拼装 daily_story image_prompt。

    风格 + visual_brief + 出场角色外貌 + 光照 + 构图。
    extra 仅用于显式附加的出图正文（勿传入质检/改写元指令）。
    """
    vb = str(seg.get("visual_brief") or "").strip()
    speakers = _daily_speakers_of(seg)
    if vb:
        from app.services.daily_story.speaker import (
            scrub_leaked_speaker_names,
            scrub_offscreen_doorway_cues,
        )
        from app.services.script.visual_brief import (
            enrich_thin_daily_visual_brief,
            scrub_daily_visual_brief,
        )

        vb = scrub_daily_visual_brief(vb)
        if seg.get("visual_subjects"):
            vb = enrich_thin_daily_visual_brief(
                {**seg, "visual_brief": vb}, setting=setting
            )
        vb = strip_verify_regen_leak(vb)
        vb = scrub_leaked_speaker_names(vb, set(speakers))
        vb = scrub_offscreen_doorway_cues(vb, allowed=set(speakers))
        # 默认陈设只在首镜保留：非首镜去除重复的「茶几上放着遥控器和空水杯」
        if int(seg.get("segment_index") or 0) > 1:
            vb = re.sub(r"[，,]\s*茶几上放着遥控器和空水杯\s*", "", vb)
            vb = vb.replace("茶几上放着遥控器和空水杯", "").strip("，, ")
        vb = _strip_vb_narrative_continuity(vb)
        # LLM 已写「场景定稿」时去掉标签（场景锚点由 S2 统一负责）
        vb = vb.replace("场景定稿：", "").strip("，,。. ")
    else:
        vb = strip_verify_regen_leak(vb)
    shot = str(seg.get("shot_type") or "").strip()
    floor_shoe_scene = _daily_setting_floor_shoe_scene(setting)
    vb_for_shoe_lock = vb
    # 结构化路径：visual_subjects + object_states 齐备时，动作/状态由结构化字段负责，
    # 跳过为自由文本设计的清洗链与姿态锁，消除跨槽位重复
    structured = bool(seg.get("visual_subjects")) and bool(seg.get("object_states"))
    if floor_shoe_scene and vb and not structured:
        vb = _scrub_floor_shoe_vb_redundancy(vb)
        vb = _scrub_floor_shoe_state_conflicts(vb)
        vb = _scrub_floor_shoe_hand_actions(vb)
        vb = _scrub_floor_shoe_idle_actions(vb)
        vb = _scrub_floor_shoe_orphan_fragments(vb)
        vb = _scrub_floor_shoe_brief_actions(vb, seg)

    if (
        floor_shoe_scene
        and not structured
        and _daily_cancan_handles_floor_shoelaces(vb_for_shoe_lock, seg)
    ):
        return _daily_floor_shoe_untie_compact_prompt(seg, vb=vb_for_shoe_lock)

    first = _daily_first_speaker(seg)
    if vb:
        vb = _strip_vb_scene_anchor_sentences(vb)
        vb = _scrub_vb_mouth_words(vb)
        vb = _strip_style_suffix(vb)

    # 多人同框（三人同框/多角色中景）时：先消解位移动词，避免“走向房间⇄同框”冲突
    multi_body = len([s for s in speakers if s in _DAILY_CHAR_MAP]) >= 3 or (
        len([s for s in speakers if s in _DAILY_CHAR_MAP]) == 2
        and shot in ("中景", "全景")
    )
    if vb and multi_body:
        vb = neutralize_displacement(vb, multi_body=True)

    # S1 风格（常量）
    s1 = _DAILY_T2I_STYLE

    s2 = scene_anchor or ""
    if s2 and shot == "特写":
        s2 = s2.split("，")[0]
    s2 = scrub_mouth_tokens(s2)
    if s2:
        s2 = f"{s2}，简笔涂鸦场景"

    # S3：有参考图时外貌靠「保持参考图外貌」句锁定，不再展开服装长描述
    s3 = ""

    # S4 本镜画面（唯一 LLM 入口，已清洗；场景/陈设归 S2，不重复）
    s4_parts: list[str] = []
    if vb:
        s4_parts.append(vb)
        if "门" in vb and "完整门板" not in vb:
            s4_parts.append("画面中的门是一扇单开门，一块完整门板")
        if ("风" in vb or "吹" in vb) and ("头发" in vb or "马尾" in vb):
            if "连着头皮" not in vb:
                s4_parts.append("发丝连着头皮")
            if "门" in vb and not any(
                w in vb for w in ("背离", "飘离门口", "远离门")
            ):
                s4_parts.append("风从门口吹向室内，头发顺风飘离门口")
    from app.services.script.visual_brief import daily_hand_injury_s4_clause

    hand_injury_clause = daily_hand_injury_s4_clause(seg, setting)
    if hand_injury_clause:
        s4_parts.append(hand_injury_clause)
    s4 = "；".join(
        p.strip("，,；;。. ") for p in s4_parts if p.strip("，,；;。. ")
    )
    from app.services.script.visual_brief import _dedupe_clause_text

    s4 = _dedupe_clause_text(s4)
    if structured and s2:
        s4 = _strip_s4_redundant_scene_prefix(s4, s2)
    s4 = _scrub_hand_contradiction_s4(s4)
    s4 = scrub_mouth_tokens(s4)

    # S5 道具状态：优先结构化 object_states（状态机已归一），否则 vb 关键词推导兜底
    s5 = ""
    obj_states = seg.get("object_states")
    if isinstance(obj_states, list) and obj_states:
        obj_states = _filter_scene_duplicate_object_states(
            obj_states,
            scene_anchor=s2,
            scene_anchors=seg.get("scene_anchors"),
        )
        rendered = _render_object_states(
            obj_states,
            setting=setting,
            dialogue=seg.get("dialogue"),
        )
        if rendered:
            s5 = rendered
            if structured:
                s4 = _strip_s4_object_state_overlap(s4, obj_states)
                s4 = _rewrite_shared_grip_to_ends_s4(s4, obj_states)
            if floor_shoe_scene and (
                "粉鞋" in rendered or "粉红运动鞋" in rendered
            ):
                s5 += "。全画面粉运动鞋只有一双两只。"
            # 无结构化 subjects 的老数据：角色姿态仍由姿态锁补；结构化时跳过（动作已在 S4）
            if floor_shoe_scene and speakers and not seg.get("visual_subjects"):
                s5 += _daily_floor_shoe_cast_poses(vb_for_shoe_lock, speakers, seg)
    elif floor_shoe_scene and speakers:
        s5 = _daily_floor_shoe_lock(vb_for_shoe_lock, speakers, seg) or ""
    s5 = scrub_mouth_tokens(s5)

    # S6 口型锁（dialogue 推导）
    s6 = ""
    if first and first in speakers:
        others = [n for n in speakers if n != first]
        mouth = f"{first}嘴唇微张，正在开口说话"
        if others:
            mouth += f"，{'、'.join(others)}嘴巴自然闭合"
        s6 = mouth

    # S7+8 镜头参数（光照 + 构图站位合并）
    layout = _daily_layout_speakers(seg, vb)
    s78 = _daily_lighting(vb) + _daily_composition(shot, layout, vb=vb)
    s78 = scrub_mouth_tokens(s78)
    # 多人同框时：为每个出镜角色注入硬主体完整性，妈妈不被省略/虚化/遮挡
    if multi_body:
        s78 = inject_role_completeness(s78, speakers, shot_type=shot)

    parts = [s1, s2, s4, s5, s3, s6, s78, _DAILY_T2I_STYLE_LOCK_TAIL]
    if extra and extra.strip():
        cleaned = strip_verify_regen_leak(extra.strip())
        if cleaned and cleaned == extra.strip():
            parts.append(cleaned)

    from app.services.script.visual_brief import strip_held_prop_from_surface

    prompt = strip_held_prop_from_surface(_join_slots(parts))
    return _scrub_detached_body_part_clauses(prompt)


_DETACHED_BODY_PART_CLAUSE_RE = re.compile(
    r"[；;]?[^；;]*(?:手中|手里|手上)(?:放着|握着|拿着)?(?:一?只?)?(?:右|左)?手[^；;]*"
    r"|[^；;]*(?:一?只?)?(?:右|左)?手在[^；;]{0,8}手中[^；;]*"
)


def _scrub_detached_body_part_clauses(prompt: str) -> str:
    """剔除「手中放着一只手」类断肢表述（object_states 误把伤势当道具）。"""
    text = _DETACHED_BODY_PART_CLAUSE_RE.sub("", prompt or "")
    return re.sub(r"[；;]{2,}", "；", text).strip("；; ")


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
        _resolve_prop_state_regression,
        daily_locked_inventory,
        scrub_daily_visual_brief,
        strip_unlocked_inventory,
    )

    # 跨镜状态保护：已落地的冲突道具不得在后续镜写回家具台面
    # （覆盖出图质检兜底重写 visual_brief 的路径）
    _resolve_prop_state_regression(segments)
    # object_states 状态机：跨镜继承 + 去重 + 校验矛盾/回归
    from app.services.script.visual_brief import normalize_object_states

    obj_issues = normalize_object_states(segments, setting=setting)
    if obj_issues:
        import logging

        logging.getLogger(__name__).warning(
            "object_states issues: %s", "; ".join(obj_issues[:5])
        )
    from app.services.script.visual_brief import promote_hand_injury_across_segments

    promote_hand_injury_across_segments(segments, setting)
    locked = daily_locked_inventory(segments, setting)
    for seg in segments:
        vb = str(seg.get("visual_brief") or "")
        cleaned = strip_unlocked_inventory(scrub_daily_visual_brief(vb), locked)
        if cleaned != vb:
            seg["visual_brief"] = cleaned
    # S2 场景锚点：按本片 setting + 分镜1 scene_anchors/画面，用模板压缩
    seg1_vb = ""
    seg1_anchors: list | None = None
    for seg in segments:
        if int(seg.get("segment_index") or 0) == 1:
            seg1_vb = str(seg.get("visual_brief") or "")
            seg1_anchors = seg.get("scene_anchors") or None
            break
    from app.services.script.visual_brief import _dialogue_blob

    dialogue_blob = _dialogue_blob(segments)
    scene_anchor = _daily_scene_anchor(
        setting, seg1_vb, seg1_anchors, dialogue_blob=dialogue_blob
    )
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
            setting=setting,
        )
        seg.pop("_hand_injury_phase", None)
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
    "画面含门时须写明「一扇单开门，一块完整门板」，"
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
    "选 1-2 个写微动（如纱帘、遥控器、空水杯、鞋带结扣）；"
    "禁止新造画面外物体（如蛋糕盒、丝带、蜡笔屑、灰尘、水渍）；"
    "须写方向、速度、幅度细节，但幅度用「轻微/极小」等相对词，禁止写具体厘米/角度数字；"
    "只写可观测的物理位移结果，禁止写隐含施力者或因果（"
    "反例：鞋带在拉扯下绷紧→正例：鞋带结扣逐渐收拢绷紧）；"
    "禁止像素级亮度调制（杯壁反光闪烁、绒面光影明暗交替、高光闪烁等）；"
    "禁人物/有生命体动作；末尾须写「人物姿势保持不变」。"
    "正例：窗边纱帘被风轻轻掀起又落下，窗帘下摆轻微向右飘动后回摆，人物姿势保持不变。"
)

_IMAGE_PROMPT_MOTION_TAIL_DAILY_KEYFRAME = (
    "【keyframe】按以下模板输出 motion_prompt（120-280 字）：\n"
    "【站位】必须与本段 image_prompt 构图句一致，禁止自行改成两人：\n"
    "若 image_prompt 有「画面从左到右是A、B、C」或"
    "「左边是A，中间是B，右边是C」，开头必须抄这句三人站位；"
    "未说话的中间人（常为妈妈）也要写进站位，并补"
    "「{中间人}保持静图姿势，全程在画面内」。\n"
    "若只有「画面左边是A，右边是B」，则抄二人站位：画面左边是{角色A}，右边是{角色B}。\n"
    "【说话句】必须按本段 dialogue 顺序，每一句台词各写一行"
    "「{该句说话人}说话，同时{微动作}后停止」；"
    "句间格式完全相同，微动作须贴合本镜画面；"
    "同人说多句就要写多行，禁止合并、漏句或打乱对白顺序。"
    "禁止写「后定格」（末句由系统在 TTS 后改为定格）。\n"
    "【动作限幅】说话人只动嘴+一个粗粒度微动作（点头、耸肩、手掌小幅摆动）；"
    "禁止食指/单指/手指蜷缩等手指级精细动作；"
    "身体姿态、站姿、头部朝向保持不变；"
    "禁止写具体厘米/角度数字，禁止「身体前倾幅度增大」「双手叉腰撑开」「大幅耸肩」等动作；"
    "非说话方保持静图姿势，不写主动作。\n"
    "站位左右/中间禁止与 image_prompt 对调。\n"
    "【时间轴】禁止自编起止秒数；写成「{角色}说话，同时…」即可，"
    "出片前系统按 TTS 句时长自动写入「X.X-Y.Y秒」。\n"
    "有台词角色必须含「说话，同时」；无台词角色可不写「说话，同时」，只写微动作。\n"
    "【收束表情】禁止写长段表情锁定（如眉头紧皱、嘴唇抿成一条线）；"
    "image_prompt 已定格表情，motion 只写说话与粗粒度微动作；"
    "系统会丢弃收束段并替换为口型锁定句。\n"
    "【锁定】服装发型稳定，身高比例（{角色B}比{角色A}矮半个头）不变。\n"
    "镜头固定，不推近不拉远，两人全程在画面内。\n"
    "禁止镜头推近/推进/拉远/变焦/放大；禁止大位移换位、全身换姿势、多人齐跑、抽象光效。\n"
    "出片前系统按 TTS 将说话句改为"
    "「X.X-Y.Y秒左侧女孩/右侧男孩开口说话，口型自然开合，说完即闭嘴…"
    "此时…嘴巴闭合不动」，并把收束表情段替换为嘴唇锁定句。\n"
    "正例（dialogue 三句：灿灿→昭昭→灿灿）：\n"
    "画面左边是灿灿，右边是昭昭。"
    "灿灿说话，同时微微点头后停止；"
    "昭昭说话，同时双肩轻轻耸起后停止；"
    "灿灿说话，同时手掌小幅向右摆动后停止。"
    "服装发型稳定，身高比例（昭昭比灿灿矮半个头）不变。"
    "镜头固定，不推近不拉远，两人全程在画面内。\n"
    "反例：0.0-1.5秒灿灿说话…（禁止自编秒数）；"
    "只写两句说话但 dialogue 有三句（漏句）；"
    "灿灿右手食指点动（手指级精细动作，禁止）；"
    "两人说话后面部表情恢复与静图一致…（长段表情锁定，禁止）；"
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
      "motion_prompt": "窗边纱帘被微风轻轻掀起又落下，窗帘下摆轻微向右飘动后回摆，人物姿势保持不变"
    },
    {
      "segment_index": 2,
      "motion_prompt": "画面左边是灿灿，右边是昭昭。灿灿说话，同时微微点头后停止；昭昭说话，同时双肩轻轻耸起后停止。服装发型稳定，身高比例（昭昭比灿灿矮半个头）不变。镜头固定，不推近不拉远，两人全程在画面内。"
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
    "禁止新造画面外物体，禁止像素级光影闪烁，只写可观测物理位移，"
    "末尾写人物姿势保持不变；"
    "keyframe 写成「{角色}说话，同时…」粗粒度微动作（点头、耸肩、手掌小幅摆动），"
    "禁止手指级精细动作与长段表情锁定，"
    "说话人身体姿态/站姿/头部朝向保持不变，动作幅度极小，禁止写具体厘米/角度；"
    "禁止自编起止秒数（系统按 TTS 注入），"
    "末尾镜头固定不推近不拉远（禁止变焦放大），禁大位移、禁纯环境晃动套话；"
    "各段互不重复，禁止套话。"
)


# ── L2 语义审核 prompt（LLM reviewer） ──

_IMAGE_PROMPT_REVIEW_SYSTEM = (
    "你是文生图(T2I)提示词审核员。逐条审查每段提示词，只报告确定存在的问题，"
    "不确定的一律不报（宁少勿乱）。"
    "审查维度："
    "①contradictions 自相矛盾（同一物体两处描述状态/位置/数量不一致，"
    "如甲处说X在A处、乙处说X在B处；甲处说散开、乙处说打死结）；"
    "②redundancies 冗余（同一短语重复 3 次以上）；"
    "③unpaintable 不可画（抽象指令/时间推移/多格叙事等无法画成单帧的内容）。"
    "输出 JSON：{\"reviews\": [...]}，每项含 segment_index、issues；"
    "issues 每项含 kind(contradiction/redundancy/unpaintable)、detail（引用原文短语）、"
    "contradiction 时另含 pair=[甲短语,乙短语]。没有问题的段落不要输出。"
)


def build_image_prompt_review_prompts(
    script: dict[str, Any],
    *,
    segment_indices: list[int] | None = None,
) -> dict[str, str]:
    """L2 审核：拼装好的 image_prompt + 本段台词，交 LLM reviewer 找语义矛盾。"""
    segments = script.get("segments") or []
    wanted = (
        {int(i) for i in segment_indices} if segment_indices is not None else None
    )
    lines: list[str] = []
    for seg in segments:
        idx = int(seg.get("segment_index") or 0)
        if wanted is not None and idx not in wanted:
            continue
        dialogue = " ".join(
            f'{d.get("speaker")}:"{d.get("text")}"'
            for d in (seg.get("dialogue") or [])
            if d.get("speaker") and d.get("text")
        )
        prompt = str(seg.get("image_prompt") or "")
        lines.append(
            f"segment {idx}: dialogue={dialogue!r}; image_prompt={prompt!r}"
        )
    user = "请审查以下各段文生图提示词：\n" + "\n".join(lines)
    return prompt_step("image_prompt_review", _IMAGE_PROMPT_REVIEW_SYSTEM, user)


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
