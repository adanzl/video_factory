"""有时间表LLM测试，输出保存到 data/debug/"""
from __future__ import annotations
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.script.board import build_material_script_prompts
from app.services.script.board_timeline import _max_chars_for_duration, slot_min_chars
from app.services.llm.llm_deepseek import DeepSeekClient

DEBUG = Path(__file__).resolve().parents[2] / "data" / "debug"
DEBUG.mkdir(parents=True, exist_ok=True)

TIMELINE = {"title":"美国建国250周年无人机庆典","duration_sec":189.0,"scenes":[
  {"index":1,"scene":"序幕 — 星条旗永不落","description":"无人机编队升空，形成大型星条旗图案，动态飘扬效果，烟花散开重组，最终组成\"250\"字样","start_sec":0,"end_sec":40,"duration_sec":40},
  {"index":2,"scene":"致敬国父与山姆大叔","description":"乔治·华盛顿肖像无人机编队，精细侧面像；山姆大叔经典\"I want you\"招贴画造型","start_sec":40,"end_sec":60,"duration_sec":20},
  {"index":3,"scene":"二战荣光 — 飞虎队与珍珠港","description":"P-40战斧战斗机鲨鱼嘴涂装出现，多机编队飞行，珍珠港场景再现，纪念二战中美合作","start_sec":60,"end_sec":85,"duration_sec":25},
  {"index":4,"scene":"太空辉煌 — 从土星5号到SLS","description":"土星5号火箭升空，尾焰细节；SLS新一代重型火箭；小女孩仰望火箭画面；火箭发射烟火融合","start_sec":85,"end_sec":120,"duration_sec":35},
  {"index":5,"scene":"阿波罗与阿尔忒弥斯 — 人类登月之路","description":"阿波罗飞船月球轨道，宇航员月球行走，地球升起经典画面，新老航天员同框，阿尔忒弥斯计划标识，月球基地概念图","start_sec":120,"end_sec":150,"duration_sec":30},
  {"index":6,"scene":"自由之鹰 — 白头海雕","description":"白头海雕展翅，头部特写，翱翔天空，目光锐利，美国国鸟国家象征","start_sec":150,"end_sec":170,"duration_sec":20},
  {"index":7,"scene":"致敬与终章 — 三千次致敬","description":"\"THANK YOU 3000\"字样，万国旗帜，星条旗再次升起，USA字样编队","start_sec":170,"end_sec":189,"duration_sec":19}]}
TL = json.dumps(TIMELINE, ensure_ascii=False)

title = "美国建国250周年庆典无人机表演"
cps = 4.1

for opening in [False, True]:
    tag = "need_opening" if opening else "no_opening"
    p = build_material_script_prompts(title, video_timeline=TL, max_title_length=16, narration_target_words=785, chars_per_sec=cps, need_opening=opening)
    data, fin = DeepSeekClient()._chat_json(p["system"], p["user"])
    lines = [f"=== {tag} ==="]
    lines.append("--- SYSTEM ---"); lines.append(p["system"])
    lines.append("--- USER ---"); lines.append(p["user"])
    lines.append("--- OUTPUT ---"); lines.append(json.dumps(data, ensure_ascii=False, indent=2))
    lines.append(f"finish_reason: {fin}")
    lines.append("--- CHECK ---")
    for s in (data.get("segments") or []):
        idx, t = s["segment_index"], (s.get("text", "") or "")
        d = next(x["duration_sec"] for x in TIMELINE["scenes"] if x["index"] == idx)
        mc = _max_chars_for_duration(d, cps)
        mn = slot_min_chars(mc)
        ok = "✅" if mn <= len(t) <= mc else ("❌" if len(t) < mn else "❌")
        lines.append(f"  seg[{idx}] {len(t)}字 预算{mn}-{mc} {ok}")
    lines.append("")
    (DEBUG / f"job28_{tag}.txt").write_text("\n".join(lines), encoding="utf-8")
    print(f"  {tag}: {len(data.get('segments') or [])}段, narration {len((data.get('narration') or '') or '')}字")

print(f"\n已保存到 {DEBUG}/")
