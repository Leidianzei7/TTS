#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
实时语音识别 - 启英泰伦 USB 声音模块
唤醒词"小智小智" → 采集指令 → SenseVoiceSmall ASR → Qwen LLM → 标准化编号指令
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
from openai import OpenAI

# ── 设备配置 ──────────────────────────────────────────────
DEVICE_INDEX = 2
SAMPLE_RATE  = 16000
CHANNELS     = 1
CHUNK        = 1024

# ── VAD / 识别参数 ────────────────────────────────────────
SILENCE_THRESHOLD = 300
SPEECH_HOLD_SEC   = 1.5
MIN_SPEECH_SEC    = 0.3

# ── 唤醒词 ────────────────────────────────────────────────
WAKE_WORD = "小智小智"

# ── LLM 配置 ──────────────────────────────────────────────
LLM_API_KEY  = "sk-1c3077000f6347858d88c0936169d5af"
LLM_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
LLM_MODEL    = "qwen-turbo"
LLM_SYSTEM   = (
    "你是一个指令解析助手。将用户的自然语言输入拆解为有序的、标准化的步骤。"
    "每条指令单独一行，格式为 '1. 动作'。只输出编号列表，不要添加任何解释。"
)

# ── 全局状态 ──────────────────────────────────────────────
audio_q: queue.Queue = queue.Queue()
running              = threading.Event()
running.set()
waiting_for_command  = False

print("正在加载 SenseVoiceSmall 语音识别模型，请稍候...")
asr_model = AutoModel(
    model="iic/SenseVoiceSmall",
    vad_model="fsmn-vad",
    device="cpu",
    use_itn=True,
    disable_pbar=True,
)
print("模型加载完成！\n")

llm_client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)


def audio_callback(indata, frames, time_info, status):
    if status:
        print(f"[音频状态] {status}", file=sys.stderr)
    audio_q.put(indata[:, 0].copy())


def recognize(audio_np: np.ndarray) -> str:
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        tmp_path = f.name
    try:
        sf.write(tmp_path, audio_np, SAMPLE_RATE)
        res = asr_model.generate(
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


def parse_instructions(text: str) -> str:
    resp = llm_client.chat.completions.create(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": LLM_SYSTEM},
            {"role": "user",   "content": text},
        ],
    )
    return resp.choices[0].message.content.strip()


def handle_asr_result(text: str):
    global waiting_for_command

    if WAKE_WORD in text:
        cmd = text[text.index(WAKE_WORD) + len(WAKE_WORD):].strip("，。,.： ")
        if cmd:
            print(f"📋 指令原文: {cmd}", flush=True)
            print("⏳ 解析中...", flush=True)
            result = parse_instructions(cmd)
            print(f"\n✅ 标准化指令:\n{result}\n", flush=True)
        else:
            print("👂 已唤醒，请说出指令...", flush=True)
            waiting_for_command = True
    elif waiting_for_command:
        waiting_for_command = False
        print(f"📋 指令原文: {text}", flush=True)
        print("⏳ 解析中...", flush=True)
        result = parse_instructions(text)
        print(f"\n✅ 标准化指令:\n{result}\n", flush=True)
    # 未唤醒时忽略识别结果


def process_loop():
    speech_buf    = np.array([], dtype=np.float32)
    in_speech     = False
    silence_cnt   = 0
    silence_limit = int(SPEECH_HOLD_SEC * SAMPLE_RATE / CHUNK)

    while running.is_set():
        try:
            chunk = audio_q.get(timeout=0.5)
        except queue.Empty:
            continue

        chunk = chunk.astype(np.float32)
        rms   = np.sqrt(np.mean(chunk ** 2) * (32768 ** 2))

        if rms > SILENCE_THRESHOLD:
            if not in_speech:
                in_speech  = True
                speech_buf = chunk.copy()
                print("🎤 正在聆听...", flush=True)
            else:
                speech_buf = np.concatenate([speech_buf, chunk])
            silence_cnt = 0
        else:
            if in_speech:
                speech_buf  = np.concatenate([speech_buf, chunk])
                silence_cnt += 1
                if silence_cnt >= silence_limit:
                    in_speech   = False
                    silence_cnt = 0
                    duration    = len(speech_buf) / SAMPLE_RATE
                    if duration >= MIN_SPEECH_SEC:
                        print("⏳ 识别中...", flush=True)
                        text = recognize(speech_buf)
                        if text.strip():
                            print(f"🗣  {text}", flush=True)
                            handle_asr_result(text)
                        else:
                            print("（未识别到有效内容）\n", flush=True)
                    speech_buf = np.array([], dtype=np.float32)


def main():
    print(f"使用音频设备 Index={DEVICE_INDEX}（启英泰伦 USB 声音模块）")
    print(f"采样率: {SAMPLE_RATE} Hz | 静音阈值 RMS: {SILENCE_THRESHOLD}")
    print(f"唤醒词: 【{WAKE_WORD}】")
    print("─" * 50)
    print("说出唤醒词后下达指令，按 Ctrl+C 停止...\n")

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
