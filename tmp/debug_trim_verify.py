"""对比原始TTS音频和裁剪后音频，验证lead-in裁剪是否真正生效"""
import subprocess, json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from app.services.tts.segment_trim import _trim_audio, TrimPlan

# 从服务器下载的原始文件（裁剪后的）
trimmed_path = r"c:\Users\adanz\project\video_factory\tmp\debug_1_1.mp3"

# 模拟裁剪过程：从当前文件再裁一次，看是否有变化
# 如果文件已经被正确裁剪，再裁0ms应该不变
# 让我们检查文件开头是否有静音

def get_audio_info(path):
    """获取音频时长和开头静音检测"""
    result = subprocess.run([
        "ffprobe", "-i", path,
        "-show_entries", "format=duration",
        "-v", "quiet", "-of", "csv=p=0"
    ], capture_output=True, text=True)
    duration = float(result.stdout.strip())
    
    # 检测开头静音
    result2 = subprocess.run([
        "ffmpeg", "-i", path,
        "-af", "silencedetect=noise=-30dB:d=0.1",
        "-f", "null", "-"
    ], capture_output=True, text=True)
    
    return duration, result2.stderr

print("=== 检查裁剪后的 1_1.mp3 ===")
duration, stderr = get_audio_info(trimmed_path)
print(f"Duration: {duration:.3f}s")

# 查找silencedetect输出
for line in stderr.split('\n'):
    if 'silence' in line.lower():
        print(f"  {line.strip()}")

# 用ffmpeg将前1.5s转为wav并分析音量
print("\n=== 导出前1.5s为WAV分析 ===")
wav_path = r"c:\Users\adanz\project\video_factory\tmp\debug_analysis.wav"
subprocess.run([
    "ffmpeg", "-y", "-i", trimmed_path,
    "-t", "1.5", "-acodec", "pcm_s16le", wav_path
], capture_output=True)

# 用python读取wav分析音量
import wave
import struct
import math

with wave.open(wav_path, 'rb') as wf:
    nframes = wf.getnframes()
    framerate = wf.getframerate()
    frames = wf.readframes(nframes)
    samples = struct.unpack(f'{nframes}h', frames)
    
    # 分析每100ms的RMS音量
    chunk_size = int(framerate * 0.1)  # 100ms
    print(f"\n采样率: {framerate}, 总帧数: {nframes}")
    print("\n每100ms RMS音量:")
    for i in range(0, min(len(samples), int(framerate * 1.5)), chunk_size):
        chunk = samples[i:i+chunk_size]
        rms = math.sqrt(sum(s*s for s in chunk) / len(chunk))
        time_ms = i / framerate * 1000
        bar = '#' * int(rms / 100)
        print(f"  {time_ms:6.0f}ms: RMS={rms:7.1f} {bar}")

# 清理临时文件
os.unlink(wav_path)
