"""日常故事重试/修订：按本轮首要问题生成单点提示，避免堆叠全套规则。"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from app.services.daily_story.dialogue_text import DAILY_STORY_LINE_CHARS_MAX
from app.services.daily_story.prompts import (
    DAILY_STORY_BODY_CHARS_MAX,
    DAILY_STORY_BODY_CHARS_MIN,
    DAILY_STORY_RETRY_PATCH_DEFICIT_MAX,
)
from app.services.daily_story.story_types import story_line_for_code


def _parse_body_char_deficit(errors: str) -> int | None:
    m = re.search(r"还差\s*(\d+)\s*字", errors or "")
    return int(m.group(1)) if m else None


def _parse_body_char_excess(errors: str) -> int | None:
    m = re.search(r"超出\s*(\d+)\s*字", errors or "")
    return int(m.group(1)) if m else None

# 数字越小越优先（先修硬性格式，再修收束形态）
_VALIDATION_PRIORITY: tuple[tuple[re.Pattern[str], str], ...] = (
    # 跑题最优先：主题都写错时，其余项修了也白修
    (re.compile(r"正文跑题"), "theme_drift"),
    (re.compile(r"连说"), "consecutive"),
    (re.compile(rf"超过.*{DAILY_STORY_LINE_CHARS_MAX}字"), "line_too_long"),
    (re.compile(r"总字数须≤"), "body_too_long"),
    (re.compile(r"E类正文过长"), "e_body_too_long"),
    (re.compile(r"汤汁太弱|尝菜眼"), "e_weak_taste_eye"),
    # 因果顺序优先于其他挑食软伤：先立规再抓现行
    (
        re.compile(
            r"因果反了|先立「不许挑食」|先妈妈立「不许挑食」|"
            r"妈妈开场训|妈妈先训孩子",
        ),
        "e_picky_causal",
    ),
    (
        re.compile(r"挑食开场|挑食前段|挑食须|挑食妈妈|挑食禁|挑食抓|挑食正文"),
        "e_picky_theme",
    ),
    (
        re.compile(
            r"说谎主题禁|说谎开场|说谎须|说谎禁|善意谎言复读|那是开脱|"
            r"叠爸爸|语气垫字|实物反证|自套逻辑|套自己|"
            r"当场否掉|开脱句过多|重复立同一规矩",
        ),
        "e_lie_theme",
    ),
    (re.compile(r"引话须|无出处|自造后再假装引用|提前引话"), "quote_ground"),
    (re.compile(r"总字数须≥"), "body_too_short"),
    (re.compile(r"角色反了"), "role_swap"),
    # D 专属须在「勿写成 A 式末四拍」之前，避免误中 C 式赛规提示
    (re.compile(r"D类收束勿写成 A 式末四拍"), "d_not_a_close"),
    (re.compile(r"D类回旋镖须在破规动作句之后"), "d_boom_after_fix"),
    (re.compile(r"D类回旋镖须点破"), "d_boom_point"),
    (re.compile(r"D类破规须亲手违反"), "d_fix_violates"),
    (re.compile(r"D类回旋镖须原样引|D类末段须用叮嘱方原话回旋镖"), "d_boomerang"),
    (re.compile(r"D类中段须有|D类中段须演骨架"), "d_literal_mid"),
    (re.compile(r"D类前段须灿灿"), "d_rule_setup"),
    (re.compile(r"D类搞砸前禁止拆穿"), "d_spoil"),
    (re.compile(r"D类哼/算了后禁止|D类末句须灿灿嘴硬"), "d_soft_close"),
    (re.compile(r"D类正文过短|D类正文过长"), "d_line_count"),
    (re.compile(r"D类主戏姐弟|D类前段勿重复唠叨|D类后果跑偏"), "d_generic"),
    (re.compile(r"收束对白须写完整|未说完|引号"), "c_incomplete_line"),
    (re.compile(r"末段须有回旋镖|实物真相反转"), "c_boomerang"),
    (re.compile(r"末句须被戳穿方"), "c_loser_last"),
    (re.compile(r"末句须写完整或嘴硬"), "c_incomplete_last"),
    # 仅 C；D/E 已有专属条，勿用裸「勿写成 A」误伤
    (re.compile(r"C类收束勿写成 A 式末四拍"), "c_not_a_close"),
    (re.compile(r"收束末两句须换人"), "c_close_alternate"),
    (re.compile(r"无破功软收|弱收束|甩给妈妈"), "soft_close"),
    (re.compile(r"多套免责|借口复读|只能一套免责"), "a_excuse"),
    (re.compile(r"提前引话|引话"), "quote_ground"),
    (re.compile(r"注水|三十下|认真数"), "padding"),
    (re.compile(r"不好玩|吐水算停"), "hammer_beat"),
    (re.compile(r"跑题"), "off_topic"),
    (re.compile(r"C类"), "c_generic"),
    (re.compile(r"D类"), "d_generic"),
)


def split_validation_errors(errors: str) -> list[str]:
    err = (errors or "").strip()
    if err.startswith("daily_story 校验失败:"):
        err = err.removeprefix("daily_story 校验失败:").strip()
    return [p.strip() for p in err.split(";") if p.strip()]


def pick_primary_validation_errors(
    errors: str,
    *,
    max_items: int = 1,
) -> list[str]:
    """从本轮校验文案中取出最高优先的 1 条（默认只修一项）。"""
    fragments = split_validation_errors(errors)
    if not fragments:
        return []
    ranked: list[tuple[int, int, str]] = []
    for idx, frag in enumerate(fragments):
        pri = len(_VALIDATION_PRIORITY)
        for i, (pat, _) in enumerate(_VALIDATION_PRIORITY):
            if pat.search(frag):
                pri = i
                break
        ranked.append((pri, idx, frag))
    ranked.sort(key=lambda t: (t[0], t[1]))
    chosen = ranked[0][2]
    # 差几个字时若同时有引话硬伤，先修引话（句内补字可下轮再做）
    if _classify_validation_fragment(chosen) == "body_too_short":
        deficit = _parse_body_char_deficit(chosen)
        if deficit is not None and deficit <= DAILY_STORY_RETRY_PATCH_DEFICIT_MAX:
            for _, _, frag in ranked:
                if _classify_validation_fragment(frag) == "quote_ground":
                    return [frag]
    return [chosen for _, _, chosen in ranked[: max(1, max_items)]]


def _hint_body_too_short(
    err: str,
    *,
    chars: int,
    type_code: str | None = None,
) -> str:
    deficit = _parse_body_char_deficit(err)
    if deficit is not None and deficit <= DAILY_STORY_RETRY_PATCH_DEFICIT_MAX:
        if type_code == "D" and chars < 16 * 19 and deficit >= 5:
            # D 短稿（13–15 句）差一点：补模板里的「机动句」比句内抠字靠谱
            return (
                f"【D·补句】只差 {deficit} 字：现在只有约 {chars // 21} 句，"
                "在中段循环里补 1 句昭昭第 6 次歪读推进（机动句，19–21 字，"
                "带新动作/新位置，勿只换说法；插在昭昭/灿灿交替处，"
                "勿造成同人连说），其余句各补 2–4 字动作细节；"
                f"尾三拍（破规→回旋镖→嘴硬）原样不动；写到 ≥{DAILY_STORY_BODY_CHARS_MIN}。"
            )
        return (
            f"【补字·句内】只差 {deficit} 字：在中段 2–3 句各加 2–6 字抬杠语气，"
            f"禁止插入新句、禁止动末四拍；写到 ≥{DAILY_STORY_BODY_CHARS_MIN}。"
        )
    deficit_txt = f"缺 ~{deficit} 字" if deficit else "字太少"
    return (
        f"【补字·扩句】{deficit_txt}：把中段多数句各扩到 19–21 字"
        "（补当场动作/状态细节），禁止 ~11 字短句、禁止加新句、"
        "禁止用三十下/认真数/计时器注水凑字；写足 ≥280 字。"
    )


def _hint_body_too_long(err: str) -> str:
    excess = _parse_body_char_excess(err)
    if excess is not None and excess <= DAILY_STORY_RETRY_PATCH_DEFICIT_MAX:
        return (
            f"【删字·句内】只从中段 1–2 句各删几个虚词/重复，"
            f"禁止删末四拍；压到 ≤{DAILY_STORY_BODY_CHARS_MAX}。"
        )
    return (
        "【删字】只删中段车轱辘重复句 1–2 句，勿动末四拍与已立赛规。"
    )


_VALIDATION_HINT_BUILDERS: dict[str, Callable[..., str]] = {}


def _register_validation_hints() -> None:
    def consecutive(**_kw: Any) -> str:
        chars = _kw.get("chars", 0)
        type_code = _kw.get("type_code")
        if type_code == "D":
            # D 收尾拍内连说常是「灿灿反应 + 灿灿破规」两连：破规句
            # speaker 不能翻（叮嘱方亲手补救才成回旋镖），只能插一句昭昭。
            return (
                "【D·连说】同人连说（常落在收尾拍内）：破规句 speaker"
                "（灿灿亲手补救）不能改成昭昭。修法二选一："
                "① 在两句之间插入被照做方（昭昭）一句即时反应/得意台词"
                "（10–16 字，如「我系的结，牢得很！」），让 speaker 交替；"
                "② 把连说的前一句改写成昭昭视角的台词（保留原句细节词）。"
                "只许加/改这 1 句；破规句、回旋镖、末句「哼/算了」原样保留。"
            )
        return (
            "【连说】把连说拆开：交替 speaker 或合并为一人一句；"
            f"保持约 {chars} 字，勿借机大删末四拍。"
        )

    def line_too_long(**_kw: Any) -> str:
        return (
            f"【单句】超长句压到 ≤{DAILY_STORY_LINE_CHARS_MAX} 字；"
            "可拆给两人轮流说，禁止同人连说硬拆。"
        )

    def c_boomerang(**_kw: Any) -> str:
        return (
            "【C·回旋镖·只改末 4 句】"
            "倒数4=按赛规可见动作/加赛；3=对方喊不算；"
            "2=你刚说/你说的+短赛规（完整一句）；"
            "1=被规则反噬方哼/认了。前文 dialogue 其余行勿动。"
        )

    def c_loser_last(**_kw: Any) -> str:
        return (
            "【C·末句说话人】末句须「被戳穿/吃亏」方嘴硬（哼/行吧/给你），"
            "禁止赢家总结或继续立规矩；只改末 1–2 句 speaker/台词。"
        )

    def c_incomplete_line(**_kw: Any) -> str:
        return (
            "【C·完整句】收束前两句须写完整（≤24字）；"
            "回旋镖可拆成两句，禁止停在引号或未说完。"
        )

    def c_incomplete_last(**_kw: Any) -> str:
        return (
            "【C·末句】补全末句或改成哼/行吧/算了/给你等嘴硬软收。"
        )

    def c_not_a_close(**_kw: Any) -> str:
        return (
            "【C·去A化】删掉「那不一样+哪里不一样」末四拍；"
            "改成赛规回旋镖反问，只改末 4 句。"
        )

    def d_not_a_close(**_kw: Any) -> str:
        return (
            "【D·去A化】删掉「那不一样+哪里不一样」末四拍；"
            "改成末三拍：灿灿破规补救→昭昭「你自己说」+叮嘱原话"
            "+点破「怎么现在又上手…」→灿灿只哼/算了；只改末 3–4 句。"
        )

    def d_boom_after_fix(**_kw: Any) -> str:
        return (
            "【D·破规先于回旋镖】正文须有灿灿亲手补救句"
            "（我来/我自己/上手/一把/拢住…，speaker=灿灿），"
            "回旋镖点破（你自己说+原话）移到补救句之后；"
            "删掉破规前昭昭的「你也破了/你这会儿也破」类预判句。"
        )

    def d_boom_point(**_kw: Any) -> str:
        return (
            "【D·点破】回旋镖须引原话并点破她此刻的破规动作："
            "「你说别浇太多，怎么自己整壶都倒进去了」；"
            "破规须是同一条规矩的亲手违犯"
            "（说别浇太多却端起壶整壶灌回、说系紧却上手解结）；"
            "禁止只引原话就停（「是你自己说别浇太多的！」×）。"
        )

    def d_fix_violates(**_kw: Any) -> str:
        return (
            "【D·破规违规】灿灿补救句须亲手演出回旋镖引的那条规矩的违犯："
            "我/被我 + 可见动作（我一把抢过水壶哗啦全倒进花盆、"
            "上手用力拍压、我指甲抠进结里用力掰），回旋镖再点破；"
            "禁止「抢水壶/收拾/擦地」止步、禁止「你还浇」指责句冒充破规"
            "（那是说她还在浇，不是她浇）、禁止只在回旋镖里被追认。"
        )

    def d_boomerang(**_kw: Any) -> str:
        frag = _kw.get("frag") or ""
        key_txt = ""
        m = re.search(r"key_line「([^」]+)」", frag)
        if m:
            key_txt = f"逐字抄「{m.group(1)}」"
        return (
            "【D·回旋镖】倒数第 2 句须「你自己说」+"
            + (key_txt or "逐字抄前段叮嘱原话")
            + "+点破矛盾；禁改引中段催促；只改末 2–3 句。"
        )

    def d_literal_mid(**_kw: Any) -> str:
        return (
            "【D·字面执行】中段补「照做/按你说的」+可见歪读场面；"
            "同一偏读递进，禁轻轻放×N、禁辩定义。"
        )

    def d_rule_setup(**_kw: Any) -> str:
        return (
            "【D·立规】正文前段灿灿须说出可抠叮嘱（轻点/系紧/轻轻…）；"
            "裸邀约「收进箱子吧」不算；key_line 须落进前段对白。"
        )

    def d_spoil(**_kw: Any) -> str:
        return (
            "【D·禁拆穿】删搞砸前灿灿纠正（不是让你…/我是让你…）；"
            "叮嘱只说一次，让歪读跑到倒/洒再发现。"
        )

    def d_soft_close(**_kw: Any) -> str:
        type_code = _kw.get("type_code")
        soft = ""
        if type_code:
            soft = story_line_for_code(type_code).retry_soft_close_hint.strip()
        return soft or (
            "【D·收束】末句停在哼/算了，禁止哼后再发指令；"
            "倒数第 2 句昭昭引原话点破。"
        )

    def d_line_count(**_kw: Any) -> str:
        return (
            "【D·句数】正文压到 15–17 句：过短补歪读递进句，"
            "过长合并中段重复回合；立叮嘱→字面→搞砸→破规→回旋镖链勿动。"
        )

    def d_generic(**_kw: Any) -> str:
        type_code = _kw.get("type_code")
        soft = ""
        if type_code:
            soft = story_line_for_code(type_code).retry_soft_close_hint.strip()
        return soft or (
            "【D】只修校验指出的问题：立叮嘱→歪读→搞砸→破规→回旋镖；"
            "勿改写成 A/C 收束。"
        )

    def c_close_alternate(**_kw: Any) -> str:
        return "【C·收束】末两句须灿灿/昭昭交替，禁止同人连说。"

    def soft_close(**_kw: Any) -> str:
        type_code = _kw.get("type_code")
        soft = ""
        if type_code:
            soft = story_line_for_code(type_code).retry_soft_close_hint.strip()
        return soft or (
            "【收束】只改末 2–3 句：先字面戳穿，末句破功方嘴硬；"
            "禁止等妈评理/一人一半和解收场。"
        )

    def e_body_too_long(**_kw: Any) -> str:
        type_code = _kw.get("type_code")
        soft = ""
        if type_code:
            soft = story_line_for_code(type_code).retry_soft_close_hint.strip()
        base = (
            "【E·删句】只删中段同型揭穿/狡辩复读；"
            "保留妈妈立论+开脱+闭环+末句破功；禁止新增台词。"
        )
        return f"{base} {soft}" if soft else base

    def e_weak_taste_eye(**_kw: Any) -> str:
        return (
            "【E·尝菜眼】开场/前段须可拍试吃：勺上沾菜、嘴角油渍、"
            "试吃咽下；禁止「偷尝汤汁」当唯一眼，改勺子或嘴角。"
        )

    def e_picky_causal(**_kw: Any) -> str:
        return (
            "【E·挑食因果】开场须妈妈先训孩子："
            "「昭昭，你最近菜吃得太少了，不能挑食哦」→"
            "下一句孩子再抓「你怎么拨到碗边」；"
            "禁孩子先问拨开、禁孩子先开口再立规。"
        )

    def e_picky_theme(**_kw: Any) -> str:
        return (
            "【E·挑食·假开脱】妈妈开场训「不能挑食」→孩子1抓拨到碗边→"
            "孩子2假替妈解释（你不懂/放凉/大人/不算，主语用妈妈，"
            "如「妈妈会吃的，上次是意外」；禁「你别翻旧账」）→"
            "孩子1再追→孩子2继续越帮越黑→verbatim 闭环→妈妈末句破功。"
            "中段妈妈少说话；禁妈妈当真用不一样；禁回训；全文宜8–12句。"
        )

    def e_lie_theme(**_kw: Any) -> str:
        return (
            "【E·说谎】孩子问电话/奶奶场面→妈妈先立「不能说谎」→"
            "开脱善意谎言只 1 句；中段须摆可拍实物反证"
            "（锅里一粒米都没有／碗都是干的／肚子还咕咕叫／外卖盒）；"
            "末段孩子把妈妈逻辑套自己（那我跟奶奶说我考了一百分，"
            "也算善意的吧）→妈妈下一句当场否掉（那可不行，你那是骗人）"
            "→孩子扣原话→妈妈末句破功；套用对象用奶奶勿岔学校老师。"
            "妈妈开脱≤3句且同一套借口加码，禁一句一个新借口"
            "（善意/特殊情况/两码事/你们还小/不一样 轮着来最闷）；"
            "「不一样」全篇最多一次；"
            "「不能说谎」只立一次，同一质问勿换词重问。"
            "禁尝菜串场、禁那不一样、禁善意/那是复读、禁句尾呵哈垫字。"
        )

    def theme_drift(**_kw: Any) -> str:
        return (
            "【跑题重写】上一稿写的不是主题那件事：规矩词、道具、"
            "可拍现行全部改用主题原词重立，按本类型公式重写正文；"
            "禁止沿用上一稿场景，禁止照抄提示词示例（挑食/尝菜等）。"
        )

    _VALIDATION_HINT_BUILDERS.update({
        "theme_drift": theme_drift,
        "consecutive": consecutive,
        "line_too_long": line_too_long,
        "body_too_short": lambda frag, *, chars=0, type_code=None, **_kw: _hint_body_too_short(
            frag, chars=chars, type_code=type_code,
        ),
        "body_too_long": lambda frag, **_kw: _hint_body_too_long(frag),
        "e_body_too_long": e_body_too_long,
        "e_weak_taste_eye": e_weak_taste_eye,
        "e_picky_causal": e_picky_causal,
        "e_picky_theme": e_picky_theme,
        "e_lie_theme": e_lie_theme,
        "c_incomplete_line": c_incomplete_line,
        "c_boomerang": c_boomerang,
        "c_loser_last": c_loser_last,
        "c_incomplete_last": c_incomplete_last,
        "c_not_a_close": c_not_a_close,
        "d_not_a_close": d_not_a_close,
        "d_boom_after_fix": d_boom_after_fix,
        "d_boom_point": d_boom_point,
        "d_fix_violates": d_fix_violates,
        "d_boomerang": d_boomerang,
        "d_literal_mid": d_literal_mid,
        "d_rule_setup": d_rule_setup,
        "d_spoil": d_spoil,
        "d_soft_close": d_soft_close,
        "d_line_count": d_line_count,
        "d_generic": d_generic,
        "c_close_alternate": c_close_alternate,
        "soft_close": soft_close,
        "c_generic": c_boomerang,
        "off_topic": lambda **_kw: "【跑题】删掉后半无关句，回到 conflict_core。",
        "role_swap": lambda **_kw: "【角色】昭昭=弟弟、灿灿=姐姐，改正自称与立场。",
        "quote_ground": lambda **_kw: (
            "【引话·只改1–2句】引话须是前文真实子串；"
            "改埋句或改引话，禁止整篇重写。"
        ),
        "padding": lambda **_kw: (
            "【删注水】删三十下/认真数/帮你盯；用抬杠补字，只留一套免责。"
        ),
        "a_excuse": lambda **_kw: (
            "【单线借口】偷吃只留「检查不算吃」；咽下后立刻末四拍。"
        ),
        "hammer_beat": lambda **_kw: (
            "【一锤】下一来回必须示范吐水/偷停，勿只口头争论。"
        ),
    })


_register_validation_hints()


def _classify_validation_fragment(fragment: str) -> str:
    for pat, key in _VALIDATION_PRIORITY:
        if pat.search(fragment):
            return key
    return "unknown"


def build_validation_retry_hints(
    errors: str,
    *,
    chars: int,
    type_code: str | None = None,
    max_issues: int = 1,
) -> str:
    """按首要校验失败项生成 1 条修订指令（字数方向由 length_mode 另管）。"""
    primaries = pick_primary_validation_errors(errors, max_items=max_issues)
    if not primaries:
        return ""
    hints: list[str] = []
    for frag in primaries:
        key = _classify_validation_fragment(frag)
        builder = _VALIDATION_HINT_BUILDERS.get(key)
        if not builder:
            continue
        if key == "body_too_short":
            hints.append(builder(frag, chars=chars, type_code=type_code))
        elif key == "body_too_long":
            hints.append(builder(frag))
        else:
            hints.append(builder(frag=frag, chars=chars, type_code=type_code))
    if not hints:
        hints.append(
            f"【本轮】只修校验指出的问题，保持约 {chars} 字，勿整稿重写。"
        )
    return "\n".join(hints) + "\n"


# ── 观感修订：一次只推一个维度 ──

_QUALITY_CON_PRIORITY: tuple[tuple[str, str], ...] = (
    ("收束引话无出处", "quote"),
    ("同人连说", "consecutive"),
    ("B事实", "fact"),
    ("C事实", "fact"),
    ("可核对事实", "fact"),
    ("B开场", "opening"),
    ("C开场", "opening"),
    ("C收束缺可拍争法", "c_filmable"),
    ("C中段归属口水战", "c_chatter"),
    ("C收束偏A", "c_de_a"),
    ("好笑不足", "humor"),
    ("格式达标但好笑", "humor"),
    ("绕圈", "redundancy"),
    ("复读拖沓", "redundancy"),
    ("身份/把关话术", "redundancy"),
)


def pick_primary_quality_issue(
    cons: list[str],
) -> tuple[str | None, str | None]:
    """返回 (kind, matched_con_text)。"""
    for needle, kind in _QUALITY_CON_PRIORITY:
        hit = next((c for c in cons if needle in c), None)
        if hit:
            return kind, hit
    return None, None


def format_quality_consecutive_revision_hint(
    *,
    chars: int = 0,
    type_code: str | None = None,
) -> str:
    """观感分检出同人连说：指导 LLM 插接话，勿只改 speaker。"""
    _ = type_code
    budget = (
        f"保持约 {chars} 字，"
        if chars > 0
        else ""
    )
    return (
        "【连说】昭昭/灿灿须轮流说话：在连说处插入另一方短接话"
        "（如「行，我这就去拿桶」「完了完了！」），"
        "勿只改 speaker 标签；"
        f"{budget}勿动末四拍。"
    )


def revision_scope_kind(
    *,
    primary_kind: str | None,
    escalation: bool,
    closing: bool,
) -> str:
    if primary_kind in ("c_filmable", "c_chatter", "redundancy"):
        return "mid"
    if primary_kind == "consecutive":
        return "mid"
    if primary_kind in ("fact", "opening"):
        return "last4" if primary_kind == "fact" else "opening"
    if primary_kind in ("quote", "c_de_a"):
        return "last4"
    if primary_kind == "humor":
        return "mid"
    if closing and not escalation:
        return "last4"
    if escalation:
        return "mid"
    return "mid"


def format_c_dialogue_scope_hint(story: dict, scope: str) -> str:
    dialogue = story.get("dialogue")
    n = len(dialogue) if isinstance(dialogue, list) else 0
    if n < 6:
        return ""
    if scope == "last4":
        start = max(0, n - 4)
        return (
            f"【改稿范围】只改 dialogue 第 {start + 1}–{n} 行（末段收束）；"
            f"第 1–{start} 行须原样保留。"
        )
    end = max(3, n - 4)
    return (
        f"【改稿范围】只改 dialogue 第 3–{end} 行（中段交锋）；"
        "末 4 句收束逐字保留，禁止改坏回旋镖。"
    )

