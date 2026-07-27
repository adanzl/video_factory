"""A 类好笑维硬伤与引话 haystack。"""

from __future__ import annotations

import re

_RE_DIRECT_QUOTE = re.compile(
    r"(?:你刚才说|你自己说|你不是说|你刚说|你说的)([^，。！？…]{3,})",
)


def closing_quote_haystack(
    lines: list[str],
    speakers: list[str] | None,
    body_text: str,
) -> str:
    if not speakers or len(speakers) != len(lines):
        return body_text
    body_n = len(lines[:-4]) if len(lines) > 4 else len(lines) - 1
    cancan = "".join(
        lines[i] for i in range(body_n) if speakers[i] == "灿灿"
    )
    return cancan if cancan.strip() else body_text


def _close_four_beat_complete(tail4: list[str]) -> bool:
    if len(tail4) < 4:
        return False
    return (
        "那不一样" in tail4[-3]
        and ("哪里不一样" in tail4[-2] or "都是听" in tail4[-2])
        and any(m in tail4[-1] for m in ("哼", "行吧", "随便", "好吧", "算了"))
    )


def collect_humor_issues(
    lines: list[str],
    speakers: list[str] | None,
) -> list[str]:
    cons: list[str] = []
    body = lines[:-4] if len(lines) > 4 else lines[:-1]
    tail4 = lines[-4:] if len(lines) >= 4 else lines
    body_text = "".join(body)
    tail_text = "".join(tail4)

    if ("哪里不一样" in body_text or "都是听" in body_text) and (
        "哪里不一样" in tail_text or "都是听" in tail_text
    ):
        cons.append("追问闭环模板复读")
    if "不公平" in body_text and "凭什么" not in body_text[:40]:
        cons.append("偏C式争公平口号")
    last = tail4[-1] if tail4 else ""
    if re.search(r"哼", last) and re.search(
        r"你.{0,4}(?:重刷|再刷|漱口|过关)|明天你|你等着",
        last,
    ):
        cons.append("末句哼完仍发指令，破功不干净")
    if re.search(r"算你厉害|你赢了|算你赢|你厉害", last):
        cons.append("末句认赢或甩狠，破功不干净")
    if len(tail4) >= 3 and "那不一样" in tail4[-3]:
        dodge = tail4[-3]
        if re.search(r"我是姐姐|我说了算", dodge) and not re.search(
            r"示范|泡沫|教学|吐泡沫|教你",
            dodge,
        ):
            cons.append("收束空甩身份，不好笑")
        if re.search(r"试味道|试甜|尝一下|帮你试|尝了|只尝|试一口", dodge) and re.search(
            r"试甜|试味道|帮你试|尝了|只尝|尝味道|甜不甜|试一口|确认味道",
            body_text,
        ):
            cons.append("收束借口复读中段，不好笑")
        if re.search(r"把关|负责|我说了算", dodge) and not re.search(
            r"样品|耗掉|泡沫|教学",
            dodge,
        ):
            cons.append("收束空甩身份，不好笑")
        if re.search(r"那不一样[，,]?\s*(我那是)?[…\.。]{0,3}\s*$", dodge):
            cons.append("收束空甩身份，不好笑")
    excuse_n = 0
    if re.search(
        r"试甜|试味道|帮你试|尝一下|尝得准|尝了|只尝|尝味道|甜不甜|"
        r"试一口|确认味道|咬一口就|知道甜|先试|算尝味|"
        r"看看熟|熟不熟|坏了没|有没有坏|是甜的|甜度|确认质量",
        body_text,
    ):
        excuse_n += 1
    if re.search(r"检查不算|检查样品|特地挑", body_text):
        excuse_n += 1
    if re.search(r"把关|资格|负责质量|检查员|有特权", body_text):
        excuse_n += 1
    if re.search(r"示范|教你吐|特批", body_text):
        excuse_n += 1
    if excuse_n >= 2:
        cons.append("中段多套免责借口叠罗汉")
    if re.search(r"偷吃|饭前|水果|苹果|草莓|葡萄", "".join(lines)):
        if re.search(
            r"半成品|大家安全|新不新鲜|合格证书|专业方法|含三秒|"
            r"为了大家|品质检测|安全起见|确认甜度|确认质量|是甜的",
            body_text,
        ):
            cons.append("偷吃质检说明书注水，不好笑")
        if sum(1 for ln in lines if "洗手" in ln) >= 2:
            cons.append("偷吃质检说明书注水，不好笑")
        check_i = next(
            (
                i
                for i, ln in enumerate(lines)
                if re.search(r"检查样品|特地挑|检查不算吃", ln)
            ),
            None,
        )
        if check_i is not None:
            cancan_dodge = any(
                (speakers[i] if speakers and i < len(speakers) else "") == "灿灿"
                and re.search(r"溅|手脏|擦过|果汁", lines[i])
                for i in range(check_i)
            )
            if not cancan_dodge:
                cons.append("偷吃缺赖账抬杠，不好笑")
        if sum(1 for ln in lines if re.search(r"[啦呀嘛]$", str(ln).rstrip())) >= 4:
            cons.append("偷吃质检说明书注水，不好笑")
        pairs = list(zip(speakers or [""] * len(lines), lines, strict=False))
        spit_i = next(
            (
                i
                for i, (sp, ln) in enumerate(pairs)
                if sp == "灿灿"
                and (
                    re.search(r"已经咽|咽下去了|看不了|吐不出来", ln)
                    or (
                        re.search(r"咽了", ln)
                        and "才算" not in ln
                        and "不咽" not in ln
                    )
                )
            ),
            None,
        )
        quote_indices = [
            i
            for i, (_sp, ln) in enumerate(pairs)
            if re.search(
                r"你刚才(?:明明|自己)?说|你自己(?:刚才)?说|你刚说",
                ln,
            )
        ]
        quote_i = quote_indices[-1] if quote_indices else None
        if len(quote_indices) >= 2 or (
            quote_i is not None and quote_i < len(pairs) - 4
        ):
            cons.append("中段提前引话，不好笑")
        if spit_i is not None and quote_i is not None and quote_i - spit_i > 3:
            cons.append("咽下后质检说明书注水，不好笑")
    if re.search(r"反正我说了算|我说了算", "".join(tail4[-1:])):
        cons.append("末句仍嘴硬甩权，破功不干净")
    if re.search(r"刷牙|漱口|牙刷|吐水", "".join(lines)):
        fun_beat = bool(re.search(
            r"噗|一[、,，]二|才[一二两三四五六\d]+下|才刷.{0,4}下",
            "".join(lines),
        ))
        if not fun_beat:
            cons.append("刷牙缺可拍一锤声画（噗/数下就吐）")
    if re.search(r"刷牙|漱口|牙刷", "".join(lines)):
        quote_frags = [
            m.group(1)
            for line in tail4
            for m in _RE_DIRECT_QUOTE.finditer(line)
        ]
        hammer_hit = bool(re.search(
            r"才刷|就吐|就停|就漱|玩手机|泡沫|几下|二十秒|五十秒",
            body_text,
        ))
        if quote_frags and hammer_hit:
            joined_q = "".join(quote_frags)
            if (
                re.search(r"两分钟", joined_q)
                and not re.search(r"吐|停|连续|漱口|手", joined_q)
                and re.search(r"吐水|漱口|停手|连续", body_text)
            ):
                cons.append("收束未扣一锤（应引吐水/停手类原话）")
    if not _close_four_beat_complete(tail4):
        cons.append("末四拍不完整")
    return cons
