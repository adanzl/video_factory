"""金故事 H4 入库 CLI。

用法:
  cd backend
  conda run -n flask_env python -m scripts.gold_story_import --seed-samples
  conda run -n flask_env python -m scripts.gold_story_import --seed-samples --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core import create_app
from app.repositories import repo_gold_story

# 专家对话 §17.10 沉淀的三条站外名场面（手工结构化，试跑入库）
_SEED_SAMPLES: list[dict[str, Any]] = [
    {
        "source": "bili",
        "source_id": "seed_m2_jiangwan",
        "url": "https://www.bilibili.com/video/seed_m2_jiangwan",
        "title": "抢酱碗·歪理自洽",
        "mechanism": "M2",
        "structure_type": "C",
        "theme_family": "占有",
        "conflict_core": "妹妹独占酱碗不让哥哥吃，被质问后用歪理自洽",
        "engagement_norm": 0.75,
        "story_raw": (
            "有个妹妹霸占着酱碗不让哥哥吃。妈妈问为什么，"
            "妹妹声嘶力竭地说：哥哥刚才吃了太多，所以现在自己要多吃一些。"
            "被戳穿后仍嘴硬，不肯让步。"
        ),
        "payload": {
            "perspective": "third_person",
            "funny_why": "把自私包装成公平规则，被质问仍自洽",
            "beat": ["独占不让", "被质问", "歪理自洽", "嘴硬不收"],
            "banned_literals": ["酱碗", "妹妹", "哥哥"],
            "dialogue_seed": [
                {"speaker": "灿灿", "intent": "宣布占有物并立歪规"},
                {"speaker": "昭昭", "intent": "质疑规则不公平"},
                {"speaker": "灿灿", "intent": "用歪理把多吃说成公平"},
            ],
            "closing_intent": "C 类占有战回旋镖 + 末句嘴硬",
            "speaker_map_note": "站外兄妹 → 昭昭/灿灿；占有方映射灿灿",
            "extract_confidence": 0.82,
            "structure_confidence": 0.85,
            "dialogue_confidence": 0.78,
        },
    },
    {
        "source": "bili",
        "source_id": "seed_m4_ditai",
        "url": "https://www.bilibili.com/video/seed_m4_ditai",
        "title": "萌娃吵架·递台词",
        "mechanism": "M4",
        "structure_type": "G",
        "theme_family": "结盟",
        "conflict_core": "吵架一方卡壳，另一方主动教递台词升级威胁",
        "engagement_norm": 0.8,
        "story_raw": (
            "两个三四岁的孩子吵架。男孩威胁不给糖，女孩回说不给糖就不让吃饼干，"
            "男孩又威胁不让玩机器人。女孩卡壳后，男孩凑过来教她："
            "「你就不让我看你家电视啊！」女孩恍然大悟，怒道："
            "「对，我就不让你看我家电视！！」"
        ),
        "payload": {
            "perspective": "third_person",
            "funny_why": "吵架变成协作递台词， escalation 自带喜感",
            "beat": ["互相威胁", "一方卡壳", "递台词", "顿悟反击"],
            "banned_literals": ["机器人", "电视", "糖"],
            "dialogue_seed": [
                {"speaker": "昭昭", "intent": "连环威胁升级"},
                {"speaker": "灿灿", "intent": "接招但词穷卡壳"},
                {"speaker": "昭昭", "intent": "教对方下一句威胁"},
                {"speaker": "灿灿", "intent": "照搬并加码喊出"},
            ],
            "closing_intent": "G 类嘴硬心软：暖收或半暖",
            "speaker_map_note": "站外男女娃 → 昭昭/灿灿；递台词者映射昭昭",
            "extract_confidence": 0.85,
            "structure_confidence": 0.88,
            "dialogue_confidence": 0.84,
        },
    },
    {
        "source": "bili",
        "source_id": "seed_m5_juhe",
        "url": "https://www.bilibili.com/video/seed_m5_juhe",
        "title": "拒和解·唐僧式加码",
        "mechanism": "M5",
        "structure_type": "A",
        "theme_family": "消耗",
        "conflict_core": "大人道歉被拒，小孩拒绝和解并连环加码威胁",
        "engagement_norm": 0.72,
        "story_raw": (
            "大人哄生气的小孩说给你道歉对不起。小孩回我不接受你的道歉，"
            "然后唐僧式碎碎念：讨厌你，我再也不陪你出去跑步了。"
            "最后还补刀：我不闲，我要上学还要上班要赚钱，"
            "没空送你，你自己去吧，去了就不要回来了。"
        ),
        "payload": {
            "perspective": "third_person",
            "funny_why": "拒和解后连环加码，把小事讲成人生宣言",
            "beat": ["被哄", "拒和解", "碎碎念加码", "补刀威胁"],
            "banned_literals": ["跑步", "上班", "上学"],
            "dialogue_seed": [
                {"speaker": "昭昭", "intent": "正式拒绝道歉"},
                {"speaker": "昭昭", "intent": "列举不再陪伴的惩罚"},
                {"speaker": "昭昭", "intent": "用忙碌理由拒绝并下逐客令"},
            ],
            "closing_intent": "A 类末段嘴硬 + 夸张威胁收束",
            "speaker_map_note": "站外四岁男孩 → 昭昭；大人不在对白内",
            "extract_confidence": 0.8,
            "structure_confidence": 0.82,
            "dialogue_confidence": 0.8,
        },
    },
]


def _seed_one(sample: dict[str, Any], *, dry_run: bool) -> dict[str, Any]:
    payload = dict(sample["payload"])
    story_raw = str(sample["story_raw"])
    auto_score = repo_gold_story.compute_auto_score(
        engagement_norm=float(sample.get("engagement_norm", 0.7)),
        extract_confidence=float(payload["extract_confidence"]),
        structure_confidence=float(payload["structure_confidence"]),
        dialogue_confidence=float(payload["dialogue_confidence"]),
    )
    row = {
        "source": sample["source"],
        "source_id": sample["source_id"],
        "url": sample["url"],
        "mechanism": sample["mechanism"],
        "structure_type": sample["structure_type"],
        "theme_family": sample.get("theme_family"),
        "title": sample.get("title"),
        "conflict_core": sample.get("conflict_core"),
        "story_raw": story_raw,
        "payload": payload,
        "engagement_norm": float(sample.get("engagement_norm", 0.7)),
        "auto_score": auto_score,
    }
    if dry_run:
        return {"action": "dry_run", **row}
    return repo_gold_story.insert_or_skip(
        source=row["source"],
        source_id=row["source_id"],
        url=row["url"],
        mechanism=row["mechanism"],
        structure_type=row["structure_type"],
        theme_family=row["theme_family"],
        title=row["title"],
        conflict_core=row["conflict_core"],
        story_raw=story_raw,
        payload=payload,
        engagement_norm=row["engagement_norm"],
        auto_score=auto_score,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="金故事 H4 入库")
    parser.add_argument(
        "--seed-samples",
        action="store_true",
        help="写入专家对话沉淀的三条试跑样本",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只打印，不写库",
    )
    args = parser.parse_args()
    if not args.seed_samples:
        parser.error("当前仅支持 --seed-samples；完整 H0–H4 流水线待实现")

    app = create_app()
    results: list[dict[str, Any]] = []
    with app.app_context():
        for sample in _SEED_SAMPLES:
            results.append(_seed_one(sample, dry_run=args.dry_run))
        if not args.dry_run:
            total = repo_gold_story.count_stories()
            active = repo_gold_story.count_stories(status="active")
            print(f"库内 gold_story 总数: {total}（active: {active}）")

    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
