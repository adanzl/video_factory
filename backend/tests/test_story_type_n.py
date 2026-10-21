import json
"""N 类正经胡说：校验/观感 smoke（注册映射见 test_gold_story_types）。"""

from app.services.daily_story.quality import (
    attach_daily_story_quality,
    score_daily_story,
    structure_score_of,
)
from app.services.daily_story.story_types import patch_type_body
from app.services.daily_story.story_types.n.validate import append_n_body_errors


def test_n_body_validate_and_structure_score():
    story = {
        "story_type": "N",
        "scene_title": "香蕉救父",
        "setting": "家中客厅",
        "conflict_core": "正经胡说：假设性二选一，荒诞自洽噎住追问方",
        "key": "正经胡说",
        "punchline_explain": "N类正经胡说，荒诞自洽噎住追问方",
        "discovery_opening": [
            {"speaker": "灿灿", "line": "如果爸爸掉水里，你先吃啥？"},
            {"speaker": "昭昭", "line": "先吃香蕉。"},
        ],
        "dialogue": [
            {"speaker": "灿灿", "line": "爸爸掉水里，你先吃苹果还是香蕉？"},
            {"speaker": "昭昭", "line": "吃香蕉。"},
            {"speaker": "灿灿", "line": "为什么？"},
            {"speaker": "昭昭", "line": "因为有籽，吃了能长成树。"},
            {"speaker": "灿灿", "line": "长成树又怎样？"},
            {"speaker": "昭昭", "line": "这样就能把爸爸捞上来。"},
            {"speaker": "灿灿", "line": "那……行吧。"},
            {"speaker": "昭昭", "line": "你服了吧。"},
            {"speaker": "灿灿", "line": "接不住了，算了。"},
            {"speaker": "昭昭", "line": "我说得通吧。"},
        ],
    }
    errors: list[str] = []
    append_n_body_errors(story, errors)
    assert errors == []

    notes = patch_type_body(story)
    assert isinstance(notes, list)

    attach_daily_story_quality(story, theme="正经胡说")
    q = story["quality"]
    assert q["structure_score"] >= 60
    assert any(
        "自洽" in r or "愣住" in r or "设问" in r for r in q.get("reasons") or []
    )


def test_n_stun_close_not_double_penalized_as_limp_soft():
    """N 类末段愣住已落位时，末句软尾勿再扣「无破功软收」。"""
    dialogue = [
        {"speaker": "灿灿", "line": "爸爸一百岁还是一千岁？"},
        {"speaker": "昭昭", "line": "一千四！"},
        {"speaker": "灿灿", "line": "为什么？"},
        {"speaker": "昭昭", "line": "因为吃血就能补回来呀。"},
        {"speaker": "灿灿", "line": "那爸爸掉河里呢？"},
        {"speaker": "昭昭", "line": "先吃香蕉有籽长成树。"},
        {"speaker": "灿灿", "line": "长成树又怎样？"},
        {"speaker": "昭昭", "line": "这样就能把爸爸捞上来。"},
        {"speaker": "灿灿", "line": "你这歪理也太绝了。"},
        {"speaker": "昭昭", "line": "我说得通吧。"},
        {"speaker": "灿灿", "line": "那……我说不过你。"},
        {"speaker": "昭昭", "line": "给你吧。"},
    ]
    story = {
        "story_type": "N",
        "punchline_explain": "N类正经胡说",
        "dialogue": dialogue,
    }
    quality = score_daily_story(story)
    reasons = quality.get("reasons") or []
    assert not any("无破功软收" in str(r) for r in reasons)
    assert any("愣住收束" in str(r) for r in reasons)
    assert structure_score_of(quality) >= 70


def test_n_mid_stun_then_soft_tail_still_penalizes_limp_close():
    """中段愣住、后又续写软收：末段仍按无破功软收扣分。"""
    dialogue = [
        {"speaker": "灿灿", "line": "爸爸一百岁还是一千岁？"},
        {"speaker": "昭昭", "line": "一千四！"},
        {"speaker": "灿灿", "line": "为什么？"},
        {"speaker": "昭昭", "line": "因为吃血就能补回来呀。"},
        {"speaker": "灿灿", "line": "那……行吧。"},
        {"speaker": "昭昭", "line": "还没完，掉河里呢？"},
        {"speaker": "灿灿", "line": "你继续编。"},
        {"speaker": "昭昭", "line": "先吃香蕉有籽长成树。"},
        {"speaker": "灿灿", "line": "然后呢？"},
        {"speaker": "昭昭", "line": "树长好就捞人。"},
        {"speaker": "灿灿", "line": "我听不懂了。"},
        {"speaker": "昭昭", "line": "给你。"},
    ]
    story = {
        "story_type": "N",
        "punchline_explain": "N类正经胡说",
        "dialogue": dialogue,
    }
    quality = score_daily_story(story)
    reasons = quality.get("reasons") or []
    assert any("无破功软收" in str(r) for r in reasons)
    assert not any("类型收束软尾（已达标）" in str(r) for r in reasons)


def test_n_stun_close_only_counts_closing_window():
    """收束判据唯一：中段追问里的语气词不算愣住，末四句才算。"""
    from app.services.daily_story.story_types.n.validate import stun_close_hit

    mid_only = [
        "行吧，那苹果呢？",
        "他们都在街上工作，别人给钱。",
        "行，以后我说话得先打草稿。",
    ]
    assert not stun_close_hit(mid_only), "中段/疑问句里的「行吧」不算收束"

    closing = [
        "他们收钱是因为要买苹果吃。",
        "突然蹦出个英文词，叫 banana。",
        "行吧，你俩这接龙我接不住。",
    ]
    assert stun_close_hit(closing)


def test_n_cross_check_quality_and_humor_agree_on_stun():
    """同一稿结构维与好笑维的愣住判词不得一有一无（#87 判词矛盾回归）。"""
    from app.services.daily_story.story_types.n.humor import (
        collect_n_humor_issues,
        score_funniness_tail,
    )
    from app.services.daily_story.story_types.n.quality import score_punchline

    lines = [
        "从今天起你说的每句话我都记下来，看你骗不骗人。",
        "没有，我要找个好人来，叫张三李四王五吧。",
        "完了完了，那赵六钱七孙八呢？",
        "他们都在街上工作，别人给钱就帮忙干活呢。",
        "行，那谁给钱呀？你倒是说清楚啊。",
        "他们收钱是因为要买苹果吃，很正经的呀。",
        "行吧，那苹果呢？你拿出来看看呀。",
        "突然蹦出个英文词，叫 banana，就是苹果吧。",
        "你再说一遍，banana 是什么？为什么叫这个？",
        "没人教，我自己想的，苹果就是 banana呢。",
        "你还真是照这个道理认真想的？",
        "当然，我刚才就是这么认真回答的。",
        "哈哈哈昭昭你太厉害了，我眼泪都笑出来了。",
        "行，以后我说话得先打草稿。",
    ]
    _bonus, punch_details = score_punchline(lines, ["妈妈"] * len(lines), "", lines[-1])
    _pts, humor_pros = score_funniness_tail(lines)
    issues = collect_n_humor_issues(lines)

    assert "愣住收束" not in punch_details
    assert "缺愣住落点" in punch_details
    assert "愣住收束" not in humor_pros, "好笑维不得再把中段「行吧」当收束"
    assert "N缺愣住收束" in issues
    assert not any("愣住" in x and "缺" not in x for x in humor_pros)


def test_consecutive_sibling_always_penalized():
    """孩子连说一律扣分：戏份靠两个孩子交替解决，不做额度豁免。"""
    from app.services.daily_story.quality import score_daily_story

    dlg = [
        {"speaker": "妈妈", "line": "我拿本子记你说的每句话，看你会不会骗人。"},
        {"speaker": "昭昭", "line": "我要找个好人来，他叫张小明。"},
        {"speaker": "昭昭", "line": "还有李小红、王大力、赵小刚。"},
        {"speaker": "妈妈", "line": "什么意思？谁教你的？"},
        {"speaker": "昭昭", "line": "因为好人多，所以得先找。"},
        {"speaker": "昭昭", "line": "不给就换个地方站，总有人给。"},
        {"speaker": "妈妈", "line": "行吧，我服了，以后说话得先打草稿。"},
    ]
    base = {
        "story_type": "N",
        "punchline_explain": "N类正经胡说",
        "conflict_core": "妈妈记录昭昭的话",
        "dialogue": dlg,
    }
    # 即便给出家长额度上下文（旧豁免条件成立），也必须扣分
    capped = dict(base)
    capped["_gold_chat_mom_lines_max"] = 3
    for story in (base, capped):
        q = score_daily_story(dict(story))
        assert any(
            "同人连说" in str(c) for c in q.get("structure_cons") or []
        ), "孩子连说必须扣分"

    # 交替写法不扣这一项
    alt = json.loads(json.dumps(base))
    alt["dialogue"][2]["speaker"] = "灿灿"
    alt["dialogue"][5]["speaker"] = "灿灿"
    q_alt = score_daily_story(alt)
    assert not any(
        "同人连说" in str(c) for c in q_alt.get("structure_cons") or []
    )


def test_non_n_single_child_run_is_not_sibling_alternation():
    """非 N 单孩叙事允许连续陈述；两个孩子都参与时才判同人连说。"""
    from app.services.daily_story.quality import _has_consecutive_sibling

    single = [
        {"speaker": "妈妈", "line": "衣服怎么又弄脏了？"},
        {"speaker": "昭昭", "line": "我又不是故意的。"},
        {"speaker": "昭昭", "line": "可我是想帮你才弄到的呀。"},
        {"speaker": "妈妈", "line": "那你好好说。"},
    ]
    assert not _has_consecutive_sibling(single, story_type="I")

    witness = [
        {"speaker": "妈妈", "line": "衣服怎么又弄脏了？"},
        {"speaker": "昭昭", "line": "我又不是故意的。"},
        {"speaker": "灿灿", "line": "我听见了。"},
        {"speaker": "昭昭", "line": "可我是想帮你才弄到的呀。"},
        {"speaker": "昭昭", "line": "你干嘛还骂我傻？"},
    ]
    assert not _has_consecutive_sibling(witness, story_type="I")

    dual = [
        {"speaker": "妈妈", "line": "你们俩别吵。"},
        {"speaker": "昭昭", "line": "是他先抢的。"},
        {"speaker": "昭昭", "line": "我根本没碰他的东西。"},
        {"speaker": "灿灿", "line": "你明明拿了。"},
        {"speaker": "妈妈", "line": "都少说一句。"},
        {"speaker": "灿灿", "line": "他刚才还推我。"},
    ]
    assert _has_consecutive_sibling(dual, story_type="I")


def test_n_token_premise_exemption_is_narrow():
    """N 类怪词/补词属机制，不算缺前提；其它缺前提照旧硬拦。"""
    from app.services.daily_story.review import _n_type_token_premise_exempt

    chain = [
        {"beat": 1, "speaker": "妈妈", "intent": "立规"},
        {"beat": 2, "speaker": "昭昭", "intent": "报出一串编的名字"},
        {"beat": 3, "speaker": "妈妈", "intent": "追问哪个好人"},
        {"beat": 4, "speaker": "昭昭", "intent": "给好人下定义"},
        {"beat": 5, "speaker": "妈妈", "intent": "追问谁教的"},
        {"beat": 6, "speaker": "昭昭", "intent": "蹦出一个自造词「哇卡」"},
        {"beat": 7, "speaker": "妈妈", "intent": "追问什么意思"},
        {"beat": 8, "speaker": "妈妈", "intent": "服了收束"},
    ]
    story = {
        "story_type": "N",
        "gold_beat_chain": chain,
        "dialogue": [
            {"speaker": "妈妈", "line": "我要记下你说的每句话。"},
            {"speaker": "昭昭", "line": "我要找个好人来。"},
            {"speaker": "妈妈", "line": "哪个好人。"},
            {"speaker": "昭昭", "line": "就是会给我钱的那种。"},
            {"speaker": "妈妈", "line": "谁教你的。"},
            {"speaker": "昭昭", "line": "哇卡。"},
            {"speaker": "妈妈", "line": "什么意思？"},
            {"speaker": "妈妈", "line": "行吧我服了。"},
        ],
    }
    # 豁免：怪词句 + 缺前提（机制要求突然，本来没有前因）
    assert _n_type_token_premise_exempt(
        {"kind": "缺前提", "lines": [6], "desc": "第6句突然蹦出「哇卡」"}, story
    )
    # 豁免：把补词与其后续拍一起点名的整条
    assert _n_type_token_premise_exempt(
        {"kind": "缺前提", "lines": [6, 7], "desc": "苹果线"}, story
    )
    # 不豁免：远离补词的普通句
    assert not _n_type_token_premise_exempt(
        {"kind": "缺前提", "lines": [1], "desc": "第1句突然冒出好人"}, story
    )
    # 不豁免：人物类缺前提
    assert not _n_type_token_premise_exempt(
        {"kind": "缺前提", "lines": [6], "desc": "前文没交代这个人物"}, story
    )
    # 不豁免：其它 kind
    assert not _n_type_token_premise_exempt(
        {"kind": "重复", "lines": [6], "desc": "重复"}, story
    )
    # 不豁免：非 N 类
    other = dict(story)
    other["story_type"] = "C"
    assert not _n_type_token_premise_exempt(
        {"kind": "缺前提", "lines": [6], "desc": "x"}, other
    )

