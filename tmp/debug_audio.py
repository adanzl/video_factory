import subprocess, json, sys

mp3_path = sys.argv[1] if len(sys.argv) > 1 else r"c:\Users\adanz\project\video_factory\tmp\debug_1_1.mp3"

# 1. Check duration
result = subprocess.run([
    "ffprobe", "-i", mp3_path,
    "-show_entries", "format=duration",
    "-v", "quiet", "-of", "csv=p=0"
], capture_output=True, text=True)
print(f"Duration: {result.stdout.strip()}s")

# 2. Check first frames
result2 = subprocess.run([
    "ffprobe", "-i", mp3_path,
    "-show_entries", "frame=pts_time,pkt_duration",
    "-select_streams", "a:0",
    "-of", "json", "-v", "quiet"
], capture_output=True, text=True)
data = json.loads(result2.stdout)
frames = data.get("frames", [])
print(f"Total frames: {len(frames)}")
for f in frames[:20]:
    print(f"  pts={f.get('pts_time','?')} dur={f.get('pkt_duration','?')}")

# 3. Export first 1.5s as wav for analysis
wav_out = mp3_path.replace(".mp3", "_first1s.wav")
subprocess.run([
    "ffmpeg", "-y", "-i", mp3_path,
    "-t", "1.5", "-acodec", "pcm_s16le", wav_out
], capture_output=True)
print(f"\nFirst 1.5s exported to: {wav_out}")
