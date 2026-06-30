"""选题生成：Prompt 与响应解析。"""

from __future__ import annotations

import re
from typing import Any

_TOPIC_TRACKS = frozenset(
    {
        "日常科学原理",
        "生活避坑实用常识",
        "数码小白避坑",
        "古代冷门生活史",
        "历史悬案",
    }
)
_TOPIC_TEMPLATES = frozenset({"误区反问式", "反差好奇式", "实操避坑式", "悬念钩子式", "未解之谜式"})


def build_topic_system_prompt(*, max_title_len: int) -> str:
    return (
        "你是 B 站历史悬案视频选题策划。输出 JSON，字段 topics。"
        "topics 为数组，每项含 title、keyword、track、template、hook。"
        "如果 track=历史悬案，title 格式：事件代号：反常画面。例如：烛影斧声：宋太祖半夜暴毙。雍正暴毙：圆明园咯血无人敢近。title 18 字以内。"
        "核心要求：冒号后面必须是一个反常画面（有人在深夜做了一件事、一个东西不该出现在那里、尸体不完整了），不能是笼统陈述。\n"
        "必须选普通人也知道的知名历史人物（慈禧、和珅、秦始皇、雍正、杨贵妃、崇祯、曹操、成吉思汗等），"
        "不选冷门人物或考古发现。\n"
        "四大方向（至少满足其一）：\n"
        "1. 尸体/文物/下落不明——人死了但身体找不到、记载有但实物没有\n"
        "2. 证据被刻意销毁——档案没了、地图烧了、史书被删了一段\n"
        "3. 物理上解释不了——两千年的东西还有弹性、长明灯千年不灭\n"
        "4. 一个人的死或生有多个无法调和的版本\n"
        "禁止：考古发现、学术争议、冷门人物、账目差异、谁说了哪句话\n"
        "风格参考：\n"
        "慈禧陵墓被军阀盗掘棺里夜明珠辗转流失，最后一次出现是1949年然后消失了\n"
        "明朝灭亡前一夜崇祯把宫里所有账册地图烧了，没人知道他最后藏了什么\n"
        "杨贵妃死在马嵬坡但日本有一座庙墓碑上写的是她的名字建于唐朝\n"
        "建文帝火中失踪四百年后有人拿出一把龙椅说自己是他的后代\n"
        "track 从以下五选一：日常科学原理、生活避坑实用常识、数码小白避坑、古代冷门生活史、历史悬案。"
        "除非主题明确是历史人物的死亡疑云、消失宝藏、未解之谜，否则不要选「历史悬案」。科技产业类话题选「数码小白避坑」或「日常科学原理」。\n"
        "如果主题聚焦未解之谜、死亡疑云、消失宝藏、皇家秘辛，track 必须选「历史悬案」；"
        "普通冷门历史知识（非悬疑类）才选「古代冷门生活史」。\n"
        "template 从以下五选一：误区反问式、反差好奇式、实操避坑式、悬念钩子式、未解之谜式。"
        "hook 用一句话说明为什么观众会点进来（15-30字）。"
        "每项还须输出 keywords：该主题涉及的核心实体数组（人名/地名/事件名，每项2-6字，1-3项），用于去重。如果一个谜案涉及多个实体（如和珅、嘉庆），则输出多个关键词。\n"
        "硬性禁止：医疗养生、理财股市、时政情感、热点新闻、真人出镜场景、"
        "无法核验的争议、预测性表述。"
        "偏好：画面可用卡通/示意插画表达，科学常识或生活原理，长尾搜索向。"
        "所有 track 的 title 可选对话反转式风格：用问句抛出事件，回应部分要有态度——自信、调侃、甚至带点挑衅，不要平淡陈述事实。"
        "例如：日本断供光刻胶？中国的五年产能等你呢。关键在回应部分要有情绪和个性，不是干巴巴的「已备好」「够用了」「投产了」。\n"
        "如果 track=历史悬案，标题必须包含一个具体反转或矛盾细节，禁止写成「xxx为何xxxx」这种平淡问句；"
        "禁止使用「惊人证据」「颠覆认知」「细思极恐」「隐藏千年的」「真相颠覆」等虚词大词；"
        "标题应当像讲一个具体事实一样自然，钩子藏在事实本身里，不靠形容词制造情绪。\n"
        "历史悬案类标题要求：每一句都要让人产生「等一下，那他是怎么死的？」「所以凶手到底是谁？」这种追问冲动；"
        "钩子必须是「已知结果 × 无法解释的细节」的组合，例如：全城目击的处决 → 第二天尸体不见了；"
        "史书写了死因 → 但出土的尸骨上有一道不属于那个时代的伤口。\n"
        "历史悬案类标题必须包含核心人物或事件名称，不可用「他」「她」「那个人」代替，让读者仅看标题就能知道在讲谁的悬案。\n"
        "标题分布建议：误区反问式约 5 条、反差好奇式约 2 条、实操避坑式约 1 条、"
        "悬念钩子式约 1 条、未解之谜式约 1 条。"
        'JSON 输出样例：{"topics": [{"title": "标题", "keywords": ["和珅","嘉庆"], "track": "历史悬案", '
        '"template": "误区反问式", "hook": "一句话钩子"}]}'
    )


def build_topic_user_prompt(*, theme: str, count: int) -> str:
    return (
        f"主题方向：{theme.strip()}\n"
        f"请生成 {count} 个互不重复、适合 AI 全自动科普成片的中文视频标题。"
    )


def normalize_title(title: str, *, max_len: int, track: str = "") -> str:
    cleaned = re.sub(r"\s+", "", title.strip())
    if track == "历史悬案":
        cap = 18
    else:
        cap = max_len
    if len(cleaned) <= cap:
        return cleaned
    # 截断到最后一个完整逗号或句号前，避免硬截断
    truncated = cleaned[:cap]
    last_break = max(truncated.rfind("，"), truncated.rfind("。"), truncated.rfind("——"))
    if last_break > cap // 2:
        return truncated[:last_break]
    return truncated


def parse_topics_payload(raw: dict[str, Any], *, max_title_len: int) -> list[dict[str, str]]:
    for key in ("topics", "titles"):
        items = raw.get(key)
        if not isinstance(items, list) or not items:
            continue
        if all(isinstance(item, str) for item in items):
            out = _topics_from_titles(items, max_title_len=max_title_len)
            if out:
                return out
        if key == "topics":
            break

    items = raw.get("topics")
    if not isinstance(items, list) or not items:
        raise ValueError("LLM response missing topics array")

    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        title = normalize_title(str(item.get("title") or ""), max_len=max_title_len, track=item.get("track", ""))
        if not title or title in seen:
            continue
        raw_kws = item.get("keywords") or item.get("keyword") or ""
        if isinstance(raw_kws, list):
            kw_str = ",".join(str(k).strip()[:6] for k in raw_kws if str(k).strip())
        else:
            kw_str = str(raw_kws).strip()[:8]
        track = str(item.get("track") or "").strip()
        template = str(item.get("template") or "").strip()
        hook = str(item.get("hook") or "").strip()
        if track not in _TOPIC_TRACKS:
            track = "日常科学原理"
        if template not in _TOPIC_TEMPLATES:
            template = "误区反问式"
        seen.add(title)
        out.append(
            {
                "title": title,
                "keyword": kw_str or None,
                "track": track,
                "template": template,
                "hook": hook,
            }
        )
    if not out:
        raise ValueError("LLM topics array has no valid entries")
    return out


def _topics_from_titles(titles: list[str], *, max_title_len: int) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw in titles:
        title = normalize_title(raw, max_len=max_title_len)
        if not title or title in seen:
            continue
        seen.add(title)
        out.append(
            {
                "title": title,
                "track": "日常科学原理",
                "template": "误区反问式",
                "hook": "",
            }
        )
    return out
