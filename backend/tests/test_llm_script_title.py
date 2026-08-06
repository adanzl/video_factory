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
from app.services.daily_story.story_types import format_block_for_code
from app.utils.title_text import select_optimized_title


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


def test_chat_title_system_prompt_has_hook_templates_and_antitrunc():
    prompts = build_chat_title_prompts(
        "藏玩具同盟",
        {
            "setting": "客厅",
            "punchline_explain": "C类公平执念，姐姐权威被戳穿",
            "dialogue": [{"speaker": "昭昭", "line": "你藏了我的橡皮"}],
        },
        max_title_length=16,
    )
    for kw in ("翻车记", "小队散伙了", "咋变这样", "手忙脚乱", "删掉钩子", "谁干的"):
        assert kw in prompts["system"], kw
    assert "宁可短" not in prompts["user"]
    assert "16" not in prompts["system"]


def test_chat_title_system_prompt_has_no_copyable_examples():
    # 句式模板只讲结构不给成品例，防 LLM 把「越擦越花」这类例词原样抄给无关剧情
    prompts = build_chat_title_prompts(
        "藏玩具同盟",
        {
            "setting": "客厅",
            "punchline_explain": "B类结盟翻车，整盒月饼滚出来被妈妈抓",
            "dialogue": [{"speaker": "昭昭", "line": "快藏，妈来了"}],
        },
        max_title_length=16,
    )
    # 形态示例用 XX 占位（如「XX翻车记」），不出现具体故事成品
    assert "XX翻车记" in prompts["system"]
    assert "偷看电视翻车记" not in prompts["system"]
    for kw in ("越擦越花", "老鼠会开柜子门吗", "自己不吃却管我", "妈妈藏的饼干"):
        assert kw not in prompts["system"], kw
    # 形态示例带 XX 占位说明 + 禁止照抄别的故事
    assert "XX" in prompts["system"]
    assert "不要照抄成品短句" in prompts["system"]


def test_chat_title_user_prompt_no_spoiler_and_avoid():
    prompts = build_chat_title_prompts(
        "月饼大作战",
        {
            "setting": "客厅",
            "punchline_explain": "B类结盟翻车，连锁意外让整盒月饼全滚出来，妈妈抓个正着",
            "dialogue": [{"speaker": "昭昭", "line": "妈，是月饼自己滚的"}],
        },
        max_title_length=16,
    )
    assert "别报流水账" in prompts["user"]
    assert "3 个候选" in prompts["user"]
    assert "已用过的标题" not in prompts["user"]

    prompts_avoid = build_chat_title_prompts(
        "月饼全滚出来了",
        {
            "setting": "客厅",
            "punchline_explain": "B类结盟翻车，连锁意外让整盒月饼全滚出来，妈妈抓个正着",
            "dialogue": [{"speaker": "昭昭", "line": "妈，是月饼自己滚的"}],
        },
        max_title_length=16,
        avoid_titles=["月饼全滚出来了"],
    )
    assert "已用过的标题" in prompts_avoid["user"]
    assert "月饼全滚出来了" in prompts_avoid["user"]
    assert "换一个角度" in prompts_avoid["user"]


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


def test_pick_best_chat_title_penalizes_outcome_reveal():
    from app.services.script.optimize_title import pick_best_chat_title

    # 具体甩锅画面/口吻 优于 结局播报（谁…全滚出来）
    best = pick_best_chat_title(
        "月饼大作战",
        ["谁把月饼全滚出来", "不是我，月饼自己滚的"],
        max_len=10,
    )
    assert best == "不是我，月饼自己滚的"
    # 结局播报也不敌「具体道具+甩锅」问句
    best2 = pick_best_chat_title(
        "月饼大作战",
        ["谁把月饼全滚出来", "谁先踩的渣"],
        max_len=10,
    )
    # 两个候选都是谁字/结局播报（谁-2 / 全滚-3），均不高于当前标题 → 保留当前
    assert best2 == "月饼大作战"


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


def test_pick_best_chat_title_defends_current_title():
    """好初稿不被更差候选顶掉：重跑时「妈，月饼自己滚的」(hook 3) 不被 0 分候选替换。"""
    from app.services.script.optimize_title import pick_best_chat_title

    assert (
        pick_best_chat_title(
            "妈，月饼自己滚的",
            ["偷吃月饼翻车记", "月饼渣谁擦"],
            max_len=10,
            anchor_words=["月饼"],
        )
        == "妈，月饼自己滚的"
    )
    # 明显更优的候选（自己+称呼=3 > 3? 需严格更高；这里给 hook 4 的候选）
    assert (
        pick_best_chat_title(
            "妈，月饼自己滚的",
            ["妈，月饼自己掉的！"],
            max_len=10,
            anchor_words=["月饼"],
        )
        == "妈，月饼自己掉的！"
    )


def test_chat_title_hook_score_penalizes_who():
    """谁字质问降 2 分，甩锅/推锅给东西压过谁问句。"""
    from app.services.script.optimize_title import _chat_title_hook_score

    assert _chat_title_hook_score("谁擦墙渣") < _chat_title_hook_score("妈，月饼是它自己滚的")
    assert _chat_title_hook_score("渣印谁擦") < _chat_title_hook_score("妈，月饼是它自己滚的")
    # 问号仍给分但被谁字压回：谁问句 < 甩锅+称呼
    assert _chat_title_hook_score("谁偷看电视？") < _chat_title_hook_score("妈，电视自己开的")


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


def test_chat_title_user_prompt_contains_core_noun_requirement():
    prompts = build_chat_title_prompts(
        "月饼大作战",
        {
            "scene_title": "月饼大作战",
            "conflict_core": "姐弟联手偷吃月饼，望风失误掉渣露馅",
            "setting": "客厅茶几上放着一盒月饼",
            "punchline_explain": "B类结盟翻车",
            "dialogue": [{"speaker": "昭昭", "line": "快藏，妈来了"}],
        },
        max_title_length=16,
    )
    # 专家要求：标题必须原样保留完整主题短语（偷吃月饼），不是只留核心名词
    assert "本集主题短语（标题必须原样保留）：偷吃月饼" in prompts["user"]
    assert "必须原样保留本集主题短语" in prompts["user"]
    assert "硬性" in prompts["system"]


def test_format_block_scene_title_requires_spoken_hook():
    for code in ("A", "B", "C", "D", "E"):
        blk = format_block_for_code(code)
        assert '"scene_title":' in blk
        assert "口语钩子" in blk
        assert "藏玩具" in blk or "分蛋糕" in blk
        assert "老鼠会开柜子门吗" in blk
        assert "场记或口语钩子均可" not in blk


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


def test_daily_story_prompts_share_contract_opening_bits():
    # 原 share_contract 后半段拆出，避免上面插测打乱；保留开场断言
    from app.services.daily_story.prompts import build_daily_story_opening_prompts

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


def test_revise_patch_A_exempts_quote_from_keep_last_four():
    """引话不接地走 revise_patch 时，A类 system 不得再叫模型原样保留末四拍
    （引话就是末四拍倒数第4句，原样保留会把要修的坏引话一起冻住）。"""
    from app.services.daily_story.prompts import (
        _daily_story_contract,
        build_daily_story_prompts,
        resolve_daily_story_retry_length_mode,
    )

    prev = _valid_story(n=18)
    err = (
        "A类引话须出自灿灿前文原话"
        "（无「你叠的被子角都没对齐」），禁止昭昭自造后再假装引用"
    )
    assert resolve_daily_story_retry_length_mode(prev, errors=err) == "revise_patch"
    sys_a, _ = build_daily_story_prompts(
        "姐姐嫌弟弟叠被子总叠不齐",
        story_type="A",
        length_mode="revise_patch",
    )
    assert "末四拍尽量原样保留" not in sys_a
    assert "引话" in sys_a and "倒数第4" in sys_a
    # 非 A 类型仍走通用 revise_patch，不回归
    generic = _daily_story_contract(length_mode="revise_patch", type_code=None)
    assert "末四拍尽量原样保留" in generic


def test_a_prompt_blocks_midbody_rehearsal_of_quote_beat():
    """中段禁提前上演「引原话→那不一样」拍子，引话只准末四拍引一次
    （拿筷子 79：中段 [12][13] 先引埋句被审读判与末四拍重复）。"""
    from app.services.daily_story.story_types.a.line import LINE_A

    blk = LINE_A.prompt_block
    assert "引话只演一次" in blk
    assert "末四拍才是昭昭引灿灿原话的场合" in blk
    assert "同一引语中段演过、末四拍再引 = 审读判重复" in blk


def test_a_prompt_includes_five_escalation_layers():
    """A 类升级路线须含全部 5 个计分层（亮权威→追问→露馅→引先例→破功）。
    缺引先例层导致审读判「冲突推进3层」，是 82–84 与 88–89 的分水岭。"""
    from app.services.daily_story.story_types.a.line import LINE_A

    blk = LINE_A.prompt_block
    assert "5 阶段须到齐" in blk
    assert "引先例" in blk
    assert "上次你也" in blk
    assert "亮权威" in blk and "一锤落地" in blk
    assert "角色护栏" in blk
    assert "一锤落地（中段第 6–15 句必出）" in blk
    # 质量修订 hint 也点名引先例层
    assert "引先例" in LINE_A.escalation_revision_hint
    assert "冲突推进不足" in LINE_A.escalation_revision_hint


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


def test_local_patch_pads_small_char_deficit():
    from app.services.daily_story.prompts import (
        dialogue_total_chars,
        try_local_patch_daily_story_body,
        validate_daily_story_json,
    )

    story = _valid_story(n=14)
    target = 228  # 还差 12，落在本地补字窗口（下限已从 280 降到 240）
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
    assert 240 - 32 <= before < 240, f"before={before}"
    patched, notes = try_local_patch_daily_story_body(story)
    after = dialogue_total_chars(patched)
    assert notes
    assert after >= before
    if after >= 240:
        validate_daily_story_json(patched, phase="body")


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


def test_b_chain_flags_orphan_wo_ye():
    from app.services.daily_story.story_types.b.humor import collect_chain_anaphora_issues

    lines = [
        "结盟",
        "嘘妈在厨房",
        "好你拆",
        "啊呀，包装撕太大了！",
        "饼干蹦出来了，快用脚接！",
        "没接住，全掉地上了。",
        "我也踩到了，更糟了。",
        "别动脚，脚印会更多。",
    ]
    issues = collect_chain_anaphora_issues(lines, None)
    assert any("我也缺前句动作" in i for i in issues)


def test_b_chain_accepts_wo_ye_step():
    from app.services.daily_story.story_types.b.humor import collect_chain_anaphora_issues

    lines = [
        "结盟",
        "包装撕太大了",
        "没接住，全掉地上了。",
        "哎呀，我踩一脚。",
        "别动脚，脚印会更多。",
    ]
    assert not collect_chain_anaphora_issues(lines, None)


def test_b_chain_accepts_ye_with_antecedent():
    from app.services.daily_story.story_types.b.humor import collect_chain_anaphora_issues

    lines = [
        "结盟",
        "包装撕太大了",
        "我不小心踩上去了。",
        "我也踩到了，更糟了。",
        "别动脚。",
    ]
    assert not collect_chain_anaphora_issues(lines, None)


def test_b_ally_accepts_guard_post_pact():
    """结盟用「站门口盯紧 / 一人一块」等语义表达也算约定，勿按词穷举。"""
    from app.services.daily_story.story_types.b.humor import collect_humor_issues

    lines = [
        "姐，蛋糕切好没，我站门口盯紧。",
        "嘘，妈在睡觉，你放轻点。",
        "好，切两块，一人一块。",
        "哎呀，奶油粘手上了！",
        "快舔掉，别滴地上。",
        "蛋糕歪了，快扶住！",
    ]
    issues = collect_humor_issues(lines, None)
    assert not any("缺结盟约定" in i for i in issues)


def test_b_huan_accepts_mid_chain_adversative():
    """「你哭得还带响」是转折用法（还居然），连锁中已有动作则放过。"""
    from app.services.daily_story.story_types.b.humor import _chain_anaphora_tag

    line = "那我说你摔了，你哭得还带响。"
    prev2 = "就说在草地上摔了个屁股蹲。你摔了还咧嘴笑。"
    assert _chain_anaphora_tag(line, prev2) is None


def test_b_huan_still_flags_ungrounded():
    """「还踩了一脚」前句无动作仍判连说，未过宽。"""
    from app.services.daily_story.story_types.b.humor import _chain_anaphora_tag

    line = "他还踩了一脚泥。"
    prev2 = "地上全是水。"
    assert _chain_anaphora_tag(line, prev2) == "还字缺前句动作"


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


def test_b_freeze_rejects_double_side_ding():
    from app.services.daily_story.story_types.b.humor import _freeze_lines_issues

    assert _freeze_lines_issues(["这下死定了……", "死定了死定了！"]) == "死定了句式重复"


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


def test_b_landing_accepts_double_doom_tail():
    from app.services.daily_story.story_types.b.humor import analyze_punish_landing

    lines = [
        "前段结盟",
        "走样连锁",
        "都怪你望风",
        "是你先弄洒",
        "妈妈：你俩，过来站好！",
        "昭昭：完蛋了！",
        "灿灿：真倒霉……",
    ]
    speakers = [
        "昭昭", "灿灿", "昭昭", "灿灿", "妈妈", "昭昭", "灿灿",
    ]
    weak, tag = analyze_punish_landing(lines, speakers)
    assert not weak, tag


def test_b_landing_flags_doom_phrase_repeat():
    from app.services.daily_story.story_types.b.humor import (
        analyze_punish_landing,
        collect_humor_issues,
    )

    lines = [
        "结盟",
        "走样",
        "妈妈：你俩，过来站好！",
        "昭昭：完蛋了。",
        "灿灿：我也完了。",
        "昭昭：都怪你！",
        "灿灿：是你先！",
        "昭昭：哼，才不是。",
    ]
    speakers = [
        "昭昭", "灿灿", "妈妈", "昭昭", "灿灿", "昭昭", "灿灿", "昭昭",
    ]
    weak, _ = analyze_punish_landing(lines, speakers)
    assert not weak
    issues = collect_humor_issues(lines, speakers)
    assert any("句式重复" in c for c in issues)
    assert any("定格后多余对白" in c for c in issues)


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

    # D「勿写成 A」不得误中 C 式赛规提示
    err_d = (
        "D类收束勿写成 A 式末四拍（引话+那不一样+哪里不一样）；"
        "应走叮嘱方破规+字面回旋镖"
    )
    assert pick_primary_validation_errors(err_d)[0].startswith("D类收束")
    hint_d = build_validation_retry_hints(err_d, chars=300, type_code="D")
    assert "D·去A化" in hint_d
    assert "赛规回旋镖" not in hint_d
    assert "你自己说" in hint_d


def test_build_quality_revision_hints_consecutive_before_humor():
    from app.services.daily_story.quality import build_quality_revision_hints
    from app.services.daily_story.retry_hints import pick_primary_quality_issue

    cons = [
        "存在同人连说",
        "B连锁也又还缺前句（我也缺前句动作）",
    ]
    kind, issue = pick_primary_quality_issue(cons)
    assert kind == "consecutive"
    assert issue == "存在同人连说"

    story = _valid_story()
    hints = build_quality_revision_hints(
        {
            "reasons": [
                "冲突推进4层",
                *cons,
                "结构67",
                "好笑5",
            ],
            "score": 72,
        },
        story=story,
    )
    assert "连说" in hints
    assert "勿只改 speaker" in hints
    assert "也又还" not in hints


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


def test_b_patch_strips_alliance_orphan_ye():
    from app.services.daily_story.story_types.b.patch import patch_b_orphan_ye

    story = {
        "punchline_explain": "B类结盟翻车",
        "dialogue": [
            {"speaker": "昭昭", "line": "姐，冰箱里蛋糕好香啊，要不要吃？"},
            {"speaker": "灿灿", "line": "小声点，吃完把盘子藏好别让妈发现。"},
            {"speaker": "昭昭", "line": "我也想吃，你切蛋糕，我负责望风。"},
            {"speaker": "灿灿", "line": "好，我切两块，你盯紧厨房门口。"},
            {"speaker": "灿灿", "line": "哎呀奶油滴桌布了！"},
            {"speaker": "妈妈", "line": "你俩拿的什么！又偷吃！"},
            {"speaker": "昭昭", "line": "被发现了！"},
        ],
    }
    notes = patch_b_orphan_ye(story)
    assert notes
    assert story["dialogue"][2]["line"] == "我想吃，你切蛋糕，我负责望风。"


def test_b_humor_ye_overuse():
    from app.services.daily_story.story_types.b.humor import collect_ye_overuse_issues

    lines = [
        "姐咱俩吃。",
        "好我也来。",
        "我也想吃。",
        "蛋糕也掉了。",
        "墙边也脏了。",
        "妈妈站好！",
        "完了！",
    ]
    issues = collect_ye_overuse_issues(lines, ["昭昭", "灿灿", "昭昭", "灿灿", "昭昭", "妈妈", "昭昭"])
    assert issues
    assert "B也字过多" in issues[0]


def test_b_patch_inserts_pre_punish_blame():
    from app.services.daily_story.story_types.b.patch import patch_b_ensure_pre_punish_blame

    story = {
        "punchline_explain": "B类结盟翻车",
        "dialogue": [
            {"speaker": "昭昭", "line": "嘘咱俩快藏。"},
            {"speaker": "灿灿", "line": "好你望风我藏。"},
            {"speaker": "灿灿", "line": "哎呀袋子破了！"},
            {"speaker": "昭昭", "line": "渣掉地上了！"},
            {"speaker": "灿灿", "line": "快用脚挡！"},
            {"speaker": "昭昭", "line": "来不及了！"},
            {"speaker": "妈妈", "line": "你俩，站好！"},
            {"speaker": "昭昭", "line": "被发现了！"},
            {"speaker": "灿灿", "line": "这下死定了……"},
        ],
    }
    notes = patch_b_ensure_pre_punish_blame(story)
    assert notes
    pre_mom = "".join(
        d["line"] for d in story["dialogue"][: story["dialogue"].index(
            next(d for d in story["dialogue"] if d["speaker"] == "妈妈"),
        )]
    )
    assert "都怪" in pre_mom or "说我" in pre_mom


def test_b_humor_flags_ungrounded_signal_ref():
    from app.services.daily_story.story_types.b.humor import collect_signal_and_freeze_issues

    lines = [
        "嘘咱俩吃蛋糕",
        "你切我望风",
        "哎呀洒了",
        "快擦",
        "都怪你望风",
        "暗号没用",
        "妈妈站好",
        "被发现了",
    ]
    speakers = ["昭昭", "灿灿", "昭昭", "灿灿", "昭昭", "灿灿", "妈妈", "昭昭"]
    issues = collect_signal_and_freeze_issues(lines, speakers)
    assert any("暗号无前文" in c for c in issues)


def test_b_humor_flags_verbose_freeze():
    from app.services.daily_story.story_types.b.humor import collect_signal_and_freeze_issues

    lines = [
        "结盟",
        "走样",
        "甩锅",
        "妈妈：你俩站好",
        "昭昭：露馅了，这下惨了，怎么办。",
        "灿灿：完了完了，全完了，被抓住了。",
    ]
    speakers = ["昭昭", "灿灿", "昭昭", "妈妈", "昭昭", "灿灿"]
    issues = collect_signal_and_freeze_issues(lines, speakers)
    assert any("定格啰嗦" in c for c in issues)


def test_b_patch_merges_mom_lines():
    from app.services.daily_story.story_types.b.patch import patch_b_merge_mom_lines

    story = {
        "punchline_explain": "B类结盟翻车",
        "dialogue": [
            {"speaker": "妈妈", "line": "满地都是牛奶！"},
            {"speaker": "妈妈", "line": "你俩站好！"},
            {"speaker": "昭昭", "line": "被发现了……"},
        ],
    }
    notes = patch_b_merge_mom_lines(story)
    assert notes
    assert story["dialogue"][0]["line"] == "满地都是牛奶，你俩站好！"
    assert len(story["dialogue"]) == 2


def test_validate_e_lie_rejects_batch3_garbage():
    from app.services.daily_story.prompts import (
        validate_daily_story_json,
        validate_daily_story_opening,
    )

    story = {
        "_theme": "不许说谎妈妈刚才也敷衍奶奶",
        "scene_title": "不许说谎",
        "setting": "客厅，妈妈刚打完电话",
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


def test_review_local_issues_catch_dup_and_empty_line():
    from app.services.daily_story.review import collect_local_issues

    issues = collect_local_issues(_review_story())
    kinds = {(it["kind"], tuple(it["lines"])) for it in issues}
    assert ("重复", (1, 5)) in kinds
    assert ("其他", (3,)) in kinds


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


def test_review_topic_cluster_skips_compact_good_story():
    """压缩正例只摆一次物证/质问，不应误伤。"""
    from app.services.daily_story.review import collect_local_issues

    story = {
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
    assert collect_local_issues(story) == []


def test_review_merge_issues_dedups_overlapping_lines():
    from app.services.daily_story.review import merge_issues

    merged = merge_issues(
        [{"lines": [11, 14], "kind": "重复", "desc": "a", "fix": ""}],
        [{"lines": [3, 11, 14], "kind": "重复", "desc": "b", "fix": ""}],
    )
    assert len(merged) == 1
    assert merged[0]["lines"] == [3, 11, 14]


def test_review_parse_issues_drops_out_of_range_lines():
    from app.services.daily_story.review import parse_review_issues

    parsed = parse_review_issues(
        {
            "issues": [
                {"lines": [2], "kind": "矛盾", "desc": "有效"},
                {"lines": [99], "kind": "矛盾", "desc": "行号越界"},
                {"lines": [1], "kind": "矛盾", "desc": ""},
            ],
        },
        line_count=5,
    )
    assert [it["desc"] for it in parsed] == ["有效"]


def test_review_apply_spot_fixes_strips_prefix_and_syncs_opening():
    from app.services.daily_story.review import apply_spot_fixes

    fixed, notes = apply_spot_fixes(
        _review_story(),
        {"fixes": [{"no": 1, "line": "昭昭：妈，你刚才跟奶奶说啥了？"}]},
    )
    assert notes == ["第1句"]
    assert fixed["dialogue"][0]["line"] == "妈，你刚才跟奶奶说啥了？"
    assert fixed["discovery_opening"][0]["line"] == "妈，你刚才跟奶奶说啥了？"


def test_review_apply_spot_fixes_honors_only_filter():
    from app.services.daily_story.review import apply_spot_fixes

    fixed, notes = apply_spot_fixes(
        _review_story(),
        {
            "fixes": [
                {"no": 1, "line": "改第一句"},
                {"no": 4, "line": "改第四句"},
            ],
        },
        only={4},
    )
    assert notes == ["第4句"]
    assert fixed["dialogue"][0]["line"] == "妈，你跟奶奶说吃撑了，可你没吃。"
    assert fixed["dialogue"][3]["line"] == "改第四句"


def test_review_penalty_deducts_and_caps():
    from app.services.daily_story.review import REVIEW_PENALTY_CAP, review_penalty

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


def test_review_applies_penalty_to_quality_score_and_grade():
    from app.services.daily_story.review import apply_review_to_quality

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
