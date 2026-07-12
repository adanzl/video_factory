"""直接测试 ffmpeg 裁剪效果"""
import shutil, subprocess, wave, struct, math
from pathlib import Path

src = Path(r"c:\Users\adanz\project\video_factory\tmp\debug_1_1.mp3")
test = Path(r"c:\Users\adanz\project\video_factory\tmp\test_trim.mp3")
wav_out = Path(r"c:\Users\adanz\project\video_factory\tmp\test_out.wav")

shutil.copy2(src, test)

def get_dur(p):
    r = subprocess.run(["ffprobe","-v","error","-show_entries","format=duration","-of","default=noprint_wrappers=1:nokey=1",str(p)], capture_output=True, text=True)
    return float(r.stdout.strip())

print(f"Original: {get_dur(test):.3f}s")

# 方法1: 和 _trim_audio 完全一样 (mp3 -> wav -> mp3)
tmp_wav = test.with_name("test_trim.trim.wav")
tmp_mp3 = test.with_name("test_trim.trim.mp3")

# Step1: mp3 -> wav with -ss
cmd1 = ["ffmpeg","-y","-hide_banner","-i",str(test),"-ss","0.738","-acodec","pcm_s16le",str(tmp_wav)]
r1 = subprocess.run(cmd1, capture_output=True, text=True)
print(f"\nStep1 (mp3->wav -ss 0.738): returncode={r1.returncode}")
if r1.returncode != 0:
    print(f"  stderr: {r1.stderr[-500:]}")

# Step2: wav -> mp3
cmd2 = ["ffmpeg","-y","-hide_banner","-i",str(tmp_wav),"-c:a","libmp3lame","-q:a","2",str(tmp_mp3)]
r2 = subprocess.run(cmd2, capture_output=True, text=True)
print(f"Step2 (wav->mp3): returncode={r2.returncode}")

# Replace
shutil.move(str(tmp_mp3), str(test))
tmp_wav.unlink(missing_ok=True)
tmp_mp3.unlink(missing_ok=True)

print(f"After trim (method 1): {get_dur(test):.3f}s")

# 分析开头音频
subprocess.run(["ffmpeg","-y","-i",str(test),"-t","1.5","-acodec","pcm_s16le",str(wav_out)], capture_output=True)
with wave.open(str(wav_out), 'rb') as wf:
    nframes = wf.getnframes()
    framerate = wf.getframerate()
    frames_data = wf.readframes(nframes)
    samples = struct.unpack(f'{nframes}h', frames_data)
    chunk_size = int(framerate * 0.1)
    print("\nMethod 1 (_trim_audio 相同逻辑) - 开头 RMS:")
    for i in range(0, min(len(samples), int(framerate * 1.5)), chunk_size):
        chunk = samples[i:i+chunk_size]
        rms = math.sqrt(sum(s*s for s in chunk) / len(chunk))
        time_ms = i / framerate * 1000
        bar = '#' * int(rms / 100)
        print(f"  {time_ms:6.0f}ms: RMS={rms:7.1f} {bar}")

# 方法2: -ss 放在 -i 前面 (input seeking, 更快更精确)
shutil.copy2(src, test)
tmp_wav2 = test.with_name("test_trim2.trim.wav")
tmp_mp32 = test.with_name("test_trim2.trim.mp3")

cmd3 = ["ffmpeg","-y","-hide_banner","-ss","0.738","-i",str(test),"-acodec","pcm_s16le",str(tmp_wav2)]
r3 = subprocess.run(cmd3, capture_output=True, text=True)
print(f"\nMethod 2 (-ss before -i): returncode={r3.returncode}")
cmd4 = ["ffmpeg","-y","-hide_banner","-i",str(tmp_wav2),"-c:a","libmp3lame","-q:a","2",str(tmp_mp32)]
subprocess.run(cmd4, capture_output=True)
shutil.move(str(tmp_mp32), str(test))
tmp_wav2.unlink(missing_ok=True)

print(f"After trim (method 2): {get_dur(test):.3f}s")

subprocess.run(["ffmpeg","-y","-i",str(test),"-t","1.5","-acodec","pcm_s16le",str(wav_out)], capture_output=True)
with wave.open(str(wav_out), 'rb') as wf:
    nframes = wf.getnframes()
    framerate = wf.getframerate()
    frames_data = wf.readframes(nframes)
    samples = struct.unpack(f'{nframes}h', frames_data)
    chunk_size = int(framerate * 0.1)
    print("\nMethod 2 (-ss before -i) - 开头 RMS:")
    for i in range(0, min(len(samples), int(framerate * 1.5)), chunk_size):
        chunk = samples[i:i+chunk_size]
        rms = math.sqrt(sum(s*s for s in chunk) / len(chunk))
        time_ms = i / framerate * 1000
        bar = '#' * int(rms / 100)
        print(f"  {time_ms:6.0f}ms: RMS={rms:7.1f} {bar}")

# Cleanup
wav_out.unlink(missing_ok=True)
test.unlink(missing_ok=True)
