"""标题优化提示词测试。"""

from __future__ import annotations

import pytest

from app.services.daily_story.prompts import (
    DAILY_STORY_BODY_CHARS_MAX,
    DAILY_STORY_BODY_CHARS_MIN,
    DAILY_STORY_BODY_WRITE_TARGET_MAX,
    DAILY_STORY_BODY_WRITE_TARGET_MIN,
    DAILY_STORY_LINE_CHARS_MAX,
    _patch_vocative_punctuation,
    build_daily_story_opening_prompts,
    build_daily_story_prompts,
    build_daily_story_theme_prompts,
    stitch_daily_story_opening,
    sync_discovery_opening_from_dialogue,
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
    assert (
        "压回硬卡" in story_sys
        or "先写够" in story_sys
        or "直接落在硬卡" in story_sys
        or "禁止先写爆" in story_sys
    )
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


def _pad_line(text: str) -> str:
    pad = max(0, DAILY_STORY_LINE_CHARS_MAX - len(text))
    return text + ("呀" * pad)


def _apply_c_type_closing(dialogue: list[dict]) -> None:
    """C 类测试稿：末 4 句满足回旋镖 + 嘴硬收束，且与前一说话人交替。"""
    if len(dialogue) < 8:
        return
    prev_sp = str(dialogue[-5].get("speaker") or "").strip()
    if prev_sp == "昭昭":
        speakers = ("灿灿", "昭昭", "灿灿", "昭昭")
    elif prev_sp == "灿灿":
        speakers = ("昭昭", "灿灿", "昭昭", "灿灿")
    else:
        speakers = ("昭昭", "灿灿", "昭昭", "灿灿")
    lines_text = (
        "你自己说先拿的人先选呀",
        "我没说大的都得给你呀",
        "等等那你说先选啥意思",
        "……哼给你吧",
    )
    for i, (sp, ln) in enumerate(zip(speakers, lines_text, strict=True)):
        dialogue[-(4 - i)] = {"speaker": sp, "line": _pad_line(ln)}


def _valid_story(*, line: str | None = None, n: int = 17) -> dict:
    # 默认 18*17=306，过正文硬卡 280–370
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
    if len(dialogue) > 10:
        dialogue[8]["line"] = _pad_line("我们说定先拿的人先选呀")
    _apply_c_type_closing(dialogue)
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


def test_validate_daily_story_json_rejects_inverted_vocative():
    story = _valid_story()
    story["dialogue"][3]["line"] = "你刚才还笑出声了呢妈妈你听听"
    with pytest.raises(ValueError, match="语序不自然"):
        validate_daily_story_json(story)


def test_validate_daily_story_json_rejects_trailing_listen_command():
    story = _valid_story()
    story["dialogue"][3]["line"] = "大人工作需要，跟你们玩不一样啊听着"
    with pytest.raises(ValueError, match="语序不自然"):
        validate_daily_story_json(story)


def test_validate_daily_story_json_allows_natural_vocative_end():
    # 句尾单喊「妈」是正常口语
    story = _valid_story()
    story["dialogue"][3]["line"] = "我隔着门都听见短视频声音了啊妈"
    validate_daily_story_json(story)


def test_validate_daily_story_json_allows_natural_vocative_start():
    # 称呼放句首是正常口语
    story = _valid_story()
    story["dialogue"][3]["line"] = "妈妈，你刚才还笑出声了呢"
    validate_daily_story_json(story)


def test_validate_daily_story_json_allows_evidence_after_vocative():
    # 「呢你看妈」中称呼在证据词之后，属于正常口语
    story = _valid_story()
    story["dialogue"][3]["line"] = "你拇指还在屏幕上滑个不停呢你看妈"
    validate_daily_story_json(story)


def test_patch_vocative_punctuation_does_not_add_trailing_comma():
    # 不强制在句尾称呼前加逗号，避免句句尾都带标点
    story = _valid_story()
    story["dialogue"][0]["line"] = "那你被子里手机屏幕怎么还亮着呀妈"
    story["dialogue"][1]["line"] = "刷到第九个视频还叫工作需要吗妈妈"
    notes = _patch_vocative_punctuation(story)
    assert not notes
    assert story["dialogue"][0]["line"] == "那你被子里手机屏幕怎么还亮着呀妈"
    assert story["dialogue"][1]["line"] == "刷到第九个视频还叫工作需要吗妈妈"


def test_patch_vocative_punctuation_strips_trailing_listen():
    story = _valid_story()
    story["dialogue"][0]["line"] = "我回工作消息，不是玩手机啊孩子们听着"
    notes = _patch_vocative_punctuation(story)
    assert "去句尾听着[0]" in notes
    assert story["dialogue"][0]["line"] == "我回工作消息，不是玩手机啊孩子们"


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
        errors=f"正文总字数须≤{DAILY_STORY_BODY_CHARS_MAX}",
        phase="body",
    )
    assert "字数硬卡" in retry_user
    assert "本轮问题" in retry_user
    assert "只删不增" in retry_user
    assert "禁止新增" in retry_user
    # 重试勿带回首稿「先写爆/铺回合」话术
    assert "先写爆" not in retry_user
    assert "铺回合" not in retry_user
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


def test_retry_small_deficit_uses_patch_not_expand():
    """只差几个字应句内微调，勿按偏短插入多句。"""
    from app.services.daily_story.prompts import (
        build_daily_story_prompts,
        build_daily_story_retry_user,
        resolve_daily_story_retry_length_mode,
    )

    prev = _valid_story(n=18)
    err = "正文总字数须≥280，当前274（还差6字）"
    assert resolve_daily_story_retry_length_mode(prev, errors=err) == "revise_patch"
    patch_sys, _ = build_daily_story_prompts("饭前偷吃", length_mode="revise_patch")
    assert "微调" in patch_sys or "句内" in patch_sys
    user = build_daily_story_retry_user(
        "灿灿不许昭昭饭前偷吃自己却先捏了一块",
        prev_story=prev,
        errors=err,
    )
    assert "句内补" in user
    assert "禁止增删句数" in user or "禁止插入新句" in user
    assert "插入约" not in user
    quote_err = (
        "正文总字数须≥280，当前274（还差6字）；"
        "A类引话须出自灿灿前文原话（无「检查不算吃」），禁止昭昭自造后再假装引用"
    )
    assert (
        resolve_daily_story_retry_length_mode(prev, errors=quote_err)
        == "revise_patch"
    )
    quote_user = build_daily_story_retry_user(
        "灿灿不许昭昭饭前偷吃自己却先捏了一块",
        prev_story=prev,
        errors=quote_err,
        story_type="A",
    )
    assert "引话" in quote_user
    assert "只改1–2句" in quote_user or "1–2句" in quote_user


def test_local_patch_pads_small_char_deficit():
    from app.services.daily_story.prompts import (
        dialogue_total_chars,
        try_local_patch_daily_story_body,
        validate_daily_story_json,
    )

    story = _valid_story(n=18)
    target = 268  # 还差 12，落在本地补字窗口
    while dialogue_total_chars(story) > target:
        progressed = False
        for d in story["dialogue"][2:-4]:
            line = d["line"]
            if len(line) <= 8:
                continue
            d["line"] = line[:-1]
            progressed = True
            if dialogue_total_chars(story) <= target:
                break
        if not progressed:
            break
    before = dialogue_total_chars(story)
    assert 280 - 32 <= before < 280
    patched, notes = try_local_patch_daily_story_body(story)
    after = dialogue_total_chars(patched)
    assert notes
    assert after >= before
    if after >= 280:
        validate_daily_story_json(patched, phase="body")


def test_local_patch_strips_a_steal_try_taste():
    from app.services.daily_story.prompts import try_local_patch_daily_story_body
    from app.services.daily_story.quality import score_daily_story

    speakers = ("昭昭", "灿灿")
    line = "一二三四五六七八九十一二三四五六"
    dlg = [
        {"speaker": speakers[i % 2], "line": line} for i in range(20)
    ]
    dlg[0]["line"] = "水果盘怎么少了一块呀呀呀"
    dlg[1]["line"] = "饭前不许偷吃你别瞎说呀呀"
    dlg[9] = {"speaker": "灿灿", "line": "这是样品，我咬了一口测试甜不甜"}
    dlg[11] = {"speaker": "灿灿", "line": "检查不算吃，咽了才算检"}
    dlg[13] = {"speaker": "灿灿", "line": "嗯，为了确认味道，只好咽了"}
    dlg[-4] = {"speaker": "昭昭", "line": "你刚才说检查不算吃"}
    dlg[-3] = {"speaker": "灿灿", "line": "那不一样，检样不算开饭"}
    dlg[-2] = {"speaker": "昭昭", "line": "哪里不一样？都进肚子了"}
    dlg[-1] = {"speaker": "灿灿", "line": "……行吧，给你一块"}
    story = {
        "scene_title": "饭前检查",
        "setting": "厨房案板旁",
        "conflict_core": "灿灿不许昭昭饭前偷吃自己却先捏",
        "dialogue": dlg,
        "punchline_explain": "A类权威翻车：检查不算吃",
    }
    before = score_daily_story(story, theme=story["conflict_core"])
    assert any("叠" in r or "多套" in r for r in (before.get("reasons") or []))
    patched, notes = try_local_patch_daily_story_body(story)
    assert any("去试尝" in n for n in notes)
    blob = "".join(d["line"] for d in patched["dialogue"])
    assert "甜不甜" not in blob
    assert "确认味道" not in blob
    after = score_daily_story(patched, theme=story["conflict_core"])
    assert not any("叠" in r or "多套" in r for r in (after.get("reasons") or []))


def test_local_patch_aligns_a_closing_quote():
    from app.services.daily_story.prompts import (
        try_local_patch_daily_story_body,
        validate_daily_story_json,
    )

    speakers = ("昭昭", "灿灿")
    line = "一二三四五六七八九十一二三四五六"
    dlg = [
        {"speaker": speakers[i % 2], "line": line} for i in range(22)
    ]
    dlg[0]["line"] = "水果盘怎么少了一块呀呀呀"
    dlg[1]["line"] = "饭前不许偷吃你别瞎说呀呀"
    # 埋句落在灿灿位（奇数）
    dlg[11] = {"speaker": "灿灿", "line": "检查样品不算偷吃呀"}
    dlg[-4] = {"speaker": "昭昭", "line": "你刚才说咽了才算检完"}
    dlg[-3] = {"speaker": "灿灿", "line": "那不一样，检样不算开饭"}
    dlg[-2] = {"speaker": "昭昭", "line": "哪里不一样？都进肚子了"}
    dlg[-1] = {"speaker": "灿灿", "line": "……行吧，给你一块"}
    story = {
        "scene_title": "饭前检查",
        "setting": "厨房案板旁",
        "conflict_core": "灿灿不许昭昭饭前偷吃自己却先捏",
        "dialogue": dlg,
        "punchline_explain": "A类权威翻车：检查不算吃",
    }
    patched, notes = try_local_patch_daily_story_body(story)
    assert any("引话" in n for n in notes)
    quote_line = patched["dialogue"][-4]["line"]
    assert "咽了才算" not in quote_line
    assert "检查" in quote_line or "不算" in quote_line
    validate_daily_story_json(patched, phase="body")


def test_draft_write_target_aligned_with_hard_card():
    from app.services.daily_story.prompts import (
        DAILY_STORY_BODY_CHARS_MAX,
        DAILY_STORY_BODY_WRITE_TARGET_MAX,
        DAILY_STORY_BODY_WRITE_TARGET_MIN,
        build_daily_story_prompts,
    )

    assert DAILY_STORY_BODY_WRITE_TARGET_MIN >= 280
    assert DAILY_STORY_BODY_WRITE_TARGET_MAX <= DAILY_STORY_BODY_CHARS_MAX
    sys, _ = build_daily_story_prompts("刷牙", length_mode="draft")
    assert "先写爆" in sys or "直接落在硬卡" in sys or "勿先写" in sys


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
    barely = _valid_story()
    barely["dialogue"] = barely["dialogue"] + [
        {"speaker": "昭昭", "line": "一二三四五六七八九十十一"},
        {"speaker": "灿灿", "line": "一二三四五六七八九十十二"},
    ] * 2
    total = dialogue_total_chars(barely)
    assert DAILY_STORY_BODY_CHARS_MAX < total <= DAILY_STORY_BODY_CHARS_MAX + 24
    user = build_daily_story_retry_user(
        "争酸奶",
        prev_story=barely,
        errors=f"正文总字数须≤{DAILY_STORY_BODY_CHARS_MAX}，当前{total}（超出20字）",
    )
    assert "句内删" in user
    assert resolve_daily_story_retry_length_mode(
        barely,
        errors=f"正文总字数须≤{DAILY_STORY_BODY_CHARS_MAX}，当前{total}（超出20字）",
    ) == "revise_patch"
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


def test_validate_rejects_conflicting_clock_start_anchors():
    from app.services.daily_story.prompts import _parse_cn_clock_token

    assert _parse_cn_clock_token("八点零五") == 8 * 60 + 5
    assert _parse_cn_clock_token("八点十五") == 8 * 60 + 15
    assert _parse_cn_clock_token("八点十二") == 8 * 60 + 12

    story = _valid_story(n=20)
    story["punchline_explain"] = "A类权威翻车，灿灿计时双标被追问"
    story["dialogue"][0]["line"] = "你八点零五就拿手机了呀呀呀呀呀呀呀呀呀"
    story["dialogue"][1]["line"] = "从八点到八点十五正好到点呀呀呀呀呀呀呀"
    with pytest.raises(ValueError, match="计时起点"):
        validate_daily_story_json(story, phase="body")


def test_validate_rejects_premature_time_up_claim():
    story = _valid_story(n=20)
    story["punchline_explain"] = "A类权威翻车，灿灿计时双标被追问"
    story["dialogue"][0]["line"] = "从八点到八点十五，时间到了呀呀呀呀呀呀呀"
    story["dialogue"][1]["line"] = "现在八点十二，我说正好到点呀呀呀呀呀呀呀"
    with pytest.raises(ValueError, match="未到所述结束时刻"):
        validate_daily_story_json(story, phase="body")


def test_validate_rejects_time_up_before_duration_limit():
    story = _valid_story(n=20)
    story["punchline_explain"] = "A类权威翻车，灿灿管手机双标"
    story["dialogue"][0]["line"] = "手机时间到了，快放下呀呀呀呀呀呀呀呀呀"
    story["dialogue"][1]["line"] = "才十分钟，说好十五分钟呀呀呀呀呀呀呀"
    with pytest.raises(ValueError, match="才玩10分钟"):
        validate_daily_story_json(story, phase="body")


def test_validate_allows_soon_time_up_with_duration_anchor():
    pad = "呀呀呀呀呀呀呀呀"
    line = lambda t: (t + pad)[:DAILY_STORY_LINE_CHARS_MAX]
    dialogue = [
        {"speaker": "灿灿", "line": line("马上到时间了别磨蹭")},
        {"speaker": "昭昭", "line": line("才十分钟说好十五分钟")},
    ]
    speakers = ("灿灿", "昭昭")
    dialogue += [
        {"speaker": speakers[i % 2], "line": line("一二三四五六七八")}
        for i in range(2, 18)
    ]
    story = {
        "scene_title": "手机",
        "setting": "客厅玩手机到点",
        "conflict_core": "姐弟玩手机到点谁说了算",
        "dialogue": dialogue,
        "punchline_explain": "A类权威翻车，灿灿管手机双标",
    }
    validate_daily_story_json(story, phase="body")


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
    from app.services.daily_story.story_types.c.quality import score_punchline
    from app.services.daily_story.quality import attach_daily_story_quality, score_daily_story

    story = _valid_story()
    story["discovery_opening"] = [{"speaker": "昭昭", "line": "咦新橡皮怎么在你手里"}]
    lines = [str(d.get("line") or "") for d in story["dialogue"]]
    speakers = [str(d.get("speaker") or "") for d in story["dialogue"]]
    bonus, details = score_punchline(
        lines,
        speakers,
        "".join(lines[-3:-1]),
        lines[-1],
    )
    assert bonus >= 8
    assert any("回旋镖" in d for d in details)

    q = score_daily_story(story)
    assert q["score"] >= 35
    attach_daily_story_quality(story)
    assert story["quality"]["score"] >= 35


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


def test_sync_discovery_opening_from_dialogue_aligns_prefix():
    story = {
        "dialogue": [
            {"speaker": "昭昭", "line": "鞋带又松了，刚系好走两步就散"},
            {"speaker": "灿灿", "line": "你就不能系紧点吗？别老让我说"},
            {"speaker": "昭昭", "line": "好，我按你说的"},
        ],
        "discovery_opening": [{"speaker": "昭昭", "line": "蝴蝶结又散了"}],
    }
    sync_discovery_opening_from_dialogue(story)
    assert story["discovery_opening"] == story["dialogue"][:2]


def test_d_opening_score_skips_stitched_prefix_overlap():
    from app.services.daily_story.story_types.d.opening import score_opening_quality

    story = {
        "dialogue": [
            {"speaker": "昭昭", "line": "这摞衣服歪着，要我帮你叠一叠吗"},
            {"speaker": "灿灿", "line": "你来叠，轻点，这摞别碰，一碰就倒"},
            {"speaker": "昭昭", "line": "好，我按你说的，连呼吸都放轻轻的"},
        ],
        "discovery_opening": [
            {"speaker": "昭昭", "line": "这摞衣服歪着，要我帮你叠一叠吗"},
            {"speaker": "灿灿", "line": "你来叠，轻点，这摞别碰，一碰就倒"},
        ],
        "conflict_core": "叠衣轻点却憋气喷倒",
        "setting": "客厅沙发旁叠衣服",
    }
    _pts, _pros, cons = score_opening_quality(story)
    assert "D开场与正文首句重复" not in cons


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
        [
            {"speaker": "昭昭", "line": "咦新橡皮怎么在你手里"},
            {"speaker": "灿灿", "line": "我才刚拿到还没拆呢"},
        ],
        conflict_core="姐弟抢新橡皮",
        setting="客厅抢新橡皮",
    )
    assert len(ok) == 2

def test_validate_daily_story_opening_coerces_name_key_shorthand():
    ok = validate_daily_story_opening(
        [
            {"昭昭": "咦新橡皮怎么在你手里"},
            {"灿灿": "我才刚拿到还没拆呢"},
        ],
        conflict_core="姐弟抢新橡皮",
        setting="客厅抢新橡皮",
    )
    assert ok == [
        {"speaker": "昭昭", "line": "咦新橡皮怎么在你手里"},
        {"speaker": "灿灿", "line": "我才刚拿到还没拆呢"},
    ]


def test_daily_story_prompts_c_type_route():
    _sys, user = build_daily_story_prompts(
        "谁先洗澡",
        story_type="C类公平执念",
    )
    assert "C 公平执念" in _sys
    assert "争归属" in _sys
    assert "C类收束模板" in user
    assert "回旋镖" in user or "对方刚说的规则" in user
    assert "字面加赛" in _sys or "加赛" in _sys
    assert "那不一样" in _sys or "禁止" in _sys


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
    assert "A类·主题锚定" in user_a or "A类·本场一锤" in user_a
    assert "末四拍" in user_a or "埋句" in user_a
    assert "哪里不一样" in user_a
    assert "本场一锤" in sys_a

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


def test_score_daily_story_structure_capped_without_humor():
    from app.services.daily_story.quality import score_daily_story

    story = {
        "scene_title": "橡皮",
        "setting": "客厅抢橡皮",
        "conflict_core": "姐弟抢橡皮",
        "punchline_explain": "C类公平执念",
        "discovery_opening": [{"speaker": "昭昭", "line": "橡皮怎么在你手里"}],
        "dialogue": [
            {"speaker": "昭昭", "line": "这是我先拿到的橡皮呀"},
            {"speaker": "灿灿", "line": "我先看到应该归我呀"},
            {"speaker": "昭昭", "line": "拿到的人先选呀"},
            {"speaker": "灿灿", "line": "我没说一直占着呀"},
            {"speaker": "昭昭", "line": "你自己说先拿到的呀"},
            {"speaker": "灿灿", "line": "……哼，给你吧"},
        ],
    }
    q = score_daily_story(story)
    assert q["score"] <= 80


def test_score_a_penalizes_stacked_excuses_below_85():
    """格式齐但中段叠两套免责+收束复读，不应摸到85。"""
    from app.services.daily_story.quality import score_daily_story

    dlg = [
        {"speaker": "昭昭", "line": "水果盘怎么少了1块？"},
        {"speaker": "灿灿", "line": "少了？我刚数过还在啊"},
        {"speaker": "昭昭", "line": "你嘴里鼓鼓的，在嚼什么"},
        {"speaker": "灿灿", "line": "饭前不许偷吃，你别瞎说"},
        {"speaker": "昭昭", "line": "那你腮帮子一动一动的"},
        {"speaker": "灿灿", "line": "我是帮你试甜不甜的"},
        {"speaker": "昭昭", "line": "试甜还要把整块塞嘴里？"},
        {"speaker": "灿灿", "line": "不塞怎么尝得准啊你说"},
        {"speaker": "昭昭", "line": "你上次偷吃也是这套词"},
        {"speaker": "灿灿", "line": "上次？那是妈妈让我尝的"},
        {"speaker": "昭昭", "line": "那我也要试，给我一块"},
        {"speaker": "灿灿", "line": "不行，小小孩饭前不能吃"},
        {"speaker": "昭昭", "line": "你不也还没开饭吗你"},
        {"speaker": "灿灿", "line": "我是检查员，检查不算吃"},
        {"speaker": "昭昭", "line": "检查员？谁任命你的啊"},
        {"speaker": "灿灿", "line": "我是姐姐，今天我说了算"},
        {"speaker": "昭昭", "line": "凭什么你能吃我不能吃"},
        {"speaker": "灿灿", "line": "因为我负责把关好不好"},
        {"speaker": "昭昭", "line": "把关就能先把水果吃掉？"},
        {"speaker": "灿灿", "line": "先尝2口才叫把关啊"},
        {"speaker": "昭昭", "line": "那检查完吐出来给我看"},
        {"speaker": "灿灿", "line": "已经咽下去了，看不了啦"},
        {"speaker": "昭昭", "line": "咽下去了还叫检查啊？"},
        {"speaker": "灿灿", "line": "咽了才知道甜不甜嘛"},
        {"speaker": "昭昭", "line": "你刚才说检查不算吃"},
        {"speaker": "灿灿", "line": "那不一样，我是在试味道"},
        {"speaker": "昭昭", "line": "哪里不一样？都进肚子里了"},
        {"speaker": "灿灿", "line": "……哼"},
    ]
    story = {
        "scene_title": "饭前试吃",
        "setting": "厨房案板旁",
        "conflict_core": "灿灿不许昭昭饭前偷吃自己却先捏",
        "discovery_opening": dlg[:2],
        "dialogue": dlg,
        "punchline_explain": "A类权威翻车：检查不算吃",
    }
    q = score_daily_story(story, theme="灿灿不许昭昭饭前偷吃自己却先捏了一块")
    assert q["score"] < 85
    assert any(
        "多套免责" in r or "借口复读" in r or "把关话术" in r or "好笑不足" in r
        for r in q["reasons"]
    )


def test_validate_rejects_brush_duration_inconsistency():
    from app.services.daily_story.prompts import validate_daily_story_json

    story = {
        "scene_title": "刷牙快慢之争",
        "setting": "卫生间门口，昭昭刚刷完牙，灿灿拿着计时器拦住他。",
        "conflict_core": "灿灿嫌昭昭刷牙太快，立规矩却自己犯规",
        "punchline_explain": "A类权威翻车，时长前后不一",
        "discovery_opening": [
            {"speaker": "昭昭", "line": "姐，你计时器上自己才刷了半分钟！"},
        ],
        "dialogue": [
            {"speaker": "昭昭", "line": "姐，你计时器上自己才刷了半分钟！"},
            {"speaker": "灿灿", "line": "你刷牙才一分钟，重刷！"},
            {"speaker": "昭昭", "line": "我刷干净了，为什么要重刷？"},
            {"speaker": "灿灿", "line": "妈妈说至少两分钟，你太快了。"},
            {"speaker": "昭昭", "line": "我用了计时器，正好两分钟。"},
            {"speaker": "灿灿", "line": "计时器肯定被你动了手脚。"},
            {"speaker": "昭昭", "line": "可你自己刷牙也很快，上次才一分半。"},
            {"speaker": "灿灿", "line": "我那次是特殊情况！现在听我的。"},
            {"speaker": "昭昭", "line": "你刚才说特殊情况可以，那我也是。"},
            {"speaker": "灿灿", "line": "那不一样，我是赶时间。"},
            {"speaker": "昭昭", "line": "哪里不一样？都是刷牙快。"},
            {"speaker": "灿灿", "line": "哼，你爱刷不刷。"},
        ],
    }
    with pytest.raises(ValueError, match="时长"):
        validate_daily_story_json(story, phase="full")


def test_validate_a_opening_rejects_spoiler_hammer():
    from app.services.daily_story.prompts import validate_daily_story_opening

    with pytest.raises(ValueError, match="揭穿"):
        validate_daily_story_opening(
            [{"speaker": "昭昭", "line": "姐你计时器上自己才刷了半分钟"}],
            conflict_core="灿灿嫌昭昭刷牙太快立规矩却自己犯规",
            setting="卫生间刷牙计时",
            type_code="A",
        )


def test_validate_b_opening_rejects_already_caught():
    from app.services.daily_story.prompts import validate_daily_story_opening

    with pytest.raises(ValueError, match="露馅|受罚"):
        validate_daily_story_opening(
            [{"speaker": "灿灿", "line": "完蛋了妈妈来了"}],
            conflict_core="姐弟偷吃薯片瞒妈妈",
            setting="客厅偷吃",
            type_code="B",
        )


def test_validate_b_opening_accepts_whisper_pact():
    from app.services.daily_story.prompts import validate_daily_story_opening

    ok = validate_daily_story_opening(
        [
            {"speaker": "昭昭", "line": "嘘，薯片轻点拆"},
            {"speaker": "灿灿", "line": "我盯厨房门"},
        ],
        conflict_core="姐弟偷吃薯片瞒妈妈",
        setting="客厅茶几旁拆薯片",
        type_code="B",
    )
    assert len(ok) == 2


def test_b_opening_score_skips_prepended_discovery_block():
    from app.services.daily_story.story_types.b.opening import score_opening_quality

    story = {
        "discovery_opening": [
            {"speaker": "昭昭", "line": "我望风，你拆，看到妈就咳一声。"},
            {"speaker": "灿灿", "line": "嘘，妈在厨房，咱俩吃这包。"},
        ],
        "dialogue": [
            {"speaker": "昭昭", "line": "我望风，你拆，看到妈就咳一声。"},
            {"speaker": "灿灿", "line": "嘘，妈在厨房，咱俩吃这包。"},
            {"speaker": "昭昭", "line": "行，你手轻点撕，我盯着门。"},
        ],
    }
    _, _, cons = score_opening_quality(story)
    assert "B开场与正文首句重复" not in cons


def test_b_smoke5_quality_scores_around_93():
    import json
    from pathlib import Path

    from app.services.daily_story.quality import score_daily_story

    root = Path(__file__).resolve().parents[2]
    payload = json.loads((root / "tmp/daily_story_b_smoke5.json").read_text())[0]
    q = score_daily_story(payload["story"], theme=payload["theme"])
    assert q["score"] == 93
    assert "B开场与正文首句重复" not in q["reasons"]
    assert any("B收束惩罚缺底" in r for r in q["reasons"])
    assert "仅单人认栽缺同框底" in "".join(q["reasons"])
    assert "开场缺可拍画面" in q["reasons"]
    assert "惩罚落槌有底" not in q["reasons"]


def test_b_landing_flags_batch_weak_endings():
    import json
    from pathlib import Path

    from app.services.daily_story.story_types.b.humor import analyze_punish_landing

    root = Path(__file__).resolve().parents[2]
    batch = json.loads((root / "tmp/daily_story_b_batch5.json").read_text())
    for idx in (2, 3, 4):
        story = batch[idx]["story"]
        lines = [str(x["line"]) for x in story["dialogue"]]
        speakers = [str(x["speaker"]) for x in story["dialogue"]]
        weak, _ = analyze_punish_landing(lines, speakers)
        assert weak, idx


def test_b_landing_accepts_double_doom_tail():
    from app.services.daily_story.story_types.b.humor import analyze_punish_landing

    lines = [
        "前段结盟",
        "走样连锁",
        "妈妈来了",
        "妈妈：你俩，过来站好！",
        "昭昭：完蛋了！",
        "灿灿：我也完了。",
        "昭昭：都怪你没望风！",
        "灿灿：是你先弄洒的！",
        "昭昭：哼，才不是我的主意。",
    ]
    speakers = [
        "昭昭", "灿灿", "妈妈", "妈妈", "昭昭", "灿灿", "昭昭", "灿灿", "昭昭",
    ]
    weak, tag = analyze_punish_landing(lines, speakers)
    assert not weak, tag


def test_b_validate_rejects_missing_landing():
    from app.services.daily_story.story_types.b.validate import append_b_body_errors

    story = {
        "punchline_explain": "B类结盟翻车，姐弟偷吃露馅",
        "dialogue": [
            {"speaker": "昭昭", "line": "嘘，咱俩吃这包。"},
            {"speaker": "灿灿", "line": "我望风你拆。"},
            {"speaker": "昭昭", "line": "好，你手轻点。"},
            {"speaker": "灿灿", "line": "哎，滑出去了！"},
            {"speaker": "昭昭", "line": "快捡起来！"},
            {"speaker": "灿灿", "line": "来不及了鞋底黏了。"},
            {"speaker": "昭昭", "line": "一步一个油印。"},
            {"speaker": "妈妈", "line": "地上怎么一地碎渣？"},
            {"speaker": "妈妈", "line": "你俩，过来站好！"},
            {"speaker": "灿灿", "line": "都怪你望风不咳嗽！"},
            {"speaker": "昭昭", "line": "哼，才不是我的主意。"},
        ],
    }
    errors: list[str] = []
    append_b_body_errors(story, errors)
    assert any("认栽底" in e for e in errors)


def test_validate_a_opening_rejects_mid_fight_timer():
    from app.services.daily_story.prompts import validate_daily_story_opening

    with pytest.raises(ValueError, match="发现现场|读秒"):
        validate_daily_story_opening(
            [
                {"speaker": "灿灿", "line": "你牙刷上的沫还挂那儿呢"},
                {"speaker": "昭昭", "line": "计时器才走了30秒"},
            ],
            conflict_core="灿灿嫌昭昭刷牙太快立规矩却自己犯规",
            setting="卫生间刷牙计时",
            type_code="A",
        )
    ok = validate_daily_story_opening(
        [
            {"speaker": "灿灿", "line": "你牙刷上的沫还挂那儿呢"},
            {"speaker": "昭昭", "line": "我才刷了几下呀"},
        ],
        conflict_core="灿灿嫌昭昭刷牙太快立规矩却自己犯规",
        setting="卫生间刷牙",
        type_code="A",
    )
    assert len(ok) == 2


def test_score_a_quote_must_come_from_cancan():
    from app.services.daily_story.quality import score_daily_story
    from app.services.daily_story.prompts import DAILY_STORY_LINE_CHARS_MAX

    pad = "呀呀呀呀"
    line = lambda t: (t + pad)[:DAILY_STORY_LINE_CHARS_MAX]
    dialogue = [
        {"speaker": "灿灿", "line": line("你刷牙才一分钟重刷")},
        {"speaker": "昭昭", "line": line("我刷够两分钟了呀")},
        {"speaker": "灿灿", "line": line("我是姐姐我说了算")},
        {"speaker": "昭昭", "line": line("那你自己也刷很快")},
        {"speaker": "灿灿", "line": line("我那次是特殊情况")},
        {"speaker": "昭昭", "line": line("为什么特殊情况可以我不可以")},
        {"speaker": "灿灿", "line": line("因为我是姐姐呀")},
        {"speaker": "昭昭", "line": line("你刚才说特殊情况可以那我也是")},
        {"speaker": "灿灿", "line": line("那不一样我赶时间")},
        {"speaker": "昭昭", "line": line("哪里不一样都是刷牙快")},
        {"speaker": "灿灿", "line": line("哼你爱刷不刷")},
    ]
    story = {
        "scene_title": "刷牙",
        "setting": "卫生间刷牙",
        "conflict_core": "姐姐管弟弟刷牙太快",
        "dialogue": dialogue,
        "punchline_explain": "A类权威翻车",
        "discovery_opening": [{"speaker": "灿灿", "line": line("你怎么刷这么快")}],
    }
    q = score_daily_story(story, theme="姐姐嫌弟弟刷牙太快")
    assert any("无出处" in r for r in q["reasons"])
    assert q["score"] < 85


def test_validate_rejects_dangling_what_is_term():
    from app.services.daily_story.prompts import validate_daily_story_json

    story = {
        "scene_title": "刷牙",
        "setting": "卫生间",
        "conflict_core": "灿灿规定连续刷自己却先停",
        "punchline_explain": "A类权威翻车",
        "discovery_opening": [{"speaker": "灿灿", "line": "你吐水了？才刷几下啊"}],
        "dialogue": [
            {"speaker": "灿灿", "line": "你吐水了？才刷几下啊"},
            {"speaker": "昭昭", "line": "什么叫连续？"},
            {"speaker": "灿灿", "line": "就是一直动，停手就重来"},
            {"speaker": "昭昭", "line": "那吐水算不算停"},
            {"speaker": "灿灿", "line": "吐水也算停"},
            {"speaker": "昭昭", "line": "你示范给我看"},
            {"speaker": "灿灿", "line": "看好了刷刷刷"},
            {"speaker": "昭昭", "line": "你才刷了三下就吐水了"},
            {"speaker": "灿灿", "line": "示范不算"},
            {"speaker": "昭昭", "line": "你刚才说吐水也算停"},
            {"speaker": "灿灿", "line": "那不一样"},
            {"speaker": "昭昭", "line": "哪里不一样都是停"},
            {"speaker": "灿灿", "line": "哼行吧"},
        ],
    }
    with pytest.raises(ValueError, match="什么叫连续|前文未出现"):
        validate_daily_story_json(story, phase="full")


def test_validate_rejects_a_mid_rule_restatement():
    from app.services.daily_story.prompts import validate_daily_story_json

    story = {
        "scene_title": "刷牙计时",
        "setting": "客厅刷牙",
        "conflict_core": "灿灿嫌昭昭刷牙太快立规矩反被打脸",
        "punchline_explain": "A类权威翻车",
        "discovery_opening": [{"speaker": "昭昭", "line": "姐你又拿秒表盯我刷牙"}],
        "dialogue": [
            {"speaker": "昭昭", "line": "姐你又拿秒表盯我刷牙"},
            {"speaker": "灿灿", "line": "你才刷一分钟，重刷"},
            {"speaker": "昭昭", "line": "那能停下来漱口或者喝水吗"},
            {"speaker": "灿灿", "line": "不能停，停了就不算数"},
            {"speaker": "昭昭", "line": "停了重来，不能耍赖哦"},
            {"speaker": "灿灿", "line": "对，我说话算数"},
            {"speaker": "昭昭", "line": "那如果刷一半停下来漱口或者吐水呢"},
            {"speaker": "灿灿", "line": "漱口吐水也算停，必须重来"},
            {"speaker": "昭昭", "line": "你确定"},
            {"speaker": "灿灿", "line": "确定，我说到做到绝不反悔"},
            {"speaker": "昭昭", "line": "好你现在刷我看着"},
            {"speaker": "灿灿", "line": "行，计时开始"},
            {"speaker": "昭昭", "line": "你才刷了五十秒就停了嘴"},
            {"speaker": "灿灿", "line": "我就漱了一下口"},
            {"speaker": "昭昭", "line": "你自己说的大人小孩都一样"},
            {"speaker": "灿灿", "line": "那不一样"},
            {"speaker": "昭昭", "line": "哪里不一样都是停"},
            {"speaker": "灿灿", "line": "哼行吧你过关了"},
        ],
    }
    with pytest.raises(ValueError, match="复读|重复追问|注水|漱口"):
        validate_daily_story_json(story, phase="full")


def test_score_c_boomerang_humor_not_flatlined():
    """C 回旋镖收束时好笑维不因同义引话被整维清零。"""
    from app.services.daily_story.quality import score_daily_story

    pad = "呀呀呀呀呀呀"
    line = lambda t: (t + pad)[:DAILY_STORY_LINE_CHARS_MAX]
    dialogue = [
        {"speaker": "昭昭", "line": line("这个先后得讲规矩")},
        {"speaker": "灿灿", "line": line("我比你大我先")},
        {"speaker": "昭昭", "line": line("你又不是真大人")},
        {"speaker": "灿灿", "line": line("那谁更急谁先上")},
        {"speaker": "昭昭", "line": line("行啊谁更急谁赢")},
        {"speaker": "灿灿", "line": line("你怎么证明你急")},
        {"speaker": "昭昭", "line": line("我去多接一杯水")},
        {"speaker": "灿灿", "line": line("等等你作弊还没比呢")},
        {"speaker": "昭昭", "line": line("你说的比谁更急喝越多越急")},
        {"speaker": "灿灿", "line": line("哼算你狠你先吧")},
    ]
    story = {
        "scene_title": "争先后",
        "setting": "门口姐弟争先后",
        "conflict_core": "姐弟争同一顺序",
        "dialogue": dialogue,
        "punchline_explain": "C类公平执念，规则字面回旋镖",
        "discovery_opening": [{"speaker": "昭昭", "line": line("你怎么站我前面")}],
    }
    q = score_daily_story(story, theme="争先后")
    assert any("回旋镖" in r for r in q["reasons"])
    assert not any("无出处" in r for r in q["reasons"])
    humor_pts = next(
        (int(m.group(1)) for r in q["reasons"] if (m := __import__("re").search(r"好笑(\d+)", r))),
        None,
    )
    assert humor_pts is not None and humor_pts >= 9, q["reasons"]
    assert any("字面加赛" in r for r in q["reasons"]), q["reasons"]


def test_score_c_folding_literal_play_not_flatlined():
    """C 叠收字面加赛：勿误扣缺可拍争法、好笑维须够格。"""
    from app.services.daily_story.quality import score_daily_story

    pad = "呀呀呀呀呀呀"
    line = lambda t: (t + pad)[:DAILY_STORY_LINE_CHARS_MAX]
    dialogue = [
        {"speaker": "灿灿", "line": line("叠好的衣服怎么翻出来了")},
        {"speaker": "昭昭", "line": line("我找袜子又不是故意的")},
        {"speaker": "灿灿", "line": line("谁弄乱谁收拾这是规矩")},
        {"speaker": "昭昭", "line": line("凭什么你定的规矩呀")},
        {"speaker": "灿灿", "line": line("我叠好了你弄乱你收")},
        {"speaker": "昭昭", "line": line("行我叠但叠完你得收")},
        {"speaker": "灿灿", "line": line("你叠的必须整整齐齐")},
        {"speaker": "昭昭", "line": line("那你看着一件一件收")},
        {"speaker": "灿灿", "line": line("行谁怕谁你叠吧")},
        {"speaker": "昭昭", "line": line("这件叠好了给你")},
        {"speaker": "灿灿", "line": line("东倒西歪算什么叠法")},
        {"speaker": "昭昭", "line": line("你叠你收又没说要多好")},
        {"speaker": "灿灿", "line": line("你耍赖还不如不叠")},
        {"speaker": "昭昭", "line": line("你说的谁弄乱谁收拾呢")},
        {"speaker": "灿灿", "line": line("哼算你狠我自己来")},
    ]
    story = {
        "scene_title": "叠好的衣服",
        "setting": "客厅沙发衣服被翻乱",
        "conflict_core": "姐弟争谁收拾叠好的衣服",
        "dialogue": dialogue,
        "punchline_explain": "C类公平执念，赛规字面回旋镖",
        "discovery_opening": [
            {"speaker": "灿灿", "line": line("沙发上那堆衣服谁弄的")},
        ],
    }
    q = score_daily_story(story, theme="弄乱叠好的衣服")
    assert not any("缺可拍争法" in r for r in q["reasons"]), q["reasons"]
    humor_pts = next(
        (int(m.group(1)) for r in q["reasons"] if (m := __import__("re").search(r"好笑(\d+)", r))),
        None,
    )
    assert humor_pts is not None and humor_pts >= 9, q["reasons"]
    assert q["score"] >= 78, q["reasons"]


def test_infer_story_type_and_normalize_punchline():
    from app.services.daily_story.story_types import (
        extract_story_type_code_from_punchline,
        infer_story_type_code,
        normalize_punchline_explain,
        parse_story_type_code,
        punchline_has_standard_type_tag,
    )

    assert extract_story_type_code_from_punchline("C类公平执念，回旋镖") == "C"
    assert extract_story_type_code_from_punchline("矛盾类型C（公平执念）：姐弟争橡皮") == "C"
    assert extract_story_type_code_from_punchline("姐弟争先后") is None
    assert extract_story_type_code_from_punchline("") is None

    story = {
        "conflict_core": "姐弟争谁先洗澡",
        "setting": "浴室门口",
        "punchline_explain": "姐弟俩用石头剪刀布争先后，妈妈让一起洗",
        "dialogue": [
            {"speaker": "昭昭", "line": "我先到应该先洗"},
            {"speaker": "灿灿", "line": "我比你大应该我先"},
            {"speaker": "昭昭", "line": "规则谁先站队谁先"},
            {"speaker": "灿灿", "line": "那平局怎么办呀"},
            {"speaker": "昭昭", "line": "你自己说猜拳定输赢"},
            {"speaker": "灿灿", "line": "我没说赢的先洗呀"},
            {"speaker": "昭昭", "line": "那你刚说的算什么"},
            {"speaker": "灿灿", "line": "哼随便你"},
        ],
    }
    assert infer_story_type_code(story, theme="谁先洗澡争夺战") == "C"
    new = normalize_punchline_explain(story["punchline_explain"], "C")
    assert new.startswith("C类公平执念，")
    assert parse_story_type_code(punchline=new) == "C"
    assert punchline_has_standard_type_tag(new)

    weak = normalize_punchline_explain(
        "矛盾类型C（公平执念）：姐弟争橡皮",
        "C",
    )
    assert weak.startswith("C类公平执念，姐弟争橡皮")

    a_tail = {
        "punchline_explain": "姐姐教作业被打脸",
        "dialogue": [
            {"speaker": "昭昭", "line": "你这道题算错了"},
            {"speaker": "灿灿", "line": "我是教你"},
            {"speaker": "昭昭", "line": "你刚才说错一次不算"},
            {"speaker": "灿灿", "line": "那不一样我是姐姐"},
            {"speaker": "昭昭", "line": "哪里不一样都是算错"},
            {"speaker": "灿灿", "line": "哼行吧"},
        ],
    }
    assert infer_story_type_code(a_tail, theme="教作业") == "A"


def test_validate_c_body_rejects_a_style_closing():
    story = _valid_story()
    dialogue = story["dialogue"]
    # 保持末四拍 speaker 交替，只改台词为 A 式模板
    sp4, sp3, sp2, sp1 = (
        dialogue[-4]["speaker"],
        dialogue[-3]["speaker"],
        dialogue[-2]["speaker"],
        dialogue[-1]["speaker"],
    )
    dialogue[-4] = {"speaker": sp4, "line": _pad_line("你刚才说大的归你先拿")}
    dialogue[-3] = {"speaker": sp3, "line": _pad_line("那不一样我是姐姐呀")}
    dialogue[-2] = {"speaker": sp2, "line": _pad_line("哪里不一样都是听你的")}
    dialogue[-1] = {"speaker": sp1, "line": _pad_line("哼行吧随便你")}
    with pytest.raises(ValueError, match="A 式末四拍|回旋镖"):
        validate_daily_story_json(story, phase="body")


def test_validate_c_body_accepts_boomerang_close():
    story = _valid_story()
    validate_daily_story_json(story, phase="body")


def test_validate_c_body_accepts_ni_gang_shuo_boomerang():
    story = _valid_story()
    sp2 = story["dialogue"][-2]["speaker"]
    story["dialogue"][-2] = {
        "speaker": sp2,
        "line": _pad_line("你刚说谁弄乱谁收拾呀"),
    }
    validate_daily_story_json(story, phase="body")


def test_validate_c_body_rejects_truncated_close_line():
    story = _valid_story()
    sp2 = story["dialogue"][-2]["speaker"]
    story["dialogue"][-2] = {
        "speaker": sp2,
        "line": "反正你说的'谁弄乱",
    }
    with pytest.raises(ValueError, match="完整|未说完|引号"):
        validate_daily_story_json(story, phase="body")


def test_build_quality_edit_scope_hint_for_c_closing():
    from app.services.daily_story.quality import (
        build_quality_edit_scope_hint,
        build_quality_revision_hints,
    )

    story = _valid_story()
    hints = build_quality_revision_hints(
        {
            "reasons": [
                "回旋镖收束",
                "冲突推进3层",
                "C收束缺可拍争法",
                "结构65",
                "好笑9",
            ],
            "score": 69,
        },
        story=story,
    )
    assert "缺可拍" in hints or "字面加赛" in hints
    assert "C·好笑目标" not in hints
    assert "改稿范围" in hints
    assert "中段" in hints
    scope = build_quality_edit_scope_hint(story, "【C·收束】回旋镖")
    assert "第" in scope and "行" in scope


def test_c_quality_has_fact_opening_and_humor_dims():
    import json

    from app.services.daily_story.quality import score_daily_story

    path = "tmp/daily_story_c_clothes_regen.json"
    try:
        raw = json.load(open(path))
    except OSError:
        return
    if not raw:
        return
    st = raw[0].get("story")
    if not isinstance(st, dict):
        return
    q = score_daily_story(st)
    reasons = q.get("reasons") or []
    assert any("好笑" in r for r in reasons)
    assert any("C事实" in r or "事实自洽" in r for r in reasons)
    assert any(
        "C开场" in r or "开场" in r for r in reasons
    ) or any("C开场锚定" in r for r in reasons)


def test_validation_retry_hints_primary_issue_only():
    from app.services.daily_story.retry_hints import (
        build_validation_retry_hints,
        pick_primary_validation_errors,
    )

    err = (
        "正文总字数须≥280，当前219（还差61字）; "
        "C类末段须有回旋镖（用对方刚立的规则反问）或实物真相反转收束"
    )
    assert "总字数" in pick_primary_validation_errors(err)[0]
    hint = build_validation_retry_hints(err, chars=219, type_code="C")
    assert "补字" in hint
    assert "末 4 句" not in hint

    err2 = (
        "dialogue[9:10] 昭昭 连说≥2句，须轮流说话; "
        "C类末段须有回旋镖（用对方刚立的规则反问）或实物真相反转收束"
    )
    hint2 = build_validation_retry_hints(err2, chars=300, type_code="C")
    assert "连说" in hint2
    assert "回旋镖·只改末" not in hint2
