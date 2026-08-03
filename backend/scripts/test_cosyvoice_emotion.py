#!/usr/bin/env python3
"""CosyVoice 情绪控制测试脚本。

通过 WebSocket 调用 DashScope CosyVoice API，用不同 instruction 合成同一段文本，
对比音频输出，验证 instruction 字段是否支持情绪/语气控制。

用法：
    DASHSCOPE_API_KEY=xxx python -m scripts.test_cosyvoice_emotion

输出：
    data/test_tts_emotion/
    ├── baseline.wav          # 无 instruction 的基准音频
    ├── happy.wav             # instruction="用开心兴奋的语气朗读"
    ├── sad.wav               # instruction="用悲伤低落的语气朗读"
    ├── angry.wav             # instruction="用生气的语气朗读"
    ├── gentle.wav            # instruction="用温柔平静的语气朗读"
    ├── whisper.wav           # instruction="用悄悄话的语气朗读，声音放轻"
    └── report.txt            # 对比报告（时长、文件大小）
"""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from pathlib import Path

# --- 配置 ---
WS_URI = os.getenv(
    "DASHSCOPE_WS_URI",
    "wss://dashscope.aliyuncs.com/api-ws/v1/inference/",
)
VOICE = os.getenv(
    "TTS_VOICE",
    "cosyvoice-v3.5-flash-leo-40c4359c732f4b459a40f3408e1186ed",
)
# 复刻音色对应的模型
VOICE_MODEL_MAP = {
    "longwan_v2": "cosyvoice-v2",
    "longcheng_v2": "cosyvoice-v2",
    "longhua_v2": "cosyvoice-v2",
    "longshu_v2": "cosyvoice-v2",
    "loongbella_v2": "cosyvoice-v2",
    "longxiaochun_v2": "cosyvoice-v2",
    "longxiaoxia_v2": "cosyvoice-v2",
    "longwan_v3": "cosyvoice-v3-flash",
    "longyingjing_v3": "cosyvoice-v3-flash",
    "longanhuan_v3": "cosyvoice-v3-flash",
    "longanhuan": "cosyvoice-v3-flash",
    "longhuhu_v3": "cosyvoice-v3-flash",
    "longhuhu": "cosyvoice-v3-flash",
    "longniuniu_v3": "cosyvoice-v3-flash",
    "longniuniu": "cosyvoice-v3-flash",
    "longxian_v3": "cosyvoice-v3-flash",
    "longjielidou_v3": "cosyvoice-v3-flash",
    "cosyvoice-v3.5-flash-leo-f9d115bfdf2346edbeb9d21ecd4f9ce9": "cosyvoice-v3.5-flash",
    "cosyvoice-v3.5-flash-leo-40c4359c732f4b459a40f3408e1186ed": "cosyvoice-v3.5-flash",
}
MODEL = VOICE_MODEL_MAP.get(VOICE, "cosyvoice-v3.5-plus")
RATE = float(os.getenv("TTS_SPEECH_RATE", "1.20"))
VOLUME = int(os.getenv("TTS_VOLUME", "50"))
PITCH = float(os.getenv("TTS_PITCH", "1.0"))

# 测试文本（日常故事对白）
TEST_TEXT = "昭昭你快看！这个蚂蚁居然能搬动比自己大十倍的东西。哇真的假的？当然是真的，你看它现在还在搬呢！"

# 测试的 instruction 场景
TEST_CASES: list[tuple[str, str | None]] = [
    ("baseline", None),                                        # 基准：无指令
    ("happy", "用开心兴奋的语气朗读，声音明亮上扬"),            # 开心
    ("sad", "用悲伤低落的语气朗读，声音低沉缓慢"),              # 悲伤
    ("angry", "用生气的语气朗读，声音急促有力"),                # 生气
    ("gentle", "用温柔平静的语气朗读，声音轻柔舒缓"),            # 温柔
    ("whisper", "用悄悄话的语气朗读，声音放轻放低，像在说秘密"),  # 悄悄话
]

# --- 工具函数 ---
def _disambiguate_dao(text: str) -> str:
    """将未保护的「倒」替换为「到」，避免 CosyVoice 误读为 dǎo。"""
    DAO3_WORDS = (
        "摔倒", "跌倒", "绊倒", "推倒", "打倒", "晕倒", "躺倒",
        "病倒", "吓倒", "醉倒", "压倒", "跪倒", "栽倒", "扑倒",
        "拉倒", "倒霉", "倒闭", "倒台", "倒塌", "倒地", "倒下",
        "倒戈", "颠倒", "倾倒",
    )
    if "倒" not in text:
        return text
    masked = text
    placeholders = []
    for i, word in enumerate(DAO3_WORDS):
        if word not in masked:
            continue
        token = f"\0DAO3_{i}\0"
        placeholders.append((token, word))
        masked = masked.replace(word, token)
    masked = masked.replace("倒", "到")
    for token, word in placeholders:
        masked = masked.replace(token, word)
    return masked


def _convert_single_digits(text: str) -> str:
    """孤立一位数数字 → 汉字。"""
    import re
    SINGLE_DIGIT_MAP = {
        '0': '零', '1': '一', '2': '二', '3': '三', '4': '四',
        '5': '五', '6': '六', '7': '七', '8': '八', '9': '九',
    }
    return re.sub(r'(?<!\d)\d(?!\d)', lambda m: SINGLE_DIGIT_MAP[m.group(0)], text)


def synthesize(text: str, instruction: str | None = None, timeout: float = 120) -> bytes:
    """通过 WebSocket 同步调用 CosyVoice，返回 WAV 音频 bytes。"""
    import websocket

    api_key = os.getenv("DASHSCOPE_API_KEY") or os.getenv("TTS_API_KEY") or ""
    if not api_key:
        raise RuntimeError("请设置 DASHSCOPE_API_KEY 环境变量")

    text = _convert_single_digits(text)
    text = _disambiguate_dao(text)

    task_id = str(uuid.uuid4())
    audio_chunks: list[bytes] = []
    error_msg: str | None = None

    ws = websocket.create_connection(
        WS_URI,
        header={
            "Authorization": f"bearer {api_key}",
            "X-DashScope-DataInspection": "enable",
        },
        timeout=timeout,
    )

    # Step 1: run-task
    params = {
        "text_type": "PlainText",
        "voice": VOICE,
        "format": "wav",
        "sample_rate": 22050,
        "volume": VOLUME,
        "rate": RATE,
        "pitch": PITCH,
        "word_timestamp_enabled": False,
        "language_hints": ["zh"],
    }
    if instruction:
        params["instruction"] = instruction

    ws.send(json.dumps({
        "header": {
            "action": "run-task",
            "task_id": task_id,
            "streaming": "duplex",
        },
        "payload": {
            "task_group": "audio",
            "task": "tts",
            "function": "SpeechSynthesizer",
            "model": MODEL,
            "parameters": params,
            "input": {},
        },
    }))

    # Step 2: wait for task-started
    deadline = time.time() + 30
    started = False
    while time.time() < deadline:
        opcode, data = ws.recv_data()
        if opcode == websocket.ABNF.OPCODE_BINARY:
            audio_chunks.append(data)
            continue
        try:
            body = json.loads(data)
        except json.JSONDecodeError:
            continue
        event = body.get("header", {}).get("event")
        if event == "task-started":
            started = True
            break
        elif event == "task-failed":
            msg = body.get("header", {}).get("error_message", "unknown")
            error_msg = f"task-failed: {msg}"
            break
    if error_msg:
        ws.close()
        raise RuntimeError(error_msg)
    if not started:
        ws.close()
        raise TimeoutError("TTS task-started 超时")

    # Step 3: send text + finish
    ws.send(json.dumps({
        "header": {
            "action": "continue-task",
            "task_id": task_id,
            "streaming": "duplex",
        },
        "payload": {"input": {"text": text}},
    }))
    ws.send(json.dumps({
        "header": {
            "action": "finish-task",
            "task_id": task_id,
            "streaming": "duplex",
        },
        "payload": {"input": {}},
    }))

    # Step 4: receive audio
    deadline = time.time() + timeout
    finished = False
    while time.time() < deadline:
        opcode, data = ws.recv_data()
        if opcode == websocket.ABNF.OPCODE_BINARY:
            audio_chunks.append(data)
        else:
            try:
                body = json.loads(data)
            except json.JSONDecodeError:
                continue
            event = body.get("header", {}).get("event")
            if event == "task-finished":
                finished = True
                ws.close()
                break
            elif event == "task-failed":
                msg = body.get("header", {}).get("error_message", "unknown")
                error_msg = f"task-failed: {msg}"
                ws.close()
                break
    if error_msg:
        raise RuntimeError(error_msg)
    if not finished:
        ws.close()
        raise TimeoutError("TTS 合成超时")

    audio = b"".join(audio_chunks)
    if not audio:
        raise RuntimeError("TTS 返回空音频")
    return audio


def main():
    output_dir = Path("data/test_tts_emotion")
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"CosyVoice 情绪控制测试")
    print(f"音色: {VOICE}")
    print(f"模型: {MODEL}")
    print(f"语速: {RATE}  音量: {VOLUME}  音调: {PITCH}")
    print(f"测试文本: {TEST_TEXT}")
    print(f"输出目录: {output_dir}")
    print(f"{'=' * 60}")

    results: list[dict] = []

    for name, instruction in TEST_CASES:
        label = f"{name}" + (f" ({instruction})" if instruction else " (无指令·基准)")
        print(f"\n▶ {label}")
        try:
            audio = synthesize(TEST_TEXT, instruction=instruction)
            out_path = output_dir / f"{name}.wav"
            out_path.write_bytes(audio)
            duration = len(audio) / (22050 * 2)  # 16-bit mono WAV
            size_kb = len(audio) / 1024
            print(f"  ✓ 完成  size={size_kb:.1f}KB  duration≈{duration:.2f}s  → {out_path.name}")
            results.append({
                "name": name,
                "instruction": instruction,
                "path": str(out_path),
                "size_bytes": len(audio),
                "duration_sec": duration,
                "error": None,
            })
        except Exception as e:
            print(f"  ✗ 失败: {e}")
            results.append({
                "name": name,
                "instruction": instruction,
                "path": None,
                "size_bytes": 0,
                "duration_sec": 0,
                "error": str(e),
            })

    # 写对比报告
    print(f"\n{'=' * 60}")
    print("对比报告")
    print(f"{'=' * 60}")

    baseline = next((r for r in results if r["name"] == "baseline"), None)
    report_lines = [
        f"CosyVoice 情绪控制测试报告",
        f"时间: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"音色: {VOICE}",
        f"模型: {MODEL}",
        f"测试文本: {TEST_TEXT}",
        f"",
        f"{'name':<12} {'size(KB)':>10} {'dur(s)':>8} {'vs baseline':>15} {'note'}",
        f"{'-' * 70}",
    ]

    for r in results:
        name = r["name"]
        size_kb = r["size_bytes"] / 1024
        dur = r["duration_sec"]
        if r["error"]:
            report_lines.append(f"{name:<12} {'FAILED':>10} {'':>8} {'':>15} {r['error']}")
            print(f"  {name}: 失败 - {r['error']}")
        else:
            diff_str = ""
            if baseline and name != "baseline" and baseline["duration_sec"] > 0:
                dur_diff = dur - baseline["duration_sec"]
                size_diff = r["size_bytes"] - baseline["size_bytes"]
                diff_str = f"{dur_diff:+.2f}s/{size_diff:+.0f}B"
            report_lines.append(f"{name:<12} {size_kb:>10.1f} {dur:>8.2f} {diff_str:>15}")
            print(f"  {name}: {size_kb:.1f}KB, {dur:.2f}s  {diff_str}")

    report_path = output_dir / "report.txt"
    report_path.write_text("\n".join(report_lines), encoding="utf-8")
    print(f"\n报告已保存: {report_path}")
    print("\n⚠ 注意：情绪控制效果取决于 CosyVoice 引擎是否支持 instruction 中的自然语言描述。")
    print("  请人工对比各音频文件，判断 instruction 是否对合成效果产生了可感知的影响。")


if __name__ == "__main__":
    main()
