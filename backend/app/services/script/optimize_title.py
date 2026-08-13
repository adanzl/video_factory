"""标题优化：提示词、LLM 响应解析与步骤组装。"""

from __future__ import annotations

import re
from typing import Any, Callable

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


def _candidate_has_anchor(candidate: str, anchors: list[str]) -> bool:
    """候选是否包含主题锚词：完整短语（≥3 字）必须完整出现；2 字核心名词按子串。"""
    if not anchors:
        return True
    core = title_core(candidate)
    phrases = [a for a in anchors if len(a) >= 3]
    nouns = [a for a in anchors if len(a) < 3]
    if phrases:
        return any(p in core for p in phrases)
    return any(a in core for a in nouns)


def filter_chat_title_candidates(candidates: list[str], anchor_words: list[str]) -> list[str]:
    """候选层硬校验：只保留包含主题锚词（完整短语优先）的候选。"""
    anchors = [str(a).strip() for a in (anchor_words or []) if str(a).strip()]
    return [c for c in candidates if _candidate_has_anchor(c, anchors)]


def ensure_chat_title_candidates(
    candidates: list[str],
    anchor_words: list[str],
    *,
    fetch_candidates: Callable[[], list[str]],
    max_attempts: int = 3,
) -> list[str]:
    """候选层硬校验+补足：缺主题锚词的候选作废；不足 3 个时重生成补足（去重保序）。"""
    seen: set[str] = set()
    out: list[str] = []
    for c in filter_chat_title_candidates(candidates, anchor_words):
        if c not in seen:
            seen.add(c)
            out.append(c)
    attempts = 0
    while len(out) < 3 and attempts < max_attempts:
        try:
            more = fetch_candidates()
        except Exception:
            break
        for c in filter_chat_title_candidates(more, anchor_words):
            if c not in seen:
                seen.add(c)
                out.append(c)
        attempts += 1
    return out[:3]


def build_chat_title_polish_prompts(
    title: str,
    draft_title: str,
    story_content: dict,
    *,
    max_title_len: int | None = None,
) -> dict[str, str]:
    """标题润色提示词：只修语病/读感，不改主题、不换钩子方向。"""
    max_len = _clamp_chat_title_len(max_title_len)
    theme_phrase = extract_theme_action_phrase(draft_title, story_content)
    skeleton = _story_type_skeleton(story_content.get("story_type"))
    type_key = str(story_content.get("story_type") or "").strip().upper()
    words = _STORY_TYPE_OUTCOME_WORDS.get(type_key)
    block_note = ""
    if words:
        block = "、".join(words.get("block", ()))
        block_note = f"\n- 禁止出现黑名单词：{block}；"
    system = (
        "你是家庭日常对话短剧标题的润色编辑。只负责让标题更顺口、更自然，禁止改主题。"
        f"输出 JSON，字段 title；title 不含空格换行，≤{max_len} 字。"
        'JSON 输出样例：{"title": "润色后标题"}'
    )
    user = (
        f"原初稿标题：{draft_title}\n"
        f"当前标题：{title}\n"
        f"主题短语（必须原样保留）：{theme_phrase or draft_title}\n"
    )
    if skeleton:
        user += f"类型骨架：{skeleton}\n"
    user += (
        "【润色要求】"
        "\n- 最小改动：只修语病、读感、节奏；可加逗号、语气词（了/呗/呀），可微调语序；"
        "\n- 禁止删掉原标题里的任何内容字（动词/结局词/钩子词），只能加字、加标点或调整语序；"
        "\n- 主题短语必须完整保留，且放在句首或中段，禁止放在句尾倒装；"
        "\n- 保持原有钩子方向和类型结局，不要换成另一个句式/结局词；"
        "\n- 润色后仍须孩子气：若原标题用了咋/凭啥/说好/明明/白忙/亏/赖皮，必须保留；"
        "\n- 不能有语病：必须通顺，不能缺字、缺动词、语序倒错；"
        "\n- 专门修语病：主谓宾要完整、语序要自然；缺主语要补（「说好先挑」→「说好我先挑」），"
        "主题短语被拆散要理顺（「说好分蛋糕先挑」→「分蛋糕说好我先挑」），"
        "缺语气词要补（「白忙」→「白忙了/白忙一场」）；"
        "\n- 保持短促封面感：不要为了补全句子把标题加长，能短则短；"
        "\n- 禁止新增剧本没有的细节、道具或夸张；"
        f"\n- 只要有一点点不顺或缺字就必须修，修不动才原样输出；{block_note}"
        f"\n- 输出 ≤{max_len} 字。"
    )
    return {
        "step": "chat_title_polish",
        "label": "标题润色",
        "system": system,
        "user": user,
    }


def parse_chat_title_polish_payload(raw: dict[str, Any], *, max_title_len: int) -> str:
    title = raw.get("title")
    if not isinstance(title, str) or not title.strip():
        raise ValueError("LLM title polish response missing title")
    return normalize_title(title, max_len=max_title_len)


_POLISH_OPTIONAL_CHARS = frozenset("的了着过吧吗呢啊呀呗啦")


def _polish_keeps_content(source: str, candidate: str) -> bool:
    """润色硬校验：只允许加字/调序/加标点，不允许删原标题的内容字。"""
    src_chars = {
        ch
        for ch in source
        if _CJK_CHAR_RE.match(ch) and ch not in _POLISH_OPTIONAL_CHARS
    }
    cand_chars = set(candidate)
    return src_chars <= cand_chars


def _title_anchor_parts(draft_title: str, story_content: dict) -> tuple[list[str], list[str]]:
    anchors = extract_core_anchor_words(draft_title, story_content)
    phrase = extract_theme_action_phrase(draft_title, story_content)
    if phrase and phrase not in anchors:
        anchors = [phrase, *anchors]
    phrases = [a for a in anchors if len(a) >= 3]
    return anchors, phrases


def _polish_candidate_ok(
    candidate: str,
    source: str,
    anchors: list[str],
    phrases: list[str],
    story_content: dict,
    *,
    allow_deletion: bool = False,
) -> bool:
    """润色/修复候选的硬校验：无变化、缺锚词、书面词、倒装、句尾、删内容字都拒收。"""
    if candidate == source:
        return False
    core = title_core(candidate)
    if not _candidate_has_anchor(candidate, anchors):
        return False
    info_hit, _, block_hit, _ = _story_type_word_hit(
        candidate,
        story_content.get("story_type"),
    )
    if (
        block_hit
        or _story_type_inversion_hit(candidate, story_content.get("story_type"))
        or _story_type_grammar_bad_hit(candidate, story_content.get("story_type"))
    ):
        return False
    type_key = (story_content.get("story_type") or "").strip().upper()
    type_words = _STORY_TYPE_OUTCOME_WORDS.get(type_key)
    if type_words and type_words.get("info") and not info_hit:
        return False
    if phrases and any(core.endswith(p) for p in phrases):
        return False
    if not allow_deletion and not _polish_keeps_content(source, candidate):
        return False
    return True


def build_chat_title_grammar_check_prompt(
    title: str,
    story_content: dict,
    *,
    max_title_len: int | None = None,
) -> dict[str, str]:
    """标题语病审核提示词：只判断，不修改。"""
    max_len = _clamp_chat_title_len(max_title_len)
    return {
        "step": "chat_title_grammar_check",
        "label": "标题语病审核",
        "system": "你是短视频标题语病审核员。只判断，不修改。输出 JSON，字段 ok（bool）和 reason（string）。",
        "user": (
            f"标题：{title}\n"
            f"标题应 ≤{max_len} 字。判断标准：\n"
            "- 主谓宾完整、不缺主语、不缺动词；\n"
            "- 语序自然，无倒装错位（如「被大块走」「大块凭啥给他」）；\n"
            "- 无歧义（如「分蛋糕赖皮」会被读成蛋糕在赖皮）；\n"
            "- 无残缺感（如「白忙」「说好先挑」缺补足或主语）；\n"
            "- 压缩过度也算语病：如「赖皮大的归你」「白忙选小的」缺成分、词序错乱。\n"
            "- 常见病句示例：「分蛋糕凭啥先挑大的亏了」缺主语/连接；"
            "「分蛋糕说好我先挑，亏我让大块」缺「出/了」；"
            "「分蛋糕明明先挑，白忙一场」「分蛋糕先挑，大块咋归你？」缺「我」，会被读成蛋糕先挑。\n"
            "- 好例：「凭啥大的归你」「白忙一场，选了小的」「说好我先挑」；"
            "「分蛋糕我先挑大的，凭啥还亏了」「分蛋糕说好我先挑，亏我让出大块」"
            "「分蛋糕明明我先挑，白忙一场」「分蛋糕我先挑，大块咋归你？」。\n"
            'JSON 输出样例：{"ok": true, "reason": ""} 或 '
            '{"ok": false, "reason": "缺主语，应为「分蛋糕说好我先挑」"}。'
        ),
    }


def parse_chat_title_grammar_check_payload(raw: dict[str, Any]) -> tuple[bool, str]:
    ok = raw.get("ok")
    if not isinstance(ok, bool):
        raise ValueError("LLM grammar check response missing ok")
    return ok, str(raw.get("reason") or "")


def build_chat_title_grammar_fix_prompts(
    title: str,
    draft_title: str,
    story_content: dict,
    reason: str,
    *,
    max_title_len: int | None = None,
) -> dict[str, str]:
    """语病修复提示词：把审核意见回喂给模型，只补字/调序，不删内容字。"""
    max_len = _clamp_chat_title_len(max_title_len)
    theme_phrase = extract_theme_action_phrase(draft_title, story_content)
    type_key = (story_content.get("story_type") or "").strip().upper()
    words = _STORY_TYPE_OUTCOME_WORDS.get(type_key)
    block_note = ""
    if words:
        block = "、".join(words.get("block", ()))
        block_note = f"\n- 禁止出现书面词：{block}；"
    return {
        "step": "chat_title_grammar_fix",
        "label": "标题语病修复",
        "system": "你是短视频标题语病修复编辑。只修语病，不改主题。输出 JSON，字段 title。",
        "user": (
            f"原标题：{title}\n"
            f"主题短语（必须完整保留）：{theme_phrase or draft_title}\n"
            f"语病审核意见：{reason or '标题不通顺'}\n"
            "【修复要求】"
            "\n- 以修好语病为准：可删错位/多余的字、可调语序、可加字；"
            "但必须保留主题短语和核心信息（先挑/大块/白忙/亏/赖皮等）；"
            "\n- 补主语、补语气词、理顺语序，修到读起来通顺自然；"
            "\n- 保持短促封面感，不要为了补全句子加长；"
            "\n- 修复示例：「分蛋糕说好我先挑，赖皮大的归你」→「分蛋糕说好我先挑，凭啥大的归你」；"
            "「明明分蛋糕我先挑，白忙选小的」→「明明我先挑分蛋糕，白忙一场选了小的」；"
            "「分蛋糕说好先挑，咋亏了」→「分蛋糕说好我先挑，咋亏了」；"
            "「分蛋糕凭啥先挑大的亏了」→「分蛋糕我先挑大的，凭啥还亏了」；"
            "「分蛋糕说好我先挑，亏我让大块」→「分蛋糕说好我先挑，亏我让出大块」；"
            "「分蛋糕明明先挑，白忙一场」→「分蛋糕明明我先挑，白忙一场」；"
            "「分蛋糕先挑，大块咋归你？」→「分蛋糕我先挑，大块咋归你？」。"
            f"\n- 主题短语必须完整保留且放在句首或中段；{block_note}"
            f"\n- 输出 ≤{max_len} 字。"
            'JSON 输出样例：{"title": "修好的标题"}'
        ),
    }


def polish_chat_title(
    title: str,
    draft_title: str,
    story_content: dict,
    *,
    max_len: int,
    fetch_json: Callable[[dict[str, str]], dict[str, Any]],
    check_json: Callable[[dict[str, str]], dict[str, Any]] | None = None,
    max_attempts: int = 2,
) -> str:
    """对选中标题做一次轻量润色；硬校验不过则回退原标题。"""
    prompts = build_chat_title_polish_prompts(
        title,
        draft_title,
        story_content,
        max_title_len=max_len,
    )
    anchors, phrases = _title_anchor_parts(draft_title, story_content)
    result = title
    for _ in range(max_attempts):
        try:
            raw = fetch_json(prompts)
            candidate = parse_chat_title_polish_payload(raw, max_title_len=max_len)
        except Exception:
            break
        if _polish_candidate_ok(candidate, title, anchors, phrases, story_content):
            result = candidate
            break
    if check_json is None:
        return result
    try:
        raw = check_json(
            build_chat_title_grammar_check_prompt(result, story_content, max_title_len=max_len)
        )
        ok, reason = parse_chat_title_grammar_check_payload(raw)
    except Exception:
        return result
    if ok and not _story_type_grammar_bad_hit(
        result,
        story_content.get("story_type"),
    ):
        return result
    if ok:
        reason = "标题压缩过度或语序有语病（如「赖皮大的归你」）"
    for _ in range(max_attempts):
        fix_prompts = build_chat_title_grammar_fix_prompts(
            result,
            draft_title,
            story_content,
            reason,
            max_title_len=max_len,
        )
        try:
            raw = fetch_json(fix_prompts)
            candidate = parse_chat_title_polish_payload(raw, max_title_len=max_len)
            ok2, reason2 = parse_chat_title_grammar_check_payload(
                check_json(
                    build_chat_title_grammar_check_prompt(
                        candidate,
                        story_content,
                        max_title_len=max_len,
                    )
                )
            )
        except Exception:
            break
        if not _polish_candidate_ok(
            candidate,
            result,
            anchors,
            phrases,
            story_content,
            allow_deletion=True,
        ):
            continue
        if ok2:
            return candidate
        reason = reason2
    return result


# 结局播报词：平铺直叙复述结果（「全滚出来」「掉一地」），比有口吻的候选弱
# 「被抓/被抓现行/露馅/翻车/散伙」不算：它们是 B 类结盟翻车的类型结局，孩子话，允许
_OUTCOME_REVEAL_RE = re.compile(r"全滚|滚出来|滚出去|掉一地|全没了|全撒|弄翻|掉地上|败露")
# 复述剧情词：纯负能量/报流水账的词重罚；「被抓/露馅/翻车/散伙」等类型结局词不罚
_SPOILER_RE = re.compile(r"满地都是|满身|全掉|全洒|全撒|散了一地|完了|死定了")

# 中文核心名词多为 2 字（月饼/电视/玩具/洗澡…）；4 字几乎都是动词+名词拼的整句
_ANCHOR_NGRAM_ORDER = (2, 3, 4)
# scene_title 扫描用「最长优先」：完整短语（分蛋糕/抢遥控器）先于 2 字碎片，
# 否则「分蛋」「控器」这类前缀/后缀碎片会因单侧边界被误判成独立词
_ANCHOR_SCENE_NGRAM_ORDER = (4, 3, 2)

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
    for n in _ANCHOR_SCENE_NGRAM_ORDER:
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
    "偷藏抢争系叠刷洗吃喝看切分收开关拿拖浇穿脱端擦摆玩躲装翻摸掏塞摘扯踢吹按"
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
    - 感叹号只在没有问号时 +1，避免「？！ 」双标点叠加刷分；
    - 命中结局动词（全滚/滚出来/掉一地/被抓住…）→ 扣分，事件播报不如有口吻的候选；
    - 逗号不给分：避免「妈，月饼全滚出来了」这类「称呼+平铺直叙」压过真正有口吻的候选。
    """
    score = 0
    if "？" in title or "?" in title:
        score += 3
    elif "！" in title or "!" in title:
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


def _story_type_word_hit(title: str, story_type: str | None) -> tuple[bool, bool, bool, bool]:
    """类型词命中：返回 (信息锚词, 孩子话风格词, 黑名单, 弱孩子话词)。未知类型都返回不命中。"""
    words = _STORY_TYPE_OUTCOME_WORDS.get((story_type or "").strip().upper())
    if not words:
        return False, False, False, False
    core = title_core(title)
    info_hit = any(w in core for w in words.get("info", ()))
    style_hit = any(w in core for w in words.get("style", ()))
    block_hit = any(w in core for w in words.get("block", ()))
    weak_hit = any(w in core for w in words.get("weak", ()))
    return info_hit, style_hit, block_hit, weak_hit


def _story_type_inversion_hit(title: str, story_type: str | None) -> bool:
    """书面倒装模式命中（如 C 类「反被挑走大块」「被大块走」）→ 拒收。"""
    patterns = _TITLE_INVERSION_PATTERNS.get((story_type or "").strip().upper(), ())
    if not patterns:
        return False
    core = title_core(title)
    return any(p in core for p in patterns)


def _story_type_grammar_bad_hit(title: str, story_type: str | None) -> bool:
    """压缩过度/语序错乱的常见语病模式命中（如「赖皮大的归你」）→ 拒收。"""
    patterns = _TITLE_GRAMMAR_BAD_RE.get((story_type or "").strip().upper(), ())
    if not patterns:
        return False
    core = title_core(title)
    return any(p.search(core) for p in patterns)


def pick_best_chat_title(draft: str, candidates: list[str], *, max_len: int, avoid_titles: list[str] | None=None, anchor_words: list[str] | None=None, story_type: str | None=None) -> str:
    """从多个候选中选最终标题：退化保护 + 长度硬截断 + 钩子分排序。

    - 命中初稿或 avoid_titles（已用过的标题）的候选降权，避免手动重跑输出同一个；
    - 问号/叹号/称呼开头/甩锅质问优先于平铺直叙的事件复述；
    - anchor_words：本场核心名词（如「月饼」）。含核心名词的候选 +2（贴主题），
      不含的候选直接作废、不参与选择；全部候选都不含核心词时回退初稿，绝不写跑题标题；
    - story_type：命中信息锚词（C 类「先挑/大块/白忙/咋还输」等）→ +2，孩子话风格词
      （说好/凭啥/明明）→ +1，弱孩子话词（呀/呗）在有信息锚词时 +1；
      黑名单书面词、书面倒装、缺信息锚词 → 直接拒收该候选；
    - 平局不再无条件保第一个候选：按 类型钩子 > 问句 > 感叹句 > 更短 的优先级排序；
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
    best_tie = (-1, -1, -1, -1)  # 初稿平局永不替换
    any_anchored = False
    for cand in candidates:
        chosen = select_optimized_title(draft, cand, max_len=max_len)
        info_hit, style_hit, block_hit, weak_hit = _story_type_word_hit(chosen, story_type)
        if (
            block_hit
            or _story_type_inversion_hit(chosen, story_type)
            or _story_type_grammar_bad_hit(chosen, story_type)
        ):
            continue
        type_key = (story_type or "").strip().upper()
        type_words = _STORY_TYPE_OUTCOME_WORDS.get(type_key)
        if type_words and type_words.get("info") and not info_hit:
            continue
        score = _chat_title_hook_score(chosen)
        if info_hit:
            score += 2
        if style_hit:
            score += 1
        if weak_hit and info_hit:
            score += 1
        anchored = _candidate_has_anchor(chosen, anchors)
        if not anchored:
            # 候选层硬校验：缺主题短语/核心名词的候选直接作废，不参与选择
            continue
        any_anchored = True
        # 显式给了核心名词才加分：贴主题的候选该比 hook 同分的局部画面候选优
        if anchors:
            score += 2
        # 主题短语句尾倒装（如「先挑咋还输了，分蛋糕」）削弱主题锚定，轻微扣分
        if anchored and phrases:
            core = title_core(chosen)
            if any(p and core.endswith(p) for p in phrases):
                score -= 2
        if title_core(chosen) == draft_core or title_core(chosen) in avoid_cores:
            score -= 8
        has_question = "？" in chosen or "?" in chosen
        has_exclamation = "！" in chosen or "!" in chosen
        cand_tie = (
            1 if (info_hit or style_hit) else 0,
            1 if has_question else 0,
            1 if has_exclamation else 0,
            -len(chosen),
        )
        if score > best_score or (score == best_score and best is not draft and cand_tie > best_tie):
            best_score = score
            best_tie = cand_tie
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

# 类型结局词绑定：info=信息锚词（必须命中）/style=孩子话风格词（加分）/weak=弱孩子话词
# （仅辅助）/block=书面词或类型错配词（直接拒收）。
# 目前先按 C 类公平执念校准；其余类型保持通用规则，待批量结果后再补充。
_STORY_TYPE_OUTCOME_WORDS: dict[str, dict[str, tuple[str, ...]]] = {
    "C": {
        "info": ("先挑", "大块", "白忙", "咋还输", "亏", "赖皮"),
        "style": ("说好", "凭啥", "明明"),
        "weak": ("呀", "呗"),
        "block": (
            "露馅", "散伙", "结盟", "反水", "穿帮", "抓包", "站队", "内讧", "甩锅",
            "按字面", "立规", "规则", "大小不均", "分配", "约定", "按理说",
            "公平", "字面", "破功",
        ),
    },
}

# 书面倒装模式：C 类命中即拒收（要求改写成「大块被挑走/大块没了」这类自然语序）
_TITLE_INVERSION_PATTERNS: dict[str, tuple[str, ...]] = {
    "C": ("反被挑走大块", "反被挑大块", "反被大块", "被大块走", "被挑大块"),
}

# 压缩过度/语序错乱的常见语病模式：命中即拒收（语病审核模型可能漏判，规则兜底）
_TITLE_GRAMMAR_BAD_RE: dict[str, tuple[re.Pattern[str], ...]] = {
    "C": (
        re.compile(r"赖皮大"),
        re.compile(r"白忙选"),
        re.compile(r"说好先挑(?!我)"),
        re.compile(r"凭啥先挑"),
        re.compile(r"让大块(?!给|出|了)"),
        re.compile(r"分蛋糕明明(?!我)先挑"),
        re.compile(r"分蛋糕先挑，?大块"),
    ),
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
        "B类是「俩孩子约好干坏事→搞砸→被抓」"
        "\n- 极简、干净、像孩子脱口而出的一句话，7–10 字，不堆画面"
        "\n【三种形态，三个候选各套一种】用 XX 代表本集故事主题（完整动作短语，严禁缩减）："
        "\n①形态一：XX+结局词（翻车记 / 散伙了 / 搞砸了 / 被抓包 / 没看成）"
        "\n②形态二：XX+孩子感叹（咋全露馅 / 咋变这样 / 还没看就被抓 / 白忙一场）"
        "\n③形态三：状态词+XX（手忙脚乱 / 慌慌张张 / 偷偷摸摸）"
        "（XX 是占位示范，不要照抄成品短句，只套结构）"
        "\n【逐候选生成规则（核心，硬性）】"
        "按顺序生成三个候选，每生成一个，立即从后续候选中排除已用的词："
        "\n- 先生成候选1（任意形态），选定一个结局词或状态词"
        "\n- 再生成候选2（剩余形态中选），结局词/状态词必须与候选1不同"
        "\n- 最后生成候选3（最后一种形态），结局词/状态词必须与候选1、候选2都不同"
        "三个候选的结局词/状态词**严禁重复**，也严禁用同义词替换来变相重复"
        "（如「散伙了」和「散伙啦」算同一个词）。"
        "生成完毕后自查：若三个候选中出现相同结局词/状态词，则整组作废重写。"
        "\n【标题生成规则】"
        f"\n- 硬性：标题必须 ≤{max_title_len} 字"
        "\n- 主题锚定（最高优先，硬性）：标题必须能看出本集故事主题，"
        "且包含该主题的完整动作+核心名词，写漏字变歧义就作废"
        "\n- 孩子气硬规则：标题写成「孩子当场脱口而出的话」，不是大人复述剧情；"
        "优先用咋/凭啥/说好/明明/白忙/亏/赖皮，呀/呗只能辅助，不能单独算孩子气；"
        "\n- 禁止书面词：按字面/立规/规则/分配/约定/按理说/公平/字面/破功，"
        "以及瞒着/赔上/搭上/满屋/一番/之际/挨罚/受罚；"
        "\n- 禁止书面倒装：不说「反被挑走大块」「被大块走」，要说「大块被挑走」「大块没了」；"
        "\n- 不能有语病：标题必须通顺，不能缺字、缺动词、语序倒错（如「先挑反被大块走」不合格）；"
        "\n- 语病自检（硬性）：写完每个候选读一遍，主谓宾要完整、语序要自然；"
        "缺主语（如「分蛋糕说好先挑」缺「我」）、主题短语被拆散（如「说好分蛋糕先挑」）都算语病；"
        "好例「分蛋糕说好我先挑，大的没了」，坏例「分蛋糕说好先挑，咋大块被挑走」；"
        "\n- 封面感硬规则：标题要像短视频封面，短促有力，不是完整口语长句；"
        "可省略主语/连接词，用问号/感叹号/短语节奏制造钩子；"
        "好例「大块归你？分蛋糕我先挑，赖皮」「先挑大的，分蛋糕亏的是我？」"
        "「分蛋糕大的哪去了？说好我先挑」；"
        "坏例「分蛋糕说好我先挑，咋大块被挑走」「分蛋糕我先挑大的，凭啥说亏」；"
        "\n- 好例：「分蛋糕说好我先挑，咋大块被挑走了」「说好我先挑大的，凭啥还亏了」"
        "「明明先挑，咋白忙了」；"
        "\n- 坏例：「分蛋糕按字面挑，白忙」「分蛋糕立规先挑反被挑大块」「先挑反被大块走」"
        "\n- 不用描述性事件名（如「抢饼干」「姐弟吵架」）"
        "\n- 禁止书面类型术语：不要出现「结盟/同盟/权威/公平/字面/破功」"
        "\n- 禁止为了短删掉钩子：超字只删虚词/语气词，保住钩子词"
        "\n- 点结局但别报流水账：可以说「翻车了/散伙了/搞砸了」，"
        "别罗列过程细节（如「线缠脚，电视黑，水杯翻」）"
        "\n- 推锅必须基于剧本真实意外：剧本写明是孩子碰翻的（手扶茶几盒子翻了），"
        "就绝不能写「月饼是它自己翻的/滚的」；剧本写「线缠住脚」才能写「是线自己缠的」"
        "\n- 称呼要符合剧本：只准用剧本里孩子原话出现过的称呼，且只在孩子真的"
        "对被瞒对象/在场角色说话时才用；瞒着妈妈藏/偷的戏（妈妈在厨房、孩子藏玩具），"
        "孩子不会开口叫妈妈，标题就绝不能开场写「妈妈，…」或「妈，…」来点破"
        "\n- 钩子要落在具体好笑画面：把一个道具+动作（「擦」「踩」「摔」「翻」）放进标题，"
        "让读者能脑补画面，别写泛泛的结果"
        "\n- 禁止用「谁…」「…怨谁」质问句"
        "\n- 钩子只准来自剧本实际内容：禁止编造剧本里没有的细节、道具、意外原因或量词"
        "（如剧本「满地水」绝不能写「满屋水」）"
        "\n- 坏标题示例（书面/大人/复述/词重复，差）：「姐弟偷吃饼干」「月饼全滚出来了」"
        "「偷看电视露馅了」「谁干的」「偷电视被抓包」"
        "「三个全是翻车记」「三个全是散伙了」"
        'JSON 输出样例：{"titles": ["候选1", "候选2", "候选3"]}。'
        "三个候选口吻必须不同，最有钩子的放第一个。"
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

    type_key = str(story_content.get("story_type") or "").strip().upper()
    type_words = _STORY_TYPE_OUTCOME_WORDS.get(type_key)
    type_note = ""
    if type_words:
        info = "、".join(type_words.get("info", ()))
        style = "、".join(type_words.get("style", ()))
        weak = "、".join(type_words.get("weak", ()))
        block = "、".join(type_words.get("block", ()))
        type_note = (
            "\n【本次类型硬规则：C 类公平执念·孩子话（优先级高于上面的通用候选1结局词列表）】"
            f"\n- 必须至少命中一个信息锚词：{info}；"
            f"\n- 孩子话风格词（加分，可选）：{style}；弱孩子话词（仅辅助）：{weak}；"
            f"\n- 禁止书面词：{block}；"
            "\n- 禁止书面倒装：不说「反被挑走大块」「被大块走」，要说「大块被挑走」「大块没了」；"
            "\n- 不能有语病：必须通顺，不能缺字、缺动词、语序倒错；"
            "\n- 泛化词（翻车记/翻车了/搞砸了/变这样）每 3 个候选最多 1 个，且不得作为候选1；"
            "\n- 同一组 3 个候选中，同一句式结构最多出现 1 次，至少覆盖 2 种不同钩子；"
            "\n- 好例：「分蛋糕说好我先挑，咋大块被挑走了」「说好我先挑大的，凭啥还亏了」"
            "「明明先挑，咋白忙了」；"
            "\n- 坏例：「分蛋糕按字面挑，白忙」「分蛋糕立规先挑反被挑大块」"
            "「先挑反被大块走」。"
        )

    anchors = extract_core_anchor_words(draft_title, story_content)
    theme_phrase = extract_theme_action_phrase(draft_title, story_content)
    anchor_note = ""
    if theme_phrase:
        anchor_note = (
            f"\n【硬性】标题必须原样保留本集主题短语「{theme_phrase}」"
            f"（如「{theme_phrase}」不能缩成「{theme_phrase[-2:]}」或只留核心名词）。"
            "不含完整主题短语的标题不合格，作废重写。"
            f"\n每个候选（候选1/2/3）都必须完整包含「{theme_phrase}」，候选1也不允许省略；"
            "主题短语放在句首或中段，禁止放在句尾倒装（如「先挑咋还输了，分蛋糕」不合格）。"
        )
    elif anchors:
        anchor_note = f"\n【硬性】标题必须包含本场核心名词：{'、'.join(anchors)}。不含核心名词的标题不合格，作废重写。"

    return (
        f"初稿标题：{draft_title}\n"
        f"剧本内容：\n{context}\n\n"
        "第一步，先看清本集的「主题 + 类型结局」：本集主题短语是"
        f"「{theme_phrase or draft_title}」，"
        "类型结局要用**孩子话**表达。"
        "（这行写在 JSON 外面，不要进 JSON。）"
        "第二步，写 3 个候选 title（同一 JSON 数组，最有钩子的放第一个），"
        "**按逐候选生成规则各套一种形态**（XX=本集主题短语，别照抄别的故事）："
        "候选1先选一个结局词/状态词（翻车记/散伙了/搞砸了/被抓包/没看成/咋全露馅/咋变这样/"
        "还没看就被抓/白忙一场/手忙脚乱/慌慌张张/偷偷摸摸 任选）；"
        "候选2换一种形态，词必须与候选1不同；"
        "候选3再用最后一种形态，词必须与前两个都不同。"
        "三个结局词/状态词**严禁重复**（含同义词变体，如「散伙了/散伙啦」算同词）。"
        "同一组 3 个候选中，同一句式结构也最多出现 1 次（如「按字面…白忙一场」与"
        "「按字面…大块被挑走」算同构），禁止三个候选都套同一个句式。"
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
        "但「翻车/散伙/搞砸/没看成/被抓包/露馅」这类通用孩子话结局词默认允许；"
        "若下方有「本次类型硬规则」，以硬规则为准（黑名单词禁用）。"
        f"{anchor_note}"
        f"{type_note}"
        "孩子气硬规则：标题写成「孩子当场脱口而出的话」，不是大人复述剧情；不能有语病。"
        "语病自检：主谓宾要完整、语序要自然；缺主语（如「分蛋糕说好先挑」缺「我」）和主题短语被拆散"
        "（如「说好分蛋糕先挑」）都算语病，必须改成「分蛋糕说好我先挑」这类通顺写法。"
        "封面感硬规则：短促、有钩子、像封面标题，不是完整口语长句；可省略主语/连接词，"
        "用问号/感叹号/短语节奏制造钩子；好例「大块归你？分蛋糕我先挑，赖皮」"
        "「先挑大的，分蛋糕亏的是我？」；坏例「分蛋糕说好我先挑，咋大块被挑走」。"
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
