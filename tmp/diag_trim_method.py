"""诊断：对当前已裁剪的 1_1.mp3 再裁一次，看开头到底是什么"""
import shutil, subprocess, wave, struct, math
from pathlib import Path

src = Path(r"c:\Users\adanz\project\video_factory\tmp\current_1_1.mp3")

def get_dur(p):
    r = subprocess.run(["ffprobe","-v","error","-show_entries","format=duration","-of","default=noprint_wrappers=1:nokey=1",str(p)], capture_output=True, text=True)
    return float(r.stdout.strip())

def rms_analysis(path, label, duration=1.5):
    wav = Path(r"c:\Users\adanz\project\video_factory\tmp\_analysis.wav")
    subprocess.run(["ffmpeg","-y","-i",str(path),"-t",str(duration),"-acodec","pcm_s16le",str(wav)], capture_output=True)
    with wave.open(str(wav), 'rb') as wf:
        nframes = wf.getnframes()
        framerate = wf.getframerate()
        frames_data = wf.readframes(nframes)
        samples = struct.unpack(f'{nframes}h', frames_data)
        chunk_size = int(framerate * 0.1)
        print(f"\n{label} (dur={get_dur(path):.3f}s):")
        for i in range(0, min(len(samples), int(framerate * duration)), chunk_size):
            chunk = samples[i:i+chunk_size]
            rms = math.sqrt(sum(s*s for s in chunk) / len(chunk))
            time_ms = i / framerate * 1000
            bar = '#' * int(rms / 100)
            print(f"  {time_ms:6.0f}ms: RMS={rms:7.1f} {bar}")
    wav.unlink(missing_ok=True)

# 1. 当前文件分析
rms_analysis(src, "当前 1_1.mp3 (52KB, 已裁)")

# 2. 方法A: 和 _trim_audio 一样 (mp3->wav with -ss, wav->mp3)
# 再裁500ms看看 (因为当前文件开头可能是"那"的残留)
test_a = Path(r"c:\Users\adanz\project\video_factory\tmp\test_a.mp3")
wav_a = Path(r"c:\Users\adanz\project\video_factory\tmp\test_a.wav")
subprocess.run(["ffmpeg","-y","-hide_banner","-i",str(src),"-ss","0.500","-acodec","pcm_s16le",str(wav_a)], capture_output=True)
subprocess.run(["ffmpeg","-y","-hide_banner","-i",str(wav_a),"-c:a","libmp3lame","-q:a","2",str(test_a)], capture_output=True)
rms_analysis(test_a, "方法A: -ss 0.500 (output seeking)", 1.0)

# 3. 方法B: -ss 在 -i 前面 (input seeking)
test_b = Path(r"c:\Users\adanz\project\video_factory\tmp\test_b.mp3")
wav_b = Path(r"c:\Users\adanz\project\video_factory\tmp\test_b.wav")
subprocess.run(["ffmpeg","-y","-hide_banner","-ss","0.500","-i",str(src),"-acodec","pcm_s16le",str(wav_b)], capture_output=True)
subprocess.run(["ffmpeg","-y","-hide_banner","-i",str(wav_b),"-c:a","libmp3lame","-q:a","2",str(test_b)], capture_output=True)
rms_analysis(test_b, "方法B: -ss 0.500 (input seeking)", 1.0)

# 4. 方法C: 先转WAV再atrim (样本级精确)
test_c = Path(r"c:\Users\adanz\project\video_factory\tmp\test_c.mp3")
wav_full = Path(r"c:\Users\adanz\project\video_factory\tmp\full.wav")
wav_c = Path(r"c:\Users\adanz\project\video_factory\tmp\test_c.wav")
subprocess.run(["ffmpeg","-y","-hide_banner","-i",str(src),"-acodec","pcm_s16le",str(wav_full)], capture_output=True)
subprocess.run(["ffmpeg","-y","-hide_banner","-i",str(wav_full),"-af","atrim=start=0.500,asetpts=PTS-STARTPTS","-acodec","pcm_s16le",str(wav_c)], capture_output=True)
subprocess.run(["ffmpeg","-y","-hide_banner","-i",str(wav_c),"-c:a","libmp3lame","-q:a","2",str(test_c)], capture_output=True)
rms_analysis(test_c, "方法C: atrim=0.500 (样本级精确)", 1.0)

# Cleanup
for f in [test_a, test_b, test_c, wav_a, wav_b, wav_full, wav_c]:
    f.unlink(missing_ok=True)

print("\n=== 结论 ===")
print("如果方法A开头仍有语音，说明 -ss output seeking 不精确")
print("如果方法C开头干净，说明应该用 atrim 替代 -ss")
