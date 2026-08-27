"""标题优化提示词测试。"""

from __future__ import annotations

import pytest

from app.services.daily_story.prompts import (
    DAILY_STORY_BODY_CHARS_MAX,
    DAILY_STORY_BODY_CHARS_MIN,
    DAILY_STORY_BODY_WRITE_TARGET_MAX,
    DAILY_STORY_BODY_WRITE_TARGET_MIN,
    DAILY_STORY_LINE_CHARS_MAX,
    build_daily_story_prompts,
    build_daily_story_theme_prompts,
    validate_daily_story_json,
)
from app.services.script.optimize_title import parse_title_optimize_payload

def test_parse_title_optimize_payload():
    title = parse_title_optimize_payload({"title": "雪崩瞬间，为啥这么猛"}, max_title_len=24)
    assert title == "雪崩瞬间，为啥这么猛"

def test_parse_chat_title_candidates_payload():
    from app.services.script.optimize_title import parse_chat_title_candidates_payload

    out = parse_chat_title_candidates_payload(
        {"titles": ["妈，月饼不是我弄的", "月饼全滚出来了", "妈，月饼不是我弄的"]},
        max_title_len=10,
    )
    assert out == ["妈，月饼不是我弄的", "月饼全滚出来了"]  # 去空去重保序

    single = parse_chat_title_candidates_payload({"title": "谁踩的月饼印"}, max_title_len=10)
    assert single == ["谁踩的月饼印"]

    with pytest.raises(ValueError):
        parse_chat_title_candidates_payload({}, max_title_len=10)
    with pytest.raises(ValueError):
        parse_chat_title_candidates_payload({"titles": ["   "]}, max_title_len=10)

def test_pick_best_chat_title_prefers_hook_and_avoids_repeat():
    from app.services.script.optimize_title import pick_best_chat_title

    # 好封面初稿（画面短语）不再被口述甩锅句替换
    assert (
        pick_best_chat_title(
            "月饼大作战",
            ["月饼全滚出来了", "妈，月饼不是我弄的"],
            max_len=10,
        )
        == "月饼大作战"
    )

    # avoid 命中降权：手动重跑时避免重复上一个标题；
    # 但候选都不优于当前标题（hook 0）时，防御当前标题，不写更差/平的标题
    best2 = pick_best_chat_title(
        "月饼大作战",
        ["妈，月饼不是我弄的", "月饼全滚出来了"],
        max_len=10,
        avoid_titles=["妈，月饼不是我弄的"],
    )
    assert best2 == "月饼大作战"

    # 标点变体也算重复：avoid 按 title_core 比对
    best3 = pick_best_chat_title(
        "月饼大作战",
        ["妈，月饼不是我弄的！", "月饼渣，我踩的印"],
        max_len=10,
        avoid_titles=["妈，月饼不是我弄的"],
    )
    # 「月饼渣，我踩的印」不高于画面初稿 → 保留当前
    assert best3 == "月饼大作战"

    # 坏初稿（剧透口述）时：甩锅声明仍压过「谁…」质问
    best4 = pick_best_chat_title(
        "剪刀剪歪了，还咋教弟弟？",
        ["谁把月饼抖一地", "妈，月饼是它自己滚的"],
        max_len=12,
        anchor_words=["月饼"],
    )
    assert best4 == "妈，月饼是它自己滚的"

    # 候选与初稿相同/命中 avoid → 回退初稿
    assert pick_best_chat_title("月饼大作战", ["月饼大作战"], max_len=10) == "月饼大作战"

def test_pick_best_chat_title_avoid_prevents_punctuation_variant_repeat():
    """重跑时标点/叹号变体也算重复：命中 avoid_titles 的候选降权，换角度候选胜出。"""
    from app.services.script.optimize_title import pick_best_chat_title

    best = pick_best_chat_title(
        "分蛋糕",
        ["分蛋糕先挑，咋还输了！", "分蛋糕先挑大的，凭啥还亏我"],
        max_len=15,
        anchor_words=["分蛋糕"],
        story_type="C",
        avoid_titles=["分蛋糕先挑咋还输了"],
    )
    assert best == "分蛋糕先挑大的，凭啥还亏我"

def test_extract_core_anchor_words():
    from app.services.script.optimize_title import extract_core_anchor_words

    story = {
        "scene_title": "月饼大作战",
        "conflict_core": "姐弟联手偷吃月饼，望风失误掉渣露馅",
        "setting": "客厅茶几上放着一盒月饼",
    }
    assert extract_core_anchor_words("月饼大作战", story) == ["月饼"]
    # 「玩具」在正文里前后都是汉字（藏玩具别），无独立词边界 → 不强制，宁可不锚定
    assert extract_core_anchor_words("藏玩具同盟", {
        "scene_title": "藏玩具同盟",
        "conflict_core": "约好一起藏玩具别让妈妈发现",
    }) == []
    # 与冲突核心无交集 → 不强制
    assert extract_core_anchor_words("月饼大作战", {"conflict_core": "姐弟吵架"}) == []
    # 不产出跨词坏碎片：最长优先取完整短语「偷看电视」（绝不「偷看电」/「偷看」）
    assert extract_core_anchor_words("偷看电视", {
        "scene_title": "偷看电视",
        "conflict_core": "姐弟趁妈妈洗澡偷看电视，约好轮班望风，结果露馅",
        "setting": "客厅，电视还黑着",
    }) == ["偷看电视"]
    # 3 字 scene_title 取完整短语，杜绝「分蛋」这种前缀碎片
    assert extract_core_anchor_words("分蛋糕", {
        "scene_title": "分蛋糕",
        "conflict_core": "姐弟争切蛋糕，谁切谁先选",
        "setting": "客厅茶几上放着一块圆形蛋糕，灿灿手拿餐刀正准备切，昭昭伸手要抢刀。",
        "theme": "分蛋糕大小不均",
    }) == ["分蛋糕"]
    # 4 字 scene_title 取完整短语，杜绝「抢遥」「控器」这种前后缀碎片
    anchors = extract_core_anchor_words("抢遥控器", {
        "scene_title": "抢遥控器",
        "conflict_core": "姐弟抢遥控器，谁也不让谁",
        "setting": "客厅，电视开着。",
        "theme": "抢遥控器谁都不让",
    })
    assert anchors == ["抢遥控器"]
    assert "抢遥" not in anchors
    assert "控器" not in anchors

def test_pick_best_chat_title_anchor_guard():
    from app.services.script.optimize_title import pick_best_chat_title

    # 含核心名词的候选胜出（哪怕口吻分略低）
    best = pick_best_chat_title(
        "月饼大作战",
        ["谁踩的渣印", "妈，月饼自己滚的"],
        max_len=10,
        anchor_words=["月饼"],
    )
    assert best == "妈，月饼自己滚的"
    # 全部不含核心名词 → 回退初稿，绝不写跑题标题
    assert (
        pick_best_chat_title(
            "月饼大作战", ["谁踩的渣印", "渣印谁擦"], max_len=10, anchor_words=["月饼"]
        )
        == "月饼大作战"
    )
    # 不传 anchor_words 时：候选全是谁字质问（-2），均不优于初稿 → 保留初稿
    assert (
        pick_best_chat_title("月饼大作战", ["谁踩的渣印", "渣印谁擦"], max_len=10)
        == "月饼大作战"
    )

def test_pick_best_chat_title_rejects_broken_anchor_fragment():
    """锚点不含跨词坏碎片：偷看电视 取完整短语，「偷看」「偷看电」绝不出现在要求里。"""
    from app.services.script.optimize_title import extract_core_anchor_words

    story = {
        "scene_title": "偷看电视",
        "conflict_core": "姐弟趁妈妈洗澡偷看电视，约好轮班望风，结果露馅",
        "setting": "客厅，电视还黑着，昭昭握着遥控器",
        "theme": "姐弟趁妈妈洗澡偷看电视",
    }
    anchors = extract_core_anchor_words("偷看电视", story)
    assert anchors == ["偷看电视"]
    assert "偷看" not in anchors
    assert "偷看电" not in anchors

def test_pick_best_chat_title_rejects_broken_prefix_fragment():
    """锚词为完整短语「分蛋糕」时，「分蛋翻车记」必须被拒，完整短语候选被接受。"""
    from app.services.script.optimize_title import (
        extract_core_anchor_words,
        extract_theme_action_phrase,
        pick_best_chat_title,
    )

    story = {
        "scene_title": "分蛋糕",
        "conflict_core": "姐弟争切蛋糕，谁切谁先选",
        "setting": "客厅茶几上放着一块圆形蛋糕，灿灿手拿餐刀正准备切，昭昭伸手要抢刀。",
        "theme": "分蛋糕大小不均",
        "story_type": "C",
    }
    anchors = extract_core_anchor_words("分蛋糕", story)
    assert anchors == ["分蛋糕"]
    assert "分蛋" not in anchors
    phrase = extract_theme_action_phrase("分蛋糕", story)
    assert phrase == "分蛋糕"
    # 坏碎片候选不含完整主题短语 → 作废，回退初稿
    assert (
        pick_best_chat_title("分蛋糕", ["分蛋翻车记"], max_len=15, anchor_words=anchors)
        == "分蛋糕"
    )
    # 含完整主题短语的画面候选正常通过
    assert (
        pick_best_chat_title(
            "分蛋糕", ["分蛋糕先切一刀"], max_len=15, anchor_words=anchors,
        )
        == "分蛋糕先切一刀"
    )

def test_chat_title_prompt_uses_full_theme_phrase():
    """标题优化提示词必须写「分蛋糕」，绝不能把「分蛋」当硬性保留短语。"""
    from app.services.script.optimize_title import build_chat_title_user_prompt

    story = {
        "scene_title": "分蛋糕",
        "conflict_core": "姐弟争切蛋糕，谁切谁先选",
        "setting": "客厅茶几上放着一块圆形蛋糕，灿灿手拿餐刀正准备切，昭昭伸手要抢刀。",
        "theme": "分蛋糕大小不均",
        "story_type": "C",
    }
    prompt = build_chat_title_user_prompt(draft_title="分蛋糕", story_content=story, max_title_len=15)
    assert "「分蛋」" not in prompt
    assert "「分蛋糕」" in prompt
    assert "本次类型硬规则" in prompt
    assert "黑名单词禁用" in prompt
    assert "候选1也不允许省略" in prompt
    assert "禁止放在句尾倒装" in prompt
    assert "同一句式结构也最多出现 1 次" in prompt
    assert "孩子气硬规则" in prompt or "孩子当场脱口而出的话" in prompt
    assert "不能有语病" in prompt
    assert "语病自检" in prompt
    assert "说好分蛋糕先挑" in prompt
    assert "封面感硬规则" in prompt
    assert "大块归你？分蛋糕我先挑，赖皮" in prompt

def test_pick_best_chat_title_hard_drops_missing_anchor():
    """缺主题短语/核心名词的候选直接作废，不参与选择。"""
    from app.services.script.optimize_title import pick_best_chat_title

    # 候选1缺「分蛋糕」，即使有类型钩子+问号也必须被跳过
    best = pick_best_chat_title(
        "分蛋糕",
        ["先挑咋还输了？", "分蛋糕先挑白忙一场"],
        max_len=15,
        anchor_words=["分蛋糕"],
        story_type="C",
    )
    assert best == "分蛋糕先挑白忙一场"
    # 全部候选都缺主题短语 → 回退初稿
    assert (
        pick_best_chat_title(
            "分蛋糕",
            ["先挑咋还输了？", "按字面白忙一场"],
            max_len=15,
            anchor_words=["分蛋糕"],
            story_type="C",
        )
        == "分蛋糕"
    )

def test_filter_chat_title_candidates_drops_missing_anchor():
    """候选层硬过滤：缺主题短语的候选被丢弃，空锚词时不过滤。"""
    from app.services.script.optimize_title import filter_chat_title_candidates

    candidates = ["分蛋糕先挑咋还输了", "先挑反被挑走大块", "分蛋糕按字面白忙"]
    assert filter_chat_title_candidates(candidates, ["分蛋糕"]) == [
        "分蛋糕先挑咋还输了",
        "分蛋糕按字面白忙",
    ]
    assert filter_chat_title_candidates(candidates, []) == candidates

def test_ensure_chat_title_candidates_refills_missing():
    """有效候选不足 3 个时，重生成补足到 3 个，缺锚词的候选不进入结果。"""
    from app.services.script.optimize_title import ensure_chat_title_candidates

    fetch = iter([
        ["先挑咋还输了", "分蛋糕按字面白忙", "分蛋糕大小不均亏"],
        ["分蛋糕先挑反被挑走大块", "分蛋糕咋还输了", "分蛋糕立规反被挑"],
    ])
    out = ensure_chat_title_candidates(
        ["分蛋糕先挑咋还输了", "先挑反被挑走大块"],
        ["分蛋糕"],
        fetch_candidates=lambda: next(fetch),
        max_attempts=2,
    )
    assert len(out) == 3
    assert all("分蛋糕" in c for c in out)
    assert "先挑反被挑走大块" not in out

def test_polish_chat_title_valid_and_fallback():
    """润色结果通过硬校验才采用；缺短语/黑名单/句尾倒装/请求异常都回退原标题。"""
    from app.services.script.optimize_title import polish_chat_title

    story = {
        "scene_title": "分蛋糕",
        "conflict_core": "姐弟争切蛋糕，谁切谁先选",
        "setting": "客厅茶几上放着一块圆形蛋糕。",
        "theme": "分蛋糕大小不均",
        "story_type": "C",
    }
    source = "分蛋糕先挑反被大块走"
    assert (
        polish_chat_title(
            source,
            "分蛋糕",
            story,
            max_len=15,
            fetch_json=lambda p: {"title": "分蛋糕先挑，反被拿走大块"},
        )
        == "分蛋糕先挑，反被拿走大块"
    )
    # 润色删掉原标题的内容字（如「挑」）→ 回退
    assert (
        polish_chat_title(
            "按字面挑，分蛋糕白忙",
            "分蛋糕",
            story,
            max_len=15,
            fetch_json=lambda p: {"title": "分蛋糕，按字面白忙"},
        )
        == "按字面挑，分蛋糕白忙"
    )
    # 缺主题短语 → 回退
    assert (
        polish_chat_title(
            source,
            "分蛋糕",
            story,
            max_len=15,
            fetch_json=lambda p: {"title": "先挑反被拿走大块"},
        )
        == source
    )
    # 含黑名单词 → 回退
    assert (
        polish_chat_title(
            source,
            "分蛋糕",
            story,
            max_len=15,
            fetch_json=lambda p: {"title": "分蛋糕先挑咋全露馅了"},
        )
        == source
    )
    # 句尾倒装 → 回退
    assert (
        polish_chat_title(
            source,
            "分蛋糕",
            story,
            max_len=15,
            fetch_json=lambda p: {"title": "先挑反被拿走，分蛋糕"},
        )
        == source
    )
    # 请求异常 → 回退
    def boom(p):
        raise RuntimeError("fetch failed")

    assert polish_chat_title(source, "分蛋糕", story, max_len=15, fetch_json=boom) == source

def test_polish_chat_title_grammar_gate():
    """语病审核不过时回喂意见修复；修复通过才采用，否则回退。"""
    from app.services.script.optimize_title import polish_chat_title

    story = {
        "scene_title": "分蛋糕",
        "conflict_core": "姐弟争切蛋糕，谁切谁先选",
        "setting": "客厅茶几上放着一块圆形蛋糕。",
        "theme": "分蛋糕大小不均",
        "story_type": "C",
    }
    source = "分蛋糕说好先挑，咋亏了"
    fixed = "分蛋糕说好我先挑，咋亏了"

    def fetch_json(p):
        if p["step"] == "chat_title_grammar_fix":
            return {"title": fixed}
        return {"title": source}

    def check_json(p):
        title = p["user"].split("标题：")[1].split("\n")[0]
        return {"ok": title == fixed, "reason": "" if title == fixed else "缺主语"}

    assert (
        polish_chat_title(
            source,
            "分蛋糕",
            story,
            max_len=15,
            fetch_json=fetch_json,
            check_json=check_json,
        )
        == fixed
    )

    # 修复结果仍不合格（缺主题短语）→ 回退原标题
    def fetch_json_bad(p):
        if p["step"] == "chat_title_grammar_fix":
            return {"title": "说好我先挑，咋亏了"}
        return {"title": source}

    assert (
        polish_chat_title(
            source,
            "分蛋糕",
            story,
            max_len=15,
            fetch_json=fetch_json_bad,
            check_json=lambda p: {"ok": False, "reason": "还是缺主语"},
        )
        == source
    )

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
    assert "动作/实物" in theme_user or "带动作/实物" in theme_user
    assert "按类型配额" in theme_user or "类型|主题" in theme_user
    assert "争最后一瓶酸奶" in theme_user  # 禁复读清单

    _ts_e, user_e = build_daily_story_theme_prompts(3, type_code="E")
    assert "只出 E 类主题" in user_e
    assert "可拍现行" in user_e or "E×3" in user_e
    assert "饭前不吃零食勺子还挂着菜" in user_e or "勺子" in user_e
    # 说谎题从 E 正例拿掉，改列为禁止
    assert "不许说谎" in user_e

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
        "key": "抢新橡皮",
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

def test_validate_daily_story_json_rejects_consecutive_same_speaker():
    story = _valid_story()
    story["dialogue"][4]["speaker"] = "昭昭"
    story["dialogue"][5]["speaker"] = "昭昭"
    with pytest.raises(ValueError, match="连说"):
        validate_daily_story_json(story)

def test_validate_daily_story_json_rejects_missing_conflict_core():
    story = _valid_story()
    del story["conflict_core"]
    with pytest.raises(ValueError, match="conflict_core"):
        validate_daily_story_json(story)

def test_validate_daily_story_json_rejects_missing_key():
    story = _valid_story()
    del story["key"]
    with pytest.raises(ValueError, match="缺少必需字段: key"):
        validate_daily_story_json(story)

def test_build_daily_story_retry_user_asks_to_expand_short_draft():
    from app.services.daily_story.prompts import (
        build_daily_story_retry_user,
        dialogue_total_chars,
        resolve_daily_story_retry_length_mode,
    )

    prev = _valid_story(n=10)
    # C·整件物偏短：走 expand（禁止照抄上一稿，须扩写重写）
    assert dialogue_total_chars(prev) < DAILY_STORY_BODY_CHARS_MIN
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
    assert "鞋带" in user
    assert "扩写" in user or "补满" in user or "revise_expand" in user.lower() or "上一稿" in user
    assert "还差100字" in user or "总字数须≥" in user

def test_validate_rejects_role_swap_claims():
    """身份自称只准按角色：昭昭=弟弟、灿灿=姐姐；互换即角色错乱。
    （削铅笔 batch8：昭昭自称「我是哥哥/我说了算」成权威，旧校验没兜住）"""
    import copy

    base = _valid_story(n=18)
    # 昭昭自称哥哥 → 拒绝
    bad1 = copy.deepcopy(base)
    for d in bad1["dialogue"]:
        if d["speaker"] == "昭昭":
            d["line"] = _pad_line("我是哥哥我说了算")
            break
    with pytest.raises(ValueError, match="角色反了"):
        validate_daily_story_json(bad1, phase="body")
    # 灿灿自称弟弟 → 拒绝
    bad2 = copy.deepcopy(base)
    for d in bad2["dialogue"]:
        if d["speaker"] == "灿灿":
            d["line"] = _pad_line("我是弟弟你别管")
            break
    with pytest.raises(ValueError, match="角色反了"):
        validate_daily_story_json(bad2, phase="body")
    # 灿灿自称姐姐 → 合法，不误伤
    ok = copy.deepcopy(base)
    for d in ok["dialogue"]:
        if d["speaker"] == "灿灿":
            d["line"] = _pad_line("我是姐姐我说了算")
            break
    validate_daily_story_json(ok, phase="body")

def _a_valid_body() -> dict:
    """A 类刷牙梗合法正文：末四拍 昭昭引原话→灿灿那不一样→昭昭哪里不一样→灿灿软破功。

    append_a_body_errors 的四个子校验全部放行（引话有出处、末句非管人、非偷吃主题）。
    """
    return {
        "scene_title": "刷牙",
        "setting": "卫生间刷牙",
        "conflict_core": "灿灿规定连续刷自己却先停",
        "punchline_explain": "A类权威翻车",
        "dialogue": [
            {"speaker": "灿灿", "line": "你吐水了？才刷几下啊"},
            {"speaker": "昭昭", "line": "什么叫连续"},
            {"speaker": "灿灿", "line": "就是一直动，停手就重来"},
            {"speaker": "昭昭", "line": "那吐水算不算停"},
            {"speaker": "灿灿", "line": "吐水也算停"},
            {"speaker": "昭昭", "line": "你示范给我看"},
            {"speaker": "灿灿", "line": "看好了刷刷刷"},
            {"speaker": "昭昭", "line": "你才刷了三下就吐水了"},
            {"speaker": "灿灿", "line": "示范不算"},
            {"speaker": "昭昭", "line": "你刚才说吐水也算停"},
            {"speaker": "灿灿", "line": "那不一样，示范不算数"},
            {"speaker": "昭昭", "line": "哪里不一样都是停"},
            {"speaker": "灿灿", "line": "哼行吧"},
        ],
    }

def _a_body_errors(story: dict) -> list[str]:
    from app.services.daily_story.story_types.a.validate import append_a_body_errors

    errors: list[str] = []
    append_a_body_errors(story, errors)
    return errors

def test_a_closing_structure_accepts_full_tail():
    """A 类完整末四拍（引原话→那不一样→哪里不一样→软破功）放行。"""
    errors = _a_body_errors(_a_valid_body())
    assert errors == []

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

def test_c_whole_item_body_too_short():
    from app.services.daily_story.prompts import c_whole_item_body_too_short

    story = {
        "conflict_core": "姐弟争同一个蓝抱枕",
        "dialogue": [{"speaker": "昭昭", "line": "短"}] * 10,
    }
    err = c_whole_item_body_too_short(
        story,
        theme="沙发上的抱枕大战",
        framework={"setting": "客厅沙发抢抱枕"},
    )
    assert err
    assert "总字数须≥" in err
    assert "C整件物句数须≥" in err

