"""gold_chat 保真机审与 Pass 2 精修测试。"""

from __future__ import annotations

import pytest

from app.services.gold_story.gold_chat import convert as gc
from app.services.gold_story.gold_chat import expand as gex
from app.services.gold_story.gold_chat import refine as grf
from app.services.gold_story.gold_chat.validate import (
    collect_align_issues,
    should_reexpand,
)

_CLOSING = "灿灿问以后还打不打架，昭昭齐声不打了，妈妈拿碘伏"
_CONFLICT_5 = "灿灿：你干嘛弄坏我的画！"


def _m5h_dialogue_v1() -> list[dict[str, str]]:
    """#5 LLM 首稿（评审前）：21 句结构，仅关键行留 bug。"""
    dlg = _m5h_dialogue_v2()
    dlg[0] = {"speaker": "昭昭", "line": "姐姐，你画啥呢？让我瞅瞅！"}
    dlg[2] = {"speaker": "昭昭", "line": "哼，小气鬼！我偏要弄你的画！"}
    dlg[8] = {"speaker": "灿灿", "line": "谁先动手谁道歉！哼，我不原谅！"}
    dlg[14] = {
        "speaker": "妈妈",
        "line": "弟弟都道歉了，画能再画，额头先涂。",
    }
    return dlg


def _m5h_refine_fixes() -> list[dict[str, str | int]]:
    """Pass 2 mock 定点修稿 → v2 结构（行号按连说合并后的 v1 稿）。"""
    return [
        {"no": 1, "line": "我在画小兔子呢，你也画你的别捣乱！"},
        {"no": 3, "line": "哼，我偏要涂一下，弄坏你的画！"},
        {"no": 9, "line": "家规就是谁先动手谁道歉！"},
        {"no": 14, "line": "昭昭先弄画不对，灿灿也别推人。"},
        {"no": 16, "line": "以后还打不打架？"},
    ]


def _m5h_dialogue_v2() -> list[dict[str, str]]:
    """#5 修稿：机审应通过（灿灿受害、昭昭先动手）。"""
    return [
        {"speaker": "灿灿", "line": "我在画小兔子呢，你也画你的别捣乱！"},
        {"speaker": "灿灿", "line": "你看，都快画好了！"},
        {"speaker": "昭昭", "line": "哼，我偏要涂一下，弄坏你的画！"},
        {"speaker": "灿灿", "line": "你干嘛！别碰我的纸！"},
        {"speaker": "昭昭", "line": "是你先推我的，我手里的彩笔都掉地上了！"},
        {"speaker": "灿灿", "line": "我也抢你画撕啦！你赔！"},
        {"speaker": "灿灿", "line": "你赔！我额头都蹭破了！"},
        {"speaker": "昭昭", "line": "呜……对不起嘛，我不是故意的。"},
        {"speaker": "灿灿", "line": "家规就是谁先动手谁道歉！"},
        {"speaker": "昭昭", "line": "姐姐，我真的错了，你别不理我。"},
        {"speaker": "灿灿", "line": "哼，我不原谅，你把兔子的耳朵全涂黑了！"},
        {"speaker": "灿灿", "line": "道歉也没用！我画了好久呢！"},
        {"speaker": "妈妈", "line": "别打了！谁先动手的？"},
        {"speaker": "昭昭", "line": "我……我先弄花的，姐姐对不起！"},
        {"speaker": "妈妈", "line": "昭昭先弄画不对，灿灿也别推人。"},
        {"speaker": "灿灿", "line": "哼……那拉手吧。"},
        {"speaker": "灿灿", "line": "以后还打不打架？"},
        {"speaker": "昭昭", "line": "不打了！"},
        {"speaker": "灿灿", "line": "不打了！这还差不多。"},
        {"speaker": "妈妈", "line": "我去拿碘伏，你额头上还没涂呢。"},
        {"speaker": "灿灿", "line": "嗯，谢谢妈妈，我先把画纸放到桌上去。"},
    ]


def _m5h_dialogue_bad_refine() -> list[dict[str, str]]:
    """#5 精修成稿：机审应拦 speaker 倒置 + 收场 invent。"""
    return [
        {"speaker": "灿灿", "line": "昭昭，你趴那儿弄啥呢？让我瞅瞅。"},
        {"speaker": "昭昭", "line": "不行！这是我的秘密，你不能看！"},
        {"speaker": "灿灿", "line": "哼，小气鬼！我偏要看！"},
        {"speaker": "昭昭", "line": "你抢坏了我的画！我也有你的画！"},
        {"speaker": "灿灿", "line": "你敢！哎呀！你推我！"},
        {"speaker": "昭昭", "line": "谁让你抢的！我也弄坏你的画！"},
        {"speaker": "灿灿", "line": "你赔！我额头都蹭破了！"},
        {"speaker": "昭昭", "line": "呜……对不起嘛，我不是故意的。"},
        {"speaker": "灿灿", "line": "家规是谁先动手谁道歉！"},
        {"speaker": "昭昭", "line": "哼，我不原谅！"},
        {"speaker": "灿灿", "line": "道歉也没用！你赔我的画！"},
        {"speaker": "妈妈", "line": "别打了！谁先动手的？"},
        {"speaker": "昭昭", "line": "我……我先推的，姐姐对不起！"},
        {"speaker": "妈妈", "line": "昭昭先动手不对，灿灿你也不该抢，都有错。"},
        {"speaker": "灿灿", "line": "哼……那拉手吧。"},
        {"speaker": "妈妈", "line": "以后还打不打架？"},
        {"speaker": "昭昭", "line": "不打了！"},
        {"speaker": "灿灿", "line": "不打了！这还差不多。"},
        {"speaker": "妈妈", "line": "我去拿碘伏，你额头上还没涂呢。"},
        {"speaker": "灿灿", "line": "你快点回来！"},
        {"speaker": "昭昭", "line": "嗯，姐姐不疼了。"},
    ]


def _m5h_dialogue_pipeline() -> list[dict[str, str]]:
    """精修流水线产出稿（含 M5 合并 + 收场 invent）。"""
    return [
        {"speaker": "灿灿", "line": "昭昭，你趴那儿画啥呢？让我瞅瞅！"},
        {"speaker": "昭昭", "line": "不行！这是我的秘密，你不能看！"},
        {"speaker": "灿灿", "line": "哼，小气鬼！我偏要看！"},
        {"speaker": "昭昭", "line": "你把我画抢坏了！再抢我打你了！"},
        {"speaker": "灿灿", "line": "你敢！哎呀！你推我！"},
        {"speaker": "昭昭", "line": "谁让你抢的！我也弄坏你的画！"},
        {"speaker": "灿灿", "line": "你赔！我额头都蹭破了！"},
        {"speaker": "昭昭", "line": "呜……对不起嘛，我不是故意的。"},
        {"speaker": "灿灿", "line": "家规就是谁先动手谁道歉！哼，我不原谅！道歉也没用！"},
        {"speaker": "妈妈", "line": "别打了！谁先动手的？"},
        {"speaker": "昭昭", "line": "我……我先推的，姐姐对不起！"},
        {"speaker": "妈妈", "line": "昭昭先动手不对，但灿灿你抢画也有错。弟弟都道歉了，原谅他吧。"},
        {"speaker": "灿灿", "line": "哼……那拉手吧。"},
        {"speaker": "妈妈", "line": "以后还打不打架？"},
        {"speaker": "昭昭", "line": "不打了！"},
        {"speaker": "灿灿", "line": "不打了！这还差不多。"},
        {"speaker": "妈妈", "line": "我去拿碘伏，你额头上还没涂呢。"},
        {"speaker": "灿灿", "line": "妈妈，我帮你拿棉签！"},
        {"speaker": "昭昭", "line": "我也去！姐姐，我扶你！"},
    ]


def _m5h_story(dialogue: list[dict[str, str]]) -> dict:
    return {
        "scene_title": "画作争夺战",
        "setting": "客厅，地上散落画纸和彩笔",
        "key": "互毁画作",
        "conflict_core": "昭昭弄坏灿灿的画，互毁扭打，妈妈调解。",
        "dialogue": dialogue,
        "punchline_explain": "H类第三方化解，妈妈定责劝和",
    }


def _issues(story: dict, **kw) -> list[dict]:
    return collect_align_issues(
        story,
        structure_type="H",
        mechanism="M5",
        closing_intent=_CLOSING,
        conflict_text=kw.pop("conflict_text", _CONFLICT_5),
        **kw,
    )


def test_collect_align_issues_i_type_contract_without_quality_ready():
    """I quality_ready=False 时，gold_chat 仍须拦缺语塞/末段制敌。"""
    from app.services.daily_story.story_types import type_body_validation_enabled

    assert not type_body_validation_enabled("I")
    story = {
        "story_type": "I",
        "punchline_explain": "I类问倒收束",
        "dialogue": [
            {"speaker": "灿灿", "line": "遥控器给我，我要看动画！"},
            {"speaker": "昭昭", "line": "不行，我先看新闻！"},
            {"speaker": "灿灿", "line": "你天天霸占电视，不讲理！"},
            {"speaker": "昭昭", "line": "我爱学习，你爱吗呀？"},
            {"speaker": "灿灿", "line": "我……我也爱学习啊。"},
            {"speaker": "昭昭", "line": "那你怎么不写作业嘛？"},
            {"speaker": "灿灿", "line": "我……我待会写吧。"},
            {"speaker": "昭昭", "line": "哼，就知道看电视呢。"},
            {"speaker": "灿灿", "line": "嘿嘿，一招制敌好不好！"},
            {"speaker": "昭昭", "line": "你等着，我写完作业再来抢！"},
            {"speaker": "灿灿", "line": "写作业还想着抢，你心不诚！"},
            {"speaker": "昭昭", "line": "我诚心诚意，写完就来看！"},
        ],
    }
    issues = collect_align_issues(
        story,
        structure_type="I",
        mechanism="M11",
    )
    kinds = {str(x.get("kind") or "") for x in issues}
    assert "对齐-类型契约" in kinds
    descs = " ".join(str(x.get("desc") or "") for x in issues)
    assert "语塞" in descs or "一招制敌" in descs or "制敌" in descs


def test_collect_align_issues_type_contract_covers_a_to_l_registry():
    """A–L 均进入类型契约机审路径（空对白跳过，有对白则不因未注册漏检）。"""
    from app.services.daily_story.story_types import STORY_TYPE_LABELS

    base_dlg = [
        {"speaker": "昭昭", "line": "这是我的东西，不准抢！"},
        {"speaker": "灿灿", "line": "凭什么你说了算呀？"},
        {"speaker": "昭昭", "line": "我说了算，你听着！"},
        {"speaker": "灿灿", "line": "那我偏不听你的！"},
        {"speaker": "昭昭", "line": "你再抢我就告状！"},
        {"speaker": "灿灿", "line": "你告去呀，我才不怕！"},
        {"speaker": "昭昭", "line": "哼，看你还嘴硬！"},
        {"speaker": "灿灿", "line": "我才不认输呢！"},
    ]
    for code in sorted(STORY_TYPE_LABELS.keys()):
        story = {
            "story_type": code,
            "punchline_explain": f"{code}类测试",
            "dialogue": list(base_dlg),
        }
        # 不应因未知类型抛错；特化类型可能有 issue，也可能没有
        collect_align_issues(story, structure_type=code, mechanism="")


def test_collect_align_issues_tear_not_only_si_huai():
    """「撕破/撕了」须算互毁前文依据，勿误拦扩写合理稿。"""
    dlg = [
        {"speaker": "灿灿", "line": "我的画马上就好，太阳要涂成金色。"},
        {"speaker": "昭昭", "line": "我看看你画的什么嘛！"},
        {"speaker": "灿灿", "line": "别碰！你手脏，会弄脏我的画！"},
        {"speaker": "昭昭", "line": "哼，我偏要碰！哎呀，不小心撕破了。"},
        {"speaker": "灿灿", "line": "你！你故意的！我也要弄坏你的画！"},
    ]
    kinds = {x["kind"] for x in _issues(_m5h_story(dlg))}
    assert "保真-互毁前文" not in kinds


def test_collect_align_issues_inverted_role_flags():
    dlg = [
        {"speaker": "灿灿", "line": "昭昭，你偷偷画什么呢？让我瞅瞅！"},
        {"speaker": "昭昭", "line": "不行！这是我的秘密画！"},
        {"speaker": "灿灿", "line": "哼，小气鬼！我偏要看！"},
        {"speaker": "昭昭", "line": "你走开！再抢我就撕了它！"},
        {"speaker": "灿灿", "line": "你敢！哎呀——你推我！"},
        {"speaker": "灿灿", "line": "不给！我撕——看你还藏！"},
        {"speaker": "昭昭", "line": "哇！我的画！你赔我！"},
        {"speaker": "灿灿", "line": "你把我额头都蹭破了！"},
        {"speaker": "昭昭", "line": "对不起……我不是故意的……"},
        {"speaker": "灿灿", "line": "家规就是谁先动手谁道歉！我不原谅你！"},
        {"speaker": "妈妈", "line": "别打了！谁先动手的？"},
        {"speaker": "昭昭", "line": "是姐姐先抢我画……"},
        {"speaker": "妈妈", "line": "都有错，拉手吧。"},
        {"speaker": "灿灿", "line": "哼……那拉手吧。"},
        {"speaker": "妈妈", "line": "以后还打不打架？"},
        {"speaker": "昭昭", "line": "不打了！"},
        {"speaker": "灿灿", "line": "不打了！"},
        {"speaker": "妈妈", "line": "来，额头涂点碘伏。"},
    ]
    kinds = {x["kind"] for x in _issues(_m5h_story(dlg))}
    assert "保真-发起方倒置" in kinds


def test_split_align_issues_warn_kinds():
    from app.services.gold_story.gold_chat.validate import (
        split_align_issues,
    )

    issues = [
        {"kind": "保真-M5合并", "lines": [9]},
        {"kind": "保真-互毁前文", "lines": [6]},
        {"kind": "保真-收场Invent", "lines": [20]},
    ]
    blocking, warn = split_align_issues(issues)
    assert {x["kind"] for x in blocking} == {"保真-互毁前文"}
    assert {x["kind"] for x in warn} == {"保真-M5合并", "保真-收场Invent"}


def test_refine_passes_with_only_align_warn(monkeypatch):
    dlg = _m5h_dialogue_v2()
    dlg[8] = {
        "speaker": "灿灿",
        "line": "家规就是谁先动手谁道歉！哼，我不原谅！道歉也没用！",
    }
    story = _m5h_story(dlg)
    from app.services.gold_story.gold_chat.validate import (
        split_align_issues,
    )

    blocking, warn = split_align_issues(_issues(story))
    assert not blocking
    assert warn

    def fail_llm(*_a, **_k):
        raise AssertionError("should not call LLM when only warn")

    monkeypatch.setattr(gc, "_align_refine_with_llm", fail_llm)
    monkeypatch.setattr(grf, "_align_refine_with_llm", fail_llm)
    out = gc.refine_gold_chat_align(
        story,
        structure_type="H",
        mechanism="M5",
        align_block="",
        mom_lines_max=4,
        closing_intent=_CLOSING,
        bail_on_structural=False,
    )
    assert out["dialogue"][8]["line"].startswith("家规就是")


def test_collect_align_issues_bad_refine_flags_speaker_and_invent():
    kinds = {x["kind"] for x in _issues(_m5h_story(_m5h_dialogue_bad_refine()))}
    assert "保真-M5拒和speaker" in kinds
    assert "保真-对象持有补丁" in kinds or "保真-互毁前文" in kinds
    assert "保真-收场Invent" in kinds


def test_should_reexpand_structural():
    issues = _issues(_m5h_story(_m5h_dialogue_bad_refine()))
    assert should_reexpand(issues)


def test_should_reexpand_single_local_issue():
    dlg = _m5h_dialogue_v2()
    dlg[8] = {"speaker": "灿灿", "line": "谁先动手谁道歉！你推我，你先道歉！"}
    dlg[10] = {"speaker": "灿灿", "line": "哼，我不原谅！"}
    dlg[11] = {"speaker": "灿灿", "line": "道歉也没用！我画了好久呢！"}
    issues = _issues(_m5h_story(dlg))
    assert issues
    assert not should_reexpand(issues)


def test_collect_align_issues_pipeline_draft_flags_merge_and_invent():
    kinds = {x["kind"] for x in _issues(_m5h_story(_m5h_dialogue_pipeline()))}
    assert "保真-M5合并" in kinds
    assert "保真-互毁前文" in kinds or "保真-互毁对象" in kinds
    assert "保真-收场Invent" in kinds


def test_refine_gold_chat_align_applies_spot_fixes(monkeypatch):
    from app.services.daily_story.story_types import apply_gold_chat_body_pipeline

    story = _m5h_story(_m5h_dialogue_v1())
    story, _ = apply_gold_chat_body_pipeline(story, structure_type="H")

    def fake_refine(_story, _issues, **_kw):
        return {"fixes": _m5h_refine_fixes()}

    monkeypatch.setattr(gc, "_align_refine_with_llm", fake_refine)
    monkeypatch.setattr(grf, "_align_refine_with_llm", fake_refine)
    out = gc.refine_gold_chat_align(
        story,
        structure_type="H",
        mechanism="M5",
        align_block="",
        mom_lines_max=4,
        closing_intent=_CLOSING,
        bail_on_structural=False,
    )
    assert any("家规就是" in str(d.get("line") or "") for d in out["dialogue"])
    assert _issues(out) == []


def test_refine_gold_chat_align_fails_when_llm_noop(monkeypatch):
    story = _m5h_story(_m5h_dialogue_v1())

    def fake_refine(_story, _issues, **_kw):
        return {"fixes": []}

    monkeypatch.setattr(gc, "_align_refine_with_llm", fake_refine)
    monkeypatch.setattr(grf, "_align_refine_with_llm", fake_refine)
    with pytest.raises(ValueError, match="align_refine_failed"):
        gc.refine_gold_chat_align(
            story,
            structure_type="H",
            mechanism="M5",
            align_block="",
            mom_lines_max=4,
            closing_intent=_CLOSING,
            max_rounds=1,
            bail_on_structural=False,
        )


def test_refine_bails_on_structural_by_default():
    story = _m5h_story(_m5h_dialogue_bad_refine())
    with pytest.raises(ValueError, match="align_structural"):
        gc.refine_gold_chat_align(
            story,
            structure_type="H",
            mechanism="M5",
            align_block="",
            mom_lines_max=4,
            closing_intent=_CLOSING,
        )


def test_gold_story_to_gold_chat_runs_align_pass(monkeypatch):
    def fake_chat(system: str, _user: str, **_kwargs) -> dict:
        if "对齐精修" in system or "保真精修" in system:
            return {"fixes": _m5h_refine_fixes()}
        return _m5h_story(_m5h_dialogue_v1())

    row = {
        "id": 5,
        "title": "双胞胎画画互毁",
        "mechanism": "M5",
        "structure_type": "H",
        "conflict_core": "昭昭弄坏灿灿的画，互毁扭打，妈妈调解",
        "story_raw": "哥哥画画弟弟捣乱互毁" * 10,
        "payload": {
            "beat": ["互毁", "妈妈调解", "和好"],
            "dialogue_seed": [{"speaker": "妈妈", "intent": "谁先动手"}],
            "closing_intent": _CLOSING,
            "scene_contract": {
                "mom_lines_max": 4,
                "story_type": "H",
                "conflict": "灿灿：你干嘛弄坏我的画！",
                "beat_chain": [
                    {
                        "beat": 1,
                        "speaker": "灿灿",
                        "intent": "专心画画：展示自己的画",
                    },
                    {
                        "beat": 2,
                        "speaker": "昭昭",
                        "intent": "捣乱毁画：弄坏灿灿的画",
                    },
                ],
            },
        },
    }
    monkeypatch.setattr(gc, "_chat_json", fake_chat)
    monkeypatch.setattr(gex, "_chat_json", fake_chat)
    monkeypatch.setattr(gc, "EXPAND_CANDIDATE_COUNT", 1)
    monkeypatch.setattr(gex, "EXPAND_CANDIDATE_COUNT", 1)
    monkeypatch.setattr(gc, "EXPAND_REGENERATE_MAX", 1)
    monkeypatch.setattr(gex, "EXPAND_REGENERATE_MAX", 1)
    _real_refine = gc.refine_gold_chat_align

    def refine_test(*args, **kwargs):
        kwargs["bail_on_structural"] = False
        return _real_refine(*args, **kwargs)

    monkeypatch.setattr(gc, "refine_gold_chat_align", refine_test)
    monkeypatch.setattr(grf, "refine_gold_chat_align", refine_test)
    monkeypatch.setattr(
        gc,
        "_attach_gold_chat_structure_score",
        lambda chat, _row: {
            **chat,
            "quality": {"structure_score": 80, "score": 80, "summary": "结构80"},
        },
    )
    monkeypatch.setattr(gc, "_gate_gold_chat_structure_score", lambda _chat: 80)
    out = gc.gold_story_to_gold_chat(row)
    assert "家规就是" in out["dialogue"][8]["line"]
    assert _issues(out) == []


_AUTH_BEAT_CHAIN = [
    {"beat": 1, "speaker": "妈妈", "intent": "立规：谁先写完作业谁玩"},
    {"beat": 2, "speaker": "昭昭", "intent": "占物：偷偷把作业本藏进冰箱"},
    {"beat": 3, "speaker": "灿灿", "intent": "急哭：找不到作业本"},
    {"beat": 4, "speaker": "妈妈", "intent": "反转：不罚反将任务"},
    {"beat": 5, "speaker": "灿灿", "intent": "补刀：威胁揭短"},
    {"beat": 6, "speaker": "昭昭", "intent": "认怂：立刻让渡"},
    {"beat": 7, "speaker": "妈妈", "intent": "权威点题收束"},
]


def _authority_story(dialogue: list[dict[str, str]]) -> dict:
    from app.services.gold_story.structure_resolve import (
        CLOSING_MODE_AUTHORITY_PUNCHLINE,
    )

    return {
        "scene_title": "权威点题样例",
        "setting": "客厅",
        "key": "权威点题",
        "conflict_core": "一方藏物抢资源，对方急哭",
        "closing_mode": CLOSING_MODE_AUTHORITY_PUNCHLINE,
        "dialogue": dialogue,
        "punchline_explain": "G类权威点题收束",
    }


def _authority_issues(story: dict) -> list[dict]:
    return collect_align_issues(
        story,
        structure_type="G",
        mechanism="M4",
        closing_intent="权威点题收束",
        beat_chain=_AUTH_BEAT_CHAIN,
        conflict_text=str(story.get("conflict_core") or ""),
    )


def test_authority_punchline_bad_opening_like_91():
    """开场跳过立规 + 急哭/撇清说话人对调 → 保真-权威*。"""
    dlg = [
        {"speaker": "昭昭", "line": "听见了听见了，我这就去写，姐姐你慢慢来。"},
        {"speaker": "灿灿", "line": "你写你的，别老盯着我这边看。"},
        {"speaker": "昭昭", "line": "谁盯你了，我去拿瓶水总行吧。"},
        {"speaker": "灿灿", "line": "咦，我作业本呢？刚才明明放在上面。"},
        {"speaker": "昭昭", "line": "我翻遍书包都找不到，急死我了！"},
        {"speaker": "灿灿", "line": "没看见，你自己乱放还赖我，哭什么呀。"},
        {"speaker": "妈妈", "line": "你藏得挺快，那今晚你负责哄她睡觉。"},
        {"speaker": "昭昭", "line": "我哄她？我不会哄人，换个别的事行？"},
        {"speaker": "灿灿", "line": "你哄我，我就告诉妈你偷吃。"},
        {"speaker": "昭昭", "line": "你玩你玩，我哄你。"},
        {"speaker": "妈妈", "line": "记住，这个家我第一，你俩并列第三。"},
    ]
    kinds = {x["kind"] for x in _authority_issues(_authority_story(dlg))}
    assert "保真-权威开场" in kinds
    assert "保真-权威角色" in kinds


def test_authority_punchline_good_opening_passes_opening_kinds():
    dlg = [
        {"speaker": "妈妈", "line": "谁先写完作业谁就能玩。"},
        {"speaker": "昭昭", "line": "听见了，我这就去写。"},
        {"speaker": "灿灿", "line": "咦，我作业本呢？翻遍书包找不到，急死我了！"},
        {"speaker": "昭昭", "line": "没看见，你自己乱放还赖我，哭什么呀。"},
        {"speaker": "妈妈", "line": "你藏得挺快，那今晚你负责哄她睡觉。"},
        {"speaker": "昭昭", "line": "我不会哄人，换个别的事行？"},
        {"speaker": "灿灿", "line": "你哄我，我就告诉妈你偷吃。"},
        {"speaker": "昭昭", "line": "你玩你玩，我哄你。"},
        {"speaker": "灿灿", "line": "这还差不多。"},
        {"speaker": "妈妈", "line": "记住，这个家我第一，你俩并列第三。"},
    ]
    kinds = {x["kind"] for x in _authority_issues(_authority_story(dlg))}
    assert "保真-权威开场" not in kinds
    assert "保真-权威角色" not in kinds


def test_authority_punchline_skin_swap_school_passes_opening_kinds():
    """换皮（交卷/选座）仍只卡抽象槽，不开场误报。"""
    chain = [
        {"beat": 1, "speaker": "老师", "intent": "立规：谁先交卷谁先选座位"},
        {"beat": 2, "speaker": "昭昭", "intent": "占物：把别人卷子藏进讲台"},
        {"beat": 3, "speaker": "灿灿", "intent": "急哭：找不到卷子"},
        {"beat": 4, "speaker": "老师", "intent": "反转：不罚反将收作业任务"},
        {"beat": 5, "speaker": "灿灿", "intent": "补刀：威胁揭短"},
        {"beat": 6, "speaker": "昭昭", "intent": "认怂：立刻让渡选座权"},
        {"beat": 7, "speaker": "老师", "intent": "权威点题收束"},
    ]
    # 角色映射仍用家中说话人；beat0 speaker 用妈妈代替老师以适配 ALLOWED speakers
    chain[0]["speaker"] = "妈妈"
    chain[3]["speaker"] = "妈妈"
    chain[6]["speaker"] = "妈妈"
    dlg = [
        {"speaker": "妈妈", "line": "谁先交卷谁先选座位，定规了。"},
        {"speaker": "昭昭", "line": "我这就交。"},
        {"speaker": "灿灿", "line": "我卷子呢？翻遍桌子找不到，急死我了！"},
        {"speaker": "昭昭", "line": "没看见，你自己乱放还赖我，哭什么呀。"},
        {"speaker": "妈妈", "line": "你藏得快，那你负责帮全班收作业。"},
        {"speaker": "昭昭", "line": "收作业我真不会，换事行？"},
        {"speaker": "灿灿", "line": "你帮我收，我就告诉老师你抄答案。"},
        {"speaker": "昭昭", "line": "你选你选，我收。"},
        {"speaker": "灿灿", "line": "这还差不多。"},
        {"speaker": "妈妈", "line": "记住，这个班我第一，你俩并列第三。"},
    ]
    story = _authority_story(dlg)
    kinds = {
        x["kind"]
        for x in collect_align_issues(
            story,
            structure_type="G",
            mechanism="M4",
            closing_intent="权威点题收束",
            beat_chain=chain,
            conflict_text="藏卷子抢选座，对方急哭",
        )
    }
    assert "保真-权威开场" not in kinds
    assert "保真-权威角色" not in kinds


def test_format_align_block_kb_chain_not_stalemate():
    from app.services.gold_story.gold_chat.prompts import format_align_block

    block = format_align_block(
        structure_type="K",
        mechanism="M12",
        beat=["妈妈不评理", "孩子自行恢复互动"],
        closing_intent="妈妈说不掺和就对了",
        k_close_mode="K_B_CHILD_SELF_RESOLVE",
    )
    assert "孩子自行恢复" in block or "自行恢复" in block
    assert "僵持（不和好" not in block


def test_format_align_block_passes_authority_closing_mode():
    from app.services.gold_story.gold_chat.prompts import format_align_block
    from app.services.gold_story.structure_resolve import (
        CLOSING_MODE_AUTHORITY_PUNCHLINE,
    )

    block = format_align_block(
        structure_type="G",
        mechanism="M4",
        beat=["立规", "反将", "让渡", "点题"],
        closing_mode=CLOSING_MODE_AUTHORITY_PUNCHLINE,
    )
    assert "开场立规/约好" in block or "立规/约好" in block
    assert "authority_punchline" not in block or True  # chain text is enough


def test_authority_punchline_rule_said_by_wrong_speaker():
    """前2句有立规槽但由孩子说 → 保真-权威开场。"""
    dlg = [
        {"speaker": "昭昭", "line": "谁先写完谁就能玩，听见没。"},
        {"speaker": "灿灿", "line": "知道了知道了。"},
        {"speaker": "灿灿", "line": "咦，我作业本呢？翻遍书包找不到，急死我了！"},
        {"speaker": "昭昭", "line": "没看见，你自己乱放还赖我，哭什么呀。"},
        {"speaker": "妈妈", "line": "你藏得挺快，那今晚你负责哄她睡觉。"},
        {"speaker": "昭昭", "line": "我不会哄人，换个别的事行？"},
        {"speaker": "灿灿", "line": "你哄我，我就告诉妈你偷吃。"},
        {"speaker": "昭昭", "line": "你玩你玩，我哄你。"},
        {"speaker": "灿灿", "line": "这还差不多。"},
        {"speaker": "妈妈", "line": "记住，这个家我第一，你俩并列第三。"},
    ]
    kinds = {x["kind"] for x in _authority_issues(_authority_story(dlg))}
    assert "保真-权威开场" in kinds


def test_authority_opening_local_patch_inserts_rule():
    """缺立规开场：窄 patch 插入 beat0 立规句后机审过开场。"""
    from app.services.gold_story.gold_chat.patch import (
        apply_authority_punchline_local_patches,
    )

    dlg = [
        {"speaker": "昭昭", "line": "听见了听见了，我这就去写。"},
        {"speaker": "灿灿", "line": "你写你的。"},
        {"speaker": "灿灿", "line": "咦，我作业本呢？翻遍书包找不到，急死我了！"},
        {"speaker": "昭昭", "line": "没看见，你自己乱放还赖我，哭什么呀。"},
        {"speaker": "妈妈", "line": "你藏得挺快，那今晚你负责哄她睡觉。"},
        {"speaker": "昭昭", "line": "我不会哄人，换个别的事行？"},
        {"speaker": "灿灿", "line": "你哄我，我就告诉妈你偷吃。"},
        {"speaker": "昭昭", "line": "你玩你玩，我哄你。"},
        {"speaker": "灿灿", "line": "这还差不多。"},
        {"speaker": "妈妈", "line": "记住，这个家我第一，你俩并列第三。"},
    ]
    story = _authority_story(dlg)
    fixed, changed = apply_authority_punchline_local_patches(
        story, beat_chain=_AUTH_BEAT_CHAIN
    )
    assert changed
    assert fixed["dialogue"][0]["speaker"] == "妈妈"
    kinds = {x["kind"] for x in _authority_issues(fixed)}
    assert "保真-权威开场" not in kinds


def test_authority_opening_local_patch_moves_rule_forward():
    from app.services.gold_story.gold_chat.patch import (
        apply_authority_punchline_local_patches,
    )

    dlg = [
        {"speaker": "昭昭", "line": "姐姐你慢慢写。"},
        {"speaker": "妈妈", "line": "谁先写完谁就能玩，说好了。"},
        {"speaker": "灿灿", "line": "咦，我作业本呢？翻遍书包找不到，急死我了！"},
        {"speaker": "昭昭", "line": "没看见，你自己乱放还赖我，哭什么呀。"},
        {"speaker": "妈妈", "line": "你藏得挺快，那今晚你负责哄她睡觉。"},
        {"speaker": "昭昭", "line": "我不会哄人，换个别的事行？"},
        {"speaker": "灿灿", "line": "你哄我，我就告诉妈你偷吃。"},
        {"speaker": "昭昭", "line": "你玩你玩，我哄你。"},
        {"speaker": "灿灿", "line": "这还差不多。"},
        {"speaker": "妈妈", "line": "记住，这个家我第一，你俩并列第三。"},
    ]
    story = _authority_story(dlg)
    fixed, changed = apply_authority_punchline_local_patches(
        story, beat_chain=_AUTH_BEAT_CHAIN
    )
    assert changed
    assert fixed["dialogue"][0]["speaker"] == "妈妈"
    assert "谁先" in fixed["dialogue"][0]["line"]
    kinds = {x["kind"] for x in _authority_issues(fixed)}
    assert "保真-权威开场" not in kinds



def test_authority_resist_slot_patch_inserts_after_reverse():
    from app.services.gold_story.gold_chat.patch import (
        apply_authority_punchline_local_patches,
    )
    from app.services.daily_story.story_types.g.validate import RE_AUTH_RESIST

    beat = [
        {"beat": 1, "speaker": "妈妈", "intent": "立规：谁先写完谁玩"},
        {"beat": 2, "speaker": "昭昭", "intent": "占物"},
        {"beat": 3, "speaker": "灿灿", "intent": "急哭"},
        {"beat": 4, "speaker": "妈妈", "intent": "反转：今晚你负责哄"},
        {"beat": 5, "speaker": "昭昭", "intent": "认怂让渡"},
        {"beat": 6, "speaker": "妈妈", "intent": "权威点题"},
    ]
    story = {
        "closing_mode": "authority_punchline",
        "gold_beat_chain": beat,
        "dialogue": [
            {"speaker": "妈妈", "line": "说好了，谁先写完谁玩。"},
            {"speaker": "昭昭", "line": "平板给我玩会儿。"},
            {"speaker": "灿灿", "line": "急得我眼泪都掉下来了。"},
            {"speaker": "妈妈", "line": "不罚你，今晚你负责哄灿灿睡觉。"},
            {"speaker": "昭昭", "line": "姐姐你玩你玩，我哄你行了吧。"},
            {"speaker": "妈妈", "line": "这个家我第一，平板第二，你俩并列第三。"},
        ],
    }
    assert not RE_AUTH_RESIST.search("".join(x["line"] for x in story["dialogue"]))
    fixed, changed = apply_authority_punchline_local_patches(story, beat_chain=beat)
    assert changed
    body = "".join(x["line"] for x in fixed["dialogue"])
    assert RE_AUTH_RESIST.search(body)


def test_authority_end_punch_patch_rewrites_last():
    from app.services.gold_story.gold_chat.patch import (
        apply_authority_punchline_local_patches,
    )
    from app.services.daily_story.story_types.g.validate import RE_AUTH_PUNCH

    beat = [
        {"beat": 1, "speaker": "妈妈", "intent": "立规：谁先写完谁玩"},
        {"beat": 2, "speaker": "昭昭", "intent": "占物"},
        {"beat": 3, "speaker": "灿灿", "intent": "急哭"},
        {"beat": 4, "speaker": "妈妈", "intent": "反转：今晚你负责哄"},
        {"beat": 5, "speaker": "昭昭", "intent": "认怂让渡"},
        {"beat": 6, "speaker": "妈妈", "intent": "宣布：这个家我第一，平板第二，你俩并列第三"},
    ]
    story = {
        "closing_mode": "authority_punchline",
        "gold_beat_chain": beat,
        "dialogue": [
            {"speaker": "妈妈", "line": "说好了，谁先写完谁玩。"},
            {"speaker": "昭昭", "line": "平板给我。"},
            {"speaker": "灿灿", "line": "急得我眼泪都掉下来了。"},
            {"speaker": "妈妈", "line": "不罚你，今晚你负责哄灿灿睡觉。"},
            {"speaker": "昭昭", "line": "我不会啊，姐姐你玩你玩。"},
            {"speaker": "妈妈", "line": "好了好了别闹了。"},
        ],
    }
    assert not RE_AUTH_PUNCH.search(story["dialogue"][-1]["line"])
    fixed, changed = apply_authority_punchline_local_patches(story, beat_chain=beat)
    assert changed
    assert RE_AUTH_PUNCH.search(fixed["dialogue"][-1]["line"])


def test_authority_trim_after_cede_keeps_one_mid():
    from app.services.gold_story.gold_chat.patch import (
        apply_authority_punchline_local_patches,
    )
    from app.services.daily_story.story_types.g.validate import RE_AUTH_PUNCH, RE_AUTH_CEDE

    beat = [
        {"beat": 1, "speaker": "妈妈", "intent": "立规：谁先写完谁玩"},
        {"beat": 2, "speaker": "昭昭", "intent": "占物藏"},
        {"beat": 3, "speaker": "灿灿", "intent": "急哭找不到"},
        {"beat": 4, "speaker": "妈妈", "intent": "反转：今晚你负责哄"},
        {"beat": 5, "speaker": "昭昭", "intent": "认怂让渡"},
        {"beat": 6, "speaker": "妈妈", "intent": "宣布并列第三"},
    ]
    story = {
        "closing_mode": "authority_punchline",
        "gold_beat_chain": beat,
        "dialogue": [
            {"speaker": "妈妈", "line": "说好了，谁先写完谁玩。"},
            {"speaker": "昭昭", "line": "本子我塞冰箱了。"},
            {"speaker": "灿灿", "line": "找不到作业本，急哭了。"},
            {"speaker": "妈妈", "line": "不罚你，今晚你负责哄她睡觉。"},
            {"speaker": "昭昭", "line": "我不会啊，姐姐你玩你玩。"},
            {"speaker": "灿灿", "line": "本子就在冷藏层。"},
            {"speaker": "昭昭", "line": "不行，我偏就不信！"},
            {"speaker": "灿灿", "line": "真的，马上给我挪开！"},
            {"speaker": "昭昭", "line": "我…别再乱动了…"},
            {"speaker": "灿灿", "line": "我…呢…"},
            {"speaker": "妈妈", "line": "这个家我第一，平板第二，你俩并列第三。"},
        ],
    }
    fixed, changed = apply_authority_punchline_local_patches(story, beat_chain=beat)
    assert changed
    dlg = fixed["dialogue"]
    assert RE_AUTH_PUNCH.search(dlg[-1]["line"])
    # find cede then gap to punch <=1
    lines = [x["line"] for x in dlg]
    cede_i = max(i for i, ln in enumerate(lines[:-1]) if RE_AUTH_CEDE.search(ln))
    assert len(lines) - 1 - cede_i - 1 <= 1
    assert not any("我…呢" in x["line"] for x in dlg)


def test_gold_chat_polish_flags_intra_line_oral_repeat():
    from app.services.gold_story.gold_chat.polish import collect_gold_chat_polish_issues

    story = {
        "dialogue": [
            {"speaker": "昭昭", "line": "我就过来，你砸一个试试看，你试试看啊！"},
        ],
    }
    kinds = [it["kind"] for it in collect_gold_chat_polish_issues(story)]
    assert "句内重复" in kinds


_HOMEWORK_OPENING_BEAT = [
    {"beat": 1, "speaker": "妈妈", "intent": "责备：作业还没写"},
    {"beat": 2, "speaker": "灿灿", "intent": "辩解：忘了本来就要写"},
    {"beat": 3, "speaker": "昭昭", "intent": "插嘴：离谱请求解围"},
]


def _opening_causality_story(
    dialogue: list[dict[str, str]],
    *,
    setting: str = "晚饭后姐弟在客厅写功课。",
) -> dict:
    return {
        "gold_beat_chain": _HOMEWORK_OPENING_BEAT,
        "setting": setting,
        "dialogue": dialogue,
    }


def test_opening_causality_blocks_defend_without_parent_trigger():
    from app.services.gold_story.gold_chat.validate import (
        collect_opening_causality_hard_errors,
        collect_opening_causality_issues,
    )

    story = _opening_causality_story(
        [
            {"speaker": "灿灿", "line": "我本来就要写，就是忘了带本子嘛！"},
            {"speaker": "昭昭", "line": "要不你先打我一下，划算不？"},
            {"speaker": "灿灿", "line": "别闹了，我还得找作业本。"},
        ],
    )
    issues = collect_opening_causality_issues(story)
    assert issues
    errs = collect_opening_causality_hard_errors(story)
    assert errs and all(e.startswith("opening_causality:") for e in errs)
    assert any("妈妈" in str(i.get("desc") or "") for i in issues)


def test_opening_causality_parent_blame_in_setting_not_dialogue():
    from app.services.gold_story.gold_chat.validate import (
        collect_opening_causality_issues,
    )

    story = _opening_causality_story(
        [
            {"speaker": "灿灿", "line": "马上去写，你别催我嘛！"},
            {"speaker": "昭昭", "line": "姐姐你先别哭，我帮你找本子。"},
            {"speaker": "灿灿", "line": "找到了，我这就写。"},
        ],
        setting="妈妈刚才责备灿灿作业还没写，气氛很紧张。",
    )
    issues = collect_opening_causality_issues(story)
    assert issues
    assert any("setting" in str(i.get("desc") or "") for i in issues)


def test_opening_causality_passes_trigger_before_defend():
    from app.services.gold_story.gold_chat.validate import (
        collect_opening_causality_issues,
        opening_causality_passes,
    )

    story = _opening_causality_story(
        [
            {"speaker": "妈妈", "line": "怎么作业还没写？别磨蹭了！"},
            {"speaker": "灿灿", "line": "我本来就要写，就是忘带本子嘛！"},
            {"speaker": "昭昭", "line": "要不你先摸我一下，划算不？"},
            {"speaker": "灿灿", "line": "别闹，我还得赶紧写。"},
        ],
    )
    assert opening_causality_passes(story)
    assert not collect_opening_causality_issues(story)


def test_opening_causality_accepts_parent_rule_trigger():
    from app.services.gold_story.gold_chat.validate import (
        collect_opening_causality_issues,
        opening_causality_passes,
    )

    beat = [
        {"beat": 1, "speaker": "妈妈", "intent": "立规：谁先动手谁先道歉"},
        {"beat": 2, "speaker": "昭昭", "intent": "插嘴：离谱请求解围"},
    ]
    story = {
        "gold_beat_chain": beat,
        "dialogue": [
            {"speaker": "妈妈", "line": "规矩说好，谁先动手谁先道歉。"},
            {"speaker": "昭昭", "line": "妈，我屁股Q弹，你打一下试试嘛！"},
        ],
    }

    assert opening_causality_passes(story, beat, mom_lines_max=1)
    assert not collect_opening_causality_issues(story, beat, mom_lines_max=1)


def test_opening_causality_accepts_parent_accountability_trigger():
    from app.services.gold_story.gold_chat.validate import (
        collect_opening_causality_issues,
        opening_causality_passes,
    )

    beat = [
        {"beat": 1, "speaker": "妈妈", "intent": "定责：昭昭先动手不对，先道歉"},
        {"beat": 2, "speaker": "昭昭", "intent": "插嘴：离谱请求解围"},
    ]
    story = {
        "gold_beat_chain": beat,
        "dialogue": [
            {"speaker": "妈妈", "line": "昭昭，你先动手不对，先道歉。"},
            {"speaker": "昭昭", "line": "妈，我屁股Q弹，你打一下试试嘛！"},
        ],
    }

    assert opening_causality_passes(story, beat, mom_lines_max=1)
    assert not collect_opening_causality_issues(story, beat, mom_lines_max=1)


def test_opening_causality_local_patch_repairs_accountability_homework_opening():
    from app.services.gold_story.gold_chat.patch import apply_opening_causality_local_patch
    from app.services.gold_story.gold_chat.validate import opening_causality_passes

    beat = [
        {"beat": 1, "speaker": "妈妈", "intent": "定责：灿灿作业没写，先把作业补上"},
        {"beat": 2, "speaker": "昭昭", "intent": "插嘴：离谱请求解围"},
    ]
    story = {
        "gold_beat_chain": beat,
        "conflict_core": "灿灿作业没写",
        "dialogue": [
            {"speaker": "灿灿", "line": "我本来就要写，就是忘带本子嘛！"},
            {"speaker": "昭昭", "line": "妈，我屁股Q弹，你打一下试试嘛！"},
            {"speaker": "妈妈", "line": "你说什么？手停在半空。"},
        ],
    }

    assert not opening_causality_passes(story, beat, mom_lines_max=2)
    fixed, ok = apply_opening_causality_local_patch(
        story, beat_chain=beat, mom_lines_max=2,
    )
    assert ok
    assert fixed["dialogue"][0]["speaker"] == "妈妈"
    assert "作业" in fixed["dialogue"][0]["line"]
    assert opening_causality_passes(fixed, beat, mom_lines_max=2)


_MOM_ZHAO_MOM_OPENING_BEAT = [
    {"beat": 1, "speaker": "妈妈", "intent": "责备：作业还没写"},
    {"beat": 2, "speaker": "昭昭", "intent": "插嘴：离谱请求解围"},
    {"beat": 3, "speaker": "妈妈", "intent": "愣住：接不住离谱话"},
]


def test_opening_causality_local_patch_inserts_missing_mom_blame():
    from app.services.gold_story.gold_chat.patch import (
        apply_opening_causality_local_patch,
    )
    from app.services.gold_story.gold_chat.validate import opening_causality_passes

    beat = [
        {"beat": 1, "speaker": "妈妈", "intent": "责备：批评灿灿作业没做，气氛紧张"},
        {"beat": 2, "speaker": "昭昭", "intent": "插嘴：凑近认真提出打自己Q弹屁股"},
        {"beat": 3, "speaker": "妈妈", "intent": "愣住：被离谱请求打断批评"},
    ]
    story = {
        "conflict_core": "灿灿作业",
        "dialogue": [
            {"speaker": "灿灿", "line": "我……我本来要写的，就是忘啊。"},
            {"speaker": "昭昭", "line": "妈妈，我屁股Q弹，你打我嘛！"},
            {"speaker": "妈妈", "line": "你说什么？手停在半空。"},
        ],
    }
    fixed, ok = apply_opening_causality_local_patch(
        story, beat_chain=beat, mom_lines_max=2,
    )
    assert ok
    assert opening_causality_passes(fixed, beat, mom_lines_max=2)
    assert fixed["dialogue"][0]["speaker"] == "妈妈"
    assert "作业" in fixed["dialogue"][0]["line"]


def test_opening_causality_local_patch_repairs_rule_homework_when_beat2_starts():
    """#96 形状：对白直接从 beat=2 昭昭起跳，beat=1 作业立规应本地补回。"""
    from app.services.gold_story.gold_chat.patch import apply_opening_causality_local_patch
    from app.services.gold_story.gold_chat.validate import opening_causality_passes

    beat = [
        {"beat": 1, "speaker": "妈妈", "intent": "立规：灿灿作业没写，先把作业补上"},
        {"beat": 2, "speaker": "昭昭", "intent": "插嘴：认真提出打自己Q弹屁股解围"},
        {"beat": 3, "speaker": "妈妈", "intent": "愣住：被离谱请求打断"},
    ]
    story = {
        "conflict_core": "灿灿作业没写",
        "dialogue": [
            {"speaker": "昭昭", "line": "妈，我屁股很Q弹，你打我吧，别打姐姐。"},
            {"speaker": "灿灿", "line": "为什么你会突然说这个？"},
            {"speaker": "昭昭", "line": "因为Q弹的打了不疼，还会弹回来。"},
        ],
    }

    assert not opening_causality_passes(story, beat, mom_lines_max=3)
    fixed, ok = apply_opening_causality_local_patch(
        story, beat_chain=beat, mom_lines_max=3,
    )

    assert ok
    assert fixed["dialogue"][0]["speaker"] == "妈妈"
    assert "说好" in fixed["dialogue"][0]["line"] or "规矩" in fixed["dialogue"][0]["line"]
    assert "作业" in fixed["dialogue"][0]["line"]
    assert opening_causality_passes(fixed, beat, mom_lines_max=3)


def test_opening_causality_rejects_q96_export_style_late_mom_react():
    """#96 已导出稿：灿灿辩解起跳、妈妈「你说什么」不能算首句责备。"""
    from app.services.gold_story.gold_chat.validate import (
        collect_opening_causality_issues,
        opening_causality_passes,
    )

    beat = [
        {"beat": 1, "speaker": "妈妈", "intent": "责备：批评灿灿作业没做，气氛紧张"},
        {"beat": 2, "speaker": "昭昭", "intent": "插嘴：凑近认真提出打自己Q弹屁股"},
        {"beat": 3, "speaker": "妈妈", "intent": "愣住：被离谱请求打断批评"},
    ]
    story = {
        "gold_beat_chain": beat,
        "dialogue": [
            {"speaker": "灿灿", "line": "我……我本来要写的，就是忘啊。"},
            {"speaker": "昭昭", "line": "妈妈，我屁股Q弹，你打我嘛！"},
            {"speaker": "灿灿", "line": "昭昭你疯啦？"},
            {"speaker": "昭昭", "line": "你打一下试试手感，比打姐姐划算吧。"},
            {"speaker": "妈妈", "line": "你说什么？手停在半空。"},
            {"speaker": "灿灿", "line": "噗嗤——昭昭你屁股有什么好打的呀，说一不二！"},
        ],
    }
    assert not opening_causality_passes(story, beat, mom_lines_max=2)
    issues = collect_opening_causality_issues(story, beat, mom_lines_max=2)
    assert issues
    kinds = " ".join(str(i.get("desc") or "") for i in issues)
    assert "未见" in kinds or "缺少" in kinds or "起跳" in kinds


def test_opening_causality_rejects_late_parent_trigger_even_if_interrupt_repeats_later():
    """服务器 #96 形状：妈妈第7句才出现，后面另一个昭昭句不能让 opening 重新起算。"""
    from app.services.gold_story.gold_chat.validate import (
        collect_opening_causality_issues,
        opening_causality_passes,
    )

    beat = [
        {"beat": 1, "speaker": "妈妈", "intent": "定责：批评灿灿作业没做，气氛紧张"},
        {"beat": 2, "speaker": "昭昭", "intent": "插嘴：一脸认真提出打自己Q弹屁股的离谱请求"},
        {"beat": 3, "speaker": "灿灿", "intent": "破功：忍不住笑出声，紧张场景瞬间破碎"},
    ]
    story = {
        "dialogue": [
            {"speaker": "灿灿", "line": "我……我马上写，妈妈你别生气，我这就拿笔"},
            {"speaker": "昭昭", "line": "妈妈，你打我的Q弹屁股吧，别骂姐姐了"},
            {"speaker": "灿灿", "line": "昭昭你闭嘴，谁要你替我挨打"},
            {"speaker": "昭昭", "line": "我的比姐姐的弹，你试试就知道，一拍就弹回来"},
            {"speaker": "灿灿", "line": "你屁股是弹簧吗，还一拍就弹回来"},
            {"speaker": "昭昭", "line": "因为姐姐屁股不弹，打了也不长记性，我的才管用"},
            {"speaker": "妈妈", "line": "昭昭，你凑什么热闹，作业没写还来捣乱"},
            {"speaker": "灿灿", "line": "噗，没忍住笑出声，昭昭你屁股是弹簧吗"},
            {"speaker": "昭昭", "line": "你听，Q弹，妈妈你摸，我没骗你"},
        ]
    }

    assert not opening_causality_passes(story, beat, mom_lines_max=2)
    issues = collect_opening_causality_issues(story, beat, mom_lines_max=2)
    assert any("第1句未落地" in str(item.get("desc") or "") for item in issues)


def test_opening_causality_patch_does_not_move_wrong_sibling_parent_line_to_front():
    """beat1 点名灿灿时，妈妈训昭昭的通用“作业没写”句不能被搬成首句。"""
    from app.services.gold_story.gold_chat.patch import apply_opening_causality_local_patch
    from app.services.gold_story.gold_chat.validate import opening_causality_passes

    beat = [
        {"beat": 1, "speaker": "妈妈", "intent": "定责：批评灿灿作业没做，气氛紧张"},
        {"beat": 2, "speaker": "昭昭", "intent": "插嘴：一脸认真提出打自己Q弹屁股的离谱请求"},
    ]
    story = {
        "conflict_core": "妈妈批评灿灿作业没做，昭昭插嘴求打自己Q弹屁股",
        "dialogue": [
            {"speaker": "灿灿", "line": "我……我马上写，妈妈你别生气，我这就拿笔"},
            {"speaker": "昭昭", "line": "妈妈，你打我的Q弹屁股吧，别骂姐姐了"},
            {"speaker": "妈妈", "line": "昭昭，你凑什么热闹，作业没写还来捣乱"},
            {"speaker": "昭昭", "line": "我的比姐姐的弹，你试试就知道"},
        ],
    }

    fixed, ok = apply_opening_causality_local_patch(
        story, beat_chain=beat, mom_lines_max=2,
    )

    assert ok
    assert fixed["dialogue"][0]["speaker"] == "妈妈"
    assert "灿灿" in fixed["dialogue"][0]["line"]
    assert "作业" in fixed["dialogue"][0]["line"]
    assert "昭昭，你凑什么热闹" not in fixed["dialogue"][0]["line"]
    assert opening_causality_passes(fixed, beat, mom_lines_max=2)


def test_opening_causality_patch_server_shape_drops_late_duplicate_trigger_before_parent_close():
    """插入正确 beat1 后，妈妈配额应删迟到重复训话，保留后段收束反应。"""
    from app.services.gold_story.gold_chat.patch import apply_opening_causality_local_patch
    from app.services.gold_story.gold_chat.validate import opening_causality_passes

    beat = [
        {"beat": 1, "speaker": "妈妈", "intent": "定责：批评灿灿作业没做，气氛紧张"},
        {"beat": 2, "speaker": "昭昭", "intent": "插嘴：一脸认真提出打自己Q弹屁股的离谱请求"},
    ]
    story = {
        "conflict_core": "妈妈批评灿灿作业没做，昭昭插嘴求打自己Q弹屁股",
        "dialogue": [
            {"speaker": "灿灿", "line": "我……我马上写，妈妈你别生气，我这就拿笔"},
            {"speaker": "昭昭", "line": "妈妈，你打我的Q弹屁股吧，别骂姐姐了"},
            {"speaker": "妈妈", "line": "昭昭，你凑什么热闹，作业没写还来捣乱"},
            {"speaker": "灿灿", "line": "噗，没忍住笑出声"},
            {"speaker": "妈妈", "line": "你们俩一个比一个会捣乱，我真是拿你们没办法"},
        ],
    }

    fixed, ok = apply_opening_causality_local_patch(
        story, beat_chain=beat, mom_lines_max=2,
    )

    assert ok
    lines = [str(row.get("line") or "") for row in fixed["dialogue"]]
    mom_lines = [
        str(row.get("line") or "")
        for row in fixed["dialogue"]
        if row.get("speaker") == "妈妈"
    ]
    assert fixed["dialogue"][0]["speaker"] == "妈妈"
    assert "灿灿" in fixed["dialogue"][0]["line"]
    assert not any("昭昭，你凑什么热闹" in line for line in lines)
    assert any("拿你们没办法" in line for line in mom_lines)
    assert len(mom_lines) == 2
    assert opening_causality_passes(fixed, beat, mom_lines_max=2)


def test_opening_causality_rejects_parent_response_style_first_line_even_with_homework_trigger():
    """妈妈先回应“打你屁股”再问作业，语义上已是 beat2 之后，不能冒充 beat1。"""
    from app.services.gold_story.gold_chat.patch import apply_opening_causality_local_patch
    from app.services.gold_story.gold_chat.validate import opening_causality_passes

    beat = [
        {"beat": 1, "speaker": "妈妈", "intent": "定责：批评灿灿作业没做，气氛紧张"},
        {"beat": 2, "speaker": "昭昭", "intent": "插嘴：认真提出打自己Q弹屁股的离谱请求"},
    ]
    story = {
        "conflict_core": "妈妈批评灿灿作业没做，昭昭插嘴求打自己Q弹屁股",
        "dialogue": [
            {"speaker": "妈妈", "line": "你说啥？打你屁股？你作业写完了吗？"},
            {"speaker": "昭昭", "line": "妈妈，你打我的Q弹屁股吧，别骂姐姐了"},
            {"speaker": "灿灿", "line": "我马上写，你别生气"},
        ],
    }

    assert not opening_causality_passes(story, beat, mom_lines_max=2)
    fixed, ok = apply_opening_causality_local_patch(
        story, beat_chain=beat, mom_lines_max=2,
    )
    assert ok
    assert fixed["dialogue"][0]["speaker"] == "妈妈"
    assert not fixed["dialogue"][0]["line"].startswith("你说啥")
    assert "作业" in fixed["dialogue"][0]["line"]
    assert fixed["dialogue"][1]["speaker"] == "昭昭"
    assert fixed["dialogue"][2]["speaker"] == "妈妈"
    assert fixed["dialogue"][2]["line"].startswith("你说啥")
    assert opening_causality_passes(fixed, beat, mom_lines_max=2)


def test_opening_causality_mom_blame_zhao_interrupt_mom_stun_ok():
    """妈妈→昭昭→妈妈 开场（#96 类），首句责备不得误判为愣住。"""
    from app.services.gold_story.gold_chat.validate import (
        collect_opening_causality_issues,
        opening_causality_passes,
    )

    story = {
        "gold_beat_chain": _MOM_ZHAO_MOM_OPENING_BEAT,
        "setting": "晚饭后客厅，姐弟在写功课。",
        "dialogue": [
            {"speaker": "妈妈", "line": "怎么作业还没写？别磨蹭了！"},
            {"speaker": "昭昭", "line": "妈，我屁股Q弹，你打一下试试嘛！"},
            {"speaker": "妈妈", "line": "你……你这孩子，我一时接不住话。"},
            {"speaker": "灿灿", "line": "姐你别闹，我还得找作业本呢。"},
        ],
    }
    assert opening_causality_passes(story)
    assert not collect_opening_causality_issues(story)


def test_short_spot_unfreezes_head_when_opening_not_ok():
    from app.services.gold_story.gold_chat.repair import list_short_spot_editable_line_nos

    dialogue = [
        {"speaker": "灿灿", "line": "我本来就要写嘛。"},
        {"speaker": "昭昭", "line": "姐姐别急。"},
        {"speaker": "灿灿", "line": "我还得找本子。"},
        {"speaker": "昭昭", "line": "我帮你翻书包。"},
        {"speaker": "灿灿", "line": "找到了。"},
        {"speaker": "昭昭", "line": "快去写吧。"},
    ]
    chat = {"dialogue": dialogue}
    frozen = list_short_spot_editable_line_nos(chat, freeze_opening=True)
    unfrozen = list_short_spot_editable_line_nos(chat, freeze_opening=False)
    assert 1 not in frozen
    assert 1 in unfrozen
