"""标题优化提示词测试。"""

from __future__ import annotations

import pytest

from app.services.daily_story.prompts import (
    DAILY_STORY_BODY_CHARS_MAX,
    DAILY_STORY_BODY_CHARS_MIN,
    DAILY_STORY_BODY_WRITE_TARGET_MAX,
    DAILY_STORY_BODY_WRITE_TARGET_MIN,
    DAILY_STORY_LINE_CHARS_MAX,
    build_daily_story_opening_prompts,
    build_daily_story_prompts,
    build_daily_story_theme_prompts,
    stitch_daily_story_opening,
    validate_daily_story_json,
    validate_daily_story_opening,
)
from app.services.script.optimize_title import (
    CHAT_TITLE_MAX_LEN,
    build_chat_title_prompts,
    build_title_optimize_system_prompt,
    build_title_optimize_user_prompt,
    parse_title_optimize_payload,
)


def test_title_optimize_system_prompt_includes_hook_formulas():
    system = build_title_optimize_system_prompt(max_title_len=24)
    assert "误区反问" in system
    assert "反差好奇" in system
    assert "3 秒内" in system


def test_title_optimize_user_prompt_asks_for_hook():
    user = build_title_optimize_user_prompt(
        draft_title="雪崩瞬间",
        narration="哇，雪崩好快呀。",
        max_title_len=24,
    )
    assert "雪崩瞬间" in user
    assert "反常识" in user


def test_parse_title_optimize_payload():
    title = parse_title_optimize_payload({"title": "雪崩瞬间，为啥这么猛"}, max_title_len=24)
    assert title == "雪崩瞬间，为啥这么猛"


def test_chat_title_clamps_to_ten_and_includes_punchline():
    prompts = build_chat_title_prompts(
        "找橡皮",
        {
            "setting": "书桌前",
            "punchline_explain": "C类公平执念，姐姐权威被戳穿",
            "dialogue": [{"speaker": "昭昭", "line": "你藏了我的橡皮"}],
        },
        max_title_length=16,
    )
    assert f"≤{CHAT_TITLE_MAX_LEN} 字" in prompts["system"]
    assert "有娃的大人" in prompts["system"]
    assert "反差说明" in prompts["user"]
    assert "C类公平执念" in prompts["user"]
    assert "16" not in prompts["system"]


def test_daily_story_prompts_share_contract():
    theme_sys, theme_user = build_daily_story_theme_prompts(3)
    story_sys, story_user = build_daily_story_prompts("谁先洗澡")
    assert "10岁" in story_sys
    assert "10岁" in theme_user
    assert str(DAILY_STORY_BODY_CHARS_MIN) in story_sys
    assert str(DAILY_STORY_BODY_CHARS_MAX) in story_sys
    assert str(DAILY_STORY_BODY_WRITE_TARGET_MIN) in story_sys
    assert str(DAILY_STORY_BODY_WRITE_TARGET_MAX) in story_sys
    assert "压回硬卡" in story_sys or "先写够" in story_sys
    assert "发现开场" in story_sys
    assert "单冲突" in story_sys
    assert "conflict_core" in story_sys
    assert str(DAILY_STORY_LINE_CHARS_MAX) in story_sys
    assert "有娃的大人" in story_sys
    assert "权威翻车" in story_sys or "矛盾类型一览" in story_sys
    assert "谁先洗澡" in story_user
    assert "发现开场" in story_user or "系统另写" in story_user
    assert "conflict_core" in story_user
    assert "对付爸妈" not in theme_user
    assert "下雨只带了一把伞" not in theme_user
    assert "动作/实物" in theme_user

    open_sys, open_user = build_daily_story_opening_prompts(
        "谁先洗澡",
        {
            "scene_title": "洗澡",
            "setting": "浴室门口争谁先洗",
            "conflict_core": "姐弟争谁先洗澡",
            "dialogue": [
                {"speaker": "昭昭", "line": "规则是谁先到谁先洗"},
                {"speaker": "灿灿", "line": "我是姐姐我优先"},
            ],
        },
    )
    assert "发现" in open_sys
    assert "谁先洗澡" in open_user
    assert "opening" in open_sys
    assert "正例" in open_sys
    assert "反例" in open_sys
    assert "鞋带" in open_sys
    assert "本场只争这一件" in open_user


def _valid_story(*, line: str | None = None, n: int = 17) -> dict:
    # 默认 18*17=306，过正文硬卡 280–340
    if line is None:
        line = "一二三四五六七八九十一二三四五六七八"
    assert len(line) <= DAILY_STORY_LINE_CHARS_MAX
    speakers = ("昭昭", "灿灿")
    dialogue = [
        {"speaker": speakers[i % 2], "line": line} for i in range(n)
    ]
    # 前 2 句露出冲突锚点（凑满 ≤18 字，避免总字数掉线）
    openers = ("这个橡皮是我的你别抢", "新橡皮明明先是我拿到的")
    for i, opener in enumerate(openers):
        pad = max(0, DAILY_STORY_LINE_CHARS_MAX - len(opener))
        dialogue[i]["line"] = opener + ("呀" * pad)
    return {
        "scene_title": "新橡皮",
        "setting": "客厅，姐弟抢新橡皮",
        "conflict_core": "姐弟抢新橡皮",
        "dialogue": dialogue,
        "punchline_explain": "C类公平执念，姐姐规则被字面戳穿",
    }


def test_validate_daily_story_json_ok():
    story = _valid_story()
    total = sum(len(d["line"]) for d in story["dialogue"])
    assert DAILY_STORY_BODY_CHARS_MIN <= total <= DAILY_STORY_BODY_CHARS_MAX
    validate_daily_story_json(story, phase="body")
    validate_daily_story_json(story, phase="full")


def test_validate_daily_story_json_rejects_long_body_chars():
    with pytest.raises(ValueError, match="总字数须≤"):
        validate_daily_story_json(_valid_story(n=34), phase="body")


def test_validate_daily_story_json_full_skips_total_char_hard_limit():
    # 拼开场后全文不再卡总字数
    long_story = _valid_story(n=34)
    validate_daily_story_json(long_story, phase="full")


def test_validate_daily_story_json_rejects_short_body_chars():
    with pytest.raises(ValueError, match="总字数须≥"):
        validate_daily_story_json(_valid_story(n=10), phase="body")

def test_validate_daily_story_json_rejects_long_line():
    story = _valid_story()
    story["dialogue"][0]["line"] = "一" * (DAILY_STORY_LINE_CHARS_MAX + 1)
    assert len(story["dialogue"][0]["line"]) > DAILY_STORY_LINE_CHARS_MAX
    with pytest.raises(ValueError, match=f"超过{DAILY_STORY_LINE_CHARS_MAX}字"):
        validate_daily_story_json(story)


def test_validate_daily_story_json_rejects_bad_speaker():
    story = _valid_story()
    story["dialogue"][0]["speaker"] = "爸爸"
    with pytest.raises(ValueError, match="爸爸"):
        validate_daily_story_json(story)


def test_validate_daily_story_json_allows_soft_ending():
    story = _valid_story()
    # 软收前先破功
    story["dialogue"][-2]["line"] = "你说晚了我已经在了呀呀呀呀"
    story["dialogue"][-1]["line"] = "算了听姐姐的一二三四五六七八"
    validate_daily_story_json(story)


def test_validate_daily_story_json_rejects_consecutive_same_speaker():
    story = _valid_story()
    story["dialogue"][4]["speaker"] = "昭昭"
    story["dialogue"][5]["speaker"] = "昭昭"
    with pytest.raises(ValueError, match="连说"):
        validate_daily_story_json(story)


def test_validate_daily_story_json_rejects_limp_soft_close():
    from app.services.daily_story.quality import score_daily_story

    story = _valid_story()
    story["dialogue"][-1]["line"] = "好了好了给你一二三四五六七八"
    q = score_daily_story(story)
    assert q["score"] < 75 or any("软收" in r or "破功" in r for r in q["reasons"])


def test_validate_daily_story_json_rejects_weak_endings():
    story = _valid_story()
    story["dialogue"][-1]["line"] = "等妈回来评理呀呀呀呀呀呀"
    with pytest.raises(ValueError, match="弱收束"):
        validate_daily_story_json(story)

    story = _valid_story()
    story["dialogue"][-1]["line"] = "一人一半倒杯子里呀呀呀"
    with pytest.raises(ValueError, match="弱收束"):
        validate_daily_story_json(story)

    story = _valid_story()
    story["dialogue"][-1]["line"] = "反正橡皮我要用呀呀呀呀"
    with pytest.raises(ValueError, match="弱收束"):
        validate_daily_story_json(story)


def test_daily_story_prompts_require_stance_coherence():
    story_sys, story_user = build_daily_story_prompts("抱枕大战")
    assert "立场连贯" in story_sys
    assert "自相矛盾" in story_sys
    assert "软收" in story_sys
    assert "轮流" in story_sys or "连说" in story_sys
    assert "镜像" in story_sys or "对称复读" in story_sys
    assert "无破功软收" in story_sys or "先破功" in story_user
    assert "弱收束" in story_sys or "一人一半" in story_sys
    assert "等妈" in story_sys or "评理" in story_user
    assert "好吧" in story_sys or "给你" in story_user or "自相矛盾" in story_sys


def test_daily_story_prompts_keep_single_rule_and_no_mom_referee():
    story_sys, story_user = build_daily_story_prompts("抱枕大战")
    assert "判赢" in story_sys or "判平" in story_sys
    assert "一人一半" in story_sys
    assert "换裁决" in story_sys or "剪刀石头布" in story_sys
    assert "明天再战" in story_sys or "本场规则" in story_user
    assert "硬拆" in story_sys
    assert "默认可不写妈妈" in story_sys or "默认可不写" in story_user
    assert "谁也别用" not in story_sys


def test_daily_story_retry_uses_validation_char_limits_not_write_pad():
    from app.services.daily_story.prompts import (
        DAILY_STORY_BODY_CHARS_MAX,
        DAILY_STORY_BODY_CHARS_MIN,
        DAILY_STORY_BODY_WRITE_TARGET_MAX,
        DAILY_STORY_BODY_WRITE_TARGET_MIN,
        build_daily_story_retry_user,
    )

    draft_sys, draft_user = build_daily_story_prompts("争酸奶", length_mode="draft")
    assert str(DAILY_STORY_BODY_WRITE_TARGET_MIN) in draft_sys
    assert str(DAILY_STORY_BODY_WRITE_TARGET_MIN) in draft_user

    revise_sys, revise_user = build_daily_story_prompts("争酸奶", length_mode="revise")
    assert "硬卡" in revise_sys
    assert str(DAILY_STORY_BODY_WRITE_TARGET_MIN) not in revise_sys
    assert str(DAILY_STORY_BODY_WRITE_TARGET_MAX) not in revise_user
    assert str(DAILY_STORY_BODY_CHARS_MIN) in revise_user
    assert str(DAILY_STORY_BODY_CHARS_MAX) in revise_user

    expand_sys, _ = build_daily_story_prompts("争酸奶", length_mode="revise_expand")
    assert "只增不删" in expand_sys
    assert "禁止超过" in expand_sys or "禁止超" in expand_sys

    trim_sys, _ = build_daily_story_prompts("争酸奶", length_mode="revise_trim")
    assert "只删不增" in trim_sys
    assert "禁止新增台词" in trim_sys

    prev = _valid_story()
    # 人为拉长上一稿，触发缩字 hint
    prev["dialogue"] = prev["dialogue"] + [
        {"speaker": "昭昭", "line": "一二三四五六七八九十十一"},
        {"speaker": "灿灿", "line": "一二三四五六七八九十十二"},
    ] * 20
    retry_user = build_daily_story_retry_user(
        "争酸奶",
        prev_story=prev,
        errors="正文总字数须≤340",
        phase="body",
    )
    assert "字数硬卡" in retry_user
    assert "本轮问题" in retry_user
    assert "只删不增" in retry_user
    assert "禁止新增" in retry_user
    assert str(DAILY_STORY_BODY_WRITE_TARGET_MIN) not in retry_user
    assert f"≤{DAILY_STORY_BODY_CHARS_MAX}" in retry_user or "只删不增" in retry_user
    # 垂直：不复述全套首稿要求模板
    assert "请根据上述规则，生成一个昭昭和灿灿" not in retry_user

def test_validate_daily_story_json_rejects_vague_punchline():
    story = _valid_story()
    story["punchline_explain"] = "姐弟斗嘴很好笑"
    with pytest.raises(ValueError, match="类型标签"):
        validate_daily_story_json(story)


def test_validate_daily_story_json_rejects_missing_conflict_core():
    story = _valid_story()
    del story["conflict_core"]
    with pytest.raises(ValueError, match="conflict_core"):
        validate_daily_story_json(story)


def test_validate_daily_story_json_rejects_offtopic_latter():
    story = _valid_story()
    # 后 1/3 岔开体育课，且前文未出现
    story["dialogue"][-1]["line"] = "体育课你还敢告老师吗"
    with pytest.raises(ValueError, match="跑题"):
        validate_daily_story_json(story)


def test_build_daily_story_retry_user_asks_to_expand_short_draft():
    from app.services.daily_story.prompts import (
        build_daily_story_retry_user,
        resolve_daily_story_retry_length_mode,
    )

    prev = _valid_story(n=10)
    assert resolve_daily_story_retry_length_mode(prev) == "revise_expand"
    assert (
        resolve_daily_story_retry_length_mode(
            prev, errors="正文总字数须≥280，当前180（还差100字）"
        )
        == "revise_expand"
    )
    user = build_daily_story_retry_user(
        "把姐姐的鞋带系一起",
        prev_story=prev,
        errors="正文总字数须≥280，当前180（还差100字）",
    )
    assert "还差" in user
    assert "上一稿" in user
    assert "鞋带" in user
    assert "只增不删" in user
    assert "插入约" in user
    assert "本轮问题" in user
    assert "勿换主题" in user or "另开账" in user
    assert "发现开场" in user


def test_resolve_daily_story_retry_length_mode_trim_when_long():
    from app.services.daily_story.prompts import (
        build_daily_story_retry_user,
        dialogue_total_chars,
        resolve_daily_story_retry_length_mode,
    )

    prev = _valid_story()
    prev["dialogue"] = prev["dialogue"] + [
        {"speaker": "昭昭", "line": "一二三四五六七八九十十一"},
        {"speaker": "灿灿", "line": "一二三四五六七八九十十二"},
    ] * 20
    assert resolve_daily_story_retry_length_mode(prev) == "revise_trim"
    barely = _valid_story(n=21)
    total = dialogue_total_chars(barely)
    assert DAILY_STORY_BODY_CHARS_MAX < total <= DAILY_STORY_BODY_CHARS_MAX + 24
    user = build_daily_story_retry_user(
        "争酸奶",
        prev_story=barely,
        errors=f"正文总字数须≤{DAILY_STORY_BODY_CHARS_MAX}，当前{total}（超出20字）",
    )
    assert "只删约 1 句" in user
    # 字数已在区间、只修连说 → revise，且提示勿大删
    ok = _valid_story()
    assert (
        resolve_daily_story_retry_length_mode(
            ok, errors="dialogue[1:2] 昭昭 连说≥2句，须轮流说话"
        )
        == "revise"
    )
    alt = build_daily_story_retry_user(
        "争酸奶",
        prev_story=ok,
        errors="dialogue[1:2] 昭昭 连说≥2句，须轮流说话",
    )
    assert "连说" in alt
    assert "勿借机大删" in alt


def test_conflict_anchor_must_words_prefers_short_object():
    from app.services.daily_story.prompts import (
        _conflict_anchor_must_words,
        build_daily_story_opening_retry_user,
    )

    must = _conflict_anchor_must_words("昭昭vs灿灿争第一个洗澡")
    assert "洗澡" in must
    assert "一个洗澡" not in must
    user = build_daily_story_opening_retry_user(
        "谁先洗澡",
        {
            "scene_title": "谁先洗",
            "setting": "浴室门口",
            "conflict_core": "昭昭vs灿灿争第一个洗澡",
            "dialogue": [{"speaker": "昭昭", "line": "谁先到谁先洗"}],
        },
        errors="发现开场未体现 conflict_core 锚点",
    )
    assert "洗澡" in user
    assert "必须点名" in user


def test_score_daily_story_penalizes_wait_mom_ending():
    from app.services.daily_story.quality import score_daily_story

    story = _valid_story()
    story["discovery_opening"] = [{"speaker": "昭昭", "line": "咦新橡皮怎么在你手里"}]
    story["dialogue"][-1]["line"] = "等妈回来评理呀呀呀呀呀呀"
    q = score_daily_story(story)
    assert q["grade"] in ("中", "偏弱")
    assert any("妈妈" in r or "等妈" in r for r in q["reasons"])
    assert "等妈" in q["summary"] or "妈妈" in q["summary"]


def test_score_daily_story_rewards_punch_ending():
    from app.services.daily_story.quality import attach_daily_story_quality, score_daily_story

    story = _valid_story()
    story["discovery_opening"] = [{"speaker": "昭昭", "line": "咦新橡皮怎么在你手里"}]
    story["dialogue"][4]["line"] = "我说先拿到的人先选才行呀呀呀呀"
    story["dialogue"][-3]["line"] = "你自己说先拿到的人先选呀呀"
    story["dialogue"][-2]["line"] = "我没说先拿到就能一直占着呀"
    story["dialogue"][-1]["line"] = "……哼，给你一二三四五六七八"
    q = score_daily_story(story)
    assert q["score"] >= 55
    assert any("回旋镖" in r for r in q["reasons"])
    attach_daily_story_quality(story)
    assert story["quality"]["score"] >= 55


def test_stitch_daily_story_opening_dedupes_overlapping_body_start():
    body = _valid_story(n=18)  # 略长，去重后仍过全文下限
    # 正文误写了发现句，应被拼开场时丢掉
    body["dialogue"][0]["line"] = "咦这个新橡皮你怎么攥着呀"
    opening = [{"speaker": "昭昭", "line": "咦这个新橡皮你怎么攥着"}]
    story = stitch_daily_story_opening(body, opening)
    assert story["dialogue"][0]["line"] == opening[0]["line"]
    assert story["dialogue"][1]["line"] != "咦这个新橡皮你怎么攥着呀"
    assert story["discovery_opening"] == opening
    validate_daily_story_json(story, phase="full")


def test_stitch_daily_story_opening_drops_same_speaker_junction():
    body = _valid_story(n=18)
    # 正文以昭昭起句；开场末句也是昭昭 → 拼后应丢掉正文首句
    body["dialogue"][0]["speaker"] = "昭昭"
    body["dialogue"][1]["speaker"] = "灿灿"
    opening = [
        {"speaker": "灿灿", "line": "新橡皮怎么在你手里呀"},
        {"speaker": "昭昭", "line": "你干嘛抢我的橡皮呀"},
    ]
    story = stitch_daily_story_opening(body, opening)
    assert story["dialogue"][0]["speaker"] == "灿灿"
    assert story["dialogue"][1]["speaker"] == "昭昭"
    # 接缝后不应再连说
    for i in range(1, min(4, len(story["dialogue"]))):
        a = story["dialogue"][i - 1]["speaker"]
        b = story["dialogue"][i]["speaker"]
        if a in ("昭昭", "灿灿") and b in ("昭昭", "灿灿"):
            assert a != b
    validate_daily_story_json(story, phase="full")


def test_validate_daily_story_opening_rejects_consecutive_speakers():
    with pytest.raises(ValueError, match="连说"):
        validate_daily_story_opening(
            [
                {"speaker": "昭昭", "line": "新橡皮怎么在你手里"},
                {"speaker": "昭昭", "line": "你干嘛抢我的橡皮呀"},
            ],
            conflict_core="姐弟抢新橡皮",
            setting="客厅抢新橡皮",
        )


def test_validate_daily_story_opening_requires_conflict_anchor():
    with pytest.raises(ValueError, match="锚点"):
        validate_daily_story_opening(
            [{"speaker": "昭昭", "line": "你看今天天气真好呀"}],
            conflict_core="姐弟抢新橡皮",
            setting="客厅",
        )
    ok = validate_daily_story_opening(
        [{"speaker": "昭昭", "line": "咦新橡皮怎么在你手里"}],
        conflict_core="姐弟抢新橡皮",
        setting="客厅抢新橡皮",
    )
    assert len(ok) == 1

def test_validate_daily_story_opening_coerces_name_key_shorthand():
    ok = validate_daily_story_opening(
        [{"昭昭": "咦新橡皮怎么在你手里"}],
        conflict_core="姐弟抢新橡皮",
        setting="客厅抢新橡皮",
    )
    assert ok == [{"speaker": "昭昭", "line": "咦新橡皮怎么在你手里"}]


def test_daily_story_prompts_c_type_route():
    _sys, user = build_daily_story_prompts(
        "谁先洗澡",
        story_type="C类公平执念",
    )
    assert "C 公平执念" in _sys
    assert "争归属" in _sys
    assert "C类收束模板" in user
    assert "切的人先选" in user or "切的你选" in user


def test_daily_story_prompts_a_type_route():
    sys_a, user_a = build_daily_story_prompts(
        "姐姐教弟弟写作业自己写错",
        story_type="A类权威翻车",
    )
    assert "好笑" in sys_a
    assert "你刚才说" in sys_a
    assert "A 权威翻车" in sys_a
    assert "禁止写成别的类型" in sys_a
    assert "引先例" in sys_a
    assert "A类·主题锚定" in user_a
    assert "A类收束模板" in user_a
    assert "前文已出现" in user_a or "埋句" in user_a
    assert "哪里不一样" in user_a

    os_a, user_o = build_daily_story_opening_prompts(
        "姐姐教弟弟写作业自己写错",
        {
            "scene_title": "教作业",
            "setting": "书桌前",
            "conflict_core": "姐弟教作业谁说了算",
            "punchline_explain": "A类权威翻车",
            "dialogue": [
                {"speaker": "灿灿", "line": "这题我刚教过你"},
                {"speaker": "昭昭", "line": "凭什么你得听我的"},
            ],
        },
    )
    assert "A 类开场补充" in os_a
    assert "权威翻车" in user_o

    _ts, user_t = build_daily_story_theme_prompts(3, type_code="A")
    assert "只出 A 类主题" in user_t


def test_score_daily_story_a_type_punchline():
    from app.services.daily_story.quality import score_daily_story

    pad = "呀呀呀呀呀呀呀呀"
    filler = (pad + "一二三四五六七八")[:DAILY_STORY_LINE_CHARS_MAX]
    speakers = ("灿灿", "昭昭")
    openers = [
        {"speaker": "灿灿", "line": ("你得听我的我是姐姐" + pad)[:DAILY_STORY_LINE_CHARS_MAX]},
        {"speaker": "昭昭", "line": ("凭什么你也得听我的" + pad)[:DAILY_STORY_LINE_CHARS_MAX]},
        {"speaker": "灿灿", "line": ("大人也要听小孩的话妈妈说的" + pad)[:DAILY_STORY_LINE_CHARS_MAX]},
        {"speaker": "灿灿", "line": ("那不一样我是教你" + pad)[:DAILY_STORY_LINE_CHARS_MAX]},
    ]
    closers = [
        {"speaker": "昭昭", "line": ("哪里不一样都是听" + pad)[:DAILY_STORY_LINE_CHARS_MAX]},
        {"speaker": "灿灿", "line": ("上次妈妈说你也要听我的" + pad)[:DAILY_STORY_LINE_CHARS_MAX]},
        {"speaker": "昭昭", "line": ("你刚才说大人要听小孩" + pad)[:DAILY_STORY_LINE_CHARS_MAX]},
        {"speaker": "灿灿", "line": ("……哼随便你" + pad)[:DAILY_STORY_LINE_CHARS_MAX]},
    ]
    mid = [
        {"speaker": speakers[i % 2], "line": filler}
        for i in range(16 - len(openers) - len(closers))
    ]
    dialogue = openers + mid + closers
    story = {
        "scene_title": "教作业",
        "setting": "书桌前姐姐教弟弟",
        "conflict_core": "姐弟教作业谁说了算",
        "dialogue": dialogue,
        "punchline_explain": "A类权威翻车，姐姐被追问闭环戳穿",
        "discovery_opening": [{"speaker": "昭昭", "line": "姐姐你这道题写错了"}],
    }
    q = score_daily_story(story)
    assert any(
        "追问闭环" in r or "引先例" in r or "权威破功" in r or "回旋" in r
        for r in q["reasons"]
    )


def test_score_daily_story_penalizes_ungrounded_closing_quote():
    from app.services.daily_story.quality import score_daily_story

    pad = "呀呀呀呀"
    line = lambda t: (t + pad)[:DAILY_STORY_LINE_CHARS_MAX]
    dialogue = [
        {"speaker": "灿灿", "line": line("你得听我的不许玩手机")},
        {"speaker": "昭昭", "line": line("可你上次查资料玩很久")},
        {"speaker": "灿灿", "line": line("那不一样我是查学习")},
        {"speaker": "昭昭", "line": line("查资料也是看屏幕呀")},
        {"speaker": "灿灿", "line": line("我是姐姐得管你")},
        {"speaker": "昭昭", "line": line("那不公平呀")},
        {"speaker": "灿灿", "line": line("教你规矩不算玩")},
        {"speaker": "昭昭", "line": line("你刚才说大人也要听小孩的话")},
        {"speaker": "灿灿", "line": line("那不一样我是教你")},
        {"speaker": "昭昭", "line": line("哪里不一样都是听")},
        {"speaker": "灿灿", "line": line("哼随便你玩吧")},
    ]
    story = {
        "scene_title": "手机",
        "setting": "客厅玩手机",
        "conflict_core": "姐姐管昭昭玩手机",
        "dialogue": dialogue,
        "punchline_explain": "A类权威翻车",
        "discovery_opening": [{"speaker": "灿灿", "line": line("你怎么还在玩手机")}],
    }
    q = score_daily_story(story, theme="灿灿不许昭昭玩手机")
    assert q["score"] < 85
    assert any("无出处" in r for r in q["reasons"])
    assert "无出处" in q["summary"] or "模板" in q["summary"] or "公平" in q["summary"]
