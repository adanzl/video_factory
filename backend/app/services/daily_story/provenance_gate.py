"""跨类型「出处闸门 / provenance_gate」共用构件。

P0：C 整件物升级规则须有前文锚点；正例/demo 逐字照抄检测。
不写主题词表 regex，只检槽位与关系类型。
"""

from __future__ import annotations

import re

_EXAMPLE_NORM_SKIP = re.compile(r"[的了吗呢啊呀哼！？。，、…\s「」“”\"'‘’：:]")

# line.py 酸奶合规示范中后段招牌句（与 validate 原 _C_EXAMPLE_PHRASES_NORM 同步）
_C_YOGURT_EXAMPLE_RAW: tuple[str, ...] = (
    "我早就不闹肚子了",
    "酸奶又没写你名字谁先拿到谁喝",
    "我先抓到手都攥出汗了松开",
    "你攥那么紧瓶身都热了我攥着瓶盖呢我先拿的",
    "瓶盖也算那你把瓶身给我我喝的时候你拿盖儿玩",
    "不行整瓶都是我的你松开手",
    "你数三下我数到二你就松手咱们同时放",
    "好我喊到三就松手你可别提前抢",
    "谁抢谁小狗我数一二你手松了我拿到了",
    "你耍赖我还没喊三呢你二就动手了",
    "你刚说数到三就松手可我数到二你还没放",
    "我那是数到二准备松你倒好二还没落音就抢了",
    "我不管现在瓶子在我手里我先喝你等下喝汤",
    "你刚才说谁抢谁小狗你抢了你才是小狗",
    "那是我说的可你也没按规矩来你赖皮",
    "反正我先拿到的你抢了不算酸奶归我",
    "哼明天我比你早",
    "那咱俩说好谁攥着酸奶再单脚站满十秒酸奶归谁",
    "行你先站我数着数满十秒才算你",
    "一二三你腿别抖我慢慢数",
    "四五你只说站满十秒又没说数数要多快",
    "你这是耍赖我站不住快数到十",
    "六七八你脚落地没站满十秒",
    "是你数太慢我才倒不算",
    "你刚说站满十秒就算慢数也是数你输",
    "可你那是故意拖长音赖皮",
    "你刚说谁攥着酸奶单脚站满十秒归谁你输归我",
    "明天我定规矩必须快数你一个字也别想拖",
)

# line.py 整件物结构正例正文招牌句（禁 LLM 逐字搬用）
_C_WHOLE_ITEM_EXAMPLE_RAW: tuple[str, ...] = (
    "又没写你名谁先拿到归谁",
    "我早抱得紧紧的的你两只手还空着呢",
    "我早抱得紧紧的你两只手还空着呢",
    "光抱着不行得双手攥住才算拿到",
    "光抱着不行得双手都抱住才算",
    "我两只手都攥紧了算不算",
    "你每次都这样我一伸手你就说先占着",
    "这次也先占着按你说的我手也搭着角",
    "这次也先占着按你说的我手也攥着",
    "光攥着不行得整个抱进怀里才算",
    "我整个抱怀里了你还说啥啊",
    "你刚抱了一下就松了我又没看见不算",
    "你刚说抱进怀里就行现在又反悔那怎么算",
    "做给我看一次不算连续三次都这样才算",
    "你总当我是小孩加一条连续证明三次才算",
    "长大就按规矩来加一条连续证明三次才算",
    "那我证明第四次因为第四次更厉害",
    "第四次更厉害第四次才最管用",
    "不算你在钻空子",
    "哪条说我钻空子了的你一条接一条说的",
    "不加了现在规则我说了算",
    "那现在到底哪条作数",
    "最开始那条作数谁先抢到",
    "最开始那条作数谁先拿到",
    "你刚说谁先拿到归谁我先抱到的",
    "你刚说谁先抢到归谁我先抢到的",
    "哼你赢规则不算赢我",
    "加一条拿到以后得连续证明三次才算",
    "新规则须上一条规则批准才算",
    "旧规则不同意你新增规则",
)

_RE_ABSURD_PROOF_RULE = re.compile(
    r"连续证明|"
    r"加一条[^。！？]{0,8}证明|"
    r"证明[^。！？]{0,6}(?:[二三四五六七八九十两]|次|才算)",
)

_RE_VERIFY_GAP_ANCHOR = re.compile(
    r"证明|演示|做给.{0,3}看|给你看|我看见|没看见|怎么算|算不算|"
    r"一次不算|一次不够|一次太|再做|别.{0,2}一下|你刚说[^。！？]{0,10}现在|"
    r"我又没|不算一直|抱了一下",
)

_RE_COUNT_QUANT_ANCHOR = re.compile(
    r"一次|两次|第[一二三四两三四五六七八九十]次|连续.{0,3}次|"
    r"[二三四五六七八九十两]次",
)


def normalize_line_for_example_match(line: str) -> str:
    return _EXAMPLE_NORM_SKIP.sub("", line or "")


def _norm_phrase_set(raw: tuple[str, ...]) -> frozenset[str]:
    return frozenset(normalize_line_for_example_match(s) for s in raw)


def c_yogurt_example_phrases_norm() -> frozenset[str]:
    return _norm_phrase_set(_C_YOGURT_EXAMPLE_RAW)


def c_whole_item_example_phrases_norm() -> frozenset[str]:
    return _norm_phrase_set(_C_WHOLE_ITEM_EXAMPLE_RAW)


def example_copy_hits(
    lines: list[str],
    phrases: frozenset[str],
    *,
    skip_first: int = 2,
) -> list[tuple[int, str]]:
    hits: list[tuple[int, str]] = []
    for j, ln in enumerate(lines[skip_first:], skip_first):
        if normalize_line_for_example_match(ln) in phrases:
            hits.append((j + 1, ln))
    return hits


def example_copy_error(
    lines: list[str],
    phrases: frozenset[str],
    *,
    min_hits: int = 2,
    skip_first: int = 2,
    label: str = "正例/demo",
) -> str | None:
    hits = example_copy_hits(lines, phrases, skip_first=skip_first)
    if len(hits) < min_hits:
        return None
    shown = "；".join(f"第{idx}句「{ln}」" for idx, ln in hits[:4])
    more = "…" if len(hits) > 4 else ""
    return (
        f"C类正文逐字照抄{label}（{shown}{more}）："
        "示范只许仿结构槽位，禁搬提示词/demo 原句——须换自己的措辞，"
        "抄正例不等于好笑"
    )


def c_example_phrases_for_profile(profile: str) -> frozenset[str]:
    phrases = set(c_yogurt_example_phrases_norm())
    if profile == "whole_item":
        phrases |= c_whole_item_example_phrases_norm()
    return frozenset(phrases)


def c_whole_item_rule_upgrade_provenance_error(
    lines: list[str],
    *,
    lookback: int = 5,
) -> str | None:
    """荒谬「证明/次数」升级规则须在前文有验证缺口 + 次数量化锚点。"""
    for i, ln in enumerate(lines):
        if not _RE_ABSURD_PROOF_RULE.search(ln):
            continue
        prior = "".join(lines[max(0, i - lookback) : i])
        has_verify = bool(_RE_VERIFY_GAP_ANCHOR.search(prior))
        has_count = bool(_RE_COUNT_QUANT_ANCHOR.search(prior))
        needs_count = bool(re.search(r"连续|[二三四五六七八九十两]", ln))
        if has_verify and (has_count or not needs_count):
            continue
        if has_verify and "一次" in prior:
            continue
        return (
            f"C类升级规则无出处（第{i + 1}句「{ln[:16]}」）："
            f"荒谬「证明/次数」规则须在前{lookback}句内已有验证缺口"
            "（怎么算/没看见/做给我看/一次不算）——禁从占有判据直接跳「证明三次」"
        )
    return None


def c_whole_item_weak_provenance_issue(lines: list[str]) -> str | None:
    """观感软降：有验证锚点但缺次数量化，或仅弱情绪桥。"""
    for i, ln in enumerate(lines):
        if not _RE_ABSURD_PROOF_RULE.search(ln):
            continue
        prior = "".join(lines[max(0, i - 5) : i])
        has_verify = bool(_RE_VERIFY_GAP_ANCHOR.search(prior))
        has_count = bool(_RE_COUNT_QUANT_ANCHOR.search(prior))
        if has_verify and not has_count and re.search(r"连续|[二三四五六七八九十两]", ln):
            return (
                f"C升级规则铺垫偏弱（第{i + 1}句）：已有验证缺口但缺「一次→N次」量化桥，"
                "读感仍像 demo 硬塞"
            )
    return None


def c_example_copy_soft_issue(lines: list[str], profile: str) -> str | None:
    """单句照抄 demo 招牌句 → 观感降分（validate ≥2 句才 hard fail）。"""
    phrases = c_example_phrases_for_profile(profile)
    hits = example_copy_hits(lines, phrases, skip_first=2)
    if len(hits) == 1:
        idx, ln = hits[0]
        return (
            f"C照抄demo单句（第{idx}句「{ln[:14]}」）："
            "正例只学结构槽位，禁搬提示词原句"
        )
    return None
