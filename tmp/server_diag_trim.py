"""服务器端诊断：验证 _trim_audio 对 1_1.mp3 的裁剪"""
import shutil, subprocess, wave, struct, math, hashlib
from pathlib import Path

CLIPS = Path("/mnt/data/project/video_factory/data/media/33/audio/clips")
src = CLIPS / "1_1.mp3"
backup = CLIPS / "1_1.mp3.bak"
test_out = Path("/tmp/test_trim_1_1.mp3")

def get_dur(p):
    r = subprocess.run(["ffprobe","-v","error","-show_entries","format=duration","-of","default=noprint_wrappers=1:nokey=1",str(p)], capture_output=True, text=True)
    return float(r.stdout.strip())

def rms_analysis(path, label):
    wav = Path("/tmp/_analysis.wav")
    subprocess.run(["ffmpeg","-y","-i",str(path),"-t","1.5","-acodec","pcm_s16le",str(wav)], capture_output=True)
    with wave.open(str(wav), 'rb') as wf:
        nframes = wf.getnframes()
        framerate = wf.getframerate()
        frames_data = wf.readframes(nframes)
        samples = struct.unpack(f'{nframes}h', frames_data)
        chunk_size = int(framerate * 0.1)
        print(f"\n{label} - 开头 RMS (100ms chunks):")
        for i in range(0, min(len(samples), int(framerate * 1.5)), chunk_size):
            chunk = samples[i:i+chunk_size]
            rms = math.sqrt(sum(s*s for s in chunk) / len(chunk))
            time_ms = i / framerate * 1000
            bar = '#' * int(rms / 100)
            print(f"  {time_ms:6.0f}ms: RMS={rms:7.1f} {bar}")
    wav.unlink(missing_ok=True)

# 1. 当前文件状态
print(f"=== 当前文件 ===")
print(f"Duration: {get_dur(src):.3f}s")
print(f"Size: {src.stat().st_size} bytes")
print(f"MD5: {hashlib.md5(src.read_bytes()).hexdigest()}")
rms_analysis(src, "当前 1_1.mp3")

# 2. 备份
shutil.copy2(src, backup)

# 3. 手动执行 trim (和 _trim_audio 完全一致)
print(f"\n=== 手动执行 trim (cut=738ms) ===")
tmp_wav = Path("/tmp/_trim_test.wav")
tmp_mp3 = Path("/tmp/_trim_test.mp3")

cmd1 = ["ffmpeg","-y","-hide_banner","-i",str(backup),"-ss","0.738","-acodec","pcm_s16le",str(tmp_wav)]
r1 = subprocess.run(cmd1, capture_output=True, text=True)
print(f"Step1 (mp3->wav -ss 0.738): rc={r1.returncode}")
if r1.returncode != 0:
    print(f"  ERROR: {r1.stderr[-300:]}")

cmd2 = ["ffmpeg","-y","-hide_banner","-i",str(tmp_wav),"-c:a","libmp3lame","-q:a","2",str(tmp_mp3)]
r2 = subprocess.run(cmd2, capture_output=True, text=True)
print(f"Step2 (wav->mp3): rc={r2.returncode}")
if r2.returncode != 0:
    print(f"  ERROR: {r2.stderr[-300:]}")

print(f"Trimmed duration: {get_dur(tmp_mp3):.3f}s")
rms_analysis(tmp_mp3, "手动 trim 后")

# 4. 对比
print(f"\n=== 对比 ===")
print(f"原始: {get_dur(backup):.3f}s")
print(f"裁剪: {get_dur(tmp_mp3):.3f}s")
print(f"差值: {get_dur(backup) - get_dur(tmp_mp3):.3f}s (期望 ~0.738s)")

# 5. 恢复原始文件
shutil.copy2(backup, src)
backup.unlink(missing_ok=True)
tmp_wav.unlink(missing_ok=True)
tmp_mp3.unlink(missing_ok=True)
print(f"\n已恢复原始文件")
