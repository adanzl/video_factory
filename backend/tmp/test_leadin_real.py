"""用真实 TTS API 测试 lead-in 裁剪。"""
import sys, os, json, logging
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

logging.basicConfig(level=logging.DEBUG, format="%(name)s %(levelname)s: %(message)s")

from app.services.tts.tts_ali import _run_tts_task
from app.services.tts.phrase_timing import normalize_word_timestamps
from app.services.tts.tts_leadin import prepare_lead_in, strip_tts_lead_in, _PUNCT_RE
from pathlib import Path

voice_zhao = "cosyvoice-v3.5-flash-leo-f9d115bfdf2346edbeb9d21ecd4f9ce9"
text = "姐姐，你看！柜子没锁！妈妈藏的饼干在里面！"

tts_text, lead_in = prepare_lead_in(text, voice=voice_zhao)
print(f"原始文本: {text}")
print(f"TTS文本: {tts_text}")
print(f"lead_in: {lead_in!r}")
print()

# 调用真实 TTS
result = _run_tts_task(tts_text, word_timestamps=True, rate=1.0, voice=voice_zhao)

# 保存音频
out_dir = Path(__file__).parent
clip_path = out_dir / "test_leadin_zhao.mp3"
clip_path.write_bytes(result.audio)
print(f"音频已保存: {clip_path}")

# 查看 raw words
print(f"\nraw words (前15个):")
for w in (result.words or [])[:15]:
    print(f"  text={w.get('text')!r} begin={w.get('begin_time')} end={w.get('end_time')} begin_idx={w.get('begin_index')}")

# normalize
words = normalize_word_timestamps(result.words)
print(f"\nnormalized words (前15个):")
for w in words[:15]:
    print(f"  text={w.text!r} begin={w.begin_time_ms} end={w.end_time_ms}")

# 检查 _PUNCT_RE 对每个前几个 word 的匹配
print(f"\n_PUNCT_RE 检查:")
for w in words[:5]:
    print(f"  {w.text!r} -> is_punct={bool(_PUNCT_RE.fullmatch(w.text))}")

# 尝试裁剪
print(f"\n尝试裁剪 lead_in={lead_in!r}...")
words_before = len(words)
words_after = strip_tts_lead_in(clip_path, words, lead_in)
print(f"裁剪前 words: {words_before}, 裁剪后 words: {len(words_after)}")
if words_after:
    print(f"裁剪后第一个 word: text={words_after[0].text!r} begin={words_after[0].begin_time_ms}")

# 检查裁剪后音频时长
from app.services.media.ffmpeg_utils import probe_duration
dur = probe_duration(clip_path)
print(f"\n裁剪后音频时长: {dur:.3f}s")
print(f"裁剪后音频: {clip_path}")
