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


def _dialogue_blob(story_content: dict | None) -> str:
    """对白 speaker + 台词，用于判断标题人物是否真出场。"""
    if not story_content:
        return ""
    lines = story_content.get("dialogue") or []
    parts: list[str] = []
    for item in lines:
        if isinstance(item, dict):
            parts.append(str(item.get("speaker") or ""))
            parts.append(str(item.get("line") or item.get("text") or ""))
        else:
            parts.append(str(item))
    return "".join(parts)


def _dialogue_speakers(story_content: dict | None) -> list[str]:
    if not story_content:
        return []
    seen: list[str] = []
    for item in story_content.get("dialogue") or []:
        if not isinstance(item, dict):
            continue
        speaker = str(item.get("speaker") or "").strip()
        if speaker and speaker not in seen:
            seen.append(speaker)
    return seen


# 标题里的家庭角色：对白没出场则禁止写进标题。
# 裸「妈」排除 干嘛/奶妈/干妈/后妈/妈妈（妈妈由更长词覆盖）。
_TITLE_CAST_ROLES: tuple[tuple[str, tuple[str, ...], re.Pattern[str]], ...] = (
    ("妈妈", ("妈妈", "妈"), re.compile(r"妈妈|(?<![奶干后阿])妈(?!妈)")),
    ("爸爸", ("爸爸", "爸", "老爸"), re.compile(r"爸爸|老爸|(?<![爷老])爸(?!爸)")),
    ("奶奶", ("奶奶",), re.compile(r"奶奶")),
    ("爷爷", ("爷爷",), re.compile(r"爷爷")),
    ("外婆", ("外婆", "姥姥"), re.compile(r"外婆|姥姥")),
    ("外公", ("外公", "姥爷"), re.compile(r"外公|姥爷")),
)


def title_absent_roles(title: str, story_content: dict | None = None) -> tuple[str, ...]:
    """标题点名了、但对白（含 speaker）未出现的家庭角色。无对白时不判。"""
    text = str(title or "")
    blob = _dialogue_blob(story_content)
    if not text or not blob:
        return ()
    absent: list[str] = []
    for label, variants, pattern in _TITLE_CAST_ROLES:
        if not pattern.search(text):
            continue
        if any(variant in blob for variant in variants):
            continue
        absent.append(label)
    return tuple(absent)


# 站内人物关系只有「姐弟」一种（灿灿=10 岁姐姐、昭昭=7 岁弟弟；昭昭称灿灿「姐姐」，
# 灿灿称昭昭「弟弟」）。下列都是源视频侧的关系标签/错关系词，剧本正文里没出现过
# 却写进标题 = 抄了源稿标签，一律拒收；不含「姐姐/弟弟」（站内合法互称）。
_TITLE_SOURCE_LABELS = ("双胞胎", "龙凤胎", "妹妹", "哥哥", "兄妹", "兄弟", "姐妹")

# 标题里的拉丁字母：剧本任何字段都没出现过 → 判脏字符（手改初稿/模型带进，如 'j'）。
_LATIN_LETTER_RE = re.compile(r"[A-Za-z]")


def _story_script_blob(story_content: dict | None) -> str:
    """剧本正文（**不含** scene_title/theme）：判断词是否真在稿子里出现过。

    场景标题/主题可能直接抄源视频标题（带「双胞胎/妹妹」这类源稿标签），
    拿它自证会把标签洗白，所以只认稿子本身；punchline_explain 是源稿侧的
    「反差说明」（同样可能带源稿标签），也不计入。
    """
    if not story_content:
        return ""
    parts = [
        str(story_content.get(key) or "")
        for key in ("setting", "conflict_core", "key")
    ]
    parts.append(_dialogue_blob(story_content))
    return "".join(parts)


def _story_full_blob(story_content: dict | None) -> str:
    """剧本全部文本（含 scene_title/theme）：脏字符宽松判定用，避免误杀合法字母。"""
    if not story_content:
        return ""
    parts = [
        str(story_content.get(key) or "")
        for key in (
            "scene_title",
            "theme",
            "setting",
            "conflict_core",
            "key",
            "punchline_explain",
        )
    ]
    parts.append(_dialogue_blob(story_content))
    return "".join(parts)


def title_source_label_leak(title: str, story_content: dict | None = None) -> tuple[str, ...]:
    """标题里的源视频标签（双胞胎/妹妹/哥哥）在剧本正文里找不到 → 漏标。无剧本时不判。"""
    text = str(title or "")
    blob = _story_script_blob(story_content)
    if not text or not blob:
        return ()
    return tuple(label for label in _TITLE_SOURCE_LABELS if label in text and label not in blob)


def title_has_unattested_latin(title: str, story_content: dict | None = None) -> bool:
    """标题里的拉丁字母在剧本里找不到出处 → 判脏。无剧本时不判。"""
    text = str(title or "")
    blob = _story_full_blob(story_content)
    if not text or not blob:
        return False
    letters = set(_LATIN_LETTER_RE.findall(text.lower()))
    if not letters:
        return False
    return not letters <= set(_LATIN_LETTER_RE.findall(blob.lower()))


def title_unusable(title: str, story_content: dict | None = None) -> bool:
    """标题不可用：源稿标签漏标，或含剧本里没有的拉丁字母（如手输 'j'）。"""
    return bool(title_source_label_leak(title, story_content)) or title_has_unattested_latin(
        title, story_content
    )


def _dialogue_cast_mismatch_note(draft_title: str, story_content: dict) -> str:
    """源标题/主题写了但对白没有的人物 → 提示词硬卡。"""
    meta = "".join(
        str(story_content.get(key) or "")
        for key in ("scene_title", "theme", "conflict_core", "key")
    )
    absent = title_absent_roles(f"{draft_title}{meta}", story_content)
    if not absent:
        return ""
    speakers = _dialogue_speakers(story_content)
    who = "、".join(speakers) if speakers else "（对白角色）"
    bad = "、".join(absent)
    return (
        f"\n【硬性·对白人物】对白出场：{who}。未出现：{bad}。"
        f"初稿/主题/冲突核心里的「{bad}」是源视频旧标签，标题禁止出现这些称呼；"
        "必须按对白实际冲突重写，禁止沿用对不上的源标题。"
    )


def filter_chat_title_candidates(
    candidates: list[str],
    *,
    story_content: dict | None = None,
) -> list[str]:
    """候选层硬校验：只留合规候选（人物对得上对白、无源稿标签/脏字符）。

    锚词**不再过滤**候选（2026-10-14 用户裁定）：拿事件短语（「抢娃娃」）当硬门槛
    会把标题逼成事件复述，好钩子（反问/原话/反差）全部被拦。锚词改为 picker 里的
    加分项，见 ``pick_best_chat_title``。
    """
    out = list(candidates)
    if story_content:
        out = [
            c
            for c in out
            if not title_absent_roles(c, story_content) and not title_unusable(c, story_content)
        ]
    return out


def ensure_chat_title_candidates(
    candidates: list[str],
    *,
    fetch_candidates: Callable[[], list[str]],
    max_attempts: int = 3,
    story_content: dict | None = None,
) -> list[str]:
    """候选层硬校验+补足：对白人物对不上的候选作废；不足 3 个时重生成补足。"""
    seen: set[str] = set()
    out: list[str] = []
    for c in filter_chat_title_candidates(
        candidates, story_content=story_content,
    ):
        if c not in seen:
            seen.add(c)
            out.append(c)
    attempts = 0
    while len(out) < 3 and attempts < max_attempts:
        try:
            more = fetch_candidates()
        except Exception:
            break
        for c in filter_chat_title_candidates(
            more, story_content=story_content,
        ):
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
    # 只保护「当前标题里已经有」的主题词：选中标题可能不含主题短语（锚词已降为软加分），
    # 此时若还按初稿强制保留，润色会把短语塞回来、把好钩子重新压平成事件复述
    must_keep = _present_anchor_words(title, draft_title, story_content)
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
    if must_keep:
        keep_line = f"须原样保留（当前标题里已有）：{'、'.join(must_keep)}\n"
        keep_rule = "\n- 上面「须原样保留」的词必须完整保留，且放在句首或中段，禁止放在句尾倒装；"
    else:
        keep_line = "本标题不含主题短语，润色时**不得**把主题短语/事件名塞回来。\n"
        keep_rule = "\n- 禁止新增主题短语/事件名（会变成平铺直叙的事件复述）；"
    user = (
        f"原初稿标题：{draft_title}\n"
        f"当前标题：{title}\n"
        f"{keep_line}"
    )
    if skeleton:
        user += f"类型骨架：{skeleton}\n"
    # 润色按类型分支（2026-10-14 专家评审）：C 类保留「白忙→白忙了」校准；
    # 其余类型禁止加语气词/把问句改陈述/删结构词，免得把口吻标题压平成陈述句
    if _is_c_type(story_content.get("story_type")):
        style_rules = (
            "\n- 缺语气词要补（「白忙」→「白忙了/白忙一场」）；"
        )
    else:
        style_rules = (
            "\n- **禁止新增原标题没有的语气词**（了/吧/呢/啊/呀/嘛）——"
            "只加语气词不算修好语病，反而把标题压成陈述句；"
            "\n- 禁止把问句改写成陈述句；禁止删掉「我/你/自己/不行/总行/凭啥/咋」这类结构词；"
            "\n- 禁止把两个分句合并成一句；"
        )
    user += (
        "【润色要求】"
        "\n- 最小改动：只修语病、读感、节奏；可加逗号、语气词（了/呗/呀），可微调语序；"
        "\n- 禁止删掉原标题里的任何内容字（动词/结局词/钩子词），只能加字、加标点或调整语序；"
        f"{keep_rule}"
        "\n- 保持原有钩子方向和类型结局，不要换成另一个句式/结局词；"
        "\n- 润色后仍须孩子气：若原标题用了咋/凭啥/说好/明明/白忙/亏/赖皮，必须保留；"
        "\n- 不能有语病：必须通顺，不能缺字、缺动词、语序倒错；"
        "\n- 专门修语病：主谓宾要完整、语序要自然；缺主语要补（「说好先挑」→「说好我先挑」），"
        "主题短语被拆散要理顺（「说好分蛋糕先挑」→「分蛋糕说好我先挑」）；"
        f"{style_rules}"
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
# 只给这些字加语气词：C 类「白忙→白忙了/白忙一场」的校准需要，其余类型禁用
_POLISH_PARTICLE_CHARS = frozenset("的了着过吧吗呢啊呀嘛啦呗")


def _polish_keeps_content(source: str, candidate: str) -> bool:
    """润色硬校验：只允许加字/调序/加标点，不允许删原标题的内容字。"""
    src_chars = {
        ch
        for ch in source
        if _CJK_CHAR_RE.match(ch) and ch not in _POLISH_OPTIONAL_CHARS
    }
    cand_chars = set(candidate)
    return src_chars <= cand_chars


def _polish_only_added_particles(source: str, candidate: str) -> bool:
    """润色是否只是在原文外新增了语气词（把标题补成陈述句）。

    「举书砸自己脑袋」→「举书砸自己脑袋了」就是这种压平：新增字符全是语气词，
    没有带来任何信息增量。非 C 类拒收（2026-10-14 专家评审口径）。
    """
    extra = [ch for ch in candidate if ch not in source]
    if not extra:
        return False
    return all(ch in _POLISH_PARTICLE_CHARS for ch in extra)


def _candidate_anchor_pool(draft_title: str, story_content: dict) -> list[str]:
    """本集可参与加分的锚词池（高置信动作/整段短语优先，再补主题短语）。"""
    anchors = extract_hard_anchor_words(draft_title, story_content)
    phrase = extract_theme_action_phrase(draft_title, story_content)
    if phrase and phrase not in anchors:
        anchors = [phrase, *anchors]
    return anchors


def _present_anchor_words(title: str, draft_title: str, story_content: dict) -> list[str]:
    """当前标题里**已经含有**的锚词：润色只保护这些，不再按初稿强行塞回主题短语。"""
    pool = _candidate_anchor_pool(draft_title, story_content)
    return [a for a in pool if _candidate_has_anchor(title, [a])]


def _title_anchor_parts(
    title: str,
    draft_title: str,
    story_content: dict,
) -> tuple[list[str], list[str]]:
    """润色硬校验用的锚词：只算当前标题里已含的高置信锚词，避免把场景词/碎片当「必须保留」。"""
    anchors = _present_anchor_words(title, draft_title, story_content)
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
    if title_absent_roles(candidate, story_content):
        return False
    # 润色不得引入源稿标签（双胞胎/妹妹）或剧本里没有的字符
    if title_unusable(candidate, story_content):
        return False
    # 非 C 类禁止靠加语气词压平（「举书砸自己脑袋」→「…脑袋了」）；C 类保留「白忙→白忙了」校准。
    # 注意：不跟 allow_deletion 绑定——语法修复路径也常靠加「了/吧」收尾，那正是要拦的压平。
    if not _is_c_type(type_key) and _polish_only_added_particles(source, candidate):
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
    # 同润色：只保护当前标题里已有的主题词，不按初稿强行塞回主题短语
    must_keep = _present_anchor_words(title, draft_title, story_content)
    keep_line = (
        f"须完整保留（当前标题里已有）：{'、'.join(must_keep)}\n" if must_keep else ""
    )
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
            f"{keep_line}"
            f"语病审核意见：{reason or '标题不通顺'}\n"
            "【修复要求】"
            "\n- 以修好语病为准：可删错位/多余的字、可调语序、可加字；"
            "但必须保留核心信息（先挑/大块/白忙/亏/赖皮等）；"
            "\n- 补主语、补语气词、理顺语序，修到读起来通顺自然；"
            "\n- 保持短促封面感，不要为了补全句子加长；"
            "\n- 修复示例：「分蛋糕说好我先挑，赖皮大的归你」→「分蛋糕说好我先挑，凭啥大的归你」；"
            "「明明分蛋糕我先挑，白忙选小的」→「明明我先挑分蛋糕，白忙一场选了小的」；"
            "「分蛋糕说好先挑，咋亏了」→「分蛋糕说好我先挑，咋亏了」；"
            "「分蛋糕凭啥先挑大的亏了」→「分蛋糕我先挑大的，凭啥还亏了」；"
            "「分蛋糕说好我先挑，亏我让大块」→「分蛋糕说好我先挑，亏我让出大块」；"
            "「分蛋糕明明先挑，白忙一场」→「分蛋糕明明我先挑，白忙一场」；"
            "「分蛋糕先挑，大块咋归你？」→「分蛋糕我先挑，大块咋归你？」。"
            f"\n- 上面「须完整保留」若列了词，须完整保留且放在句首或中段；{block_note}"
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
    anchors, phrases = _title_anchor_parts(title, draft_title, story_content)
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
# A/B/D/E 封面剧透词（C 类不套：白忙/先挑 是已校准信息锚）
_COVER_SPOILER_RE = re.compile(
    r"歪了|剪歪|翻车|白忙|露馅|被抓包|搞砸|散伙|戳穿|还咋教|咋收场|没藏成"
)
# 口述反问/追问：封面短语不应被这类问句刷掉
_RHETORICAL_RE = re.compile(r"还咋|咋就|咋收场|凭啥|说好")

# 中文核心名词多为 2 字（月饼/电视/玩具/洗澡…）；4 字几乎都是动词+名词拼的整句
_ANCHOR_NGRAM_ORDER = (2, 3, 4)
# 场景标题按标点切短语段；锚词只在段内取，绝不跨段拼
_ANCHOR_CLAUSE_SPLIT_RE = re.compile(r"[\s，,。！？!?；;、…]+")

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


def _clause_anchor_windows(clause: str) -> list[tuple[str, bool]]:
    """一个短语段里可当锚词的窗口：``(窗口, 是否高置信硬锚词)``。

    只取「段边界对齐」的窗口：整段（≤4 字）、或从动作动词一直到段尾（抢娃娃/抢鸡爪/
    争夺战），或段首/段尾 2 字名词。绝不产出从更长的词里切出来的 3–4 字碎片——
    「双胞胎抢娃娃」的「胎抢娃娃」、「奶瓶争夺战」的「瓶争夺战」都是这么来的。

    硬锚词（动作/整段短语，如「抢娃娃」「砸头」）= 可作「标题须含」的硬门槛；
    软锚词（段首/段尾 2 字名词，多为「阳台」这类场景词）= 只加分与提示，不作硬门槛。
    """
    hard: list[str] = []
    soft: list[str] = []
    if 2 <= len(clause) <= 4:
        hard.append(clause)
    for i, ch in enumerate(clause):
        if ch in _THEME_ACTION_VERBS and 2 <= len(clause) - i <= 4:
            hard.append(clause[i:])
        two = clause[i:i + 2]
        if two in _THEME_ACTION_2CHAR and 2 <= len(clause) - i <= 4:
            hard.append(clause[i:])
    if len(clause) >= 2:
        soft.append(clause[:2])
        soft.append(clause[-2:])
    out: list[tuple[str, bool]] = []
    seen: set[str] = set()
    for w, is_hard in ((w, True) for w in hard):
        if len(w) >= 2 and w not in seen:
            seen.add(w)
            out.append((w, is_hard))
    for w in soft:
        if len(w) >= 2 and w not in seen:
            seen.add(w)
            out.append((w, False))
    return out


def _collect_anchor_words(draft: str, story_content: dict) -> list[tuple[str, bool]] | None:
    """``(锚词, 是否硬锚词)`` 列表：段内窗口 → 正文自证 → 关系/源稿标签过滤。

    返回 ``None`` = 锚词不可信（源标题点名了对白没出场的人），调用方**不得**再走
    主题兜底（否则又会把「怼妈」这类源稿标签洗成锚词），直接不锚定。
    """
    raw_scene = str(story_content.get('scene_title') or draft or '').strip()
    scene = title_core(raw_scene)
    if not scene:
        return []
    # 源标题点名了对白没有的人（如金故事「怼妈」映射成姐弟戏）→ 锚词不可信，宁可不锚定
    if title_absent_roles(scene, story_content) or title_absent_roles(draft, story_content):
        return None
    blob = ''.join(str(story_content.get(k) or '') for k in ('conflict_core', 'setting', 'theme'))
    script_blob = _story_script_blob(story_content)
    found: list[tuple[str, bool]] = []
    for clause in (c for c in _ANCHOR_CLAUSE_SPLIT_RE.split(raw_scene) if c):
        for w, is_hard in _clause_anchor_windows(clause):
            if any(w == kept for kept, _ in found):
                continue
            if not (w in blob and _word_boundary_in_blob(w, blob)):
                continue
            if title_absent_roles(w, story_content) or title_source_label_leak(w, story_content):
                continue
            # 段内切出来的窗口必须由剧本正文自证（「抢娃娃」若在正文里只以
            # 「布娃娃」出现，就退回被正文认过的「娃娃」；「看抢拼图」直接作废）
            if w != clause and w not in script_blob:
                continue
            found.append((w, is_hard))
            break
        if len([1 for _, is_hard in found if is_hard]) >= 2:
            break
    return found


def extract_core_anchor_words(draft: str, story_content: dict) -> list[str]:
    """提取本场核心动作/物件词（2–4 字），硬锚词在前：scene_title 与正文共有的词。

    用于提示词「标题须含核心物件/动作」与 picker 兜底，防「鞋底渣印谁擦」式
    盯住次级元素、把核心主题（月饼）丢掉。

    只保留在正文中有独立词位（前/后非汉字）的候选，避免「偷看电」这类把
    「偷看电视」从词边界切开的坏碎片进提示词、被 LLM 照抄成病句标题；
    段内切出来的窗口（动词尾/2 字名词）还要能在**剧本正文**（不含 scene_title/
    theme）里找到出处，否则可能是「胎抢娃娃」这种跨词碎片，宁可不锚定。

    scene_title 提不到（太短/只出现在词内）时，用主题（theme）兜底提取核心名词，
    让标题仍能锚定主题；两者都取不到时返回空列表 = 不强制。
    """
    found = _collect_anchor_words(draft, story_content)
    if found is None:
        return []
    if not found:
        fallback = _extract_theme_fallback(str(story_content.get('theme') or ''), story_content)
        return [w for w in fallback if not title_absent_roles(w, story_content)]
    hard = [w for w, is_hard in found if is_hard][:2]
    soft = [w for w, is_hard in found if not is_hard]
    return (hard + soft)[:2]


def extract_hard_anchor_words(draft: str, story_content: dict) -> list[str]:
    """高置信硬锚词（动作/整段短语）：只有它们才配作「标题须含」的硬门槛。

    段首/段尾 2 字名词（如「阳台」这类场景词）不出现在这里——作硬门槛会误拦
    合规候选，只该加分与提示（见 ``_clause_anchor_windows``）。
    """
    found = _collect_anchor_words(draft, story_content)
    if not found:
        return []
    return [w for w, is_hard in found if is_hard][:2]


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
    从 theme / conflict_core / scene_title 里找「动作动词+紧邻核心名词」组合，
    且组合结果必须在正文里有独立词位（否则是「回看抢拼图」→「看抢拼图」这种
    切头碎片）；找不到就退回核心名词本身。
    """
    anchor = extract_core_anchor_words(draft, story_content)
    if not anchor:
        return ""
    noun = anchor[0]
    script_blob = _story_script_blob(story_content)

    def _composed_ok(phrase: str) -> bool:
        """组合短语也必须由剧本正文认下：防「回看抢拼图」→「看抢拼图」这种切头碎片。"""
        if title_absent_roles(phrase, story_content):
            return False
        if phrase not in script_blob:
            return False
        return _word_boundary_in_blob(phrase, script_blob)

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
                phrase = two + noun  # 偷看+电视 → 偷看电视；偷吃+月饼 → 偷吃月饼
                if _composed_ok(phrase):
                    return phrase
            prev = src[i - 1]
            if prev in _THEME_ACTION_VERBS:
                phrase = prev + noun  # 藏+玩具 → 藏玩具
                if _composed_ok(phrase):
                    return phrase
    if title_absent_roles(noun, story_content):
        return ""
    return noun


# ---------- 钩子形态判据（2026-10-14 专家评审口径，功能词类别，不给单篇词表） ----------
# 分句切分：逗号/问号/叹号/顿号都算边界（对照结构靠它拆两半）
_TITLE_CLAUSE_SPLIT_RE = re.compile(r"[\s，,。！？!?；;、…]+")
_FIRST_PERSON_RE = re.compile(r"[我俺咱]")
_SECOND_PERSON_RE = re.compile(r"[你您]")
# 否定：不行/不能/别/没/不（对照结构的前半边）
_NEGATION_RE = re.compile(r"不行|不能|不可以|别|没|不|亏|白忙")
# 肯定/许可：总行/可以/偏/就/才/归/算（对照结构的后半边）
_AFFIRMATION_RE = re.compile(r"总行|可以|偏|就|才|归|算|行")
# 反问词：咋/怎么/凭什么/为啥/难道/吗/呢
_RHETORICAL_WORD_RE = re.compile(r"咋|怎么|凭什么|为啥|难道|吗|呢")
# 反转连接：却/倒/偏/结果/没想到/反而/越…越
_REVERSAL_LINK_RE = re.compile(r"却|倒|偏|结果|没想到|反而|居然|竟然")
# 条件-承诺：就/才/总/也/还/就……总
_CONDITION_PROMISE_RE = re.compile(r"就|才|总|也|还")
# 立场/口吻功能词：条件、否定、许可、语气（原话型靠它识别）
_STANCE_WORD_RE = re.compile(r"不算|总行|凭啥|明明|说好|偏要|就不|就是不|归我|归你|行吧|呗|嘛")
# 金句立规矩：才算/才叫/才是
_RULE_SLOGAN_RE = re.compile(r"才算|才叫|才是")
# 编辑式旁白（属反转叙述，非纯画面复述）
_EDITORIAL_RE = re.compile(r"更|反而|居然|竟然")


def _is_c_type(story_type: str | None) -> bool:
    return str(story_type or "").strip().upper() == "C"


def _is_visual_cover_phrase(title: str) -> bool:
    """是否像封面画面/物件短语（剪刀下的直线），而不是口述复述或反问。"""
    text = str(title or "").strip()
    if not text:
        return False
    if "？" in text or "?" in text:
        return False
    if _COVER_SPOILER_RE.search(text) or _SPOILER_RE.search(text) or _OUTCOME_REVEAL_RE.search(text):
        return False
    if _RHETORICAL_RE.search(text):
        return False
    if text[:1] in "妈姐爸哥弟" and ("，" in text or "," in text):
        return False
    if "不是我" in text or "怪我" in text:
        return False
    return True


def maybe_keep_cover_draft(
    draft: str,
    story_content: dict,
    *,
    max_len: int,
    avoid_titles: list[str] | None = None,
) -> str | None:
    """初稿已是好封面标题则直接保留，返回初稿；否则 None 表示继续优化。

    C 类不走这条（仍用先挑/白忙硬卡）。手动重跑把当前标题放进 avoid 时也不保，
    允许换角度。
    """
    text = str(draft or "").strip()
    if not text:
        return None
    if _is_c_type((story_content or {}).get("story_type")):
        return None
    avoid_cores = {title_core(t) for t in (avoid_titles or []) if str(t).strip()}
    if title_core(text) in avoid_cores:
        return None
    if len(text) > max_len:
        return None
    if not _is_visual_cover_phrase(text):
        return None
    if title_absent_roles(text, story_content):
        return None
    # 源稿标签（双胞胎/妹妹）与剧本里没有的脏字符（手改初稿的 'j'）不进初稿保留
    if title_unusable(text, story_content):
        return None
    return text


def _chat_title_hook_score(title: str, *, story_type: str | None = None) -> int:
    """钩子分：多候选相对排序（不拦截单结果）。

    2026-10-14 专家评审后重排：**口吻/反差/原话压过画面复述**。
    旧表只给画面物件 +4，口吻/反差/原话三类完全没有正分，导致好钩子与画面句同分、
    平局按「更短优先」输给画面句（#117 实测）。新表：

    - 形态基分：口吻/原话 +5、对照/反差 +5、结果反转 +4、反问 +3、金句 +3、
      画面 +2、动作任务 +2（画面由 +4 降权）；
    - 结构分：第一人称 +2、第二人称 +1、否定+肯定双分句 +2、反转连接 +2、
      反问词 +2、问号 +1、条件-承诺 +1；
    - 立场分：含「自己」+1、称呼开头 +1、甩锅声明 +1（均较旧表降权）；
    - 简短分：≤10 字 +1、≤7 字 +2；
    - 扣分：封面剧透 -5（C 类不过该表：「白忙」是 C 类必需信息锚词）、含「谁」-3
      （且不触发反问加分）、≥2 逗号 -3、纯事件复述 -2、锚词硬塞 -1（锚词由调用方传入，
      见 picker）。
    """
    text = str(title or "").strip()
    if not text:
        return 0
    core = title_core(text)
    has_q = "？" in text or "?" in text
    has_excl = "！" in text or "!" in text

    # ---- 形态基分 ----
    score = _title_form_base_score(text)

    # ---- 结构分 ----
    if _FIRST_PERSON_RE.search(core):
        score += 2
    if _SECOND_PERSON_RE.search(core):
        score += 1
    if _is_contrast_title(text):
        score += 2  # 否定分句 + 肯定分句双分句
    if _REVERSAL_LINK_RE.search(core):
        score += 2
    if _RHETORICAL_WORD_RE.search(core):
        score += 2
    if has_q:
        score += 1
    if _CONDITION_PROMISE_RE.search(core):
        score += 1

    # ---- 立场分 ----
    if "不是我" in text or "怪我" in text:
        score += 1
    if "自己" in text:
        score += 1
    if text[:1] in "妈姐爸哥弟":
        score += 1

    # ---- 简短分（封面大字：短促有力）----
    length = len(core)
    if length <= 7:
        score += 2
    elif length <= 10:
        score += 1

    # ---- 扣分 ----
    # 「谁…」质问句历史上刷过屏（谁擦的渣/渣印谁擦/谁踩的渣印）：扣分且不给反问加分
    if "谁" in text:
        score -= 3
    # 封面剧透词 / 结局播报。注意 C 类不过 _COVER_SPOILER_RE：该表含「白忙」，
    # 而「白忙」是 C 类的必需信息锚词（硬卡要求含它），不能反过来扣分。
    if _SPOILER_RE.search(text) or _OUTCOME_REVEAL_RE.search(text):
        score -= 5
    elif not _is_c_type(story_type) and _COVER_SPOILER_RE.search(text):
        score -= 5
    # 平铺罗列：≥2 逗号 = 逐项列事件，像事故清单
    if text.count("，") + text.count(",") >= 2:
        score -= 3
    # 纯事件复述：只有画面/动作形态、没有任何口吻/反差/反问/反转结构
    if _is_plain_event_restatement(text):
        score -= 2
    if has_excl and not _is_c_type(story_type):
        score += 1  # 感叹句仍给一点，但救不回上面的大扣分
    return score


def _title_form_base_score(title: str) -> int:
    """形态基分：先判形态再给分（口吻/反差 > 反转/反问/金句 > 画面/动作）。"""
    text = str(title or "").strip()
    if not text:
        return 0
    if _is_contrast_title(text):
        return 5
    if _is_original_speech_title(text):
        return 5
    if _is_reversal_title(text):
        return 4
    if _is_rhetorical_title(text):
        return 3
    if _RULE_SLOGAN_RE.search(title_core(text)):
        return 3
    if _is_visual_cover_phrase(text):
        return 2
    return 2  # 动作任务型等其余形态：与画面同档


def _is_rhetorical_title(title: str) -> bool:
    """反问/质问型：有问号或反问词，且不含「谁」（谁字问句单独扣分、不给形态分）。"""
    text = str(title or "").strip()
    if not text or "谁" in text:
        return False
    if "？" in text or "?" in text:
        return True
    return bool(_RHETORICAL_WORD_RE.search(title_core(text)))


def _is_original_speech_title(title: str) -> bool:
    """口吻/原话型：第一/二人称 + 立场/条件/否定/许可等功能词，且非纯第三人称复述。"""
    core = title_core(title)
    if not core or "谁" in title:
        return False
    if not (_FIRST_PERSON_RE.search(core) or _SECOND_PERSON_RE.search(core)):
        return False
    if "？" in title or "?" in title:
        return False  # 问句归反问型
    return bool(
        _STANCE_WORD_RE.search(core)
        or _CONDITION_PROMISE_RE.search(core)
        or _REVERSAL_LINK_RE.search(core)
    )


def _is_contrast_title(title: str) -> bool:
    """对照/反差型：分句 ≥2，一句否定、一句肯定/许可，且两分句有共同实体。"""
    text = str(title or "").strip()
    if not text:
        return False
    clauses = [c for c in _TITLE_CLAUSE_SPLIT_RE.split(text) if c]
    if len(clauses) < 2:
        return False
    neg = [c for c in clauses if _NEGATION_RE.search(c)]
    pos = [c for c in clauses if _AFFIRMATION_RE.search(c)]
    if not neg or not pos:
        return False
    neg_text = "".join(neg)
    pos_text = "".join(pos)
    shared = {ch for ch in neg_text if _CJK_CHAR_RE.match(ch)} & {
        ch for ch in pos_text if _CJK_CHAR_RE.match(ch)
    }
    return len(shared) >= 1


def _is_reversal_title(title: str) -> bool:
    """结果反转型：带反转连接词（结果/反而/没想到/却/倒/偏），或短句对撞（越 X 越 Y）。"""
    core = title_core(title)
    if not core:
        return False
    if _REVERSAL_LINK_RE.search(core):
        return True
    return bool(re.search(r"越.{0,4}越", core)) or bool(_EDITORIAL_RE.search(core))


def _is_plain_event_restatement(title: str) -> bool:
    """纯事件复述：画面/动作型语言，但没有任何口吻/反差/反问/反转结构。"""
    text = str(title or "").strip()
    if not text:
        return False
    if "？" in text or "?" in text:
        return False
    if _is_contrast_title(text) or _is_reversal_title(text):
        return False
    core = title_core(text)
    if _FIRST_PERSON_RE.search(core) or _SECOND_PERSON_RE.search(core):
        return False
    return bool(_STANCE_WORD_RE.search(core)) is False


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


def pick_best_chat_title(draft: str, candidates: list[str], *, max_len: int, avoid_titles: list[str] | None=None, anchor_words: list[str] | None=None, soft_anchor_words: list[str] | None=None, story_type: str | None=None, story_content: dict | None=None) -> str:
    """从多个候选中选最终标题：退化保护 + 长度硬截断 + 钩子分排序。

    - 命中初稿或 avoid_titles（已用过的标题）的候选降权，避免手动重跑输出同一个；
    - C 类：问号/叹号/称呼开头/甩锅质问优先于平铺直叙的事件复述；
    - A/B/D/E：画面物件短语优先，口述反问与封面剧透词降权；
    - anchor_words / soft_anchor_words：**只加分，不作门槛**（2026-10-14 用户裁定）。
      命中任一锚词 +2，一次封顶。曾经「不含锚词直接作废 + 全废回退初稿」的硬门槛已删除：
      锚词多来自事件短语（如「抢娃娃」），作硬门槛等于强制标题复述事件，
      好钩子（反问/原话/反差，如「砸姐姐不行，砸自己总行」）会被整体拦掉；
      跑题风险改由「类型信息锚词硬卡 + 初稿严格更高分才替换」兜；
    - story_content：标题点名了对白没有的家庭角色（妈妈/爸爸等）→ 该候选作废；
      初稿自身也对不上对白时，不保护初稿，让对白候选胜出；
      初稿含源稿标签（双胞胎/妹妹）或剧本里没有的脏字符（手输 'j'）时同样不保护；
    - story_type：命中信息锚词（C 类「先挑/大块/白忙/咋还输」等）→ +2，孩子话风格词
      （说好/凭啥/明明）→ +1，弱孩子话词（呀/呗）在有信息锚词时 +1；
      **C 类缺信息锚词 → 直接拒收该候选**（这条是类型硬卡，与锚词无关，保留）；
      黑名单书面词、书面倒装 → 拒收；
    - 平局不再无条件保第一个候选：按 类型钩子 > 问句 > 感叹句 > 更短 的优先级排序；
    - **防御当前标题**：以初稿自身的钩子分为基线，候选必须严格更高才替换。
      否则手动重跑会把「妈，月饼自己滚的」(3分) 换成「偷吃月饼翻车记」(0分)，
      越跑越差、来回跳。
    """
    avoid = [str(t).strip() for t in (avoid_titles or []) if str(t).strip()]
    anchors = [str(a).strip() for a in (anchor_words or []) if str(a).strip()]
    bonus_anchors = [*anchors, *(str(a).strip() for a in (soft_anchor_words or []) if str(a).strip())]
    draft_core = title_core(draft)
    avoid_cores = {title_core(t) for t in avoid}
    # 完整主题短语（≥3 字，如「偷看电视」）必须完整出现；2 字核心名词（电视）按子串即可
    phrases = [a for a in anchors if len(a) >= 3]
    nouns = [a for a in anchors if len(a) < 3]
    draft_mismatch = bool(title_absent_roles(draft, story_content)) or title_unusable(
        draft, story_content
    )
    draft_usable = not draft_mismatch
    best = draft if draft_usable else ""
    best_score = (
        -999 if not draft_usable else _chat_title_hook_score(draft, story_type=story_type)
    )
    best_tie = (-1, -1, -1, -1)  # 初稿平局永不替换
    for cand in candidates:
        chosen = select_optimized_title(draft, cand, max_len=max_len)
        if title_absent_roles(chosen, story_content) or title_unusable(chosen, story_content):
            continue
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
        score = _chat_title_hook_score(chosen, story_type=story_type)
        if info_hit:
            score += 2
        if style_hit:
            score += 1
        if weak_hit and info_hit:
            score += 1
        anchored = _candidate_has_anchor(chosen, anchors)
        # 含锚词加分，**不作门槛**：缺锚词的好钩子候选照样参选（2026-10-14 用户裁定）
        anchored_bonus = _candidate_has_anchor(chosen, bonus_anchors)
        if bonus_anchors and anchored_bonus:
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
        if _is_c_type(story_type):
            cand_tie = (
                1 if (info_hit or style_hit) else 0,
                1 if has_question else 0,
                1 if has_exclamation else 0,
                -len(chosen),
            )
        else:
            cand_tie = (
                1 if _is_visual_cover_phrase(chosen) else 0,
                0 if has_question else 1,
                1 if has_exclamation else 0,
                -len(chosen),
            )
        if score > best_score or (score == best_score and best is not draft and cand_tie > best_tie):
            best_score = score
            best_tie = cand_tie
            best = chosen
    if best:
        return best
    # 初稿不可信、又没有可用候选时退回场景标题：绝不能返回空串把标题写没
    return str((story_content or {}).get("scene_title") or draft).strip() or draft

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


def _build_chat_title_system_prompt_c(*, max_title_len: int) -> str:
    """C 类公平执念：保持先挑/白忙/孩子话校准，不套封面物件标准。"""
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
        "\n- 标题人物必须来自对白：对白没出现的人（妈妈/爸爸等）禁止写进标题；"
        "源标题写了但对白没有，必须按对白重写，禁止沿用怼妈这类对不上的旧标题"
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


def build_chat_title_system_prompt(
    *,
    max_title_len: int = CHAT_TITLE_MAX_LEN,
    story_type: str | None = None,
) -> str:
    """chat 流水线标题：面向孩子与有娃家长。"""
    max_title_len = _clamp_chat_title_len(max_title_len)
    if _is_c_type(story_type):
        return _build_chat_title_system_prompt_c(max_title_len=max_title_len)
    return (
        "你是家庭日常对话短剧的标题编辑，面向孩子和有娃的大人。"
        "根据剧本输出 JSON，字段 titles（3 个候选）。"
        f"title：≤{max_title_len} 字，不含空格换行，适合短封面。"
        "\n【唯一标准：有钩子】标题要让人想点进来，不是复述事件。"
        "钩子可以是孩子原话/口吻、对照反差、反问、结果反转、具体画面——"
        "**口吻与反差优先于画面复述**。"
        "\n【七种形态】"
        "\nF1 画面物件型：<可拍物/身体部位>+<动作/状态>，如「剪刀下的直线」「冰箱最后的果汁」"
        "\nF2 动作任务型：<角色>+<目标动作>+<条件/障碍>，如「教弟弟剪直线」「浇花别浇太多」"
        "\nF3 口吻原话型：第一/二人称 + 立场/条件/威胁/辩解/谈判，"
        "像孩子当场脱口而出，如「就尝一口不算吃」"
        "\nF4 对照反差型：<A>不行，<B>总行 / 以为<A>，其实<B>，用一正一反制造荒诞"
        "\nF5 反问质问型：反问词（咋/凭啥/明明/难道）+ 冲突点 + 问号，"
        "如「剪歪了还咋教」"
        "\nF6 金句立规矩型：<条件>才<评价>，如「剪直了才算本事」"
        "\nF7 结果反转型：预期落空或反转，如「关门关到门更开」「浇花发洪水」"
        "\n【候选配额（硬性）】每写一条先想好它属于哪个形态，输出时在 JSON 外加标注："
        "\n- 至少 1 条 F3 或 F4 或 F5（口吻/反差/反问）；"
        "\n- 至少 1 条 F1 或 F2（画面/动作）；"
        "\n- 至少 1 条 F6 或 F7（金句/反转）；"
        "\n- 同一形态最多 2 条；禁止三条同形态。"
        "\n- 候选1 =钩子潜力最高的一条，**不限定形态**（口吻/反差型就该放第一个）。"
        "\n生成完毕自查：若三条全无 F3/F4/F5，或三条同形态，整组作废重写。"
        "\n【标题生成规则】"
        f"\n- 硬性：标题必须 ≤{max_title_len} 字"
        "\n- 口吻/反差型必须像孩子说话：可用咋/凭啥/说好/明明/总行/不算，"
        "但禁止为凑口吻硬加语气词（了/吧/呢/啊）"
        "\n- 不用描述性事件名（如「抢饼干」「姐弟吵架」）；不要平铺直叙复述过程"
        "\n- 禁止书面类型术语：结盟/同盟/权威/公平/字面/破功"
        "\n- 禁止用「谁…」「…怨谁」质问句"
        "\n- 禁止编造剧本里没有的细节、道具或量词"
        "\n- 称呼只准用剧本孩子原话里出现过的，瞒着妈妈的戏不要开场「妈，…」"
        "\n- 标题人物必须来自对白：对白没出现的人（妈妈/爸爸等）禁止写进标题；"
        "源标题写了但对白没有，必须按对白重写，禁止沿用怼妈这类对不上的旧标题"
        "\n- 坏例：「剪刀剪歪了，还咋教弟弟？」「折飞机翻车」「看电视被抓包！」"
        "「三个全是翻车记」「三条全是画面复述」"
        "\n- 好例（仅示范形态，勿照抄）：「剪刀下的直线」「洗手不搓泡」"
        "「浇花发洪水」「关门关到门更开」"
        'JSON 输出样例：{"titles": ["候选1", "候选2", "候选3"]}。'
        "最有钩子的放第一个。"
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
    type_key = str(story_content.get("story_type") or "").strip().upper()
    if theme_phrase and title_absent_roles(theme_phrase, story_content):
        theme_phrase = ""
    if theme_phrase:
        # 锚词只作建议（2026-10-14 用户裁定）：不再写「必须原样保留」，避免逼出事件复述
        context_parts.append(f"本集主题短语（优先据此写，不强制照抄）：{theme_phrase}")
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
    elif type_key == "A":
        type_note = (
            "\n【本次类型硬规则：A 类权威翻车·封面不剧透】"
            "\n- 只表现立规矩/教人/示范的表面，翻车留给视频；"
            "\n- 禁止：还咋教、被戳穿、剪歪、翻车、咋收场；"
            "\n- 正例：剪刀下的直线、教弟弟剪直线、剪直了才算本事；"
            "\n- 反例：剪刀剪歪了，还咋教弟弟？、笔字写歪咋收场、折飞机翻车。"
        )

    anchors = extract_hard_anchor_words(draft_title, story_content)
    soft_anchors = [
        w for w in extract_core_anchor_words(draft_title, story_content) if w not in anchors
    ]
    theme_phrase = extract_theme_action_phrase(draft_title, story_content)
    if theme_phrase and title_absent_roles(theme_phrase, story_content):
        theme_phrase = ""
    cast_note = _dialogue_cast_mismatch_note(draft_title, story_content)
    # 手输初稿不干净（源稿标签/脏字符）时不拿它当「核心物件」，免得模型照抄
    fallback_label = draft_title
    if title_unusable(draft_title, story_content):
        fallback_label = str(
            story_content.get("scene_title") or story_content.get("theme") or draft_title
        ).strip()
    core_label = theme_phrase or fallback_label
    if title_absent_roles(core_label, story_content):
        core_label = "对白里的冲突（不要用源标题里没出场的人）"
    anchor_note = ""
    # 锚词只作建议不强制（2026-10-14 用户裁定）：硬性「必须含」会把标题逼成事件复述，
    # 好钩子（反问/原话/反差）全被挤掉；类型信息锚词硬卡仍在下方的 type_note 里。
    if _is_c_type(type_key) and theme_phrase:
        anchor_note = (
            f"\n【建议】本集主题短语是「{theme_phrase}」，带上更贴主题，但**不强制**；"
            "**优先写有钩子的说法**（孩子原话、反问、反差），"
            "别为了凑主题短语把标题写成事件复述。"
        )
    elif anchors or soft_anchors:
        names = "、".join([*anchors, *soft_anchors])
        anchor_note = (
            f"\n【建议·非强制】本场核心物件/动作/场景词：{names}。"
            "带上更贴主题，但不强制照抄；"
            "**优先写有钩子的说法**（孩子原话、反问、反差），别为了凑这些词把标题写成事件复述。"
        )

    if _is_c_type(type_key):
        steps = (
            "第一步，先看清本集的「主题 + 类型结局」：本集主题短语是"
            f"「{core_label}」，"
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
        )
        tail = (
            "主题锚定（最高优先）：标题要能看出本集主题，且带上本集主题短语或类型结局"
            "（上面「类型骨架」的结局，用孩子话）——"
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
        )
    else:
        steps = (
            "第一步，先找本集最强的钩子（孩子原话/反差/意外结果），本集核心物件/动作是"
            f"「{core_label}」。"
            "（这行写在 JSON 外面，不要进 JSON。）"
            "第二步，写 3 个候选 title（同一 JSON 数组，**钩子潜力最高**的放第一个，"
            "不限定形态），按配额覆盖形态："
            "至少 1 条 F3 口吻原话/F4 对照反差/F5 反问质问（如「就尝一口不算吃」这种口吻）；"
            "至少 1 条 F1 画面物件/F2 动作任务（如「剪刀下的直线」）；"
            "至少 1 条 F6 金句立规矩/F7 结果反转（如「剪直了才算本事」）。"
            "同一形态最多 2 条，禁止三条同形态、禁止三条全是画面复述。"
        )
        tail = (
            "主题锚定：保留核心物件/动作，允许画面化改写，不强制原文照抄；"
            "**口吻/反差/反问优先于画面复述**；"
            "禁止「结盟/同盟/权威/公平/字面/破功」这类书面术语。"
            f"{anchor_note}"
            f"{type_note}"
            "钩子要短促、能拍成封面大字；不要完整口语长句、不要剧透翻车、"
            "不要为凑口吻硬加语气词（了/吧/呢/啊）。"
            "好例「剪刀下的直线」「浇花发洪水」；坏例「剪刀剪歪了，还咋教弟弟？」。"
        )

    return (
        f"初稿标题：{draft_title}\n"
        f"剧本内容：\n{context}\n\n"
        f"{steps}"
        f"每个必须 ≤{max_title_len} 字：超字只删虚词/语气词，禁止删成事件名、禁止为了短丢钩子。"
        "钩子只从本剧本的冲突高潮台词/反差/核心道具里提炼，禁止套用与剧本无关的现成短句；"
        "禁止给剧本编造剧本里没有的细节、道具、意外原因或量词"
        "（如剧本只说「满地水」就绝不能写「满屋水」）；"
        "称呼只准用剧本孩子原话里的，且只在孩子真对被瞒对象/在场角色说话时用——"
        "瞒着妈妈藏/偷的戏孩子不会喊妈妈，标题不能开场「妈妈，…」「妈，…」点破。"
        f"{cast_note}"
        f"{tail}"
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
        "system": build_chat_title_system_prompt(
            max_title_len=max_len,
            story_type=story_content.get("story_type"),
        ),
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
