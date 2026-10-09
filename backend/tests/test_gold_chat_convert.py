"""gold_chat 转换测试。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.gold_story.gold_chat import convert as gc
from app.services.gold_story.gold_chat import expand as gex
from app.services.gold_story.gold_chat import finalize as gcf
from app.services.gold_story.gold_chat import refine as grf
from app.services.gold_story.gold_chat import export as gce


def _sample_row() -> dict:
    return {
        "id": 1,
        "source_id": "BV1TEST0001",
        "url": "https://www.bilibili.com/video/BV1TEST0001",
        "title": "测试标题",
        "mechanism": "M6",
        "structure_type": "A",
        "status": "active",
        "conflict_core": "弟弟幻想报复姐姐，开门秒怂",
        "payload": {
            "setting": "卧室门口",
            "beat": ["被欺负", "关门幻想", "开门怂", "姐姐得意"],
            "dialogue_seed": [
                {"speaker": "昭昭", "intent": "抱怨被欺负"},
                {"speaker": "灿灿", "intent": "得意威胁"},
            ],
            "closing_intent": "昭昭缩回角落",
            "banned_literals": ["小姨", "萌娃"],
            "funny_why": "幻想与怂的反差",
        },
    }


def _sample_chat() -> dict:
    lines = [
        {"speaker": "昭昭", "line": "你刚才又抢我遥控器，我还不敢说。"},
        {"speaker": "灿灿", "line": "谁让你手慢，我先用就是我的。"},
        {"speaker": "昭昭", "line": "那我关上门，我在里面练功夫，等会儿打回来。"},
        {"speaker": "灿灿", "line": "你练啊，开门我看你还敢不敢。"},
        {"speaker": "昭昭", "line": "我……我先看看你在不在门口。"},
        {"speaker": "灿灿", "line": "在啊，你出来试试。"},
        {"speaker": "昭昭", "line": "算了算了，我先不跟你计较。"},
        {"speaker": "灿灿", "line": "刚才不是说要打回来吗？"},
        {"speaker": "昭昭", "line": "我就是先歇一会儿，又不是怕你。"},
        {"speaker": "灿灿", "line": "那你把门打开，别躲里面。"},
        {"speaker": "昭昭", "line": "不开，我要再练两招。"},
        {"speaker": "灿灿", "line": "行，你练，我等着。"},
        {"speaker": "昭昭", "line": "好了好了，遥控器还你一半行吧。"},
        {"speaker": "灿灿", "line": "这还差不多，明天继续。"},
    ]
    while gc.dialogue_total_chars({"dialogue": lines}) < 240:
        lines.append(
            {
                "speaker": "昭昭",
                "line": "我就是先歇一会儿，又不是怕你。",
            }
        )
    return {
        "scene_title": "关门练功",
        "setting": "卧室门口",
        "key": "关门练功",
        "conflict_core": "弟弟幻想报复姐姐，开门秒怂",
        "dialogue": lines,
        "punchline_explain": "A类嘴硬加码：幻想英勇开门就怂",
    }


def test_validate_gold_chat_ok():
    story = _sample_chat()
    gc.validate_gold_chat(story, banned_literals=["小姨"])


def test_ensure_gold_chat_min_chars_does_not_force_dirty_fill():
    """机械清理后宁可保留字数不足，也不靠固定态度尾巴硬凑 240。"""
    story = {
        "story_type": "J",
        "dialogue": [
            {"speaker": "昭昭", "line": "这是我的地盘，你快走开听见没有呀真的！"},
            {"speaker": "灿灿", "line": "我先趴在这儿的，该你马上走开听见没有！"},
            {"speaker": "昭昭", "line": "哼，看招，我先推你一下试试看啊真的！"},
            {"speaker": "灿灿", "line": "你敢打我，我就马上告诉妈妈去啊真的！"},
            {"speaker": "昭昭", "line": "就打你，你抢了我的位置啊真的不行！"},
            {"speaker": "灿灿", "line": "谁赢谁说了算，咱们现在来比呀啊！"},
            {"speaker": "昭昭", "line": "我拿出最强形态，再出拳打你啊听见！"},
            {"speaker": "灿灿", "line": "草莓熊肘击，我砸你肚子一下听清楚！"},
            {"speaker": "昭昭", "line": "哎哟我输了，你也太厉害啦呀真的！"},
            {"speaker": "灿灿", "line": "玩具都归我，你到那边去躺着吧啊！"},
            {"speaker": "昭昭", "line": "等长大再算账，我现在怕你啊真的！"},
            {"speaker": "灿灿", "line": "我说了算，你乖乖躺好别动呀听见！"},
        ],
    }
    chars = gc.dialogue_total_chars(story)
    assert chars < gc.DAILY_STORY_BODY_CHARS_MIN
    assert gc.DAILY_STORY_BODY_CHARS_MIN - chars <= gc.GOLD_CHAT_NEAR_MISS_DEFICIT_MAX
    out, changed = gc._ensure_gold_chat_min_chars(story)
    assert changed
    assert gc.dialogue_total_chars(out) < gc.DAILY_STORY_BODY_CHARS_MIN
    blob = "".join(str(row.get("line") or "") for row in out["dialogue"])
    assert not any(
        phrase in blob
        for phrase in (
            "我偏就不信",
            "说一不二",
            "马上给我挪开",
            "少废话听我的",
        )
    )

    # 大缺口：剥灌尾后不靠粒子硬凑到 240
    short = {
        "story_type": "J",
        "dialogue": [
            {"speaker": "昭昭", "line": "看招！"},
            {"speaker": "灿灿", "line": "谁赢谁说了算！"},
        ]
        * 6,
    }
    out_short, _ = gc._ensure_gold_chat_min_chars(short)
    assert gc.dialogue_total_chars(out_short) < gc.DAILY_STORY_BODY_CHARS_MIN


def test_generic_n_near_miss_does_not_inject_attitude_tails():
    from app.services.gold_story.gold_chat.length import (
        _expand_short_gold_chat_lines,
        _pad_gold_chat_line,
    )

    story = {
        "story_type": "N",
        "dialogue": [
            {
                "speaker": "昭昭" if i % 2 == 0 else "灿灿",
                "line": "我就是这么想的，你先听我说。",
            }
            for i in range(12)
        ],
    }
    out, changed = _expand_short_gold_chat_lines(
        story,
        ignore_deficit_cap=True,
    )
    assert not changed
    blob = "".join(row["line"] for row in out["dialogue"])
    assert not any(
        phrase in blob
        for phrase in (
            "我偏就不信",
            "说一不二",
            "马上给我挪开",
            "我可记住啦",
        )
    )

    padded, added = _pad_gold_chat_line(
        "我回房间补作业。",
        1,
        story_type="N",
        speaker="灿灿",
    )
    assert added == 1
    assert padded in {
        "我回房间补作业啊。",
        "我回房间补作业呢。",
        "我回房间补作业吧。",
        "我回房间补作业呀。",
    }

    already_particle, added = _pad_gold_chat_line(
        "铅笔找不到了嘛。",
        3,
        story_type="N",
        speaker="灿灿",
    )
    assert added == 0
    assert already_particle == "铅笔找不到了嘛。"


def test_relay_parent_prefix_is_rewritten_to_direct_speech():
    from app.services.gold_story.scene import (
        collect_voice_errors,
        patch_dialogue_narration_to_speech,
    )

    story = {
        "dialogue": [
            {"speaker": "灿灿", "line": "妈妈说，用过的东西放回原位，这是习惯。"},
        ],
    }
    notes = patch_dialogue_narration_to_speech(story)

    assert story["dialogue"][0]["line"] == "用过的东西放回原位，这是习惯。"
    assert notes == ["转述→现场对白[1]"]
    assert collect_voice_errors(story["dialogue"]) == []


    not_relay = {"dialogue": [{"speaker": "昭昭", "line": "反正爸爸说了算。"}]}
    assert patch_dialogue_narration_to_speech(not_relay) == []
    assert not_relay["dialogue"][0]["line"] == "反正爸爸说了算。"


def test_g_cleanup_224_near_miss_closes_with_semantic_mid_pair():
    from app.services.gold_story.gold_chat.length import _stabilize_local_length_candidate

    def fit(text: str, size: int) -> str:
        core = text.rstrip("。")
        return (core + "真" * size)[: size - 1] + "。"

    bases = [
        ("妈妈", "昭昭把玩具收好"),
        ("昭昭", "我还没玩完等会再收"),
        ("灿灿", "用完的东西要放回去"),
        ("昭昭", "你干嘛动我的积木"),
        ("灿灿", "我先把这边收起来"),
        ("昭昭", "我还想继续玩呢"),
        ("灿灿", "那我先去看书了"),
        ("昭昭", "等等剩下的我来收"),
        ("灿灿", "那边还有几块别漏"),
        ("昭昭", "知道啦我这就收"),
        ("灿灿", "我去沙发看书"),
        ("昭昭", "那我也读给我留位置"),
    ]
    dialogue = [
        {"speaker": speaker, "line": fit(line, 18 if i < 8 else 20)}
        for i, (speaker, line) in enumerate(bases)
    ]
    story = {"story_type": "G", "dialogue": dialogue}
    assert gc.dialogue_total_chars(story) == 224

    out, changed = _stabilize_local_length_candidate(
        story,
        structure_type="G",
        mechanism="M4",
        dialogue_seed=[
            {"speaker": "妈妈", "intent": "昭昭，把玩具收好"},
            {"speaker": "灿灿", "intent": "把积木按颜色码进箱子"},
        ],
    )

    assert changed
    assert gc.dialogue_total_chars(out) >= gc.DAILY_STORY_BODY_CHARS_MIN
    lines = [str(row.get("line") or "") for row in out["dialogue"]]
    assert "你还真要把这些都收好啊？" in lines
    assert "我先把手边这些放回去。" in lines


def test_g_111_pre_score_consecutive_cleanup_recovers_structure_without_filler():
    from app.services.daily_story.prompts import dialogue_total_chars
    from app.services.daily_story.quality import score_daily_story
    from app.services.gold_story.gold_chat.convert import (
        patch_gold_chat_consecutive_siblings,
    )
    from app.services.gold_story.gold_chat.length import _boost_short_with_mid_lines

    story = {
        "story_type": "G",
        "conflict_core": "昭昭拒绝收玩具，灿灿示范后昭昭主动跟随",
        "punchline_explain": "G类嘴硬心软，行动示范后主动跟随暖收",
        "dialogue": [
            {"speaker": "妈妈", "line": "昭昭，把玩具收好，地上都下不去脚了。"},
            {"speaker": "昭昭", "line": "我还没玩完呢，等会儿再收。"},
            {"speaker": "灿灿", "line": "昭昭，你踢积木干嘛？都散到沙发底下了。"},
            {"speaker": "昭昭", "line": "我就踢！反正我还没玩完，不收。"},
            {"speaker": "灿灿", "line": "用过的东西放回原位，这是习惯。"},
            {"speaker": "灿灿", "line": "不是罚你，是下次想玩一找就找到。"},
            {"speaker": "昭昭", "line": "我就是还没玩完，你别管我。"},
            {"speaker": "灿灿", "line": "行，我不吵，我把积木按颜色码好。"},
            {"speaker": "灿灿", "line": "红色放这格，蓝色放那格，你看着。"},
            {"speaker": "昭昭", "line": "姐姐，你码积木干嘛？又不玩了。"},
            {"speaker": "灿灿", "line": "我拿绘本看，每天读书学习是第十条。"},
            {"speaker": "昭昭", "line": "第十条？妈妈说的第十条是啥？"},
            {"speaker": "灿灿", "line": "对，妈妈说的，每天读书学习不能忘。"},
            {"speaker": "昭昭", "line": "那我也读，等我先把玩具收进柜子。"},
            {"speaker": "昭昭", "line": "姐姐，我收好了，挤一挤一起看。"},
            {"speaker": "灿灿", "line": "好，你坐这边，我翻页你跟着念。"},
            {"speaker": "昭昭", "line": "我念得慢，你别笑我。"},
            {"speaker": "灿灿", "line": "不笑，我等你，第十条要一起做到。"},
        ],
    }
    seed = [
        {"speaker": "妈妈", "intent": "昭昭，把玩具收好"},
        {"speaker": "昭昭", "intent": "我还没玩完呢"},
        {"speaker": "灿灿", "intent": "把积木按颜色码好"},
        {"speaker": "昭昭", "intent": "那我也读"},
    ]

    cleaned, notes = patch_gold_chat_consecutive_siblings(
        story,
        dialogue_seed=seed,
    )
    assert len([n for n in notes if n.startswith("G行动连说去冗余")]) == 3

    if dialogue_total_chars(cleaned) < gc.DAILY_STORY_BODY_CHARS_MIN:
        cleaned, changed = _boost_short_with_mid_lines(
            cleaned,
            structure_type="G",
            mechanism="M4",
            dialogue_seed=seed,
        )
        assert changed

    assert dialogue_total_chars(cleaned) >= gc.DAILY_STORY_BODY_CHARS_MIN
    kid_speakers = [
        str(row.get("speaker") or "")
        for row in cleaned["dialogue"]
        if str(row.get("speaker") or "") in {"昭昭", "灿灿"}
    ]
    assert all(a != b for a, b in zip(kid_speakers, kid_speakers[1:]))

    quality = score_daily_story(cleaned, skip_relevancy=True)
    reasons = " ".join(str(x) for x in quality.get("reasons") or [])
    assert int(quality.get("structure_score") or 0) >= 75
    assert "存在同人连说" not in reasons
    assert "冲突推进不足" not in reasons


def test_102_action_narration_is_locally_rewritten_without_structure_repair():
    from app.services.gold_story.scene import (
        collect_narration_dialogue_errors,
        collect_voice_errors,
        patch_dialogue_narration_to_speech,
        sanitize_dialogue_seed_speech,
    )

    story = {
        "dialogue": [
            {"speaker": "灿灿", "line": "抬手一巴掌拍在桌上，昭昭立刻缩手老实！"},
            {"speaker": "灿灿", "line": "端碗只说一个字：喝，眼神一冷昭昭就怂！"},
            {"speaker": "昭昭", "line": "乖乖接过碗，仰头灌了下去，苦得直咧嘴！"},
            {"speaker": "昭昭", "line": "抹着眼泪，二十年后又是一条好汉！"},
            {"speaker": "灿灿", "line": "瞪他一眼，作业写不写"},
        ],
    }
    notes = patch_dialogue_narration_to_speech(story)

    assert len(notes) == 5
    assert [row["line"] for row in story["dialogue"]] == [
        "一巴掌就老实了吧！",
        "喝！",
        "苦死我了！",
        "二十年后又是一条好汉！",
        "作业写不写？",
    ]
    assert collect_narration_dialogue_errors(story["dialogue"]) == []
    assert collect_voice_errors(story["dialogue"]) == []

    seed = sanitize_dialogue_seed_speech(
        [
            {"speaker": "灿灿", "intent": "抬手一巴掌，昭昭立刻老实"},
            {"speaker": "灿灿", "intent": "端碗只说一个字：喝"},
            {"speaker": "昭昭", "intent": "乖乖接过碗，仰头灌了下去"},
            {"speaker": "昭昭", "intent": "抹着眼泪，二十年后又是一条好汉"},
            {"speaker": "灿灿", "intent": "瞪他一眼，作业写不写"},
        ]
    )
    assert [row["intent"] for row in seed] == [
        "一巴掌就老实了吧！",
        "喝！",
        "我喝了！",
        "二十年后又是一条好汉！",
        "作业写不写？",
    ]


def test_j_m8_237_near_miss_closes_in_place_like_102():
    from app.services.daily_story.prompts import dialogue_total_chars
    from app.services.gold_story.gold_chat.length import _stabilize_local_length_candidate

    story = {
        "story_type": "J",
        "dialogue": [
            {"speaker": "灿灿", "line": "昭昭，坐好，我辅导你写作业，别耍赖啊。"},
            {"speaker": "昭昭", "line": "姐你今天真好看，头发像动画片里的公主吧。"},
            {"speaker": "灿灿", "line": "少扯，写作业，先写三行再喝药，规矩今天就这么定。"},
            {"speaker": "昭昭", "line": "三行太多，我写一行就喝，行不行啊姐啊。"},
            {"speaker": "昭昭", "line": "我手疼笔都握不住，明天写也一样对啊。"},
            {"speaker": "灿灿", "line": "手疼就换左手，本子摊平，别装可怜吧。"},
            {"speaker": "昭昭", "line": "那我先喝药，喝完药手更抖写不了字啊。"},
            {"speaker": "妈妈", "line": "昭昭乖，把药喝了，病才能好。"},
            {"speaker": "昭昭", "line": "太苦了，我不喝，闻着就想吐吧。"},
            {"speaker": "灿灿", "line": "喝啊！"},
            {"speaker": "昭昭", "line": "我喝我喝，别瞪我吧。"},
            {"speaker": "爸爸", "line": "我们吓唬都是假的，你姐是真打。"},
            {"speaker": "昭昭", "line": "二十年后咱又是一条好汉，你等着啊。"},
            {"speaker": "灿灿", "line": "哼，我说了算，你还敢顶嘴吧？"},
            {"speaker": "昭昭", "line": "不敢了，我这就去写作业啊。"},
        ],
    }
    assert dialogue_total_chars(story) == 237

    out, changed = _stabilize_local_length_candidate(
        story,
        structure_type="J",
        mechanism="M8",
    )

    assert changed
    assert dialogue_total_chars(out) >= 240
    assert len(out["dialogue"]) == len(story["dialogue"])
    assert out["dialogue"][9]["line"] == "喝啊，听我的！"


def test_n_local_semantic_mid_pair_recovers_clean_q96_shape():
    from app.services.daily_story.story_types.n.validate import append_n_body_errors
    from app.services.gold_story.gold_chat.length import (
        _stabilize_local_length_candidate,
    )

    story = {
        "story_type": "N",
        "dialogue": [
            {"speaker": "灿灿", "line": "我……我本来要写的，就是铅笔找不到了嘛。"},
            {"speaker": "昭昭", "line": "妈，我屁股很Q弹，你打我吧，别打姐姐。"},
            {"speaker": "妈妈", "line": "昭昭，你手都停半空了，为什么突然说这个？"},
            {"speaker": "昭昭", "line": "因为没人教，我自己想的，Q弹的打了不疼，还响呢！"},
            {"speaker": "灿灿", "line": "噗……昭昭你别说了，我肩膀都抖了。"},
            {"speaker": "妈妈", "line": "你还笑？作业没写你倒笑得出来？"},
            {"speaker": "昭昭", "line": "姐姐笑，是喜欢我屁股Q弹，还是不信？"},
            {"speaker": "灿灿", "line": "妈，我这就写，你别听昭昭胡说，快挪开。"},
            {"speaker": "昭昭", "line": "我没胡说，你看我扭一下，弹回来还带晃的。"},
            {"speaker": "妈妈", "line": "行吧行吧，你们俩一个比一个会捣乱。"},
            {"speaker": "灿灿", "line": "我回房间补作业，十分钟就写完吧。"},
            {"speaker": "昭昭", "line": "那妈，我屁股还打不打了？不打我收起来咯。"},
        ],
    }
    before = gc.dialogue_total_chars(story)
    assert before < gc.DAILY_STORY_BODY_CHARS_MIN

    out, changed = _stabilize_local_length_candidate(
        story,
        structure_type="N",
        mechanism="M6",
    )
    body = "".join(str(row.get("line") or "") for row in out["dialogue"])
    errors: list[str] = []
    append_n_body_errors(out, errors)

    assert changed
    assert gc.dialogue_total_chars(out) >= gc.DAILY_STORY_BODY_CHARS_MIN
    assert len(out["dialogue"]) > len(story["dialogue"])
    assert sum(1 for row in out["dialogue"] if row.get("speaker") == "妈妈") == 3
    # N 的明显长度缺口先走实义对，原有干净句不要再被单粒子污染。
    assert any("照这个道理认真想" in row["line"] for row in out["dialogue"])
    assert "噗……昭昭你别说了，我肩膀都抖了。" in [row["line"] for row in out["dialogue"]]
    assert "姐姐笑，是喜欢我屁股Q弹，还是不信？" in [row["line"] for row in out["dialogue"]]
    assert "妈，我这就写，你别听昭昭胡说，快挪开。" in [row["line"] for row in out["dialogue"]]
    assert not errors
    assert not any(
        phrase in body
        for phrase in ("我偏就不信", "说一不二", "马上给我挪开", "嘛真的吧", "咯呢")
    )


def test_n_229_near_miss_closes_locally_without_llm_regen():
    """N 已有理由链但可扩行顶格时，229→240 应走实义补位，不把 11 字缺口交给 LLM。"""
    from app.services.gold_story.gold_chat.length import _ensure_gold_chat_min_chars

    def full_line(text: str) -> str:
        return (text + "真" * 24)[:24]

    dialogue = [
        {"speaker": "妈妈", "line": "小时候这事又被提起来了"},
        {"speaker": "昭昭", "line": full_line("你为什么老说我那次只是运气好")},
        {"speaker": "灿灿", "line": full_line("因为我就是认真觉得那个理由说得通")},
        {"speaker": "昭昭", "line": full_line("我还可以继续把这个想法说清楚")},
        {"speaker": "灿灿", "line": full_line("那你就继续说我认真听着呢")},
        {"speaker": "昭昭", "line": full_line("我前面说的就是这个意思没变")},
        {"speaker": "灿灿", "line": full_line("我知道你是在认真解释这件事")},
        {"speaker": "昭昭", "line": full_line("所以我才一直按这个道理往下说")},
        {"speaker": "灿灿", "line": full_line("行那我再听听你还能怎么解释")},
        {"speaker": "妈妈", "line": "先听你们说完"},
        {"speaker": "妈妈", "line": "我还在听"},
        {"speaker": "妈妈", "line": "嗯" * 16},
    ]
    story = {"story_type": "N", "dialogue": dialogue}
    assert gc.dialogue_total_chars(story) == 229

    out, changed = _ensure_gold_chat_min_chars(
        story,
        structure_type="N",
        mechanism="M6",
    )

    assert changed
    assert gc.dialogue_total_chars(out) >= gc.DAILY_STORY_BODY_CHARS_MIN
    assert len(out["dialogue"]) == len(story["dialogue"]) + 2
    assert any("照这个道理认真想" in row["line"] for row in out["dialogue"])


def test_validate_expand_n_221_uses_contract_for_local_length_close(monkeypatch):
    """N 残稿未写出 why/reason 关键词时，也应从 beat 契约识别理由方，本地补长而非烧重生成。"""

    def full_line(text: str) -> str:
        return (text + "真" * 24)[:24]

    dialogue = [
        {"speaker": "妈妈", "line": "又说起你小时候那件旧事"},
        {"speaker": "昭昭", "line": full_line("哪是命大我明明会挑地方落")},
        {"speaker": "灿灿", "line": full_line("你每次都把这件事说得特别认真")},
        {"speaker": "昭昭", "line": full_line("我本来就是照自己的想法说的")},
        {"speaker": "灿灿", "line": full_line("那你继续把这个想法说清楚吧")},
        {"speaker": "昭昭", "line": full_line("我前面讲的意思一直都没有变")},
        {"speaker": "灿灿", "line": full_line("听起来你还真把它当成道理了")},
        {"speaker": "昭昭", "line": full_line("我当然是认真想过才这么说的")},
        {"speaker": "灿灿", "line": full_line("行我先听你把剩下的话讲完")},
        {"speaker": "妈妈", "line": "你们先说完"},
        {"speaker": "妈妈", "line": "我听着呢"},
    ]
    story = {
        "story_type": "N",
        "scene_title": "菜篓子旧事",
        "setting": "客厅，一家人聊起以前的事",
        "key": "菜篓子旧事",
        "conflict_core": "家里人重提昭昭小时候的旧事，昭昭嘴硬解释",
        "dialogue": dialogue,
        "punchline_explain": "N类童真歪理：昭昭一本正经为旧事找理由",
    }
    current = gc.dialogue_total_chars(story)
    assert current < 221
    story["dialogue"][-1]["line"] += "嗯" * (221 - current)
    assert gc.dialogue_total_chars(story) == 221

    row = {
        "payload": {
            "scene_contract": {
                "beat_chain": [
                    {"speaker": "妈妈", "intent": "重提旧事：说起昭昭小时候的意外"},
                    {"speaker": "昭昭", "intent": "质疑：那不是命大，是自己会挑地方落"},
                    {"speaker": "妈妈", "intent": "追问：地方又不是你摆的，怎么挑"},
                ]
            },
            "dialogue_seed": [
                {"speaker": "昭昭", "line": "哪是命大，我会挑地方落。"}
            ],
        }
    }

    def fail_if_llm_called(*args, **kwargs):
        raise AssertionError("221 字 N 稿不应进入 LLM 短稿 FIX")

    monkeypatch.setattr(gex, "_fix_chat_with_llm", fail_if_llm_called)
    out = gex._validate_expand_chat(
        story,
        banned_literals=[],
        source_type="field",
        mom_lines_max=3,
        structure_type="N",
        mechanism="M6",
        row=row,
    )

    assert gc.dialogue_total_chars(out) >= gc.DAILY_STORY_BODY_CHARS_MIN
    lines = [str(row.get("line") or "") for row in out["dialogue"]]
    assert any("照这个道理认真想" in line for line in lines)
    assert any("刚才就是这么认真回答" in line for line in lines)


def test_n_post_align_221_stabilizer_uses_contract_context():
    """post-align 清理压到 221 时也必须带契约收口，不能再次失忆后进入重生成。"""
    from app.services.gold_story.gold_chat.length import _stabilize_local_length_candidate

    def fit(text: str, size: int) -> str:
        core = text.rstrip("。")
        return (core + "真" * size)[: size - 1] + "。"

    dialogue = [
        {"speaker": "妈妈", "line": fit("又说起你小时候那件旧事", 15)},
        {"speaker": "昭昭", "line": fit("那不叫命大我就是会挑地方落", 20)},
        {"speaker": "妈妈", "line": fit("菜篓子不是你摆的你怎么挑", 15)},
        {"speaker": "昭昭", "line": fit("我看准软地方才往那边落", 20)},
        {"speaker": "灿灿", "line": fit("你说得还真像自己安排好的一样", 20)},
        {"speaker": "昭昭", "line": fit("我当时就是一点都没有慌", 20)},
        {"speaker": "灿灿", "line": fit("你醒来还先惦记着吃饭", 20)},
        {"speaker": "昭昭", "line": fit("醒了先吃饭也很正常", 20)},
        {"speaker": "妈妈", "line": fit("你这套道理还挺完整", 15)},
        {"speaker": "灿灿", "line": fit("我都快听得接不上话了", 20)},
        {"speaker": "昭昭", "line": fit("反正我觉得自己判断没错", 20)},
        {"speaker": "妈妈", "line": fit("行吧这话我真接不住了", 16)},
    ]
    story = {"story_type": "N", "dialogue": dialogue}
    assert gc.dialogue_total_chars(story) == 221
    beat_chain = [
        {"speaker": "妈妈", "intent": "重提旧事：说起昭昭小时候的意外"},
        {"speaker": "昭昭", "intent": "质疑：那不是命大，是自己会挑地方落"},
        {"speaker": "妈妈", "intent": "追问：地方又不是你摆的，怎么挑"},
    ]

    without_contract, _ = _stabilize_local_length_candidate(
        story, structure_type="N", mechanism="M6",
    )
    assert gc.dialogue_total_chars(without_contract) < gc.DAILY_STORY_BODY_CHARS_MIN

    closed, changed = _stabilize_local_length_candidate(
        story,
        structure_type="N",
        mechanism="M6",
        beat_chain=beat_chain,
    )
    assert changed
    assert gc.dialogue_total_chars(closed) >= gc.DAILY_STORY_BODY_CHARS_MIN
    assert len(closed["dialogue"]) == len(story["dialogue"]) + 2
    # 补位落在妈妈追问和昭昭已有回答之后，不能切断 beat2→beat3 的开口因果。
    assert closed["dialogue"][2]["speaker"] == "妈妈"
    assert closed["dialogue"][3]["speaker"] == "昭昭"
    assert closed["dialogue"][4]["speaker"] == "灿灿"
    assert "照这个道理认真想" in closed["dialogue"][4]["line"]


def test_n_natural_mid_pairs_skips_when_parent_qa_in_closing_tail():
    """契约要求落在家长追问之后，但 Q/A 已在末段时不得退回早先 reason_idx 插句。"""
    from app.services.gold_story.gold_chat.length import _n_natural_mid_pairs

    dialogue = [
        {"speaker": "妈妈", "line": "又说起你小时候那件旧事。"},
        {"speaker": "昭昭", "line": "那不叫命大，我会挑地方落。"},
        {"speaker": "灿灿", "line": "你每次都说得特别认真。"},
        {"speaker": "妈妈", "line": "菜篓子不是你摆的，你怎么挑？"},
        {"speaker": "昭昭", "line": "我看准软地方才往那边落。"},
        {"speaker": "妈妈", "line": "行吧，先吃饭。"},
    ]
    beat_chain = [
        {"speaker": "妈妈", "intent": "重提旧事：说起昭昭小时候的意外"},
        {"speaker": "昭昭", "intent": "质疑：那不是命大，是自己会挑地方落"},
        {"speaker": "妈妈", "intent": "追问：地方又不是你摆的，怎么挑"},
    ]
    pairs, insert_at = _n_natural_mid_pairs(dialogue, beat_chain=beat_chain)
    assert pairs == ()
    assert insert_at is None


def test_n_natural_mid_pairs_skips_insert_when_reason_in_closing_tail():
    from app.services.gold_story.gold_chat.length import _n_natural_mid_pairs

    dialogue = [
        {"speaker": "妈妈", "line": "又提起以前那件事。"},
        {"speaker": "灿灿", "line": "你怎么回事？"},
        {"speaker": "昭昭", "line": "我才不要听你指挥。"},
        {"speaker": "妈妈", "line": "那你讲清楚。"},
        {"speaker": "昭昭", "line": "因为我早就看好了位置。"},
        {"speaker": "妈妈", "line": "行吧，先吃饭。"},
    ]
    beat_chain = [
        {"speaker": "妈妈", "intent": "重提旧事"},
        {"speaker": "昭昭", "intent": "嘴硬：先顶一句"},
        {"speaker": "昭昭", "intent": "回答：给出荒诞理由"},
    ]
    pairs, insert_at = _n_natural_mid_pairs(dialogue, beat_chain=beat_chain)
    assert pairs == ()
    assert insert_at is None


def test_n_contract_length_fallback_rejects_ambiguous_reasoner():
    """两个孩子都被契约标成解释方时禁止猜角色，宁可交上层修稿。"""
    from app.services.gold_story.gold_chat.length import _n_natural_mid_pairs

    dialogue = [
        {"speaker": "妈妈", "line": "又提起以前那件事。"},
        {"speaker": "昭昭", "line": "我有我的说法。"},
        {"speaker": "妈妈", "line": "你继续说。"},
        {"speaker": "灿灿", "line": "我也有另一套说法。"},
    ]
    beat_chain = [
        {"speaker": "昭昭", "intent": "解释：认真说明自己的理由"},
        {"speaker": "灿灿", "intent": "解释：也给出自己的理由"},
    ]
    pairs, insert_at = _n_natural_mid_pairs(dialogue, beat_chain=beat_chain)
    assert pairs == ()
    assert insert_at is None


def test_shared_local_length_close_leaves_clean_shortage_for_repair():
    from app.services.gold_story.gold_chat.length import (
        _stabilize_local_length_candidate,
    )
    from app.services.gold_story.gold_chat.repair import (
        prepare_candidate_for_acceptance,
    )

    story = _sample_chat()
    story["dialogue"][0]["line"] = "你。"
    story["dialogue"][1]["line"] = "我。"
    assert gc.dialogue_total_chars(story) < gc.DAILY_STORY_BODY_CHARS_MIN

    closed, changed = _stabilize_local_length_candidate(
        story,
        structure_type="A",
        mechanism="M6",
    )
    assert changed
    prepared, errors = prepare_candidate_for_acceptance(
        closed,
        mom_lines_max=3,
        banned_literals=[],
    )

    assert gc.dialogue_total_chars(prepared) < gc.DAILY_STORY_BODY_CHARS_MIN
    assert any("正文总字数须≥" in error for error in errors)
    assert not [
        error
        for error in errors
        if "单句过长" in error or "垫字" in error
    ]
    body = "".join(str(row.get("line") or "") for row in prepared["dialogue"])
    assert "我偏就不信" not in body
    assert "说一不二" not in body


def test_n_post_sanitize_close_recovers_contract_without_dirty_fill():
    from app.services.daily_story.story_types.n.validate import RE_SOLEMN_REASON
    from app.services.gold_story.gold_chat import refine as grf
    from app.services.gold_story.gold_chat.repair import (
        prepare_candidate_for_acceptance_after_local_length_close,
    )

    story = _sample_chat()
    story["story_type"] = "N"
    story["dialogue"] = [
        {"speaker": "灿灿", "line": "如果只能选一个，你认真说选姐姐还是选我？"},
        {"speaker": "昭昭", "line": "我当然先选姐姐，这个答案不用想太久。"},
        {"speaker": "灿灿", "line": "为什么，你总得给我一个能听懂的理由吧？"},
        {"speaker": "昭昭", "line": "她笑起来像小太阳，我看见就觉得特别亮。"},
        {"speaker": "灿灿", "line": "你这个说法听着怎么越来越奇怪了？"},
        {"speaker": "昭昭", "line": "我是在认真回答你，没有故意逗你玩。"},
        {"speaker": "灿灿", "line": "那你继续说，我倒要看看还能怎么讲。"},
        {"speaker": "昭昭", "line": "我说完就是这个答案，不准备临时改口。"},
        {"speaker": "灿灿", "line": "行吧，我服了，你还真能一本正经讲下去。"},
        {"speaker": "昭昭", "line": "那就这么定，别再让我重新选一次。"},
        {"speaker": "灿灿", "line": "我听懂了。"},
        {"speaker": "昭昭", "line": "这回说清楚了。"},
    ]
    assert gc.dialogue_total_chars(story) < gc.DAILY_STORY_BODY_CHARS_MIN

    closed = grf._stabilize_n_contract_candidate(
        gex._normalize_chat_speakers(story),
        structure_type="N",
        mechanism="M6",
    )
    prepared, errors = prepare_candidate_for_acceptance_after_local_length_close(
        closed,
        mom_lines_max=3,
        banned_literals=[],
        structure_type="N",
        mechanism="M6",
    )
    body = "".join(str(x.get("line") or "") for x in prepared.get("dialogue") or [])

    assert gc.dialogue_total_chars(prepared) >= gc.DAILY_STORY_BODY_CHARS_MIN
    assert RE_SOLEMN_REASON.search(body)
    assert not [
        error
        for error in errors
        if "正文总字数须≥" in error or "单句过长" in error or "垫字" in error
    ]
    assert "我偏就不信" not in body
    assert "说一不二" not in body


def test_validate_gold_chat_rejects_banned():
    story = _sample_chat()
    story["dialogue"][0]["line"] = "小姨又欺负我"
    with pytest.raises(ValueError, match="禁词"):
        gc.validate_gold_chat(story, banned_literals=["小姨"])


def test_validate_gold_chat_rejects_relay_and_paren():
    story = _sample_chat()
    story["dialogue"][0]["line"] = "妈妈说了，抢不过就躲着点。"
    with pytest.raises(ValueError, match="转述"):
        gc.validate_gold_chat(story)
    story["dialogue"][0]["line"] = "（从厨房走出来）昭昭，你说啥？"
    with pytest.raises(ValueError, match="括号"):
        gc.validate_gold_chat(story)


def test_normalize_chat_speakers_keeps_father():
    story = _sample_chat()
    story["dialogue"][0]["speaker"] = "爸爸"
    out = gc._normalize_chat_speakers(story)
    assert out["dialogue"][0]["speaker"] == "爸爸"


def test_normalize_chat_speakers_father_alias_to_dad():
    story = _sample_chat()
    story["dialogue"][0]["speaker"] = "老爸"
    out = gc._normalize_chat_speakers(story)
    assert out["dialogue"][0]["speaker"] == "爸爸"


def test_gate_gold_chat_structure_score_raises_when_low():
    with pytest.raises(ValueError, match=r"structure_score:63"):
        gc._gate_gold_chat_structure_score(
            {"quality": {"structure_score": 63, "score": 63}}
        )


def test_gate_gold_chat_structure_score_ok():
    assert gc._gate_gold_chat_structure_score(
        {"quality": {"structure_score": 80, "score": 80}}
    ) == 80


def test_lift_structure_second_prompt_includes_previous_validation_error():
    """定点修稿第二轮须带上轮校验/门控错误，勿只重复结构分反馈。"""
    prompts: list[str] = []
    chat = _sample_chat()
    chat["quality"] = {
        "structure_score": 60,
        "score": 60,
        "reasons": ["无破功软收"],
    }
    row = _sample_row()

    def fake_fix(_chat: dict, fb: str, **_kwargs: object) -> dict:
        prompts.append(fb)
        out = dict(_chat)
        if len(prompts) == 1:
            raise ValueError("正文总字数须≥240")
        out["quality"] = {"structure_score": 80, "score": 80, "reasons": []}
        return out

    out, struct = gcf._lift_gold_chat_structure_with_llm(
        chat,
        row,
        st_final="N",
        mech="M6",
        banned=[],
        mom_max=1,
        attach_score=lambda c, _r: c,
        gate_score=lambda _c: 80,
        normalize_chat=lambda c: c,
        fix_llm=fake_fix,
        validate_chat=lambda _c: None,
        max_attempts=2,
    )
    assert struct == 80
    assert len(prompts) == 2
    assert "正文总字数须≥240" in prompts[1]
    assert "上一轮未过" in prompts[1]
    assert out["quality"]["structure_score"] == 80


def test_attach_gold_chat_structure_score_writes_quality():
    row = _sample_row()
    chat = _sample_chat()
    out = gc._attach_gold_chat_structure_score(chat, row)
    assert isinstance(out.get("quality"), dict)
    assert out["story_type"] == "A"
    assert "structure_score" in out["quality"]


def _bypass_structure_gate(monkeypatch):
    monkeypatch.setattr(
        gc,
        "_attach_gold_chat_structure_score",
        lambda chat, _row: {
            **chat,
            "quality": {"structure_score": 80, "score": 80, "summary": "结构80"},
        },
    )
    monkeypatch.setattr(gc, "_gate_gold_chat_structure_score", lambda _chat: 80)
    # 测试夹具对白过不了 A–L 契约机审；跳过精修对齐
    monkeypatch.setattr(gc, "refine_gold_chat_align", lambda story, **_kw: story)
    monkeypatch.setattr(grf, "refine_gold_chat_align", lambda story, **_kw: story)


def test_gold_story_to_gold_chat_retries_when_one_line_short(monkeypatch):
    """差 1 句：不本地硬插注水句；须 FIX 扩写或扩写重抽。"""
    import copy

    calls: dict[str, int | bool] = {"n": 0}
    _bypass_structure_gate(monkeypatch)

    def fake_chat(system: str, _user: str, **_kwargs) -> dict:
        if "编辑" in system or "定点" in system:
            calls["fix"] = True
            return _sample_chat()
        calls["n"] = int(calls["n"]) + 1
        chat = _sample_chat()
        if int(calls["n"]) == 1:
            chat["dialogue"] = chat["dialogue"][:11]
        return chat

    monkeypatch.setattr(gc, "_chat_json", fake_chat)
    monkeypatch.setattr(gex, "_chat_json", fake_chat)
    monkeypatch.setattr(gc, "EXPAND_CANDIDATE_COUNT", 1)
    monkeypatch.setattr(gex, "EXPAND_CANDIDATE_COUNT", 1)
    monkeypatch.setattr(gc, "EXPAND_REGENERATE_MAX", 5)
    monkeypatch.setattr(gex, "EXPAND_REGENERATE_MAX", 5)

    def spot_fix(chat, _fb, **_kw):
        calls["fix"] = True
        out = copy.deepcopy(chat)
        for _ in range(64):
            if gc.dialogue_total_chars(out) >= gc.DAILY_STORY_BODY_CHARS_MIN:
                break
            progressed = False
            rows = out.get("dialogue") or []
            for row in rows[1:-1]:
                if len(str(row.get("line") or "")) >= 22:
                    continue
                row["line"] = str(row.get("line") or "") + "补"
                progressed = True
                if gc.dialogue_total_chars(out) >= gc.DAILY_STORY_BODY_CHARS_MIN:
                    break
            if not progressed:
                break
        return out

    monkeypatch.setattr(gex, "_short_spot_fix_chat_with_llm", spot_fix)
    out = gc.gold_story_to_gold_chat(_sample_row())
    assert len(out["dialogue"]) >= 12
    blob = "".join(str(d.get("line") or "") for d in out["dialogue"])
    assert "你给我听好了" not in blob


def test_gold_story_to_gold_chat_rejects_when_far_too_short(monkeypatch):
    _bypass_structure_gate(monkeypatch)

    def fake_chat(_system: str, _user: str, **_kwargs) -> dict:
        bad = _sample_chat()
        bad["dialogue"] = bad["dialogue"][:2]
        return bad

    monkeypatch.setattr(gc, "_chat_json", fake_chat)
    monkeypatch.setattr(gex, "_chat_json", fake_chat)
    monkeypatch.setattr(gc, "EXPAND_CANDIDATE_COUNT", 1)
    monkeypatch.setattr(gex, "EXPAND_CANDIDATE_COUNT", 1)
    with pytest.raises(ValueError, match="篇幅驳回"):
        gc.gold_story_to_gold_chat(_sample_row())


def test_bump_short_regen_helpers():
    err11 = "对白句数须≥12，当前11; 正文总字数须≥240，当前155"
    assert gc._is_regenerable_line_short_error(err11)
    assert gc._bump_short_regen_or_reject(err11, 0) == 1
    assert gc._bump_short_regen_or_reject(err11, 2) == 3
    with pytest.raises(ValueError, match="重生成3次仍不达标"):
        gc._bump_short_regen_or_reject(err11, 3)
    err10 = "对白句数须≥12，当前10"
    assert gc._is_regenerable_line_short_error(err10)
    assert gc._bump_short_regen_or_reject(err10, 0) == 1
    err9 = "对白句数须≥12，当前9"
    assert gc._is_regenerable_line_short_error(err9)
    err8 = "对白句数须≥12，当前8"
    assert not gc._is_regenerable_line_short_error(err8)
    with pytest.raises(ValueError, match="本地垫字仍不足"):
        gc._bump_short_regen_or_reject(err8, 0)
    # 字数 near-miss / 大缺口均可重生成（勿立刻「本地垫字仍不足」）
    err_chars = "正文总字数须≥240，当前235"
    assert gc._char_deficit_from_error(err_chars) == 5
    assert gc._is_regenerable_short_error(err_chars)
    assert gc._bump_short_regen_or_reject(err_chars, 0) == 1
    err_short = "正文总字数须≥240，当前117"
    assert gc._is_regenerable_short_error(err_short)
    assert gc._bump_short_regen_or_reject(err_short, 0) == 1
    with pytest.raises(ValueError, match="重生成3次仍不达标"):
        gc._bump_short_regen_or_reject(err_chars, 3)


def test_attach_gold_chat_structure_score_skips_opening_penalty_for_body():
    """计分前清空 discovery_opening，避免前 2 句被当开场扣分。"""
    row = _sample_row()
    row["structure_type"] = "J"
    row["title"] = "世子之争"
    chat = {
        "scene_title": "世子之争",
        "setting": "地板垫上，灿灿和昭昭在抢垫子",
        "conflict_core": "昭昭先动手，灿灿一锤镇住",
        "punchline_explain": "J类权威压住：一锤肘击后镇住",
        "story_type": "J",
        "dialogue": [
            {"speaker": "昭昭", "line": "这垫子是我的地盘你走开！"},
            {"speaker": "灿灿", "line": "谁赢谁说了算玩具归我！"},
            {"speaker": "昭昭", "line": "拿出最强形态来打我！"},
            {"speaker": "灿灿", "line": "草莓熊肘击砸你肚子！"},
            {"speaker": "昭昭", "line": "啊我输了你太厉害啦！"},
            {"speaker": "灿灿", "line": "以后玩具都归我安排！"},
            {"speaker": "昭昭", "line": "哼等我长大再跟你算！"},
            {"speaker": "灿灿", "line": "这局我已经镇住你了！"},
            {"speaker": "昭昭", "line": "再求你一次松口行不行！"},
            {"speaker": "灿灿", "line": "不行规矩就是这样定的！"},
            {"speaker": "昭昭", "line": "那我保证这次听你的话！"},
            {"speaker": "灿灿", "line": "保证也没用现在听我的！"},
        ],
    }
    out = gc._attach_gold_chat_structure_score(chat, row)
    reasons = " ".join(str(r) for r in (out.get("quality") or {}).get("reasons") or [])
    assert "开场未满" not in reasons
    assert "J开场缺求放行" not in reasons
    assert "缺发现开场" not in reasons
    score = int((out.get("quality") or {}).get("structure_score") or 0)
    assert score >= 75, (score, reasons)


def test_gold_chat_structure_score_skips_bili_title_relevancy():
    """gold_chat 结构分不按 B 站标题字面跑题（保真走 beat/契约）。"""
    row = _sample_row()
    row["title"] = "世子之争"
    chat = _sample_chat()
    chat["scene_title"] = "垫子争夺战"
    chat["story_type"] = "J"
    chat["dialogue"] = [
        {"speaker": "昭昭", "line": "这沙发我先占好了，你挪开！"},
        {"speaker": "灿灿", "line": "不行，我先来的，该你走！"},
    ] * 6
    out = gc._attach_gold_chat_structure_score(chat, row)
    reasons = " ".join(str(r) for r in (out.get("quality") or {}).get("reasons") or [])
    assert "跑题" not in reasons


def test_validate_expand_expands_short_with_fix_before_regen(monkeypatch):
    """偏短时先 FIX 句内扩写，勿立刻整稿重生成。"""
    calls = {"fix": 0}

    short = _sample_chat()
    short["story_type"] = "J"
    short["dialogue"] = [
        {"speaker": "昭昭", "line": "看招！"},
        {"speaker": "灿灿", "line": "你敢！"},
    ] * 6
    assert gc.dialogue_total_chars(short) < gc.DAILY_STORY_BODY_CHARS_MIN

    def fake_fix(story, errors, **_kw):
        calls["fix"] += 1
        assert "正文总字数须≥" in errors
        return _sample_chat()

    monkeypatch.setattr(gc, "_fix_chat_with_llm", fake_fix)
    monkeypatch.setattr(gex, "_fix_chat_with_llm", fake_fix)
    monkeypatch.setattr(gc, "_ensure_gold_chat_min_chars", lambda s, **kw: (s, False))
    import app.services.gold_story.gold_chat.length as glength
    monkeypatch.setattr(glength, "_ensure_gold_chat_min_chars", lambda s, **kw: (s, False))
    monkeypatch.setattr(gex, "_ensure_gold_chat_min_chars", lambda s, **kw: (s, False))
    out = gc._validate_expand_chat(
        short,
        banned_literals=[],
        source_type="field",
        mom_lines_max=0,
        structure_type="J",
    )
    assert calls["fix"] == 1
    assert len(out["dialogue"]) >= 12


def test_apply_deterministic_shorten_trims_one_char():
    story = _sample_chat()
    story["dialogue"][0]["line"] = "你刚才又抢我遥控器，我还不敢说呀！"
    assert len(story["dialogue"][0]["line"]) == 17  # sanity
    long_line = "你" * 24 + "呀"
    assert len(long_line) == 25
    story["dialogue"][0]["line"] = long_line
    out, changed = gc._apply_deterministic_shorten(story)
    assert changed
    assert len(out["dialogue"][0]["line"]) <= gc.CHAT_MAX_LINE_CHARS


def test_shorten_overlong_llm_freezes_non_target_lines_and_speakers(monkeypatch):
    story = _sample_chat()
    story["dialogue"][0]["line"] = "这是一句完全没有语气词可以机械裁掉的超长对白内容测试甲乙丙丁"
    original_second = dict(story["dialogue"][1])
    assert len(story["dialogue"][0]["line"]) > gc.CHAT_MAX_LINE_CHARS

    def fake_chat(*_a, **_k):
        out = {**story, "dialogue": [dict(x) for x in story["dialogue"]]}
        out["dialogue"][0]["line"] = "这句只保留必要语义"
        out["dialogue"][0]["speaker"] = story["dialogue"][0]["speaker"]
        out["dialogue"][1]["line"] = "模型顺手改坏了非目标行"
        out["dialogue"][1]["speaker"] = "妈妈"
        return out

    monkeypatch.setattr(gex, "_chat_json", fake_chat)
    out = gex._shorten_overlong_lines_with_llm(story)
    assert out["dialogue"][0]["line"] == "这句只保留必要语义"
    assert out["dialogue"][0]["speaker"] == story["dialogue"][0]["speaker"]
    assert out["dialogue"][1] == original_second


def test_validate_expand_shortens_before_full_fix(monkeypatch):
    calls: list[str] = []

    def fake_validate(story, **kwargs):
        for item in story.get("dialogue") or []:
            if len(str(item.get("line") or "")) > gc.CHAT_MAX_LINE_CHARS:
                raise ValueError(
                    f"单句过长(max=31>{gc.CHAT_MAX_LINE_CHARS})"
                )
        return None

    def fake_shorten(story, **_kw):
        calls.append("shorten")
        out = dict(story)
        rows = [dict(x) for x in out["dialogue"]]
        rows[0]["line"] = str(rows[0]["line"])[: gc.CHAT_MAX_LINE_CHARS]
        out["dialogue"] = rows
        return out

    monkeypatch.setattr(gc, "validate_gold_chat", fake_validate)
    monkeypatch.setattr(gc, "_shorten_overlong_lines_with_llm", fake_shorten)
    monkeypatch.setattr(gex, "_shorten_overlong_lines_with_llm", fake_shorten)

    def _boom(*_a, **_k):
        raise AssertionError("should not full fix")

    monkeypatch.setattr(gc, "_fix_chat_with_llm", _boom)
    monkeypatch.setattr(gex, "_fix_chat_with_llm", _boom)
    story = _sample_chat()
    story["dialogue"][0]["line"] = "你" * 31
    out = gc._validate_expand_chat(
        story,
        banned_literals=[],
        source_type="field",
        mom_lines_max=1,
    )
    assert calls == ["shorten"]
    assert len(out["dialogue"][0]["line"]) <= gc.CHAT_MAX_LINE_CHARS


def test_gold_story_to_gold_chat(monkeypatch):
    _bypass_structure_gate(monkeypatch)

    def fake_chat(_system: str, _user: str, **_kwargs) -> dict:
        return _sample_chat()

    monkeypatch.setattr(gc, "_chat_json", fake_chat)
    monkeypatch.setattr(gex, "_chat_json", fake_chat)
    out = gc.gold_story_to_gold_chat(_sample_row())
    assert out["scene_title"] == "关门练功"
    assert len(out["dialogue"]) >= 4
    assert out["quality"]["structure_score"] == 80


def test_convert_failure_preserves_existing_export(tmp_path, monkeypatch):
    from app.services.gold_story.gold_chat.finalize import GoldChatAcceptanceBlocked

    sid = "BV1KEEPEXPORT"
    export_dir = tmp_path / "gold_chat"
    export_dir.mkdir(parents=True)
    json_path = export_dir / f"{sid}.json"
    original = '{"keep": true}'
    json_path.write_text(original, encoding="utf-8")

    row = _sample_row()
    row["source_id"] = sid
    row["id"] = 96

    monkeypatch.setattr(gc, "gold_chat_export_dir", lambda _cfg=None: export_dir)
    monkeypatch.setattr(gce, "gold_chat_export_dir", lambda _cfg=None: export_dir)
    _bypass_structure_gate(monkeypatch)
    monkeypatch.setattr(
        gc,
        "gold_story_to_gold_chat",
        lambda _r, **kw: _sample_chat(),
    )
    monkeypatch.setattr(
        gc,
        "apply_gold_chat_normalizations",
        lambda chat, **_kw: (chat, []),
    )
    monkeypatch.setattr(
        gc,
        "_refine_after_normalize",
        lambda chat, _row, **_kw: chat,
    )
    monkeypatch.setattr(gc, "_rebuild_h3a_h3b_on_convert", lambda r: r)
    monkeypatch.setattr(gc, "_persist_structure_correction", lambda r, _n: r)
    monkeypatch.setattr(gc, "_resolve_structure_row", lambda r: (r, []))
    monkeypatch.setattr(gc, "_persist_m5_h_contract_if_needed", lambda r: r)

    def _fail_finalize(*_args, **_kwargs):
        raise GoldChatAcceptanceBlocked("终检语义硬伤：第[2]句·错位：测试")

    monkeypatch.setattr(gcf, "run_gold_chat_finalize", _fail_finalize)

    with pytest.raises(GoldChatAcceptanceBlocked) as exc_info:
        gc.convert_gold_chat(row)

    assert json_path.read_text(encoding="utf-8") == original
    timing = getattr(exc_info.value, "gold_chat_timing", None)
    assert isinstance(timing, dict)
    assert timing["status"] == "failed"
    assert timing["stage"] == "finalize"
    assert set(timing["stages_ms"]) == {"contract", "draft", "normalize_refine", "finalize"}
    assert "export_backfill" not in timing["stages_ms"]


def test_rebuild_h3a_h3b_on_convert_refreshes_contract(monkeypatch):
    """重转切入点：用 story_raw+H3 重跑 H3a/H3b 写回契约。"""
    patched: dict = {}
    cores: list[str] = []

    def fake_build_scene(**_kwargs):
        return {
            "story_type": "I",
            "location": "客厅",
            "characters": ["灿灿", "昭昭", "妈妈"],
            "object": "小学单科成绩单",
            "conflict": "昭昭宣扬灿灿考了低分，妈妈责备戳痛处",
            "mechanism": "宣传高分该谢、低分怪分数",
            "beat_chain": [
                {"beat": 1, "speaker": "灿灿", "intent": "责备宣传"},
                {"beat": 2, "speaker": "昭昭", "intent": "双标辩解"},
                {"beat": 3, "speaker": "妈妈", "intent": "冰箱反问"},
                {"beat": 4, "speaker": "昭昭", "intent": "嘴硬"},
            ],
            "closing_intent": "昭昭嘴硬",
            "mom_lines_max": 2,
            "remap_note": "戏核家长须保留出场",
            "banned_literals": [],
            "contract_confidence": 0.9,
        }

    def fake_build_seed(**_kwargs):
        return {
            "setting": "客厅，灿灿攥着成绩单",
            "dialogue_seed": [
                {"speaker": "灿灿", "intent": "责备宣传低分"},
                {"speaker": "昭昭", "intent": "双标辩解"},
                {"speaker": "妈妈", "intent": "冰箱反问"},
                {"speaker": "昭昭", "intent": "嘴硬"},
            ],
            "closing_intent": "昭昭嘴硬",
            "speaker_map_note": "妈妈保留",
            "dialogue_confidence": 0.9,
        }

    monkeypatch.setattr(
        "app.services.gold_story.collect.llm.build_scene_contract",
        fake_build_scene,
    )
    monkeypatch.setattr(
        "app.services.gold_story.collect.llm.build_dialogue_seed",
        fake_build_seed,
    )
    monkeypatch.setattr(
        gc.repo_gold_story,
        "patch_story_payload",
        lambda gid, patch: patched.update({"gid": gid, **patch}),
    )
    monkeypatch.setattr(
        gc.repo_gold_story,
        "update_conflict_core",
        lambda gid, core: cores.append(core),
    )

    row = {
        "id": 44,
        "title": "分数宣传",
        "mechanism": "M11",
        "structure_type": "I",
        "conflict_core": "站外旧核：高考高分口吻残留",
        "theme_family": "分数",
        "payload": {
            "story_raw": "姐姐考了差分化妹妹宣传，妈妈责备并用冰箱反问。" * 3,
            "beat": [
                "妹妹宣扬，妈妈责备",
                "妹妹辩称双标",
                "妈妈反问冰箱",
                "妈妈点出开好头",
            ],
            "scene_contract": {
                "characters": ["灿灿", "昭昭"],
                "mom_lines_max": 0,
                "object": "站外旧分数口吻",
            },
            "source_type": "field",
            "structure_confidence": 0.8,
        },
    }
    out = gc._rebuild_h3a_h3b_on_convert(row)
    sc = out["payload"]["scene_contract"]
    assert "妈妈" in sc["characters"]
    assert int(sc["mom_lines_max"]) >= 2
    assert "高考" not in str(out.get("conflict_core") or "")
    assert "低分" in str(out.get("conflict_core") or "")
    assert cores and "低分" in cores[0]
    assert any(
        isinstance(r, dict) and r.get("speaker") == "妈妈"
        for r in out["payload"]["dialogue_seed"]
    )
    assert patched.get("gid") == 44


def test_sanitize_pad_suffix_strips_compound_tails():
    story = {
        "dialogue": [
            {
                "speaker": "昭昭",
                "line": "那跟我有啥关系不行了吧真的了呢。",
            },
            {
                "speaker": "灿灿",
                "line": "你别再宣传了真的了呢",
            },
            {
                "speaker": "妈妈",
                "line": "评论冰箱还得会制冷吗？",
            },
        ]
    }
    out, changed = gc.patch_sanitize_pad_suffix(story)
    assert changed
    lines = [str(x["line"]) for x in out["dialogue"]]
    assert "真的了呢" not in lines[0]
    assert "不行了吧" not in lines[0]
    assert "真的了呢" not in lines[1]
    assert "冰箱" in lines[2]


def test_sanitize_pad_suffix_strips_glued_buxing():
    """粘连垫字「知道不行/关系不行」应剥；真拒绝「还不行」保留。"""
    story = {
        "dialogue": [
            {"speaker": "昭昭", "line": "姐数学58分，全班都知道不行！"},
            {
                "speaker": "昭昭",
                "line": "跟我没关系不行，我才不怕呢。",
            },
            {"speaker": "灿灿", "line": "这样还不行！"},
        ]
    }
    out, changed = gc.patch_sanitize_pad_suffix(story)
    assert changed
    lines = [str(x["line"]) for x in out["dialogue"]]
    assert "知道不行" not in lines[0]
    assert "都知道" in lines[0]
    assert "关系不行" not in lines[1]
    assert "没关系" in lines[1]
    assert lines[2] == "这样还不行！"


def test_parse_conflict_propaganda_roles():
    from app.services.gold_story.gold_chat.validate import (
        _parse_conflict_propaganda_roles,
    )

    roles = _parse_conflict_propaganda_roles(
        "昭昭到处说姐姐考了58分，妈妈责备昭昭戳姐姐痛处"
    )
    assert roles == ("昭昭", "灿灿")


def test_patch_score_propaganda_speakers_realigns():
    story = {
        "conflict_core": "昭昭到处说灿灿考了58分",
        "dialogue": [
            {"speaker": "昭昭", "line": "她考高分我宣传，她得谢我。"},
            {"speaker": "昭昭", "line": "你到处说，我同学都笑我。"},
            {"speaker": "灿灿", "line": "我宣传高分你谢我，宣传低分你怪我。"},
            {"speaker": "灿灿", "line": "低分被怪是分数问题，怪我咯。"},
        ],
    }
    out, changed = gc.patch_score_propaganda_speakers(
        story, conflict_text=story["conflict_core"]
    )
    assert changed
    assert out["dialogue"][1]["speaker"] == "灿灿"
    assert out["dialogue"][2]["speaker"] == "昭昭"
    assert out["dialogue"][3]["speaker"] == "昭昭"


def test_patch_collapse_empty_sibling_repeats():
    story = {
        "dialogue": [
            {"speaker": "灿灿", "line": "别说了！"},
            {"speaker": "灿灿", "line": "别说了！"},
            {"speaker": "灿灿", "line": "别说了！"},
        ]
    }
    out, changed = gc.patch_collapse_empty_sibling_repeats(story)
    assert changed
    assert out["dialogue"][0]["line"] == "别说了！"
    assert out["dialogue"][1]["line"] != "别说了！"


def test_format_role_binding_block_propaganda():
    from app.services.gold_story.gold_chat.prompts import format_role_binding_block

    block = format_role_binding_block(
        "昭昭到处说姐姐考了58分，妈妈责备昭昭戳姐姐痛处"
    )
    assert "宣传方 = 昭昭" in block
    assert "受害方 = 灿灿" in block


def test_export_gold_chat_files(tmp_path, monkeypatch):
    monkeypatch.setattr(gc, "gold_chat_export_dir", lambda _cfg=None: tmp_path)
    monkeypatch.setattr(gce, "gold_chat_export_dir", lambda _cfg=None: tmp_path)
    row = _sample_row()
    chat = _sample_chat()
    paths = gc.export_gold_chat_files(
        source_id=row["source_id"],
        row=row,
        chat=chat,
    )
    assert Path(paths["json"]).is_file()
    assert Path(paths["markdown"]).is_file()
    payload = json.loads(Path(paths["json"]).read_text(encoding="utf-8"))
    assert payload["daily_story"]["scene_title"] == "关门练功"


def test_gold_chat_summary_from_payload():
    summary = gc.gold_chat_summary(
        "BV1TEST0001",
        row={
            "source_id": "BV1TEST0001",
            "payload": {
                "gold_chat_exported_at": "2026-08-24T00:00:00+00:00",
                "gold_chat_scene_title": "嘴硬心软",
                "gold_chat_lines": 18,
                "gold_chat_chars": 260,
                "gold_chat_structure_score": 82,
                "gold_chat_humor_score": 14,
                "bili_title": "东北弟弟打架被姐姐骂",
            },
        },
    )
    assert summary["has_gold_chat"] is True
    assert summary["scene_title"] == "嘴硬心软"
    assert summary["chat_lines"] == 18
    assert summary["bili_title"] == "东北弟弟打架被姐姐骂"
    assert summary["structure_score"] == 82
    assert summary["humor_score"] == 14


def test_import_gold_chat_daily_story_insert_and_reimport(
    app_ctx, tmp_path, monkeypatch,
):
    from app.repositories import repo_daily_story, repo_gold_story

    with app_ctx.app_context():
        inserted = repo_gold_story.insert_or_skip(
            source="bilibili",
            source_id="BV1TESTIMPORT01",
            url="https://www.bilibili.com/video/BV1TESTIMPORT01",
            mechanism="M6",
            structure_type="A",
            story_raw="导入测试专用故事" * 20,
            payload={
                "setting": "卧室门口",
                "beat": ["被欺负", "关门幻想", "开门怂", "姐姐得意"],
                "dialogue_seed": [
                    {"speaker": "昭昭", "intent": "抱怨被欺负"},
                    {"speaker": "灿灿", "intent": "得意威胁"},
                ],
                "closing_intent": "昭昭缩回角落",
                "banned_literals": ["小姨", "萌娃"],
                "funny_why": "幻想与怂的反差",
            },
            title="测试标题",
            conflict_core="弟弟幻想报复姐姐，开门秒怂",
            extract_confidence=0.8,
            structure_confidence=0.8,
            dialogue_confidence=0.8,
            auto_score=0.9,
            status="active",
        )
        assert inserted.get("action") == "insert"
        row = repo_gold_story.get_story(int(inserted["id"]))
        row["payload"]["scene_contract"] = {"mom_lines_max": 0}

    chat = _sample_chat()
    monkeypatch.setattr(gc, "gold_chat_export_dir", lambda _cfg=None: tmp_path)
    monkeypatch.setattr(gce, "gold_chat_export_dir", lambda _cfg=None: tmp_path)
    gc.export_gold_chat_files(source_id=row["source_id"], row=row, chat=chat)
    captured_mom_max: list[int | None] = []
    original_validate = gc.validate_gold_chat

    def capture_validate(story, **kwargs):
        captured_mom_max.append(kwargs.get("mom_lines_max"))
        return original_validate(
            story,
            **{**kwargs, "mom_lines_max": 1},
        )

    monkeypatch.setattr(gc, "validate_gold_chat", capture_validate)

    with app_ctx.app_context():
        out = gc.import_gold_chat_daily_story(row, review=False)
        assert out["action"] == "insert"
        assert captured_mom_max[0] == 0
        assert out["status"] == "review_pending"
        assert any("需重新终验" in reason for reason in out["production_reasons"])
        ds_id = int(out["daily_story_id"])
        saved = repo_daily_story.get_story(ds_id)
        assert saved["story"]["scene_title"] == "关门练功"
        assert saved["status"] == "review_pending"
        assert saved["story"]["dialogue"] == chat["dialogue"]
        assert "需重新终验" in "；".join(
            saved["story"].get("quality", {}).get("production_reasons", [])
        )

        row["gold_chat_daily_story_id"] = ds_id
        skip = gc.import_gold_chat_daily_story(row, review=False)
        assert skip["action"] == "skip"
        assert skip["status"] == "review_pending"
        assert any("需重新终验" in reason for reason in skip["production_reasons"])

        chat2 = dict(chat)
        chat2["scene_title"] = "新标题"
        gc.export_gold_chat_files(source_id=row["source_id"], row=row, chat=chat2)
        updated = gc.import_gold_chat_daily_story(row, force=True, review=False)
        assert updated["action"] == "update"
        assert updated["status"] == "review_pending"
        assert updated["production_reasons"]
        saved2 = repo_daily_story.get_story(ds_id)
        assert saved2["story"]["scene_title"] == "新标题"


def test_import_keeps_exported_final_quality(app_ctx, tmp_path, monkeypatch):
    from app.repositories import repo_daily_story, repo_gold_story
    from app.services.llm import llm_mgr as llm_mgr_mod

    with app_ctx.app_context():
        inserted = repo_gold_story.insert_or_skip(
            source="bilibili",
            source_id="BV1TESTIMPORT02",
            url="https://www.bilibili.com/video/BV1TESTIMPORT02",
            mechanism="M6",
            structure_type="A",
            story_raw="终分导入测试" * 20,
            payload={
                "setting": "卧室门口",
                "beat": ["被欺负", "关门幻想", "开门怂", "姐姐得意"],
                "scene_contract": {"mom_lines_max": 1},
            },
            title="测试标题",
            conflict_core="弟弟幻想报复姐姐，开门秒怂",
            extract_confidence=0.8,
            structure_confidence=0.8,
            dialogue_confidence=0.8,
            auto_score=0.9,
            status="active",
        )
        row = repo_gold_story.get_story(int(inserted["id"]))

    chat = _sample_chat()
    dialogue = [dict(item) for item in chat["dialogue"]]
    chat["quality"] = {
        "score": 91,
        "structure_score": 80,
        "grade": "好",
        "pass": True,
        "humor": {
            "funny_score": 11,
            "best_moment": "开门就怂",
            "humor_type": "natural",
        },
        "summary": "结构80，好笑11，总分91",
        "reasons": ["总分91=结构80+LLM好笑11"],
    }
    chat["story_type"] = "A"
    from app.services.daily_story.quality import (
        gold_story_review_contract,
        stamp_story_review_binding,
    )
    stamp_story_review_binding(
        chat,
        semantic_pass=True,
        review_contract=gold_story_review_contract(row, chat),
    )
    monkeypatch.setattr(gc, "gold_chat_export_dir", lambda _cfg=None: tmp_path)
    monkeypatch.setattr(gce, "gold_chat_export_dir", lambda _cfg=None: tmp_path)
    gc.export_gold_chat_files(source_id=row["source_id"], row=row, chat=chat)

    def _forbid_renorm(*_args, **_kwargs):
        raise AssertionError("终分稿不应再归一化")

    def _forbid_review(*_args, **_kwargs):
        raise AssertionError("终分稿不应再审读")

    monkeypatch.setattr(gc, "apply_gold_chat_normalizations", _forbid_renorm)
    monkeypatch.setattr(llm_mgr_mod, "_get_client", _forbid_review)

    with app_ctx.app_context():
        out = gc.import_gold_chat_daily_story(row, review=True)
        assert out["action"] == "insert"
        assert out["status"] == "active"
        assert out["production_reasons"] == []
        saved = repo_daily_story.get_story(int(out["daily_story_id"]))

    quality = saved["story"]["quality"]
    assert quality["score"] == 91
    assert quality["structure_score"] == 80
    assert quality["humor"]["funny_score"] == 11
    assert saved["story"]["dialogue"] == dialogue
    assert saved["status"] == "active"


def test_real_final_acceptance_export_import_stays_active(
    app_ctx, tmp_path, monkeypatch,
):
    """真实终验入口绑定最终正文后，导出再导入必须原样保持 active。"""
    from app.repositories import repo_daily_story, repo_gold_story
    from app.services.daily_story.review import ExportSemanticReviewResult

    with app_ctx.app_context():
        inserted = repo_gold_story.insert_or_skip(
            source="bilibili",
            source_id="BV1TESTIMPORT03",
            url="https://www.bilibili.com/video/BV1TESTIMPORT03",
            mechanism="M6",
            structure_type="A",
            story_raw="真实终验导入链路" * 20,
            payload={
                "setting": "卧室门口",
                "dialogue_seed": [
                    {"speaker": "昭昭", "intent": "抱怨被欺负"},
                    {"speaker": "灿灿", "intent": "得意威胁"},
                ],
                "closing_intent": "昭昭嘴硬收场",
                "scene_contract": {"mom_lines_max": 1},
            },
            title="真实终验导入链路",
            conflict_core="弟弟幻想报复姐姐，开门秒怂",
            extract_confidence=0.8,
            structure_confidence=0.8,
            dialogue_confidence=0.8,
            auto_score=0.9,
            status="active",
        )
        row = repo_gold_story.get_story(int(inserted["id"]))

    chat = _sample_chat()
    chat["dialogue"][-4:] = [
        {"speaker": "昭昭", "line": "我先把门开一条缝看看，你别突然冲进来呀。"},
        {"speaker": "灿灿", "line": "你开呀，我就在门口站着，看看你练成什么了。"},
        {"speaker": "昭昭", "line": "等等，我鞋带还没系好，高手出门也得先系鞋带。"},
        {"speaker": "灿灿", "line": "你刚才练的不会就是系鞋带功夫吧，笑死我了。"},
    ]
    chat["story_type"] = "A"
    chat["quality"] = {
        "structure_score": 80,
        "score": 80,
        "grade": "好",
        "summary": "结构80",
        "reasons": [],
    }
    semantic_result = ExportSemanticReviewResult(
        completed=True,
        issues=[],
        humor={
            "funny_score": 11,
            "best_moment": "开门秒怂",
            "humor_type": "situational",
        },
        error=None,
    )
    monkeypatch.setattr(
        "app.services.daily_story.review.run_export_semantic_review",
        lambda *_args, **_kwargs: semantic_result,
    )

    accepted = gcf.run_gold_chat_final_acceptance(
        chat,
        row,
        sid=str(row["source_id"]),
    )
    assert accepted["quality"]["semantic_pass"] is True
    assert accepted["quality"]["reviewed_content_hash"]
    assert accepted["quality"]["humor"]["funny_score"] == 11

    monkeypatch.setattr(gc, "gold_chat_export_dir", lambda _cfg=None: tmp_path)
    monkeypatch.setattr(gce, "gold_chat_export_dir", lambda _cfg=None: tmp_path)
    gc.export_gold_chat_files(
        source_id=str(row["source_id"]),
        row=row,
        chat=accepted,
    )

    with app_ctx.app_context():
        out = gc.import_gold_chat_daily_story(row, review=True)
        saved = repo_daily_story.get_story(int(out["daily_story_id"]))

    assert out["status"] == "active"
    assert out["production_reasons"] == []
    assert saved["status"] == "active"
    assert saved["story"]["dialogue"] == accepted["dialogue"]
    assert (
        saved["story"]["quality"]["reviewed_content_hash"]
        == accepted["quality"]["reviewed_content_hash"]
    )


def test_resolve_gold_chat_snippet_same_source():
    from app.services.gold_story.collect.llm import (
        GOLD_CHAT_LINES_SNIPPET,
        GOLD_CHAT_LINES_SNIPPET_SOURCE_ID,
        resolve_gold_chat_snippet,
    )

    note = resolve_gold_chat_snippet(GOLD_CHAT_LINES_SNIPPET_SOURCE_ID)
    assert "不注入全文正例" in note
    assert "未满 240" in note
    assert "18–24" not in note
    assert GOLD_CHAT_LINES_SNIPPET not in note


def test_format_dialogue_seed_marks_spoken_lines():
    text = gc._format_dialogue_seed(
        [
            {"speaker": "灿灿", "intent": "零食归我，作业本归你，公平吧？"},
            {"speaker": "昭昭", "intent": "立规反杀"},
        ]
    )
    assert "要点" in text
    assert "勿逐字照抄" in text
    assert "intent：立规反杀" in text


def test_closing_for_prompt_shortens_long():
    long = (
        "灿灿求饶但嘴硬收场：昭昭用灿灿自己立的规矩"
        "「零食归我，作业本归你」堵住，灿灿语塞，答应归还零食，末句嘴硬约下次"
    )
    out = gc._closing_for_prompt(long)
    assert len(out) < len(long)
    assert "灿灿求饶但嘴硬收场" in out


def test_expand_regen_feedback_includes_short_error():
    from app.services.gold_story.gold_chat.prompts import (
        format_expand_regen_feedback,
    )

    fb = format_expand_regen_feedback(
        "正文总字数须≥240，当前214",
        None,
        structure_type="C",
        mechanism="M2",
    )
    assert "未满" in fb or "≥240" in fb
    assert "214" in fb or "错误" in fb


def test_gold_chat_scenario_rules_are_contract_scoped():
    from app.services.gold_story.gold_chat.prompts import (
        format_scenario_rules_block,
    )

    unrelated = format_scenario_rules_block(
        mechanism="M9",
        structure_type="N",
        conflict_text="昭昭提出荒诞问题，灿灿认真回答",
        closing_intent="昭昭被答案噎住",
    )
    assert "互毁" not in unrelated
    assert "上药" not in unrelated

    mediation = format_scenario_rules_block(
        mechanism="M5",
        structure_type="H",
        conflict_text="灿灿先弄坏昭昭的画，双方互毁后妈妈调解",
        closing_intent="妈妈涂药后收束",
    )
    assert "本场互毁" in mediation
    assert "本场调解" in mediation
    assert "本场上药" in mediation

    # 「不和好」不得因含子串「和好」而注入调解
    denied = format_scenario_rules_block(
        mechanism="M8",
        structure_type="J",
        conflict_text="昭昭先动手抢垫子",
        closing_intent="灿灿压住，昭昭怂退，不和好，妈妈不出场",
    )
    assert "本场调解" not in denied
    assert "定责" not in denied

    # 中段拒和 + 结尾要求和好 → 仍注入和好/调解
    mid_refuse = format_scenario_rules_block(
        mechanism="M5",
        structure_type="H",
        conflict_text="灿灿拒绝和好，说不和好，冲突升级",
        closing_intent="妈妈调解后姐弟拉手和好",
    )
    assert "本场调解" in mid_refuse or "本场和好" in mid_refuse


def test_gold_chat_align_refine_prompts_are_type_scoped():
    from app.services.gold_story.gold_chat.prompts import (
        format_align_refine_system,
        format_align_refine_user,
    )

    sys_j = format_align_refine_system(mechanism="M8", structure_type="J")
    user_j = format_align_refine_user(
        issues_block="（无）",
        align_block="checklist",
        story_json="{}",
        chars_min=240,
        chars_max=370,
        banned_literals="（无）",
        mom_lines_max=1,
        max_line=24,
        mechanism="M8",
        structure_type="J",
        closing_intent="灿灿压住，昭昭怂退",
    )
    j_all = sys_j + user_j
    assert "保真-互毁" not in j_all
    assert "保真-和好" not in j_all
    assert "保真-M5" not in j_all
    assert "不打了" not in j_all
    assert "拉手" not in j_all
    assert "不得减少正文总字数" not in j_all
    assert "改短" in j_all or "改短或扩写" in j_all
    assert "≥240" in user_j or "≥{chars_min}" not in user_j

    # 否定契约：不和好 + 妈妈不出场 → 禁止和好/定责
    deny_closing = "灿灿压住，昭昭怂退，不和好，妈妈不出场"
    sys_deny = format_align_refine_system(
        mechanism="M8",
        structure_type="J",
        closing_intent=deny_closing,
    )
    user_deny = format_align_refine_user(
        issues_block="（无）",
        align_block="checklist",
        story_json="{}",
        chars_min=240,
        chars_max=370,
        banned_literals="（无）",
        mom_lines_max=1,
        max_line=24,
        mechanism="M8",
        structure_type="J",
        closing_intent=deny_closing,
    )
    deny_all = sys_deny + user_deny
    assert "保真-和好" not in deny_all
    assert "保真-H定责" not in deny_all
    assert "妈妈分层定责" not in deny_all

    # 中段「不和好」不得覆盖结尾和好要求
    mid_refuse_closing = "妈妈调解后姐弟拉手和好"
    mid_refuse_conflict = "灿灿拒绝和好，说不和好，冲突升级"
    user_mid = format_align_refine_user(
        issues_block="（无）",
        align_block="checklist",
        story_json="{}",
        chars_min=240,
        chars_max=370,
        banned_literals="（无）",
        mom_lines_max=1,
        max_line=24,
        mechanism="M5",
        structure_type="H",
        closing_intent=mid_refuse_closing,
        conflict_text=mid_refuse_conflict,
    )
    assert "保真-和好" in user_mid
    assert "保真-H定责" in user_mid

    sys_h = format_align_refine_system(
        mechanism="M5",
        structure_type="H",
        closing_intent="灿灿问还打不打架，拉手和好",
        conflict_text="互毁后妈妈调解",
    )
    user_h = format_align_refine_user(
        issues_block="（无）",
        align_block="checklist",
        story_json="{}",
        chars_min=240,
        chars_max=370,
        banned_literals="（无）",
        mom_lines_max=1,
        max_line=24,
        mechanism="M5",
        structure_type="H",
        closing_intent="灿灿问还打不打架，拉手和好",
        conflict_text="互毁后妈妈调解",
    )
    h_all = sys_h + user_h
    assert "M5 立规" in sys_h
    assert "保真-互毁" in user_h
    assert "保真-和好" in user_h
    assert "拉手" in h_all


def test_is_truncation_error():
    assert gc._is_truncation_error(
        "LLM output truncated (finish_reason=length)；对白 JSON 须短小"
    )
    assert not gc._is_truncation_error("正文总字数须≥240，当前214")


def test_resolve_gold_chat_snippet_cross_source():
    from app.services.gold_story.collect.llm import (
        GOLD_CHAT_LINES_SNIPPET,
        resolve_gold_chat_snippet,
    )

    assert resolve_gold_chat_snippet("BV1OTHER") == GOLD_CHAT_LINES_SNIPPET


def test_normalize_enriches_setting_from_bowl_lines():
    chat = {
        "setting": "餐桌旁，灿灿和昭昭在吵架",
        "story_type": "C",
        "dialogue": [
            {"speaker": "昭昭", "line": "你碗里肉这么多，凭什么不能给我夹一块！"},
            {"speaker": "灿灿", "line": "你碗里那青菜不香吗？"},
        ],
    }
    row = {
        "structure_type": "C",
        "mechanism": "M2",
        "payload": {
            "scene_contract": {
                "location": "餐桌",
                "object": "肉",
                "characters": ["灿灿", "昭昭"],
            }
        },
    }
    out, notes = gc.apply_gold_chat_normalizations(chat, row=row)
    assert "肉" in str(out.get("setting") or "")
    assert "青菜" in str(out.get("setting") or "")
    assert any("冲突物" in n for n in notes)


def test_gate_forced_m14_p_rejects_when_not_q():
    """无拆穿反噬链的假 P 仍结构驳回；能纠到 Q 的不走此门。"""
    row = {
        "id": 99,
        "mechanism": "M14",
        "structure_type": "P",
        "conflict_core": "两人互骂了一会儿就散了",
        "payload": {
            "story_raw": "姐弟互骂几句，没有道具整蛊也没有认怂。",
            "beat": ["互骂", "散场"],
            "closing_intent": "散了",
            "dialogue_seed": [
                {"speaker": "灿灿", "intent": "骂一句"},
                {"speaker": "昭昭", "intent": "回骂"},
            ],
        },
    }
    with pytest.raises(ValueError, match="forced-m14p-not-prank"):
        gc._gate_forced_m14_p_or_raise(row)


def test_resolve_row_75_to_m15_q_allows_convert_gate():
    row = {
        "id": 75,
        "mechanism": "M14",
        "structure_type": "P",
        "conflict_core": "灿灿抽签耍赖，借口胃小推食，妈妈看穿让洗碗",
        "payload": {
            "story_raw": (
                "妈妈和灿灿玩抽签吃饭，灿灿耍赖重抽、逞强吃辣，"
                "最后借口胃小把剩食推给妈妈，妈妈看穿心思让她洗碗。"
            ),
            "beat": ["抽签", "逞强", "推食", "洗碗"],
            "closing_intent": "妈妈笑着让灿灿洗碗，看穿她的小心思",
            "dialogue_seed": [
                {"speaker": "灿灿", "intent": "耍赖重抽"},
                {"speaker": "灿灿", "intent": "推食借口胃小"},
                {"speaker": "妈妈", "intent": "看穿心思让洗碗"},
            ],
            "structure_mapping_note": "M2→M14+P",
        },
    }
    out, notes = gc._resolve_structure_row(row)
    assert out["mechanism"] == "M15"
    assert out["structure_type"] == "Q"
    assert any("cheat-expose" in n or "M15" in n for n in notes)
    gc._gate_forced_m14_p_or_raise(out)  # 已是 Q，不应抛


def test_local_hard_repairs_punchline_and_mom():
    story = _sample_chat()
    story.pop("punchline_explain", None)
    story["story_type"] = "A"
    story["dialogue"] = list(story["dialogue"]) + [
        {"speaker": "妈妈", "line": "别吵了先吃饭。"},
        {"speaker": "妈妈", "line": "吃完再理论。"},
    ]
    out = gc._apply_gold_chat_local_hard_repairs(
        story, structure_type="A", mom_lines_max=1
    )
    assert "punchline_explain" in out
    assert str(out["punchline_explain"]).startswith("A类")
    mom_n = sum(
        1
        for d in out["dialogue"]
        if isinstance(d, dict) and d.get("speaker") == "妈妈"
    )
    assert mom_n <= 1


def test_reject_message_not_pad_when_missing_fields():
    err = "缺少字段: punchline_explain; 妈妈台词须≤1句，当前2; 正文总字数须≥240，当前226"
    msg = gc._short_content_reject_message(err)
    assert "校验驳回" in msg
    assert "本地垫字仍不足" not in msg
    assert gc._has_non_short_hard_errors(err)


def test_structure_cons_lists_mom_penalty_and_log_cons():
    from app.services.daily_story.quality import (
        score_daily_story,
        structure_cons_for_log,
    )

    dialogue = [
        {"speaker": "妈妈", "line": "你作业写完了吗？"},
        {"speaker": "昭昭", "line": "妈，我屁股Q弹，你打我吧。"},
        {"speaker": "妈妈", "line": "你说什么？"},
        {"speaker": "灿灿", "line": "噗，弹簧屁股吗？"},
        {"speaker": "妈妈", "line": "都给我消停。"},
        {"speaker": "昭昭", "line": "因为弹，所以打了不哭呀。"},
        {"speaker": "灿灿", "line": "为什么？"},
        {"speaker": "昭昭", "line": "因为Q弹就能救场呀。"},
        {"speaker": "灿灿", "line": "你这歪理也太绝了。"},
        {"speaker": "昭昭", "line": "我说得通吧。"},
        {"speaker": "灿灿", "line": "那……我说不过你。"},
        {"speaker": "昭昭", "line": "行吧。"},
    ]
    base = {
        "story_type": "N",
        "conflict_core": "Q弹救场",
        "punchline_explain": "N类正经胡说",
        "dialogue": dialogue,
    }
    q_default = score_daily_story(dict(base))
    cons_default = q_default.get("structure_cons") or []
    assert any("妈妈台词偏多（3句）" in str(c) for c in cons_default)
    assert structure_cons_for_log(q_default)

    with_contract = dict(base)
    with_contract["_gold_chat_mom_lines_max"] = 3
    q_contract = score_daily_story(with_contract)
    cons_contract = q_contract.get("structure_cons") or []
    assert not any("妈妈台词偏多" in str(c) for c in cons_contract)

    over = dict(with_contract)
    over["dialogue"] = list(dialogue) + [
        {"speaker": "妈妈", "line": "灿灿快去写作业。"},
    ]
    q_over = score_daily_story(over)
    assert any("妈妈台词偏多（4句）" in str(c) for c in q_over.get("structure_cons") or [])


def test_structure_score_feedback_and_fail_log_use_structure_cons():
    import logging

    from app.services.gold_story.gold_chat.prompts import (
        format_structure_score_feedback,
    )

    quality = {
        "structure_score": 70,
        "structure_cons": ["妈妈台词偏多（3句）"],
        "reasons": ["结构70", "妈妈台词偏多（3句）"],
    }
    fb = format_structure_score_feedback("structure_score:70", {"quality": quality})
    assert "偏多" in fb

    logger_name = "app.services.gold_story.gold_chat.convert"
    mod_logger = logging.getLogger(logger_name)
    captured: list[str] = []

    class _CaptureHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            captured.append(record.getMessage())

    handler = _CaptureHandler()
    handler.setLevel(logging.INFO)
    saved_level = mod_logger.level
    saved_propagate = mod_logger.propagate
    saved_handlers = mod_logger.handlers[:]
    try:
        mod_logger.handlers = [handler]
        mod_logger.propagate = False
        mod_logger.setLevel(logging.INFO)
        chat = {"story_type": "N", "dialogue": [{"speaker": "昭昭", "line": "测"}]}
        gc.log_gold_chat_structure_score_fail(chat, quality, structure_type="N")
    finally:
        mod_logger.setLevel(saved_level)
        mod_logger.propagate = saved_propagate
        mod_logger.handlers[:] = saved_handlers

    assert captured
    assert "妈妈台词偏多" in captured[0]
    assert "reasons=" in captured[0]


def test_structure_cons_excludes_humor_regex_diagnostics():
    from app.services.daily_story.quality import structure_cons_for_log

    quality = {
        "structure_cons": ["妈妈台词偏多（3句）"],
        "reasons": [
            "结构70",
            "妈妈台词偏多（3句）",
            "好笑诊断：末句缺回旋",
        ],
    }
    cons = structure_cons_for_log(quality)
    assert cons == ["妈妈台词偏多（3句）"]
    assert not any("好笑" in c for c in cons)

    empty_key = {"structure_cons": [], "reasons": ["好笑诊断：xxx"]}
    assert structure_cons_for_log(empty_key) == []


def test_refine_short_candidate_uses_real_validation_without_padding(monkeypatch):
    """只 mock 模型与语义对齐；真实字数、单句长度等硬校验必须通过。"""
    import copy
    from app.services.gold_story.gold_chat.repair import GoldChatRepairBudget

    repaired = _sample_chat()
    for index, line in enumerate(repaired["dialogue"]):
        line["speaker"] = "昭昭" if index % 2 == 0 else "灿灿"
    gc.validate_gold_chat(repaired, mom_lines_max=2)
    short = copy.deepcopy(repaired)
    for line in short["dialogue"]:
        line["line"] = line["line"][:10]
    assert gc.dialogue_total_chars(short) < gc.DAILY_STORY_BODY_CHARS_MIN
    prompts = []

    def fix(candidate, prompt, **kwargs):
        prompts.append(prompt)
        assert gc.dialogue_total_chars(candidate) < gc.DAILY_STORY_BODY_CHARS_MIN
        return copy.deepcopy(repaired)

    def no_padding(*args, **kwargs):
        raise AssertionError("精修校验不得机械补字")

    monkeypatch.setattr(grf, "collect_align_issues", lambda *args, **kwargs: [])
    monkeypatch.setattr(gc, "_fix_chat_with_llm", fix)
    monkeypatch.setattr(gex, "_ensure_gold_chat_min_chars", no_padding)
    budget = GoldChatRepairBudget(max_repairs=2)
    result = grf.refine_gold_chat_align(
        short, structure_type="", mechanism="", align_block="",
        mom_lines_max=2, repair_budget=budget,
    )
    gc.validate_gold_chat(result, mom_lines_max=2)
    assert gc.dialogue_total_chars(result) >= gc.DAILY_STORY_BODY_CHARS_MIN
    assert len(prompts) == budget.used == 1
    assert "正文总字数" in prompts[0]


def test_prepare_short_candidate_does_not_pad_to_pass():
    import copy

    short = copy.deepcopy(_sample_chat())
    for line in short["dialogue"]:
        line["line"] = line["line"][:10]
    before = copy.deepcopy(short["dialogue"])
    with pytest.raises(ValueError, match="正文总字数"):
        gex._prepare_chat_for_validate(
            short, structure_type="", mechanism="", mom_lines_max=2,
        )
    assert short["dialogue"] == before


def test_refine_short_repair_exhaustion_preserves_candidate(monkeypatch):
    import copy
    from app.services.gold_story.gold_chat.repair import AlignRepairFailure, GoldChatRepairBudget

    short = _sample_chat()
    for line in short["dialogue"]:
        line["line"] = line["line"][:10]
    calls = []

    def unsuccessful_fix(candidate, prompt, **kwargs):
        calls.append(prompt)
        return copy.deepcopy(candidate)

    monkeypatch.setattr(grf, "collect_align_issues", lambda *args, **kwargs: [])
    monkeypatch.setattr(gc, "_fix_chat_with_llm", unsuccessful_fix)
    budget = GoldChatRepairBudget(max_repairs=2)
    with pytest.raises(AlignRepairFailure, match="正文总字数") as caught:
        grf.refine_gold_chat_align(
            short, structure_type="", mechanism="", align_block="",
            mom_lines_max=2, repair_budget=budget, max_rounds=2,
        )
    assert len(calls) == budget.used == 2
    assert gc.dialogue_total_chars(caught.value.candidate) < gc.DAILY_STORY_BODY_CHARS_MIN


def test_expand_local_length_close_avoids_second_llm_repair(monkeypatch, caplog):
    import copy
    import logging
    from app.services.gold_story.gold_chat import repair

    real_gate = gc._gate_gold_chat_structure_score
    _bypass_structure_gate(monkeypatch)
    monkeypatch.setattr(gc, "_gate_gold_chat_structure_score", real_gate)
    monkeypatch.setattr(gex.logger, "handlers", [caplog.handler])
    generations = []
    repair_inputs = []

    def generate(*args, **kwargs):
        generations.append(1)
        return _sample_chat()

    def score(chat, row):
        current_score = 80 if chat.get("revision") else 65
        return {**chat, "quality": {"structure_score": current_score, "score": current_score}}

    def fix(chat, prompt, **kwargs):
        repair_inputs.append((chat.get("revision", 0), prompt))
        result = copy.deepcopy(chat)
        # 模拟第 1 次结构修稿已把结构分修到 80，但正文被压到 233 字。
        for line in result["dialogue"]:
            while len(line["line"]) > 1 and gc.dialogue_total_chars(result) > 233:
                line["line"] = line["line"][:-1]
        result["revision"] = len(repair_inputs)
        return result

    monkeypatch.setattr(
        gex,
        "_short_spot_fix_chat_with_llm",
        lambda chat, fb, **kw: fix(chat, fb),
    )
    monkeypatch.setattr(gex, "_chat_json", generate)
    monkeypatch.setattr(gex, "EXPAND_CANDIDATE_COUNT", 1)
    monkeypatch.setattr(gex, "EXPAND_REGENERATE_MAX", 5)
    monkeypatch.setattr(gc, "_attach_gold_chat_structure_score", score)
    monkeypatch.setattr(gex, "_fix_chat_with_llm", fix)
    budget = repair.GoldChatRepairBudget(max_repairs=2)

    with caplog.at_level(logging.INFO):
        result = gex.gold_story_to_gold_chat(_sample_row(), repair_budget=budget)

    assert result["revision"] == 1
    assert result["quality"]["structure_score"] == 80
    assert gc.dialogue_total_chars(result) >= gc.DAILY_STORY_BODY_CHARS_MIN
    assert len(generations) == 1
    assert [revision for revision, _ in repair_inputs] == [0]
    assert budget.used == 1
    assert budget.remaining == 1
    assert "candidate rejected stage=expand_structure score=65" in caplog.text
    assert "repair post-hard length close chars=233->" in caplog.text


def test_expand_structure_restores_accidental_parent_speaker_without_deleting_body():
    import copy

    baseline = {
        "dialogue": [
            {"speaker": "妈妈", "line": "先把规矩说清楚。"},
            {"speaker": "昭昭", "line": "我有话要认真解释。"},
            {"speaker": "灿灿", "line": "那你先说，我听着。"},
            {"speaker": "妈妈", "line": "你们继续说。"},
            {"speaker": "昭昭", "line": "我继续把理由讲完。"},
            {"speaker": "妈妈", "line": "行吧，我听明白了。"},
        ]
    }
    draft = copy.deepcopy(baseline)
    draft["dialogue"][1]["speaker"] = "妈妈"
    before_chars = gc.dialogue_total_chars(draft)

    out, changed = gex._restore_extra_parent_speakers_from_baseline(
        draft,
        baseline,
        parent_lines_max=3,
    )

    assert changed
    assert out["dialogue"][1]["speaker"] == "昭昭"
    assert len(out["dialogue"]) == len(draft["dialogue"])
    assert gc.dialogue_total_chars(out) == before_chars
    assert sum(
        row.get("speaker") in {"妈妈", "爸爸"}
        for row in out["dialogue"]
    ) == 3


def test_expand_structure_repair_caps_mom_before_acceptance(monkeypatch, caplog):
    """N 结构修稿新增第 4 句妈妈时，同轮裁回并补足字数，不再烧第二次预算。"""
    import copy
    import logging
    from app.services.gold_story.gold_chat import repair

    real_gate = gc._gate_gold_chat_structure_score
    _bypass_structure_gate(monkeypatch)
    monkeypatch.setattr(gc, "_gate_gold_chat_structure_score", real_gate)
    monkeypatch.setattr(gex.logger, "handlers", [caplog.handler])

    row = _sample_row()
    row["structure_type"] = "N"
    row["mechanism"] = "M6"
    row["payload"]["scene_contract"] = {"mom_lines_max": 3}
    repair_calls = []

    def generate(*args, **kwargs):
        chat = _sample_chat()
        chat["story_type"] = "N"
        chat["punchline_explain"] = "N类：追问后一本正经自洽，最后让对方接不住"
        chat["dialogue"] = [
            {"speaker": "灿灿", "line": "我……我本来要写的，就是铅笔找不到了嘛。"},
            {"speaker": "昭昭", "line": "妈，我屁股很Q弹，你打我吧，别打姐姐。"},
            {"speaker": "妈妈", "line": "昭昭，你手都停半空了，为什么突然说这个？"},
            {"speaker": "昭昭", "line": "因为没人教，我自己想的，Q弹的打了不疼，还响呢！"},
            {"speaker": "灿灿", "line": "你还真是照这个道理认真想的？"},
            {"speaker": "昭昭", "line": "当然，我刚才就是这么认真回答的。"},
            {"speaker": "灿灿", "line": "噗……昭昭你别说了，我肩膀都抖了。"},
            {"speaker": "妈妈", "line": "你还笑？作业没写你倒笑得出来？"},
            {"speaker": "昭昭", "line": "姐姐笑，是喜欢我屁股Q弹，还是不信？"},
            {"speaker": "灿灿", "line": "妈，我这就写，你别听昭昭胡说，快挪开。"},
            {"speaker": "昭昭", "line": "我没胡说，你看我扭一下，弹回来还带晃的。"},
            {"speaker": "妈妈", "line": "行吧行吧，你们俩一个比一个会捣乱。"},
            {"speaker": "灿灿", "line": "我回房间补作业，十分钟就写完吧。"},
            {"speaker": "昭昭", "line": "那妈，我屁股还打不打了？不打我收起来咯。"},
        ]
        assert gc.dialogue_total_chars(chat) >= gc.DAILY_STORY_BODY_CHARS_MIN
        assert sum(x.get("speaker") == "妈妈" for x in chat["dialogue"]) == 3
        return chat

    def score(chat, _row):
        current = 80 if chat.get("revision") else 65
        return {**chat, "quality": {"structure_score": current, "score": current}}

    def fix(chat, prompt, **kwargs):
        repair_calls.append(prompt)
        out = copy.deepcopy(chat)
        # 模拟真实失败：结构修稿已把分数修好，但又新增一条妈妈句（句数也变化）。
        # 这样不能靠 baseline speaker 还原，必须走 N-aware hard trim。
        out["dialogue"].insert(10, {"speaker": "妈妈", "line": "先把这件事说清楚。"})
        out["revision"] = 1
        assert sum(x.get("speaker") == "妈妈" for x in out["dialogue"]) == 4
        return out

    monkeypatch.setattr(gex, "_chat_json", generate)
    monkeypatch.setattr(gex, "EXPAND_CANDIDATE_COUNT", 1)
    monkeypatch.setattr(gex, "EXPAND_REGENERATE_MAX", 5)
    monkeypatch.setattr(gc, "_attach_gold_chat_structure_score", score)
    monkeypatch.setattr(gex, "_fix_chat_with_llm", fix)
    budget = repair.GoldChatRepairBudget(max_repairs=2)

    with caplog.at_level(logging.INFO):
        result = gex.gold_story_to_gold_chat(row, repair_budget=budget)

    mom_n = sum(x.get("speaker") == "妈妈" for x in result["dialogue"])
    assert result["quality"]["structure_score"] == 80
    assert gc.dialogue_total_chars(result) >= gc.DAILY_STORY_BODY_CHARS_MIN
    assert mom_n <= 3
    assert len(repair_calls) == 1
    assert budget.used == 1
    assert budget.remaining == 1
    assert "repair local hard close mom=4->3 max=3" in caplog.text
    body = "".join(str(x.get("line") or "") for x in result["dialogue"])
    assert "为什么突然说这个" in body


def test_expand_stops_when_alignment_budget_exhausted(monkeypatch):
    from app.services.gold_story.gold_chat.repair import (
        AlignRepairFailure, GoldChatRepairBudget, GoldChatRepairExhausted,
    )

    _bypass_structure_gate(monkeypatch)
    generations = []

    def generate(*args, **kwargs):
        generations.append(1)
        return _sample_chat()

    def fail_alignment(chat, **kwargs):
        budget = kwargs["repair_budget"]
        assert budget.consume(stage="align")
        assert budget.consume(stage="align")
        candidate = {**chat, "revision": "latest_align"}
        raise AlignRepairFailure(
            stage="align_validate", validation_errors=["正文总字数须≥240，当前222"],
            align_issues=[], candidate=candidate,
        )

    monkeypatch.setattr(gex, "_chat_json", generate)
    monkeypatch.setattr(gex, "EXPAND_CANDIDATE_COUNT", 1)
    monkeypatch.setattr(gex, "EXPAND_REGENERATE_MAX", 5)
    monkeypatch.setattr(grf, "refine_gold_chat_align", fail_alignment)
    budget = GoldChatRepairBudget(max_repairs=2)
    with pytest.raises(GoldChatRepairExhausted, match="当前222") as caught:
        gex.gold_story_to_gold_chat(_sample_row(), repair_budget=budget)
    assert caught.value.stage == "align_validate"
    assert caught.value.candidate["revision"] == "latest_align"
    assert len(generations) == 1
    assert budget.used == 2
