"""日常故事「人读」审稿：逐句查读着出戏的硬伤。

关键词打分只认字面，抓不到「一粒米都没有」和「把剩饭倒掉了」互相打架、
「我藏车你藏零食」下一句被说反、同一质问问三遍这类问题，故加一道审读。

次数写死，无回环：
1. `collect_local_issues` 程序先查同义重复句与两字空句；
2. 审读 1 次（LLM 以读者身份逐句读）→ 结构化问题清单；
3. 定点修 1 次（只回改动行，按行号替换，说话人与行数不动）；
4. 再审读 1 次 → 剩余问题直接扣分并写进 quality，不再重生成。
首轮不再双遍并集（双遍+thinking 曾把单稿拖到十几分钟）。
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

REVIEW_KINDS: tuple[str, ...] = (
    "矛盾",
    "错位",
    "示范",
    "重复",
    "塑料",
    "接不上",
    "无效证据",
    "其他",
)

# 各类硬伤扣分（读着最出戏的扣最重）
_KIND_PENALTY: dict[str, int] = {
    "矛盾": 8,
    "错位": 8,
    "示范": 10,
    "重复": 5,
    "塑料": 5,
    "接不上": 8,
    "无效证据": 8,
    "其他": 3,
}
REVIEW_PENALTY_CAP = 25
REVIEW_MAX_ISSUES = 6
# 首轮单遍：召回靠本地检 + 复审，禁止双遍 LLM 把单稿拖长
REVIEW_FIRST_PASSES = 1

_RE_PUNCT = re.compile(r"[，。！？…、：；~—\s·「」“”\"'?!.,]")
# 末段结构句：引用原话闭环，跟前面质问像也不算复读
_RE_STRUCT_CLOSE = re.compile(r"你自己说|那你刚才算不算|那你刚才也")

# 话题聚类：换词复读近邻检测抓不到时，按话题打标签计数
# (标签, 正则, 触发阈值) —— ≥阈值才报，末 2 句不计入质问类
_TOPIC_SPECS: tuple[tuple[str, re.Pattern[str], int], ...] = (
    (
        "空锅干碗物证",
        re.compile(
            r"空锅|干碗|一粒米|碗.{0,6}干|干干的|锅里.{0,10}(?:没|空)|"
            r"盘子.{0,4}空|空盘",
        ),
        3,
    ),
    (
        "肚子饿物证",
        re.compile(r"咕咕叫|肚子.{0,4}饿|没吃饱|没吃到|一口都没"),
        3,
    ),
    (
        "质问电话撒谎",
        re.compile(
            r"(?:电话里|跟奶奶).{0,14}(?:说|谎)|为啥.{0,2}说|为什么.{0,2}说|"
            r"那句话算不算|算不算谎",
        ),
        3,
    ),
)
# 自套逻辑那句常含「跟奶奶说」，不当质问复读
_RE_SELF_APPLY_SKIP = re.compile(
    r"那我(?:也|跟|对)|我也(?:这么|这样)|"
    r"我(?:明天|以后|回头)?跟(?:老师|奶奶|爷爷|外婆)说",
)


def _dialogue(story: dict) -> list[dict]:
    rows = story.get("dialogue")
    if not isinstance(rows, list):
        return []
    return [r for r in rows if isinstance(r, dict)]


def numbered_dialogue(story: dict) -> str:
    """给审读用的带行号台词表（行号从 1 起）。"""
    out: list[str] = []
    for i, row in enumerate(_dialogue(story), 1):
        sp = str(row.get("speaker") or "").strip()
        line = str(row.get("line") or "").strip()
        out.append(f"{i}. {sp}：{line}")
    return "\n".join(out)


def _norm(line: str) -> str:
    return _RE_PUNCT.sub("", line)


def _bigrams(text: str) -> set[str]:
    return {text[i : i + 2] for i in range(len(text) - 1)}


def _near_duplicate(a: str, b: str) -> bool:
    na, nb = _norm(a), _norm(b)
    # 下限压到 6 字：「要诚实不能说谎」只有 7 字，卡 8 字会漏掉整句复读
    if len(na) < 6 or len(nb) < 6:
        return False
    if na == nb or na in nb or nb in na:
        return True
    ga, gb = _bigrams(na), _bigrams(nb)
    if not ga or not gb:
        return False
    return len(ga & gb) / len(ga | gb) >= 0.55


def _is_struct_close(line: str, *, index: int, n: int) -> bool:
    """末 3 句里的原话闭环，不当复读。"""
    return index >= n - 3 and bool(_RE_STRUCT_CLOSE.search(line))


def _collect_topic_repeats(lines: list[str]) -> list[dict[str, Any]]:
    """同一话题换词说满阈值次 → 重复。"""
    n = len(lines)
    issues: list[dict[str, Any]] = []
    for label, pattern, threshold in _TOPIC_SPECS:
        hits = [
            i + 1
            for i, ln in enumerate(lines)
            if pattern.search(ln)
            and not _is_struct_close(ln, index=i, n=n)
            and not _RE_SELF_APPLY_SKIP.search(ln)
        ]
        if len(hits) < threshold:
            continue
        nos = "、".join(str(h) for h in hits)
        issues.append({
            "lines": hits,
            "kind": "重复",
            "desc": f"「{label}」在第{nos}句反复出现，换词复读",
            "fix": (
                f"只保留一处{label}，其余改成新信息或删掉"
            ),
        })
    return issues


def collect_local_issues(story: dict) -> list[dict[str, Any]]:
    """程序能直接判死的：同义重复、话题复读、两三字空句。"""
    rows = _dialogue(story)
    lines = [str(r.get("line") or "").strip() for r in rows]
    n = len(lines)
    issues: list[dict[str, Any]] = []

    seen_pairs: set[int] = set()
    for i in range(n):
        if i in seen_pairs or _is_struct_close(lines[i], index=i, n=n):
            continue
        for j in range(i + 1, n):
            if j in seen_pairs or _is_struct_close(lines[j], index=j, n=n):
                continue
            if not _near_duplicate(lines[i], lines[j]):
                continue
            seen_pairs.add(j)
            issues.append({
                "lines": [i + 1, j + 1],
                "kind": "重复",
                "desc": f"第{i + 1}句与第{j + 1}句说的是同一件事，换词重复",
                "fix": f"把第{j + 1}句改成推进新信息的话，勿复述第{i + 1}句",
            })
            break

    issues.extend(_collect_topic_repeats(lines))

    for i, line in enumerate(lines, 1):
        # 「怎么办！」这类三字惊慌句是有效反应，只揪「行！」级别的空应答
        if len(_norm(line)) <= 2:
            issues.append({
                "lines": [i],
                "kind": "其他",
                "desc": f"第{i}句是空应答（{line}），占行不推进",
                "fix": f"把第{i}句改成带信息的一句，或并进相邻句",
            })

    return issues


def build_review_prompts(theme: str, story: dict) -> tuple[str, str]:
    """审读提示：读者视角挑硬伤，不做风格建议。"""
    system = (
        "你是儿童短视频文案的审稿人，不是作者。"
        "你的唯一任务是像观众一样逐句读这段对白，挑出「读着出戏」的硬伤。\n"
        "只报下面 8 类，别报风格偏好、别夸、别改写全文：\n"
        "1 矛盾：前后事实打架"
        "（例：说「锅里一粒米都没有」，后面又说「你把剩饭倒掉了」；"
        "或同一件道具的位置/状态打架：钥匙一会儿还挂在门口钩上，"
        "一会儿又被说成跑掉了）。\n"
        "2 错位：谁做什么前后对不上"
        "（例：约定「我藏车你藏零食」，下一句却说成「你塞零食我塞车」；"
        "或某人做的事后来被说成另一人做的）。\n"
        "3 示范：大人开口指导孩子去隐瞒或说谎"
        "（例：妈妈说「这事不能让奶奶知道」「别告诉爸爸」）。\n"
        "  注意：大人自己言行不一、被孩子当场抓住双标，是本片的笑点设定，"
        "不算坏示范，别报；孩子之间商量瞒着大人也是设定，别报。\n"
        "4 重复：同一件事换词说两遍以上，或同一个质问反复问；"
        "帮腔开脱用同一个理由说两遍也算。\n"
        "5 塑料：不像真人会说的话"
        "（例：被当场抓住的人不接话，张口先讲道理教育对方）。\n"
        "6 接不上：回句没接住上一句的话头，答非所问或训错对象"
        "（例：孩子说「你自己没换鞋就进来了」，"
        "大人却回头命令孩子「赶紧脱了放鞋柜上」——孩子并没穿着鞋）。\n"
        "7 无效证据：追问方摆出的证据在证明一个没人否认的事，"
        "没打在对方刚说的开脱上"
        "（例：大人已承认没换鞋、只辩称「拿个东西不算」，"
        "孩子却还在花几句证明「这双就是出门的鞋」——该拆的是「不算」）。\n"
        "  故意荒诞的开脱（钥匙会跑、地板长花纹）是笑点设定，"
        "只要接住了话头就别报。\n"
        "8 其他：上面装不下但确实读着出戏的。\n\n"
        "下面几处是本类结构设计，即使看着像重复也别报：\n"
        "- 开场两句是片头定格，与正文开头重合是正常拼接；\n"
        "- 最后一句大人认输软收，倒数第二句孩子引用大人原话闭环。\n"
        "除此之外，同一个质问被反复问、同一条规矩被说两遍，都要报。\n"
        "没问题就返回空数组，不要为凑数硬报。\n\n"
        "按四步走，别跳步：\n"
        "第一步 facts：逐条记下读到的事实——谁答应做什么（分工、约定）、"
        "出现过哪些实物状态（锅空/碗干/袋破/渣在哪）、"
        "每个人做过哪些动作。\n"
        "第二步 chain（对质戏必做）：先写一句「争议点」——"
        "被抓的人**承认了什么、还在辩什么**；"
        "然后从被抓现行那句起**逐句**标注"
        "「第n句 回应第m句的哪个点」。"
        "标注时当场判：某句标不出它回应上一句的什么，就是「接不上」；"
        "孩子摆的证据落在「已承认」一侧而不是争议点上，就是「无效证据」；"
        "开脱句与前面记下的实物状态硬碰（钥匙明明还挂着却说跑了），"
        "就是「矛盾」。\n"
        "第三步 checks：前 7 类**每一类都必须表态**，"
        "写「无」或写清哪几句有问题，不许省略某一类。\n"
        "第四步 issues：把 checks 里判「有」的逐条展开。\n\n"
        "只输出 JSON：\n"
        '{"facts":["3昭昭分工:自己藏车、灿灿藏零食","5锅里没米","6剩饭被倒掉"],'
        '"chain":{"争议点":"妈妈承认没换鞋，辩「拿东西不算进屋」",'
        '"标注":["4回应3的抓现行:辩拿钥匙","5回应4:帮腔不算",'
        '"8回应不了7:在证明已承认的事→无效证据"]},'
        '"checks":{"矛盾":"第5句锅里没米，第6句又倒剩饭","错位":"无",'
        '"示范":"无","重复":"第5句与第8句都说碗干","塑料":"无",'
        '"接不上":"无","无效证据":"第8句"},'
        '"issues":[{"lines":[5,6],"kind":"矛盾",'
        '"desc":"第5句说锅里一粒米都没有，第6句又说把剩饭倒掉了",'
        '"fix":"第6句改成…"}]}\n'
        f"lines 用左侧行号；最多报 {REVIEW_MAX_ISSUES} 条，按严重度排序；"
        "fix 写一句具体怎么改，别写空话。"
    )
    user = (
        f"主题：{theme}\n"
        f"场景：{story.get('setting') or ''}\n"
        f"矛盾内核：{story.get('conflict_core') or ''}\n\n"
        f"对白：\n{numbered_dialogue(story)}\n\n"
        "逐句读一遍，按上面 8 类输出 JSON。"
    )
    return system, user


def parse_review_issues(raw: Any, *, line_count: int) -> list[dict[str, Any]]:
    """解析审读输出，丢掉行号越界与类型不认的条目。"""
    if not isinstance(raw, dict):
        return []
    items = raw.get("issues")
    if not isinstance(items, list):
        return []
    out: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind") or "").strip()
        if kind not in REVIEW_KINDS:
            kind = "其他"
        nos = item.get("lines")
        if isinstance(nos, int):
            nos = [nos]
        if not isinstance(nos, list):
            continue
        picked = [
            int(n)
            for n in nos
            if isinstance(n, (int, float)) and 1 <= int(n) <= line_count
        ]
        if not picked:
            continue
        desc = str(item.get("desc") or "").strip()
        if not desc:
            continue
        out.append({
            "lines": picked,
            "kind": kind,
            "desc": desc,
            "fix": str(item.get("fix") or "").strip(),
        })
        if len(out) >= REVIEW_MAX_ISSUES:
            break
    return out


def merge_issues(*groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """合并问题清单：同类且行号有交集视为同一条，避免同一处重复扣分。"""
    out: list[dict[str, Any]] = []
    for group in groups:
        for item in group:
            lines = set(item["lines"])
            for kept in out:
                if kept["kind"] == item["kind"] and lines & set(kept["lines"]):
                    kept["lines"] = sorted(set(kept["lines"]) | lines)
                    break
            else:
                out.append({**item, "lines": sorted(lines)})
    return out[:REVIEW_MAX_ISSUES]


def build_spot_fix_prompts(
    theme: str,
    story: dict,
    issues: list[dict[str, Any]],
    *,
    line_chars_max: int,
) -> tuple[str, str]:
    """定点修提示：只回被点出的那几行，行数与说话人不动。"""
    system = (
        "你是儿童短视频文案的修订者。给你一段对白和审稿人挑出的问题，"
        "只重写被点到的那几行，其余一字不动。\n"
        "硬要求：\n"
        f"- 行数不变、说话人不变、每行≤{line_chars_max}字；\n"
        "- line 只写台词本身，**不要带「昭昭：」这种说话人前缀**；\n"
        "- 只改被点到的行号，勿顺手改别处，勿新增或删除行；\n"
        "- 改完后前后事实要对得上，别再造新矛盾；\n"
        "- **末段孩子引用大人原话的闭环句与最后一句认输，一律不许改**"
        "（那是收束硬结构）；\n"
        "- 口语，像真人小孩和妈妈说话，勿写旁白与镜头描写。\n"
        "只输出 JSON：\n"
        '{"fixes":[{"no":5,"line":"改好的这一句"}]}'
    )
    issue_text = "\n".join(
        f"- 第{'、'.join(str(n) for n in it['lines'])}句"
        f"（{it['kind']}）：{it['desc']}"
        + (f" 建议：{it['fix']}" if it.get("fix") else "")
        for it in issues
    )
    user = (
        f"主题：{theme}\n"
        f"场景：{story.get('setting') or ''}\n"
        f"矛盾内核：{story.get('conflict_core') or ''}\n\n"
        f"对白：\n{numbered_dialogue(story)}\n\n"
        f"审稿人挑出的问题：\n{issue_text}\n\n"
        "只输出需要改的行（no 用左侧行号）。"
    )
    return system, user


def _strip_speaker_prefix(line: str, *, speaker: str) -> str:
    """模型爱把「昭昭：」抄进台词，带前缀会顶爆单句字数硬卡。"""
    for name in (speaker, "昭昭", "灿灿", "妈妈"):
        if name and line.startswith(name):
            return line[len(name) :].lstrip("：:").strip()
    return line


def fix_line_numbers(raw: Any) -> list[int]:
    """取出定点修想改的行号，供逐条试用。"""
    if not isinstance(raw, dict) or not isinstance(raw.get("fixes"), list):
        return []
    out: list[int] = []
    for item in raw["fixes"]:
        if not isinstance(item, dict):
            continue
        try:
            no = int(item.get("no"))
        except (TypeError, ValueError):
            continue
        if no not in out:
            out.append(no)
    return out


def apply_spot_fixes(
    story: dict,
    raw: Any,
    *,
    only: set[int] | None = None,
) -> tuple[dict, list[str]]:
    """按行号替换台词；同步 discovery_opening；返回新故事与改动说明。

    `only` 限定本次只落哪几行，用于逐条试落、避开会破硬卡的那条。
    """
    import copy

    if not isinstance(raw, dict):
        return story, []
    fixes = raw.get("fixes")
    if not isinstance(fixes, list):
        return story, []

    out = copy.deepcopy(story)
    rows = _dialogue(out)
    opening = out.get("discovery_opening")
    notes: list[str] = []
    for item in fixes:
        if not isinstance(item, dict):
            continue
        try:
            no = int(item.get("no"))
        except (TypeError, ValueError):
            continue
        new_line = _strip_speaker_prefix(
            str(item.get("line") or "").strip(),
            speaker=str(rows[no - 1].get("speaker") or "").strip()
            if 1 <= no <= len(rows)
            else "",
        )
        if not new_line or not (1 <= no <= len(rows)):
            continue
        if only is not None and no not in only:
            continue
        old_line = str(rows[no - 1].get("line") or "").strip()
        if new_line == old_line:
            continue
        rows[no - 1]["line"] = new_line
        notes.append(f"第{no}句")
        # 开场是正文前两句的副本，改了就得同步，否则拼接后自相矛盾
        if isinstance(opening, list) and no <= len(opening):
            row = opening[no - 1]
            if isinstance(row, dict) and str(row.get("line") or "").strip() == old_line:
                row["line"] = new_line
    return out, notes


def review_penalty(issues: list[dict[str, Any]]) -> tuple[int, list[str]]:
    """剩余硬伤换算扣分与 quality 里要写的原因。"""
    if not issues:
        return 0, []
    points = 0
    reasons: list[str] = []
    for item in issues:
        points += _KIND_PENALTY.get(item["kind"], _KIND_PENALTY["其他"])
        nos = "、".join(str(n) for n in item["lines"])
        reasons.append(f"审读第{nos}句{item['kind']}：{item['desc']}")
    return min(REVIEW_PENALTY_CAP, points), reasons


def apply_review_to_quality(
    story: dict,
    issues: list[dict[str, Any]],
) -> dict:
    """把审读结果落到 quality：扣分、记原因、存清单。"""
    from app.services.daily_story.quality import _grade_from_score

    quality = story.get("quality")
    if not isinstance(quality, dict):
        return story
    points, reasons = review_penalty(issues)
    quality["review_issues"] = issues
    if not points:
        return story
    score = max(0, int(quality.get("score") or 0) - points)
    quality["score"] = score
    quality["grade"] = _grade_from_score(score)
    quality["reasons"] = [*(quality.get("reasons") or []), *reasons]
    head = reasons[0]
    quality["summary"] = (
        f"{head}，另有{len(reasons) - 1}项" if len(reasons) > 1 else head
    )
    return story


def _apply_fixes_greedily(
    story: dict,
    raw_fixes: Any,
    *,
    theme: str,
) -> dict:
    """逐条试落定点修：能过硬卡的留下，会破结构的那条丢掉。

    审读只看读感，不知道各类的收束硬卡（如末段须扣原话闭环、
    说谎题须留实物反证），整批落盘常被硬卡整体打回，逐条试才留得下好的。
    """
    from app.services.daily_story.prompts import validate_daily_story_json
    from app.services.daily_story.quality import attach_daily_story_quality

    accepted: set[int] = set()
    for no in fix_line_numbers(raw_fixes):
        trial = accepted | {no}
        condition, notes = apply_spot_fixes(story, raw_fixes, only=trial)
        if not notes:
            continue
        try:
            validate_daily_story_json(condition, phase="full")
        except ValueError as exc:
            logger.info(
                "[DAILY_STORY] spot fix line %d dropped (breaks hard card): %s",
                no,
                exc,
            )
            continue
        accepted = trial

    if not accepted:
        logger.warning("[DAILY_STORY] spot fix produced nothing usable")
        return story

    fixed, notes = apply_spot_fixes(story, raw_fixes, only=accepted)
    # 定点改句后可能又带回重复立规等；再跑一轮本地结构 patch
    from app.services.daily_story.prompts import try_local_patch_daily_story_body

    fixed["_theme"] = theme
    patched, patch_notes = try_local_patch_daily_story_body(fixed)
    if patch_notes:
        fixed = patched
        notes.extend(patch_notes)
        logger.info(
            "[DAILY_STORY] local patch after spot fix: %s",
            ",".join(patch_notes),
        )
    if isinstance(fixed, dict):
        fixed.pop("_theme", None)
        fixed.pop("_story_type", None)
    try:
        validate_daily_story_json(fixed, phase="full")
    except ValueError as exc:
        logger.warning(
            "[DAILY_STORY] spot fix+patch still breaks hard card, keep pre-fix: %s",
            exc,
        )
        return story
    attach_daily_story_quality(fixed, theme=theme)
    logger.info("[DAILY_STORY] spot fix applied: %s", "，".join(notes))
    return fixed


def run_daily_story_review(
    client: Any,
    theme: str,
    story: dict,
) -> dict:
    """审读→定点修→复审，全程固定次数；客户端不支持则只走程序检查。"""
    if not isinstance(story, dict) or not _dialogue(story):
        return story

    review = getattr(client, "review_daily_story_issues", None)
    spot_fix = getattr(client, "spot_fix_daily_story", None)

    # 首轮审读跑两遍取并集：单遍召回会漏，两遍能稳住明显硬伤
    issues = merge_issues(
        collect_local_issues(story),
        *(
            [review(theme, story) for _ in range(REVIEW_FIRST_PASSES)]
            if callable(review)
            else []
        ),
    )
    if not issues:
        logger.info("[DAILY_STORY] review clean, no spot fix")
        return apply_review_to_quality(story, [])

    logger.info(
        "[DAILY_STORY] review found %d issue(s): %s",
        len(issues),
        "；".join(f"{i['kind']}@{i['lines']}" for i in issues),
    )

    if callable(spot_fix):
        story = _apply_fixes_greedily(
            story,
            spot_fix(theme, story, issues),
            theme=theme,
        )

    remaining = merge_issues(
        collect_local_issues(story),
        review(theme, story) if callable(review) else [],
    )
    if remaining:
        logger.warning(
            "[DAILY_STORY] review remaining %d issue(s) after spot fix",
            len(remaining),
        )
    return apply_review_to_quality(story, remaining)
