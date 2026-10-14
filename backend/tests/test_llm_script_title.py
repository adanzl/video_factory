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
    validate_daily_story_body_part_chars,
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

    # 口吻型（孩子原话甩锅）现在压过事件名初稿「X大作战」
    # （2026-10-14 专家评审重排评分表：口吻/反差优先于画面复述）
    assert (
        pick_best_chat_title(
            "月饼大作战",
            ["月饼全滚出来了", "妈，月饼不是我弄的"],
            max_len=10,
        )
        == "妈，月饼不是我弄的"
    )

    # avoid 命中降权：手动重跑时避免重复上一个标题（这个标题已被用过，不再选它）
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
    # 两条候选都不含 avoid 命中项，但「月饼渣，我踩的印」是画面复述 → 保留当前
    assert best3 == "月饼渣，我踩的印"

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
    """提示词给的是完整主题短语「分蛋糕」，绝不能把「分蛋」当短语；且只作建议不硬卡。"""
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
    assert "不强制" in prompt
    assert "标题必须原样保留" not in prompt
    assert "同一句式结构也最多出现 1 次" in prompt
    assert "孩子气硬规则" in prompt or "孩子当场脱口而出的话" in prompt
    assert "不能有语病" in prompt
    assert "语病自检" in prompt
    assert "说好分蛋糕先挑" in prompt
    assert "封面感硬规则" in prompt
    assert "大块归你？分蛋糕我先挑，赖皮" in prompt

def test_pick_best_chat_title_anchor_is_bonus_not_gate():
    """锚词降为软加分（2026-10-14 用户裁定）：不含主题词的钩子候选能胜出（#117 实景）。"""
    from app.services.script.optimize_title import pick_best_chat_title

    story = _job117_story()
    # 干净初稿（remap 后）也压不住更有钩子的候选
    assert (
        pick_best_chat_title(
            "姐弟抢娃娃，弟弟自砸头",
            ["砸姐姐不行，砸自己总行"],
            max_len=15,
            anchor_words=["抢娃娃"],
            soft_anchor_words=["砸头"],
            story_type="G",
            story_content=story,
        )
        == "砸姐姐不行，砸自己总行"
    )
    # 类型信息锚词硬卡仍在（与锚词门槛无关）：C 类缺「先挑/大块/白忙」的候选仍被拒
    assert (
        pick_best_chat_title(
            "分蛋糕",
            ["蛋糕分好了吗"],
            max_len=15,
            anchor_words=["分蛋糕"],
            story_type="C",
        )
        == "分蛋糕"
    )

def test_filter_chat_title_candidates_keeps_anchorless():
    """候选过滤只做合规红线（人物/标签/脏字符），锚词不再过滤候选。"""
    from app.services.script.optimize_title import filter_chat_title_candidates

    candidates = ["分蛋糕先挑咋还输了", "先挑反被挑走大块", "分蛋糕按字面白忙"]
    assert filter_chat_title_candidates(candidates) == candidates

def test_ensure_chat_title_candidates_refills_to_three():
    """有效候选不足 3 个时重生成补足到 3 个；合规候选不再因缺锚词被丢。"""
    from app.services.script.optimize_title import ensure_chat_title_candidates

    fetch = iter([
        ["先挑咋还输了", "分蛋糕按字面白忙", "分蛋糕大小不均亏"],
        ["分蛋糕先挑反被挑走大块", "分蛋糕咋还输了", "分蛋糕立规反被挑"],
    ])
    out = ensure_chat_title_candidates(
        ["分蛋糕先挑咋还输了"],
        fetch_candidates=lambda: next(fetch),
        max_attempts=2,
    )
    assert len(out) == 3
    assert out[0] == "分蛋糕先挑咋还输了"
    # 缺「分蛋糕」的候选也保留（锚词已不过滤）；同串仍去重
    assert out[1] == "先挑咋还输了"
    assert out.count("分蛋糕先挑咋还输了") == 1

def _job101_sister_roast_story() -> dict:
    """金故事源标题带「怼妈」，转写后对白只有灿灿/昭昭。"""
    return {
        "scene_title": "萌娃金句怼妈",
        "theme": "萌娃金句怼妈",
        "key": "金句怼妈",
        "conflict_core": "妈妈考验女儿社交观，反被女儿用历史典故和哲理金句问倒",
        "setting": "客厅沙发上，灿灿端着水杯，昭昭盘腿坐着，两人面对面聊夸奖和朋友",
        "story_type": "I",
        "dialogue": [
            {"speaker": "灿灿", "line": "昭昭，别人夸你好看，你怎么一点都不激动？"},
            {"speaker": "昭昭", "line": "智慧没增加，光好看有什么用，看看戚夫人和吕雉。"},
            {"speaker": "灿灿", "line": "那你说，朋友多了到底好不好？"},
            {"speaker": "昭昭", "line": "姐姐，你爱朋友多，还是爱自己开心？"},
            {"speaker": "灿灿", "line": "行行行，我说不过你，你赢了。"},
            {"speaker": "昭昭", "line": "看你还嘴硬！"},
        ],
    }


def test_title_absent_roles_ignores_ganma():
    """「干嘛」里的妈不算家庭角色。"""
    from app.services.script.optimize_title import title_absent_roles

    story = {
        "dialogue": [
            {"speaker": "灿灿", "line": "你干嘛抢遥控器"},
            {"speaker": "昭昭", "line": "我先拿到的"},
        ],
    }
    assert title_absent_roles("你干嘛抢遥控器", story) == ()


def test_chat_title_rejects_mom_when_dialogue_has_no_mom():
    """源标题「怼妈」但对白是姐弟：不保初稿、不强制锚、候选丢掉妈妈。"""
    from app.services.script.optimize_title import (
        build_chat_title_user_prompt,
        extract_core_anchor_words,
        filter_chat_title_candidates,
        maybe_keep_cover_draft,
        pick_best_chat_title,
        title_absent_roles,
    )

    story = _job101_sister_roast_story()
    assert title_absent_roles("萌娃金句怼妈", story) == ("妈妈",)
    assert title_absent_roles("萌娃金句怼妈妈", story) == ("妈妈",)
    assert title_absent_roles("别人夸你好看", story) == ()
    assert maybe_keep_cover_draft("萌娃金句怼妈", story, max_len=15) is None
    assert extract_core_anchor_words("萌娃金句怼妈", story) == []
    assert filter_chat_title_candidates(
        ["萌娃金句怼妈妈", "别人夸你好看", "姐姐你爱朋友多"],
        story_content=story,
    ) == ["别人夸你好看", "姐姐你爱朋友多"]
    best = pick_best_chat_title(
        "萌娃金句怼妈",
        ["萌娃金句怼妈妈", "别人夸你好看"],
        max_len=15,
        story_content=story,
    )
    assert best == "别人夸你好看"
    assert "妈" not in best
    prompt = build_chat_title_user_prompt(
        draft_title="萌娃金句怼妈",
        story_content=story,
        max_title_len=15,
    )
    assert "【硬性·对白人物】" in prompt
    assert "未出现：妈妈" in prompt
    assert "对白出场：灿灿、昭昭" in prompt
    assert "本集核心物件/动作（须保留" not in prompt


def test_chat_title_keeps_mom_when_dialogue_has_mom():
    """对白有妈妈时，标题可以写妈妈；封面初稿仍可保留。"""
    from app.services.script.optimize_title import (
        maybe_keep_cover_draft,
        title_absent_roles,
    )

    story = {
        "scene_title": "洗手不搓泡",
        "theme": "妈妈教洗手",
        "story_type": "E",
        "dialogue": [
            {"speaker": "妈妈", "line": "洗手要搓出泡"},
            {"speaker": "昭昭", "line": "我搓了呀"},
        ],
    }
    assert title_absent_roles("妈妈洗手不搓泡", story) == ()
    assert maybe_keep_cover_draft("洗手不搓泡", story, max_len=15) == "洗手不搓泡"


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


def test_story_type_prompts_only_inject_matching_scene_rules():
    a_brush_system, a_brush_user = build_daily_story_prompts(
        "姐姐嫌弟弟刷牙太快",
        story_type="A",
    )
    a_brush = a_brush_system + a_brush_user
    assert "这刀还没剪直" not in a_brush
    assert "下剪" not in a_brush_user
    assert "顺着推" not in a_brush_user
    assert "压着剪" not in a_brush_user
    assert "你刚剪的这一刀" not in a_brush_user
    assert "不强制使用「那不一样」「哪里不一样」" in a_brush

    a_cut_system, a_cut_user = build_daily_story_prompts(
        "姐姐教弟弟剪纸却自己剪歪",
        story_type="A",
    )
    assert "剪纸场景补充" in a_cut_system
    assert "下剪、压线、翻面、对折" in a_cut_system
    assert "你刚剪的这一刀" in a_cut_user
    assert "倒数第3 句必须含「那不一样」" not in a_cut_user

    c_turns_system, c_turns_user = build_daily_story_prompts(
        "姐弟争论家务应该轮流还是按贡献分配",
        story_type="C",
    )
    c_turns = c_turns_system + c_turns_user
    assert "通用公平分支" in c_turns
    assert "瓶身/吸管" not in c_turns
    assert "轮流、贡献、承诺、补偿" in c_turns

    d_system, d_user = build_daily_story_prompts(
        "姐姐让弟弟把鞋带系紧",
        story_type="D",
    )
    assert "模板之外的字一个不改" not in d_system + d_user

    d_water_system, _d_water_user = build_daily_story_prompts(
        "浇花别浇太多水",
        story_type="D",
    )
    assert "整座端进箱子" not in d_water_system
    assert "离手即塌" not in d_water_system
    assert "字面执行推到极限" in d_water_system
    assert "锁语义，不锁固定台词" in d_system


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


def test_validate_stitched_story_counts_body_without_opening():
    story = _valid_story(n=18)
    opening = [
        {"speaker": "昭昭", "line": "开场第一句呀呀呀呀呀呀呀呀呀呀呀呀"},
        {"speaker": "灿灿", "line": "开场第二句呀呀呀呀呀呀呀呀呀呀呀呀"},
    ]
    story["discovery_opening"] = opening
    story["dialogue"] = opening + story["dialogue"]
    with pytest.raises(ValueError, match="总字数须≤"):
        validate_daily_story_json(story, phase="body")
    validate_daily_story_body_part_chars(story)


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
    story["dialogue"][0]["speaker"] = "爷爷"
    with pytest.raises(ValueError, match="爷爷"):
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


def test_c_whole_item_format_block_matches_line_budget():
    from app.services.daily_story.prompts import build_daily_story_prompts

    theme = "沙发上的抱枕大战"
    system, _user = build_daily_story_prompts(theme, story_type="C")
    assert "数组长度必须等于 19、20、21 或 22" in system
    assert "数组长度必须等于 14、15 或 16" not in system


def test_e_core_word_substituted_in_user_prompt():
    from app.services.daily_story.prompts import (
        build_daily_story_prompts,
        extract_e_core_word,
    )

    theme = "九点了必须睡觉妈妈还在刷手机"
    assert extract_e_core_word(theme) == "睡觉"
    _sys, user = build_daily_story_prompts(theme, story_type="E")
    assert "核心词「睡觉」" in user
    assert "{core_word}" not in user


def test_revise_patch_direction_c_short_vs_e_long():
    from app.services.daily_story.prompts import (
        DAILY_STORY_BODY_CHARS_MAX,
        build_daily_story_prompts,
    )

    c_sys, c_user = build_daily_story_prompts(
        "沙发上的抱枕大战",
        story_type="C",
        length_mode="revise_patch",
        body_chars=230,
    )
    assert "偏短" in c_sys or "句内微调·偏短" in c_sys
    assert "偏长压缩" not in c_sys
    assert "偏短" in c_user

    e_sys, e_user = build_daily_story_prompts(
        "九点了必须睡觉妈妈还在刷手机",
        story_type="E",
        length_mode="revise_patch",
        body_chars=DAILY_STORY_BODY_CHARS_MAX + 10,
    )
    assert "偏长" in e_sys
    assert "各加 2–8 字" not in e_sys
    assert "偏长" in e_user


def test_e_user_allows_two_consecutive_lines_not_ban_lianshuo():
    from app.services.daily_story.prompts import build_daily_story_prompts

    _sys, user = build_daily_story_prompts(
        "九点了必须睡觉妈妈还在刷手机",
        story_type="E",
    )
    assert "禁同人连说" not in user
    assert "最多连续2句" in user


def test_e_patch_keeps_two_consecutive_sibling_lines():
    from app.services.daily_story.prompts import (
        _patch_consecutive_speakers,
        try_local_patch_daily_story_body,
    )

    story = {
        "punchline_explain": "E类妈妈破功，睡觉规矩被戳穿",
        "conflict_core": "姐弟抓妈妈九点后刷手机",
        "setting": "客厅沙发",
        "dialogue": [
            {"speaker": "妈妈", "line": "九点了必须睡觉别磨蹭"},
            {"speaker": "灿灿", "line": "你刚才还说大人要早睡呢"},
            {"speaker": "灿灿", "line": "手机屏还亮着我都看见了"},
            {"speaker": "昭昭", "line": "就是说啊你自己先破规矩"},
            {"speaker": "妈妈", "line": "好好好我这就放下手机"},
        ],
    }
    notes = _patch_consecutive_speakers(story)
    assert story["dialogue"][1]["speaker"] == "灿灿"
    assert story["dialogue"][2]["speaker"] == "灿灿"
    assert not any(n.startswith("连说改speaker[2]") for n in notes)
    _out, notes2 = try_local_patch_daily_story_body(story)
    assert _out["dialogue"][1]["speaker"] == "灿灿"
    assert _out["dialogue"][2]["speaker"] == "灿灿"


def test_e_patch_still_breaks_three_consecutive_sibling_lines():
    from app.services.daily_story.prompts import _patch_consecutive_speakers

    story = {
        "punchline_explain": "E类妈妈破功",
        "dialogue": [
            {"speaker": "灿灿", "line": "第一句帮腔"},
            {"speaker": "灿灿", "line": "第二句帮腔"},
            {"speaker": "灿灿", "line": "第三句不该连说"},
            {"speaker": "妈妈", "line": "好了别吵"},
        ],
    }
    _patch_consecutive_speakers(story)
    run = sum(
        1
        for d in story["dialogue"][:3]
        if d.get("speaker") == "灿灿"
    )
    assert run <= 2


def test_revise_patch_in_band_for_yinhua_and_g_long():
    from app.services.daily_story.prompts import (
        DAILY_STORY_BODY_CHARS_MAX,
        DAILY_STORY_BODY_CHARS_MIN,
        build_daily_story_prompts,
    )

    mid = (DAILY_STORY_BODY_CHARS_MIN + DAILY_STORY_BODY_CHARS_MAX) // 2
    e_sys, e_user = build_daily_story_prompts(
        "九点了必须睡觉妈妈还在刷手机",
        story_type="E",
        length_mode="revise_patch",
        body_chars=mid,
    )
    assert "达标" in e_sys
    assert "各加 2–8 字" not in e_sys
    assert "达标只修局部" in e_user

    g_sys, g_user = build_daily_story_prompts(
        "谁先写完作业",
        story_type="G",
        length_mode="revise_patch",
        body_chars=DAILY_STORY_BODY_CHARS_MAX + 10,
    )
    assert "偏长" in g_sys
    assert "压到" in g_sys or "删冗余" in g_sys
    assert "偏长句内删" in g_user or "压到" in g_user


def _job117_story() -> dict:
    """#117 稿子：源稿称谓「双胞胎/妹妹」，站内角色是灿灿/昭昭。"""
    return {
        "scene_title": "双胞胎抢娃娃，妹妹自砸头",
        "theme": "双胞胎抢娃娃，妹妹自砸头",
        "setting": "客厅沙发前，灿灿怀里抱着布娃娃，昭昭脚边摊着一本硬壳绘本",
        "conflict_core": "灿灿和昭昭抢同一个布娃娃，谁也不让谁。",
        "key": "抢娃娃自砸头",
        "dialogue": [
            {"speaker": "灿灿", "line": "这个布娃娃我先抱的，你松手别拽了！"},
            {"speaker": "昭昭", "line": "我没砸姐姐，我砸我自己总行！"},
        ],
    }


def test_extract_core_anchor_words_no_cross_word_fragment():
    """长 scene_title 不再切出跨词碎片：双胞胎抢娃娃→抢娃娃，不是「胎抢娃娃」。"""
    from app.services.script.optimize_title import extract_core_anchor_words

    anchors = extract_core_anchor_words("双胞胎抢娃娃，妹妹自砸头", _job117_story())
    assert anchors == ["抢娃娃", "砸头"]
    for bad in ("胎抢娃娃", "妹妹自砸", "妹妹", "双胞胎"):
        assert bad not in anchors
    # 段内切出来的窗口必须由剧本正文自证：「抢鸡爪」正文里没有 → 退回正文认过的「阳台」
    chicken = {
        "scene_title": "阳台抢鸡爪",
        "setting": "阳台上摆着小板凳，鸡爪放在盘子里",
        "conflict_core": "灿灿和昭昭都想要盘子里的鸡爪。",
        "key": "抢食加码",
    }
    assert extract_core_anchor_words("阳台抢鸡爪", chicken) == ["阳台"]


def test_title_guards_reject_source_labels_and_dirty_chars():
    """源稿标签（双胞胎/妹妹）与剧本里没有的拉丁字母不得进标题。"""
    from app.services.script.optimize_title import (
        filter_chat_title_candidates,
        title_source_label_leak,
        title_unusable,
    )

    story = _job117_story()
    assert title_source_label_leak("妹妹自砸头", story) == ("妹妹",)
    assert title_source_label_leak("双胞胎抢娃娃", story) == ("双胞胎",)
    # 站内关系只有姐弟：兄妹/兄弟/姐妹/龙凤胎 都是错关系词
    assert title_source_label_leak("龙凤胎抢娃娃", story) == ("龙凤胎",)
    assert title_source_label_leak("兄妹抢娃娃", story) == ("兄妹",)
    assert title_source_label_leak("姐妹抢娃娃", story) == ("姐妹",)
    assert title_source_label_leak("兄弟抢娃娃", story) == ("兄弟",)
    # 姐弟/姐姐/弟弟 是站内合法称呼，放行
    assert title_source_label_leak("姐弟抢娃娃", story) == ()
    assert title_source_label_leak("姐姐抢娃娃，弟弟自砸头", story) == ()
    assert title_unusable("胎抢娃娃，j自砸头", story) is True
    assert title_unusable("妹妹自砸头", story) is True
    assert title_unusable("抢娃娃，砸自己头", story) is False
    # 对白真提到过「妹妹」（第三方）时不算漏标
    third_party = dict(story, dialogue=[{"speaker": "灿灿", "line": "隔壁妹妹也想来玩。"}])
    assert title_source_label_leak("隔壁妹妹也想来", third_party) == ()
    # 剧本里出现过的字母放行（Q弹屁股救场）
    q_story = dict(story, scene_title="Q弹屁股救场", setting="昭昭一屁股坐上去，Q弹得很")
    assert title_unusable("Q弹屁股救场", q_story) is False
    # 候选层硬校验：漏标/脏字符候选直接作废
    out = filter_chat_title_candidates(
        ["布娃娃谁先抱归谁", "妹妹自砸头，姐姐认怂", "抢娃娃，j自砸头"],
        story_content=story,
    )
    assert out == ["布娃娃谁先抱归谁"]


def test_extract_hard_anchor_words_excludes_scene_only_words():
    """硬锚词只要动作/整段短语；纯场景词（阳台）只作软锚词，不作硬门槛。"""
    from app.services.script.optimize_title import (
        extract_core_anchor_words,
        extract_hard_anchor_words,
    )

    assert extract_hard_anchor_words("双胞胎抢娃娃，妹妹自砸头", _job117_story()) == ["抢娃娃"]
    # 「砸头」是段尾名词窗口 → 只作软锚词，仍进提示词与加分
    assert extract_core_anchor_words("双胞胎抢娃娃，妹妹自砸头", _job117_story()) == [
        "抢娃娃",
        "砸头",
    ]
    chicken = {
        "scene_title": "阳台抢鸡爪",
        "setting": "阳台上摆着小板凳，鸡爪放在盘子里",
        "conflict_core": "灿灿和昭昭都想要盘子里的鸡爪。",
        "key": "抢食加码",
    }
    assert extract_hard_anchor_words("阳台抢鸡爪", chicken) == []
    assert extract_core_anchor_words("阳台抢鸡爪", chicken) == ["阳台"]


def test_pick_best_chat_title_anchors_only_bonus():
    """锚词（含场景词）一律只加分：不含锚词的合规候选照样胜出。"""
    from app.services.script.optimize_title import pick_best_chat_title

    chicken = {
        "scene_title": "阳台抢鸡爪",
        "setting": "阳台上摆着小板凳，鸡爪放在盘子里",
        "conflict_core": "灿灿和昭昭都想要盘子里的鸡爪。",
        "key": "抢食加码",
    }
    # 硬锚词/软锚词都当过，候选缺锚词也不被作废（用口吻型候选：新评分下它压过画面初稿）
    for kwargs in (
        {"anchor_words": [], "soft_anchor_words": ["阳台"]},
        {"anchor_words": ["阳台"]},
    ):
        assert (
            pick_best_chat_title(
                "阳台抢鸡爪",
                ["凭啥鸡爪归你"],
                max_len=15,
                story_content=chicken,
                **kwargs,
            )
            == "凭啥鸡爪归你"
        )


def test_chat_title_prompt_anchor_note_no_longer_hard():
    """提示词里锚词只作建议，禁止再写「硬性必须含锚词」（会逼出事件复述）。"""
    from app.services.script.optimize_title import build_chat_title_user_prompt

    story = _job117_story()
    prompt = build_chat_title_user_prompt(
        draft_title="姐弟抢娃娃，弟弟自砸头",
        story_content=story,
        max_title_len=15,
    )
    assert "【建议·非强制】" in prompt
    assert "抢娃娃" in prompt
    assert "标题须含核心物件/动作" not in prompt
    assert "不含核心物件/动作的标题不合格" not in prompt
    assert "优先写有钩子的说法" in prompt


def test_polish_prompt_keeps_only_present_theme_words():
    """润色只保护当前标题里已有的主题词，不把主题短语塞回平掉的好标题。"""
    from app.services.script.optimize_title import build_chat_title_polish_prompts

    story = _job117_story()
    # 选中标题不含「抢娃娃」→ 不得要求必须保留该短语
    prompts = build_chat_title_polish_prompts(
        "砸姐姐不行，砸自己总行",
        "姐弟抢娃娃，弟弟自砸头",
        story,
        max_title_len=15,
    )
    assert "须原样保留" not in prompts["user"]
    assert "不得" in prompts["user"]
    # 选中标题含「抢娃娃」→ 照旧要求完整保留
    prompts2 = build_chat_title_polish_prompts(
        "抢娃娃，弟弟举书砸自己头",
        "姐弟抢娃娃，弟弟自砸头",
        story,
        max_title_len=15,
    )
    assert "须原样保留（当前标题里已有）：抢娃娃" in prompts2["user"]


def test_hook_score_prefers_voice_over_flat_and_keeps_c_calibration():
    """评分表锁定：口吻/原话 > 反转/金句 > 画面复述；「谁」类仍被压低；C 类不被剧透扣分误伤。"""
    from app.services.script.optimize_title import _chat_title_hook_score as s

    voice = s("我砸我自己总行", story_type="G")
    contrast = s("砸姐姐不行，砸自己总行", story_type="G")
    visual = s("举书砸自己脑袋", story_type="G")
    assert voice > visual and contrast > visual
    # 画面基分降到 2：不再靠 +4 压过口吻型
    assert visual <= 4
    # 「谁」字质问句仍被压低（历史上刷过屏）
    for who in ("谁踩的渣印", "渣印谁擦"):
        assert s(who, story_type="G") < visual
    # C 类不过封面剧透表：「白忙」是硬卡要求的必需信息锚词，不能反被扣 5 分
    assert s("说好我先挑，白忙一场", story_type="C") == s("说好我先挑，白忙一场", story_type="G") + 5


def test_polish_rejects_particle_only_flatening_for_non_c():
    """非 C 类禁止靠加语气词压平（「举书砸自己脑袋」→「…脑袋了」）；C 类保留白忙→白忙了。"""
    from app.services.script.optimize_title import build_chat_title_polish_prompts

    story = _job117_story()
    prompts = build_chat_title_polish_prompts(
        "我砸我自己总行", "姐弟抢娃娃，弟弟自砸头", story, max_title_len=15
    )
    assert "禁止新增原标题没有的语气词" in prompts["user"]
    assert "缺语气词要补" not in prompts["user"]
    # C 类仍保留补语气词校准
    c_story = dict(story, story_type="C")
    c_prompts = build_chat_title_polish_prompts(
        "分蛋糕先挑，白忙", "分蛋糕", c_story, max_title_len=15
    )
    assert "缺语气词要补" in c_prompts["user"]


def test_pick_best_chat_title_unusable_draft_not_fallback():
    """手输初稿带脏字符时：不当基线、也不当「无锚词候选」的兜底，让候选胜出。"""
    from app.services.script.optimize_title import pick_best_chat_title, title_unusable

    story = _job117_story()
    picked = pick_best_chat_title(
        "抢娃娃，j自砸头",
        ["举书砸头反砸自己", "布娃娃谁先抱归谁"],
        max_len=15,
        anchor_words=["娃娃"],
        story_content=story,
        avoid_titles=["抢娃娃，j自砸头"],
    )
    assert picked != "抢娃娃，j自砸头"
    assert title_unusable(picked, story) is False
    # 一个可用候选都没有时不许返回空串（否则会把 job 标题写没）
    assert pick_best_chat_title(
        "抢娃娃，j自砸头", [], max_len=15, anchor_words=["娃娃"], story_content=story,
    ) != ""

