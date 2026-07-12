"""测试 lead-in 裁剪逻辑：用真实 TTS 返回的 word timestamps 模拟。"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.tts.tts_leadin import prepare_lead_in, strip_tts_lead_in, _PUNCT_RE
from app.services.tts.phrase_timing import TimedWord, normalize_word_timestamps
from pathlib import Path
import json

# 模拟 TTS 返回的 word timestamps（基于真实 CosyVoice 行为）
# 场景1: 正常分词 "那" + "，" + "姐" + ...
words_scenario1 = [
    {"text": "那", "begin_time": 0, "end_time": 200, "begin_index": 0},
    {"text": "，", "begin_time": 200, "end_time": 280, "begin_index": 1},
    {"text": "姐", "begin_time": 280, "end_time": 410, "begin_index": 2},
    {"text": "姐", "begin_time": 410, "end_time": 540, "begin_index": 3},
    {"text": "，", "begin_time": 540, "end_time": 600, "begin_index": 4},
    {"text": "你", "begin_time": 600, "end_time": 700, "begin_index": 5},
]

# 场景2: TTS 把 "那，" 合成一个 token
words_scenario2 = [
    {"text": "那，", "begin_time": 0, "end_time": 280, "begin_index": 0},
    {"text": "姐", "begin_time": 280, "end_time": 410, "begin_index": 1},
    {"text": "姐", "begin_time": 410, "end_time": 540, "begin_index": 2},
]

# 场景3: TTS 省略标点
words_scenario3 = [
    {"text": "那", "begin_time": 0, "end_time": 200, "begin_index": 0},
    {"text": "姐", "begin_time": 200, "end_time": 330, "begin_index": 1},
    {"text": "姐", "begin_time": 330, "end_time": 460, "begin_index": 2},
]

lead_in = "那，"
lead_content_chars = [c for c in lead_in if not _PUNCT_RE.fullmatch(c)]

print(f"lead_in={lead_in!r} lead_content_chars={lead_content_chars}")
print(f"_PUNCT_RE fullmatch '，': {bool(_PUNCT_RE.fullmatch('，'))}")
print()

for name, raw_words in [("场景1: 正常分词", words_scenario1),
                         ("场景2: 合并token", words_scenario2),
                         ("场景3: 省略标点", words_scenario3)]:
    words = normalize_word_timestamps(raw_words)
    print(f"=== {name} ===")
    print(f"  normalized words: {[(w.text, w.begin_time_ms, w.end_time_ms) for w in words]}")

    # 模拟第一遍匹配
    matched_content = 0
    last_lead_word_idx = -1
    for i, word in enumerate(words):
        if matched_content >= len(lead_content_chars):
            break
        if word.text == lead_content_chars[matched_content]:
            matched_content += 1
            last_lead_word_idx = i
        elif _PUNCT_RE.fullmatch(word.text):
            expected_idx = matched_content
            if expected_idx < len(lead_in) and lead_in[expected_idx] == word.text:
                last_lead_word_idx = i
        else:
            break

    print(f"  matched_content={matched_content} last_lead_word_idx={last_lead_word_idx}")

    if matched_content >= len(lead_content_chars):
        content_end_idx = last_lead_word_idx
        for j in range(last_lead_word_idx + 1, len(words)):
            if _PUNCT_RE.fullmatch(words[j].text):
                content_end_idx = j
            else:
                break
        remaining = words[content_end_idx + 1:]
        cut_ms = max(0, remaining[0].begin_time_ms - 15) if remaining else -1
        print(f"  content_end_idx={content_end_idx} cut_ms={cut_ms}")
        print(f"  remaining[0]={( remaining[0].text, remaining[0].begin_time_ms) if remaining else 'NONE'}")
        print(f"  => 裁剪后从 '{remaining[0].text if remaining else 'N/A'}' 开始")
    else:
        print(f"  => 匹配失败! 需要 fallback")

        # 模拟 fallback
        for i, word in enumerate(words):
            if not _PUNCT_RE.fullmatch(word.text):
                content_count = sum(1 for w in words[:i + 1] if not _PUNCT_RE.fullmatch(w.text))
                if content_count >= len(lead_content_chars):
                    cut_ms = max(0, word.end_time_ms - 15)
                    remaining = words[i + 1:]
                    print(f"  fallback: cut_ms={cut_ms} remaining[0]={remaining[0].text if remaining else 'NONE'}")
                    break
    print()
