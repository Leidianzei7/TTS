#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
实时语音识别 - 启英泰伦 USB 声音模块
使用 FunASR SenseVoiceSmall + fsmn-vad
"""

import sys
import queue
import threading
import time
import tempfile
import os
import numpy as np
import sounddevice as sd
import soundfile as sf
from funasr import AutoModel
from funasr.utils.postprocess_utils import rich_transcription_postprocess

# ── 设备配置 ──────────────────────────────────────────────
DEVICE_INDEX = 2        # USB PnP Audio Device（启英泰伦模块）Index 2
SAMPLE_RATE  = 16000    # SenseVoice 要求 16kHz
CHANNELS     = 1        # 单声道
CHUNK        = 1024     # 每次读取帧数

# ── VAD / 识别参数 ────────────────────────────────────────
SILENCE_THRESHOLD = 300   # RMS 低于此值视为静音（按环境调节）
SPEECH_HOLD_SEC   = 1.5   # 检测到声音后继续录制的最小时长（秒）
MIN_SPEECH_SEC    = 0.3   # 最短有效语音长度（秒）

# ── 全局状态 ──────────────────────────────────────────────
audio_q: queue.Queue = queue.Queue()
running   = threading.Event()
running.set()

print("正在加载 SenseVoiceSmall 语音识别模型，请稍候...")
model = AutoModel(
    model="iic/SenseVoiceSmall",
    vad_model="fsmn-vad",
    device="cpu",
    use_itn=True,
    disable_pbar=True,
)
print("模型加载完成！\n")


def audio_callback(indata, frames, time_info, status):
    """sounddevice 回调：将采集到的音频帧放入队列"""
    if status:
        print(f"[音频状态] {status}", file=sys.stderr)
    audio_q.put(indata[:, 0].copy())   # 取第一声道


def recognize(audio_np: np.ndarray) -> str:
    """调用 FunASR 完成识别，返回文本"""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        tmp_path = f.name
    try:
        sf.write(tmp_path, audio_np, SAMPLE_RATE)
        res = model.generate(
            input=tmp_path,
            cache={},
            language="auto",
            use_itn=True,
            batch_size_s=60,
            merge_vad=True,
            merge_length_s=15,
        )
        if res and res[0].get("text"):
            return rich_transcription_postprocess(res[0]["text"])
        return ""
    finally:
        os.remove(tmp_path)


def process_loop():
    """从队列取音频，做 VAD 触发，触发后送识别"""
    buffer      = np.array([], dtype=np.float32)
    speech_buf  = np.array([], dtype=np.float32)
    in_speech   = False
    silence_cnt = 0
    silence_limit = int(SPEECH_HOLD_SEC * SAMPLE_RATE / CHUNK)

    while running.is_set():
        try:
            chunk = audio_q.get(timeout=0.5)
        except queue.Empty:
            continue

        # 转 float32 防止溢出
        chunk = chunk.astype(np.float32)
        rms   = np.sqrt(np.mean(chunk ** 2) * (32768 ** 2))   # 模拟 int16 量级

        if rms > SILENCE_THRESHOLD:
            if not in_speech:
                in_speech   = True
                speech_buf  = chunk.copy()
                print("🎤 正在聆听...", flush=True)
            else:
                speech_buf  = np.concatenate([speech_buf, chunk])
            silence_cnt = 0
        else:
            if in_speech:
                speech_buf  = np.concatenate([speech_buf, chunk])
                silence_cnt += 1
                if silence_cnt >= silence_limit:
                    # 说话结束
                    in_speech   = False
                    silence_cnt = 0
                    duration    = len(speech_buf) / SAMPLE_RATE
                    if duration >= MIN_SPEECH_SEC:
                        print("⏳ 识别中...", flush=True)
                        text = recognize(speech_buf)
                        if text.strip():
                            print(f"\n📝 {text}\n", flush=True)
                        else:
                            print("（未识别到有效内容）\n", flush=True)
                    speech_buf = np.array([], dtype=np.float32)


def main():
    print(f"使用音频设备 Index={DEVICE_INDEX}（启英泰伦 USB 声音模块）")
    print(f"采样率: {SAMPLE_RATE} Hz | 静音阈值 RMS: {SILENCE_THRESHOLD}")
    print("─" * 50)
    print("开始实时语音识别，按 Ctrl+C 停止...\n")

    proc_thread = threading.Thread(target=process_loop, daemon=True)
    proc_thread.start()

    try:
        with sd.InputStream(
            device=DEVICE_INDEX,
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype="float32",
            blocksize=CHUNK,
            callback=audio_callback,
        ):
            while running.is_set():
                time.sleep(0.1)
    except KeyboardInterrupt:
        print("\n\n停止识别。")
    except Exception as e:
        print(f"\n音频设备错误: {e}")
    finally:
        running.clear()
        proc_thread.join(timeout=3)


if __name__ == "__main__":
    main()
