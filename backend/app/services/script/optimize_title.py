"""标题优化：提示词、LLM 响应解析与步骤组装。"""

from __future__ import annotations

import re
from typing import Any

from app.config import get_settings
from app.services.topic.text import normalize_title
from app.utils.title_text import select_optimized_title, title_core

_TITLE_HOOK_FORMULAS = (
    "【高点击标题模板】择最适合口播内容的一种强化（可组合，总字数仍须≤上限）："
    "①误区反问式：「你以为X？其实Y」「X不是Y，而是Z」「别再把X当Y了」；"
    "②反差好奇式：「X竟然会Y」「原来X是这样」「X背后藏着Y」；"
    "③悬念具象式：用具体场景/名词开头（如「雪崩瞬间」「磁铁靠近」），"
    "后半补反差或疑问（「为啥会…」「千万别…」「真相是…」）；"
    "④对话反转式：先抛出一个事件或矛盾（常用问号），再用带态度的口语回应——自信、调侃、挑衅，不要平淡陈述。如「日本断供光刻胶？中国的五年产能等你呢」「限芯令升级？华为笑而不语」；"
    "⑤对比打脸式：「X说Y，结果Z」「号称X，实际Y」，适合辟谣或反转类内容。"
)

_TITLE_TECHNIQUES = (
    "【写法技巧】"
    "前 8～12 字承载最大钩子（移动端封面第一眼）；"
    "用具体名词、数字、对比替代空泛词（禁用「小知识」「了解一下」「科普」作主体）；"
    "可用轻疑问、轻否定、轻反差，禁止标题党（震惊、绝绝子、不转不是、99%的人都）；"
    "禁止平淡陈述（「关于X的介绍」「X原理解读」「X是怎么回事」）。"
    "若口播为儿童科普口吻，标题面向家长/学生点击：好奇悬念优先，勿装婴儿语。"
)

_TITLE_SELF_CHECK = (
    "【输出前自检】"
    "① 3 秒内能否让人想问「真的吗/为什么」；"
    "② 是否比初稿更有信息增量或情绪张力；"
    "③ 是否未超出字数、未编造口播未提及的事实。"
)

_DIALOGUE_RETENTION_NOTE = (
    "注意：如果初稿已经是「事件？嘲讽回应」格式（如「日本断供光刻胶？仓库堆成山了」），"
    "优化时后半句只删字不换字，保持原意和态度不变。超过字数就删末尾字，不要改写。"
)


def build_title_optimize_system_prompt(*, max_title_len: int) -> str:
    return (
        "你是 B 站科普短视频标题优化师。根据初稿标题与口播内容，输出 JSON，字段 title。"
        f"title 为优化后的视频标题：不含空格换行，≤{max_title_len} 字，适合封面最多三行展示。"
        "若初稿含冒号（：）、问号等标点，优化后须保留，勿删除。"
        "优化目标：显著提升点击欲，保留核心主题，让人忍不住点进来看答案。"
        f"{_TITLE_HOOK_FORMULAS}"
        f"{_TITLE_TECHNIQUES}"
        f"{_TITLE_SELF_CHECK}"
        f"{_DIALOGUE_RETENTION_NOTE}"
        "不得改变口播主题方向，不得引入口播未涉及的新概念或虚假夸张。"
        "硬性禁止：医疗养生、理财股市、时政情感、热点新闻、真人出镜、无法核验的争议。"
        'JSON 输出样例：{"title": "优化后标题"}'
    )


def build_title_optimize_user_prompt(
    *,
    draft_title: str,
    narration: str,
    max_title_len: int,
) -> str:
    snippet = narration.strip().replace("\n", "")
    if len(snippet) > 500:
        snippet = snippet[:500] + "…"
    return (
        f"初稿标题：{draft_title}\n"
        f"口播内容（用于提炼最强钩子，勿照搬长句）：{snippet}\n\n"
        "请先从口播中找出 1 个最强反常识点、反差或悬念，再据此写 title。"
        f"要求比初稿「{draft_title}」更有点击欲；若初稿已平淡，须明显改写而非换同义词。"
        f"输出 ≤{max_title_len} 字的 title。"
    )


def parse_title_optimize_payload(raw: dict[str, Any], *, max_title_len: int) -> str:
    title = raw.get("title")
    if not isinstance(title, str) or not title.strip():
        raise ValueError("LLM title optimize response missing title")
    return normalize_title(title, max_len=max_title_len)


def parse_chat_title_candidates_payload(raw: dict[str, Any], *, max_title_len: int) -> list[str]:
    """chat 标题多候选解析：接受 ``{"titles": [...]}`` 或 ``{"title": "..."}``。

    逐个 normalize_title（长度硬卡），去空去重，保序。
    """
    titles = raw.get("titles")
    if not isinstance(titles, list) or not titles:
        single = raw.get("title")
        titles = [single] if isinstance(single, str) and single.strip() else []
    out: list[str] = []
    seen: set[str] = set()
    for t in titles:
        if not isinstance(t, str) or not t.strip():
            continue
        t = normalize_title(t, max_len=max_title_len)
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    if not out:
        raise ValueError("LLM chat title optimize response missing titles")
    return out


# 结局播报词：平铺直叙复述结果（「全滚出来」「掉一地」），比有口吻的候选弱
# 「被抓/被抓现行/露馅/翻车/散伙」不算：它们是 B 类结盟翻车的类型结局，孩子话，允许
_OUTCOME_REVEAL_RE = re.compile(r"全滚|滚出来|滚出去|掉一地|全没了|全撒|弄翻|掉地上|败露")
# 复述剧情词：纯负能量/报流水账的词重罚；「被抓/露馅/翻车/散伙」等类型结局词不罚
_SPOILER_RE = re.compile(r"满地都是|满身|全掉|全洒|全撒|散了一地|完了|死定了")

# 中文核心名词多为 2 字（月饼/电视/玩具/洗澡…）；4 字几乎都是动词+名词拼的整句
_ANCHOR_NGRAM_ORDER = (2, 3, 4)

# 汉字范围：判断词在正文里是否前后有非汉字边界
_CJK_CHAR_RE = re.compile(r'[一-鿿]')


def _word_boundary_in_blob(word: str, blob: str) -> bool:
    """word 在 blob 里是否至少出现一次「前或后紧邻非汉字」的独立词位。

    防止把 4 字场景在词边界外切成坏碎片：如「偷看电视」里三字窗口「偷看电」
    在正文中只出现在「偷看电视」内部（前后都是汉字），不算独立词，不能当核心名词。
    """
    start = 0
    while True:
        i = blob.find(word, start)
        if i < 0:
            return False
        before_ok = i == 0 or not _CJK_CHAR_RE.match(blob[i - 1])
        after_ok = i + len(word) >= len(blob) or not _CJK_CHAR_RE.match(blob[i + len(word)])
        if before_ok or after_ok:
            return True
        start = i + 1


# 提取主题兜底词时过滤的虚字/连接字（「约好一起藏玩具」里的「约好」「一起」是衔接词，不是核心名词）
_ANCHOR_FUNC_CHARS = frozenset("的了着又再先就把被给让在是都也还却自己之与和或你我他它妈吧吗呢别让约好")


def _extract_theme_fallback(theme: str, story_content: dict) -> list[str]:
    """scene_title 提取不到核心名词时，从故事主题兜底提取（2–4 字）。

    场景标题可能太短/太口语（「藏玩具同盟」正文里只有词内出现），
    而主题（「约好一起藏玩具别让妈妈发现」）里藏着核心名词「玩具」。

    只保留同时出现在正文（conflict_core/setting）里的词——主题的衔接词
    （「约好」「一起」「别让」）不会出现在正文，被滤掉；「玩具」这种核心名词
    在正文（玩具车）和主题里都有，被留下。
    """
    theme = title_core(theme)
    if not theme:
        return []
    body = ''.join(str(story_content.get(k) or '') for k in ('conflict_core', 'setting'))
    for n in _ANCHOR_NGRAM_ORDER:
        found: list[str] = []
        for i in range(len(theme) - n + 1):
            w = theme[i:i + n]
            if any(ch in _ANCHOR_FUNC_CHARS for ch in w):
                continue
            if w in body and w not in found:
                found.append(w)
        if found:
            return found[:2]
    return []


def extract_core_anchor_words(draft: str, story_content: dict) -> list[str]:
    """提取本场核心名词（2–4 字）：原始 scene_title 与冲突核心/场景/主题共有的词。

    用于「标题必须包含核心名词」的硬要求与 picker 兜底，防「鞋底渣印谁擦」式
    盯住次级元素、把核心主题（月饼）丢掉。

    只保留在正文中有独立词位（前/后非汉字）的候选，避免「偷看电」这类把
    「偷看电视」从词边界切开的坏碎片进提示词、被 LLM 照抄成病句标题。

    scene_title 提不到（太短/只出现在词内）时，用主题（theme）兜底提取核心名词，
    让标题仍能锚定主题；两者都取不到时返回空列表 = 不强制。
    """
    scene = title_core(str(story_content.get('scene_title') or draft or ''))
    if not scene:
        return []
    blob = ''.join(str(story_content.get(k) or '') for k in ('conflict_core', 'setting', 'theme'))
    for n in _ANCHOR_NGRAM_ORDER:
        found: list[str] = []
        for i in range(len(scene) - n + 1):
            w = scene[i:i + n]
            if w in blob and w not in found and _word_boundary_in_blob(w, blob):
                found.append(w)
        if found:
            return found[:2]
    return _extract_theme_fallback(str(story_content.get('theme') or ''), story_content)


# 主题动作动词：用来拼「动作+核心名词」的完整主题短语（偷看电视/偷吃月饼/藏玩具）
_THEME_ACTION_VERBS = frozenset(
    "偷藏抢争系叠刷洗吃喝看切收开关拿拖浇穿脱端擦摆玩躲装翻摸掏塞摘扯踢吹按"
)
# 常见双字动作动词（动词+动词或副词+动词），如「偷看」「偷吃」「藏」——每个词单独一个元素
_THEME_ACTION_2CHAR = frozenset(
    {
        "偷看", "偷吃", "偷藏", "偷拿", "偷玩", "偷翻", "偷喝", "偷用",
        "抢着", "争着", "藏着", "躲着", "拖着", "端着", "擦着", "玩着", "翻着",
        "系紧", "叠好", "刷完", "洗完", "吃完", "喝完", "看完", "切好",
        "收好", "关好", "放好", "拖好", "浇好", "穿好", "脱好", "摆好", "摘好",
    }
)


def extract_theme_action_phrase(draft: str, story_content: dict) -> str:
    """提取本集「完整动作+核心名词」的主题短语（如「偷看电视」「偷吃月饼」「藏玩具」）。

    专家要求标题必须原样保留这个完整动作短语（「偷看电视」绝不可缩成「偷电视」）。
    从 theme / conflict_core / scene_title 里找「动作动词+紧邻核心名词」组合；
    找不到就退回核心名词本身。
    """
    anchor = extract_core_anchor_words(draft, story_content)
    if not anchor:
        return ""
    noun = anchor[0]
    for src in (
        str(story_content.get('theme') or ''),
        str(story_content.get('conflict_core') or ''),
        str(story_content.get('scene_title') or draft or ''),
    ):
        src = title_core(src)
        i = src.find(noun)
        if i > 0:
            two = src[i - 2:i] if i >= 2 else ""
            if two in _THEME_ACTION_2CHAR:
                return two + noun  # 偷看+电视 → 偷看电视；偷吃+月饼 → 偷吃月饼
            prev = src[i - 1]
            if prev in _THEME_ACTION_VERBS:
                return prev + noun  # 藏+玩具 → 藏玩具
    return noun


def _chat_title_hook_score(title: str) -> int:
    """轻量钩子分：问号/叹号、甩锅口吻、称呼开头；扣结局播报分。

    只做多候选相对排序，不拦截单结果：
    - 问号/叹号、甩锅/辩解词（不是我/谁/怪我）、「自己」（把锅甩给道具）、称呼开头 → 加分；
    - 命中结局动词（全滚/滚出来/掉一地/被抓住…）→ 扣分，事件播报不如有口吻的候选；
    - 逗号不给分：避免「妈，月饼全滚出来了」这类「称呼+平铺直叙」压过真正有口吻的候选。
    """
    score = 0
    if "？" in title or "?" in title:
        score += 3
    if "！" in title or "!" in title:
        score += 1
    # 甩锅声明/辩解（不是我/怪我）加分；「谁…」不加分——它只是质问句一种，
    # 一视同仁避免「谁这个谁那个」刷屏，让孩子原话/具体画面/推锅给东西同台竞争
    if "不是我" in title or "怪我" in title:
        score += 2
    if "自己" in title:
        score += 2
    if title[:1] in "妈姐爸哥弟":
        score += 1
    # 「谁…」质问句本身已刷屏（谁擦的渣/渣印谁擦/谁踩的渣印），
    # 扣 3 让谁字问句整体为负（谁-3 + 问号+3 = 0），让位于荒谬反差/孩子原话/具体道具
    if "谁" in title:
        score -= 3
    # 结局播报重罚：把结局动词全说出来（「月饼全滚出来」「掉一地」「被抓住」）
    # 或把笑点直接剧透（「露馅了/被抓了/满地都是」）——感叹号给 +1 救不回来
    if _SPOILER_RE.search(title) or _OUTCOME_REVEAL_RE.search(title):
        score -= 5
    # 平铺罗列重罚：≥2 个逗号 = 在逐项列事件（「线缠脚上，电视黑了，水杯翻」），
    # 像事故清单没有口吻/结构/账，比有口吻的候选弱
    if title.count("，") + title.count(",") >= 2:
        score -= 3
    return score


def pick_best_chat_title(draft: str, candidates: list[str], *, max_len: int, avoid_titles: list[str] | None=None, anchor_words: list[str] | None=None, story_type: str | None=None) -> str:
    """从多个候选中选最终标题：退化保护 + 长度硬截断 + 钩子分排序。

    - 命中初稿或 avoid_titles（已用过的标题）的候选降权，避免手动重跑输出同一个；
    - 问号/叹号/称呼开头/甩锅质问优先于平铺直叙的事件复述；
    - anchor_words：本场核心名词（如「月饼」）。含核心名词的候选 +2（贴主题），
      不含的 -8 重罚；全部候选都不含核心词时回退初稿，绝不写跑题标题；
    - story_type：命中类型骨架关键词（B 类的「结盟/翻车/露馅」等）→ +2，贴「主题+类型」；
    - **防御当前标题**：以初稿自身的钩子分为基线，候选必须严格更高才替换。
      否则手动重跑会把「妈，月饼自己滚的」(3分) 换成「偷吃月饼翻车记」(0分)，
      越跑越差、来回跳。
    """
    avoid = [str(t).strip() for t in (avoid_titles or []) if str(t).strip()]
    anchors = [str(a).strip() for a in (anchor_words or []) if str(a).strip()]
    draft_core = title_core(draft)
    avoid_cores = {title_core(t) for t in avoid}
    # 完整主题短语（≥3 字，如「偷看电视」）必须完整出现；2 字核心名词（电视）按子串即可
    phrases = [a for a in anchors if len(a) >= 3]
    nouns = [a for a in anchors if len(a) < 3]
    best = draft
    best_score = _chat_title_hook_score(draft)
    any_anchored = False
    for cand in candidates:
        chosen = select_optimized_title(draft, cand, max_len=max_len)
        score = _chat_title_hook_score(chosen)
        if not anchors:
            anchored = True
        elif phrases:
            anchored = any(p in title_core(chosen) for p in phrases)
        else:
            anchored = any(a in title_core(chosen) for a in nouns)
        if anchored:
            any_anchored = True
            # 显式给了核心名词才加分：贴主题的候选该比 hook 同分的局部画面候选优
            if anchors:
                score += 2
        else:
            score -= 8
        if title_core(chosen) == draft_core or title_core(chosen) in avoid_cores:
            score -= 8
        if score > best_score:
            best_score = score
            best = chosen
    if anchors and not any_anchored:
        return draft
    return best

# --------------- chat (daily_story) 标题优化 ---------------

# chat 封面标题 ≤15，跟 standard 一致（放宽到 15 给钩子留足空间）
CHAT_TITLE_MAX_LEN = 15


def _clamp_chat_title_len(max_title_len: int | None) -> int:
    if max_title_len is None:
        return CHAT_TITLE_MAX_LEN
    return max(1, min(int(max_title_len), CHAT_TITLE_MAX_LEN))


# 类型骨架：A–E 故事类型的核心结构，标题要突出「主题 + 类型」，而不是只抓局部画面/道具
_STORY_TYPE_SKELETON = {
    "A": "权威翻车——姐姐立规矩/教人，自己被同一规则戳穿，权威当场垮掉",
    "B": "结盟翻车——俩孩子约好一起干（瞒着妈妈），中途走样连锁崩掉，互甩锅被抓现行",
    "C": "公平执念——争同一资源，双规则互咬，谁先嘴硬谁先输",
    "D": "字面执行——把大人的话抠字面执行到极端，反而把简单事搞砸",
    "E": "妈妈破功——妈妈立规矩，自己先违反/双标，被孩子抓到现场",
}


def _story_type_skeleton(story_type: str | None) -> str:
    """把 story_type（A–E）转成标题优化用的类型骨架描述；未知类型返回空。"""
    key = str(story_type or "").strip().upper()
    return _STORY_TYPE_SKELETON.get(key, "")


def build_chat_title_system_prompt(*, max_title_len: int = CHAT_TITLE_MAX_LEN) -> str:
    """chat 流水线标题：面向孩子与有娃家长，硬上限 ≤10 字。"""
    max_title_len = _clamp_chat_title_len(max_title_len)
    return (
        "你是家庭日常对话短剧的标题编辑，面向孩子和有娃的大人。"
        "根据剧本输出 JSON，字段 title。"
        f"title：≤{max_title_len} 字，不含空格换行，适合短封面。"
        "\n【标题 = 主题 + 类型结局，孩子话，极简】这是唯一标准，三条硬规矩："
        "\n- 主题必须出现（user prompt 的「故事主题」），且必须原样保留该主题的动作+核心名词组合"
        "（如「偷看电视」绝不可缩成「偷电视」）"
        "\n- 类型结局用**孩子话**点出（不是书面术语）："
        "B类是「俩孩子约好干坏事→搞砸→被抓」，孩子话结局词限定用："
        "翻车/散伙/被抓包/搞砸/露馅/没看成/手忙脚乱——"
        "**必须多样化，三个候选不能全押同一个词**"
        "\n- 极简、干净、像孩子脱口而出的一句话，7–10 字，不堆画面"
        "\n【三种形态，三个候选各套一种】用 XX 代表本集故事主题"
        "（完整动作短语，严禁缩减）："
        "\n①XX+结局词：可以写成「XX翻车记」「XX小队散伙了」「XX被抓包」「XX搞砸了」"
        "「XX露馅了」「XX没看成」——**优先选「翻车记」之外的词**，"
        "除非剧本冲突天然就是「翻车」感最强"
        "\n②XX+孩子感叹：「XX咋变这样」「XX咋全露馅」「XX没看成还挨训」"
        "——「挨训」偏成人，建议替换成「被抓包/露馅」"
        "\n③状态词+XX：「手忙脚乱XX」「慌慌张张XX」「偷偷摸摸XX」"
        "（XX 是占位示范，不要照抄成品短句，只套结构）"
        "\n【标题生成规则】"
        f"\n- 硬性：标题必须 ≤{max_title_len} 字"
        "\n- 主题锚定（最高优先，硬性）：标题必须能看出本集故事主题，"
        "且包含该主题的完整动作+核心名词，写漏字变歧义就作废"
        "\n- 口吻要像孩子：多用感叹号「！」、问号、口语虚词（咋/嘛/呀/呗/喽），"
        "禁止书面词（瞒着/赔上/搭上/满屋/一番/之际/挨罚/受罚）"
        "\n- 不用描述性事件名（如「抢饼干」「姐弟吵架」）"
        "\n- 禁止书面类型术语：不要出现「结盟/同盟/权威/公平/字面/破功」"
        "\n- 禁止为了短删掉钩子：超字只删虚词/语气词，保住钩子词"
        "\n- 点结局但别报流水账：可以说「翻车了/散伙了/被抓了」这类类型结局词，"
        "别罗列过程细节（「线缠脚，电视黑，水杯翻」=报流水账，差）"
        "\n- 推锅必须基于剧本真实意外：剧本写明是孩子碰翻的（手扶茶几盒子翻了），"
        "就绝不能写「月饼是它自己翻的/滚的」；剧本写「线缠住脚」才能写「是线自己缠的」"
        "\n- 称呼要符合剧本：只准用剧本里孩子原话出现过的称呼，且只在孩子真的"
        "对被瞒对象/在场角色说话时才用；瞒着妈妈藏/偷的戏（妈妈在厨房、孩子藏玩具），"
        "孩子不会开口叫妈妈，标题就绝不能开场写「妈妈，…」或「妈，…」来点破"
        "\n- 钩子要落在具体好笑画面：把一个道具+动作（「擦」「踩」「摔」「翻」）放进标题，"
        "让读者能脑补画面，别写泛泛的结果"
        "\n- 三个候选必须各套一种形态，禁止三个都套同一种；"
        "禁止用「谁…」「…怨谁」质问句"
        "\n- **结局词多样性（新增）**：三个候选中，「翻车记」最多只能出现一次，"
        "尽量让结局词不重样（如第一个用「散伙了」，第二个用「被抓包」，第三个用「露馅」），"
        "避免所有选题都变成「翻车记」"
        "\n- 钩子只准来自剧本实际内容：禁止编造剧本里没有的细节、道具、意外原因或量词"
        "（如剧本「满地水」绝不能写「满屋水」）"
        "\n- 坏标题示例（书面/大人/复述，差）：「姐弟偷吃饼干」「月饼全滚出来了」"
        "「被妈妈抓住」「偷看电视露馅了」「瞒着妈看个电视赔上满屋水」「谁干的」"
        "「偷电视被抓包」「电视没看成还挨罚」"
        'JSON 输出样例：{"titles": ["候选1", "候选2", "候选3"]}。'
        "三个候选口吻尽量不同，最有钩子的放第一个；"
        "只想出一个方向时也至少列 2 个不同角度的。"
        '（也可退化为 {"title": "单个"}）'
    )


def build_chat_title_user_prompt(
    *,
    draft_title: str,
    story_content: dict,
    max_title_len: int = CHAT_TITLE_MAX_LEN,
    avoid_titles: list[str] | None = None,
) -> str:
    """根据故事内容构建 chat 标题优化的 user prompt。

    avoid_titles：已用过的标题（如手动重跑前的当前标题），让模型换个角度，
    避免「重跑 N 次输出同一个」。
    """
    max_title_len = _clamp_chat_title_len(max_title_len)
    setting = (story_content.get("setting") or "").strip()
    punchline = (story_content.get("punchline_explain") or "").strip()
    dialogue_lines = story_content.get("dialogue") or []
    dialogue_text = ""
    if dialogue_lines and isinstance(dialogue_lines[0], dict):
        parts = [f"{d.get('speaker', '')}：{d.get('line', '')}" for d in dialogue_lines]
        dialogue_text = "\n".join(parts)
    elif dialogue_lines:
        dialogue_text = "\n".join(str(l) for l in dialogue_lines)
    if len(dialogue_text) > 400:
        dialogue_text = dialogue_text[:400] + "…"

    theme = (story_content.get("theme") or "").strip()
    context_parts = []
    if theme:
        context_parts.append(f"故事主题：{theme}")
    theme_phrase = extract_theme_action_phrase(draft_title, story_content)
    if theme_phrase:
        context_parts.append(f"本集主题短语（标题必须原样保留）：{theme_phrase}")
    skeleton = _story_type_skeleton(story_content.get("story_type"))
    if skeleton:
        context_parts.append(f"类型骨架：{skeleton}")
    if setting:
        context_parts.append(f"场景：{setting}")
    conflict_core = (story_content.get("conflict_core") or "").strip()
    if conflict_core:
        context_parts.append(f"冲突核心：{conflict_core}")
    if punchline:
        context_parts.append(f"反差说明：{punchline}")
    context_parts.append(f"对话（优先看结尾与冲突句）：\n{dialogue_text}")
    context = "\n".join(context_parts)

    avoid_note = ""
    if avoid_titles:
        seen = "、".join(str(t).strip() for t in avoid_titles if str(t).strip())
        if seen:
            avoid_note = f"\n已用过的标题：{seen}。这次换一个角度，别和它们同方向。"

    anchors = extract_core_anchor_words(draft_title, story_content)
    theme_phrase = extract_theme_action_phrase(draft_title, story_content)
    anchor_note = ""
    if theme_phrase:
        anchor_note = f"\n【硬性】标题必须原样保留本集主题短语「{theme_phrase}」"
        f"（如「{theme_phrase}」不能缩成「{theme_phrase[-2:]}」或只留核心名词）。"
        "不含完整主题短语的标题不合格，作废重写。"
    elif anchors:
        anchor_note = f"\n【硬性】标题必须包含本场核心名词：{'、'.join(anchors)}。不含核心名词的标题不合格，作废重写。"

    return (
        f"初稿标题：{draft_title}\n"
        f"剧本内容：\n{context}\n\n"
        "第一步，先看清本集的「主题 + 类型结局」：本集主题短语是"
        f"「{theme_phrase or draft_title}」，"
        "类型结局要用**孩子话**表达（翻车/散伙/被抓包/搞砸/露馅/没看成/手忙脚乱）。"
        "（这行写在 JSON 外面，不要进 JSON。）"
        "第二步，写 3 个候选 title（同一 JSON 数组，最有钩子的放第一个），"
        "**三个候选必须各套一种形态**（XX=本集主题短语，别照抄别的故事）："
        "①XX+结局词（XX翻车记 / XX小队散伙了）；"
        "②XX+孩子感叹（XX咋变这样）；"
        "③状态词+XX（手忙脚乱XX / 慌慌张张XX）。"
        "都落在「主题 + 类型结局」上，极简干净，别只抓一个局部道具/意外（「线缠脚电视黑」这种=没点出结局）。"
        f"每个必须 ≤{max_title_len} 字：超字只删虚词/语气词，禁止删成事件名、禁止为了短丢钩子。"
        "钩子只从本剧本的冲突高潮台词/反差/核心道具里提炼，禁止套用与剧本无关的现成短句；"
        "禁止给剧本编造剧本里没有的细节、道具、意外原因或量词"
        "（如剧本只说「满地水」就绝不能写「满屋水」）；"
        "推锅口吻只能指向剧本里确实自发发生或孩子原话归咎的事（如剧本写明是孩子手滑碰翻的，"
        "就绝不能写「是它自己翻的/滚的」）；"
        "称呼只准用剧本孩子原话里的，且只在孩子真对被瞒对象/在场角色说话时用——"
        "瞒着妈妈藏/偷的戏孩子不会喊妈妈，标题不能开场「妈妈，…」「妈，…」点破。"
        "主题锚定（最高优先，硬性）：标题必须原样保留本集主题短语（上面「本集主题短语」）"
        "和类型结局（上面「类型骨架」的结局，用孩子话）——"
        "禁止「结盟/同盟/权威/公平/字面/破功」这类书面术语，"
        "但「翻车/散伙/搞砸/没看成/被抓包/露馅」这类孩子话结局词**允许并鼓励**。"
        f"{anchor_note}"
        "点结局但别报流水账；用孩子口吻、问句或留半截吊起来。"
        f"{avoid_note}"
    )


def build_chat_title_prompts(
    draft_title: str,
    story_content: dict,
    *,
    max_title_length: int | None = None,
    avoid_titles: list[str] | None = None,
) -> dict[str, str]:
    max_len = _clamp_chat_title_len(max_title_length)
    return {
        "step": "chat_title_optimize",
        "label": "标题优化",
        "system": build_chat_title_system_prompt(max_title_len=max_len),
        "user": build_chat_title_user_prompt(
            draft_title=draft_title,
            story_content=story_content,
            max_title_len=max_len,
            avoid_titles=avoid_titles,
        ),
    }


def build_title_optimize_prompts(
    draft_title: str,
    narration: str,
    *,
    max_title_length: int | None = None,
) -> dict[str, str]:
    settings = get_settings()
    max_len = settings.max_title_length if max_title_length is None else max_title_length
    return {
        "step": "title_optimize",
        "label": "标题优化",
        "system": build_title_optimize_system_prompt(max_title_len=max_len),
        "user": build_title_optimize_user_prompt(
            draft_title=draft_title,
            narration=narration,
            max_title_len=max_len,
        ),
    }
