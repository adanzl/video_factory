"""检查 lead-in 裁剪是否生效。"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pathlib import Path
from app.services.tts.tts_ali import _run_tts_task
from app.services.tts.phrase_timing import normalize_word_timestamps
from app.services.tts.tts_leadin import prepare_lead_in, strip_tts_lead_in
from app.services.media.ffmpeg_utils import probe_duration

voice = "cosyvoice-v3.5-flash-leo-f9d115bfdf2346edbeb9d21ecd4f9ce9"
text = "姐姐，你看！柜子没锁！妈妈藏的饼干在里面！"

tts_text, lead_in = prepare_lead_in(text, voice=voice)
print(f"tts_text={tts_text}")
print(f"lead_in={lead_in!r}")

result = _run_tts_task(tts_text, word_timestamps=True, rate=0.7, voice=voice)
words = normalize_word_timestamps(result.words)
print(f"words[:8]={[(w.text, w.begin_time_ms, w.end_time_ms) for w in words[:8]]}")

# 保存原始音频
out_dir = Path("/tmp/lead_test")
out_dir.mkdir(exist_ok=True)
raw_path = out_dir / "raw.mp3"
raw_path.write_bytes(result.audio)
print(f"raw duration={probe_duration(raw_path):.3f}s")

# 裁剪
trimmed_path = out_dir / "trimmed.mp3"
trimmed_path.write_bytes(result.audio)  # copy
words_after = strip_tts_lead_in(trimmed_path, words, lead_in)
print(f"after strip: words count {len(words)} -> {len(words_after)}")
if words_after:
    print(f"first remaining word: {words_after[0].text!r} begin={words_after[0].begin_time_ms}")
print(f"trimmed duration={probe_duration(trimmed_path):.3f}s")
print(f"trimmed path={trimmed_path}")
