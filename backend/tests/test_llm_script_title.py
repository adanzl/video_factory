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
from app.services.script.optimize_title import parse_title_optimize_payload
from app.utils.title_text import select_optimized_title

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

    # 问句/称呼开头 + 甩锅口吻 优于平铺直叙的事件复述
    best = pick_best_chat_title(
        "月饼大作战",
        ["月饼全滚出来了", "妈，月饼不是我弄的"],
        max_len=10,
    )
    assert best == "妈，月饼不是我弄的"

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
    # 「月饼渣，我踩的印」hook 0 不高于当前标题 → 保留当前
    assert best3 == "月饼大作战"

    # 「谁…」不加分：甩锅声明/推锅给东西 与 谁问句同台竞争，避免谁字刷屏
    best4 = pick_best_chat_title(
        "月饼大作战",
        ["谁把月饼抖一地", "妈，月饼是它自己滚的"],
        max_len=10,
    )
    assert best4 == "妈，月饼是它自己滚的"

    # 候选与初稿相同/命中 avoid → 回退初稿
    assert pick_best_chat_title("月饼大作战", ["月饼大作战"], max_len=10) == "月饼大作战"

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
    # 不产出跨词坏碎片：偷看电视 → 电视（绝不「偷看电」）
    assert extract_core_anchor_words("偷看电视", {
        "scene_title": "偷看电视",
        "conflict_core": "姐弟趁妈妈洗澡偷看电视，约好轮班望风，结果露馅",
        "setting": "客厅，电视还黑着",
    }) == ["电视"]

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
    """锚点不含跨词坏碎片：偷看电视 只产出「电视」，「偷看电」绝不出现在要求里。"""
    from app.services.script.optimize_title import extract_core_anchor_words

    story = {
        "scene_title": "偷看电视",
        "conflict_core": "姐弟趁妈妈洗澡偷看电视，约好轮班望风，结果露馅",
        "setting": "客厅，电视还黑着，昭昭握着遥控器",
        "theme": "姐弟趁妈妈洗澡偷看电视",
    }
    anchors = extract_core_anchor_words("偷看电视", story)
    assert anchors == ["电视"]
    assert "偷看电" not in anchors

def test_select_optimized_title_degraded_truncation_falls_back():
    # 优化只是初稿删字截断 → 回退初稿
    assert select_optimized_title("藏玩具同盟", "藏玩具", max_len=10) == "藏玩具同盟"
    # 正常优化保留
    assert select_optimized_title("月饼大作战", "月饼全滚出来了", max_len=10) == "月饼全滚出来了"
    # 超长且初稿合法 → 回退初稿
    assert select_optimized_title("月饼大作战", "月饼大作战全都滚出来了", max_len=10) == "月饼大作战"
    # 初稿也超长 → 截断兜底（optimized 截到 max_len）
    assert select_optimized_title("月饼大作战全都滚出来了", "月饼大作战全都滚出来了呀", max_len=10) == "月饼大作战全都滚出来"
    # 仅标点/空白变化 → 保留来源标点
    assert select_optimized_title("检查不算吃！", "检查不算吃", max_len=10) == "检查不算吃！"
    # 带逗号 11 字标题钻 title_core 去标点 ≤max_len 的空子 → 超长回退初稿
    assert select_optimized_title("月饼大作战", "妈，月饼真不是我俩滚的", max_len=10) == "月饼大作战"

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

def test_theme_is_writable_rejects_oral_lie_without_eye():
    from app.services.daily_story.prompts import (
        filter_writable_themes,
        theme_is_writable,
    )

    assert not theme_is_writable("不许说谎妈妈刚才也敷衍奶奶")
    assert not theme_is_writable("讨论什么叫公平")
    assert theme_is_writable("九点了必须睡觉妈妈还在刷手机")
    assert theme_is_writable("饭前不能吃零食妈妈自己尝菜")
    assert theme_is_writable("争最后一瓶酸奶")
    kept = filter_writable_themes([
        "不许说谎妈妈刚才也敷衍奶奶",
        "九点了必须睡觉妈妈还在刷手机",
        "不许说谎妈妈刚才也敷衍奶奶",
    ])
    assert kept == ["九点了必须睡觉妈妈还在刷手机"]

def test_theme_quota_and_near_dedupe():
    from app.services.daily_story.prompts import (
        allocate_theme_type_quotas,
        filter_writable_themes,
        parse_typed_theme_lines,
        select_themes_by_quota,
        themes_near_duplicate,
    )

    assert allocate_theme_type_quotas(15) == {
        "A": 3, "B": 3, "C": 3, "D": 3, "E": 3,
    }
    assert themes_near_duplicate("争最后一瓶酸奶", "抢最后一瓶酸奶")
    assert not themes_near_duplicate("浇花别浇太多", "关门轻点没关严")

    typed = parse_typed_theme_lines(
        "C|争沙发上最后一块靠垫归谁\n"
        "C|争沙发靠垫归谁坐\n"
        "A|姐姐嫌弟弟刷牙沫溅一圈\n"
        "B|俩人约定藏起打翻的颜料\n"
        "D|浇花别浇太多结果溢出来\n"
        "E,A|说好不玩手机被窝屏幕还亮着\n"
        "胡说一行\n",
    )
    assert (("C",), "争沙发上最后一块靠垫归谁") in typed
    assert (("E", "A"), "说好不玩手机被窝屏幕还亮着") in typed
    picked = select_themes_by_quota(
        typed,
        {"A": 1, "B": 1, "C": 1, "D": 1, "E": 1},
        avoid=["争沙发靠垫"],
    )
    assert len(picked) == 5
    # C 近义被 avoid / 同批去重后应只留一条靠垫题或被 avoid 掉
    assert sum("靠垫" in r["theme"] for r in picked) <= 1
    assert all(isinstance(r["story_types"], list) and r["story_types"] for r in picked)
    primaries = {r["story_types"][0] for r in picked}
    assert primaries == {"A", "B", "C", "D", "E"}
    phone = next(r for r in picked if "手机" in r["theme"])
    assert phone["story_types"][0] == "E"
    assert "A" in phone["story_types"] or len(phone["story_types"]) >= 1

    near_filtered = filter_writable_themes(
        ["争最后一瓶酸奶", "抢最后一瓶酸奶喝", "浇花溢出来"],
        avoid=["争最后一瓶酸奶"],
    )
    assert near_filtered == ["浇花溢出来"]

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

@pytest.mark.parametrize(
    "line, ok",
    [
        ("你刚才还笑出声了呢妈妈你听听", False),
        ("大人工作需要，跟你们玩不一样啊听着", False),
        ("妈妈，你刚才还笑出声了呢", True),
    ],
    ids=["inverted", "trailing_listen", "vocative_start"],
)
def test_validate_daily_story_json_vocative_naturalness(line, ok):
    story = _valid_story()
    story["dialogue"][3]["line"] = line
    if ok:
        validate_daily_story_json(story)
    else:
        with pytest.raises(ValueError, match="语序不自然"):
            validate_daily_story_json(story)

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

def test_validate_daily_story_json_rejects_missing_key():
    story = _valid_story()
    del story["key"]
    with pytest.raises(ValueError, match="缺少必需字段: key"):
        validate_daily_story_json(story)

def test_build_daily_story_retry_user_asks_to_expand_short_draft():
    from app.services.daily_story.prompts import (
        build_daily_story_retry_user,
        resolve_daily_story_retry_length_mode,
    )

    prev = _valid_story(n=10)
    # 下限从 280 降到 240，10 句 × 24 字 = 240 刚好踩线，
    # gap=0 ≤ PATCH_DEFICIT_MAX(32) → revise_patch 而非 revise_expand
    assert resolve_daily_story_retry_length_mode(prev) == "revise_patch"
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
        "key": "饭前偷吃",
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
        DAILY_STORY_BODY_CHARS_MAX,
        build_daily_story_retry_user,
        dialogue_total_chars,
        resolve_daily_story_retry_length_mode,
    )
    from app.services.daily_story.dialogue_text import DAILY_STORY_LINE_CHARS_MAX

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
    ]
    total = dialogue_total_chars(barely)
    assert (
        DAILY_STORY_BODY_CHARS_MAX
        < total
        <= DAILY_STORY_BODY_CHARS_MAX + DAILY_STORY_LINE_CHARS_MAX
    )
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
    assert q["score"] >= 30
    attach_daily_story_quality(story)
    assert story["quality"]["score"] >= 30

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

def test_patch_d_no_content_rewrite():
    """D patch：删妈妈/压句数可以，但不改写干净台词的内容。"""
    from app.services.daily_story.prompts import try_local_patch_daily_story_body

    speakers = ("昭昭", "灿灿")
    dlg = [
        {"speaker": speakers[i % 2], "line": f"台词{i}一二三四五六七八"}
        for i in range(12)
    ]
    dlg[5] = {"speaker": "妈妈", "line": "汤都凉了赶紧放下别端"}
    story = {
        "scene_title": "端汤",
        "setting": "厨房餐桌边",
        "conflict_core": "端汤不许晃字面执行烫手",
        "dialogue": dlg,
        "punchline_explain": "D类字面执行，灿灿叮嘱不许晃",
    }
    patched, notes = try_local_patch_daily_story_body(story)
    # 妈妈插话被删（删除类规则允许）
    assert any("妈妈" in n for n in notes)
    assert not any(
        str(d.get("speaker") or "") == "妈妈" for d in patched["dialogue"]
    )
    # 其余台词一字未改（禁止模板改写）
    kept = [d["line"] for d in patched["dialogue"]]
    original = [d["line"] for d in story["dialogue"] if d["speaker"] != "妈妈"]
    assert kept == original

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

def test_validate_rejects_brush_duration_inconsistency():
    from app.services.daily_story.prompts import validate_daily_story_json

    story = {
        "scene_title": "刷牙快慢之争",
        "setting": "卫生间门口，昭昭刚刷完牙，灿灿拿着计时器拦住他。",
        "key": "刷牙计时",
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

def test_b_opening_rejects_fixup_lead_first_line():
    """B 开场首句禁止补救中段指令（快把/盖好），须先给发现/现状拍。"""
    from app.services.daily_story.story_types.b.opening import (
        append_b_opening_errors,
    )

    opening = [
        {"speaker": "昭昭", "line": "姐，快把裂口转过去，胶水瓶盖好。"},
        {"speaker": "灿灿", "line": "小声点，藏好别让妈看见。"},
    ]
    errors: list[str] = []
    append_b_opening_errors(opening, type_code="B", errors=errors)
    assert any("补救" in e for e in errors), errors

def test_b_freeze_only_ending_accepted():
    from app.services.daily_story.story_types.b.humor import (
        analyze_post_freeze_bloat,
        analyze_punish_landing,
    )

    lines = [
        "咱俩吃这包，你望风我拆",
        "哎，薯片滑出去了",
        "踩到了，鞋底黏了",
        "都怪你手太快！",
        "是你让我拆的！",
        "妈妈：地上怎么一地碎渣？",
        "妈妈：你俩，站好！！！",
        "昭昭：完蛋了！",
        "灿灿：真倒霉……",
    ]
    speakers = [
        "昭昭", "灿灿", "昭昭", "昭昭", "灿灿", "妈妈", "妈妈", "昭昭", "灿灿",
    ]
    weak, tag = analyze_punish_landing(lines, speakers)
    assert not weak, tag
    bloat, bloat_tag = analyze_post_freeze_bloat(lines, speakers)
    assert not bloat, bloat_tag

def test_b_landing_flags_post_freeze_blame():
    from app.services.daily_story.story_types.b.humor import (
        analyze_post_freeze_bloat,
        collect_humor_issues,
    )

    lines = [
        "结盟",
        "走样",
        "都怪你",
        "是你先",
        "妈妈：你俩，过来站好！",
        "昭昭：完蛋了！",
        "灿灿：真倒霉……",
        "昭昭：都怪你没望风！",
        "灿灿：哼，才不是。",
    ]
    speakers = [
        "昭昭", "灿灿", "昭昭", "灿灿", "妈妈", "昭昭", "灿灿", "昭昭", "灿灿",
    ]
    bloat, _ = analyze_post_freeze_bloat(lines, speakers)
    assert bloat
    issues = collect_humor_issues(lines, speakers)
    assert any("定格后多余对白" in c for c in issues)

@pytest.mark.parametrize(
    "lines, expect_orphan",
    [
        (
            [
                "结盟",
                "嘘妈在厨房",
                "好你拆",
                "啊呀，包装撕太大了！",
                "饼干蹦出来了，快用脚接！",
                "没接住，全掉地上了。",
                "我也踩到了，更糟了。",
                "别动脚，脚印会更多。",
            ],
            True,
        ),
        (
            [
                "结盟",
                "包装撕太大了",
                "我不小心踩上去了。",
                "我也踩到了，更糟了。",
                "别动脚。",
            ],
            False,
        ),
    ],
)
def test_b_chain_anaphora_wo_ye(lines, expect_orphan):
    from app.services.daily_story.story_types.b.humor import collect_chain_anaphora_issues

    issues = collect_chain_anaphora_issues(lines, None)
    has = any("我也缺前句动作" in i for i in issues)
    assert has is expect_orphan

@pytest.mark.parametrize(
    "line, prev2, expect_tag",
    [
        ("那我说你摔了，你哭得还带响。", "就说在草地上摔了个屁股蹲。你摔了还咧嘴笑。", None),
        ("他还踩了一脚泥。", "地上全是水。", "还字缺前句动作"),
    ],
)
def test_b_huan_chain_anaphora_tag(line, prev2, expect_tag):
    from app.services.daily_story.story_types.b.humor import _chain_anaphora_tag

    assert _chain_anaphora_tag(line, prev2) == expect_tag

def test_b_fact_accepts_mishap_chain_not_role_swap():
    """约定分工后虽有角色词与甩锅，但正文有真实连环走样，不算「无走样却改口」。"""
    from app.services.daily_story.story_types.b.facts import collect_fact_issues

    story = {
        "punchline_explain": "B类结盟翻车：姐弟联手偷吃，蛋糕掉地露馅",
        "conflict_core": "姐弟联手偷吃蛋糕，望风失误露馅",
        "dialogue": [
            {"speaker": "昭昭", "line": "我拿盘子，你盯门口"},
            {"speaker": "灿灿", "line": "好，一人一块，我望风"},
            {"speaker": "昭昭", "line": "嘘，妈在睡觉，放轻点"},
            {"speaker": "灿灿", "line": "哎呀，奶油粘手上了！"},
            {"speaker": "昭昭", "line": "快舔掉，别滴地上。"},
            {"speaker": "灿灿", "line": "蛋糕歪了，快扶住！"},
            {"speaker": "昭昭", "line": "扶住了，奶油蹭脸了。"},
            {"speaker": "灿灿", "line": "别笑，快擦掉！"},
            {"speaker": "昭昭", "line": "擦不掉，越擦越花。"},
            {"speaker": "灿灿", "line": "用水冲，水声哗哗。"},
            {"speaker": "昭昭", "line": "你手滑，碟子掉了！"},
            {"speaker": "灿灿", "line": "我接住了，蛋糕掉地上！"},
            {"speaker": "昭昭", "line": "别动，我拿纸，你踩到渣。"},
            {"speaker": "灿灿", "line": "我不敢抬脚，怕滑倒。"},
            {"speaker": "昭昭", "line": "都怪你没看好！"},
            {"speaker": "灿灿", "line": "是你自己搞砸的！"},
            {"speaker": "妈妈", "line": "你俩拿的什么！又偷吃！"},
            {"speaker": "昭昭", "line": "被发现了！"},
            {"speaker": "灿灿", "line": "这下死定了……"},
        ],
    }
    issues = collect_fact_issues(story)
    assert not any("无走样却改口" in i for i in issues)

def test_b_fact_rejects_division_flip():
    """分工翻转：开场昭昭望风，正文变灿灿盯门 → 硬卡。"""
    from app.services.daily_story.story_types.b.facts import _division_flip_error

    # 一致：L0 灿灿「我望风」→ 归灿灿；L1 昭昭「你盯着门口」→ 归灿灿；L2 同
    lines = [
        "姐，你拧瓶盖我望风",
        "嘘，我拧盖，你盯着门口",
        "行，我望风，你下手",
    ]
    sps = ["灿灿", "昭昭", "灿灿"]
    assert _division_flip_error(lines, sps) is None

    # 翻转：开场昭昭望风（L0 灿灿说「你望风」），正文灿灿盯门（L1 灿灿「我盯着」）
    lines2 = [
        "姐，你望风，我拧盖",
        "嘘，我盯着门口，你快点拧",
        "行，你望风，我下手",
    ]
    sps2 = ["灿灿", "灿灿", "昭昭"]
    err = _division_flip_error(lines2, sps2)
    assert err is not None and "分工翻转" in err, err

def test_b_blame_round_capped():
    """段4互甩只许一轮（≤2句），超过报硬卡。"""
    from app.services.daily_story.story_types.b.validate import (
        append_b_body_errors,
    )

    story = {
        "punchline_explain": "B类结盟翻车",
        "dialogue": [
            {"speaker": "昭昭", "line": "嘘，咱俩藏相框。"},
            {"speaker": "灿灿", "line": "我望风，你粘。"},
            {"speaker": "昭昭", "line": "胶水挤多了。"},
            {"speaker": "灿灿", "line": "你光顾着粘，没看妈！"},
            {"speaker": "昭昭", "line": "你也没喊我！"},
            {"speaker": "灿灿", "line": "都怪你乱动！"},
            {"speaker": "昭昭", "line": "是你自己搞砸的！"},
            {"speaker": "妈妈", "line": "满地胶水，站好！"},
            {"speaker": "昭昭", "line": "完蛋了。"},
            {"speaker": "灿灿", "line": "死定了。"},
        ],
    }
    errors: list[str] = []
    append_b_body_errors(story, errors)
    assert any("互甩只许一轮" in e for e in errors), errors

def test_b_blame_round_two_lines_ok():
    """段4互甩一轮（2句）不误伤。"""
    from app.services.daily_story.story_types.b.validate import (
        append_b_body_errors,
    )

    story = {
        "punchline_explain": "B类结盟翻车",
        "dialogue": [
            {"speaker": "昭昭", "line": "嘘，咱俩藏相框。"},
            {"speaker": "灿灿", "line": "我望风，你粘。"},
            {"speaker": "昭昭", "line": "胶水挤多了。"},
            {"speaker": "灿灿", "line": "都怪你没望风，妈都到客厅了！"},
            {"speaker": "昭昭", "line": "怪你挤那么多胶水！"},
            {"speaker": "妈妈", "line": "满地胶水，站好！"},
            {"speaker": "昭昭", "line": "完蛋了。"},
            {"speaker": "灿灿", "line": "死定了。"},
        ],
    }
    errors: list[str] = []
    append_b_body_errors(story, errors)
    assert not any("互甩只许一轮" in e for e in errors), errors

def test_b_watch_blame_flags_owner_deflect():
    """望风人自己反咬别人没望风 → 硬卡。"""
    from app.services.daily_story.story_types.b.facts import append_b_fact_errors

    story = {
        "punchline_explain": "B类结盟翻车",
        "dialogue": [
            {"speaker": "昭昭", "line": "姐，相框裂了。"},
            {"speaker": "灿灿", "line": "嘘，你拿着扫帚，我看着门。"},
            {"speaker": "昭昭", "line": "胶水挤多了。"},
            {"speaker": "灿灿", "line": "都怪你没望风，门都没关紧！"},
            {"speaker": "妈妈", "line": "站好！"},
            {"speaker": "昭昭", "line": "完蛋了。"},
            {"speaker": "灿灿", "line": "死定了。"},
        ],
    }
    errors: list[str] = []
    append_b_fact_errors(story, errors)
    assert any("望风" in e and "错位" in e for e in errors), errors

def test_b_watch_blame_accepts_targeting_owner():
    """甩锅指向望风人本身（昭昭怪灿灿没望风）→ 配套成立不误伤。"""
    from app.services.daily_story.story_types.b.facts import append_b_fact_errors

    story = {
        "punchline_explain": "B类结盟翻车",
        "dialogue": [
            {"speaker": "昭昭", "line": "姐，相框裂了。"},
            {"speaker": "灿灿", "line": "嘘，你粘，我看着门。"},
            {"speaker": "昭昭", "line": "胶水挤多了。"},
            {"speaker": "昭昭", "line": "都怪你没望风，妈都到客厅了！"},
            {"speaker": "妈妈", "line": "站好！"},
            {"speaker": "昭昭", "line": "完蛋了。"},
            {"speaker": "灿灿", "line": "死定了。"},
        ],
    }
    errors: list[str] = []
    append_b_fact_errors(story, errors)
    assert not any("错位" in e for e in errors), errors

def test_b_freeze_rejects_triple_side_ding():
    from app.services.daily_story.story_types.b.humor import _freeze_lines_issues

    assert _freeze_lines_issues(
        ["这下死定了……", "死定了死定了！", "死定了！"],
    ) == "死定了句式重复"

def test_b_validate_rejects_blood_content():
    from app.services.daily_story.story_types.b.validate import append_b_body_errors

    story = {
        "punchline_explain": "B类结盟翻车",
        "dialogue": [
            {"speaker": "昭昭", "line": "嘘，咱俩藏。"},
            {"speaker": "灿灿", "line": "我望风你扫。"},
            {"speaker": "昭昭", "line": "好，你手轻点。"},
            {"speaker": "灿灿", "line": "玻璃扎手流血了！"},
            {"speaker": "昭昭", "line": "快拿创可贴！"},
            {"speaker": "灿灿", "line": "血滴地上了。"},
            {"speaker": "昭昭", "line": "越擦越糟连锁。"},
            {"speaker": "妈妈", "line": "你俩，过来站好！"},
            {"speaker": "昭昭", "line": "完蛋了！"},
            {"speaker": "灿灿", "line": "惨了……"},
        ],
    }
    errors: list[str] = []
    append_b_body_errors(story, errors)
    assert any("流血" in e for e in errors)

def test_b_landing_flags_batch_weak_endings():
    from app.services.daily_story.story_types.b.humor import (
        analyze_post_freeze_bloat,
        analyze_punish_landing,
    )

    lines = [
        "结盟",
        "走样",
        "妈妈脚步声",
        "妈妈：你俩，过来！",
        "昭昭：被发现了！",
        "灿灿：都怪你望风没咳嗽！",
        "昭昭：哼，才不是我的主意。",
    ]
    speakers = [
        "昭昭", "灿灿", "灿灿", "妈妈", "昭昭", "灿灿", "昭昭",
    ]
    weak, _ = analyze_punish_landing(lines, speakers)
    bloat, _ = analyze_post_freeze_bloat(lines, speakers)
    assert weak or bloat

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
    assert any("定格" in e for e in errors)

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

def test_validate_rejects_dangling_what_is_term():
    from app.services.daily_story.prompts import validate_daily_story_json

    story = {
        "scene_title": "刷牙",
        "setting": "卫生间",
        "key": "连续刷牙",
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
        "key": "刷牙计时",
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

@pytest.mark.parametrize(
    "slot, line, speaker_order, needle",
    [
        (-4, "示范就能算错吗？", None, ("倒数第4句", "引前文灿灿原话")),
        (-3, "示范不算数", None, ("倒数第3句", "那不一样")),
        (-2, "都是停", None, ("倒数第2句", "哪里不一样")),
        (None, None, ("灿灿", "昭昭", "灿灿", "昭昭"), ("末4句 speaker",)),
        (-1, "行吧你改回来吧", None, ("末句禁止",)),
    ],
    ids=["no_quote", "no_bu_yiyang", "no_where", "speaker_order", "last_command"],
)
def test_a_closing_structure_rejects_slot(slot, line, speaker_order, needle):
    """A 末四拍各槽位硬卡（引话/那不一样/哪里不一样/speaker/末句禁管人）。"""
    story = _a_valid_body()
    if speaker_order is not None:
        for item, sp in zip(story["dialogue"][-4:], speaker_order, strict=True):
            item["speaker"] = sp
    else:
        story["dialogue"][slot]["line"] = line
    errors = _a_body_errors(story)
    assert any(all(n in e for n in needle) for e in errors), errors

def test_a_closing_structure_accepts_beat1_quote_with_comma():
    """倒数第4句「你刚才说，检查不算吃对吧」带逗号也算引话，不误杀。

    回归实测模型确实这样写；RE_CLOSING_QUOTE 要求引话紧贴「说」，
    硬卡须放行「说，+引话」的合法变体。
    """
    story = _a_valid_body()
    story["dialogue"][-4]["line"] = "你刚才说，检查不算吃对吧"
    errors = _a_body_errors(story)
    assert not any("倒数第4句" in e for e in errors), errors

def test_a_closing_structure_non_a_skipped():
    """非 A 类末四拍不套 A 结构硬卡（避免误伤）。"""
    from app.services.daily_story.story_types import parse_story_type_code

    story = _a_valid_body()
    story["punchline_explain"] = "C类公平执念"
    assert parse_story_type_code(punchline="C类公平执念") == "C"
    errors = _a_body_errors(story)
    assert not any("末四拍" in e for e in errors), errors

def _a_steal_body() -> dict:
    """A 类偷吃合法正文：前 4 句纯反咬赖账，末四拍完整。

    前 4 句灿灿只反咬（你嘴馋/果汁溅的），无检查/试甜字；
    末四拍 昭昭引原话→那不一样→哪里不一样→软破功。
    """
    return {
        "scene_title": "检查不算吃",
        "setting": "客厅茶几，水果盘少了一块，灿灿嘴角有果渣",
        "conflict_core": "灿灿偷吃苹果还立规矩",
        "punchline_explain": "A类权威翻车",
        "dialogue": [
            {"speaker": "昭昭", "line": "茶几上的苹果怎么少了一块"},
            {"speaker": "灿灿", "line": "明明是你嘴馋，别赖我"},
            {"speaker": "昭昭", "line": "你嘴里鼓鼓囊囊嚼的是啥"},
            {"speaker": "灿灿", "line": "那是果汁溅的，我擦擦就行"},
            {"speaker": "昭昭", "line": "上次你偷吃巧克力也这套话"},
            {"speaker": "灿灿", "line": "我是姐姐，规矩我定的"},
            {"speaker": "昭昭", "line": "那你这口怎么算"},
            {"speaker": "灿灿", "line": "这是检查样品，特地挑的"},
            {"speaker": "昭昭", "line": "检查样品就能整块吃掉？"},
            {"speaker": "灿灿", "line": "检查不算吃，咽下去才算"},
            {"speaker": "昭昭", "line": "那你吐出来给我看看"},
            {"speaker": "灿灿", "line": "已经咽下去了，看不了"},
            {"speaker": "昭昭", "line": "你刚才说检查不算吃"},
            {"speaker": "灿灿", "line": "那不一样，检样不算开饭"},
            {"speaker": "昭昭", "line": "哪里不一样，都进肚子了"},
            {"speaker": "灿灿", "line": "行吧，给你一块，别哭了"},
        ],
    }

def test_a_steal_rejects_check_word_in_first_four():
    """偷吃对白前 4 句出现检查/试甜类字：硬卡须拦（模型实测反复违规）。"""
    story = _a_steal_body()
    story["dialogue"][3]["line"] = "我这是帮你试试苹果甜不甜"
    errors = _a_body_errors(story)
    assert any("检查线前置" in e for e in errors), errors

def test_a_steal_accepts_clean_first_four_repel():
    """偷吃前 4 句纯反咬赖账（你嘴馋/果汁溅的）：硬卡放行。"""
    story = _a_steal_body()
    errors = _a_body_errors(story)
    assert not any("检查线前置" in e for e in errors), errors

def test_a_steal_check_early_skips_non_steal():
    """非偷吃主题（刷牙）前 4 句含检查字不套偷吃硬卡（避免误伤）。"""
    story = _a_valid_body()
    story["dialogue"][0]["line"] = "你检查牙呢？才刷几下啊"
    errors = _a_body_errors(story)
    assert not any("检查线前置" in e for e in errors), errors

def test_attach_daily_story_quality_finalizes_structure_plus_regex_humor():
    """保存路径：attach 后总分 = 结构 + 正则好笑。"""
    from app.services.daily_story.quality import (
        attach_daily_story_quality,
        score_daily_story,
    )

    story = {
        "scene_title": "叠好的衣服",
        "setting": "客厅沙发衣服被翻乱",
        "conflict_core": "姐弟争谁收拾叠好的衣服",
        "dialogue": [
            {"speaker": "灿灿", "line": "沙发上那堆衣服谁弄乱的"},
            {"speaker": "昭昭", "line": "不是我呀，我刚从房间出来"},
            {"speaker": "灿灿", "line": "你脚边全是皱的，肯定你翻过"},
            {"speaker": "昭昭", "line": "那是猫弄的，你看这爪印"},
            {"speaker": "灿灿", "line": "猫不会把叠好的翻开，你弄乱谁收拾"},
            {"speaker": "昭昭", "line": "谁弄乱谁收拾？你刚才也伸手碰了"},
            {"speaker": "灿灿", "line": "我碰一下怎么算翻"},
            {"speaker": "昭昭", "line": "你说的谁弄乱谁收拾呢"},
            {"speaker": "灿灿", "line": "哼算你狠我自己来"},
        ],
        "punchline_explain": "C类公平执念，赛规字面回旋镖",
        "discovery_opening": [
            {"speaker": "灿灿", "line": "沙发上那堆衣服谁弄乱的"},
            {"speaker": "昭昭", "line": "不是我呀，我刚从房间出来"},
        ],
    }
    raw = score_daily_story(story, theme="弄乱叠好的衣服")
    attach_daily_story_quality(story, theme="弄乱叠好的衣服")
    q = story["quality"]
    structure = int(q["structure_score"])
    humor = int(q["humor_regex_points"])
    assert q["score"] == min(100, structure + humor), q
    assert q["score"] >= structure
    assert raw["score"] == structure

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

def test_validate_c_body_rejects_rule_drift_no_verdict():
    """C 稿换比法/重开 ≥3 次且无人宣判旧局 → 赛规漂移硬卡（稿B 型）。"""
    story = _valid_story()
    dialogue = story["dialogue"]
    # 中段塞 3 句无宣判的换比法：重新 / 重来 / 换一种，且避开末段收束。
    # 注意不用「数到三」——2026-08-09 修正：数到三是对启动方式提公平条件
    # （接规三选一②），不是换比法，已移出 RE_RULE_SWITCH（见 validate.py 注释）。
    dialogue[4] = {"speaker": dialogue[4]["speaker"], "line": _pad_line("好咱们重新开一局呀")}
    dialogue[6] = {"speaker": dialogue[6]["speaker"], "line": _pad_line("那重来再比一次呀")}
    dialogue[9] = {"speaker": dialogue[9]["speaker"], "line": _pad_line("都不行换一种比法呀")}
    with pytest.raises(ValueError, match="赛规漂移|规则被反复单方面推翻"):
        validate_daily_story_json(story, phase="body")

def test_validate_c_body_allows_rule_drift_with_verdict():
    """换比法后有人宣判（妈妈裁定/明明说）→ 放行，不算漂移。"""
    story = _valid_story()
    dialogue = story["dialogue"]
    dialogue[4] = {"speaker": dialogue[4]["speaker"], "line": _pad_line("好咱们重新开一局呀")}
    dialogue[6] = {"speaker": dialogue[6]["speaker"], "line": _pad_line("那重来再比一次呀")}
    dialogue[9] = {"speaker": dialogue[9]["speaker"], "line": _pad_line("妈妈说定了先拿先选呀")}
    validate_daily_story_json(story, phase="body")

@pytest.mark.parametrize(
    "edits, match",
    [
        ({4: "谁先咬到谁吃呀"}, "判据漂移"),
        ({4: "碰到不算拿到才算呀"}, "判据漂移"),
        ({4: "抓到手不算攥稳才算呀", 7: "攥稳不算握死才算呀"}, "分级杠精"),
    ],
)
def test_validate_c_body_rejects_criterion_drift(edits, match):
    """C 判据漂移/分级杠精硬卡（消耗、占有态、接触弱词、分级杠）。"""
    story = _valid_story()
    dialogue = story["dialogue"]
    for idx, text in edits.items():
        dialogue[idx] = {"speaker": dialogue[idx]["speaker"], "line": _pad_line(text)}
    with pytest.raises(ValueError, match=match):
        validate_daily_story_json(story, phase="body")

def test_validate_c_body_accepts_possession_criterion():
    """占有系判据（谁先拿到归谁吃）放行，不误伤。"""
    story = _valid_story()
    dialogue = story["dialogue"]
    dialogue[4] = {"speaker": dialogue[4]["speaker"], "line": _pad_line("谁先拿到归谁吃呀")}
    validate_daily_story_json(story, phase="body")

def _mom_ruling_check(speakers, lines):
    from app.services.daily_story.story_types.c.validate import _mom_ruling_ignored_error

    return _mom_ruling_ignored_error(speakers, lines)

@pytest.mark.parametrize(
    "speakers, lines, expect_err",
    [
        (
            ["昭昭", "灿灿", "妈妈", "昭昭", "灿灿", "昭昭", "灿灿"],
            ["a", "b", "c", "d", "e", "我先碰的", "我先碰的你碰晚了"],
            True,
        ),
        (
            ["昭昭", "妈妈", "灿灿", "昭昭", "灿灿"],
            ["a", "b", "c", "d", "妈妈刚说谁先碰到谁用呀"],
            False,
        ),
        (
            ["昭昭", "灿灿", "昭昭", "灿灿"],
            ["a", "b", "c", "d"],
            False,
        ),
    ],
)
def test_c_mom_ruling_ignored(speakers, lines, expect_err):
    """妈妈裁定后僵局硬卡；引用原规或无妈妈则放行。"""
    err = _mom_ruling_check(speakers, lines)
    if expect_err:
        assert err and "妈妈" in err and "僵局" in err
    else:
        assert err is None

def test_b_patch_splits_consecutive_with_bridge():
    from app.services.daily_story.story_types.b.patch import patch_b_body
    from app.services.daily_story.prompts import try_local_patch_daily_story_body

    story = {
        "punchline_explain": "B类结盟翻车，姐弟瞒妈妈扫碎片",
        "dialogue": [
            {"speaker": "昭昭", "line": "姐姐地上怎么这么多碎片。"},
            {"speaker": "灿灿", "line": "你扫我拿桶，别告诉妈。"},
            {"speaker": "灿灿", "line": "哎呀全扫桌布上了！"},
            {"speaker": "昭昭", "line": "你别掀了全是渣！"},
            {"speaker": "灿灿", "line": "别动扎脚咋办！"},
            {"speaker": "昭昭", "line": "我也不敢用手捡。"},
            {"speaker": "灿灿", "line": "听妈妈脚步声！"},
            {"speaker": "灿灿", "line": "都怪你扫太大劲！"},
            {"speaker": "妈妈", "line": "你俩过来！"},
            {"speaker": "昭昭", "line": "被发现了！"},
            {"speaker": "灿灿", "line": "这下死定了……"},
        ],
    }
    notes = patch_b_body(story)
    assert any("插接话" in n for n in notes)
    dlg = story["dialogue"]
    for i in range(1, len(dlg)):
        a, b = dlg[i - 1], dlg[i]
        if a["speaker"] in ("昭昭", "灿灿") and a["speaker"] == b["speaker"]:
            pytest.fail(f"still consecutive at {i}")

    raw = {
        "punchline_explain": "B类结盟翻车，姐弟瞒妈妈扫碎片",
        "dialogue": [
            {"speaker": "灿灿", "line": "你扫我拿桶。"},
            {"speaker": "灿灿", "line": "哎呀全扫桌布上了！"},
            {"speaker": "妈妈", "line": "你俩过来！"},
        ],
    }
    _, local_notes = try_local_patch_daily_story_body(raw)
    assert not any("连说改speaker" in n for n in local_notes)
    assert any("B插接话" in n for n in local_notes)

def test_b_patch_strips_orphan_ye():
    from app.services.daily_story.story_types.b.patch import patch_b_orphan_ye

    story = {
        "punchline_explain": "B类结盟翻车",
        "dialogue": [
            {"speaker": "昭昭", "line": "嘘咱俩快扫。"},
            {"speaker": "灿灿", "line": "好你拿桶我扫。"},
            {"speaker": "灿灿", "line": "哎呀全扫桌布上了！"},
            {"speaker": "昭昭", "line": "你别掀了全是渣！"},
            {"speaker": "灿灿", "line": "别动扎脚咋办！"},
            {"speaker": "昭昭", "line": "我也不敢用手捡。"},
            {"speaker": "妈妈", "line": "你俩过来！"},
            {"speaker": "昭昭", "line": "完蛋了！"},
        ],
    }
    notes = patch_b_orphan_ye(story)
    assert notes
    assert story["dialogue"][5]["line"] == "我不敢用手捡。"

def test_validate_e_lie_rejects_batch3_garbage():
    from app.services.daily_story.prompts import (
        validate_daily_story_json,
        validate_daily_story_opening,
    )

    story = {
        "_theme": "不许说谎妈妈刚才也敷衍奶奶",
        "scene_title": "不许说谎",
        "setting": "客厅，妈妈刚打完电话",
        "key": "不许说谎",
        "conflict_core": "妈妈说不能说谎，自己却敷衍奶奶",
        "punchline_explain": "E类妈妈破功，不能说谎被闭环",
        "discovery_opening": [
            {"speaker": "昭昭", "line": "妈，你电话里跟奶奶说吃撑了是吧？"},
            {"speaker": "妈妈", "line": "我这不是敷衍，是让奶奶放心。"},
        ],
        "dialogue": [
            {"speaker": "昭昭", "line": "妈，你电话里跟奶奶说吃撑了是吧？"},
            {"speaker": "妈妈", "line": "我这不是敷衍，是让奶奶放心。"},
            {"speaker": "妈妈", "line": "对人要诚实，不能说谎，记住了吗？"},
            {"speaker": "灿灿", "line": "奶奶问你吃饭没，你说吃了好多好吃的呢。"},
            {"speaker": "昭昭", "line": "那你刚才那一口算不算啊"},
            {"speaker": "妈妈", "line": "我说什么了？就说我们挺好的呀。"},
            {"speaker": "灿灿", "line": "你说吃了红烧鱼清蒸虾，冰箱里都没有。"},
            {"speaker": "妈妈", "line": "那不一样，我不想让奶奶担心。"},
            {"speaker": "昭昭", "line": "你自己说不能说谎，那你刚才算不算？"},
            {"speaker": "妈妈", "line": "……行行行，我错了，以后不敷衍了。"},
        ],
    }
    with pytest.raises(ValueError, match="尝菜串场|说谎"):
        validate_daily_story_json(story, phase="full")
    with pytest.raises(ValueError, match="说谎开场"):
        validate_daily_story_opening(
            story["discovery_opening"],
            conflict_core=story["conflict_core"],
            setting=story["setting"],
            type_code="E",
        )

def test_validate_e_lie_accepts_compact_positive():
    from app.services.daily_story.story_types.e.opening import append_e_opening_errors
    from app.services.daily_story.story_types.e.validate import append_e_body_errors

    story = {
        "_theme": "不许说谎妈妈刚才也敷衍奶奶",
        "scene_title": "不许说谎",
        "setting": "客厅，妈妈刚打完电话",
        "conflict_core": "妈妈说不能说谎，自己却敷衍奶奶",
        "punchline_explain": "E类妈妈破功，不能说谎被闭环",
        "dialogue": [
            {"speaker": "昭昭", "line": "妈，你电话里跟奶奶说吃撑了是吧？"},
            {"speaker": "妈妈", "line": "对人要诚实，不能说谎，记住了。"},
            {
                "speaker": "灿灿",
                "line": "你说吃了三碗，那锅里为什么一粒米都没有？",
            },
            {"speaker": "妈妈", "line": "那是善意的，不让奶奶担心。"},
            {"speaker": "昭昭", "line": "我肚子还咕咕叫，碗都是干的呢。"},
            {
                "speaker": "灿灿",
                "line": "那我跟奶奶说我考了一百分，也算善意的吧？",
            },
            {"speaker": "妈妈", "line": "那可不行，你那是骗人。"},
            {"speaker": "昭昭", "line": "你自己说不能说谎，那你刚才算不算？"},
            {"speaker": "妈妈", "line": "……行行行，我错了，以后不敷衍了。"},
        ],
    }
    body_errs: list[str] = []
    append_e_body_errors(story, body_errs)
    assert body_errs == []

    open_errs: list[str] = []
    append_e_opening_errors(
        [
            {"speaker": "昭昭", "line": "妈，你电话里跟奶奶说吃撑了是吧？"},
            {"speaker": "妈妈", "line": "对人要诚实，不能说谎，记住了。"},
        ],
        type_code="E",
        errors=open_errs,
        conflict_core=story["conflict_core"],
        setting=story["setting"],
    )
    assert open_errs == []

def test_validate_e_picky_rejects_catch_before_rule():
    """现行=规矩名：禁先问拨开再答不许挑食；须妈妈开场。"""
    from app.services.daily_story.story_types.e.opening import append_e_opening_errors
    from app.services.daily_story.story_types.e.validate import append_e_body_errors

    story = {
        "_story_type": "E",
        "_theme": "吃饭不许挑食妈妈把青菜拨到碗边",
        "scene_title": "拨到碗边的青菜",
        "setting": "餐桌旁",
        "conflict_core": "妈妈说不许挑食自己却拨开青菜",
        "dialogue": [
            {"speaker": "昭昭", "line": "妈，你碗边上那些青菜怎么都拨开了？"},
            {"speaker": "妈妈", "line": "吃饭不许挑食，青菜都得吃。"},
            {"speaker": "灿灿", "line": "可你自己碗边也堆了一大堆。"},
            {"speaker": "妈妈", "line": "我这是晾着，等会儿配饭吃。"},
            {"speaker": "昭昭", "line": "晾了半天还不动筷子，算不算挑？"},
            {"speaker": "灿灿", "line": "那我把肉拨开，也算晾着配饭？"},
            {"speaker": "昭昭", "line": "你自己说吃饭不许挑食。"},
            {"speaker": "妈妈", "line": "……行行行，我夹起来吃了啊。"},
        ],
    }
    body_errs: list[str] = []
    append_e_body_errors(story, body_errs)
    assert any("妈妈开场训" in e or "因果反了" in e for e in body_errs)

    open_errs: list[str] = []
    append_e_opening_errors(
        story["dialogue"][:2],
        type_code="E",
        errors=open_errs,
        conflict_core=story["conflict_core"],
        setting=story["setting"],
    )
    assert any("妈妈先训" in e or "因果反了" in e for e in open_errs)

def test_validate_e_picky_accepts_rule_before_catch():
    from app.services.daily_story.story_types.e.opening import append_e_opening_errors
    from app.services.daily_story.story_types.e.validate import append_e_body_errors

    story = {
        "_story_type": "E",
        "_theme": "吃饭不许挑食妈妈把青菜拨到碗边",
        "scene_title": "拨到碗边的青菜",
        "setting": "餐桌旁",
        "conflict_core": "妈妈说不许挑食自己却拨开青菜",
        "dialogue": [
            {"speaker": "妈妈", "line": "昭昭，你最近菜吃得太少了，不能挑食哦"},
            {"speaker": "昭昭", "line": "那你怎么把青菜拨到碗边上去了？"},
            {"speaker": "妈妈", "line": "我这是晾着，等会儿配饭吃。"},
            {"speaker": "灿灿", "line": "晾了半天还不动筷子，算不算挑？"},
            {"speaker": "昭昭", "line": "那我把肉拨开，也算晾着配饭？"},
            {"speaker": "灿灿", "line": "你自己说不能挑食。"},
            {"speaker": "昭昭", "line": "那你拨开算不算挑食？"},
            {"speaker": "妈妈", "line": "……行行行，我夹起来吃了啊。"},
        ],
    }
    body_errs: list[str] = []
    append_e_body_errors(story, body_errs)
    assert not any("因果反了" in e or "妈妈开场训" in e for e in body_errs)

    open_errs: list[str] = []
    append_e_opening_errors(
        story["dialogue"][:2],
        type_code="E",
        errors=open_errs,
        conflict_core=story["conflict_core"],
        setting=story["setting"],
    )
    assert open_errs == []

def _review_story() -> dict:
    return {
        "setting": "客厅",
        "conflict_core": "妈妈说不能说谎自己敷衍奶奶",
        "dialogue": [
            {"speaker": "昭昭", "line": "妈，你跟奶奶说吃撑了，可你没吃。"},
            {"speaker": "妈妈", "line": "对人要诚实，不能说谎。"},
            {"speaker": "灿灿", "line": "行！"},
            {"speaker": "妈妈", "line": "那是善意的，不让奶奶担心。"},
            {"speaker": "昭昭", "line": "妈，你跟奶奶说吃撑了，可你没吃。"},
        ],
        "discovery_opening": [
            {"speaker": "昭昭", "line": "妈，你跟奶奶说吃撑了，可你没吃。"},
            {"speaker": "妈妈", "line": "对人要诚实，不能说谎。"},
        ],
    }

@pytest.mark.parametrize(
    "story_factory, expect_kinds",
    [
        ("dup", {("重复", (1, 5)), ("其他", (3,))}),
        ("short_tail", set()),
        ("mid_empty", {("其他", (2,))}),
    ],
    ids=["dup_and_empty", "short_tail_ok", "mid_empty"],
)
def test_review_local_issues_empty_and_dup(story_factory, expect_kinds):
    from app.services.daily_story.review import collect_local_issues

    if story_factory == "dup":
        story = _review_story()
    elif story_factory == "short_tail":
        story = {
            "dialogue": [
                {"speaker": "昭昭", "line": "你刚说谁先碰到谁切，我贴上了！"},
                {"speaker": "灿灿", "line": "你作弊，我手还悬在上面呢！"},
                {"speaker": "昭昭", "line": "哼。"},
            ],
        }
    else:
        story = {
            "dialogue": [
                {"speaker": "昭昭", "line": "你刚说谁先碰到谁切，我贴上了！"},
                {"speaker": "灿灿", "line": "行！"},
                {"speaker": "昭昭", "line": "哼。"},
            ],
        }
    issues = collect_local_issues(story)
    kinds = {(it["kind"], tuple(it["lines"])) for it in issues}
    if story_factory == "short_tail":
        assert not any(it["kind"] == "其他" for it in issues), issues
    else:
        assert expect_kinds <= kinds, kinds

def test_review_topic_cluster_catches_repeated_challenge():
    """同一质问换词三遍，近邻检测抓不到时靠话题聚类。"""
    from app.services.daily_story.review import collect_local_issues

    story = {
        "dialogue": [
            {"speaker": "昭昭", "line": "妈，你电话里跟奶奶说吃了三碗饭？"},
            {"speaker": "妈妈", "line": "对人要诚实，不能说谎。"},
            {"speaker": "昭昭", "line": "那你为啥要说三碗？"},
            {"speaker": "妈妈", "line": "那是善意的，不让奶奶担心。"},
            {"speaker": "昭昭", "line": "锅里一粒米都没有。"},
            {"speaker": "灿灿", "line": "那你电话里为啥说吃撑了呢？"},
            {"speaker": "灿灿", "line": "那我跟奶奶说我考了一百分，也算善意？"},
            {"speaker": "妈妈", "line": "那可不行，你那是骗人。"},
            {"speaker": "昭昭", "line": "你自己说不能说谎，那你刚才算不算？"},
            {"speaker": "妈妈", "line": "……行行行，我错了。"},
        ],
    }
    issues = collect_local_issues(story)
    topic = [it for it in issues if "质问电话撒谎" in it["desc"]]
    assert topic, issues
    assert set(topic[0]["lines"]) >= {1, 3, 6}

def test_review_merge_issues_dedups_overlapping_lines():
    from app.services.daily_story.review import merge_issues

    merged = merge_issues(
        [{"lines": [11, 14], "kind": "重复", "desc": "a", "fix": ""}],
        [{"lines": [3, 11, 14], "kind": "重复", "desc": "b", "fix": ""}],
    )
    assert len(merged) == 1
    assert merged[0]["lines"] == [3, 11, 14]

def _review_mock_story() -> dict:
    """A 类「开场副本与正文第3句换词复读」场景（local 检测器抓不到）。"""
    return {
        "scene_title": "抢遥控器",
        "setting": "客厅",
        "conflict_core": "灿灿立规矩管遥控器自己说错",
        "punchline_explain": "A类权威翻车：灿灿说错动画片细节被昭昭戳穿",
        "dialogue": [
            {"speaker": "昭昭", "line": "客厅沙发上遥控器怎么不在老位置"},
            {"speaker": "灿灿", "line": "我正抱着它看动画片呢，别想拿走"},
            {"speaker": "昭昭", "line": "客厅茶几上遥控器怎么攥你手里"},
            {"speaker": "灿灿", "line": "我正看动画片呢，别跟我抢"},
            {"speaker": "昭昭", "line": "那你先说说这部片叫啥名字"},
            {"speaker": "灿灿", "line": "这有什么难，叫汪汪队立大功"},
            {"speaker": "昭昭", "line": "你说说看，片里那只狗叫啥"},
            {"speaker": "灿灿", "line": "行吧，遥控器给你，你看吧"},
        ],
        "discovery_opening": [
            {"speaker": "昭昭", "line": "客厅沙发上遥控器怎么不在老位置"},
            {"speaker": "灿灿", "line": "我正抱着它看动画片呢，别想拿走"},
        ],
        "quality": {"score": 80, "grade": "好", "reasons": []},
    }

class _ReviewMockClient:
    """审读/定点修次数可控的 mock client。"""

    def __init__(self, review_results, fix_responses):
        self._reviews = list(review_results)
        self._fixes = list(fix_responses)
        self.review_calls = 0
        self.fix_calls = 0

    def review_daily_story_issues(self, theme, story):
        self.review_calls += 1
        item = self._reviews.pop(0) if self._reviews else []
        if isinstance(item, tuple):  # (issues, humor) 显式带好笑评估
            return item
        return item, None

    def spot_fix_daily_story(self, theme, story, issues):
        self.fix_calls += 1
        return self._fixes.pop(0) if self._fixes else {}

def _patch_review_llm(monkeypatch):
    """隔离定点修对 validate/patch/quality 的依赖，聚焦 review 流程行为。

    validate/patch/quality 本身有独立测试，这里只验证
    「remaining 触发第二轮、allowed 过滤设计行、修掉的不再扣分」。
    """
    from app.services.daily_story import prompts, quality

    monkeypatch.setattr(prompts, "validate_daily_story_json", lambda *a, **k: None)
    monkeypatch.setattr(
        prompts,
        "try_local_patch_daily_story_body",
        lambda story, *a, **k: (story, []),
    )
    monkeypatch.setattr(quality, "attach_daily_story_quality", lambda *a, **k: None)

def test_review_second_round_fixes_design_line_dup(monkeypatch):
    """开场副本与正文第3句换词复读：复审才报出，第二轮应修掉而非只扣分。"""
    _patch_review_llm(monkeypatch)
    from app.services.daily_story.review import run_daily_story_review

    client = _ReviewMockClient(
        review_results=[
            [{"lines": [5, 7], "kind": "重复", "desc": "正文重复", "fix": "改第7句"}],
            [
                {
                    "lines": [1, 3],
                    "kind": "重复",
                    "desc": "第3句重复第1句问遥控器位置",
                    "fix": "第3句改问别的",
                },
                {
                    "lines": [2, 4],
                    "kind": "重复",
                    "desc": "第4句重复第2句",
                    "fix": "第4句改问别的",
                },
            ],
        ],
        fix_responses=[
            {},  # 首轮不修，让复审保留问题
            {
                "fixes": [
                    {"no": 3, "line": "你手里拿的什么，给我看看"},
                    {"no": 4, "line": "我正看到关键处，你等会儿"},
                ]
            },
        ],
    )
    out = run_daily_story_review(client, "抢遥控器看动画片", _review_mock_story())

    assert client.fix_calls == 2  # 第二轮定点修被触发
    assert out["dialogue"][2]["line"] == "你手里拿的什么，给我看看"  # 第3句真被改
    assert out["dialogue"][3]["line"] == "我正看到关键处，你等会儿"
    # 开场片头副本（第1、2句）不能被动
    assert out["dialogue"][0]["line"] == "客厅沙发上遥控器怎么不在老位置"
    assert out["dialogue"][1]["line"] == "我正抱着它看动画片呢，别想拿走"
    q = out["quality"]
    assert q["score"] == 80  # 重复被修掉，不再扣分
    assert not any(
        1 in it.get("lines", []) or 2 in it.get("lines", [])
        for it in q.get("review_issues", [])
    )

def test_review_fixable_body_lines_skips_design_rows():
    """第二轮可修行：排除开场片头副本与末段原话闭环，只留正文。"""
    from app.services.daily_story.review import _fixable_body_lines

    story = _review_mock_story()
    story["dialogue"][5] = {"speaker": "灿灿", "line": "你自己说轮流看，怎么攥着不放"}
    issues = [
        {"lines": [1, 3], "kind": "重复", "desc": "开场vs正文", "fix": ""},
        {"lines": [2, 4], "kind": "重复", "desc": "开场vs正文", "fix": ""},
        {"lines": [6], "kind": "重复", "desc": "末段闭环", "fix": ""},
        {"lines": [7], "kind": "重复", "desc": "正文可修", "fix": ""},
    ]
    assert _fixable_body_lines(issues, story) == {3, 4, 7}

@pytest.mark.parametrize(
    "payload, check",
    [
        (
            {
                "issues": [
                    {"lines": [2], "kind": "矛盾", "desc": "有效"},
                    {"lines": [99], "kind": "矛盾", "desc": "行号越界"},
                    {"lines": [1], "kind": "矛盾", "desc": ""},
                ],
            },
            "out_of_range",
        ),
        (
            {
                "issues": [
                    {"lines": [1], "kind": "书面", "desc": "风格1", "fix": ""},
                    {"lines": [2], "kind": "书面", "desc": "风格2", "fix": ""},
                    {"lines": [3], "kind": "书面", "desc": "风格3", "fix": ""},
                    {"lines": [4], "kind": "矛盾", "desc": "硬伤", "fix": ""},
                ],
            },
            "severity_caps",
        ),
    ],
    ids=["out_of_range", "severity_caps"],
)
def test_review_parse_issues_kinds_and_caps(payload, check):
    from app.services.daily_story.review import parse_review_issues

    parsed = parse_review_issues(payload, line_count=5)
    if check == "out_of_range":
        assert [it["desc"] for it in parsed] == ["有效"]
    else:
        assert parsed[0]["kind"] == "矛盾"
        assert sum(1 for it in parsed if it["kind"] == "书面") <= 2

def test_strip_action_declaration_removes_verbose_announcement():
    from app.services.daily_story.review import _strip_action_declaration

    assert (
        _strip_action_declaration("让开，我来扯掉这夹子，袜子都被你毁了！")
        == "让开，袜子都被你毁了！"
    )
    assert (
        _strip_action_declaration("让开，我来把夹子拿下来，袜子都被你弄坏了！")
        == "让开，袜子都被你弄坏了！"
    )
    assert _strip_action_declaration("我来关！") == "我来关！"
    assert _strip_action_declaration("我来帮你拿东西") == "我来帮你拿东西"
    assert (
        _strip_action_declaration("整个托盘汪着水，花根都要泡烂了，我抢过壶。")
        == "整个托盘汪着水，花根都要泡烂了。"
    )
    assert (
        _strip_action_declaration(
            "我举壶猛灌到托盘溢满，这不就是你之前说的效果。"
        )
        == "这不就是你之前说的效果。"
    )

def test_fix_missing_tone_particle_adds_ba():
    from app.services.daily_story.review import _fix_missing_tone_particle

    assert (
        _fix_missing_tone_particle("水从盆底渗出来了，你满意了，快把水壶放下。")
        == "水从盆底渗出来了，你满意了吧，快把水壶放下。"
    )
    assert _fix_missing_tone_particle("你满意了吧。") == "你满意了吧。"

def test_collect_wording_issues_flags_written_lines():
    from app.services.daily_story.review import collect_wording_issues

    story = {
        "dialogue": [
            {"speaker": "昭昭", "line": "你说要夹紧，让袜子印上深痕。"},
        ],
        "discovery_opening": [],
    }
    issues = collect_wording_issues(story)
    assert issues
    assert issues[0]["lines"] == [1]
    assert issues[0]["kind"] == "书面"

def test_d_soft_tail_half_sentence_rules():
    from app.services.daily_story.story_types.d.validate import (
        _RE_SOFT_TAIL_BANNED,
        _RE_SOFT_TAIL_OK_END,
    )

    ok = "哼，行吧，这袜子算是白洗了。"
    bad = "哼，行吧，以后都轻拿轻放。"
    assert not _RE_SOFT_TAIL_BANNED.search(ok)
    assert _RE_SOFT_TAIL_OK_END.search(ok)
    assert _RE_SOFT_TAIL_BANNED.search(bad)

def test_d_literal_marker_accepts_plain_ni_shuo():
    from app.services.daily_story.story_types.d.humor import RE_BOOM_CLOSE
    from app.services.daily_story.story_types.d.validate import RE_LITERAL_MID

    line = "你说别浇太多，离‘太多’还差半壶呢。"
    assert RE_LITERAL_MID.search(line)
    assert not RE_BOOM_CLOSE.search(line)

def test_review_apply_spot_fixes_strips_prefix_and_syncs_opening():
    from app.services.daily_story.review import apply_spot_fixes

    fixed, notes = apply_spot_fixes(
        _review_story(),
        {"fixes": [{"no": 1, "line": "昭昭：妈，你刚才跟奶奶说啥了？"}]},
    )
    assert notes == ["第1句"]
    assert fixed["dialogue"][0]["line"] == "妈，你刚才跟奶奶说啥了？"
    assert fixed["discovery_opening"][0]["line"] == "妈，你刚才跟奶奶说啥了？"

def test_review_penalty_and_quality_deduction():
    """审读扣分封顶，并写入 quality；带 LLM 好笑时仍扣硬伤。"""
    from app.services.daily_story.review import (
        REVIEW_PENALTY_CAP,
        apply_review_to_quality,
        review_penalty,
    )

    points, reasons = review_penalty([
        {"lines": [5, 8], "kind": "重复", "desc": "碗干说两遍", "fix": ""},
        {"lines": [10], "kind": "示范", "desc": "妈妈教孩子隐瞒", "fix": ""},
    ])
    assert points == 15
    assert reasons[0].startswith("审读第5、8句重复：")
    many = [
        {"lines": [i], "kind": "示范", "desc": "坏示范", "fix": ""}
        for i in range(1, 6)
    ]
    assert review_penalty(many)[0] == REVIEW_PENALTY_CAP

    story = {
        "dialogue": [{"speaker": "昭昭", "line": "话"}],
        "quality": {"grade": "好", "score": 89, "summary": "旧", "reasons": ["好笑9"]},
    }
    apply_review_to_quality(story, [
        {"lines": [10], "kind": "示范", "desc": "妈妈教孩子隐瞒", "fix": ""},
    ])
    assert story["quality"]["score"] == 79
    assert "审读第10句示范" in story["quality"]["summary"]
    assert story["quality"]["review_issues"][0]["kind"] == "示范"

    story2 = {
        "dialogue": [{"speaker": "昭昭", "line": "话"}],
        "quality": {"grade": "好", "score": 80, "structure_score": 80, "reasons": []},
    }
    apply_review_to_quality(
        story2,
        [{"lines": [10], "kind": "示范", "desc": "妈妈教孩子隐瞒", "fix": ""}],
        humor={"funny_score": 8, "best_moment": "那句", "humor_type": "natural"},
    )
    assert story2["quality"]["score"] == 78  # 80 + 8 − 10

def test_parse_humor_accepts_valid_rejects_bad():
    from app.services.daily_story.review import parse_humor

    ok = parse_humor({
        "humor": {"funny_score": 7, "best_moment": "笑点那句", "humor_type": "natural"},
    })
    assert ok == {"funny_score": 7, "best_moment": "笑点那句", "humor_type": "natural"}
    assert parse_humor({"humor": {"funny_score": 21, "humor_type": "x"}}) is None
    assert parse_humor({"humor": {"funny_score": "高", "humor_type": "natural"}}) is None
    assert parse_humor({"issues": []}) is None
    assert parse_humor(None) is None
    assert parse_humor("not a dict") is None

@pytest.mark.parametrize(
    "structure, funny, expect_pass, reason_needle",
    [
        (80, 14, True, "发布达标"),
        (80, 4, False, "好笑4/20<12"),
        (70, 14, False, "结构70<75"),
    ],
    ids=["ok", "low_humor", "low_structure"],
)
def test_apply_review_to_quality_publish_line(structure, funny, expect_pass, reason_needle):
    from app.services.daily_story.review import apply_review_to_quality

    story = {
        "dialogue": [{"speaker": "昭昭", "line": "话"}],
        "quality": {
            "grade": "好" if structure >= 75 else "中",
            "score": structure,
            "structure_score": structure,
            "reasons": [],
        },
    }
    apply_review_to_quality(
        story,
        [],
        humor={
            "funny_score": funny,
            "best_moment": "那句",
            "humor_type": "natural" if funny >= 12 else "formulaic",
        },
    )
    q = story["quality"]
    assert q["pass"] is expect_pass
    assert any(reason_needle in r for r in q["reasons"])
    if expect_pass:
        assert q["score"] == structure + funny
        assert q["humor"]["funny_score"] == funny

def test_b_patch_strips_filler():
    """B 一句一改：本地剥垫字，而非整段重试。"""
    from app.services.daily_story.story_types.b.patch import patch_b_strip_filler

    story = {
        "punchline_explain": "B类结盟翻车，姐弟偷吃露馅互甩锅",
        "dialogue": [
            {"speaker": "昭昭", "line": "你望风我下手真的呀"},
            {"speaker": "灿灿", "line": "别弄出声好不好"},
            {"speaker": "昭昭", "line": "奶油蹭裤腿了呢了呀"},
        ],
    }
    notes = patch_b_strip_filler(story)
    assert len(notes) == 3
    assert story["dialogue"][0]["line"] == "你望风我下手"
    assert story["dialogue"][1]["line"] == "别弄出声"
    assert story["dialogue"][2]["line"] == "奶油蹭裤腿了"

def test_c_patch_trims_soft_last_long_explanation():
    """C 一句一改：末句「哼，+长解释/文字游戏」截成完整嘴硬话，禁光杆叹词。"""
    from app.services.daily_story.prompts import try_local_patch_daily_story_body

    story = _valid_story()
    story["dialogue"][-1]["line"] = "哼，你那是碰，我这是拿，不一样！"
    patched, notes = try_local_patch_daily_story_body(story)
    assert any("软收截断" in n for n in notes)
    assert patched["dialogue"][-1]["line"] == "哼，明天我一定赢过你！"

def test_patch_c_stray_rebuttal_drops_unfounded_prefix():
    """C 类正文首句「我早就不疼了」须有前文指控，无指控删前缀（v23 主题1 抓）。

    v23 主题 1：灿灿开场理由换「上次我让了你」（先后欠账），模型照抄示范句式
    「我早就不疼了」顶回没人说过的理由 → 悬空自证；本地删前缀保留后半段抛判据。
    有「你上次喝多肚子疼」指控时保留；占有宣告「我早就拿到了」不误删。
    """
    from app.services.daily_story.story_types.c.patch import patch_c_stray_rebuttal

    def _story(d2: str, d3: str) -> dict:
        dlg = [
            {"speaker": "昭昭", "line": "姐姐，冰箱里最后一瓶酸奶，给我喝吧"},
            {"speaker": "灿灿", "line": d2},
            {"speaker": "昭昭", "line": d3},
        ]
        pad = "一二三四五六七八九十十一十二十三十四十五十六"
        for i in range(20):
            dlg.append({"speaker": "灿灿" if i % 2 else "昭昭", "line": pad})
        return {
            "punchline_explain": "C类公平执念，姐姐规则被字面戳穿",
            "dialogue": dlg,
        }

    # 无指控（先后欠账理由）→ 删前缀
    s = _story("不行，上次我让了你，这回该我先喝！", "我早就不疼了，酸奶没写你名字，谁先拿到归谁！")
    notes = patch_c_stray_rebuttal(s)
    assert notes
    assert s["dialogue"][2]["line"] == "酸奶没写你名字，谁先拿到归谁！"

    # 有指控（对方弱项）→ 保留
    s2 = _story("不行，你上次喝多肚子疼，这回给我喝！", "我早就不疼了，果汁又没写你名字，谁先拿到归谁！")
    assert not patch_c_stray_rebuttal(s2)
    assert s2["dialogue"][2]["line"].startswith("我早就不疼了")

    # 占有宣告「我早就拿到了」→ 不误删
    s3 = _story("不行，上次我让了你", "我早就拿到了，酸奶归我！")
    assert not patch_c_stray_rebuttal(s3)

def test_c_validate_hardblocks_stubborn_dim_drift():
    """C 硬卡：末句嘴硬比较维度须字面在本场立规句（用户 2026-08-09 v27 抓）。

    v27 果汁「比你早」/棒棒糖「比你举得久」/巧克力「比你举得久」三篇都 PASS
    交付了——观感降分拦不住，升格 validate 硬卡命中即整稿重抽。
    立规是仪式判据（举过头顶坚持三秒）时，末句发明立规句没有的比法 = 收束换赛规。
    """
    from app.services.daily_story.story_types.c.validate import append_c_body_errors

    def _story(dialogue: list[dict]) -> dict:
        s = _valid_story()
        s["dialogue"] = dialogue
        s["punchline_explain"] = (
            "C类公平执念，灿灿立规举过头顶坚持三秒，昭昭按字面执行，"
            "灿灿赖账，昭昭用其原规反问，灿灿嘴硬收场"
        )
        return s

    # v27 果汁稿：立规「举过头顶坚持三秒」，末句「比你早」（时序，本场无比早）→ 硬卡
    juice = _story(
        [
            {"speaker": "昭昭", "line": "姐姐，冰箱里最后一杯果汁，给我喝吧。"},
            {"speaker": "灿灿", "line": "不行，上次我让你了，这回该我了！"},
            {"speaker": "昭昭", "line": "可谁先拿到归谁，我攥住了！"},
            {"speaker": "灿灿", "line": "你攥住不算，得举过头顶坚持三秒才算！"},
            {"speaker": "昭昭", "line": "举就举，我数三下，你看着表！"},
            {"speaker": "灿灿", "line": "你数太快怎么办，我数，我数到三你才能动！"},
            {"speaker": "昭昭", "line": "好，你数，我举过头顶，你数到三我就放下！"},
            {"speaker": "灿灿", "line": "一，二，三！你举了，可你刚才先拿到，不算！"},
            {"speaker": "昭昭", "line": "你刚说举过头顶坚持三秒才算，我举了，该我喝！"},
            {"speaker": "灿灿", "line": "那是我说的，可你举的时候手抖了，不算！"},
            {"speaker": "昭昭", "line": "我手没抖，你数到三我才放，你赖皮！"},
            {"speaker": "灿灿", "line": "你举的时间不够，我数到二你就放了！"},
            {"speaker": "昭昭", "line": "你数到三我才放，你数到二我还没动，你瞎说！"},
            {"speaker": "灿灿", "line": "我不管，现在杯子在我手里，我先喝！"},
            {"speaker": "昭昭", "line": "你刚说谁先举过头顶坚持三秒谁喝，我举了，你抢！"},
            {"speaker": "灿灿", "line": "哼，明天我比你早！"},
        ]
    )
    errs: list[str] = []
    append_c_body_errors(juice, errs)
    assert any("比法漂移" in e for e in errs), errs

    # v27 棒棒糖稿：立规「举过头顶坚持三秒」，末句「比你举得久」（本场无比久）→ 硬卡
    lollipop = _story(
        [
            {"speaker": "昭昭", "line": "姐姐，客厅茶几上最后一根棒棒糖，给我吃吧。"},
            {"speaker": "灿灿", "line": "不行，你上次吃多牙疼，这次我先吃！"},
            {"speaker": "昭昭", "line": "我早就不牙疼了，糖又没写你名字，谁先抢到归谁！"},
            {"speaker": "灿灿", "line": "我先举过头顶坚持三秒才算，归我！"},
            {"speaker": "昭昭", "line": "你举啊，我数三秒，一秒，两秒……"},
            {"speaker": "灿灿", "line": "你数太快了，我还没站稳呢，重来！"},
            {"speaker": "昭昭", "line": "你刚说举过头顶坚持三秒，我数到三你才举，不算！"},
            {"speaker": "灿灿", "line": "那你也举啊，你举过头顶我也数三秒，看谁先坚持住！"},
            {"speaker": "昭昭", "line": "好，我举，你数，我举过头顶了，你数啊！"},
            {"speaker": "灿灿", "line": "一，二，三，你举过头顶三秒了，该我了！"},
            {"speaker": "昭昭", "line": "你耍赖，我举的时候你数得快，你举的时候数得慢！"},
            {"speaker": "灿灿", "line": "我数得慢是因为你举得歪，不算标准！"},
            {"speaker": "昭昭", "line": "你刚说举过头顶坚持三秒就算，我举得直直的"},
            {"speaker": "灿灿", "line": "那是我说的，可你举的时候我还没准备好呢！"},
            {"speaker": "昭昭", "line": "你刚才说谁先抢到归谁，我抢到了，糖该归我！"},
            {"speaker": "灿灿", "line": "哼，明天我比你举得久！"},
        ]
    )
    errs = []
    append_c_body_errors(lollipop, errs)
    assert any("比法漂移" in e for e in errs), errs

    # 仪式判据 + 万能「明天我一定赢过你」→ 硬卡放行
    good = _story(
        [
            {"speaker": "昭昭", "line": "姐姐，茶几上最后一块巧克力，给我吃吧"},
            {"speaker": "灿灿", "line": "不行，我先抢到的！归我！"},
            {"speaker": "昭昭", "line": "你那是按住，我这是举过头顶，举得高才算好不好呀！"},
            {"speaker": "灿灿", "line": "举过头顶当然算，可你手抖了，不算，重来你听着！"},
            {"speaker": "昭昭", "line": "我手没抖，是你喊太快，我还没站定，再举一次呢！"},
            {"speaker": "灿灿", "line": "好，那重来，你举过头顶，我数到三你举稳才算嘛！"},
            {"speaker": "昭昭", "line": "好，你喊吧，我这次举得高高的，你数准点啊！"},
            {"speaker": "灿灿", "line": "一、二、三，你举过头顶了，算你做到了，给呀！"},
            {"speaker": "昭昭", "line": "那巧克力归我了，你松手！"},
            {"speaker": "灿灿", "line": "你刚说谁先拿到归谁，可我先拿到的，我先吃！"},
            {"speaker": "昭昭", "line": "你按住不算拿到，我举过头顶才是拿到，我赢了！"},
            {"speaker": "灿灿", "line": "你举过头顶是我喊的，不算你本事！"},
            {"speaker": "昭昭", "line": "你刚说举过头顶坚持三秒就算，我做到了，该我！"},
            {"speaker": "灿灿", "line": "哼，明天我一定赢过你！"},
        ]
    )
    errs = []
    append_c_body_errors(good, errs)
    assert not any("比法漂移" in e for e in errs), errs

def test_c_validate_hardblocks_opening_possession_contradicts_setting():
    """C 硬卡：开场占有宣告须与 setting 持有者一致（用户 2026-08-09 v27 酸奶稿抓）。

    setting「昭昭手里攥着最后一瓶酸奶」，开场第 2 句灿灿却自称「我先拿到的」——
    与可见场景矛盾；失方第 2 句只能孩子气理由反对（你上次喝多闹肚子/我搬回来的）。
    己方=setting 持有者时开场直接宣示占有才合法。
    """
    from app.services.daily_story.story_types.c.opening import append_c_opening_errors

    # v27 酸奶稿：setting 昭昭持有，灿灿自称我先拿到 → 矛盾
    bad_opening = [
        {"speaker": "昭昭", "line": "冰箱里最后一瓶酸奶，我想喝。"},
        {"speaker": "灿灿", "line": "不行，我先拿到的，归我！"},
    ]
    errs: list[str] = []
    append_c_opening_errors(
        bad_opening,
        type_code="C",
        errors=errs,
        setting="客厅，冰箱门开着，昭昭手里攥着最后一瓶酸奶，灿灿伸手来抢。",
    )
    assert any("与 setting 矛盾" in e for e in errs), errs

    # v28 酸奶稿：setting 灿灿持有，灿灿开场第 2 句用理由反对 → 放行
    good_opening = [
        {"speaker": "昭昭", "line": "姐姐，冰箱里最后一瓶酸奶，给我喝吧"},
        {"speaker": "灿灿", "line": "不行，你上次喝多闹肚子，这次我先喝！"},
    ]
    errs = []
    append_c_opening_errors(
        good_opening,
        type_code="C",
        errors=errs,
        setting="客厅冰箱前，灿灿刚打开冰箱门，手已握住最后一瓶酸奶的瓶身。",
    )
    assert not any("与 setting 矛盾" in e for e in errs), errs

    # 己方=setting 持有者，开场直接宣示占有 → 放行
    owner_opening = [
        {"speaker": "灿灿", "line": "这瓶酸奶我先拿到的，归我！"},
        {"speaker": "昭昭", "line": "你上次喝多闹肚子，这次让我喝！"},
    ]
    errs = []
    append_c_opening_errors(
        owner_opening,
        type_code="C",
        errors=errs,
        setting="客厅，灿灿手里攥着最后一瓶酸奶，昭昭伸手来抢。",
    )
    assert not any("与 setting 矛盾" in e for e in errs), errs

def test_c_validate_hardblocks_opening_loser_criterion():
    """C 硬卡：开场失方禁抛占有判据/宣示能力（用户 2026-08-09 v29 酸奶稿抓）。

    setting 明写灿灿正拿在手里、昭昭伸手来抢，昭昭第 2 句却立「谁先拿到归谁」
    判据/宣示「我够得着」——先拿到者已是灿灿，判据必对己不利，且「够得着」与
    「伸手来抢」（够不着才有抢的张力）矛盾；失方第 2 句只能孩子气理由反对。
    持有者本人抛判据不查（sp==holder）。
    """
    from app.services.daily_story.story_types.c.opening import append_c_opening_errors

    # v29 酸奶稿：setting 灿灿持有，失方昭昭抛「谁先拿到归谁」判据+「我够得着」→ 拦
    bad_opening = [
        {"speaker": "灿灿", "line": "冰箱里最后一瓶酸奶，在我手里呢"},
        {"speaker": "昭昭", "line": "谁先拿到归谁，我够得着！"},
    ]
    errs: list[str] = []
    append_c_opening_errors(
        bad_opening,
        type_code="C",
        errors=errs,
        setting="冰箱前，灿灿刚打开冰箱门，最后一瓶酸奶正拿在手里，昭昭伸手来抢。",
    )
    assert any("失方抛占有判据" in e for e in errs), errs

    # 对照：失方第 2 句孩子气理由反对 → 放行
    good_opening = [
        {"speaker": "灿灿", "line": "冰箱里最后一瓶酸奶，在我手里呢"},
        {"speaker": "昭昭", "line": "不行，你上次喝多闹肚子，这次该我喝！"},
    ]
    errs = []
    append_c_opening_errors(
        good_opening,
        type_code="C",
        errors=errs,
        setting="冰箱前，灿灿刚打开冰箱门，最后一瓶酸奶正拿在手里，昭昭伸手来抢。",
    )
    assert not any("失方抛占有判据" in e for e in errs), errs

    # 持有者本人立判据不查（sp==holder 跳过失方检查）→ 放行
    owner_criterion = [
        {"speaker": "灿灿", "line": "谁先拿到归谁，我已经拿到了！"},
        {"speaker": "昭昭", "line": "你上次喝多闹肚子，这次让我喝！"},
    ]
    errs = []
    append_c_opening_errors(
        owner_criterion,
        type_code="C",
        errors=errs,
        setting="客厅，灿灿手里攥着最后一瓶酸奶，昭昭伸手来抢。",
    )
    assert not any("失方抛占有判据" in e for e in errs), errs

def test_c_validate_hardblocks_agree_contest_without_proposal():
    """C 硬卡：正文首句「X就X」接招须有开场提议（用户 2026-08-09 v27 酸奶稿抓）。

    v27 酸奶稿开场末句灿灿只做占有宣告「我先拿到的，归我」，正文首句昭昭
    「举就举，我举过头顶了」——接招回应一个开场从没提议过的比赛（举），凭空
    进入未立赛规。只有 X 字面出现在开场两句（真提议过该动作）才放行。
    """
    from app.services.daily_story.story_types.c.validate import append_c_body_errors

    def _story(dialogue: list[dict]) -> dict:
        s = _valid_story()
        s["dialogue"] = dialogue
        s["punchline_explain"] = (
            "C类公平执念，灿灿立规举过头顶坚持三秒，昭昭按字面执行，"
            "灿灿赖账，昭昭用其原规反问，灿灿嘴硬收场"
        )
        return s

    # v27 酸奶稿：开场末句只占有宣告，正文首句接招「举就举」→ 凭空进入未立赛规
    bad = _story(
        [
            {"speaker": "昭昭", "line": "冰箱里最后一瓶酸奶，我想喝。"},
            {"speaker": "灿灿", "line": "不行，我先拿到的，归我！"},
            {"speaker": "昭昭", "line": "举就举，我举过头顶了，你数真的呀！"},
            {"speaker": "灿灿", "line": "一、二、三，好了，你放下，该我了呢了呀！"},
            {"speaker": "昭昭", "line": "我举完了，酸奶还是我的，你刚说的了吧！"},
            {"speaker": "灿灿", "line": "我说的是我先举才算，你举了不算嘛了呀！"},
            {"speaker": "昭昭", "line": "你耍赖，规则是你定的，我照做了啊！"},
            {"speaker": "灿灿", "line": "那我也举，我举得比你久，归我了呀！"},
            {"speaker": "昭昭", "line": "你举吧，我数着，三秒不到就放下好不好呀！"},
            {"speaker": "灿灿", "line": "我举过头顶了，你数到三了吗你听着呀？"},
            {"speaker": "昭昭", "line": "你刚说举过头顶坚持三秒才算，你才两秒！"},
            {"speaker": "灿灿", "line": "我不管，我举了，酸奶该我喝！"},
            {"speaker": "昭昭", "line": "你定的规则自己都不守，还想要酸奶？"},
            {"speaker": "灿灿", "line": "哼，明天我一定赢过你！"},
        ]
    )
    errs: list[str] = []
    append_c_body_errors(bad, errs)
    assert any("凭空进入未立赛规" in e for e in errs), errs

    # 开场第 2 句真提议过「举」→ 接招合法放行
    good = _story(
        [
            {"speaker": "昭昭", "line": "冰箱里最后一瓶果汁，给我喝吧。"},
            {"speaker": "灿灿", "line": "行，要比举过头顶才给，敢不敢？"},
            {"speaker": "昭昭", "line": "举就举，我举过头顶了，你数啊！"},
            {"speaker": "灿灿", "line": "一、二、三，好了，你放下，该我了！"},
            {"speaker": "昭昭", "line": "我举完了，果汁还是我的，你刚说的了吧！"},
            {"speaker": "灿灿", "line": "我说的是我先举才算，你举了不算嘛！"},
            {"speaker": "昭昭", "line": "你耍赖，规则是你定的，我照做了啊！"},
            {"speaker": "灿灿", "line": "那我也举，我举得比你久，归我了呀！"},
            {"speaker": "昭昭", "line": "你举吧，我数着，三秒不到就放下好不好呀！"},
            {"speaker": "灿灿", "line": "我举过头顶了，你数到三了吗你听着呀？"},
            {"speaker": "昭昭", "line": "你刚说举过头顶坚持三秒才算，你才两秒！"},
            {"speaker": "灿灿", "line": "我不管，我举了，果汁该我喝！"},
            {"speaker": "昭昭", "line": "你定的规则自己都不守，还想要果汁？"},
            {"speaker": "灿灿", "line": "哼，明天我一定赢过你！"},
        ]
    )
    errs = []
    append_c_body_errors(good, errs)
    assert not any("凭空进入未立赛规" in e for e in errs), errs

def test_c_validate_hardblocks_rule_maker_must_lose():
    """C 硬卡：立规人必须输——仪式立规句提出者须是末句说话人（被戳穿方）。

    v47 酸奶稿：灿灿立规「谁先拿到再单脚站满十秒谁喝」，但灿灿自己站满赢、
    末句昭昭嘴硬——立规人赢任何一轮判定，方向反了 → 整稿重抽。
    正确稿：立规人=输家=末句说话人 → 放行。
    """
    from app.services.daily_story.story_types.c.validate import append_c_body_errors

    def _story(dlg: list[dict]) -> dict:
        s = _valid_story()
        s["dialogue"] = dlg
        s["punchline_explain"] = "C类公平执念，姐姐规则被字面戳穿"
        return s

    # v47 形态（去语气词堆砌干扰）：规则是灿灿说的（第2句），末句却是昭昭嘴硬
    bad = _story(
        [
            {"speaker": "昭昭", "line": "冰箱里最后一瓶酸奶，我先抢到了！"},
            {"speaker": "灿灿", "line": "你放下！谁先拿到再单脚站满十秒谁喝！"},
            {"speaker": "昭昭", "line": "我先抢到的，酸奶归我，你松手！"},
            {"speaker": "灿灿", "line": "谁先拿到再单脚站满十秒谁喝，你敢比吗？"},
            {"speaker": "昭昭", "line": "我单脚站满十秒，你可别耍赖！"},
            {"speaker": "灿灿", "line": "我数数，你站好，一、二、三……十！"},
            {"speaker": "昭昭", "line": "你数太快了，我还没站稳呢！"},
            {"speaker": "灿灿", "line": "规则又没说数多快，我数到十你就得站住！"},
            {"speaker": "昭昭", "line": "那你数慢点，我扶一下墙总行了吧？"},
            {"speaker": "灿灿", "line": "扶墙也算站？那我也扶，看谁先倒！"},
            {"speaker": "昭昭", "line": "我扶墙站好了，你数到十了吗？"},
            {"speaker": "灿灿", "line": "我早数完了，你扶墙不算，我赢了！"},
            {"speaker": "昭昭", "line": "你耍赖，你刚才也扶墙了！"},
            {"speaker": "灿灿", "line": "你刚说谁先拿到再单脚站满十秒谁喝，我站满了！"},
            {"speaker": "昭昭", "line": "哼，明天我抢先单脚站，你数数慢死了！"},
        ]
    )
    errs: list[str] = []
    append_c_body_errors(bad, errs)
    assert any("立规人必须输" in e for e in errs), errs

    # 正确形态：灿灿立规（第2句）、灿灿输、末句灿灿嘴硬
    good = _story(
        [
            {"speaker": "昭昭", "line": "冰箱里最后一瓶酸奶，我先抢到了！"},
            {"speaker": "灿灿", "line": "你放下！得单脚站满十秒才能喝，我定的规矩！"},
            {"speaker": "昭昭", "line": "行，比就比，你先站，我来数！"},
            {"speaker": "灿灿", "line": "我单脚站好了，你数吧！"},
            {"speaker": "昭昭", "line": "一、二、三、四、五、六、七、八、九、十，到了！"},
            {"speaker": "灿灿", "line": "等等！我单脚还没抬稳你就数完了！"},
            {"speaker": "昭昭", "line": "你的规矩是站满十秒，我数到十了你两只脚还踩地上，你输。"},
            {"speaker": "灿灿", "line": "你数那么快，谁来得及站稳！不算不算！"},
            {"speaker": "昭昭", "line": "那按规矩，该我站了，你数！"},
            {"speaker": "灿灿", "line": "行，你站好，我数，一……二……"},
            {"speaker": "昭昭", "line": "我站得稳稳的，你快数！"},
            {"speaker": "灿灿", "line": "三……四……五……"},
            {"speaker": "昭昭", "line": "十！我站满了，酸奶归我！"},
            {"speaker": "灿灿", "line": "你耍赖，你自己数的不算！"},
            {"speaker": "昭昭", "line": "你刚说得单脚站满十秒才能喝，我站满了，酸奶归我！"},
            {"speaker": "灿灿", "line": "哼，明天我肯定能站满十秒，你等着！"},
        ]
    )
    errs = []
    append_c_body_errors(good, errs)
    assert not any("回旋镖引话归属错误" in e for e in errs), errs

def test_c_validate_hardblocks_tone_stack():
    """C 硬卡：句尾语气词堆砌（v47 酸奶稿第 3/4/7/10 句病句尾）≥2 句重抽。"""
    from app.services.daily_story.story_types.c.validate import append_c_body_errors

    def _story(dlg: list[dict]) -> dict:
        s = _valid_story()
        s["dialogue"] = dlg
        s["punchline_explain"] = "C类公平执念，姐姐规则被字面戳穿"
        return s

    bad = _story(
        [
            {"speaker": "昭昭", "line": "冰箱里最后一瓶酸奶，我先抢到了！"},
            {"speaker": "灿灿", "line": "你放下！谁先拿到再单脚站满十秒谁喝！"},
            {"speaker": "昭昭", "line": "我先抢到的，酸奶归我，你松手好不好了呀！"},
            {"speaker": "灿灿", "line": "谁先拿到再单脚站满十秒谁喝，你敢比吗你听着了呀？"},
            {"speaker": "昭昭", "line": "比就比，我单脚站满十秒，你可别耍赖真的呀！"},
            {"speaker": "灿灿", "line": "我数数，你站好，一、二、三…了呢了呀…"},
            {"speaker": "昭昭", "line": "你数太快了，我还没站稳了呢了呀！"},
            {"speaker": "灿灿", "line": "规则又没说数多快，我数到十你就得站住了吧。"},
            {"speaker": "昭昭", "line": "那你数慢点，我扶一下墙总行了吧？"},
            {"speaker": "灿灿", "line": "扶墙也算站？那我也扶，看谁先倒嘛了呀！"},
            {"speaker": "昭昭", "line": "我扶墙站好了，你数到十了吗了啊？"},
            {"speaker": "灿灿", "line": "我早数完了，你扶墙不算，我赢了！"},
            {"speaker": "昭昭", "line": "你耍赖，你刚才也扶墙了！"},
            {"speaker": "灿灿", "line": "你刚说谁先拿到再单脚站满十秒谁喝，我站满了！"},
            {"speaker": "昭昭", "line": "哼，明天我抢先单脚站，你数数慢死了！"},
        ]
    )
    errs: list[str] = []
    append_c_body_errors(bad, errs)
    assert any("句尾语气词堆砌" in e for e in errs), errs

    # 单句语气词（每句最多一个）不误伤
    good = _story(
        [
            {"speaker": "昭昭", "line": "冰箱里最后一瓶酸奶，我先抢到了！"},
            {"speaker": "灿灿", "line": "你放下！得单脚站满十秒才能喝，我定的规矩！"},
            {"speaker": "昭昭", "line": "行，比就比，你先站，我来数！"},
            {"speaker": "灿灿", "line": "我单脚站好了，你数吧！"},
            {"speaker": "昭昭", "line": "一、二、三、四、五、六、七、八、九、十，到了！"},
            {"speaker": "灿灿", "line": "等等！我单脚还没抬稳你就数完了！"},
            {"speaker": "昭昭", "line": "你的规矩是站满十秒，我数到十了你两只脚还踩地上，你输。"},
            {"speaker": "灿灿", "line": "你数那么快，谁来得及站稳！不算不算！"},
            {"speaker": "昭昭", "line": "那按规矩，该我站了，你数！"},
            {"speaker": "灿灿", "line": "行，你站好，我数，一……二……"},
            {"speaker": "昭昭", "line": "我站得稳稳的，你快数！"},
            {"speaker": "灿灿", "line": "三……四……五……"},
            {"speaker": "昭昭", "line": "十！我站满了，酸奶归我！"},
            {"speaker": "灿灿", "line": "你耍赖，你自己数的不算！"},
            {"speaker": "昭昭", "line": "你刚说得单脚站满十秒才能喝，我站满了，酸奶归我！"},
            {"speaker": "灿灿", "line": "哼，明天我肯定能站满十秒，你等着！"},
        ]
    )
    errs = []
    append_c_body_errors(good, errs)
    assert not any("句尾语气词堆砌" in e for e in errs), errs


def test_c_line_rules_cover_cut_finality_boomerang_limit_and_quantifier():
    """C 类规则已补：切完禁重切、回旋镖限次、量词落地、开场禁说明文。"""
    from app.services.daily_story.story_types.c.line import LINE_C

    assert "切分/拆封即终结" in LINE_C.prompt_block
    assert "回旋镖限次" in LINE_C.prompt_block
    assert "量词落地" in LINE_C.prompt_block
    assert "禁说明文式开场" in LINE_C.opening_system_append
    assert "回旋镖优先打立规人最自信的原话" in LINE_C.prompt_block
    assert "禁自打嘴巴式自信" in LINE_C.prompt_block
    assert "定义战只许一轮" in LINE_C.prompt_block
    assert "我那是让着你" in LINE_C.prompt_block


def test_c_criterion_inject_action_dispatch_skips_ritual_script():
    """C 判据链注入：动作分派型破段不得再硬套单脚站仪式。"""
    from app.services.llm.llm_deepseek import (
        _C_CRITERION_INJECT_TEMPLATE,
        _C_CRITERION_PACKAGE_SYSTEM,
    )

    block = _C_CRITERION_INJECT_TEMPLATE.format(
        zhaozhao_rule="切完我先挑，谁反悔谁小狗",
        cancan_rule="好，说好切完你先挑，谁反悔谁小狗",
        boomerang_quote="说好切完你先挑",
        boomerang_source="cancan_rule",
        trap="立规人答应切完先挑后反悔硬抢，被对方按字面先挑走大块",
        break_script=(
            "按动作分派/占有规则字面执行：对方按字面先挑走大块，立规人反悔硬抢，"
            "被原规反问当场判输；执行纠纷只用 换/端/抢/抱/藏。"
        ),
    )
    assert "切完你先挑" in block
    assert "立规人提出仪式规则后" not in block
    assert "数数人故意拖长音" not in block
    assert "挑哪块都一样" in _C_CRITERION_PACKAGE_SYSTEM


def test_c_ground_closing_quote_allows_perspective_swap():
    """C 回旋镖引话：我/你视角互换算同一承诺。"""
    from app.services.daily_story.story_types.c.humor import (
        ground_closing_quote,
    )

    assert ground_closing_quote("歪了算你输", "歪了算我输")
    assert ground_closing_quote("切完你先挑", "切完我先挑")
    assert ground_closing_quote(
        "切完我先挑，那我挑了大的，就归我",
        "说好切完你先挑，谁反悔谁小狗",
    )


def test_c_validate_hardblocks_recut_after_cut():
    """C 硬卡：切好的资源禁止重切/恢复/重新比。"""
    from app.services.daily_story.story_types.c.validate import (
        append_c_body_errors,
    )

    story = _valid_story()
    story["dialogue"][8]["line"] = _pad_line("这两块得重新切一刀，我切的不算！")
    errs: list[str] = []
    append_c_body_errors(story, errs)
    assert any("切分即终结" in e for e in errs), errs


def test_c_validate_hardblocks_repeated_boomerang():
    """C 硬卡：直接引话式回旋镖 ≥3 次整稿重抽。"""
    from app.services.daily_story.story_types.c.validate import (
        append_c_body_errors,
    )

    story = _valid_story()
    story["dialogue"][6]["line"] = _pad_line("你刚说先挑大块")
    story["dialogue"][8]["line"] = _pad_line("你刚才说先挑大块")
    errs: list[str] = []
    append_c_body_errors(story, errs)
    assert any("回旋镖重复" in e for e in errs), errs


def test_c_facts_flags_ungrounded_container_quantifier():
    """C 事实：'这盘'未在 setting/前文交代容器即悬空。"""
    from app.services.daily_story.story_types.c.facts import (
        collect_fact_issues,
    )

    story = _valid_story()
    story["setting"] = "客厅，姐弟抢新橡皮"
    story["dialogue"][10]["line"] = _pad_line("这盘归我，你别抢！")
    issues = collect_fact_issues(story)
    assert any("量词悬空" in i for i in issues), issues


def test_c_facts_flags_even_claim_and_leave_claim_contradiction():
    """C 事实：说过「一样大/挑哪块都一样」后禁再写「特意留」。"""
    from app.services.daily_story.story_types.c.facts import (
        collect_fact_issues,
    )

    story = _valid_story()
    story["setting"] = "客厅茶几上放着一块圆形蛋糕"
    story["dialogue"][5]["line"] = _pad_line("行，我切得一样大，你挑哪块都一样。")
    story["dialogue"][10]["line"] = _pad_line("那块是我特意留给自己吃的！")
    issues = collect_fact_issues(story)
    assert any("自信与留块矛盾" in i for i in issues), issues


def test_c_humor_flags_repeated_boomerang():
    """C 观感：全文「你刚说/你说的」式回旋镖 ≥3 次判重复。"""
    from app.services.daily_story.story_types.c.humor import (
        collect_humor_issues,
    )

    lines = [
        "你刚说切完你先挑",
        "你刚说谁反悔谁小狗",
        "你刚说切完你先挑",
        "你刚说谁反悔谁小狗",
        "你刚说大块归我",
        "哼，明天我自己藏大块",
    ]
    speakers = ["昭昭", "灿灿", "昭昭", "灿灿", "昭昭", "灿灿"]
    issues = collect_humor_issues(lines, speakers)
    assert any("回旋镖重复" in i for i in issues), issues


def test_c_opening_flags_scene_card_line():
    """C 开场：'X还在Y上'式说明文判观感问题。"""
    from app.services.daily_story.story_types.c.opening import (
        score_opening_quality,
    )

    story = {
        "setting": "厨房餐桌上放着最后一块蛋糕，灿灿刚切成一大一小两块。",
        "discovery_opening": [
            {
                "speaker": "昭昭",
                "line": "姐姐，你切好的蛋糕还在餐桌上，我想先挑！",
            },
            {"speaker": "灿灿", "line": "不行，我切的，这块大的该归我！"},
        ],
    }
    _, _, cons = score_opening_quality(story)
    assert any("说明文" in c for c in cons), cons
