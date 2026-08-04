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
_OUTCOME_REVEAL_RE = re.compile(r"全滚|滚出来|滚出去|掉一地|全没了|全撒|弄翻|被抓住|被抓|掉地上")


def extract_core_anchor_words(draft: str, story_content: dict) -> list[str]:
    """提取本场核心名词（2–4 字）：原始 scene_title 与冲突核心/场景/主题共有的词。

    用于「标题必须包含核心名词」的硬要求与 picker 兜底，防「鞋底渣印谁擦」式
    盯住次级元素、把核心主题（月饼）丢掉。取不到交集时返回空列表 = 不强制。
    """
    scene = title_core(str(story_content.get('scene_title') or draft or ''))
    if not scene:
        return []
    blob = ''.join(str(story_content.get(k) or '') for k in ('conflict_core', 'setting', 'theme'))
    for n in (3, 2, 4):
        found: list[str] = []
        for i in range(len(scene) - n + 1):
            w = scene[i:i + n]
            if w in blob and w not in found:
                found.append(w)
        if found:
            return found[:2]
    return []


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
        score += 2
    if "不是我" in title or "谁" in title or "怪我" in title:
        score += 2
    if "自己" in title:
        score += 2
    if title[:1] in "妈姐爸哥弟":
        score += 1
    if _OUTCOME_REVEAL_RE.search(title):
        score -= 3
    return score


def pick_best_chat_title(draft: str, candidates: list[str], *, max_len: int, avoid_titles: list[str] | None=None, anchor_words: list[str] | None=None) -> str:
    """从多个候选中选最终标题：退化保护 + 长度硬截断 + 钩子分排序。

    - 命中初稿或 avoid_titles（已用过的标题）的候选降权，避免手动重跑输出同一个；
    - 问号/叹号/称呼开头/甩锅质问优先于平铺直叙的事件复述；
    - anchor_words：本场核心名词（如「月饼」）。不含任一核心词的候选重罚；
      全部候选都不含核心词时回退初稿，绝不写跑题标题。
    """
    avoid = [str(t).strip() for t in (avoid_titles or []) if str(t).strip()]
    anchors = [str(a).strip() for a in (anchor_words or []) if str(a).strip()]
    draft_core = title_core(draft)
    avoid_cores = {title_core(t) for t in avoid}
    best = draft
    best_score = -10**9
    any_anchored = False
    for cand in candidates:
        chosen = select_optimized_title(draft, cand, max_len=max_len)
        score = _chat_title_hook_score(chosen)
        anchored = (not anchors) or any(a in title_core(chosen) for a in anchors)
        if anchored:
            any_anchored = True
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

# chat 封面标题固定 ≤10；不跟全局 MAX_TITLE_LENGTH（默认16）走
CHAT_TITLE_MAX_LEN = 10


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
        "\n【标题句式模板】按其中一种句式，从本剧本抓最强钩子（只讲句式，不给成品例："
        "禁止把别的故事里的话/梗直接套用过来）："
        "\n①台词钩子：冲突高潮里孩子说的原话，稍压虚词，像在替孩子喊话。"
        "\n②反差设问：大人双标/口嗨被戳穿的问句，让人想点开反驳。"
        "\n③意外后果：小动作惹出没料到的连锁结果，把「越补越糟」的荒诞说半截吊胃口；"
        "最好带甩锅口吻——把意外赖给道具/对方，像孩子替自己开脱，别只报结局。"
        "\n④悬念藏匿：藏/偷/瞒 + 藏住的东西，勾起「后来呢」。"
        "\n【标题生成规则】"
        f"\n- 硬性：标题必须 ≤{max_title_len} 字（最终上架字数以此为准）"
        "\n- 优先来源：①冲突高潮里孩子甩锅/辩解/质问的那句台词"
        "（比平铺直叙复述事件更有钩子）；"
        "\n② punchline_explain 里的反差浓缩成口语；"
        "\n③ 核心道具/动作名词"
        "\n- 要有口吻或轻反差，让家长一秒认出「自家日常笑点」"
        "\n- 不用描述性事件名（如「抢饼干」「姐弟吵架」）"
        "\n- 禁止为了短删掉钩子：超字只删虚词/语气词，保住钩子词"
        "\n- 别做事件播报：把结局动词（「全滚出来」「掉一地」「被抓住」）"
        "换成孩子口吻（甩锅「不是我」/质问「谁…」/喊话「妈，…」）或留半截吊胃口"
        "\n- 钩子要落在具体好笑画面：把一个道具+动作（「擦」「踩」「摔」「翻」）放进标题，"
        "让读者能脑补画面，别写泛泛的结果；优先找「为偷吃一口赔上一整盒」式的荒谬反差账"
        "\n- 主题不能丢（最高优先，硬性）：标题必须包含本场核心名词（user prompt 列出的「核心名词」），"
        "不能只写具体画面/甩锅口吻而丢掉核心名词；不含核心名词的候选作废"
        "\n- 三个候选句式要拉开（一句孩子原话 / 一个具体道具意外 / 一个反差问句），"
        "别全是「谁…」「…怨谁」质问句"
        "\n- 坏标题示例：「姐弟偷吃饼干」「月饼全滚出来了」「被妈妈抓住」「孩子的选择」"
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

    context_parts = []
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
        "请写 3 个候选 title（同一 JSON 数组，最有钩子的放第一个；"
        "句式要拉开：一句孩子原话 / 一个具体道具意外 / 一个反差问句，别三个都一个方向）。"
        f"每个必须 ≤{max_title_len} 字：超字只删虚词/语气词，禁止删成事件名、禁止为了短丢钩子。"
        "钩子只从本剧本的冲突高潮台词/反差/核心道具里提炼，禁止套用与剧本无关的现成短句。"
        "主题锚定（最高优先）：标题要落在本场核心上，不能只留甩锅或问答口吻丢掉主题。"
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
