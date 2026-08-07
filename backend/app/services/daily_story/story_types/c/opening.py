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
# 正向：发现争点实物/场面（含讨要式「给我X」——用户定，2026-08-08）
C_OPENING_ANCHOR_RE = re.compile(
    r"怎么|谁|凭什么|不公平|规矩|抢|弄乱|翻|叠|洒|倒|多拿|先|给我",
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
# 命令式攻击开场（先礼后兵检测，2026-08-08 用户）：未动手对峙时开场第 1 句
# 必须是愿望式（我想先挑），命令式（我先挑/我得先挑/我要挑）攻击性太强——
# 对方还没表态，没理由上来就抢，先表达想要把球抛给对方。只打「第1句命令式主张」；
# 已动手场景（占有系动词在场：拿到/抢到/在我手里）豁免（「我先拿到的！遥控器归我！」合法）。
C_OPENING_COMMAND_CLAIM_RE = re.compile(
    r"(?:我得先[^。！？]{0,8}|我先[^。！？]{0,8}|我要[^。！？]{0,4}?先[^。！？]{0,8})",
)
# 请求式开场（先礼后兵·愿望式细化，2026-08-08 用户）：「让我先X吧」「先给我X吧」
# 软绵绵的商量/求施舍，孩子争东西理直气壮不会求人——改讨要式「给我X」或愿望式
# 「我想先X」。
C_OPENING_REQUEST_RE = re.compile(
    r"让我先[^。！？]{0,8}?吧|让我先|给我先[^。！？]{0,6}?吧|先给我[^。！？]{0,8}?吧|先给我[^。！？]{0,8}",
)
# 废话状态开场（先礼后兵·愿望式细化，2026-08-08 用户）：「我还没X呢/我还没碰呢」
# 是空状态陈述——不是愿望（我想先X）也不是主张（我先拿到的），观众听完不知道
# 孩子想要什么，未动手对峙里是四不像。已动手场景失方辩解应面向「你」而非陈述自己。
C_OPENING_DEAD_STATE_RE = re.compile(
    r"我还没[^。！？]{0,8}?呢|我都还没[^。！？]{0,8}",
)
# 开场弱判据（2026-08-08 用户）：「我先看见/我先看到/我老早就看见」——看见是内心
# 事件，经不起一句「看见没用，谁拿到谁吃」。开场即主张占有权用「看见」=弱判据，
# 改「拿到/抢到」或对孩子气理由。第 2 句失方辩解也禁（不豁免）。
C_OPENING_WEAK_SEE_RE = re.compile(
    r"我(?:先|早就|老早|已经)看见|我先看到|我先瞧见",
)
# 已动手豁免信号：占有系已完成态/宣示主权
_C_OPENING_POSSESSED_RE = re.compile(
    r"拿到|抢到|在我手里|我占|抓住|攥着|到手",
)
# 换词躲（先礼后兵同物对齐，2026-08-08）：第 2 句须与第 1 句争【同一件东西】。
# 孩子抢东西不会用「清点/整理/检查/数一数」这类归类管理词，它们是 AI 生成通病——
# 「挑零件」↔「清点得我来」各说各话，观众听不出争什么。直接打「开场第 2 句出现
# 归类/管理类动词」：孩子只会说「挑/看/先拿」，不会说「清点/核对/登记」。不按剧情词表。
_C_OPENING_SWAPWORD_SUSPECT_RE = re.compile(
    r"清点|整理|检查|数一数|核对|保管|看着点|登记|归类|盘点",
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
# 缺由头检测（专家定夺，2026-08-08）：开场只说局部容器/动作（纸箱划开/零件袋/这个盒子）
# 却不说整体物件名（新玩具/新书/酸奶），观众不知道争的是什么——拆箱稿 81 分开场
# 「纸箱划开，零件袋我得先挑」死在这。只打「容器词出现且无整体物词」；
# 整体物在场（最后一瓶酸奶/那摞新书）不判。
_C_OPENING_CONTAINER_RE = re.compile(
    r"纸箱|箱子|盒|包裹|袋子|袋|包装|封条|盒盖|壳|瓶|罐|柜子|抽屉",
)
_C_OPENING_OBJECT_RE = re.compile(
    r"玩具|书|酸奶|蛋糕|糖果|巧克力|碗碟|碗筷|盘子|橡皮|遥控器|零食|冰棍|靠垫|"
    r"衣服|枕头|饼干|牙刷|拖鞋|披萨|积木|拼图|牛奶|果汁|薯片|水果|果冻|冰糕|"
    r"游戏机|台灯|水杯|水壶|电视|冰箱|水枪|发卡|娃娃|球|笔|本子|乐高|贴纸|"
    r"玩具枪|模型|点心|饼干盒|奶酪|薯条|饮料|汽水|奶茶|汉堡|披萨盒",
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
    # 2 字词优先（争点物多是 2 字：新书/拼图/酸奶/水杯），3 字词兜底。
    # 旧 bug：3 字词全排 2 字词前 + 截断 24，conflict_core+setting 一拼长
    # 3 字词就超 24，2 字实词全被挤出列表，开场明明锚定了却误报
    # 「未扣 conflict_core」。2 字优先、放宽到 40。
    result = [t for t in tokens if len(t) == 2] + [t for t in tokens if len(t) == 3]
    return result[:40]


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

    # 开场只许姐弟对说（2026-08-08 用户）：妈妈/大人在开场占一句会抢掉定场画面，
    # 妈妈裁定是正文后话。speaker 非昭昭/灿灿即扣。
    for d in opening:
        sp = str((d.get("speaker") or "") if isinstance(d, dict) else "").strip()
        if sp and sp not in ("昭昭", "灿灿"):
            cons.append("C开场说话人须仅昭昭/灿灿——妈妈/大人不出场占开场，定场画面"
                        "留给姐弟互怼，妈妈裁定是正文后话")
            pts -= 3
            break

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
    # 锚定源只用 conflict_core（争点本体，短且聚焦），不掺 setting——
    # setting 是场景描述，掺进去会稀释争点 token 占比（新书/拼图等 2 字实词
    # 被场景 3 字词淹没，锚定正确却误报「未扣 conflict_core」）。
    if pts >= 0 and core.strip():
        tokens = _conflict_anchor_tokens(core)
        anchored = bool(tokens) and any(t in joined for t in tokens)
        if not anchored and setting:
            # 兜底：争点物词只在 setting 出现（如 conflict_core 抽象成「先后」）
            s_tokens = _conflict_anchor_tokens(setting)
            anchored = bool(s_tokens) and any(t in joined for t in s_tokens)
        if not anchored and re.search(r"衣服|叠好|零食|酸奶|马桶|洗澡", core + setting) \
                and re.search(r"衣服|叠|零食|酸奶|马桶|洗澡", joined):
            anchored = True
        if tokens and not anchored:
            cons.append("C开场未扣 conflict_core")
            pts -= 2

    # 缺由头（专家定夺，2026-08-08）：容器/包装词在场但无整体物件名——
    # 「纸箱划开，零件袋我得先挑」观众不知箱里是什么，须先说整体（新玩具/新书/酸奶）
    if _C_OPENING_CONTAINER_RE.search(joined) and not _C_OPENING_OBJECT_RE.search(joined):
        cons.append("C开场缺由头：只报局部容器/动作（纸箱/零件袋），须先说整体物件"
                    "（新玩具/新书/酸奶）让观众听懂争的是什么")
        pts -= 2

    # 命令式攻击（先礼后兵，2026-08-08 用户）：未动手对峙时第 1 句须愿望式
    # （我想先挑），命令式（我先挑！/我得先挑）攻击性太强。已动手豁免。
    if not _C_OPENING_POSSESSED_RE.search(joined):
        if C_OPENING_COMMAND_CLAIM_RE.search(lines_o[0]):
            cons.append("C开场命令式攻击（我先挑/我得先挑）：未动手对峙应先礼后兵——"
                        "第1句愿望式「我想先挑」，把球抛给对方，勿上来就抢")
            pts -= 2

    # 泛用「先拿」（动作对应用途，2026-08-08 用户）：主张用「先拿/我想先拿」是泛用
    # 获取动作，没主张到使用权利——书说先看、吃的说先吃/拿走。任意句（含第2句）都
    # 禁；「先拿到」/「拿走」是占有/归属主张合法（我先拿到的/这盒我拿走）。
    if re.search(r"先拿(?!到)", joined):
        cons.append("C开场泛用「先拿」：争的是使用权利，动作要对应用途——书→先看/先读、"
                    "拼图→先拼/先玩、吃的→先吃/给我吃吧/拿走，「先拿」是获取过程不是"
                    "主张（「先拿到/拿走」才合法）")
        pts -= 2

    # 请求式（2026-08-08 用户）：愿望式只认「我想先X」，「让我先X吧」是软绵绵
    # 商量/求施舍，孩子争东西理直气壮不会求人。无论已动手与否都禁（已动手也不该
    # 求人，孩子要么宣示主权要么质问独占）。
    if C_OPENING_REQUEST_RE.search(lines_o[0]):
        cons.append("C开场请求式（让我先X吧/先给我X吧）：软绵绵的商量，孩子争东西不会"
                    "求人——改愿望式「我想先挑/我想先看」或讨要式「给我吃吧」")
        pts -= 2

    # 开场弱判据（2026-08-08 用户）：「我先看见的」是内心事件不构成占有，开场主张
    # 使用权用看见=弱判据。任意一句（第1句愿望/第2句失方辩解）都禁。
    if C_OPENING_WEAK_SEE_RE.search(joined):
        cons.append("C开场弱判据（我先看见/我先看到）：看见是内心事件，经不起「看见没用"
                    "谁拿到谁吃」——改孩子气理由（我搬回来的/我求妈妈买的）或占有系"
                    "（我先拿到的）")
        pts -= 2

    # 废话状态（2026-08-08 用户）：「我还没碰呢」空状态陈述，不是愿望不是主张，
    # 观众听完不知道孩子想要什么。扣分重，防被锚定加分盖过。
    if C_OPENING_DEAD_STATE_RE.search(lines_o[0]):
        cons.append("C开场废话状态（我还没碰呢）：不是愿望不是主张，观众不知道孩子"
                    "想要什么——改愿望式「我想先看」直说自己的愿望")
        pts -= 4

    # 换词躲（同物对齐，2026-08-08 用户）：第 1 句争「挑零件」、第 2 句回「清点/整理」
    # ——归类管理词不是孩子抢东西会说的话，各说各话。第 2 句须抢同一样东西、用词对齐。
    if len(lines_o) >= 2 and _C_OPENING_SWAPWORD_SUSPECT_RE.search(lines_o[1]):
        cons.append("C开场换词躲（挑零件↔清点/整理）：第2句用归类管理词、与第1句争点"
                    "词不一致，两人各说各话——第2句须抢同一样东西（挑零件↔挑零件）")
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
