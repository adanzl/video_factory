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


# 结局播报词：平铺直叙复述结果（「全滚出来」「掉一地」「被抓住」），比有口吻的候选弱
_OUTCOME_REVEAL_RE = re.compile(r"全滚|滚出来|滚出去|掉一地|全没了|全撒|弄翻|被抓住|被抓|掉地上|露馅|败露|被抓现行")
# 复述剧情词：「露馅了/被抓了/满身渣/满地都是」这类把笑点直接剧透的结局复述，重罚
_SPOILER_RE = re.compile(r"露馅|被抓|被抓住|满地都是|满身|全掉|全洒|全撒|散了一地|被抓现行|完了|死定了")

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


def pick_best_chat_title(draft: str, candidates: list[str], *, max_len: int, avoid_titles: list[str] | None=None, anchor_words: list[str] | None=None) -> str:
    """从多个候选中选最终标题：退化保护 + 长度硬截断 + 钩子分排序。

    - 命中初稿或 avoid_titles（已用过的标题）的候选降权，避免手动重跑输出同一个；
    - 问号/叹号/称呼开头/甩锅质问优先于平铺直叙的事件复述；
    - anchor_words：本场核心名词（如「月饼」）。含核心名词的候选 +2（贴主题），
      不含的 -8 重罚；全部候选都不含核心词时回退初稿，绝不写跑题标题；
    - **防御当前标题**：以初稿自身的钩子分为基线，候选必须严格更高才替换。
      否则手动重跑会把「妈，月饼自己滚的」(3分) 换成「偷吃月饼翻车记」(0分)，
      越跑越差、来回跳。
    """
    avoid = [str(t).strip() for t in (avoid_titles or []) if str(t).strip()]
    anchors = [str(a).strip() for a in (anchor_words or []) if str(a).strip()]
    draft_core = title_core(draft)
    avoid_cores = {title_core(t) for t in avoid}
    best = draft
    best_score = _chat_title_hook_score(draft)
    any_anchored = False
    for cand in candidates:
        chosen = select_optimized_title(draft, cand, max_len=max_len)
        score = _chat_title_hook_score(chosen)
        anchored = (not anchors) or any(a in title_core(chosen) for a in anchors)
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


def build_chat_title_system_prompt(*, max_title_len: int = CHAT_TITLE_MAX_LEN) -> str:
    """chat 流水线标题：面向孩子与有娃家长，硬上限 ≤10 字。"""
    max_title_len = _clamp_chat_title_len(max_title_len)
    return (
        "你是家庭日常对话短剧的标题编辑，面向孩子和有娃的大人。"
        "根据剧本输出 JSON，字段 title。"
        f"title：≤{max_title_len} 字，不含空格换行，适合短封面。"
        "\n【最高优先：主题】标题必须让人一眼看出本集在讲什么，落在"
        "user prompt 的「故事主题」上（如「约好一起藏玩具别让妈妈发现」→"
        "标题要让人知道是藏玩具被发现的戏，不能只写「渣印谁踩的」这种和主题无关的局部画面）。"
        "钩子（口吻/问句/反差）是为主题服务的，只能加在主题之上，不能把主题换掉。"
        "\n【最高目标：让人想点开】标题要像家长刷到会停一下的亲子短视频——"
        "有画面、有反差、有口吻，一看就想知道「然后呢」。"
        "最忌讳的是把剧情复述一遍（「偷看电视露馅了」「月饼渣踩得满地都是」）——"
        "那是剧情简介，不是标题。"
        "\n【标题句式模板】围绕本集主题抓最强钩子（只讲句式，不给成品例："
        "禁止把别的故事里的话/梗直接套用过来），按优先级："
        "\n①荒谬反差账（最好）：为一点小事赔上很大代价的「账」，把悬殊说半截吊胃口——"
        "句式骨架如「为[一小块]赔上[一整盒]」「[一点渣]换来[一屋乱]」，具体数字/数量放进去，"
        "让「得不偿失」的荒诞自己说话。这是最想让人点开的一类。"
        "\n②越补越糟：小动作引出连锁意外，把「怎么越弄越糟」的狼狈留半截，不报结局。"
        "\n③台词钩子：冲突高潮里孩子针对本主题说的原话，稍压虚词，像在替孩子喊话"
        "（可带甩锅「不是我」——但只能把锅甩给剧本里确实自发发生、或孩子原话里归咎的事："
        "剧本写「手扶茶几盒子翻了」是孩子碰翻的，就绝不能写「月饼是它自己翻的/滚的」；"
        "剧本写「线缠住脚」是线的问题，才能写「是线自己缠的」）。"
        "\n④悬念藏匿：藏/偷/瞒 + 藏住的东西，勾起「后来呢」。"
        "\n【标题生成规则】"
        f"\n- 硬性：标题必须 ≤{max_title_len} 字（最终上架字数以此为准）"
        "\n- 主题锚定（最高优先，硬性）：标题必须能看出本集主题（user prompt 的「故事主题」），"
        "并包含该主题的核心名词（user prompt 列出的「核心名词」）；"
        "只写局部画面/道具/甩锅口吻而看不出主题的候选作废"
        "\n- 优先来源：①punchline_explain 里的荒谬反差（浓缩成「为X赔上Y」的账）"
        "②冲突高潮里孩子针对主题的甩锅/辩解台词；③核心道具+动作的具体画面；"
        "④故事主题本身（浓缩成有口吻的短句，不是平铺复述）"
        "\n- 要有口吻或轻反差，让家长一秒认出「自家日常笑点」"
        "\n- 不用描述性事件名（如「抢饼干」「姐弟吵架」）"
        "\n- 禁止为了短删掉钩子：超字只删虚词/语气词，保住钩子词"
        "\n- 禁止复述剧情/报结局：不要把「露馅了」「被抓了」「满身渣」这类结局直接说出来"
        "（那等于把笑点提前剧透）。要留半截：只说「越补越糟」的过程或荒谬的「账」，别说到头。"
        "\n- 推锅必须基于剧本真实意外：剧本写明是孩子碰翻的（手扶茶几盒子翻了），"
        "就绝不能写「月饼是它自己翻的/滚的」；剧本写「线缠住脚」才能写「是线自己缠的」"
        "\n- 称呼要符合剧本：只准用剧本里孩子原话出现过的称呼，且只在孩子真的"
        "对被瞒对象/在场角色说话时才用；瞒着妈妈藏/偷的戏（妈妈在厨房、孩子藏玩具），"
        "孩子不会开口叫妈妈，标题就绝不能开场写「妈妈，…」或「妈，…」来点破"
        "\n- 钩子要落在具体好笑画面：把一个道具+动作（「擦」「踩」「摔」「翻」）放进标题，"
        "让读者能脑补画面，别写泛泛的结果；优先找「为偷吃一口赔上一整盒」式的荒谬反差账"
        "\n- 三个候选句式要拉开（一句荒谬反差账 / 一个具体道具意外 / 一句孩子原话或悬念），"
        "禁止用「谁…」「…怨谁」质问句——「谁干的/谁碰的/谁先露馅」已刷屏，"
        "一律不用，换成荒谬账、孩子原话、具体道具+动作"
        "\n- 钩子只准来自剧本实际内容（冲突核心/对话原话/反差说明/核心道具）："
        "禁止给剧本编造剧本里没有的细节、道具或意外原因"
        "（如剧本里电视是孩子开的，就绝不能写「电视自己开的」）；"
        "禁止写一个完全脱离本剧本的现成短句"
        "\n- 坏标题示例：「姐弟偷吃饼干」「月饼全滚出来了」「被妈妈抓住」「孩子的选择」"
        "「偷看电视露馅了」「谁干的」"
        'JSON 输出样例：{"titles": ["候选1", "候选2", "候选3"]}。'
        "三个候选句式/口吻尽量不同，最有钩子的放第一个；"
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
    anchor_note = ""
    if anchors:
        anchor_note = f"\n【硬性】标题必须包含本场核心名词：{'、'.join(anchors)}。不含核心名词的标题不合格，作废重写。"

    return (
        f"初稿标题：{draft_title}\n"
        f"剧本内容：\n{context}\n\n"
        "第一步，先用一句话写下本集最荒谬/反差最强的那个点"
        "（如「为了偷吃一口月饼，赔上整盒」「藏个玩具，弄出满屋渣」，"
        "一定要从剧本里的具体连锁/台词来，别凭空想）——这行写在 JSON 外面，不要进 JSON。"
        "第二步，围绕这个点写 3 个候选 title（同一 JSON 数组，最有钩子的放第一个）："
        "三个候选必须各自抓**三个不同画面/角度**——比如①荒谬反差账（为X赔上Y）、"
        "②具体道具+动作的瞬间（渣印、线缠、水杯翻这种定格画面）、③孩子原话或悬念；"
        "严禁三个都套同一句式（别全是「为X赔上Y」），严禁三个都说同一件事的不同说法。"
        f"每个必须 ≤{max_title_len} 字：超字只删虚词/语气词，禁止删成事件名、禁止为了短丢钩子。"
        "钩子只从本剧本的冲突高潮台词/反差/核心道具里提炼，禁止套用与剧本无关的现成短句；"
        "禁止给剧本编造剧本里没有的细节、道具或意外原因；"
        "推锅口吻只能指向剧本里确实自发发生或孩子原话归咎的事（如剧本写明是孩子手滑碰翻的，"
        "就绝不能写「是它自己翻的/滚的」）；"
        "称呼只准用剧本孩子原话里的，且只在孩子真对被瞒对象/在场角色说话时用——"
        "瞒着妈妈藏/偷的戏孩子不会喊妈妈，标题不能开场「妈妈，…」「妈，…」点破。"
        "主题锚定（最高优先）：标题必须落在本集主题上（上面「故事主题」），"
        "让人一眼看出这集在讲什么；可以含蓄，但不能只留一个局部画面/道具/甩锅口吻把主题丢掉。"
        f"{anchor_note}"
        "别平铺直叙复述结局；优先找一个具体好笑画面或「为偷吃一口赔上整盒」式的荒谬反差，"
        "用人物口吻、问句或留半截吊起来。"
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
