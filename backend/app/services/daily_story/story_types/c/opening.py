"""C 类发现开场校验与开场质量分。"""

from __future__ import annotations

import re

from app.services.daily_story.dialogue_text import score_opening_cinematic

# 开场禁止已分胜负/已回旋镖收束
C_OPENING_RESOLVED_RE = re.compile(
    r"你输了|我赢了|算你狠|回旋镖|谁弄乱谁收拾.*你收",
)
# 勿像 A 管教、B 密谋
C_OPENING_A_RE = re.compile(
    r"那不一样|听我的|写作业|刷牙太快|检查不算",
)
C_OPENING_B_RE = re.compile(
    r"嘘|别告诉|咱俩|暗号|望风|完蛋|妈妈来了",
)
# 正向：发现争点实物/场面
C_OPENING_ANCHOR_RE = re.compile(
    r"怎么|谁|凭什么|不公平|规矩|抢|弄乱|翻|叠|洒|倒|多拿|先",
)
# 肢体嫁接倒装（硬卡，2026-08-07）：物/处所+怎么+你的肢体+也/还+动词
# ——「茶几上遥控器怎么你手也搭着」「你脚还压着」把镜头画面照搬成句，孩子不这么说话。
# 只打结构（你的肢体+也/还+动作动词），不按单篇剧情/词表。
C_OPENING_LIMB_GRAFT_RE = re.compile(
    r"你(?:手|脚|指|头|身|脸).{0,3}(?:也|还).{0,3}(?:搭|压|按|抓|碰|戳|踩|贴|放)",
)
# 镜头翻译倒装（硬卡，2026-08-07）：处所/物+怎么+你/我+(肢体)+也/还+动作
# ——「茶几上遥控器怎么你也按着」把镜头画面照搬成句（处所物开头+怎么+人也动作），
# 读着像旁白；同一画面孩子质问的是人。与 LIMB_GRAFT 互补（后者要求肢体词，
# 前者抓「你也按着」这种无肢体词的变体）。
C_OPENING_CAMERA_RE = re.compile(
    r"(?:茶几|桌上|沙发|柜|盒|架|冰箱|门口|台)[^。！？]{0,5}"
    r"(?:遥控器|蛋糕|披萨|酸奶|杯子|橡皮|靠垫|衣服|糖|饼干|遥控)[^。！？]{0,3}"
    r"怎么.{0,6}(?:你|我)(?:手|脚|指|头)?.{0,2}(?:也|还|就)",
)
# 处所物+光主张硬拼（硬卡）：以「处所词+物名」开头且后接「我先/我要」主张，
# 处所成废前缀——「电视柜前遥控器我先按到的」→ 删处所「遥控器我先按到的！」
C_OPENING_LOC_CLAIM_RE = re.compile(
    r"^(?:桌|沙发|茶几|柜|台|盒|架|门口|冰箱|浴室|窗|地上|旁边|电视柜)"
    r".{0,4}?(?:遥控器|蛋糕|披萨|酸奶|杯子|橡皮|靠垫|衣服|枕头|糖|饼干|遥控)"
    r".{0,6}?(?:我先|我手先|我先按|我先碰|我先拿|我先抢|我要|该我|归我)",
)
# 自指假惊讶（硬卡，2026-08-07 专家）：「怎么…我…（手里/拿着/抢到/按到）」——
# 争抢是故意的，夺方对自己当前状态/动作装惊讶不像孩子像演戏（「怎么在我手里」
# 「怎么我拿着了」）；惊讶只能指向对方或物。只打结构，不按剧情词表。
C_OPENING_SELF_SURPRISE_RE = re.compile(
    r"怎么.{0,5}(?:我|自己).{0,5}(?:手|拿|抢|按|着|在|这)|"
    r"(?:我|自己).{0,2}怎么.{0,5}(?:手|拿|抢|按|着|在|这)",
)
# 接触系动词当占有主张（硬卡，2026-08-07 专家）：「我先按到的」「你手也搭着」
# 「我摸到了」「我手先够到的」——占有只说占有系动词（拿到/抢到/抓到手），
# 碰/摸/搭/挨/蹭/按/压/点/够/伸/探只描述局部接触/够取不构成占有，孩子绝不会用它们
# 主张「我先…」。只打结构（主语+接触系动词+到/着/上/的），不按单篇剧情词表；
# 「你先拿到的」不中。
C_OPENING_CONTACT_CLAIM_RE = re.compile(
    r"(?:我|你)(?:手|脚|指)?(?:先|就|都|也|还|已经|早就|一)?"
    r"(?:碰|摸|搭|挨|蹭|按|压|点|够|伸|探|揽)(?:到|着|上|的)",
)
# 「按」主张占有权/按电视操作（硬卡，2026-08-07 专家四轮）：遥控器主题第一层是占有
# 冲突，开场「我按电视」「你先按到」「我按了」把按钮操作混进占有主张——按的宾语是
# 按钮、不构成占有，且主题词「按电视」只作由头。CONTACT_CLAIM 只拦「按+到/着/上/的」，
# 这条抓「按+电视/按钮/了」等按字主张。只打结构（主语+按），不按剧情词表。
C_OPENING_PRESS_RE = re.compile(
    r"(?:我|你)(?:手|脚|指)?[^。！？]{0,6}按(?:电视|按钮|遥控|屏幕|到|着|了|的|上)",
)


def append_c_opening_errors(
    normalized: list[dict],
    *,
    type_code: str | None,
    errors: list[str],
) -> None:
    code = (type_code or "").strip().upper()[:1]
    if code != "C":
        return
    for i, item in enumerate(normalized):
        line = item["line"]
        if C_OPENING_RESOLVED_RE.search(line):
            errors.append(
                f"opening[{i}] C类开场禁止已分胜负或已收束"
                "（你赢了/算你狠等），留给正文末四拍",
            )
            break
        if C_OPENING_A_RE.search(line):
            errors.append(
                f"opening[{i}] C类开场勿像A管教末四拍"
                "（那不一样/听我的等），应是发现争点",
            )
            break
        if C_OPENING_B_RE.search(line):
            errors.append(
                f"opening[{i}] C类开场勿像B密谋露馅"
                "（嘘/别告诉/完蛋等），应是争资源现场",
            )
            break
        if C_OPENING_LIMB_GRAFT_RE.search(line):
            errors.append(
                f"opening[{i}] C类肢体嫁接倒装（你手也搭着/你脚还压着）："
                "把镜头画面照搬成句，孩子质问的是人——改「你怎么+动作」（你怎么拿着"
                "不放手）",
            )
            break
        if C_OPENING_LOC_CLAIM_RE.search(line):
            errors.append(
                f"opening[{i}] C类处所物+光主张硬拼（电视柜前遥控器我先按到的）："
                "处所成废前缀——删处所改「遥控器我先按到的！」",
            )
            break
        if C_OPENING_SELF_SURPRISE_RE.search(line):
            errors.append(
                f"opening[{i}] C类自指假惊讶（怎么在我手里/怎么我拿着了）："
                "争抢是故意的，夺方不该对自己状态装惊讶——改「我先拿到的！」"
                "宣示主权，惊讶只指向对方或物",
            )
            break
        if C_OPENING_CAMERA_RE.search(line):
            errors.append(
                f"opening[{i}] C类镜头翻译倒装（茶几上遥控器怎么你也按着）："
                "处所物+怎么+人也动作把镜头画面照搬成句——已动手直接冲人，"
                "改「我先拿到的！」「你手拿开！」",
            )
            break
        if C_OPENING_CONTACT_CLAIM_RE.search(line):
            errors.append(
                f"opening[{i}] C类接触系动词当占有主张（我先按到的/我摸到了/"
                "你手也搭着）：碰/摸/搭/按只描述局部接触不构成占有，孩子占有"
                "只说「我先拿到的」「我抢到了」——改占有系动词直给",
            )
            break
        if C_OPENING_PRESS_RE.search(line):
            errors.append(
                f"opening[{i}] C类「按」主张占有权（我按电视/你先按到）："
                "按的宾语是按钮不构成占有，且主题词「按电视」只作由头——"
                "第一层冲突是占有遥控器，改「我先拿到的！」「我抢到了！」",
            )
            break


def _opening_body_overlap(a: str, b: str) -> bool:
    left = (a or "").strip()
    right = (b or "").strip()
    if not left or not right:
        return False
    if left == right or left in right or right in left:
        return True
    n = min(len(left), len(right), 8)
    return n >= 4 and left[:n] == right[:n]


def _first_body_line_after_opening(story: dict) -> str:
    opening = story.get("discovery_opening")
    dialogue = story.get("dialogue")
    if not isinstance(opening, list) or not isinstance(dialogue, list):
        return ""
    o_lines = [
        str(d.get("line") or "").strip()
        for d in opening
        if isinstance(d, dict)
    ]
    d_lines = [
        str(d.get("line") or "").strip()
        for d in dialogue
        if isinstance(d, dict)
    ]
    k = 0
    while (
        k < len(o_lines)
        and k < len(d_lines)
        and _opening_body_overlap(o_lines[k], d_lines[k])
    ):
        k += 1
    return d_lines[k] if k < len(d_lines) else ""


def _conflict_anchor_tokens(blob: str) -> list[str]:
    cleaned = re.sub(
        r"灿灿|昭昭|[，。！？\s]|vs|VS|争谁|谁该|重新",
        "",
        blob,
    )
    # 滑动窗口 2–3 字 n-gram 全量，优先 3 字词（更倾向实词）。
    # 旧版 re.findall(r"[\u4e00-\u9fff]{2,}") 贪婪匹配会把整段中文
    # 当成一个 token，导致 any(t in opening) 永远为 False
    # （如 cleaned="争同一个蓝水杯客厅…" → 一个 token，而 opening
    #  里的 "蓝水杯" 只是它的子串，不是它本身）。
    tokens: list[str] = []
    seen: set[str] = set()
    for i in range(len(cleaned)):
        for L in (2, 3):
            chunk = cleaned[i:i + L]
            if len(chunk) == L and chunk not in seen:
                seen.add(chunk)
                tokens.append(chunk)
    # 3 字词优先（更可能命中实词如"蓝水杯"），最多保留 24 个
    result = [t for t in tokens if len(t) == 3] + [t for t in tokens if len(t) == 2]
    return result[:24]


def score_opening_quality(story: dict) -> tuple[int, list[str], list[str]]:
    """开场质量：约 -6～+6，叠在结构分上。"""
    pros: list[str] = []
    cons: list[str] = []
    opening = story.get("discovery_opening")
    if not isinstance(opening, list) or not opening:
        return -5, pros, ["C开场缺失"]

    lines_o = [
        str(d.get("line") or "").strip()
        for d in opening
        if isinstance(d, dict)
    ]
    joined = "".join(lines_o)
    pts = 0

    if C_OPENING_RESOLVED_RE.search(joined):
        cons.append("C开场已像末段收束")
        pts -= 5
    elif C_OPENING_A_RE.search(joined):
        cons.append("C开场偏A管教")
        pts -= 4
    elif C_OPENING_B_RE.search(joined):
        cons.append("C开场偏B密谋")
        pts -= 4
    elif C_OPENING_ANCHOR_RE.search(joined):
        pts += 3
        pros.append("C开场锚定争点")

    core = str(story.get("conflict_core") or "")
    setting = str(story.get("setting") or "")
    anchor_blob = core + setting
    if pts >= 0 and anchor_blob.strip():
        tokens = _conflict_anchor_tokens(anchor_blob)
        anchored = bool(tokens) and any(t in joined for t in tokens)
        if not anchored and anchor_blob.strip():
            if re.search(r"衣服|叠好|零食|酸奶|马桶|洗澡", anchor_blob) and re.search(
                r"衣服|叠|零食|酸奶|马桶|洗澡", joined,
            ):
                anchored = True
        if tokens and not anchored:
            cons.append("C开场未扣 conflict_core")
            pts -= 2

    first_body = _first_body_line_after_opening(story)
    if first_body and _opening_body_overlap(lines_o[-1], first_body):
        cons.append("C开场与正文首句重复")
        pts -= 3

    cin_pts, cin_pros, cin_cons = score_opening_cinematic(lines_o)
    pts += cin_pts
    pros.extend(cin_pros)
    cons.extend(cin_cons)

    return max(-8, min(8, pts)), pros, cons


def opening_revision_hint(issue: str) -> str | None:
    if "开场" not in issue and "C开场" not in issue:
        return None
    return (
        f"【开场·C】{issue}。"
        "须 2 句正片第一镜：地点+争点物（浴室门口拖鞋、冰箱酸奶）；"
        "勿照抄正文首句；勿你赢了/算你狠/嘘别告诉/那不一样；勿单句干问。"
    )
