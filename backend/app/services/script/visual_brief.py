"""分镜画面概述规则与构建函数。"""

from __future__ import annotations

# ── JSON 样例 ─────────────────────────────────────────────────────

_VISUAL_BRIEF_JSON_EXAMPLE_FULL = """{
  "segments": [
    {"segment_index": 1, "visual_brief": "画面主旨与关键视觉（80-150字）", "visual_mode": "static_motion"},
    {"segment_index": 2, "visual_brief": "画面主旨", "visual_mode": "static_motion"}
  ]
}

注意：segments 须覆盖输入的每一段，segment_index 一一对应；不要修改各段 text。"""

_VISUAL_BRIEF_JSON_EXAMPLE_PARTIAL = """{
  "segments": [
    {"segment_index": 2, "visual_brief": "画面主旨与关键视觉（80-150字）", "visual_mode": "static_motion"}
  ]
}

注意：仅输出标记为【需生成】的 segment；【仅上下文】无需输出；不要修改各段 text。"""


# ── builders（常量须在上方）───────────────────────────────────────

from typing import Any
import re

from app.utils.job_info import (
    CONTENT_STYLE_DAILY_STORY,
)

from app.services.script.prompt_common import (
    append_supplementary_to_user,
    json_output_clause,
    prompt_step,
    resolve_script_profile,
    supplementary_system_clause,
)
from app.services.script.voiceover_standard.styles import resolve_style_rules


_DAILY_VISUAL_ROLE = "你是日常亲子对话短剧的分镜画面设计师。"

_VISUAL_BRIEF_CONTENT_RULE = (
    "visual_brief 为该镜画面描述（80-150 字）：写清视觉主旨、关键动作或对比关系、"
    "场景类型与氛围，帮助后续扩写文生图提示词；"
    "不写镜头焦距、光线方向、材质参数等细节。"
)

# daily：visual_brief 直接进入规则拼装 image_prompt，不再二次 LLM 扩写
_DAILY_VISUAL_BRIEF_CONTENT_RULE = (
    "visual_brief 为该镜核心场景描述（100-200 字），将直接拼入文生图提示词，"
    "写成一段连贯中文，写满可出图细节（地点陈设、人物动作表情、冲突道具融在正文里）。"
    "画风/外貌/口型/光线/景别由系统补全，brief 只写本镜可见的场景与动作。"
    "【场景定稿】分镜1必须先写一句完整场景定稿，按"
    "「地点 → 主体陈设位置 → 陈设样式 → 背景」顺序："
    "地点与 setting 一致；花盆等主体陈设写明摆放位置与颜色材质"
    "（如「花盆放在阳台地面、画面中央偏右，砖红色陶土花盆」）；"
    "植物写明品种/颜色/形态（如「花盆里一株盛开的红色月季花，"
    "大朵饱满、花瓣层叠、叶片翠绿完整」），禁止只写「红花/花/植物」；"
    "托盘等承托物写明位于正下方（如「花盆正下方是浅灰色圆形托盘」）；"
    "背景写明可见陈设（如「背景是阳台栏杆和几盆绿植」）；"
    "会移动/被拿起的核心冲突道具（浇花水壶、相框、蛋糕、薯片等）"
    "不写在场景定稿的主体陈设句里，只写在状态句/持物动作句；"
    "固定陈设（花盆、托盘、沙发、茶几等）才进场景定稿句。"
    "本镜已写人手持/递出某物时，场景陈设句禁止再出现同一物"
    "（禁止「桌上摊着A和B」同时又「右手握着B」；桌上只留未被拿起的物件）。"
    "浇花水壶示例：只在持物角色动作句写「昭昭右手握着一把蓝色塑料浇花水壶（宽口短嘴）」；"
    "场景句只写花盆、托盘、水渍、背景，禁止再出现「水壶」字样。"
    "后续分镜沿用分镜1定稿的地点、固定陈设样式与背景（文字保持一致），"
    "但冲突道具的状态/位置句必须按本镜剧情重写，禁止整句照抄分镜1；"
    "禁止用「背景同分镜1/场景同前」等引用句代替。"
    "【道具接触】道具必须与手或承托面明确接触，禁止悬空/漂浮/停在半空："
    "浇花水壶只允许在持物角色动作句中出现一次，"
    "写明手握壶柄、壶身与手接触，另一只手托壶底或自然下垂；"
    "花盆放在地面，托盘在花盆正下方；"
    "只有尚未交接时才可以写「手指悬空未接触水壶」。"
    "【冲突道具状态】本片 setting 与台词点名的核心冲突道具"
    "（如浇花水壶、蛋糕、薯片）必须每镜写清当前状态，"
    "首次出现时确定完整品类与款式并全片沿用："
    "品类按台词定全（台词有电视/看动画片/看新闻则写「电视遥控器」，禁止只写「遥控器」），"
    "款式写颜色+形状（如「黑色长方形」「蓝色塑料宽口短嘴」），"
    "禁止中途变换样式或品类；"
    "状态随剧情单向推进，禁止所有分镜写成同一状态；"
    "状态句放在地点句之后；"
    "道具在本镜发生位移/状态变化时，本镜必须写变化后的新状态，"
    "禁止沿用上一镜或分镜1的旧状态句；"
    "同一镜内道具只能有一种位置/状态，禁止场景句与动作句自相矛盾"
    "（如场景句写「茶几上立着摔裂的相框」、动作句又写「相框摔在地上」）；"
    "掉落/破碎类示例：相框滑落镜写「客厅，摔裂的相框从昭昭手中滑落摔向地面，旁边是扫帚和簸箕」，"
    "落地后写「客厅，摔裂的相框掉在地上，旁边是扫帚和簸箕」，"
    "后续保持地上/碎片状态，禁止回写「茶几上立着…」。"
    "【场景分层】固定家具与地面道具分层写：家具句只写台面状态"
    "（如「沙发和茶几上没有任何物品，表面整洁」），"
    "道具位置句单独锚定地面（如「木地板上散落着摔裂的相框和玻璃碎片，扫帚和簸箕倒在一旁」）；"
    "道具已掉落/破碎时，禁止写「A和B之间+道具名」这类把道具引向家具台面的措辞；"
    "用强状态动词（散落、倒在一旁、翻倒在地、横卧）代替「在」。"
    "冲突道具全片只有一件：写「一个/唯一一个」限定（如「一个摔裂的相框」），"
    "禁止出现多个同款（如满地都是相框、相框们）；玻璃碎片等残骸是同一件道具的附属，"
    "不构成第二件。"
    "只有台词或 setting 点名的道具才写，"
    "禁止新增第二件同款道具或无关杂物。"
    "【剧情连续性】先按全片 narration 明确本镜剧情拍"
    "（如：递壶→交接→浇水），再写画面；"
    "相邻镜须因果承接：上一镜的持物/手势/道具状态本镜要延续或明确变化，"
    "禁止道具凭空出现/消失；全片固定左昭昭右灿灿；"
    "每镜开头可用「接上一镜/此时」承接，避免每镜都像独立截图；"
    "两人始终同框清晰入画，禁止把其中一人写成背景模糊/远景；"
    "禁止括号内心理/解释说明（如「其实是小块，但昭昭认为大」），只写可见画面。"
    "【安全】儿童角色不得持真实刀具/锐器；剧情涉及刀时统一写「塑料蛋糕刀」"
    "（蛋糕刀样式，非水果刀/餐刀），禁止「水果刀」「餐刀」「锋利刀具」等表述；"
    "剧情涉及剪刀时全片同一把，写「剪刀」（儿童塑料圆头），"
    "禁止改写成金属锋利剪或另编尺子/铅笔。"
    "画面涉及门（含门口/门外）时，门一律写成「一扇单开门」"
    "（单扇门：只有一块完整门板，没有分成两扇），"
    "门外是柔和的白色亮光；门被风吹得更开时须写明向内开；"
    "半开状态写「门板边缘与门框之间露出一道空隙」，禁止写「门缝」一词。"
    "【风与头发】画面涉及风吹/风灌时，风只吹本镜在场角色的头发："
    "谁说头发被风吹乱，风就吹谁的头发（与台词一致）；台词未提头发时，"
    "只吹离门口最近、搭着/扶着门的角色"
    "（正向写明「门外的风吹起昭昭的黑色短发，发丝向上飘起」），"
    "发丝必须连着头皮；"
    "风从门外吹进室内时，头发须顺着风向背离门口飘"
    "（如昭昭在门左侧、门在右侧，短发向左飘起），"
    "禁止逆风朝门口方向飘；"
    "禁止写「马尾被吹起」「碎发乱飞」「发丝/马尾从门缝飘入」"
    "等易被画成独立飘浮头发的表述。"
    "【站位】两人：「画面左边是A，右边是B」，再按左→右写动作；"
    "三人默认「从左到右是昭昭、妈妈、灿灿」并写清每人动作；"
    "昭昭与灿灿同框默认左昭昭、右灿灿，全片尽量固定；"
    "站位用参照物加画面方位正面写（茶几前/沙发边/画面左边），"
    "不用「对面/她右侧/他左侧」等相对虚词；"
    "speakers 列出的角色都要入画，未发言者写旁听姿态。"
    "【人物关系】对标本段 dialogue：质问方进攻（瞪/皱眉 + 指或叉腰二选一），"
    "辩解方防御（摊手/耸肩/撇嘴）；每人只定格一组姿势（冲突最强一瞬）；"
    "禁止同一人同时写「左手叉腰+右手指」。"
    "【手部总账与互斥】本镜角色数×2=可见手总数，每角色恰好两只手。"
    "每人只准一个主动手部动作，另一只必须写「自然下垂/放在身侧」；"
    "持物角色：一只手握物，另一只下垂，禁止再写指/叉腰/按纸；"
    "持物角色禁止写任何「双手」动作（双手抱头/双手捂脸/双手撑膝/双手叉腰等），"
    "双手动作与单手握物互斥，会画成三只手；"
    "无持物时指、叉腰、摊手三选一，不要叠「身体前倾」；"
    "不要写易诱发多手的撑桌/抱胸/交叉等动作；"
    "禁止同一角色同时出现两组手部动作（如双手撑桌又另有手拿道具）；"
    "禁止把 A 角色的动作写成 B 角色的动作；"
    "持物人与伸手人必须分离：非持物角色伸向道具时写明「手指悬空，未接触道具」，"
    "持物角色写明「手指包裹道具」；"
    "递出/递给须写「手指仍接触该物」，禁止写成已离手或回到桌上。"
    "【人物】写眉眼与肢体（瞪圆眼、皱眉、撇嘴、前倾、摊手等），强度对齐台词语气；"
    "口型由系统注入，但 brief 的表情须与说话兼容："
    "首说话人（dialogue 第一句）正在说话，可写「撇嘴说话」「咧嘴笑着说」「笑眯眯地说话」等，"
    "禁止写「闭嘴」「不开口」「光笑不说话」等与说话冲突的表情；"
    "其他角色禁止写说话/反驳/大喊/开口等，只用眉眼肢体表达情绪；"
    "【硬性】非首说话人出现「说话/反驳/大喊/开口/嘴巴张开」任一词汇即整段不合格，必须重写。"
    "【持物一致性】同一道具的持物手全片统一（默认右手持物），禁止左右手跳变；"
    "持物手与相邻镜保持一致。"
    "已握在手里的道具不要再写桌上/纸旁/旁边还有该物，桌上只写未持物的陈设；"
    "道具名优先只在持物句出现一次；先写「画面左边/右边是谁」，再写持物人动作；"
    "非持物人看向持物人，禁止写「盯着剪刀/看着水壶」等盯着物。"
    "【道具】冲突道具用台词已出现的物件与状态；"
    "衣物类用「衣服/衣物堆/皱成一团的衣服」泛称（粉色卫衣/蓝色T恤是角色身上穿的，不当道具）。"
    "事实对齐台词：说皱就画「原本叠好、现已揉皱」；说只碰一下就画无辜摊手。"
    "【开场】segment_index=1 且特写时，定格冲突峰值姿势，表情再夸张一档。"
    "正例（对白：灿灿抱怨刚叠好的衣服皱成一团；昭昭说只碰一下没弄皱）："
    "'客厅沙发上，原本叠好的衣服已被揉皱成一团；"
    "画面左边是昭昭，右边是灿灿；"
    "昭昭双手摊开耸肩，撇着嘴角一脸无辜；"
    "灿灿右手食指指向身前那团皱衣服，左手叉腰，瞪圆眼睛、皱着眉；"
    "茶几上放着遥控器和空水杯。'"
)

_EMOTION_RULE_DIALOGUE = (
    "情绪须对标台词语气强度（争吵时表情激烈如瞪眼皱眉撇嘴、温和平静时表情放松）。"
)

_EMOTION_RULE_NARRATION = (
    "氛围与本段口播语气一致，点到即可，勿夸张表演或堆砌表情描写。"
)

_DAILY_SPEAKER_RULE = (
    "【角色入画】可入画 = 本段须入画角色（若输入含 speakers 字段则以其为准）"
    " = 本段 dialogue 发言 ∪ 台词写明当场在场 ∪ 同场粘性角色"
    "（setting 已点名，或前面分镜已出场的角色，后续镜继续保留）。"
    "speakers 列出的角色必须全部入画；未发言者写旁听/在场姿态"
    "（坐着吃饭、看向说话人、夹菜等），禁止消失。"
    "禁止无故旁观/路过/另一房间凑人数。"
    "仅转述或询问去向不算新授予入画（如「妈妈说过…」「妈妈呢？」）；"
    "但若台词明确是「躲着/瞒着/别让妈妈看见/别被妈妈发现」等避开妈妈视线，"
    "则妈妈本镜必须离场，不得因同场粘性继续入画。"
    "台词说「妈出来了/进来了」但本镜 speakers 不含妈妈时："
    "只画空门口（门口无人），禁止画路人/半张脸；"
    "禁止写「盯/瞟/望向门口等人」——改写角色互看或看向道具。"
    "若该段无人发言且 speakers 为空，禁止出现昭昭/灿灿/妈妈等人像，只写场景。"
)

_DAILY_SETTING_RULE = (
    "【地点锚点】全片 setting 已给定（如客厅）；"
    "每镜 visual_brief 落在该地点或其可见角落（沙发/茶几/书桌/门口）。"
)

_BODY_PART_OBJECT_RE = re.compile(
    r"^(?:一?只?)?(?:右|左)?(?:手|脚|手臂|腿|手指|手掌|头发|发丝|马尾)$"
    r"|^.+的(?:手|脚|头发)$"
)


def is_body_part_object(obj: str) -> bool:
    """身体部位不是可持道具；写入 object_states 会诱发断肢漂浮（如「手中放着一只手」）。"""
    o = (obj or "").strip()
    if not o:
        return False
    return bool(_BODY_PART_OBJECT_RE.match(o))


_HAND_INJURY_SETTING_RE = re.compile(r"手(?:上有伤|背.{0,2}伤|.{0,2}肿)|肿.{0,4}手")
_HAND_INJURY_DIALOGUE_RE = re.compile(
    r"手.{0,4}肿|肿成馒头|你这手|手都|擦擦药|擦药"
)
_HAND_BANDAGE_DIALOGUE_RE = re.compile(r"擦擦药|擦药|包扎|缠(?:上)?纱布|创可贴|缠绷带")
_HAND_INJURY_FORM_RE = re.compile(r"红肿|淤青|擦伤|肿胀|肿")
_HAND_BANDAGED_RE = re.compile(r"纱布|绷带|创可贴|包扎|缠好")


def _segment_dialogue_text(seg: dict) -> str:
    parts = [str(seg.get("text") or "")]
    for row in seg.get("dialogue") or []:
        if isinstance(row, dict):
            parts.append(str(row.get("text") or row.get("line") or ""))
    return "".join(parts)


def hand_injury_story_active(
    setting: str | None,
    segments: list[dict] | None = None,
) -> bool:
    if setting and _HAND_INJURY_SETTING_RE.search(setting):
        return True
    if segments:
        return bool(_HAND_INJURY_DIALOGUE_RE.search(_dialogue_blob(segments)))
    return False


def _injured_hand_side_from_object(obj: str) -> str:
    if "左" in obj:
        return "左手"
    if "右" in obj:
        return "右手"
    return "右手"


def _hand_injury_form_phrase(form: str) -> str:
    form = (form or "").strip()
    if form and _HAND_INJURY_FORM_RE.search(form):
        return form
    return "红肿淤青略肿"


def _first_bandage_segment_index(segments: list[dict]) -> int | None:
    for seg in sorted(
        segments, key=lambda s: int(s.get("segment_index") or 0)
    ):
        if _HAND_BANDAGE_DIALOGUE_RE.search(_segment_dialogue_text(seg)):
            return int(seg.get("segment_index") or 0)
    return None


def _hand_injury_phase(seg: dict, bandage_from: int | None) -> str:
    idx = int(seg.get("segment_index") or 0)
    if bandage_from is not None and idx >= bandage_from:
        return "bandaged"
    return "swollen"


def _subject_has_hand_injury_visual(action: str) -> bool:
    text = action or ""
    return bool(_HAND_INJURY_FORM_RE.search(text) or _HAND_BANDAGED_RE.search(text))


def _strip_swollen_hand_phrases(action: str, *, injured_side: str) -> str:
    covering = "左" if injured_side == "右手" else "右"
    text = action or ""
    text = re.sub(rf"，?{covering}手[^，]*捂[^，]*{injured_side}[^，]*", "", text)
    text = re.sub(r"，?[^，]*(?:红肿|淤青|肿胀)[^，]*", "", text)
    return text.strip("，, ")


def _enrich_subject_hand_injury_swollen(
    sub: dict,
    *,
    injured_side: str,
    form_phrase: str,
) -> None:
    action = str(sub.get("action") or "").strip()
    if _HAND_INJURY_FORM_RE.search(action):
        return
    covering = "左" if injured_side == "右手" else "右"
    injury_clause = f"{injured_side}手背{form_phrase}"
    if re.search(rf"{covering}手.*捂.*{injured_side}", action):
        sub["action"] = f"{action}，{injury_clause}".strip("，")
    elif "捂" in action and "手" in action:
        sub["action"] = f"{action}，{injury_clause}".strip("，")
    elif action:
        sub["action"] = (
            f"{covering}手捂住{injured_side}手背，{injury_clause}，{action}"
        )
    else:
        sub["action"] = f"{covering}手捂住{injured_side}手背，{injury_clause}"


def _enrich_subject_hand_injury_bandaged(
    sub: dict,
    *,
    injured_side: str,
    applying: bool,
) -> None:
    action = _strip_swollen_hand_phrases(
        str(sub.get("action") or "").strip(),
        injured_side=injured_side,
    )
    if applying:
        clause = (
            f"灿灿正给昭昭{injured_side}缠白色纱布包扎，"
            f"{injured_side}连着昭昭身体"
        )
    else:
        clause = f"{injured_side}缠着白色纱布绷带"
    if _HAND_BANDAGED_RE.search(action):
        sub["action"] = action
        return
    sub["action"] = f"{clause}，{action}".strip("，") if action else clause


def _enrich_subject_hand_injury(
    sub: dict,
    *,
    injured_side: str,
    form_phrase: str,
    phase: str = "swollen",
    applying_bandage: bool = False,
) -> None:
    if phase == "bandaged":
        _enrich_subject_hand_injury_bandaged(
            sub,
            injured_side=injured_side,
            applying=applying_bandage,
        )
        return
    _enrich_subject_hand_injury_swollen(
        sub,
        injured_side=injured_side,
        form_phrase=form_phrase,
    )


def _subject_action_has_hand_injury(action: str) -> bool:
    return _subject_has_hand_injury_visual(action)


def _refresh_visual_brief_from_subjects(seg: dict) -> None:
    subjects = seg.get("visual_subjects")
    if isinstance(subjects, list) and subjects:
        seg["visual_brief"] = render_visual_subjects(subjects)


def migrate_body_part_injury_to_subjects(seg: dict, st: dict) -> None:
    """object_states 误写身体部位时，把 form 迁回 visual_subjects.action。"""
    obj = str(st.get("object") or "").strip()
    if not is_body_part_object(obj) or "手" not in obj:
        return
    holder = str(st.get("holder") or "").strip() or "昭昭"
    injured_side = _injured_hand_side_from_object(obj)
    form_phrase = _hand_injury_form_phrase(str(st.get("form") or ""))
    subjects = seg.get("visual_subjects")
    if not isinstance(subjects, list):
        return
    for sub in subjects:
        if isinstance(sub, dict) and str(sub.get("name") or "").strip() == holder:
            _enrich_subject_hand_injury(
                sub,
                injured_side=injured_side,
                form_phrase=form_phrase,
                phase="swollen",
            )
            break
    _refresh_visual_brief_from_subjects(seg)


def promote_hand_injury_across_segments(
    segments: list[dict],
    setting: str | None = None,
) -> None:
    """全片手伤：擦药前红肿，擦药镜及之后包扎（不写断肢道具）。"""
    if not hand_injury_story_active(setting, segments):
        return
    bandage_from = _first_bandage_segment_index(segments)
    swollen_form = "红肿肿胀"
    for seg in segments:
        speakers = [str(s) for s in (seg.get("speakers") or []) if str(s).strip()]
        if "昭昭" not in speakers:
            continue
        subjects = seg.get("visual_subjects")
        if not isinstance(subjects, list):
            continue
        phase = _hand_injury_phase(seg, bandage_from)
        applying = bool(
            phase == "bandaged"
            and _HAND_BANDAGE_DIALOGUE_RE.search(_segment_dialogue_text(seg))
        )
        seg["_hand_injury_phase"] = phase
        for sub in subjects:
            if isinstance(sub, dict) and str(sub.get("name") or "").strip() == "昭昭":
                _enrich_subject_hand_injury(
                    sub,
                    injured_side="右手",
                    form_phrase=swollen_form,
                    phase=phase,
                    applying_bandage=applying,
                )
        _refresh_visual_brief_from_subjects(seg)


def daily_hand_injury_s4_clause(seg: dict, setting: str | None = None) -> str:
    """T2I 兜底：手伤剧情但 vb 仍无伤势描写时，按阶段补红肿或包扎。"""
    speakers = [
        str(s).strip()
        for s in (seg.get("speakers") or [])
        if str(s).strip()
    ]
    if "昭昭" not in speakers:
        return ""
    if not hand_injury_story_active(setting, [seg]):
        return ""
    vb = str(seg.get("visual_brief") or "")
    phase = str(seg.get("_hand_injury_phase") or "swollen")
    if phase == "bandaged":
        if _HAND_BANDAGED_RE.search(vb):
            return ""
        if _HAND_BANDAGE_DIALOGUE_RE.search(_segment_dialogue_text(seg)):
            return (
                "灿灿正给昭昭右手缠白色纱布包扎，"
                "昭昭右手连着身体，不是漂浮断肢"
            )
        return "昭昭右手缠着白色纱布绷带，双手连着昭昭身体"
    if _HAND_INJURY_FORM_RE.search(vb):
        return ""
    return (
        "昭昭右手手背红肿肿胀，左手捂住右手手背，"
        "双手连着昭昭身体，不是漂浮断肢"
    )


_DAILY_OBJECT_STATE_RULE = (
    "【object_states】每段另输出 object_states 数组：本片锁定活动道具在本镜的最终状态，"
    "每项含 object、count、form、holder、position 五字段："
    "object=道具名（本片 setting/台词点名的活动道具，与【物品锁定】列表对齐，如粉鞋/相框/水壶）；"
    "核心冲突道具必须写完整品类：台词/setting 有电视相关词（电视/看动画片/看新闻/霸占电视）时"
    "写「电视遥控器」，禁止只写「遥控器」；空调/风扇遥控器同理写全品类；"
    "身体部位（手/脚/头发等）不是道具，禁止写入 object_states；"
    "伤势/红肿/淤青写在 visual_subjects 的 action/expression"
    "（如「左手捂住右手手背，右手红肿」），不要写「一只手」当物件；"
    "台词出现擦药/包扎后，后续镜昭昭右手改写成缠着白色纱布绷带，不再写红肿；"
    "count=数量词（两只/一个/一把等）；"
    "form=本镜最终状态（如鞋带散开/鞋带打成死结两只鞋底贴在一起/摔裂掉在地上）；"
    "核心冲突道具首次出现时在 form 里确定款式并全片沿用："
    "写颜色+形状（如「黑色长方形，两端被两人各握一端」"
    "/「蓝色塑料宽口短嘴」，不再重复品类名），后续镜重复该款式，禁止中途变换样式；"
    "holder=持有人角色名，无人持有写「无」；"
    "position=具体位置（地垫中央/茶几上/灿灿双手中）；"
    "未变化道具沿用上一镜状态原样照写；状态变化必须与剧情一致；"
    "同一道具同一镜只能有一条状态；禁止前后镜状态无理由回退。"
)

_DAILY_VISUAL_SUBJECTS_RULE = (
    "【visual_subjects】每段输出 visual_subjects 数组，不再输出 visual_brief 自由文本："
    "为本段每个入画角色各写一条 {name, posture, action, expression}："
    "name=角色名（昭昭/灿灿/妈妈，必须在本段 speakers 内，禁止写未授权角色）；"
    "posture=姿态与位置，≤12字，写清参照锚点（站在茶几前/坐在沙发上/蹲在画面左边地垫旁）；"
    "action=一个主动作，≤15字；手部互斥：每人只准一组手部动作，"
    "对称动作可写「双手叉腰/双手捏住」，非对称动作只写主动手、另一只手自然下垂；"
    "持物时写明哪只手握物、道具与手接触；持物角色禁止再写任何「双手」动作"
    "（双手抱头/双手捂脸/双手撑膝等），单手握物+双手动作=三只手，整段不合格；"
    "expression=眉眼与嘴角静态，≤10字（如皱眉瞪眼/撇嘴/眯眼笑）；"
    "禁止写场景陈设样式、角色外貌发型服装、道具状态与数量、口型开合；"
    "expression 禁止出现「说话/开口/大喊」等口型词，口型由系统统一注入；"
    "其他角色禁写说话/反驳类表情，只用眉眼肢体表达情绪；"
    "情绪对标台词语气强度；每人只定格一组姿势（冲突最强一瞬）。"
    "【人物关系】对标本段 dialogue：质问方进攻（瞪/皱眉 + 指或叉腰二选一），"
    "辩解方防御（摊手/耸肩/撇嘴）；禁止把 A 角色的动作写成 B 角色的动作。"
    "【门】画面涉及门（含门口/门外）时，门一律写成「一扇单开门」"
    "（单扇门：只有一块完整门板，没有分成两扇），门外是柔和的白色亮光；"
    "半开状态写「门板边缘与门框之间露出一道空隙」，禁止写「门缝」一词。"
    "【道具】冲突道具用台词已出现的物件与状态；"
    "衣物类用「衣服/衣物堆」泛称（粉色卫衣/蓝色T恤是角色身上穿的，不当道具）；"
    "事实对齐台词：说皱就画「刚叠好的衣服现已揉皱成一团」，说只碰一下就画无辜摊手。"
    "【站位】两人写「画面左边是A，右边是B」，全片固定左昭昭右灿灿；"
    "三人同框写「从左到右是昭昭、妈妈、灿灿」；"
    "站位用参照物加方位正面写（茶几前/沙发边/画面左边），"
    "相对位置写具体锚点（如妈妈站在茶几前、昭昭站在沙发边）；"
    "speakers 列出的角色都要入画，未发言者写旁听姿态。"
    "【安全】儿童角色不得持真实刀具/锐器；剧情涉及刀时统一写「塑料蛋糕刀」，"
    "涉及剪刀时全片同一把写「剪刀」（儿童塑料圆头）。"
    "【风与头发】画面涉及风吹时，风只吹本镜在场角色的头发："
    "谁说头发被风吹乱，风就吹谁的头发（与台词一致，写在对应角色的 action 里）；"
    "台词未提头发时，只吹离门口最近、搭着/扶着门的角色；"
    "发丝必须连着头皮；风从门外吹进室内时，头发顺风背离门口飘；"
    "禁止写「马尾被吹起」「碎发乱飞」「发丝/马尾从门缝飘入」等易被画成独立飘浮头发的表述；"
    "发丝连头皮等细节由系统注入提示词（系统注入示例：「门外的风吹起昭昭的黑色短发，"
    "发丝向上飘起」），LLM 只需在 action 里点出「头发被风吹起」。"
    "【开场】segment_index=1 且特写时，定格冲突峰值姿势，表情再夸张一档。"
    "【scene_anchors】每段另输出 scene_anchors 数组：本镜场景的大型固定物名词，"
    "1-4个（如沙发/茶几/地垫/水槽/滑梯），只写名词不写材质样式，"
    "地点与 setting 一致；可移动小物件（遥控器/水杯/书包）不写；"
    "台词/setting 涉及电视相关词（电视/看动画片/看新闻/霸占电视/电视柜）时，"
    "scene_anchors 必须含「电视」（画面要画得出一台电视，供指电视/看电视）；"
    "全片同一场景时各段保持一致。"
    "【cast】每段另输出 cast 数组：本镜额外在场且非常态的角色名。"
    "昭昭、灿灿是固定主角，默认每镜都在，不要写进 cast；"
    "只把「按剧情需要才入镜」的角色（如妈妈）在真正登场时写进 cast。"
    "妈妈入镜仅当本镜台词含 speaker=妈妈，或台词明文写明妈妈当场可见动作/状态；"
    "偷吃/藏匿/怕被撞破、台词只是转述或询问去向（「妈说过/妈妈在哪」）、「躲着/瞒着/别让妈妈"
    "看见」时，妈妈不在场，cast 输出空数组。"
    "无额外在场角色时 cast 为空数组 []。"
)

_VISUAL_BRIEF_JSON_EXAMPLE_DAILY = """{
  "segments": [
    {"segment_index": 1, "visual_mode": "static_motion",
     "cast": [],
     "visual_subjects": [
       {"name": "昭昭", "posture": "蹲在地垫旁", "action": "双手捏住鞋带", "expression": "皱眉用力"},
       {"name": "灿灿", "posture": "站在地垫旁", "action": "右手叉腰", "expression": "瞪眼"}
     ],
     "object_states": [{"object": "粉鞋", "count": "两只", "form": "鞋带散开", "holder": "无", "position": "地垫中央"}],
     "scene_anchors": ["地垫", "沙发", "茶几"]}
  ]
}

注意：segments 须覆盖输入的每一段，segment_index 一一对应；不要修改各段 text。"""

_VISUAL_BRIEF_JSON_EXAMPLE_DAILY_PARTIAL = """{
  "segments": [
    {"segment_index": 2, "visual_mode": "static_motion",
     "cast": ["妈妈"],
     "visual_subjects": [
       {"name": "昭昭", "posture": "蹲在地垫旁", "action": "双手摊开", "expression": "表情惊讶"},
       {"name": "灿灿", "posture": "蹲在地垫上", "action": "双手拎起粉鞋", "expression": "皱眉"}
     ],
     "object_states": [{"object": "粉鞋", "count": "两只", "form": "鞋带打成死结", "holder": "灿灿", "position": "灿灿双手中"}],
     "scene_anchors": ["地垫", "沙发", "茶几"]}
  ]
}

注意：仅输出标记为【需生成】的 segment；【仅上下文】无需输出；不要修改各段 text。"""

_MOM_DIALOGUE_RULE = (
    "【角色约束】妈妈可入画当且仅当："
    "本段 dialogue 含 speaker=\"妈妈\"，或台词写明妈妈当场可见动作/状态"
    "（如躺着刷手机、手里亮屏）；二者皆无则禁止妈妈入画"
    "（旁观、路过、另一房间等都不允许）。"
    "仅转述旧话或询问去向（如「妈妈说过…」「妈妈呢？」）不算在场，不可入画。"
    "若台词是「躲着妈妈」「瞒着妈妈」「别让妈妈看见/发现」等，"
    "表示妈妈不在当前视线内，禁止把妈妈画到人物面前。"
    "「妈出来了/进来了」若本镜未把妈妈列入 speakers："
    "门口写「单开门半开，门外柔和白光」，只画空门口，不写路人或第三张脸。"
    "不要为了让妈妈入画而改写/强加台词。"
)

# 角色身上固定着装：禁止当道具（蓝T恤=昭昭穿的，粉卫衣=灿灿穿的）
_DAILY_OUTFIT_PROP_REWRITES: tuple[tuple[str, str], ...] = (
    ("粉色卫衣、蓝色T恤等", "衣服"),
    ("蓝色T恤、粉色卫衣等", "衣服"),
    ("粉色卫衣", "衣服"),
    ("蓝色T恤", "衣服"),
    ("蓝色短袖T恤", "衣服"),
    ("米色上衣", "衣服"),
    ("彩色衣物", "衣服"),
    ("彩色T恤", "衣服"),
)

_DAILY_BRIEF_LABEL_RE = re.compile(
    r"(?:冲突道具|地点|人物|道具|场景|主体|构图|光照)\s*[：:]"
)

# visual_brief 中「昭昭右手…」类单角色动作句（单帧只保留每人首句）
_POSE_CLAUSE_START_RE = re.compile(
    r"^(昭昭|灿灿|妈妈)(?:[，,]|右手|左手|双手|身体|瞪|点|叉|摊|耸|仰头|点头|张嘴|比划)"
)

# brief 禁写口型（拼装层会硬加「微微张嘴」）；顺带剥语气词
_MOUTH_AND_TONE_RE = re.compile(
    r"(?:嘴巴大张|张大嘴|嘴巴张开|嘴巴明显张开|嘴巴微张|张着嘴|微微张嘴|正在开口说话|"
    r"嘴巴闭合不露齿|嘴巴完全闭合不露齿|嘴巴闭合|不露齿|"
    r"语气\S{1,4})"
)

# 句内双手互斥：双手叉腰 + 右手指/比划 → 左手叉腰
_RIGHT_HAND_ACTION_RE = re.compile(r"右手(?:指|食指|指向|比划)")

# 默认背景陈设：仅归一「纯默认陈设」句，其余（含冲突/装饰道具）一律保留
_DEFAULT_TABLE_SET = "茶几上放着遥控器和空水杯"
_TABLE_SET_CLAUSE_RE = re.compile(r"茶几上(?:放着|摆着)[^。；]*")
# 默认陈设槽位值（来自 prompt 默认模板，非开放词表，不随主题扩展）
_DEFAULT_TABLE_ITEMS = ("遥控器", "空水杯")
# 陈设句框架词（短语级剥离，勿用单字字符类——会把「茶」等道具字误删）
_TABLE_FRAME_RE = re.compile(r"茶几上|放着|摆着|和|与|及|、|，|。|；|：|\s")

# 日故事全局角色事实（story 提示词已有，visual_brief 补齐，防性别/称呼错配）
_DAILY_CHARACTER_FACTS = (
    "【角色事实】昭昭=7岁弟弟（男孩）、灿灿=10岁姐姐（女孩）、妈妈=成年女性；"
    "描述中禁止把昭昭写成妹妹/女孩、把灿灿写成弟弟/男孩、把妈妈写成阿姨等错配称呼。"
)

# 固定陈设词表：分镜1 出现过即视为本片常驻陈设，后续镜缺失时强制补回，
# 防止出图质检兜底重写 visual_brief 时把沙发/茶几等固定家具写丢
_DAILY_FIXED_FURNITURE = (
    "沙发", "茶几", "餐桌", "书桌", "柜子", "柜顶", "书架", "电视柜",
    "床头柜", "鞋柜", "凳子", "椅子", "床", "花盆", "托盘",
    "扫帚", "簸箕", "水桶", "拖把", "垃圾桶",
)


def _daily_fixed_furniture(segments: list[dict]) -> tuple[str, ...]:
    """取分镜1 已建立的固定陈设（家具/常驻道具），只含词表内名词。"""
    for seg in segments:
        if int(seg.get("segment_index") or 0) != 1:
            continue
        vb = str(seg.get("visual_brief") or "")
        return tuple(f for f in _DAILY_FIXED_FURNITURE if f in vb)
    return ()


# 杂物剥离用的已知名词（文具/零食等）。冲突物识别不靠这份名单，
# 而走 setting/台词容器句中心语（面前/碗里/端着）。
_LOCKABLE_PROPS: tuple[str, ...] = (
    "剪刀", "纸", "水壶", "相框", "蛋糕", "薯片", "酸奶",
    "饼干", "衣服", "衣物", "袜子", "鞋带", "洗手液",
    "尺子", "直尺", "铅笔", "橡皮", "文具", "彩笔",
    "书包", "本子", "书本", "杂志", "抱枕", "靠垫", "废纸",
)
_CLUTTER_ONLY_PROPS = frozenset(
    (
        "尺子", "直尺", "铅笔", "橡皮", "文具", "彩笔",
        "书包", "本子", "书本", "杂志", "抱枕", "靠垫", "废纸",
    )
)
_SCISSOR_ALIAS_RE = re.compile(r"(?:儿童)?(?:安全|塑料)?剪刀")
_EXTRA_PAPER_RE = re.compile(
    r"两张[^，。；;]{0,10}纸|另一张[^，。；;]{0,10}纸|几张废纸|几段剪下的纸边"
)


def _dialogue_blob(segments: list[dict]) -> str:
    parts: list[str] = []
    for seg in segments:
        for row in seg.get("dialogue") or []:
            if not isinstance(row, dict):
                continue
            parts.append(str(row.get("text") or row.get("line") or ""))
    return "".join(parts)


def _dialogue_rows_any(dialogue: list | None) -> list[dict]:
    rows: list[dict] = []
    for row in dialogue or []:
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _row_speaker_line(row: dict) -> tuple[str, str]:
    sp = str(row.get("speaker") or "").strip()
    line = str(row.get("line") or row.get("text") or "").strip()
    return sp, line


def _other_kid(speaker: str) -> str:
    if speaker == "昭昭":
        return "灿灿"
    if speaker == "灿灿":
        return "昭昭"
    return ""


_NAMED_CONTAINER_RE = re.compile(
    r"(昭昭|灿灿|妈妈)"
    r".{0,8}?"
    r"(面前|碗里|盘里|手里|手中|端着|捧着)"
    r"(?:那)?"
    r"(?:一盘|一碗|一块|几根|一根|一些|两块|一袋|一双)?"
    r"([\u4e00-\u9fa5]{1,8})"
)
_DEIXIS_CONTAINER_RE = re.compile(
    r"(你|我)(?:的)?"
    r"(碗里|盘里|手里|面前)"
    r"(?:那)?"
    r"(?:一盘|一碗|一块|几根)?"
    r"([\u4e00-\u9fa5]{1,8})"
)
_SETTING_SURFACE_RE = re.compile(
    r"(?:桌上|茶几上|地垫上)"
    r"(?:摊着|放着|摆着|立着)?"
    r"(?:一张|一把|一个|一双|两只)?"
    r"([^，。；]{1,14})"
)


def _valid_activity_prop(prop: str) -> str:
    key = _prop_key(prop)
    if not key or key in _PROP_NOUN_SKIP:
        return ""
    if key in _DAILY_FIXED_FURNITURE:
        return ""
    if key in ("客厅", "卧室", "厨房", "餐厅", "门口"):
        return ""
    return key


def extract_story_prop_holdings(
    setting: str,
    dialogue: list | None = None,
) -> list[tuple[str, str]]:
    """从 setting/台词容器句抽 (holder, prop)。不查道具名词名单。"""
    out: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()

    def _add(holder: str, raw: str) -> None:
        prop = _valid_activity_prop(raw)
        if not prop:
            return
        item = (holder, prop)
        if item in seen:
            return
        seen.add(item)
        out.append(item)

    for m in _NAMED_CONTAINER_RE.finditer(str(setting or "")):
        _add(m.group(1), m.group(3))
    for m in _SETTING_SURFACE_RE.finditer(str(setting or "")):
        _add("", m.group(1))
    for row in _dialogue_rows_any(dialogue):
        sp, line = _row_speaker_line(row)
        if not line:
            continue
        for m in _NAMED_CONTAINER_RE.finditer(line):
            _add(m.group(1), m.group(3))
        for m in _DEIXIS_CONTAINER_RE.finditer(line):
            who = m.group(1)
            raw = m.group(3)
            if who == "我":
                holder = sp if sp in {"昭昭", "灿灿", "妈妈"} else ""
            else:
                holder = _other_kid(sp)
            if holder:
                _add(holder, raw)
    return out


def extract_story_activity_props(
    setting: str,
    dialogue: list | None = None,
) -> set[str]:
    """本片活动道具名：容器句抽出的中心语（无白名单）。"""
    return {prop for _holder, prop in extract_story_prop_holdings(setting, dialogue)}


def bowl_container_owners(
    setting: str | None,
    dialogue: list | None = None,
) -> dict[str, str]:
    """容器句冲突物 → 碗主人。表示归谁的碗/盘，不是拿在手里。"""
    out: dict[str, str] = {}
    for holder, prop in extract_story_prop_holdings(setting or "", dialogue):
        if holder and prop:
            out[prop] = holder
    return out


def unbind_foreign_bowl_food_action(
    action: str,
    actor: str,
    owners: dict[str, str],
) -> str:
    """对方碗里的冲突物不要写进自己的动作句，否则出图会把食物画到自己面前。"""
    a = str(action or "")
    actor = str(actor or "").strip()
    if not a or not actor or not owners:
        return a
    for prop, who in owners.items():
        if not prop or who == actor or prop not in a:
            continue
        a = re.sub(
            rf"指着{re.escape(who)}面前的{re.escape(prop)}盘?",
            "伸手指向对面",
            a,
        )
        a = re.sub(rf"伸向{re.escape(prop)}盘?", "伸向对面的碗", a)
        a = re.sub(
            rf"{re.escape(who)}面前的{re.escape(prop)}盘?",
            "对面",
            a,
        )
        a = a.replace(f"{prop}盘", "对面")
        a = a.replace(prop, "")
    a = re.sub(r"[，,]{2,}", "，", a)
    return a.strip("，, ")


def enrich_setting_with_dialogue_props(
    setting: str,
    dialogue: list | None = None,
    *,
    contract_object: str = "",
) -> str:
    """setting 缺冲突物时，用台词容器句/契约 object 补持有落点。"""
    text = str(setting or "").strip()
    rows = _dialogue_rows_any(dialogue)
    holdings = list(extract_story_prop_holdings(text, rows))
    blob = "".join(_row_speaker_line(r)[1] for r in rows)
    obj = str(contract_object or "").strip()
    if obj and obj not in text and obj in blob:
        key = _valid_activity_prop(obj) or _clip_prop_noun(obj)
        if key and not any(p == key or key in p for _h, p in holdings):
            holder = ""
            for h, p in holdings:
                if p == key:
                    holder = h
                    break
            if not holder:
                for row in rows:
                    sp, line = _row_speaker_line(row)
                    if key not in line:
                        continue
                    m = _DEIXIS_CONTAINER_RE.search(line)
                    if m and _valid_activity_prop(m.group(3)) == key:
                        holder = (
                            sp if m.group(1) == "我" else _other_kid(sp)
                        )
                        break
            holdings.append((holder, key))
    bits: list[str] = []
    seen_prop: set[str] = set()
    for holder, prop in holdings:
        if not prop or prop in text or prop in seen_prop:
            continue
        seen_prop.add(prop)
        if holder:
            bits.append(f"{holder}面前有{prop}")
        else:
            bits.append(f"{prop}在场")
    if not bits:
        return text
    if not text:
        return "，".join(bits)
    return text.rstrip("。，,") + "，" + "，".join(bits)


def normalize_object_states(
    segments: list[dict],
    setting: str | None = None,
) -> list[str]:
    """object_states 状态机：跨镜继承缺失状态、去重、自动修正矛盾与状态回归。

    原地归一 segments 的 object_states，返回修正记录列表（供日志；不阻塞流水线）。
    """
    notes: list[str] = []
    last_state: dict[str, dict] = {}
    form_seq: dict[str, list[str]] = {}  # 每个 object 的 form 单向演进历史
    dlg_rows: list = []
    for seg in segments:
        dlg_rows.extend(_dialogue_rows_any(seg.get("dialogue")))
    bowl_owners = bowl_container_owners(setting, dlg_rows)
    for seg in segments:
        idx = int(seg.get("segment_index") or 0)
        raw = seg.get("object_states")
        states = [st for st in raw if isinstance(st, dict)] if isinstance(raw, list) else []
        seen: dict[str, dict] = {}
        body_injury_states: list[dict] = []
        for st in _collapse_object_aliases(states):
            obj = str(st.get("object") or "").strip()
            if not obj:
                continue
            if is_body_part_object(obj):
                body_injury_states.append(st)
                notes.append(
                    f"segment {idx}: object_states 剔除身体部位 object={obj!r}，"
                    "伤势改由 visual_subjects 表达"
                )
                continue
            if obj in seen:
                notes.append(f"segment {idx}: object_states 重复 object={obj}，去重")
                continue
            seen[obj] = st
        merged: dict[str, dict] = {k: dict(v) for k, v in last_state.items()}
        for obj, st in seen.items():
            merged[obj] = st
        for obj, st in merged.items():
            form = str(st.get("form") or "").strip()
            # 状态回归自动修正：form 回退到历史较早值，则沿用最新状态（单向推进）
            if form:
                seq = form_seq.setdefault(obj, [])
                if form in seq:
                    pos_in_seq = seq.index(form)
                    if pos_in_seq < len(seq) - 1:
                        notes.append(
                            f"segment {idx}: object={obj} 状态回归 {form!r}，"
                            f"自动修正为 {seq[-1]!r}"
                        )
                        st["form"] = seq[-1]
                        form = seq[-1]
                else:
                    seq.append(form)
            # holder/position：碗/盘里的冲突物保持容器位；手持物才归入手中
            holder = str(st.get("holder") or "").strip()
            pos = str(st.get("position") or "").strip()
            bowl_who = bowl_owners.get(obj) or ""
            if bowl_who:
                if holder != bowl_who:
                    st["holder"] = bowl_who
                    holder = bowl_who
                new_pos = f"{bowl_who}碗里"
                if pos != new_pos:
                    notes.append(
                        f"segment {idx}: object={obj} 容器归属 {bowl_who}，"
                        f"position 写 {new_pos}"
                    )
                    st["position"] = new_pos
            elif holder and holder != "无":
                if not pos:
                    st["position"] = f"{holder}手中"
                elif "手" not in pos and "手" not in holder:
                    notes.append(
                        f"segment {idx}: object={obj} holder={holder} 与 position={pos} 矛盾，"
                        f"position 归入 {holder}手中"
                    )
                    st["position"] = f"{holder}手中"
        seg["object_states"] = [dict(v, object=k) for k, v in merged.items()]
        for st in body_injury_states:
            migrate_body_part_injury_to_subjects(seg, st)
        last_state = merged
    return notes


def _sanitize_subject_action(action: str) -> str:
    """action 字段槽内消毒：重写易诱发拿鞋/套鞋/手指变形的高危措辞。"""
    a = action or ""
    # 指鞋/指鞋带易诱发拿鞋或套鞋，改为看
    a = re.sub(r"(?:右|左)?手?(?:食指|拇指)?\s*指(?:向|着)[^，。；]{0,6}鞋", "看向粉鞋", a)
    # 穿鞋眼易被画成往脚上套鞋；与其他改写去重
    a = re.sub(r"穿(?:进|过)[^，。；]{0,4}鞋眼", "", a)
    a = re.sub(r"各捏(?:住)?一根鞋带", "捏住鞋带", a)
    # 手指级精细动作降级为粗粒度
    a = re.sub(r"手指[^，。；]{0,4}包裹", "捏住", a)
    a = re.sub(r"(捏住鞋带){2,}", r"\1", a)
    return a.strip("，, ")


def _sanitize_subject_expression(expression: str) -> str:
    """expression 字段槽内消毒：禁止口型词，口型由 S6 锁统一注入。"""
    e = expression or ""
    # 口型词直接剥掉（口型由 S6 槽位负责，expression 只写眉眼/嘴角静态）
    e = re.sub(r"(?:撇嘴|咧嘴|笑着|微笑)?说话", "", e)
    e = re.sub(r"开口|张嘴|张口|大喊|喊叫|反驳", "", e)
    e = re.sub(r"[，,]{2,}", "，", e)
    return e.strip("，, ")


def _collapse_object_aliases(states: list) -> list[dict]:
    """同物异名去重：「薯片」并入「薯片袋」等，保留更长 object 名。"""
    rows = [st for st in states if isinstance(st, dict)]
    names = [str(st.get("object") or "").strip() for st in rows]
    drop: set[str] = set()
    for short in names:
        if not short:
            continue
        for long in names:
            if short != long and short in long:
                drop.add(short)
    return [
        st
        for st in rows
        if str(st.get("object") or "").strip() not in drop
    ]


def _daily_scene_location(setting: str | None) -> str:
    text = (setting or "").strip()
    if not text:
        return "客厅"
    return text.split("，")[0].strip() or "客厅"


def _vb_has_rich_scene_opening(vb: str, setting: str | None) -> bool:
    """S4 是否已有 64/7 式场景开场（地点 + 陈设/动作铺陈）。"""
    if len(vb) >= 130:
        loc = _daily_scene_location(setting)
        return loc in vb
    loc = _daily_scene_location(setting)
    if loc not in vb:
        return False
    return any(k in vb for k in ("沙发", "茶几", "地垫", "门口", "鞋柜", "阳台"))


def _dedupe_clause_text(text: str) -> str:
    """去掉完全重复的句/分句（S4 内 LLM 偶发复读）。"""
    if not text:
        return text
    parts = re.split(r"(?<=[。；;])", text)
    seen: set[str] = set()
    kept: list[str] = []
    for part in parts:
        s = part.strip()
        if not s:
            continue
        key = re.sub(r"\s+", "", s)
        if key in seen:
            continue
        seen.add(key)
        kept.append(s)
    return "".join(kept).strip("，,；;。 ")


def _prop_snapshot_from_object_states(states: list) -> str:
    """从 object_states 抽一句道具快照（仅用于 vb 内提及，避免 strip_unlocked 补尾巴）。"""
    for st in _collapse_object_aliases(states):
        obj = str(st.get("object") or "").strip()
        if is_body_part_object(obj):
            continue
        form = str(st.get("form") or "").strip()
        pos = str(st.get("position") or "").strip()
        count = str(st.get("count") or "").strip()
        if not obj or not pos:
            continue
        head = count + obj if count else obj
        clause = f"{pos}放着{head}"
        if form:
            clause += f"，{form}"
        return clause
    return ""


def _fuse_scene_opening_with_mom(
    loc: str,
    anchors: list[str],
    mom_clause: str,
) -> str:
    """场景开场与妈妈动作合句，避免 S4 清洗误删无角色场景句。"""
    head = loc
    if anchors:
        head += "，" + "、".join(anchors[:3]) + "清晰可见"
    return f"{head}，{mom_clause}。"


def _format_enriched_subject_clause(
    name: str,
    sub: dict | None,
    *,
    side: str | None = None,
) -> str:
    sub = sub or {}
    posture = str(sub.get("posture") or "").strip()
    action = _sanitize_subject_action(str(sub.get("action") or "").strip())
    expr = _sanitize_subject_expression(str(sub.get("expression") or "").strip())
    bits = [b for b in (posture, action, expr) if b]
    if not bits:
        return ""
    if side:
        tail = bits[1:] if bits[0].startswith(("站", "蹲", "坐")) else bits
        tail_text = "，".join(tail)
        return f"画面{side}是{name}" + (f"，{tail_text}" if tail_text else "")
    head = bits[0]
    if not head.startswith(name):
        head = name + head
    tail = "，".join(bits[1:])
    return head + (f"，{tail}" if tail else "")


def enrich_thin_daily_visual_brief(seg: dict, setting: str | None = None) -> str:
    """薄 vb 加厚为 64/7 式：场景开场 + 妈妈居中 + 左右孩锚点。"""
    vb = str(seg.get("visual_brief") or "").strip()
    vb = re.sub(r"。?画面中有[^。；]+[。；]?", "。", vb).strip("，,；;。 ")
    structured = bool(seg.get("visual_subjects")) and bool(seg.get("object_states"))
    if not structured and _vb_has_rich_scene_opening(vb, setting):
        return _resolve_vague_spatial_terms(_dedupe_clause_text(vb))

    subjects = seg.get("visual_subjects") or []
    owners = bowl_container_owners(setting, seg.get("dialogue"))
    if owners:
        for sub in subjects:
            if not isinstance(sub, dict):
                continue
            name = str(sub.get("name") or "").strip()
            sub["action"] = unbind_foreign_bowl_food_action(
                str(sub.get("action") or ""), name, owners
            )
    speakers = [str(s) for s in (seg.get("speakers") or []) if str(s).strip()]
    subject_map = {
        str(s.get("name") or "").strip(): s
        for s in subjects
        if isinstance(s, dict) and str(s.get("name") or "").strip()
    }

    loc = _daily_scene_location(setting)
    anchors = [
        str(a).strip() for a in (seg.get("scene_anchors") or []) if str(a).strip()
    ]
    # 结构化路径：道具归 S5，S4 不写 prop_snap（避免与 object_states 三遍复读）
    prop_snap = (
        ""
        if structured
        else _prop_snapshot_from_object_states(seg.get("object_states") or [])
    )

    char_lines: list[str] = []
    if "妈妈" in speakers:
        mom_clause = _format_enriched_subject_clause("妈妈", subject_map.get("妈妈"))
        if mom_clause:
            char_lines.append(_fuse_scene_opening_with_mom(loc, anchors, mom_clause))
    elif loc:
        opening = loc
        if anchors:
            opening += "，" + "、".join(anchors[:3]) + "清晰可见"
        if prop_snap:
            char_lines.append(f"{opening}，{prop_snap}。")
        else:
            char_lines.append(f"{opening}。")
    for kid, side in (("昭昭", "左边"), ("灿灿", "右边")):
        if kid in speakers:
            line = _format_enriched_subject_clause(
                kid, subject_map.get(kid), side=side
            )
            if line:
                char_lines.append(line)
    for name in speakers:
        if name in ("妈妈", "昭昭", "灿灿"):
            continue
        line = _format_enriched_subject_clause(name, subject_map.get(name))
        if line:
            char_lines.append(line)

    if not char_lines and vb:
        return _resolve_vague_spatial_terms(vb)

    body = "。".join(char_lines)
    if (
        prop_snap
        and "妈妈" not in speakers
        and prop_snap not in body
    ):
        body = body.rstrip("。") + "。" + prop_snap
    body = re.sub(r"[。]{2,}", "。", body)
    return _resolve_vague_spatial_terms(_dedupe_clause_text(body.strip("，,；;。 ")))


def render_visual_subjects(subjects: list) -> str:
    """visual_subjects → visual_brief 文本（供下游检测与 S4 画面槽使用）。"""
    parts: list[str] = []
    for s in subjects:
        if not isinstance(s, dict):
            continue
        name = str(s.get("name") or "").strip()
        if not name:
            continue
        bits = [
            str(s.get(k) or "").strip()
            for k in ("posture", "action", "expression")
        ]
        bits = [b for b in bits if b]
        if len(bits) >= 2:
            bits[1] = _sanitize_subject_action(bits[1])
        if len(bits) >= 3:
            bits[2] = _sanitize_subject_expression(bits[2])
        bits = [b for b in bits if b]
        if not bits:
            parts.append(name)
            continue
        clause = name + bits[0]
        if len(bits) > 1:
            clause += "，" + "，".join(bits[1:])
        parts.append(clause)
    text = "。".join(p.rstrip("。") for p in parts if p)
    return _resolve_vague_spatial_terms(text)


def validate_object_states(segments: list[dict]) -> list[str]:
    """不改写原数据的 object_states 校验（深拷贝后跑状态机）。"""
    import copy

    return normalize_object_states(copy.deepcopy(segments))


def daily_locked_inventory(
    segments: list[dict],
    setting: str | None = None,
) -> set[str]:
    """本片允许入画的物品：setting/台词里的活动道具 + 分镜1 家具/默认陈设。"""
    setting_text = str(setting or "")
    spoken = setting_text + _dialogue_blob(segments)
    vb1 = ""
    for seg in segments:
        if int(seg.get("segment_index") or 0) == 1:
            vb1 = str(seg.get("visual_brief") or "")
            break
    # 冲突道具：setting / 台词容器句抽出的中心语（不靠道具名词白名单）。
    # 尺子/铅笔等杂物只认 setting 与分镜1 画面，避免台词「拿尺子比」误锁实物。
    rows: list[dict] = []
    for seg in segments:
        rows.extend(_dialogue_rows_any(seg.get("dialogue")))
    locked = extract_story_activity_props(setting_text, rows)
    locked |= {
        n
        for n in _LOCKABLE_PROPS
        if n not in _CLUTTER_ONLY_PROPS and (n in spoken or n in vb1)
    }
    locked |= {
        n for n in _CLUTTER_ONLY_PROPS if n in setting_text or n in vb1
    }
    locked |= {n for n in _DAILY_FIXED_FURNITURE if n in spoken or n in vb1}
    for n in ("遥控器", "空水杯"):
        if n in vb1 or n in spoken:
            locked.add(n)
    return locked


_BARE_DELETE_SKIP = frozenset({"橡皮"})  # 避免误伤「橡皮擦拭痕迹」
_CORE_LOCK_PROPS = (
    "剪刀", "纸", "相框", "水壶", "蛋糕", "薯片", "酸奶", "衣服",
)


def _drop_unlocked_name(body: str, name: str, locked: set[str]) -> str:
    """去掉未锁定物品的短词组，尽量不拆掉整句锁定道具。"""
    if name not in body:
        return body
    patterns = [
        rf"背景是{name}和[\u4e00-\u9fa5]{{1,6}}",
        rf"背景是[\u4e00-\u9fa5]{{1,6}}和{name}",
        rf"(?:一把|一支|一张|一条|一个|几张|几把)(?:塑料|儿童|安全)?{name}",
        rf"和{name}",
        rf"{name}和",
    ]
    # 短名可能嵌在已锁定长名里（床⊂床头柜），此时不裸删。
    # 橡皮不裸删，避免涂鸦风格句「橡皮擦拭」被拆开。
    if (
        name not in _BARE_DELETE_SKIP
        and not any(name != other and name in other for other in locked)
    ):
        patterns.append(name)
    out = body
    for pat in patterns:
        out = re.sub(pat, "", out)
    return out


def strip_unlocked_inventory(body: str, locked: set[str]) -> str:
    """后续镜/质检重写不得新增未锁定家具和杂物；剪刀别名收回「剪刀」。"""
    if not body:
        return body
    out = body
    if "剪刀" in locked:
        out = _SCISSOR_ALIAS_RE.sub("剪刀", out)
    if "纸" in locked:
        out = _EXTRA_PAPER_RE.sub("一张剪坏的纸", out)
    names = sorted(
        [n for n in (*_DAILY_FIXED_FURNITURE, *_LOCKABLE_PROPS) if n not in locked],
        key=len,
        reverse=True,
    )
    for name in names:
        out = _drop_unlocked_name(out, name, locked)
    missing = [n for n in _CORE_LOCK_PROPS if n in locked and n not in out]
    if missing:
        out = out.rstrip("，,；;。 ") + "。画面中有" + "、".join(missing) + "。"
    out = re.sub(r"[，,]{2,}", "，", out)
    out = re.sub(r"[；;]{2,}", "；", out)
    out = re.sub(r"。{2,}", "。", out)
    out = re.sub(r"（）|\(\)", "", out)
    return out.strip("，,；;。 ")


def _collapse_duplicate_pose_clauses(body: str) -> str:
    """同一角色多段动作只保留首段（文生图为单帧）。"""
    parts = re.split(r"([；;。])", body)
    if not parts:
        return body
    seen: set[str] = set()
    out: list[str] = []
    i = 0
    while i < len(parts):
        segment = parts[i]
        delim = parts[i + 1] if i + 1 < len(parts) else ""
        clause = segment.strip()
        drop = False
        if clause:
            m = _POSE_CLAUSE_START_RE.match(clause)
            if m:
                name = m.group(1)
                if name in seen:
                    drop = True
                else:
                    seen.add(name)
        if not drop:
            out.append(segment)
            if delim:
                out.append(delim)
        i += 2 if delim else 1
    return "".join(out)


def _collapse_dual_active_hands(body: str) -> str:
    """同一人指+叉腰/握+指等会诱发第三只手：只留一个主动手，另一只下垂。"""
    parts = re.split(r"([；;。])", body)
    if not parts:
        return body
    hold_re = re.compile(r"(?:右手|左手)?(?:握着|握住|拿着|持着)")
    point_re = re.compile(r"(?:右手|左手)?(?:食指)?(?:指着|指向|比划)")
    press_re = re.compile(r"(?:右手|左手)?(?:按在|压着|压住)")
    out: list[str] = []
    i = 0
    while i < len(parts):
        segment = parts[i]
        delim = parts[i + 1] if i + 1 < len(parts) else ""
        for name in ("昭昭", "灿灿", "妈妈"):
            if name not in segment:
                continue
            has_hold = bool(hold_re.search(segment))
            has_point = bool(point_re.search(segment))
            has_hip = "叉腰" in segment
            has_press = bool(press_re.search(segment))
            if sum([has_hold, has_point, has_hip, has_press]) < 2:
                continue
            if has_hold:
                segment = re.sub(
                    r"(左手|右手|双手)叉腰", r"\1自然下垂", segment
                )
                segment = re.sub(
                    r"(左手|右手)(?:食指)?(?:指着|指向|比划)[^，。；]{0,16}",
                    r"\1自然下垂",
                    segment,
                )
                segment = re.sub(
                    r"(左手|右手)(?:按在|压着|压住)[^，。；]{0,16}",
                    r"\1自然下垂",
                    segment,
                )
            elif has_point and has_hip:
                segment = re.sub(
                    r"(左手|右手|双手)叉腰", r"\1自然下垂", segment
                )
            elif has_point and has_press:
                segment = re.sub(
                    r"(左手|右手)(?:按在|压着|压住)[^，。；]{0,16}",
                    r"\1自然下垂",
                    segment,
                )
            elif has_hip and has_press:
                segment = re.sub(
                    r"(左手|右手)(?:按在|压着|压住)[^，。；]{0,16}",
                    r"\1自然下垂",
                    segment,
                )
            segment = segment.replace("身体前倾，", "").replace("身体前倾", "")
        out.append(segment)
        if delim:
            out.append(delim)
        i += 2 if delim else 1
    return "".join(out)


def _fix_hands_on_hips_conflict(body: str) -> str:
    """同一分句「双手叉腰」又写右手动作时，改为左手叉腰。"""
    parts = re.split(r"([；;。])", body)
    if not parts:
        return body
    out: list[str] = []
    i = 0
    while i < len(parts):
        segment = parts[i]
        delim = parts[i + 1] if i + 1 < len(parts) else ""
        if "双手叉腰" in segment and _RIGHT_HAND_ACTION_RE.search(segment):
            segment = segment.replace("双手叉腰", "左手叉腰")
        out.append(segment)
        if delim:
            out.append(delim)
        i += 2 if delim else 1
    return "".join(out)


def _only_default_table_items(clause: str) -> bool:
    """陈设句去掉默认项+框架词后无其他实质内容才算纯默认（不做道具词表判断）。

    注意：仅出现默认项子集（如只有「空水杯」）时也会归一到默认全集，
    这是兜底策略的一部分（补齐缺失默认项）。
    """
    remaining = clause
    for item in _DEFAULT_TABLE_ITEMS:
        remaining = remaining.replace(item, "")
    remaining = _TABLE_FRAME_RE.sub("", remaining)
    return remaining == ""


def _normalize_default_table_set(body: str) -> str:
    """茶几背景陈设：仅归一「纯默认陈设」句，其余一律保留。

    不做「哪些道具算冲突道具」的词表判断——任何非默认道具
    （蛋糕/花瓶/杂志等）都保留；去杂物职责在生成端 prompt。
    """
    return _TABLE_SET_CLAUSE_RE.sub(
        lambda m: (
            _DEFAULT_TABLE_SET
            if _only_default_table_items(m.group(0))
            else m.group(0)
        ),
        body,
    )


def _dedupe_default_table_set(body: str) -> str:
    """默认陈设句全片只保留第一次出现，删除后续重复。"""
    marker = _DEFAULT_TABLE_SET
    first = body.find(marker)
    if first < 0:
        return body
    head = body[: first + len(marker)]
    tail = body[first + len(marker) :]
    return head + tail.replace(marker, "")


_DEFAULT_TABLE_TAIL_RE = re.compile(
    r"[，,]\s*(?:茶几上放着|旁边是)遥控器和空水杯\s*"
)

# 冲突道具被误写进固定陈设句（X上立着Y），但本镜 Y 已位移/状态变化时兜底归一
_POSITION_CLAUSE_RE = re.compile(
    r"([\u4e00-\u9fa5]{1,8}?)(?:上)(?:立着|放着|摆着|摊着|搁着)"
    r"([\u4e00-\u9fa5A-Za-z0-9]{2,14})"
)
# 关键道具词后面接这些字时多半是另一物件（蛋糕刀/月饼盒/薯片袋），不算道具位移
_PROP_COMPOUND_SUFFIXES = ("刀", "盒", "袋", "盘", "罐", "瓶", "碗", "杯", "架")
# 位移/状态变化动词（含「扫」：相框被扫帚推远）
_MOVED_STATE_RE = re.compile(r"(?:摔|掉|落|躺|滚|滑|脱手|踩|扫|捡|碎|散)")
_HAND_HOLD_RE = re.compile(
    r"([\u4e00-\u9fa5]{2,3})(?:右手|左手|双手)?(?:拿|捧|握|抱)着?"
)
# 从动作句抽出被拿起的物件（不按主题词表枚举）。
_HOLD_OBJECT_RE = re.compile(
    r"(?:右手|左手|双手)?"
    r"(?:握着|握住|拿着|持着|举着|端着|托着|托住|提着|接过|"
    r"递出|递给|抓住|抓着|拿起|紧握)"
    r"(?:一把|一支|一张|一条|一个)?"
    r"([^，。；、（(\n]{1,12})"
)
_NAMED_HOLD_RE = re.compile(
    r"(昭昭|灿灿|妈妈)"
    r"([^。；]{0,24}?)"
    r"(右手|左手|双手)?"
    r"(握着|握住|拿着|持着|举着|端着|托着|托住|提着|接过|"
    r"递给|递出|抓住|抓着|拿起|紧握)"
    r"(?:一把|一支|一张|一条|一个)?"
    r"([^，。；、（(\n]{1,12})"
)
_DAILY_LR_LOCK_RE = re.compile(
    r"画面左边是\s*(昭昭|灿灿|妈妈)\s*[，,；;]?\s*右边是\s*(昭昭|灿灿|妈妈)"
)
_RELATIVE_STAND_RE = re.compile(
    r"(昭昭|灿灿|妈妈)站在"
    r"(?:她|他|(?:昭昭|灿灿|妈妈))(?:的)?"
    r"(左侧|右边|右侧|左边)"
)
_SPATIAL_ANCHOR_PRIORITY = (
    "茶几", "沙发", "餐桌", "书桌", "地垫", "水槽", "门口",
)
_SQUAT_OPPOSITE_RE = re.compile(
    r"(昭昭|灿灿|妈妈)蹲在(昭昭|灿灿|妈妈)对面"
)
_STAND_OPPOSITE_RE = re.compile(
    r"(昭昭|灿灿|妈妈)站在(茶几|沙发|餐桌|书桌|地垫|水槽|门口)对面"
)
_STAND_BARE_OPPOSITE_RE = re.compile(
    r"(昭昭|灿灿|妈妈)站在对面"
)
_STAND_BESIDE_CHAR_RE = re.compile(
    r"(昭昭|灿灿|妈妈)站在(昭昭|灿灿|妈妈)(?:旁边|身旁|一侧)"
)
_STAND_BESIDE_OBJ_RE = re.compile(
    r"(昭昭|灿灿|妈妈)站在(茶几|沙发|餐桌|书桌|地垫|水槽|门口)(?:旁|旁边|一侧)"
)
_SURFACE_PLACE_RE = re.compile(
    r"(桌上|桌面上|茶几上|沙发上|餐桌上|书桌上|旁边|纸旁|身旁|旁)"
    r"(?:还)?"
    r"(?:摊着|放着|立着|摆着|搁着|摊开|是)"
)
_HELD_BY_RE = re.compile(
    r"([^，。；、]{1,12}?)由(昭昭|灿灿|妈妈)"
    r"(右手|左手|双手)?"
    r"(握着|握住|拿着|持着|举着|端着|托着|托住|提着|接过|"
    r"递给|递出|抓住|抓着|拿起|紧握)"
)
_NAMED_GAZE_PROP_RE = re.compile(
    r"(昭昭|灿灿|妈妈)"
    r"([^。；]{0,24}?)"
    r"(?:眼睛)?"
    r"(?:盯着|看着|看向)"
    r"(?:那把|一把|这把)?"
    r"([\u4e00-\u9fa5]{2,8})"
)
_SURFACE_ITEM_SPLIT_RE = re.compile(r"和|与|及|、")


_MEASURE_HEAD_RE = re.compile(
    r"^(?:那|这)?"
    r"(?:一|两|几)?"
    r"(?:盘|碗|块|根|袋|盒|瓶|杯|张|把|支|条|个|份|串|双|件)"
)
_PROP_NOUN_SKIP = frozenset(
    {"东西", "那个", "这个", "什么", "哪里", "这样", "那样", "一下"}
)


def _clip_prop_noun(raw: str) -> str:
    s = (raw or "").strip()
    s = re.split(
        r"不香|这么|好多|好香|香得|香吗|凭什么|不能|都得|[吗呢啊呀吧哦]",
        s,
        maxsplit=1,
    )[0]
    return s.strip("的了着过呢嘛呀啊吧哦，。！？ ")


def _prop_key(prop: str) -> str:
    """取道具中心语：量词后名词（一盘肉→肉），「的」后名词；否则末两字。"""
    text = _clip_prop_noun(prop)
    if not text:
        return ""
    if "的" in text:
        text = text.rsplit("的", 1)[1].strip()
    m = _MEASURE_HEAD_RE.match(text)
    if m and m.end() < len(text):
        return text[m.end() :]
    if len(text) <= 2:
        return text
    return text[-2:]


def _key_means_same_prop(clause: str, key: str) -> bool:
    """clause 里 key 是否指同一道具（「蛋糕刀/薯片袋」这类同前缀别物不算）。"""
    start = 0
    while True:
        i = clause.find(key, start)
        if i < 0:
            return False
        nxt = clause[i + len(key) : i + len(key) + 1]
        if nxt and nxt in _PROP_COMPOUND_SUFFIXES:
            start = i + len(key)
            continue
        return True


def _held_prop_keys(body: str) -> set[str]:
    """本镜动作句里被拿起/递出的物件名词（由持物动词抽出，不查词表）。"""
    keys: set[str] = set()
    for clause in re.split(r"[；;。]", body):
        if not any(n in clause for n in ("昭昭", "灿灿", "妈妈")):
            continue
        if (
            _SURFACE_PLACE_RE.search(clause)
            and not _HOLD_OBJECT_RE.search(clause)
            and not _HELD_BY_RE.search(clause)
        ):
            continue
        for m in _HOLD_OBJECT_RE.finditer(clause):
            raw = (m.group(1) or "").strip()
            if not raw:
                continue
            key = _prop_key(raw)
            if not key:
                continue
            keys.add(key)
        for m in _HELD_BY_RE.finditer(clause):
            raw = (m.group(1) or "").strip()
            key = _prop_key(raw)
            if key:
                keys.add(key)
    return keys


def _strip_held_from_surface_clause(clause: str, keys: set[str]) -> str:
    """陈设句里删掉已被拿起的并列项，保留桌上其余物件。"""
    m = _SURFACE_PLACE_RE.search(clause)
    if not m:
        return clause
    head = clause[: m.end()]
    rest = clause[m.end() :]
    extra = ""
    comma = re.search(r"[，,]", rest)
    if comma:
        items_blob = rest[: comma.start()]
        extra = rest[comma.start() :]
    else:
        items_blob = rest
    parts = [
        p.strip()
        for p in _SURFACE_ITEM_SPLIT_RE.split(items_blob)
        if p.strip()
    ]
    kept = [
        p
        for p in parts
        if not any(_key_means_same_prop(p, k) for k in keys)
    ]
    if not kept:
        # 已持物时不要留「纸旁放着剪刀」，否则 T2I 把剪刀画回桌上。
        return extra.lstrip("，, ") if extra else ""
    if len(kept) == 1:
        items = kept[0]
    elif len(kept) == 2:
        items = "和".join(kept)
    else:
        items = "、".join(kept)
    return head + items + extra


def held_prop_owners(body: str) -> dict[str, str]:
    """本镜「谁握着哪件」：prop_key → 持物人。"""
    owners: dict[str, str] = {}
    for m in _NAMED_HOLD_RE.finditer(body or ""):
        raw = (m.group(5) or "").strip()
        key = _prop_key(raw)
        if len(key) < 2:
            continue
        owners[key] = m.group(1)
    for m in _HELD_BY_RE.finditer(body or ""):
        raw = (m.group(1) or "").strip()
        key = _prop_key(raw)
        if len(key) < 2:
            continue
        owners[key] = m.group(2)
    return owners


def restore_held_prop_owners(new: str, old: str) -> str:
    """质检重写若把持物人改给别人，拨回旧 brief 的持物人。"""
    owners = held_prop_owners(old)
    if not owners:
        return new

    def _repl(m: re.Match) -> str:
        who = m.group(1)
        raw = (m.group(5) or "").strip()
        key = _prop_key(raw)
        locked = ""
        for old_key, holder in owners.items():
            if (
                key == old_key
                or _key_means_same_prop(raw, old_key)
                or _key_means_same_prop(old_key, key)
            ):
                locked = holder
                break
        if locked and who != locked:
            return locked + m.group(0)[len(who) :]
        return m.group(0)

    text = _NAMED_HOLD_RE.sub(_repl, new)

    def _repl_by(m: re.Match) -> str:
        raw = (m.group(1) or "").strip()
        who = m.group(2)
        key = _prop_key(raw)
        locked = ""
        for old_key, holder in owners.items():
            if (
                key == old_key
                or _key_means_same_prop(raw, old_key)
                or _key_means_same_prop(old_key, key)
            ):
                locked = holder
                break
        if locked and who != locked:
            prefix = f"{m.group(1)}由"
            suffix = m.group(0)[len(prefix) + len(who) :]
            return prefix + locked + suffix
        return m.group(0)

    return _HELD_BY_RE.sub(_repl_by, text)


def _pick_spatial_anchor(body: str) -> str:
    for name in _SPATIAL_ANCHOR_PRIORITY:
        if name in body:
            return name
    return "沙发"


def _default_side_for(name: str) -> str:
    if name == "妈妈":
        return "中间"
    if name == "昭昭":
        return "左边"
    if name == "灿灿":
        return "右边"
    return "中间"


def _resolve_vague_spatial_terms(body: str) -> str:
    """相对虚词改正面锚点：对面→物件前，旁边→画面左/右边。"""
    if not body:
        return body
    anchor = _pick_spatial_anchor(body)
    lock = _DAILY_LR_LOCK_RE.search(body)
    side_of: dict[str, str] = {}
    if lock:
        side_of = {lock.group(1): "左边", lock.group(2): "右边"}

    def _side(who: str) -> str:
        return side_of.get(who) or _default_side_for(who)

    body = _STAND_OPPOSITE_RE.sub(r"\1站在\2前", body)
    body = _STAND_BARE_OPPOSITE_RE.sub(rf"\1站在{anchor}前", body)
    body = _SQUAT_OPPOSITE_RE.sub(
        lambda m: f"{m.group(1)}蹲在画面{_side(m.group(1))}", body
    )
    body = _STAND_BESIDE_CHAR_RE.sub(
        lambda m: f"{m.group(1)}站在画面{_side(m.group(1))}", body
    )
    body = _STAND_BESIDE_OBJ_RE.sub(r"\1站在\2前侧", body)
    return body


def _resolve_relative_lr_conflict(body: str) -> str:
    """「画面左边是A」与「A站在她右侧」并存时，相对站位改成画面左右。"""
    lock = _DAILY_LR_LOCK_RE.search(body)
    if not lock:
        return body
    left, right = lock.group(1), lock.group(2)
    side_of = {left: "左边", right: "右边"}

    def _repl(m: re.Match) -> str:
        who = m.group(1)
        locked = side_of.get(who)
        if not locked:
            return m.group(0)
        rel_is_right = "右" in m.group(2)
        if rel_is_right != (locked == "右边"):
            return f"{who}站在画面{locked}"
        return m.group(0)

    return _RELATIVE_STAND_RE.sub(_repl, body)


def _retarget_gaze_from_held_prop(body: str) -> str:
    """非持物人「盯着剪刀」会诱发剪刀画到他眼前/手里，改成看向持物人。"""
    owners = held_prop_owners(body)
    if not owners:
        return body

    def _repl(m: re.Match) -> str:
        gazer = m.group(1)
        mid = m.group(2) or ""
        raw = m.group(3) or ""
        key = _prop_key(raw)
        holder = owners.get(key)
        if not holder:
            for old_key, who in owners.items():
                if _key_means_same_prop(raw, old_key) or _key_means_same_prop(
                    old_key, key
                ):
                    holder = who
                    break
        if not holder or gazer == holder:
            return m.group(0)
        return f"{gazer}{mid}看向{holder}"

    return _NAMED_GAZE_PROP_RE.sub(_repl, body)


def strip_held_prop_from_surface(body: str) -> str:
    """同镜已持物/递出时，从桌上/茶几上陈设句剥掉同一物件。

    不枚举剪刀/水壶：持物动词命中什么，就剥什么。
    无人持物的「桌上只有该物」原样保留。
    """
    keys = _held_prop_keys(body)
    if not keys:
        return body
    out: list[str] = []
    for part in re.split(r"([；;。])", body):
        if part in {"；", ";", "。"} or not part:
            out.append(part)
            continue
        out.append(_strip_held_from_surface_clause(part, keys))
    text = "".join(out)
    text = re.sub(r"[，,]{2,}", "，", text)
    text = re.sub(r"[，,]\s*(?=[；;。]|$)", "", text)
    text = re.sub(r"[；;]{2,}", "；", text)
    return text.strip("，,；; ")


def _resolve_stale_prop_position_conflict(body: str) -> str:
    """冲突道具被写进固定陈设句、本镜又发生位移/状态变化时，
    把陈设句改写为当前位置，消除「茶几上立着X」与「X摔在地上」并存矛盾。"""
    if not any(v in body for v in ("上立着", "上放着", "上摆着", "上摊着", "上搁着")):
        return body
    changed = body
    for m in _POSITION_CLAUSE_RE.finditer(body):
        prop = m.group(2)
        if "遥控器" in prop or "空水杯" in prop:
            continue
        key = _prop_key(prop)
        moved = False
        holder = ""
        for clause in re.split(r"[；;。]", body):
            if not _key_means_same_prop(clause, key):
                continue
            # 跳过陈设句本身（道具名里可能带「摔/碎」等字，如「摔裂的相框」）
            if m.group(0) in clause:
                continue
            if any(v in clause for v in ("碎片", "散落", "地上", "地面", "脚下")):
                moved = True
                break
            if _MOVED_STATE_RE.search(clause):
                moved = True
                break
            held_here = _held_prop_keys(clause)
            if any(
                k == key or _key_means_same_prop(k, key)
                for k in held_here
            ):
                moved = True
                hm = _HAND_HOLD_RE.search(clause)
                holder = hm.group(1) if hm else ""
                break
        if not moved:
            continue
        if f"{key}碎片" in body:
            repl = f"地上散落着{prop}碎片"
        elif holder:
            repl = f"{prop}被{holder}拿在手中"
        else:
            repl = f"{prop}掉在地上"
        changed = changed.replace(m.group(0), repl, 1)
    return changed


# 「A和B之间」会把模型注意力引向家具台面上方；道具已落地时改写为分层写法
_FURNITURE_PAIR_BETWEEN_RE = re.compile(
    r"(^|[，,。；;])"
    r"(沙发|茶几|餐桌|书桌|柜子|书架|电视柜|床头柜|鞋柜|凳子|椅子)"
    r"(?:和|与)"
    r"(沙发|茶几|餐桌|书桌|柜子|书架|电视柜|床头柜|鞋柜|凳子|椅子)"
    r"之间(?=[，,；;。])"
)
# 道具已落地的强状态句（散落/摔/掉/躺 + 地面）
_GROUND_STATE_RE = re.compile(
    r"(?:散落|掉在|摔在|躺在地|落在地|摔落地|散落一地|碎在地).{0,6}(?:地上|地面|地板)"
    r"|(?:地上|地面|地板).{0,6}(?:散落|碎片|碎玻璃)"
)
# 跨镜状态追踪用：道具已落地的宽松标志（碎片/散落/掉/摔/躺 + 地面）
_PROP_GROUND_MARK_RE = re.compile(
    r"碎片|碎玻璃|散落|掉在|摔在|躺在地|落在地|碎在地|地上|地面|脚下"
)


def _resolve_furniture_between_conflict(body: str) -> str:
    """道具已落地时，「沙发和茶几之间」会诱导模型把道具画上台面，
    改写为「沙发、茶几上没有任何物品，表面整洁」+ 地面状态句保留。"""
    if "之间" not in body or not _GROUND_STATE_RE.search(body):
        return body

    def _repl(m: re.Match) -> str:
        return f"{m.group(1)}{m.group(2)}、{m.group(3)}上没有任何物品，表面整洁"

    return _FURNITURE_PAIR_BETWEEN_RE.sub(_repl, body)


def _daily_conflict_prop_key(segments: list[dict]) -> str:
    """识别本片冲突道具名：取首个「X上立着/放着/摆着Y」陈设句里的道具名词。"""
    for seg in segments:
        vb = str(seg.get("visual_brief") or "")
        for m in _POSITION_CLAUSE_RE.finditer(vb):
            prop = m.group(2)
            if "遥控器" in prop or "空水杯" in prop:
                continue
            key = _prop_key(prop)
            if key:
                return key
    return ""


def _prop_is_grounded(vb: str, key: str) -> bool:
    """本镜是否已把冲突道具写到地面（道具名与地面标志须同句）。"""
    for clause in re.split(r"[；;。]", vb):
        if not _key_means_same_prop(clause, key):
            continue
        if _PROP_GROUND_MARK_RE.search(clause):
            return True
    return False


def _resolve_prop_state_regression(segments: list[dict]) -> list[dict]:
    """跨镜道具状态保护：一旦冲突道具已落地，后续镜禁止再写回家具台面。

    出图质检兜底重写 visual_brief 时，LLM 可能照抄旧 setting
    （如「茶几上立着摔裂的相框」），单镜兜底抓不到这种无同镜矛盾的回归，
    这里按分镜顺序追踪：落地后任何「X上立着/放着/摆着<道具>」改写回地上。
    """
    key = _daily_conflict_prop_key(segments)
    if not key:
        return segments
    grounded = False
    for seg in sorted(
        segments, key=lambda s: int(s.get("segment_index") or 0)
    ):
        vb = str(seg.get("visual_brief") or "")
        if not grounded:
            grounded = _prop_is_grounded(vb, key)
            continue
        for m in list(_POSITION_CLAUSE_RE.finditer(vb)):
            prop = m.group(2)
            if "遥控器" in prop or "空水杯" in prop:
                continue
            if not _key_means_same_prop(prop, key):
                continue
            repl = (
                f"地上散落着{prop}碎片"
                if f"{key}碎片" in vb
                else f"{prop}掉在地上"
            )
            vb = vb.replace(m.group(0), repl, 1)
        seg["visual_brief"] = vb
    return segments


def normalize_daily_visual_brief_sequence(
    segments: list[dict],
    *,
    setting: str | None = None,
) -> list[dict]:
    """非首镜去掉重复默认陈设句，避免每镜都写「遥控器和空水杯」。"""
    _resolve_prop_state_regression(segments)
    locked = daily_locked_inventory(segments, setting)
    fixed = _daily_fixed_furniture(segments)
    for seg in segments:
        idx = int(seg.get("segment_index") or 0)
        vb = str(seg.get("visual_brief") or "")
        vb = strip_unlocked_inventory(vb, locked)
        vb = _strip_non_first_speaker_speech(vb, seg.get("dialogue") or [])
        vb = _resolve_stale_prop_position_conflict(vb)
        vb = _resolve_furniture_between_conflict(vb)
        if idx > 1:
            vb = _DEFAULT_TABLE_TAIL_RE.sub("", vb)
            vb = vb.replace("茶几上放着遥控器和空水杯", "")
            vb = vb.replace("旁边是遥控器和空水杯", "")
        vb = vb.replace("花盆旁的托盘", "花盆下方的托盘")
        vb = vb.replace("花盆旁边是托盘", "花盆下方是托盘")
        vb = vb.replace("花盆旁边有托盘", "花盆下方有托盘")
        vb = vb.replace("托盘在花盆旁", "托盘在花盆下方")
        vb = re.sub(
            r"画面左边是灿灿[，,，]*右边是昭昭",
            "画面左边是昭昭，右边是灿灿",
            vb,
        )
        vb = _resolve_relative_lr_conflict(vb)
        if "花盆" in vb and "一株" not in vb and "红花" not in vb:
            plant = "花盆里有一株盛开的红花，花朵明显可见，枝叶完整。"
            if vb.endswith(("。", "；", ";")):
                vb += plant
            else:
                vb = vb.rstrip("，, ；; ") + "。" + plant
        vb = vb.replace("画面中有一把浇花水壶。", "")
        vb = vb.replace("画面中只有一把蓝色塑料浇花水壶，宽口短嘴，", "")
        vb = vb.replace("画面中唯一的蓝色塑料浇花水壶，宽口短嘴，", "")
        vb = vb.replace("核心道具蓝色塑料浇花水壶，宽口短嘴，", "")
        vb = vb.replace("核心道具蓝色塑料浇花水壶", "")
        # 水壶只保留持壶动作里的唯一一次完整描述，其余指代去掉名词
        vb = vb.replace("未接触水壶", "未接触")
        vb = vb.replace("看向水壶", "看向前方")
        vb = vb.replace("看着水壶", "看着前方")
        vb = vb.replace("指向水壶", "指向花盆")
        vb = vb.replace("指着水壶", "指着花盆")
        vb = vb.replace("伸向水壶", "伸向前方")
        vb = vb.replace("水壶方向", "前方")
        vb = vb.replace("停在半空", "仍握在手中")
        vb = vb.replace("水壶悬空", "水壶握在手中")
        vb = re.sub(r"神情[，,]+神情(不悦)?", r"神情\1", vb)
        vb = re.sub(r"神情[，,]+神情", "神情", vb)
        vb = re.sub(r"神情{2,}", "神情", vb)
        vb = re.sub(r"[，,]{2,}", "，", vb).strip("，, ")
        # 固定陈设强制在场：分镜1 出现过的家具/常驻道具，本镜缺失时补回
        missing = [f for f in fixed if f not in vb]
        if missing:
            clause = "画面中有" + "、".join(missing) + "。"
            vb = f"{clause}{vb}" if not vb else f"{vb}{clause}"
        seg["visual_brief"] = vb
    return segments


def _strip_non_first_speaker_speech(body: str, dialogue: list) -> str:
    """非首说话人只保留眉眼情绪，去掉说话/反驳/开口/嘴巴张开等口型描述。"""
    speakers: list[str] = []
    for item in dialogue or []:
        name = str(item.get("speaker") or "").strip()
        if name:
            speakers.append(name)
    if len(speakers) < 2:
        return body
    first = speakers[0]
    non_first = list(dict.fromkeys(speakers[1:]))
    if not non_first:
        return body
    clauses = re.split(r"(?<=[。；])", body)
    out: list[str] = []
    for clause in clauses:
        if any(name in clause for name in non_first):
            clause = re.sub(
                r"嘴巴(?:张开|微张|大张)(?:说话|反驳|大吼|正要反驳|正在反驳)?",
                "神情",
                clause,
            )
            clause = re.sub(
                r"(?:正在)?(?:说话|反驳|大喊|开口|大吼|抱怨|阻止|同意|辩解|抗议|怒吼|喊话|争辩)",
                "神情",
                clause,
            )
            clause = re.sub(r"神情(?=[。；]|$)", "神情不悦", clause)
            clause = re.sub(r"神情[，,，]{1,}", "神情，", clause)
            clause = re.sub(r"[，,]{2,}", "，", clause)
        out.append(clause)
    return "".join(out)


def scrub_daily_visual_brief(text: str) -> str:
    """去掉 daily visual_brief 中易破坏拼装出图的标签与固定着装词。"""
    body = (text or "").strip()
    if not body:
        return body
    body = _DAILY_BRIEF_LABEL_RE.sub("", body)
    for src, dst in _DAILY_OUTFIT_PROP_REWRITES:
        body = body.replace(src, dst)
    # 矛盾定语：叠好 ≠ 皱成一团
    body = body.replace(
        "皱成一团的刚叠好的衣服",
        "原本叠好现已揉皱成一团的衣服",
    )
    body = body.replace(
        "刚叠好的皱成一团的衣服",
        "原本叠好现已揉皱成一团的衣服",
    )
    # 「门缝」会诱发双开门中缝，统一改写成单开门与门框的空隙
    body = body.replace("门缝", "门与门框的空隙")
    # 儿童安全+刀型统一：一律写成塑料蛋糕刀（非水果刀）
    body = body.replace("塑料刀", "塑料蛋糕刀")
    body = body.replace("餐刀", "塑料蛋糕刀")
    body = body.replace("水果刀", "塑料蛋糕刀")
    body = body.replace("小刀", "塑料蛋糕刀")
    body = body.replace("拿刀", "拿塑料蛋糕刀")
    body = body.replace("持刀", "持塑料蛋糕刀")
    body = body.replace("握刀", "握塑料蛋糕刀")
    body = _MOUTH_AND_TONE_RE.sub("", body)
    body = _fix_hands_on_hips_conflict(body)
    body = _collapse_dual_active_hands(body)
    body = _normalize_default_table_set(body)
    body = _dedupe_default_table_set(body)
    body = strip_held_prop_from_surface(body)
    body = _retarget_gaze_from_held_prop(body)
    body = _resolve_vague_spatial_terms(body)
    body = _resolve_relative_lr_conflict(body)
    body = _resolve_stale_prop_position_conflict(body)
    body = _resolve_furniture_between_conflict(body)
    body = re.sub(r"[，,]{2,}", "，", body)
    body = re.sub(r"[，,]\s*(?=[；;。]|$)", "", body)
    body = _collapse_duplicate_pose_clauses(body)
    return body.strip("，, ").strip()



def _segments_have_dialogue(segments: list[dict]) -> bool:
    return any(bool(seg.get("dialogue")) for seg in segments)


def _cast_and_emotion_rules(
    profile_style: str,
    segments: list[dict],
) -> tuple[str, str, bool]:
    """返回 (cast_rule, emotion_rule, include_dialogue)。

    角色入画规则仅在日常，或 segments 已带 dialogue 时注入；
    纯口播生活片不再无 dialogue 却禁画妈妈。
    日常可入画 = 发言 ∪ 台词在场 ∪ 同场粘性（setting/前镜已出场）。
    """
    if profile_style == CONTENT_STYLE_DAILY_STORY:
        return _DAILY_SPEAKER_RULE, _EMOTION_RULE_DIALOGUE, True
    if _segments_have_dialogue(segments):
        return _MOM_DIALOGUE_RULE, _EMOTION_RULE_DIALOGUE, True
    return "", _EMOTION_RULE_NARRATION, False


def _visual_role(profile_style: str) -> str:
    if profile_style == CONTENT_STYLE_DAILY_STORY:
        return _DAILY_VISUAL_ROLE
    return resolve_style_rules(profile_style).role


def _format_one_visual_brief_segment(
    seg: dict,
    *,
    prefix: str = "",
    include_dialogue: bool = False,
) -> str:
    idx = seg.get("segment_index")
    text = str(seg.get("text") or "")
    line = f"{prefix}segment {idx}: text={text!r}"
    shot = str(seg.get("shot_type") or "").strip()
    if shot:
        line += f"; shot_type={shot!r}"
    speakers = seg.get("speakers")
    if isinstance(speakers, list) and speakers:
        names = [str(s).strip() for s in speakers if str(s).strip()]
        if names:
            line += f"; speakers={('、'.join(names))!r}"
    if include_dialogue:
        dialogue = seg.get("dialogue") or []
        dl_parts = [
            f'{d["speaker"]}:"{d["text"]}"'
            for d in dialogue
            if d.get("speaker") and d.get("text")
        ]
        if dl_parts:
            line += "; dialogue=" + " ".join(dl_parts)
    return line


def format_visual_brief_segments_for_prompt(
    segments: list[dict],
    *,
    include_dialogue: bool = False,
    segment_indices: list[int] | None = None,
) -> str:
    ordered = sorted(
        segments,
        key=lambda seg: int(seg.get("segment_index") or seg.get("index") or 0),
    )
    if segment_indices is None:
        return "\n".join(
            _format_one_visual_brief_segment(seg, include_dialogue=include_dialogue)
            for seg in ordered
        )

    wanted = {int(idx) for idx in segment_indices}
    max_idx = max(
        (int(seg.get("segment_index") or 0) for seg in ordered),
        default=0,
    )
    extra: set[int] = set()
    for idx in wanted:
        if idx - 1 >= 1:
            extra.add(idx - 1)
        if idx + 1 <= max_idx:
            extra.add(idx + 1)
    extra -= wanted
    shown = wanted | extra

    lines: list[str] = []
    for seg in ordered:
        idx = int(seg.get("segment_index") or 0)
        if idx not in shown:
            continue
        tag = "【仅上下文】" if idx in extra else "【需生成】"
        lines.append(
            _format_one_visual_brief_segment(
                seg,
                prefix=tag,
                include_dialogue=include_dialogue,
            )
        )
    return "\n".join(lines)


def build_visual_brief_prompts(
    script: dict[str, Any],
    *,
    feedback: str | None = None,
    supplementary_info: str | None = None,
    job: dict | None = None,
    orientation: str | None = None,
    content_style: str | None = None,
    segment_indices: list[int] | None = None,
) -> dict[str, str]:
    """第二步：基于已切分的 segments 与全文 narration 生成 visual_brief。

    segment_indices 非空时只要求 LLM 输出这些段（邻段作上下文）。
    """
    _profile_orientation, profile_style = resolve_script_profile(
        job,
        orientation=orientation,
        content_style=content_style,
    )
    segments = script.get("segments") or []
    if profile_style == CONTENT_STYLE_DAILY_STORY:
        from app.services.daily_story.speaker import annotate_sticky_stage_speakers

        annotate_sticky_stage_speakers(
            segments,
            setting=str(script.get("setting") or "").strip(),
        )
    narration = str(script.get("narration") or "").strip()
    visual_style = str(script.get("visual_style") or "").strip()
    title = str(script.get("title") or "").strip()
    cast_rule, emotion_rule, include_dialogue = _cast_and_emotion_rules(
        profile_style, segments
    )
    setting_rule = (
        _DAILY_SETTING_RULE if profile_style == CONTENT_STYLE_DAILY_STORY else ""
    )
    if profile_style == CONTENT_STYLE_DAILY_STORY:
        setting_text = str(script.get("setting") or "").strip()
        if setting_text:
            # 本片物件锚点：setting 里出现的场景物件须每镜在场（状态可随剧情演变）
            setting_rule += (
                "【本片物件锚点】以下为本片 setting 全句，"
                "其中出现的冲突相关物件（如薯片袋、衣服、剪刀、纸）每镜保持在场，"
                "状态可随剧情演变；背景陈设仍用默认遥控器和空水杯："
                f"「{setting_text}」"
            )
            locked = daily_locked_inventory(segments, setting_text)
            if locked:
                names = "、".join(sorted(locked, key=len, reverse=True))
                setting_rule += (
                    f"【物品锁定】本片只允许这些物品入画：{names}。"
                    "禁止新增分镜1/setting/台词没有的家具、文具或第二件同款"
                    "（如尺子、铅笔、沙发、另一张纸）；"
                    "剪刀全片同一把，写「剪刀」，勿改成安全剪/金属锋利剪。"
                )
            dlg_rows: list[dict] = []
            for seg in segments:
                dlg_rows.extend(_dialogue_rows_any(seg.get("dialogue")))
            holdings = extract_story_prop_holdings(setting_text, dlg_rows)
            if holdings:
                hold_bits = []
                for holder, prop in holdings:
                    if holder:
                        hold_bits.append(f"{holder}碗里有{prop}")
                    else:
                        hold_bits.append(prop)
                setting_rule += (
                    "【持物锁定】冲突物在谁的碗/盘里，不是拿在手里："
                    + "；".join(hold_bits)
                    + "。object_states.position 写「谁碗里/谁面前」，禁止写成手中"
                    "（除非本镜台词明确在递碗/端盘）；"
                    "站位左昭昭右灿灿：左边昭昭面前碗里是青菜，右边灿灿面前碗里是肉；"
                    "用正面写，不要写「没有肉」；禁止道具换手；action 不要无故写端着碗。"
                    "对方碗里的食物不要写进自己的动作句（不要写「指着肉盘」，改写指向对面）。"
                )
    content_rule = (
        _DAILY_VISUAL_SUBJECTS_RULE
        if profile_style == CONTENT_STYLE_DAILY_STORY
        else _VISUAL_BRIEF_CONTENT_RULE
    )
    partial = segment_indices is not None
    coverage = (
        "segments 仅需输出标记为【需生成】的分镜；【仅上下文】分段无需输出；"
        if partial
        else "segments 为分镜数组，须与输入逐段一一对应；"
    )
    seg_fields = (
        "各段含 segment_index, visual_subjects, object_states, scene_anchors, "
        "visual_mode=static_motion；"
        if profile_style == CONTENT_STYLE_DAILY_STORY
        else "各段含 segment_index, visual_brief, visual_mode=static_motion；"
    )
    seg_rule = (
        f"{coverage}"
        f"{seg_fields}"
        "不要输出或修改各段 text。"
        f"{content_rule}"
        f"{emotion_rule}"
        f"{cast_rule}"
        f"{_DAILY_CHARACTER_FACTS if profile_style == CONTENT_STYLE_DAILY_STORY else ''}"
        f"{_DAILY_OBJECT_STATE_RULE if profile_style == CONTENT_STYLE_DAILY_STORY else ''}"
        f"{setting_rule}"
        "须通读全文 narration，保证相邻分镜画面衔接自然、叙事节奏连贯，"
        "避免前后镜主体/场景毫无关联的跳跃；"
        + (
            "同时每镜 visual_subjects 只表达本段 text 内容，禁止提前画后续段落情节。"
            if profile_style == CONTENT_STYLE_DAILY_STORY
            else "同时每镜 visual_brief 只表达本段 text 内容，禁止提前画后续段落情节。"
        )
    )
    if profile_style == CONTENT_STYLE_DAILY_STORY:
        example = (
            _VISUAL_BRIEF_JSON_EXAMPLE_DAILY_PARTIAL
            if partial
            else _VISUAL_BRIEF_JSON_EXAMPLE_DAILY
        )
    else:
        example = (
            _VISUAL_BRIEF_JSON_EXAMPLE_PARTIAL
            if partial
            else _VISUAL_BRIEF_JSON_EXAMPLE_FULL
        )
    system = (
        f"{_visual_role(profile_style)}输出 JSON，字段：segments。"
        f"{seg_rule}"
        f"{supplementary_system_clause(supplementary_info, scope='visual')}"
        f"{json_output_clause(example)}"
    )
    seg_lines = format_visual_brief_segments_for_prompt(
        segments,
        include_dialogue=include_dialogue,
        segment_indices=segment_indices,
    )
    style_line = (
        f"全片 visual_style：{visual_style}\n\n"
        if visual_style
        else ""
    )
    setting = str(script.get("setting") or "").strip()
    setting_line = f"全片地点 setting：{setting}\n" if setting else ""
    if profile_style == CONTENT_STYLE_DAILY_STORY:
        seg_label = "visual_subjects/object_states/scene_anchors"
    else:
        seg_label = "visual_brief"
    if partial:
        seg_header = (
            "【各分镜口播 text】（已固定；仅【需生成】段输出 "
            f"{seg_label}，【仅上下文】勿输出）：\n"
        )
    else:
        seg_header = (
            "【各分镜口播 text】（已固定，请为每一段生成 "
            f"{seg_label}）：\n"
        )
    user = append_supplementary_to_user(
        (
            f"标题：{title}\n"
            f"{setting_line}"
            f"{style_line}"
            f"【口播全文 narration】（供把握画面节奏与连贯性，勿改写）：\n{narration}\n\n"
            f"{seg_header}"
            f"{seg_lines}"
        ),
        supplementary_info,
        scope="visual",
    )
    if feedback:
        user += f"\n\n上次不合格：{feedback}。请按要求重写。"
    return prompt_step("visual_brief", system, user)
