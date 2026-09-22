"""gold_chat ↔ daily_story 类型流水线薄适配。

类型 body / 修订 hint 经 ``story_types`` 公开桥；本模块只做：
金稿 row 字段映射、机制附录、扩写链（mech+structure）。
勿在此再造一套字母类型 patch。
"""

from __future__ import annotations

import copy
import re
from typing import Any, cast

from app.services.gold_story.types import (
    allowed_structure_types,
    catalog_entry,
    mechanism_label,
    normalize_structure_type,
)
from app.services.gold_story.structure_resolve import (
    CLOSING_MODE_AUTHORITY_PUNCHLINE,
    resolve_structure_row,
)
from app.services.daily_story.story_types import (
    STORY_TYPE_LINES,
    apply_gold_chat_body_pipeline,
    gold_chat_type_revision_hint,
)

# 结构类型默认扩写链（无 mechanism 特化时的 fallback）
_STRUCTURE_TYPE_CHAINS: dict[str, tuple[str, ...]] = {
    "A": (
        "立规/亮权威",
        "追问/顶回",
        "一锤可拍（可拍画面）",
        "埋可引用原话（全文一次）",
        "末四拍：引话→那不一样→哪里不一样→破功",
    ),
    "B": (
        "结盟/密谋",
        "走样/露馅",
        "甩锅",
        "末句仍嘴硬甩锅",
    ),
    "C": (
        "争同一资源：占有/护住争点物",
        "立赛规/双规则（每轮一句新判据）",
        "三轮升级：占有→定义→加码",
        "末四拍：可见动作→喊不算→回旋镖引原话→立规方嘴硬收场",
    ),
    "D": (
        "合理规矩",
        "歪读/字面执行",
        "跑偏",
        "叮嘱方破规",
        "执行方原话回旋镖收束",
    ),
    "E": (
        "妈妈立论/立规",
        "追问",
        "改口",
        "妈妈破功闭环",
    ),
    "F": (
        "互相威胁",
        "加码",
        "僵持/露怯",
    ),
    "G": (
        "互怼/数落 escalating",
        "真情 pivot/护短一句（同路巧合可先问去向）",
        "愣住 beat（含笑出声）",
        "暖收或嘴硬里带软（可笑散）",
    ),
    "H": (
        "冲突升级/互毁",
        "僵持/拒和",
        "第三方定责劝和（分层）",
        "仪式性和好",
    ),
    "I": (
        "争锋/互怼",
        "价值高地/标准一句",
        "灵魂拷问（不可答/不可接）",
        "对方语塞",
        "赢家嘴硬总结（无 A 式反噬）",
    ),
    "J": (
        "闹/求放行",
        "一锤/否决压住",
        "对方怂/不敢再顶",
        "家长旁观或感叹（非 A 反噬、非 H 劝和）",
    ),
    "K": (
        "互打互骂升级",
        "大人躲/叹/劝失败",
        "僵持（不和好；禁止套 H）",
    ),
    "L": (
        "争物短（勿拖成规则战）",
        "成人表演公平催让渡（给他/给她）",
        "被偏袒方拒收退让",
        "点破偏心",
        "成人语塞（禁止第二轮争夺）",
    ),
    "N": (
        "设问/考验（二选一或假设难题）",
        "离谱秒答",
        "追问为什么",
        "一本正经荒诞自洽",
        "对方愣住/接不住（禁止第二轮抬杠）",
    ),
    "O": (
        "立赛规争资源（猜拳/赢者吃等）",
        "一方死磕过程/多次赢赛",
        "资源被吃空/目标溜走",
        "赢赛方点题认栽（光顾着赢/X没了）",
        "可有低冲突反应（笑/旁观/无奈）；点题后立即停，禁止第二轮抬杠",
    ),
    "P": (
        "下料/挑战递物",
        "硬撑或自食其果",
        "回敬加码（以牙还牙）",
        "认怂散场（认输/不敢再试；可短笑散）",
    ),
    "Q": (
        "立玩法/约定",
        "孩子耍赖或借口加码",
        "被拆穿（家长或姐弟均可）",
        "赖法反噬收场",
    ),
}

# mechanism + structure 特化扩写链（优先于 _STRUCTURE_TYPE_CHAINS）
_MECH_STRUCTURE_CHAINS: dict[tuple[str, str], tuple[str, ...]] = {
    ("M1", "C"): (
        "争点物占有/护住",
        "引用对方原话堵截（回旋镖扣原话）",
        "三轮规则升级（占有→定义→加码）",
        "末四拍回旋镖收束",
    ),
    ("M2", "C"): (
        "护住/占有争点物（肉/物须可拍）",
        "堵截1：引用对方刚说过的话",
        "堵截2：搬出第三方规矩（妈妈说…）",
        "三轮升级：占有→定义→加码（勿中段车轱辘）",
        "对方语塞/败北 beat",
        "末四拍回旋镖引原话收束",
    ),
    ("M2", "L"): (
        "争物短（可拍，勿双规则拉锯）",
        "成人催让渡：表演公平（给他/给她）",
        "被偏袒方拒收退让（不想要了/你们喝吧）",
        "点破偏心（哪门子公平/向着）",
        "成人语塞；点题后禁止第二轮争夺",
    ),
    ("M3", "F"): (
        "互相威胁",
        "互呛加码",
        "僵持/露怯（无 A–E 标准收束）",
    ),
    ("M4", "G"): (
        "互怼/数落 escalating（须递进，禁复读各走各的）",
        "pivot：护短/真心一句；同路巧合可写先问去向、怕你一人、行动跟上",
        "愣住 beat（含笑出声破功，但禁旁白写「笑出声」入 line）",
        "暖收或半暖（可笑散/一起走，勿 F 僵持）；对白须可说出口，禁动作神态旁白",
    ),
    ("M5", "G"): (
        "数落/互损 escalating（翻旧账：咬人没记性/丢人，弟弟不服顶嘴）",
        "拒和/加码：立规不许再咬 + 亮旧痕/旧账（嘴硬不原谅）",
        "pivot：真心一句（你重要/舍不得/怕你疼），不提前软化",
        "愣住 beat（你说啥/……）",
        "暖收或嘴硬里带软（哼，算你识相/过来，给你揉揉）",
    ),
    ("M5", "A"): (
        "立规/拒和 escalating",
        "加码：嘴硬不原谅",
        "A 末四拍或等价收束（引话/破功）",
    ),
    ("M5", "H"): (
        "升级：抢看/占物 → 拒看/推搡（object 须可拍）",
        "双向互毁：须写清谁先弄坏谁、谁报复；「也弄坏你的」须有前文",
        "伤情：story_raw 有则可拍一句（蹭破/头破/要涂碘伏）",
        "弱势方先软：story_raw/beat 有哭腔或服软则写，**非必选**",
        "M5 角色：前文互毁/推搡锁定先动手方与受害方；"
        "服软/道歉与拒和/加码不得同一 speaker",
        "M5 角色：scene conflict 受害方须 establish 持有物，先毁物者≠受害方",
        "M5 立规：家规/规矩/规定引入（如谁先动手谁担责）",
        "M5 拒和：妈妈介入前至少 1 句嘴硬拒和（不原谅/免谈等）",
        "M5 加码：妈妈介入前再 1 句升级嘴硬（画/物弄了好久、变不回来等；与是否道歉无关）",
        "H 调解①：妈妈问「谁先动手」",
        "H 调解②：定责劝和（分层，勿一句「都错了」了事）",
        "仪式性和好：拉手/勉强松口",
        "齐声承诺：以后还打不打架 → 不打了",
        "收场：story_raw 有碘伏/涂药则写；可选妈妈一句录下来/发圈",
    ),
    ("M5", "J"): (
        "互打/求放过/试探规矩",
        "否决权/拒放行压住",
        "对方怂/不敢再顶",
        "家长旁观或感叹（非 H 劝和）",
    ),
    ("M6", "A"): (
        "成人概念童化/歪问",
        "立规/一锤",
        "埋句→末四拍反噬",
    ),
    ("M6", "N"): (
        "设问/考验（二选一或假设难题）",
        "离谱秒答（可先不解释）",
        "追问为什么",
        "一本正经荒诞自洽（童言把胡说讲圆）",
        "对方愣住/哭笑不得；禁止第二轮抬杠/立规",
    ),
    ("M13", "O"): (
        "立赛规争资源（猜拳/赢者吃等）",
        "一方死磕过程/多次赢赛",
        "资源被吃空/目标溜走",
        "赢赛方点题认栽（光顾着赢/X没了；勿带不公平/不服尾巴）",
        "可有低冲突反应；得意收束勿夹慢慢赢/再来；点题后立即停，禁止第二轮抬杠",
    ),
    ("M14", "P"): (
        "下料/挑战递物（声称好吃/无害）",
        "硬撑或自食其果",
        "回敬加码（再试试/也给你）",
        "认怂散场；禁止第二轮再开挑战拖尾",
    ),
    ("M7", "D"): (
        "合理规矩",
        "歪读字面执行",
        "跑偏",
        "叮嘱方破规→执行方回旋镖",
    ),
    ("M8", "A"): (
        "一锤可拍",
        "埋句",
        "末四拍反噬/破功",
    ),
    ("M8", "J"): (
        "闹/求放行/试探权威",
        "一锤定音威慑（镇住，不翻车）",
        "对方怂/不敢再顶",
        "家长旁观或感叹（非 A 反噬）",
    ),
    ("M9", "B"): (
        "结盟/密谋",
        "走样/露馅",
        "甩锅",
        "末句仍嘴硬",
    ),
    ("M10", "E"): (
        "妈妈立论",
        "假帮腔/讽刺",
        "追问→妈妈改口破功",
    ),
    ("M11", "I"): (
        "争锋/互怼 escalating（可含双规则拉扯）",
        "立价值标准/道德高地（须可拍一句）",
        "灵魂拷问：抛出不可答/不可接问题",
        "对方语塞/败北 beat",
        "赢家嘴硬总结（无反噬；禁 narration/meta）",
    ),
    ("M12", "K"): (
        "互打互骂升级",
        "大人躲/叹/劝失败",
        "僵持（不和好；禁止套 H）",
    ),
}

_M12_K_B_CHAIN: tuple[str, ...] = (
    "互打互骂升级（篇幅宜压短）",
    "找家长评理→挡回/不评理/立规旁观",
    "姐弟仍不服短顶嘴",
    "隔一会儿孩子自行发起恢复互动（一起走/一起玩/邀约一句）",
    "家长短句对第三方总结（不掺和/不评理），禁 H 定责仪式",
)

_M12_K_UNKNOWN_CHAIN: tuple[str, ...] = (
    "严格按 beat_chain/closing_intent 逐步落实",
    "禁止擅自补劝失败两拍或僵持尾",
    "禁止擅自写 H 式定责仪式和好",
)

# mechanism 特化 prompt 追加（保留原 gold_chat_convert 里 H/I/J/K 细节）
_MECH_HINT_APPEND: dict[tuple[str, ...], str] = {
    ("M5", "H"): (
        "\n- **M5+H**：互毁须双向且受害方须**当场动手**撕/弄坏对方画（写撕了/撕啦），"
        "禁仅口头「那我也撕」；推/扭打后**须写伤情一句**（额/头/蹭破/疼），"
        "再写昭昭哭腔道歉 → 灿灿立规 → 拒和 → 加码 → 妈妈问谁先动手；"
        "昭昭须承认先弄画/先推/先动手；"
        "先动手方与受害方分工：服软/道歉≠拒和/加码，禁止同一 speaker；"
        "scene conflict 受害方须在前 2 句 establish 持有/创作，先毁物者≠受害方；"
        "禁止「秘密画/抢看秘密」偏题，须写捣乱毁画→互毁→扭打；"
        "「还打不打架」须 closing_intent 指定角色问（常为灿灿），禁止妈妈代问；"
        "齐声「不打了」=姐弟各一句（昭昭+灿灿），勿合并舞台说明；"
        "story_raw 有碘伏/涂药须写妈妈拿碘伏收场，**禁止发朋友圈/录视频** invent；"
        "碘伏后禁止新剧情（一起画/续写承诺）；句尾禁叠「呢呢」"
    ),
    ("M3", "F"): (
        "\n- **M3+F**：互呛链须双向顶嘴/加码（你再说/试试/还…呢镜像），"
        "至少两轮升级；收束可为僵持/露怯，或 seed 有则外部打断"
        "（偷拍/镜头/闭嘴/尴尬微笑）；"
        "外部打断后**≤5句**收场：僵住/互看/小声闭嘴/干笑或一句「闹着玩呢」/"
        "茄子/快走，**禁商量应对镜头**（瞪他/摆笑脸/数三二一/满意了吧）；"
        "禁半句省略号糊弄（呵呵…你听着…/嘿嘿…好不好…）；"
        "外部打断后宜尴尬收束或装闹着玩，**禁 B 式一伙/团结表演、禁 H 式和好/别吵了**；"
        "禁 seed 外零食分物 invent（薯片等）；禁 G pivot 暖收；禁 C/A 末四拍；"
        "punchline_explain 须以「F类：」开头"
    ),
    ("M11", "I"): (
        "\n- **M11+I**：中段须写清**本稿**价值高地/标准一句"
        "（来自 object/mechanism/seed，**禁止**套用正例口号除非本稿就是该梗）；"
        "灵魂拷问须不可答/不可接，**且必须打穿宣传方借口**"
        "（如「低分怪分数/跟我无关/我宣传有理」）；"
        "优先换位/双标反问（「换你被到处说低分，乐意吗」）；"
        "若用冰箱类比，须读成堵住「跟我无关」："
        "按你这理评论别人你自己得行；**禁止**写成「谁都能评」帮宣传方开脱；"
        "语塞须可机读（说不过/哑口/我……/服了/接不上等），"
        "**禁止**语塞句后半继续辩「得比别人强才能说」；"
        "戏核家长在 beat 时，灵魂拷问/点破须由妈妈（或爸爸）说，勿并给姐弟；"
        "**角色硬锁（分数宣传稿）**：conflict/seed 标明的宣传方"
        "（常为昭昭）=唯一说「我宣传/宣扬/高分该谢低分怪分/门口喊/让都听见」的人；"
        "受害方（常为灿灿）=被说低分/抗议「你到处说/同学笑我」；"
        "禁止受害方说宣传腔，禁止宣传方说受害腔；"
        "**语塞后控场**：拷问方收束制敌；禁止受害方抢答成人辩经反转拷问结论；"
        "禁止分数互相揭短；禁止 setting 未出现的空降道具（拿桶等）；"
        "禁止「姐姐说/她说」转述在场姐弟；在场互指用你；"
        "分数口径须与 conflict/seed 一致；"
        "**篇幅前置**：争锋+拷问+语塞须写满全文≥240字；"
        "对方服软或赢家口语制敌（不乐意就别乱说/别跟我吵）落在末 1–2 句即停；"
        "**禁止**念类型标签作台词（勿说「一招制敌」「问倒」「语塞」）；"
        "**禁止**无新信息的空转复读凑句（含连说「别说了」）；"
        "禁止 A 末四拍反噬/破功；收束须现场口语"
    ),
    ("M8", "J"): (
        "\n- **M8+J**：一锤威慑须镇住对方，收束对方怂/不敢再顶；"
        "昭昭须字面写出怂退（认输/我输了/不敢再/回房间/不理你等）；"
        "**篇幅前置**：按 beat 预算扩写（扭打→立规→应战→一锤→认输），"
        f"全文≥240字（目标280–340），每句宜16–22字；"
        "禁止 1:1 扩 seed；认输后禁不服/再来/威胁；"
        "家长可旁观或感叹一句；禁止 A 末四拍反噬/破功"
    ),
    ("M5", "J"): (
        "\n- **M5+J**：否决权/拒放行压住（家规不许、不放行）；"
        "对方怂；家长可旁观或感叹；禁止写成调解和好（勿套 H），"
        "禁止 A 末四拍反噬"
    ),
    ("M12", "K", "K_B_CHILD_SELF_RESOLVE"): (
        "\n- **M12+K · k_close_mode=K_B_CHILD_SELF_RESOLVE**："
        "家长**不劝架不定责**，用规矩挡回告状/继续吃饭旁观；"
        "争吵段宜短；**末段须孩子自行恢复互动**（邀约/一起走/一起玩），"
        "笑点在打后反差；禁止「别闹快分开」劝架失败收束；"
        "禁止 H 式定责道歉拉手；妈妈末句可短总结不掺和；"
        "禁止末段堆「不理你/谁稀罕」冷战当收束"
    ),
    ("M12", "K", "K_UNKNOWN"): (
        "\n- **M12+K · k_close_mode=K_UNKNOWN**：严格按 beat_chain/closing，"
        "禁止擅自补劝失败或僵持尾；禁止擅自补 H 仪式和好"
    ),
    ("M12", "K"): (
        "\n- **M12+K · k_close_mode=K_A_PARENT_FAIL_STALEMATE**："
        "主戏是姐弟互打互骂升级；大人须**叹/劝失败**"
        "（管不了/劝不动），禁只写一句「我看着」薄旁观；"
        "收束僵持不和好；禁止套 H 定责劝和+仪式性和好；"
        "禁止套 J 求否（再求你一次/保证也没用）；"
        "压制方收束宜得意/谁怕谁，败方不服不理；"
        "**禁止**末两句对称复读「我才不理你」空喊；"
        "line 禁动作指令（按在沙发上/继续挠/吐舌头），须可说出口；"
        "若冲突/key 含挠痒逼哭：须有可说的压制点题（还不哭/继续挠）"
        "+败方破功哭腔，勿只写追跑空喊；"
        "大人劝失败宜两拍：先劝止，孩子不听，再叹管不了；"
        "点题后禁宣告「笔归我了/我赢了」结案，收束僵持；"
        "护手怕疼等反差须写成可说出口的自护娇气（如哎哟我手好疼），"
        "禁旁白「护着手/用另一只手」，亦勿写成互咬对打回应；"
        "收束宜「不理你/谁怕谁/记仇」，勿硬念「就不和好」点题；"
        "禁「警告你/今天教训你/我数三下/今天非治你不可」成人腔；"
        "「越劝越打」只可对劝架大人说，禁止对弟妹说「你越劝」；"
        "禁多句复读同一扩写尾巴（我才不怕呢/再闹我恼了等）；"
        "点题后禁再堆推/吵/吼/骂空打垫字对"
    ),
    ("M2", "C"): (
        "\n- **M2+C**：自私包装公平——用对方原话+第三方规矩双重堵截；"
        "严格按 beat_chain/dialogue_seed 顺序，禁止中段 8+ 句重复同一质问；"
        "seed 全部拍写完即收束，**禁止另起第二轮争夺**（角色分工不得反转）；"
        "点题句（scene_title/key）或 closing_intent 落实后**禁止续写**；"
        "**C 层触发词（须字面出现）**：C1 争归属（凭什么/谁先/归谁）；"
        "C2 挑战规则（你刚说/规矩）；C3 挑战权威（凭什么你/你说了算）；"
        "C4 新证据（妈妈说过）；末 5 句须含你刚说/你说的回旋镖；"
        "非整件物：三轮为「原话堵截→妈妈说过→我说了算」，勿写谁先拿到归谁；"
        "句尾语气词每句最多一个，禁了呢了呀/着呢了呀；"
        "判据/自证只用占有系（拿到/抢到/攥手里），禁碰/摸/搭/吃到当胜出词；"
        "punchline_explain 须以「C类：」开头"
    ),
    ("M2", "L"): (
        "\n- **M2+L**：表演公平被拒领点破——成人催让渡后被偏袒方拒收；"
        "赢点是退让揭穿偏心，**禁止**套 C 双规则/回旋镖/吃商收束；"
        "妈妈台词≤1；点题（我不喝了/偏心）后**禁止第二轮要/不要**；"
        "对白须可说出口，禁分镜/心理旁白；"
        "punchline_explain 须以「L类：」开头"
    ),
    ("M6", "N"): (
        "\n- **M6+N**：正经胡说——设问后离谱答，追问下用童言一本正经讲圆；"
        "赢点是荒诞自洽噎住对方，**禁止**套 C 回旋镖、A 末四拍、E 改口、I 灵魂拷问；"
        "愣住/哭笑不得后**禁止第二轮抬杠**；对白须可说出口，禁分镜旁白；"
        "punchline_explain 须以「N类：」开头"
    ),
    ("M13", "O"): (
        "\n- **M13+O**：目标错位——立赛规后一方死磕过程/赢赛，资源被吃空；"
        "赢点是「我光顾着赢、目标没了」点题认栽，**禁止**套 C 双规则回旋镖、"
        "A 末四拍、N 荒诞自洽、I 灵魂拷问；"
        "死磕宜约两轮见底，玩上瘾接着玩，**禁止**偏不信翻盘式反复加赛；"
        "点题须主角自悟，**禁止**对手先揭穿你光顾着赢；"
        "点题句须干脆认栽，**禁止**带不公平/不服申诉尾巴；"
        "资源溜走后的得意收束（嘿嘿/吃饱）**禁止**夹慢慢赢/再来续赛暗示；"
        "点题句落地后**立即收束**：最多 1–2 句低冲突反应"
        "（笑/旁观/无奈/叹气/妈妈笑场）；"
        "**禁止**点题后再写不行/真的/偏就不信/再来等第二轮抬杠；"
        "字数不够只扩中段死磕/资源溜走，**禁止**用抬杠反应句或叠语气词凑字；"
        "对白须可说出口，禁分镜旁白；"
        "punchline_explain 须以「O类：」开头"
    ),
    ("M14", "P"): (
        "\n- **M14+P**：整蛊互整——道具下料/挑战→硬撑或自食→回敬加码→认怂散场；"
        "赢点是以牙还牙后一方认输，**禁止**套 C 双规则回旋镖、F 纯口头威胁链、"
        "G 真情 pivot 暖收、A 末四拍；"
        "中段须可见道具/动作回敬升级，勿只复读互呛；"
        "**保真硬锁**：首发下料方=挑战发起人；回敬后**须由发起人认怂**"
        "（closing_intent/conflict_core 若写明认怂人，对白须一致）；"
        "**禁止**后半逆袭把认怂方颠倒；**禁止**双方抢着比谁更能吃/更能撑；"
        "key/punchline **禁止**写「回旋镖」（易误套 C）；宜写整蛊回敬/认怂；"
        "认怂后**立即收束**（最多 1–2 句笑散/分吃），禁止再开一局拖尾；"
        "句尾语气词每句最多一个，禁了呢了呀/着呢了呀；"
        "禁垫字尾巴（马上给我挪开/我才不怕呢/不许再耍赖/我偏就不信）；"
        "对白须可说出口，禁分镜旁白；"
        "punchline_explain 须以「P类：」开头"
    ),
    ("M15", "Q"): (
        "\n- **M15+Q**：耍赖翻车——立玩法→耍赖/借口加码→被拆穿→反噬收场；"
        "与 E「妈妈破功」对仗：E 是大人被绕穿，Q 是孩子被拆穿后翻车；"
        "拆穿方可家长或姐弟，**不锁家长**；"
        "**开场硬约束**：前 2–3 句须先点名玩法/约定"
        "（抽签/猜拳/轮流/几口几下/谁多谁少等可拍规则或计量单位），"
        "**禁止**首句直接「重抽/太少/逞强」起跳；"
        "**角色硬锁（单孩+家长拆双孩时尤其重要）**："
        "seed/conflict 标明的耍赖孩子=唯一耍赖方（常为灿灿）；"
        "重抽/逞强/胃小推食/借口甩锅等**第一人称耍赖句只能由耍赖方说**；"
        "新增姐弟（常为昭昭）**只拆穿/质疑**，禁止抢耍赖方借口与推食；"
        "妈妈若出场作最终裁决（洗碗等），宜点明与前面借口的因果，勿空泛「小心思」；"
        "**禁止**套 P 道具互整认怂、E 妈妈破功、H 劝和、C 双规则回旋镖；"
        "须同时有立约定+耍赖加码+他人拆穿+反噬，禁止无拆穿方的自食其果伪反噬；"
        "对白须可说出口，禁分镜旁白/动作说明入 line；"
        "禁垫字尾巴与多尾音叠堆；拆穿接话禁复读同一短句；"
        "逞强/加码后须有示弱借口再反噬；终裁须回指借口；"
        "拆穿具体事实须有前文铺垫；"
        "punchline_explain 须以「Q类：」开头"
    ),
    ("M1", "C"): (
        "\n- **M1+C**：回旋镖扣原话——收束须引正文真出现过的对方原话"
    ),
}


_RE_MAPPING_G = re.compile(r"G\s*型|G\s*类|符合\s*G")
_RE_SEED_PIVOT = re.compile(
    r"护|撑腰|重要|舍不得|在乎|心疼|真心|动你|管你|认真的|我怕",
)
_RE_SEED_SOFT = re.compile(
    r"识相|暖|嘴硬|原谅|饶|擦|药|说好了|行了|撑腰|嗯|笑",
)


def is_m8_j_domination(
    *,
    mechanism: str = "",
    structure_type: str = "",
) -> bool:
    return (
        str(mechanism or "").strip().upper() == "M8"
        and str(structure_type or "").strip().upper() == "J"
    )


def _dialogue_seed_blob(seed: list[Any] | None) -> str:
    parts: list[str] = []
    for item in seed or []:
        if not isinstance(item, dict):
            continue
        parts.append(str(item.get("intent") or item.get("beat") or ""))
    return "\n".join(parts)


def _mapping_note_suggests_g(note: str) -> bool:
    return bool(_RE_MAPPING_G.search(str(note or "")))


def _seed_suggests_g(seed: list[Any] | None) -> bool:
    blob = _dialogue_seed_blob(seed)
    if not blob.strip():
        return False
    return bool(_RE_SEED_PIVOT.search(blob) and _RE_SEED_SOFT.search(blob))


def resolve_gold_chat_structure_row(row: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """gold_chat 入口纠偏 structure_type（M2+C→M8+J、mapping_note+seed→G）。"""
    out, notes = resolve_structure_row(row)
    payload = cast(dict[str, Any], out.get("payload") or {})
    payload = copy.deepcopy(payload)
    mechanism = str(out.get("mechanism") or "").strip().upper()
    current = str(out.get("structure_type") or "").strip().upper()
    mapping_note = str(payload.get("structure_mapping_note") or "")
    seed = payload.get("dialogue_seed")
    if not isinstance(seed, list):
        seed = []

    target = "G"
    if current == target:
        out["payload"] = payload
        return out, notes
    if not _mapping_note_suggests_g(mapping_note) or not _seed_suggests_g(seed):
        out["payload"] = payload
        return out, notes
    if mechanism and target not in allowed_structure_types(mechanism):
        out["payload"] = payload
        return out, notes

    normalize_structure_type(target)
    out["structure_type"] = target
    notes.append(f"structure_type:{current}→{target}(mapping+seed)")

    sc = payload.get("scene_contract")
    if isinstance(sc, dict):
        sc = copy.deepcopy(sc)
        sc_type = str(sc.get("story_type") or "").strip().upper()
        if sc_type and sc_type != target:
            sc["story_type"] = target
            notes.append(f"scene_contract.story_type:{sc_type}→{target}")
        payload["scene_contract"] = sc
    out["payload"] = payload
    return out, notes


# M4+G 权威点题旁路扩写链（closing_mode=authority_punchline）
_M4_G_AUTHORITY_PUNCHLINE_CHAIN: tuple[str, ...] = (
    "开场立规/约好（第1句=beat0立规方；谁先完成谁得资源）",
    "一方耍手段占便宜",
    "权威不罚反将：资源+任务捆给耍手段方",
    "被反将方抗拒/辩解一句（不会/换事等，勿跳过）",
    "对方揭短/施压 → 耍手段方认怂让渡",
    "末句权威点题收束（秩序/排名宣布；勿硬塞护短擦药 pivot）",
    "对白须可说出口，禁动作神态旁白",
)

_M4_G_AUTHORITY_HINT = (
    "\n- **M4+G 权威点题旁路**：本篇 closing_mode=authority_punchline；"
    "须落实立规→反将→认怂让渡→权威点题；"
    "**开场硬约束**：第1句=beat0立规方+立规句；开场2句内完成立规；"
    "立规出现前禁止藏物/急哭/撇清/让渡/点题；"
    "急哭/找不到句与藏物撇清句 speaker 不得对调；"
    "**禁止**硬塞护短/擦药/说好了式真情 pivot 暖收（与点题收束抢戏）；"
    "妈妈可多句点题，末句落秩序宣布；对白须可说出口"
)


def type_align_chain(
    *,
    structure_type: str,
    mechanism: str = "",
    closing_mode: str = "",
    k_close_mode: str = "",
) -> tuple[str, ...]:
    """金稿对齐扩写链：mechanism+structure 特化 > 结构类型默认。"""
    st = str(structure_type or "").strip().upper()
    mech = str(mechanism or "").strip().upper()
    mode = str(closing_mode or "").strip()
    k_mode = str(k_close_mode or "").strip()
    if (
        mech == "M4"
        and st == "G"
        and mode == CLOSING_MODE_AUTHORITY_PUNCHLINE
    ):
        return _M4_G_AUTHORITY_PUNCHLINE_CHAIN
    if mech == "M12" and st == "K" and k_mode == "K_B_CHILD_SELF_RESOLVE":
        return _M12_K_B_CHAIN
    if mech == "M12" and st == "K" and k_mode == "K_UNKNOWN":
        return _M12_K_UNKNOWN_CHAIN
    if mech and st:
        chain = _MECH_STRUCTURE_CHAINS.get((mech, st))
        if chain and not (
            st == "K" and k_mode in ("K_B_CHILD_SELF_RESOLVE", "K_UNKNOWN")
        ):
            return chain
    if st == "K" and k_mode in ("K_B_CHILD_SELF_RESOLVE", "K_UNKNOWN"):
        return _M12_K_UNKNOWN_CHAIN if k_mode == "K_UNKNOWN" else _M12_K_B_CHAIN
    return _STRUCTURE_TYPE_CHAINS.get(st, ())


def structure_type_hint(
    *,
    structure_type: str,
    mechanism: str = "",
    closing_mode: str = "",
    k_close_mode: str = "",
) -> str:
    """注入 gold_chat LLM prompt：类型公式 + 成熟流水线修订 hint + 扩写链。"""
    st = str(structure_type or "").strip().upper()
    mech = str(mechanism or "").strip().upper()
    mode = str(closing_mode or "").strip()
    k_mode = str(k_close_mode or "").strip()
    if not st:
        return ""

    entry = catalog_entry(st)
    name = entry["name"] if entry else st
    mech_label = mechanism_label(mech) if mech else "?"
    header = f"【{st} {name} · 机制 {mech or '?'}（{mech_label}）】"

    parts: list[str] = [header]
    if st == "K" and k_mode == "K_B_CHILD_SELF_RESOLVE":
        parts.append(
            "- 公式：互打宜短→挡回/不评理旁观→孩子自行恢复互动"
        )
        parts.append(
            "- 收束：孩子邀约/一起走；家长短总结不掺和；禁僵持劝失败模板"
        )
    elif st == "K" and k_mode == "K_UNKNOWN":
        parts.append("- 公式：仅跟 beat_chain/closing，勿套 K-A 僵持默认")
        parts.append("- 收束：由 beat 决定，勿擅自选劝失败或僵持")
    elif entry:
        parts.append(f"- 公式：{entry['formula']}")
        parts.append(f"- 收束：{entry['closing']}")

    if mode == CLOSING_MODE_AUTHORITY_PUNCHLINE and mech == "M4" and st == "G":
        parts.append("- 旁路：closing_mode=authority_punchline（权威点题，非真情暖收）")
    elif st in STORY_TYPE_LINES:
        if st == "K" and k_mode == "K_B_CHILD_SELF_RESOLVE":
            parts.append(
                "- 收束修订：末段孩子自行恢复互动；勿大人劝架/僵持尾"
            )
            parts.append(
                "- 正文锚：争执压短→挡回→孩子邀约→家长一句不掺和"
            )
        elif st == "K" and k_mode == "K_UNKNOWN":
            parts.append("- 收束修订：勿补劝失败+僵持；严格 beat")
        else:
            type_hint = gold_chat_type_revision_hint(st)
            if type_hint:
                parts.append(type_hint)

    chain = type_align_chain(
        structure_type=st,
        mechanism=mech,
        closing_mode=mode,
        k_close_mode=k_mode,
    )
    if chain:
        parts.append("- 扩写链（逐步落实，禁止跳步）：")
        parts.extend(f"  · {step}" for step in chain)

    if mode == CLOSING_MODE_AUTHORITY_PUNCHLINE and mech == "M4" and st == "G":
        parts.append(_M4_G_AUTHORITY_HINT.strip())
    else:
        if mech == "M12" and st == "K":
            if k_mode in ("K_B_CHILD_SELF_RESOLVE", "K_UNKNOWN"):
                extra = _MECH_HINT_APPEND.get((mech, st, k_mode), "")
            else:
                extra = _MECH_HINT_APPEND.get((mech, st), "")
        else:
            extra = _MECH_HINT_APPEND.get((mech, st), "")
        if extra:
            parts.append(extra.strip())
    if k_mode and st == "K":
        parts.append(f"- k_close_mode={k_mode}（生成前锁定，勿与 beat 相反）")

    parts.append("- 详拍亦见下方「金稿对齐 checklist」与 beat_chain")
    return "\n".join(parts)


def apply_type_body_pipeline(
    chat: dict[str, Any],
    *,
    structure_type: str,
) -> tuple[dict[str, Any], list[str]]:
    """转调 daily ``apply_gold_chat_body_pipeline``（兼容旧调用名）。"""
    return apply_gold_chat_body_pipeline(chat, structure_type=structure_type)
