"""gold_chat 保真机审与 Pass 2 精修测试。"""

from __future__ import annotations

import pytest

from app.services.daily_story.gold_story import gold_chat_convert as gc
from app.services.daily_story.gold_story.gold_chat_fidelity import collect_fidelity_issues


def _m5h_dialogue_v1() -> list[dict[str, str]]:
    """#5 LLM 首稿（评审前）：互毁前文/M5/定责有缺口。"""
    return [
        {"speaker": "灿灿", "line": "昭昭，你趴地上画啥呢？让我瞅瞅！"},
        {"speaker": "昭昭", "line": "不行！这是我的秘密，你不能看！"},
        {"speaker": "灿灿", "line": "哼，小气鬼！我偏要看！"},
        {"speaker": "昭昭", "line": "你走开！再抢我打你了！"},
        {"speaker": "灿灿", "line": "你敢！哎呀！你推我！"},
        {"speaker": "昭昭", "line": "谁让你抢的！我也弄坏你的画！"},
        {"speaker": "灿灿", "line": "你赔！我额头都蹭破了！"},
        {"speaker": "昭昭", "line": "呜……对不起嘛，我不是故意的。"},
        {"speaker": "灿灿", "line": "谁先动手谁道歉！哼，我不原谅！"},
        {"speaker": "昭昭", "line": "姐姐，我真的错了，你别不理我。"},
        {"speaker": "灿灿", "line": "道歉也没用！我画了好久呢！"},
        {"speaker": "妈妈", "line": "别打了！谁先动手的？"},
        {"speaker": "昭昭", "line": "我……我先推的，姐姐对不起！"},
        {"speaker": "妈妈", "line": "灿灿，弟弟都道歉了，你画坏了可以再画，额头破了得先处理。"},
        {"speaker": "灿灿", "line": "哼……那拉手吧。"},
        {"speaker": "妈妈", "line": "以后还打不打架？"},
        {"speaker": "昭昭", "line": "不打了！"},
        {"speaker": "灿灿", "line": "不打了！这还差不多。"},
        {"speaker": "妈妈", "line": "我去拿碘伏，你额头上还没涂呢。"},
        {"speaker": "灿灿", "line": "嗯，谢谢妈妈。"},
    ]


def _m5h_dialogue_v2() -> list[dict[str, str]]:
    """#5 修稿：机审应通过。"""
    return [
        {"speaker": "灿灿", "line": "昭昭，你趴地上画啥呢？让我瞅瞅！"},
        {"speaker": "昭昭", "line": "不行！这是我的秘密，你不能看！"},
        {"speaker": "灿灿", "line": "哼，小气鬼！我偏要看！"},
        {"speaker": "昭昭", "line": "你走开！你把我画抢坏了！再抢我打你了！"},
        {"speaker": "灿灿", "line": "你敢！哎呀！你推我！"},
        {"speaker": "昭昭", "line": "谁让你抢的！我也弄坏你的画！"},
        {"speaker": "灿灿", "line": "你赔！我额头都蹭破了！"},
        {"speaker": "昭昭", "line": "呜……对不起嘛，我不是故意的。"},
        {"speaker": "灿灿", "line": "家规就是谁先动手谁道歉！你推我，你先道歉！哼，我不原谅！"},
        {"speaker": "昭昭", "line": "姐姐，我真的错了，你别不理我。"},
        {"speaker": "灿灿", "line": "道歉也没用！我画了好久呢！"},
        {"speaker": "妈妈", "line": "别打了！谁先动手的？"},
        {"speaker": "昭昭", "line": "我……我先推的，姐姐对不起！"},
        {"speaker": "妈妈", "line": "昭昭先推不对，灿灿你也别抢画。画能重画，额头先处理。"},
        {"speaker": "灿灿", "line": "哼……那拉手吧。"},
        {"speaker": "妈妈", "line": "以后还打不打架？"},
        {"speaker": "昭昭", "line": "不打了！"},
        {"speaker": "灿灿", "line": "不打了！这还差不多。"},
        {"speaker": "妈妈", "line": "我去拿碘伏，你额头上还没涂呢。"},
        {"speaker": "灿灿", "line": "嗯，谢谢妈妈。"},
    ]


def _m5h_story(dialogue: list[dict[str, str]]) -> dict:
    return {
        "scene_title": "画作争夺战",
        "setting": "客厅，地上散落画纸和彩笔",
        "key": "互毁画作",
        "conflict_core": "灿灿抢看昭昭秘密画互毁扭打，妈妈调解。",
        "dialogue": dialogue,
        "punchline_explain": "H类第三方化解，妈妈定责劝和",
    }


def test_collect_fidelity_issues_m5h_first_draft():
    issues = collect_fidelity_issues(
        _m5h_story(_m5h_dialogue_v1()),
        structure_type="H",
        mechanism="M5",
    )
    kinds = {str(x.get("kind") or "") for x in issues}
    assert "保真-互毁前文" in kinds
    assert "保真-M5立规" in kinds
    assert "保真-H定责" in kinds
    mutual = next(x for x in issues if x["kind"] == "保真-互毁前文")
    assert mutual["lines"] == [4]


def test_collect_fidelity_issues_m5h_merged_line_passes():
    """LLM 常把前文合并进「也弄坏」同句 — 机审应认可。"""
    dlg = list(_m5h_dialogue_v1())
    dlg[5] = {
        "speaker": "昭昭",
        "line": "你把我画抢坏了！我也弄坏你的画！",
    }
    issues = collect_fidelity_issues(
        _m5h_story(dlg),
        structure_type="H",
        mechanism="M5",
    )
    kinds = {str(x.get("kind") or "") for x in issues}
    assert "保真-互毁前文" not in kinds


def test_collect_fidelity_issues_m5h_fixed_passes():
    issues = collect_fidelity_issues(
        _m5h_story(_m5h_dialogue_v2()),
        structure_type="H",
        mechanism="M5",
    )
    assert issues == []


def test_refine_gold_chat_fidelity_applies_spot_fixes(monkeypatch):
    story = _m5h_story(_m5h_dialogue_v1())
    fidelity_block = "【checklist】"

    def fake_refine(_story, issues, **_kw):
        assert issues
        fixes = []
        for item in issues:
            if item["kind"] == "保真-互毁前文":
                fixes.append({"no": 4, "line": "你走开！你把我画抢坏了！再抢我打你了！"})
            elif item["kind"] == "保真-M5立规":
                fixes.append(
                    {
                        "no": 9,
                        "line": "家规就是谁先动手谁道歉！你推我，你先道歉！哼，我不原谅！",
                    }
                )
            elif item["kind"] == "保真-H定责":
                fixes.append(
                    {
                        "no": 14,
                        "line": "昭昭先推不对，灿灿你也别抢画。画能重画，额头先处理。",
                    }
                )
        return {"fixes": fixes}

    monkeypatch.setattr(gc, "_fidelity_refine_with_llm", fake_refine)
    out = gc.refine_gold_chat_fidelity(
        story,
        structure_type="H",
        mechanism="M5",
        fidelity_block=fidelity_block,
        mom_lines_max=4,
    )
    assert out["dialogue"][3]["line"].startswith("你走开！你把我画抢坏了")
    assert "家规就是" in out["dialogue"][8]["line"]
    assert "别抢画" in out["dialogue"][13]["line"]
    gc.validate_gold_chat(out, mom_lines_max=4)


def test_refine_gold_chat_fidelity_accepts_merged_retaliation_line(monkeypatch):
    """LLM 若仍合并同句，机审应放行，不因互毁前文卡死。"""
    story = _m5h_story(_m5h_dialogue_v1())

    def fake_refine(_story, issues, **_kw):
        return {
            "fixes": [
                {"no": 6, "line": "你把我画抢坏了！我也弄坏你的画！"},
                {"no": 9, "line": "家规就是谁先动手谁道歉！哼，我不原谅！"},
                {
                    "no": 14,
                    "line": "昭昭先推不对，灿灿你也别抢画。画能重画，额头先处理。",
                },
            ]
        }

    monkeypatch.setattr(gc, "_fidelity_refine_with_llm", fake_refine)
    out = gc.refine_gold_chat_fidelity(
        story,
        structure_type="H",
        mechanism="M5",
        fidelity_block="",
        mom_lines_max=4,
    )
    assert "抢坏了" in out["dialogue"][5]["line"]
    assert collect_fidelity_issues(out, structure_type="H", mechanism="M5") == []


def test_refine_gold_chat_fidelity_fails_when_llm_noop(monkeypatch):
    story = _m5h_story(_m5h_dialogue_v1())

    def fake_refine(_story, _issues, **_kw):
        return {"fixes": []}

    monkeypatch.setattr(gc, "_fidelity_refine_with_llm", fake_refine)
    with pytest.raises(ValueError, match="fidelity_refine_failed"):
        gc.refine_gold_chat_fidelity(
            story,
            structure_type="H",
            mechanism="M5",
            fidelity_block="",
            mom_lines_max=4,
            max_rounds=1,
        )


def test_gold_story_to_gold_chat_runs_fidelity_pass(monkeypatch):
    """M5+H 首稿 hard 过、保真不过 → Pass 2 精修后返回。"""

    def fake_chat(system: str, _user: str) -> dict:
        if "保真精修" in system:
            return {
                "fixes": [
                    {"no": 4, "line": "你走开！你把我画抢坏了！再抢我打你了！"},
                    {
                        "no": 9,
                        "line": "家规就是谁先动手谁道歉！你推我，你先道歉！哼，我不原谅！",
                    },
                    {
                        "no": 14,
                        "line": "昭昭先推不对，灿灿你也别抢画。画能重画，额头先处理。",
                    },
                ]
            }
        return _m5h_story(_m5h_dialogue_v1())

    row = {
        "id": 5,
        "title": "双胞胎画画互毁",
        "mechanism": "M5",
        "structure_type": "H",
        "conflict_core": "互毁扭打妈妈调解",
        "story_raw": "哥哥画画弟弟捣乱互毁" * 10,
        "payload": {
            "beat": ["互毁", "妈妈调解", "和好"],
            "dialogue_seed": [{"speaker": "妈妈", "intent": "谁先动手"}],
            "closing_intent": "拉手和好",
            "scene_contract": {"mom_lines_max": 4, "story_type": "H"},
        },
    }
    monkeypatch.setattr(gc, "_chat_json", fake_chat)
    out = gc.gold_story_to_gold_chat(row)
    assert "家规就是" in out["dialogue"][8]["line"]
    assert collect_fidelity_issues(out, structure_type="H", mechanism="M5") == []
