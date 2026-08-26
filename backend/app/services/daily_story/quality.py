"""日常故事观感打分（规则版，贴近人工质检口径）。"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

_LIMP_SOFT_CLOSE_MARKERS = (
    "给你", "算了", "好吧", "好了好了", "行吧", "随你",
    "我不管", "不管了", "随便你", "那行", "行行行",
    "哼", "吃吧", "你赢",
)
_PUNCHLINE_TYPE_MARKERS = (
    "权威翻车", "公平执念", "字面执行", "结盟翻车", "妈妈破功", "嘴硬心软",
    "问倒收束", "权威压住", "家长看戏", "退让点破",
    "A类", "B类", "C类", "D类", "E类", "F类", "G类", "H类", "I类", "J类", "K类", "L类",
    "A：", "B：", "C：", "D：", "E：", "F：", "G：", "H：", "I：", "J：", "K：", "L：",
)
_MOM_JUDGE_PATTERNS = (
    "谁先放好谁先选", "算你赢", "算他赢", "一人一半", "一人一个",
)

_WEAK_END_WAIT_MOM = ("等妈", "叫妈", "问妈", "告诉妈", "妈回来", "评理")
_WEAK_END_SPLIT = ("一人一半", "平分", "倒杯子", "一人一个")
_WEAK_END_STUBBORN = ("反正我要用", "反正橡皮", "反正是我的", "谁用谁小狗")

_STRONG_END_MARKERS = (
    "标签", "已经在了", "说晚了", "那不算", "当然不算",
    "自相矛盾", "你让的", "戳穿",
)

from app.services.daily_story.prompts import (
    DAILY_STORY_OPENING_LINES_MAX,
    DAILY_STORY_OPENING_LINES_MIN,
)
from app.services.daily_story.story_types.quality import (
    closing_satisfied,
    quality_profile_for_code,
    resolve_quality_profile,
    score_punchline_for_profile,
)
# ── 绕圈检测 ──
_REDUNDANCY_STOP_WORDS: frozenset[str] = frozenset({
    "我", "你", "他", "她", "我们", "你们", "他们", "她们",
    "的", "了", "是", "在", "不", "就", "也", "都", "要",
    "会", "能", "有", "和", "还", "这", "那", "说", "个",
    "吗", "呢", "吧", "啊", "嘛", "哦", "嗯", "呀",
    "怎么", "什么", "为什么", "没有", "不是", "可以", "不能",
    "这个", "那个", "一个", "已经", "现在", "所以", "因为",
    "但是", "如果", "虽然", "而且", "还是", "应该", "必须",
})
_CONTENT_WORD_RE = re.compile(r"[\u4e00-\u9fff]{2,}")

# 结构（格式/节奏/类型收束形态）满分 80（扣分制，未达标逐项扣）；总分 = 结构 + LLM 好笑
# 发布线（llm_mgr target 结构 75）：结构≥75 且 LLM 好笑≥HUMOR_PUBLISH_MIN（0-20 制）
HUMOR_PUBLISH_MIN = 10
STRUCTURE_SCORE_CAP = 80
# 扣分制各维度满分（结构分从 80 满分往下扣，未达标按维度扣分，cons 与分数对应）
OPENING_SCORE_FULL = 2          # 开场：缺/未满各最多扣 2（2026-08-25 自 6 下调）
ESCALATION_SCORE_FULL = 14      # 推进：4 层达标满分，3层-6 / 2层-12 / ≤1层-14
PUNCHLINE_SCORE_FULL = 8        # 收束形态：回旋镖/反转/破功落位达标满分，未落位扣8
# 节奏维度无独立满分：紧凑达标不减，绕圈/拖沓按 _score_redundancy 原扣分（-5~-12）
# 好笑维度 0–20：达标=HUMOR_PUBLISH_MIN（够发布线）；很好笑=15（仅标签）
_HUMOR_POINTS_FOR_GOOD = HUMOR_PUBLISH_MIN
_HUMOR_POINTS_FOR_GREAT = 15
# 共享数字加分（A/B/C/E 兜底）：全文任意「数字+分钟/秒/下」≥2 处 → +2
_RE_NUMBER_BONUS = re.compile(r"(?:\d+|[一二三四五六七八九十两]+)(?:分钟|秒|下)")

_RE_HAMMER = re.compile(
    # 禁止裸 \d+ 凑「一锤」（如「少了1块」）；须带量词或翻车动作
    r"(?:\d+|[一二三四五六七八九十两]+)(?:分钟|秒|下|次|遍)|"
    r"算错|写错|弹错|多玩|少玩|进位|竖式|升fa|降|"
    r"就吐水|才刷了|刷了三|泡沫还|边刷边|玩手机|噗|"
    r"咽下|塞嘴里|整块塞",
)

# ── 好笑 / 节奏（规则近似人工：具体、有出处、少复读）──
_RE_DIRECT_QUOTE = re.compile(
    r"(?:你刚才说|你自己说|你不是说|你刚说|你说的)([^，。！？…]{3,})",
)
_RE_MOM_PRECEDENT_CLAIM = re.compile(
    r"(?:上次|之前|昨天).{0,10}(?:妈|妈妈)|妈妈(?:说过|说要|也说过)",
)
_A_DRUDGE_PHRASES = (
    "你得听", "听我的", "我是姐姐", "考验", "我没错", "那不一样",
    "凭什么", "不公平", "教你", "规矩",
)
_A_TEMPLATE_MARKERS = ("哪里不一样", "都是听", "大人也要听小孩", "大人要听小孩")

# 口语「碰了一下」等不算可拍一锤
_RE_HAMMER_SOFT = re.compile(
    r"了一下|碰一下|试一下|看一下|摸一下|瞅一下",
)


def _text_has_hammer_beat(text: str) -> bool:
    if not _RE_HAMMER.search(text):
        return False
    if re.search(
        r"(?:\d+|[二三四五六七八九十两]+)(?:分钟|秒|次|遍)|"
        r"算错|写错|噗|才刷|就吐|咽下|塞嘴里|整块塞|玩手机|泡沫|"
        r"(?:两|三|四|五|几|\d+)下",
        text,
    ):
        return True
    if _RE_HAMMER_SOFT.search(text):
        return False
    return True


_HUMOR_ISSUE_CAPS_SHARED: tuple[tuple[str, int], ...] = (
    ("模板复读", 6),
    ("末四拍不完整", 5),
    ("偏C", 8),
    ("未扣一锤", 4),
    ("仍发指令", 4),
    ("认弟弟赢", 4),
    ("空甩身份", 4),
    ("可拍一锤", 4),
    ("预热注水", 5),
    ("把关话术", 5),
    ("质检说明书", 5),
    ("缺赖账", 5),
    ("催进度", 5),
    ("埋句过早", 5),
    ("检查样品复读", 5),
    ("缺咽下一锤", 5),
    ("咽下自相矛盾", 4),
    ("权威过早", 5),
    ("角色错位", 5),
    ("语气词注水", 4),
    ("多套免责", 4),
    ("借口复读", 4),
)


def _apply_humor_issue_caps(
    points: int,
    cons: list[str],
    profile,
) -> int:
    caps = (*_HUMOR_ISSUE_CAPS_SHARED, *profile.humor_issue_caps)
    for c in cons:
        for substr, cap in caps:
            if substr in c:
                points = min(points, cap)
                break
    return points


def _dialogue_lines(story: dict) -> list[str]:
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return []
    out: list[str] = []
    for item in dialogue:
        if not isinstance(item, dict):
            continue
        text = str(item.get("line") or "").strip()
        if text:
            out.append(text)
    return out


def _dialogue_speakers(story: dict) -> list[str]:
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return []
    out: list[str] = []
    for item in dialogue:
        if not isinstance(item, dict):
            continue
        sp = str(item.get("speaker") or "").strip()
        text = str(item.get("line") or "").strip()
        if text:
            out.append(sp)
    return out


def _grade_from_score(score: int) -> str:
    if score >= 70:
        return "好"
    if score >= 45:
        return "中"
    return "偏弱"


def _has_consecutive_sibling(dialogue: list) -> bool:
    prev = ""
    run = 0
    for item in dialogue:
        if not isinstance(item, dict):
            continue
        sp = str(item.get("speaker") or "").strip()
        if sp not in ("昭昭", "灿灿"):
            prev, run = sp, 0
            continue
        if sp == prev:
            run += 1
            if run >= 2:
                return True
        else:
            prev, run = sp, 1
    return False


def _score_escalation(
    lines: list[str],
    *,
    layer_patterns: tuple[tuple[str, re.Pattern[str]], ...],
) -> tuple[int, list[str]]:
    n = len(lines)
    if n < 6:
        return -12, ["冲突无明显推进"]

    quarter = max(1, n // 4)
    segments = [
        lines[:quarter],
        lines[quarter:quarter * 2],
        lines[quarter * 2:quarter * 3],
        lines[quarter * 3:],
    ]

    triggered_per_seg: list[set[str]] = []
    for seg in segments:
        seg_text = "".join(seg)
        triggered: set[str] = set()
        for label, pat in layer_patterns:
            if pat.search(seg_text):
                triggered.add(label)
        triggered_per_seg.append(triggered)

    layer_first_seg: dict[str, int] = {}
    for i, triggered in enumerate(triggered_per_seg):
        for label in triggered:
            if label not in layer_first_seg:
                layer_first_seg[label] = i

    layer_count = len(layer_first_seg)

    # 层数→推进分（2026-08-10 专家校准：3 层从 8 提为 10，使 3 层只扣 4 分，
    # 发布线 75 下 80-4=76 仍可通过；4 层满分 14 扣 0、2 层扣 12、≤1 层扣 14）
    layer_scores = {0: -12, 1: -6, 2: 2, 3: 10, 4: 14, 5: 18}
    bonus = layer_scores.get(layer_count, 18)

    if layer_count >= 4:
        return bonus, [f"冲突推进{layer_count}层"]
    if layer_count == 3:
        return bonus, [f"冲突推进{layer_count}层"]
    if layer_count == 2:
        return bonus, ["冲突层次偏少"]
    if layer_count <= 1:
        return bonus, ["冲突无明显推进"]
    return bonus, []


# 破坏类动词：被撞倒/砸碎/碰翻/带倒的受事故物，须在 setting 或正文前文出现过。
# 这是「动作-受事一致性」的抽象不变量（查动词宾语是否先落地），非按单篇剧情的词表。
_RE_ACCIDENT_VERBS = re.compile(
    r"撞倒|撞翻|撞歪|撞碎|撞破|砸碎|砸倒|碰翻|碰倒|碰碎|碰倒|"
    r"带倒|带翻|踩翻|踩倒|踢翻|踢倒|打翻|打碎|摔碎|摔破|弄倒|弄翻|"
    r"推倒|扑倒|勾倒|勾翻|扯倒|拉倒|扫倒|绊倒|颠翻|掀翻|碰洒|弄洒|打洒"
)


# 事故物名词末尾常见语气词/助词（只剥末尾，勿伤词身）
_RE_PROP_TAIL = re.compile(r"[啊呢呀吧嘛的着了]+$")
# 非受事故物的动词后表达（应忽略，不当作「凭空道具」）：
# 日常补救工具/常用物（扫帚/抹布/抱枕等）家家都有，观众不会问「哪来的」，
# 用户痛批的是「易碎物凭空」（花瓶/水杯/颜料）——那才需要先落地。
_RE_PROP_SKIP = re.compile(
    r"^(挡一下|一下|开了|过来|过去|东西|身上|旁边|门|窗|柜|桌|地|"
    r"在地上|在地|出声|出来|进来|飞|跑|摔|倒|碎|"
    r"扫帚|扫把|簸箕|拖把|抹布|毛巾|抱枕|枕头|毯子|垫子|"
    r"纸巾|报纸|桶|盆|筐|盒子|书包)$",
)


def _accident_props_from_line(line: str) -> list[str]:
    """提取一句里被破坏类动词带出的受事故物名词。

    优先取动词后的短名词短语（带倒水杯→水杯）；若动词后是补语/动词
    （踢倒挡一下），回看动词前「把/将」之后的名词（把鞋架踢倒→鞋架）。
    """
    found: list[str] = []
    for m in _RE_ACCIDENT_VERBS.finditer(line):
        after = line[m.end():]
        head = re.sub(r"^[了到在过上这那一个是把将]", "", after)
        seg = re.match(r"[一-鿿]{1,6}", head)
        candidate = ""
        if seg:
            raw = seg.group(0)
            if _RE_PROP_SKIP.match(raw):
                candidate = ""
            else:
                candidate = _RE_PROP_TAIL.sub("", raw)
        if not candidate:
            # 回看动词前的「把/将 + 名词」
            before = line[: m.start()]
            bm = re.search(r"[把将]([一-鿿]{1,6})[^一-鿿]*$", before)
            if bm:
                candidate = _RE_PROP_TAIL.sub("", bm.group(1))
        if candidate and not _RE_PROP_SKIP.match(candidate):
            found.append(candidate)
    return found


def _score_accident_prop_grounding(
    story: dict,
    lines: list[str],
) -> tuple[int, list[str]]:
    """B 类：事故物须先落地——正文被撞倒/砸碎/碰翻的物件，须在 setting 或该句之前的正文出现过。

    返回 (bonus, details)，bonus ≤ 0（只扣分不加分）。命中凭空道具则每次扣分并出详情。
    """
    setting = str(story.get("setting") or "").strip()
    known_so_far = setting
    hits: list[str] = []
    for i, ln in enumerate(lines):
        for prop in _accident_props_from_line(ln):
            if len(prop) < 2:
                continue
            if prop not in known_so_far:
                hits.append(f"「{ln[:18]}」的「{prop}」前面没出现过")
            else:
                known_so_far += prop
        known_so_far += ln
    if not hits:
        return 0, []
    return -15, ["事故道具凭空（" + "；".join(hits[:2]) + "）"]


# 说人话/儿童说话：对白里出现类型元语言或成人书面/网络职场词 = 掉书袋。
# 类型元语言（剧本/类型术语泄漏进角色嘴里）：
# 「规矩/规则」是孩子家常口语（「这是规矩」），不算掉书袋，排除。
_RE_META_SPEECH = re.compile(
    r"甩锅|结盟|翻车|露馅|分工|计划|策略|套路|秘密|诡计|目标|方案|"
    r"收尾|补救|连锁"
)
# 成人书面/网络职场词（孩子不该这么说）：
_RE_ADULT_SPEECH = re.compile(
    r"搞定|总之|关键|情况|事情|绝对|毕竟|显然|坦白说|说实话|搞不好|"
    r"性价比|靠谱|优化|及时止损|舍己为人|煞费苦心|感人肺腑|以身作则|"
    r"归根结底|分析一下|关键问题是|失误在于|主要原因|根本原因"
)


def _score_childlike_diction(lines: list[str]) -> tuple[int, list[str]]:
    """对白是否「说人话」：抓类型元语言与成人书面词泄漏。

    开局（前 4 句）出现即扣（开场定观众观感，最不能掉书袋）；
    全篇≥2 处也扣；仅正文零星 1 处不判（容忍孩子偶尔冒出）。
    返回 (bonus, details)，bonus ≤ 0。
    """
    hits: list[str] = []
    for i, ln in enumerate(lines):
        for pat, kind in ((_RE_META_SPEECH, "类型术语"), (_RE_ADULT_SPEECH, "成人词")):
            for m in pat.finditer(ln):
                frag = m.group(0)
                if frag == "秘密" and re.search(r"我的秘密|小秘密", ln):
                    continue
                hits.append((i, f"对白[{i}]「{frag}」（{kind}：{ln[:20]}）"))
    if not hits:
        return 0, []
    opening_hits = [d for i, d in hits if i < 4]
    if opening_hits or len(hits) >= 2:
        shown = (opening_hits or [d for _, d in hits])[:2]
        return -8, ["说人话：对白掉书袋（" + "；".join(shown) + "）"]
    return 0, []


def _score_relevancy(story: dict, theme: str | None) -> tuple[int, list[str]]:
    if not theme:
        return 0, []

    theme_chars_raw = re.findall(r"[\u4e00-\u9fff]", theme)
    theme_words: list[str] = []
    for length in (4, 3, 2):
        for i in range(len(theme_chars_raw) - length + 1):
            w = "".join(theme_chars_raw[i:i + length])
            if w not in theme_words:
                theme_words.append(w)
    if not theme_words:
        return 0, []

    core = str(story.get("conflict_core") or "")
    setting = str(story.get("setting") or "")
    lines = _dialogue_lines(story)
    opening = story.get("discovery_opening")
    has_opening = isinstance(opening, list) and opening
    if has_opening:
        first4 = "".join(lines[:4]) if len(lines) >= 4 else "".join(lines)
        check_text = core + setting + first4
    else:
        check_text = core + setting + "".join(lines)

    matched_long = [w for w in theme_words if len(w) >= 3 and w in check_text]
    matched_any = [w for w in theme_words if w in check_text]
    # 短主题容易因语序/虚词后缀漏判（如「浇花」→「把花浇透」、
    # 「擦桌子」→「把饭桌擦干净」，其中「子」是后缀未必出现），
    # 补单字检查：≥2 字主题至少命中 2 个单字即算扣题
    if not matched_any and 2 <= len(theme_chars_raw) <= 4:
        singles = [w for w in theme_words if len(w) == 1]
        if not singles:
            singles = theme_chars_raw
        hit_n = sum(1 for s in singles if s in check_text)
        need = 2 if len(theme_chars_raw) >= 3 else len(theme_chars_raw)
        if hit_n >= need:
            return 0, []
    # 长主题（≥5 字）常把物件嵌在 conflict_core 单字里（画作→画），
    # 2-gram 对不上时看主题前两字是否已在核心/开场落地。
    if not matched_any and len(theme_chars_raw) >= 5:
        if any(c in check_text for c in theme_chars_raw[:2]):
            return 0, []
    if not matched_any:
        return -30, [f"跑题：主题「{theme}」未在核心/开场中体现"]
    return 0, []


def _score_redundancy(lines: list[str]) -> tuple[int, list[str]]:
    n = len(lines)
    if n < 8:
        return 0, []

    body_end = max(4, n - 4)
    body_lines = lines[:body_end]
    if len(body_lines) < 4:
        return 0, []

    all_text = "".join(body_lines)
    word_counts = Counter(
        w for w in _CONTENT_WORD_RE.findall(all_text)
        if w not in _REDUNDANCY_STOP_WORDS
    )
    debate_words = {w for w, _ in word_counts.most_common(8)}

    max_consecutive_hits = 0
    worst_word = ""
    for i in range(len(body_lines) - 3):
        window = body_lines[i:i + 4]
        for word in debate_words:
            hit_lines = sum(1 for line in window if word in line)
            if hit_lines > max_consecutive_hits:
                max_consecutive_hits = hit_lines
                worst_word = word

    if max_consecutive_hits >= 4:
        return -10, [f"「{worst_word}」连续4句绕圈"]
    if max_consecutive_hits >= 3:
        return -5, [f"「{worst_word}」连续3句偏绕"]

    hook_hits = 0
    worst_hook = ""
    for phrase in _A_DRUDGE_PHRASES:
        n_hit = sum(1 for line in body_lines if phrase in line)
        if n_hit > hook_hits:
            hook_hits = n_hit
            worst_hook = phrase
    if hook_hits >= 5:
        return -12, [f"中段「{worst_hook}」复读拖沓"]
    if hook_hits >= 4:
        return -7, [f"中段「{worst_hook}」偏重复"]

    for stem in ("漱口", "两分钟", "重来", "停了"):
        n_hit = sum(1 for line in body_lines if stem in line)
        if n_hit >= 4:
            return -10, [f"中段「{stem}」复读拖沓"]

    # 刷牙预热注水：有一锤但前面「认真数/三十下」过多 → 不算紧凑
    pad_n = sum(
        1
        for line in body_lines
        if re.search(r"三十下|认真数|帮你盯|你确定能|偷工减料|起步", line)
    )
    if pad_n >= 2:
        return -8, ["中段预热注水，好笑被拖死"]

    # 中段身份/把关话术过多 = 拖沓，不给「节奏紧凑」加分
    auth_pad = sum(
        1
        for line in body_lines
        if re.search(r"我是姐姐|我说了算|检查员|把关|听我的|你得听", line)
    )
    if auth_pad >= 5:
        return -6, ["中段身份/把关话术过多"]

    return 2, ["节奏紧凑"]


def _subseq_in_window(frag: str, hay: str, *, max_extra: int = 3) -> bool:
    """frag 按原顺序落在 hay 的一个近距窗口内（允许原话多出少量字）。

    容忍引话省略助词/插入词（「关门要轻点」↔「关门记得要轻点」），
    窗口 ≤ len(frag)+max_extra，防止跨句拼出假出处。
    """
    if not frag or not hay:
        return False
    for start in range(len(hay)):
        if hay[start] != frag[0]:
            continue
        j = 1
        limit = min(len(hay), start + len(frag) + max_extra)
        for k in range(start + 1, limit):
            if j < len(frag) and hay[k] == frag[j]:
                j += 1
        if j >= len(frag):
            return True
    return False


def _fragment_grounded_in_text(fragment: str, haystack: str, *, min_run: int = 5) -> bool:
    frag = re.sub(r"[的话呢呀嘛吧啊…\s「」『』“”\"'‘’：:]", "", fragment)
    hay = re.sub(r"[\s「」『』“”\"'‘’]", "", haystack)
    if len(frag) < min_run:
        min_run = max(3, len(frag))
    if len(frag) < 3:
        return True
    # ≥6 字引文：连续命中，或按序落在近距窗口（容忍省字），
    # 禁止靠 2 字片拼出「假出处」
    if len(frag) >= 6:
        run = min(6, len(frag))
        for i in range(len(frag) - run + 1):
            if frag[i:i + run] in hay:
                return True
        return _subseq_in_window(frag, hay)
    run = min(min_run, len(frag))
    for i in range(len(frag) - run + 1):
        if frag[i:i + run] in hay:
            return True
    if _subseq_in_window(frag, hay):
        return True
    # 短引文才允许同义改写：2 字片过半命中
    pieces = [frag[i:i + 2] for i in range(0, len(frag) - 1, 2)]
    if len(pieces) >= 3:
        hit = sum(1 for p in pieces if p in hay)
        if hit >= (len(pieces) * 2 + 2) // 3:
            return True
    return False


def _collect_humor_issues(
    lines: list[str],
    *,
    type_code: str,
    speakers: list[str] | None = None,
) -> list[str]:
    """好笑维度的硬伤（不直接改结构分，用于压低好笑分）。"""
    cons: list[str] = []
    if len(lines) < 6:
        return cons

    profile = quality_profile_for_code(type_code)
    body = lines[:-4] if len(lines) > 4 else lines[:-1]
    tail4 = lines[-4:] if len(lines) >= 4 else lines
    body_text = "".join(body)
    quote_haystack = body_text
    if profile.closing_quote_haystack:
        quote_haystack = profile.closing_quote_haystack(
            lines, speakers, body_text,
        )

    for line in tail4:
        for m in _RE_DIRECT_QUOTE.finditer(line):
            frag = m.group(1).strip()
            grounded = _fragment_grounded_in_text(frag, quote_haystack)
            if profile.ground_closing_quote:
                grounded = grounded or profile.ground_closing_quote(
                    frag, quote_haystack,
                )
            if not grounded:
                cons.append(f"收束引话无出处（「{frag[:12]}」）")
                if profile.stop_on_ungrounded_quote:
                    return cons

    if profile.collect_humor_issues:
        cons.extend(profile.collect_humor_issues(lines, speakers))
    return cons


def _score_funniness(
    lines: list[str],
    *,
    type_code: str,
    humor_issues: list[str],
    speakers: list[str] | None = None,
) -> tuple[int, list[str], list[str]]:
    """好笑维度 0–20，叠在结构分（≤80）之上。"""
    cons = list(humor_issues)
    pros: list[str] = []
    if len(lines) < 6:
        return 0, pros, cons

    profile = quality_profile_for_code(type_code)
    if any("无出处" in c for c in cons):
        if profile.stop_on_ungrounded_quote:
            return 0, pros, cons
        cons = [c for c in cons if "无出处" not in c]

    body = lines[:-4] if len(lines) > 4 else lines[:-1]
    tail4 = lines[-4:] if len(lines) >= 4 else lines
    mid_text = "".join(body[: max(1, len(body) * 2 // 3)])
    full_text = "".join(lines)
    late4_text = "".join(tail4)

    points = 0
    # 模板复读等：不是扣结构，而是好笑加分项一律不计（无“有意思的点”）
    humor_blocked = any(
        any(
            k in c
            for k in (
                "模板复读",
                "中段动作复读",
                "缺字面歪读点",
                "肢体抢物复读",
            )
        )
        for c in cons
    )
    scene_pts, scene_pros = 0, []
    if not humor_blocked and profile.score_scene_beat:
        scene_pts, scene_pros = profile.score_scene_beat(
            lines, text_has_hammer_beat=_text_has_hammer_beat,
        )
    if scene_pts:
        points += scene_pts
        pros.extend(scene_pros)
    elif not humor_blocked and _text_has_hammer_beat(mid_text):
        points += 5
        pros.append("有一锤场面")
    elif not humor_blocked and _text_has_hammer_beat(full_text):
        points += 2
        pros.append("有具体场面")

    grounded_tail = any(
        p in late4_text
        for p in (
            "你刚才说",
            "你自己说",
            "你不是说",
            "明明说",
            "你自己",
            "你说的",
            # D 变体回旋镖「你说别太多…倒完」：引的正是前文叮嘱原话
            "你说别",
            # E 类闭环侧写句式（对妈少用「你」硬质问）：自己说的规矩…
            "自己说",
        )
    )
    if (
        not humor_blocked
        and grounded_tail
        and not any("无出处" in c for c in cons)
    ):
        points += 4
        pros.append("收束扣原话")

    if not humor_blocked:
        if profile.score_specificity_bonus:
            # 类型专属 +2 同位替代（D：数字具体量 OR 荒诞整体执行，任一风味即给）
            points += profile.score_specificity_bonus(lines, speakers)
        elif len(_RE_NUMBER_BONUS.findall(full_text)) >= 2:
            points += 2

    if not humor_blocked and profile.score_funniness_tail:
        tail_pts, tail_pros = profile.score_funniness_tail(lines, speakers)
        points += tail_pts
        pros.extend(tail_pros)

    points = _apply_humor_issue_caps(points, cons, profile)

    points = max(0, min(20, points))

    return points, pros, cons


def score_daily_story(
    story: dict | None,
    *,
    theme: str | None = None,
) -> dict[str, Any]:
    """给故事打观感分。

    评分模型：
    - 结构分（格式、层数、收束形态、节奏）80 满分扣分制
    - humor_regex_points 仅作离线诊断（修订 hint），不计入总分
    - 发布线好笑由 LLM 审读注入 funny_score（0-20）；
      有 LLM 时总分 = 结构 + LLM 好笑 − 审读硬伤；无 LLM 时总分暂=结构分
    """
    if not isinstance(story, dict):
        return {
            "grade": "偏弱",
            "score": 0,
            "summary": "无有效故事内容",
            "reasons": ["故事为空"],
        }

    # 扣分制：结构满分 80，各维度未达标逐项扣分，cons 与分数严格对应。
    # 不再有「40 基准 + 加分」，任何格式/节奏/收束形态缺陷都能在 reasons 里看到扣分。
    score = STRUCTURE_SCORE_CAP
    pros: list[str] = []
    cons: list[str] = []

    dialogue = story.get("dialogue") if isinstance(story.get("dialogue"), list) else []
    lines = _dialogue_lines(story)
    speakers = _dialogue_speakers(story)
    last = lines[-1] if lines else ""
    tail2 = "".join(lines[-2:]) if lines else ""
    prev2 = "".join(lines[-3:-1]) if len(lines) >= 3 else "".join(lines[:-1])

    # ── 跑题：一次扣到位 ──
    rel_bonus, rel_details = _score_relevancy(story, theme)
    score += rel_bonus
    if rel_bonus < 0:
        cons.extend(rel_details)

    # ── 必备字段 ──
    if not str(story.get("conflict_core") or "").strip():
        score -= 10
        cons.append("缺 conflict_core")

    explain = str(story.get("punchline_explain") or "")
    profile = resolve_quality_profile(story)

    from app.services.daily_story.story_types import story_type_punchline_conflict

    type_conflict = story_type_punchline_conflict(story)
    if type_conflict:
        cons.append(type_conflict)

    if not explain or not any(m in explain for m in _PUNCHLINE_TYPE_MARKERS):
        score -= 10
        cons.append("笑点解析缺类型")

    # ── 开场维度（满分 2）：gold_chat 正文无 discovery_opening 时不扣 ──
    opening = story.get("discovery_opening")
    body_only = not isinstance(opening, list) or not opening
    if body_only and len(lines) >= 16:
        pass
    elif not isinstance(opening, list) or not (
        DAILY_STORY_OPENING_LINES_MIN
        <= len(opening)
        <= DAILY_STORY_OPENING_LINES_MAX
    ):
        score -= OPENING_SCORE_FULL
        cons.append("缺发现开场")
    elif profile.score_opening_quality:
        op_pts, op_pros, op_cons = profile.score_opening_quality(story)
        opening_deduction = max(
            0,
            OPENING_SCORE_FULL - min(OPENING_SCORE_FULL, max(0, op_pts)),
        )
        if opening_deduction:
            score -= opening_deduction
            cons.append(f"开场未满（-{opening_deduction}）")
        pros.extend(op_pros)
        cons.extend(op_cons)

    if profile.collect_fact_issues:
        fact_issues = profile.collect_fact_issues(story)
        if fact_issues:
            for issue in fact_issues:
                cons.append(issue)
            score -= min(
                21,
                len(fact_issues) * profile.fact_issue_penalty,
            )
        else:
            if profile.code in ("A", "B", "C"):
                pros.append("事实自洽")

    # ── 角色违规 ──
    mom_n = sum(
        1 for d in dialogue
        if isinstance(d, dict) and str(d.get("speaker") or "").strip() == "妈妈"
    )
    if mom_n >= profile.mom_lines_penalty_at:
        score -= profile.mom_lines_penalty
        cons.append(f"妈妈台词偏多（{mom_n}句）")

    if profile.penalize_mom_judge:
        for pat in _MOM_JUDGE_PATTERNS:
            if any(
                pat in str(d.get("line") or "")
                for d in dialogue
                if isinstance(d, dict) and d.get("speaker") == "妈妈"
            ):
                score -= 25
                cons.append(f"妈妈裁判式收场（{pat}）")
                break

    if _has_consecutive_sibling(dialogue):
        score -= 15
        cons.append("存在同人连说")

    # ── 事故道具凭空（B 类翻车连锁）──
    if profile.code == "B":
        prop_bonus, prop_details = _score_accident_prop_grounding(story, lines)
        score += prop_bonus
        if prop_bonus < 0:
            cons.extend(prop_details)

    # ── 说人话/儿童说话（类型元语言与成人词泄漏）──
    child_bonus, child_details = _score_childlike_diction(lines)
    score += child_bonus
    if child_bonus < 0:
        cons.extend(child_details)

    # ── 收束硬伤 ──
    weak_hit = False
    if profile.penalize_wait_mom_end and any(m in tail2 for m in _WEAK_END_WAIT_MOM):
        score -= 25
        cons.append("收束甩给妈妈")
        weak_hit = True
    if profile.penalize_split_end and any(m in tail2 for m in _WEAK_END_SPLIT):
        score -= 20
        cons.append("收束偏和解")
        weak_hit = True
    if profile.penalize_stubborn_end and any(m in last for m in _WEAK_END_STUBBORN):
        score -= 15
        cons.append("耍赖软收")
        weak_hit = True

    # ── 收束破功：达标制（先破功再软收 / 末句破功 = 达标不减分）──
    limp = any(m in last for m in _LIMP_SOFT_CLOSE_MARKERS)
    punched = any(m in prev2 for m in profile.punch_before_soft_markers) or any(
        m in prev2 or m in last for m in _STRONG_END_MARKERS
    )
    if limp and not punched:
        score -= 20
        cons.append("无破功软收")
        weak_hit = True
    elif limp and punched:
        pros.append("先破功再软收")
    elif any(m in last for m in _STRONG_END_MARKERS):
        pros.append("末句有破功落点")

    layer_patterns = profile.layer_patterns()

    # ── 推进维度（满分 14）：4 层达标；3层-6 / 2层-12 / ≤1层-14 ──
    esc_bonus, esc_details = _score_escalation(lines, layer_patterns=layer_patterns)
    esc_achieved = max(0, min(ESCALATION_SCORE_FULL, esc_bonus))
    esc_deduction = ESCALATION_SCORE_FULL - esc_achieved
    score -= esc_deduction
    if esc_deduction:
        cons.append(f"冲突推进不足（-{esc_deduction}）")
    else:
        pros.extend(esc_details)

    # ── 节奏维度：紧凑达标不减；绕圈/拖沓按原扣分（-5~-12）──
    red_bonus, red_details = _score_redundancy(lines)
    if red_bonus < 0:
        score += red_bonus
        cons.extend(red_details)
    elif red_bonus > 0:
        pros.extend(red_details)

    # ── 收束形态（满分 8）：有回旋镖/反转/破功落点 = 达标；无 = 扣满 ──
    punch_bonus, punch_details = score_punchline_for_profile(
        profile, lines, speakers, prev2, last,
    )
    humor_issues = _collect_humor_issues(
        lines, type_code=profile.code, speakers=speakers,
    )
    if humor_issues:
        grounded = not any("无出处" in c for c in humor_issues)
        if not grounded and punch_bonus > 8:
            punch_bonus = 8
            punch_details = [
                d for d in punch_details
                if "破功" in d or "闭环" in d
            ][:2]

    if punch_bonus > 0:
        pros.extend(punch_details)
    else:
        score -= PUNCHLINE_SCORE_FULL
        cons.append(f"收束形态未落位：无回旋镖/反转/破功落点（-{PUNCHLINE_SCORE_FULL}）")
        if punch_details:
            cons.extend(punch_details)

    if profile.code == "I":
        from app.services.daily_story.story_types.i.quality import score_i_trailing_tail

        tail_ded, tail_cons = score_i_trailing_tail(lines)
        if tail_ded:
            score -= tail_ded
            cons.extend(tail_cons)

    structure_score = max(0, min(STRUCTURE_SCORE_CAP, score))
    # humor_regex_points：离线诊断（cons→修订 hint），不计入 score / 总分。
    humor_regex_points, humor_pros, humor_cons = _score_funniness(
        lines,
        type_code=profile.code,
        humor_issues=humor_issues,
        speakers=speakers,
    )
    pros.extend(humor_pros)
    cons.extend(humor_cons)
    pros.append(f"结构{structure_score}")
    # score 暂=结构分；finalize 有 LLM 好笑才加成总分
    grade = _grade_from_score(structure_score)
    summary = _build_summary(
        pros, cons, grade, profile.summary_highlight_tokens,
    )

    return {
        "grade": grade,
        "score": structure_score,
        "structure_score": structure_score,
        "humor_regex_points": humor_regex_points,
        "summary": summary,
        "reasons": [*pros, *cons],
    }


def _build_summary(
    pros: list[str],
    cons: list[str],
    grade: str,
    highlight_tokens: tuple[str, ...],
) -> str:
    highlights = [
        p for p in pros
        if any(k in p for k in highlight_tokens)
    ]

    if cons:
        severe = any(
            w in c
            for c in cons
            for w in (
                "甩给妈妈", "和解", "无破功", "跑题",
                "无出处", "未埋旧账", "模板", "拖沓", "好笑不足", "末四拍",
                "未扣一锤", "仍发指令",
            )
        )
        if severe or grade == "偏弱":
            primary = next(
                (
                    c for c in cons
                    if any(
                        k in c
                        for k in (
                            "收束", "软收", "绕圈", "跑题", "推进",
                            "出处", "模板", "拖沓", "公平", "好笑",
                        )
                    )
                ),
                cons[0],
            )
            summary = primary
            if len(cons) > 1:
                summary += f"，另有{len(cons) - 1}项"
            return summary
        if highlights:
            parts = list(highlights)
            minor = next((c for c in cons if "绕圈" in c), None)
            if minor:
                parts.append(f"（{minor}）")
            return "，".join(parts)

    if highlights:
        return "，".join(highlights)
    if grade == "偏弱":
        return "无明显亮点"
    return "结构完整，收束一般"


def structure_score_of(quality: dict[str, Any] | None) -> int:
    """读取结构分（生成循环 target 用这个，勿用含好笑的总分）。"""
    if not isinstance(quality, dict):
        return 0
    if quality.get("structure_score") is not None:
        try:
            return int(quality["structure_score"])
        except (TypeError, ValueError):
            pass
    try:
        return int(quality.get("score") or 0)
    except (TypeError, ValueError):
        return 0


def _is_humor_score_reason(reason: str) -> bool:
    """reasons 里由 regex 好笑分产出的标签（非 LLM 正式分）。"""
    s = str(reason).strip()
    if s.startswith("正则好笑"):
        return True
    if s.startswith("好笑") and len(s) > 2 and s[2:].isdigit():
        return True
    return s in ("好笑够格", "好笑达标", "很好笑")


def finalize_daily_story_total(
    quality: dict[str, Any],
    *,
    humor: dict[str, Any] | None = None,
    review_penalty_points: int = 0,
) -> dict[str, Any]:
    """总分 = 结构 + LLM 好笑 − 审读硬伤（有 LLM 时）。

    无 LLM ``humor.funny_score`` 时：总分暂=结构分，``humor_pending=True``，
    不判发布线。``humor_regex_points`` 仅保留作离线诊断。
    """
    structure = structure_score_of(quality)
    funny = 0
    source = "pending"
    if isinstance(humor, dict) and humor.get("funny_score") is not None:
        try:
            funny = max(0, min(20, int(humor.get("funny_score"))))
            source = "llm"
            humor_type = humor.get("humor_type")
            if humor_type not in ("natural", "formulaic", "none"):
                humor_type = "none"
            quality["humor"] = {
                "funny_score": funny,
                "best_moment": str(humor.get("best_moment") or "").strip()[:40],
                "humor_type": humor_type,
            }
        except (TypeError, ValueError):
            source = "pending"
    if source != "llm":
        quality.pop("humor", None)
        quality["humor_pending"] = True
    else:
        quality["humor_pending"] = False

    points = max(0, int(review_penalty_points or 0))
    if source == "llm":
        total = max(0, min(100, structure + funny - points))
    else:
        total = structure

    quality["score"] = total
    quality["grade"] = _grade_from_score(total)

    reasons = [
        r
        for r in (quality.get("reasons") or [])
        if not str(r).startswith("总分")
        and not str(r).startswith("发布达标")
        and not str(r).startswith("未达发布线")
        and not str(r).startswith("LLM好笑")
        and not str(r).startswith("好笑待LLM审读")
        and not _is_humor_score_reason(str(r))
    ]
    if source == "llm":
        if not any(str(r).startswith("好笑") and str(r)[2:].isdigit() for r in reasons):
            reasons.append(f"好笑{funny}")
        pass_ok = structure >= 75 and funny >= HUMOR_PUBLISH_MIN
        quality["pass"] = pass_ok
        if pass_ok:
            reasons.append(
                f"发布达标：结构{structure}≥75，"
                f"LLM好笑{funny}/20≥{HUMOR_PUBLISH_MIN}"
            )
        else:
            misses = []
            if structure < 75:
                misses.append(f"结构{structure}<75")
            if funny < HUMOR_PUBLISH_MIN:
                misses.append(f"好笑{funny}/20<{HUMOR_PUBLISH_MIN}")
            reasons.append(
                f"未达发布线（{'，'.join(misses)}，"
                f"须结构≥75且好笑≥{HUMOR_PUBLISH_MIN}）"
            )
        tail = f"-硬伤{points}" if points else ""
        reasons.append(f"总分{total}=结构{structure}+LLM好笑{funny}{tail}")
        quality["summary"] = f"结构{structure}，好笑{funny}，总分{total}"
    else:
        quality.pop("pass", None)
        reasons.append("好笑待LLM审读")
        reasons.append(f"总分{total}=结构{structure}（好笑待LLM审读）")
        quality["summary"] = f"结构{structure}，好笑待LLM审读，总分{total}"
    quality["reasons"] = reasons
    return quality


def attach_daily_story_quality(
    story: dict[str, Any],
    *,
    theme: str | None = None,
    finalize: bool = True,
) -> dict[str, Any]:
    """重算观感分。默认 finalize=True：有 LLM 好笑则总分=结构+LLM 好笑，否则暂=结构分。

    生成循环比较结构分请用 ``structure_score_of(quality)``，不要看总分。
    若稿上已有 LLM ``quality.humor``，finalize 时保留并优先用它。
    """
    if not isinstance(story, dict):
        return story
    from app.services.daily_story.story_types import repair_punchline_explain_for_story_type

    repair_punchline_explain_for_story_type(story)
    prev = story.get("quality") if isinstance(story.get("quality"), dict) else None
    prev_humor = prev.get("humor") if isinstance(prev, dict) else None
    quality = score_daily_story(story, theme=theme)
    if finalize:
        finalize_daily_story_total(
            quality,
            humor=prev_humor if isinstance(prev_humor, dict) else None,
        )
    story["quality"] = quality
    return story


def build_quality_revision_hints(
    quality: dict,
    *,
    story: dict | None = None,
) -> str:
    """根据质量评分结果，生成**单维度**修订指令（一次只推一项）。"""
    from app.services.daily_story.retry_hints import (
        format_c_dialogue_scope_hint,
        format_quality_consecutive_revision_hint,
        pick_primary_quality_issue,
        revision_scope_kind,
    )

    reasons = quality.get("reasons", [])
    pros = [r for r in reasons if not any(
        r.startswith(w) for w in (
            "缺", "存", "妈", "无破功", "收束偏", "耍赖", "跑题",
            "收束引", "引先例收", "追问闭", "偏C", "模板", "拖沓",
            "C收束", "C中段", "格式达标", "收束引话无出处",
        )
    )]
    cons = [r for r in reasons if r not in pros]

    profile = resolve_quality_profile(story)
    esc_type_hint, close_type_hint = profile.revision_hints()
    has_punch_ending = closing_satisfied(pros, profile)
    score = structure_score_of(quality)

    hints: list[str] = []
    primary_kind: str | None = None

    kind, issue_text = pick_primary_quality_issue(cons)
    if kind and issue_text:
        primary_kind = kind
        from app.services.daily_story.story_types import parse_story_type_code

        code = parse_story_type_code(
            punchline=str((story or {}).get("punchline_explain") or ""),
        )
        q_profile = quality_profile_for_code(code)
        if kind == "redundancy":
            hints.append(
                f"【去绕圈】{issue_text}。同一逻辑点最多 2 句，删重复回合；"
                "若删后偏短，用新证据补 1 来回，勿动末四拍。"
            )
        elif kind == "consecutive":
            from app.services.daily_story.prompts import dialogue_total_chars

            chars = dialogue_total_chars(story) if isinstance(story, dict) else 0
            hints.append(
                format_quality_consecutive_revision_hint(
                    chars=chars,
                    type_code=code,
                ),
            )
        elif kind == "humor" and q_profile.humor_revision_hint:
            hint = q_profile.humor_revision_hint(issue_text)
            if not hint and "好笑不足" in issue_text:
                hint = q_profile.humor_revision_hint("好笑不足")
            if hint:
                hints.append(hint)
            else:
                # 主项是「格式达标但好笑不足」等元问题、自身无定点可修时，
                # 退回扫具体 con：取第一个能映射出定点修 hint 的具体毛病
                # （照做口头禅复读/回旋镖未点破…），让 refine 对准病灶，
                # 而不是泛泛「中段一件具体小事升级」。
                # 注意：部分 humor con（照做口头禅复读/回旋镖未点破…）不以
                # 上方黑名单前缀开头，会被误分进 pros，故补扫含「不好笑/不好玩」的 reason。
                humor_cons = cons + [
                    r
                    for r in reasons
                    if r not in cons and ("不好笑" in r or "不好玩" in r)
                ]
                fallback = next(
                    (
                        q_profile.humor_revision_hint(c)
                        for c in humor_cons
                        if q_profile.humor_revision_hint(c)
                    ),
                    None,
                )
                hints.append(
                    fallback
                    or (
                        f"【好笑】{issue_text}。中段一件具体小事升级，"
                        "收束只引前文真实说过的话。"
                    )
                )
        elif kind in ("fact", "opening"):
            hint = None
            if q_profile.humor_revision_hint:
                hint = q_profile.humor_revision_hint(issue_text)
            if hint:
                hints.append(hint)
            else:
                hints.append(f"【修补】{issue_text}。")
        elif kind in ("c_filmable", "c_chatter", "c_de_a", "quote", "c_reason_repeat"):
            hint = (
                q_profile.humor_revision_hint(issue_text)
                if q_profile.humor_revision_hint
                else None
            )
            hints.append(hint or f"【修补】{issue_text}。")

    need_esc = False
    layer_info = next((r for r in pros if "推进" in r), "")
    if not hints:
        if not layer_info or "2层" in layer_info or "偏少" in layer_info:
            need_esc = True
        elif "3层" in layer_info and score < 75 and has_punch_ending:
            need_esc = True
        if need_esc:
            primary_kind = primary_kind or "escalation"
            hints.append(esc_type_hint)
        elif not has_punch_ending:
            primary_kind = primary_kind or "closing"
            hints.append(close_type_hint)

    for c in cons:
        if hints:
            break
        if "缺 conflict_core" in c:
            hints.append(
                "【补 conflict_core】添加 ≤24 字冲突摘要，格式「谁 vs 谁争什么」。",
            )
        if "缺发现开场" in c:
            hints.append("【补开场】添加 2 句正片开端（地点+画面），点名冲突实物。")

    if not hints:
        return ""

    scope = revision_scope_kind(
        primary_kind=primary_kind,
        escalation=need_esc,
        closing=not has_punch_ending,
    )
    if profile.code == "C" and isinstance(story, dict) and primary_kind != "opening":
        scope_line = format_c_dialogue_scope_hint(story, scope)
        if scope_line:
            hints.append(scope_line)
    if primary_kind == "opening":
        hints.append(
            "【改稿范围】只改 discovery_opening（须 2 句，有背景有画面）；"
            "正文 dialogue 与末四拍勿动。",
        )

    return "\n".join(hints)


def build_quality_edit_scope_hint(
    story: dict | None,
    revision_blob: str,
) -> str:
    """C 类观感修订：限定可改 dialogue 行号，避免整稿重写。"""
    if not isinstance(story, dict) or not (revision_blob or "").strip():
        return ""
    from app.services.daily_story.story_types import parse_story_type_code

    code = parse_story_type_code(
        punchline=str(story.get("punchline_explain") or ""),
    )
    if code != "C":
        return ""

    dialogue = story.get("dialogue")
    n = len(dialogue) if isinstance(dialogue, list) else 0
    if n < 6:
        return ""

    blob = revision_blob
    if any(
        k in blob
        for k in (
            "推进", "升级", "绕圈", "去绕圈", "冲突",
            "归谁", "你没叠", "口水战", "缺可拍争法", "字面加赛",
        )
    ):
        end = max(3, n - 4)
        return (
            f"【改稿范围】只改 dialogue 第 3–{end} 行（中段交锋）；"
            "末 4 句收束已合格则逐字保留，禁止改坏回旋镖。"
        )
    if any(
        k in blob
        for k in ("收束", "回旋镖", "C·", "好笑", "末句", "末段", "C类")
    ):
        start = max(0, n - 4)
        return (
            f"【改稿范围】只改 dialogue 第 {start + 1}–{n} 行（末段收束）；"
            f"第 1–{start} 行须原样保留（speaker 与 line 勿动）。"
        )
    if any(k in blob for k in ("绕圈", "去绕圈")):
        end = max(3, n - 4)
        return (
            f"【改稿范围】只改 dialogue 第 3–{end} 行（中段交锋）；"
            "勿动末 4 句收束与 setting/conflict_core。"
        )
    return (
        "【改稿范围】优先改中段或末 4 句；禁止换 conflict_core 与主题。"
    )
