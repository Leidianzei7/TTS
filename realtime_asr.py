#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
实时语音识别 + TTS 回应 - 启英泰伦 USB 声音模块
唤醒词"小智小智" → ASR → Qwen LLM → 自然语言语音回应 + 标准化指令打印
"""

import sys
import queue
import threading
import time
import tempfile
import os
import io
import numpy as np
import sounddevice as sd
import soundfile as sf
from funasr import AutoModel
from funasr.utils.postprocess_utils import rich_transcription_postprocess
from openai import OpenAI
from pypinyin import lazy_pinyin
import dashscope
from dashscope.audio.tts_v2 import SpeechSynthesizer, AudioFormat

# ── 设备配置 ──────────────────────────────────────────────
# 运行 `python3 -c "import sounddevice as sd; print(sd.query_devices())"` 查看设备列表
DEVICE_INDEX        = 2     # 麦克风输入设备编号（USB PnP 输入端）
OUTPUT_DEVICE_INDEX = 1     # 扬声器输出设备编号（USB PnP 输出端，同一物理模块）
SAMPLE_RATE         = 16000 # 麦克风采样率（Hz），SenseVoiceSmall 要求 16kHz
CHANNELS            = 1     # 输入声道数（单声道）
CHUNK               = 1024  # 每次读取的音频帧数，影响处理延迟（越小延迟越低，CPU 占用越高）

# ── VAD（语音活动检测）参数 ──────────────────────────────
SILENCE_THRESHOLD = 1000  # RMS 能量阈值，超过则判定为有声音
                          # 环境噪声大时调高（如 1500-2000），安静环境可调低（如 500）
SPEECH_HOLD_SEC   = 1.5   # 停顿多久（秒）后触发识别，说话慢时调大，想快速响应时调小
MIN_SPEECH_SEC    = 0.3   # 有效语音最短时长（秒），低于此时长的片段直接丢弃（过滤误触）

# ── 唤醒词 ────────────────────────────────────────────────
WAKE_WORD  = "小智小智"   # 唤醒词，说出后系统开始监听指令
_WW_LEN    = len(WAKE_WORD)
_WW_PINYIN = "".join(lazy_pinyin(WAKE_WORD))  # 拼音版本，用于近同音字容错匹配

# ── LLM 配置 ──────────────────────────────────────────────
LLM_API_KEY  = "sk-1c3077000f6347858d88c0936169d5af"
LLM_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"  # 阿里云华北2
LLM_MODEL    = "qwen-turbo"   # 可换 qwen-plus（更准）或 qwen-max（最强，更慢）
LLM_SYSTEM   = (
    "你是小智，一个智能语音助手。用户用语音下达指令，你需要严格按以下格式回复：\n"
    "[口语回复]：<用自然、口语化的1-2句话回应用户，不要读指令列表>\n"
    "[执行指令]：\n"
    "1. 动作一\n"
    "2. 动作二\n\n"
    "只输出这两个部分，不要任何额外说明。"
)

# ── TTS 配置 ──────────────────────────────────────────────
# 可用中文音色（CosyVoice v2）：
#   longxiaochun_v2（男，成熟）longxiaoxia_v2（女，温柔）
#   longxiaobai_v2（男，活泼）longxiaomiao_v2（女，知性）
TTS_VOICE       = "longxiaochun_v2"
TTS_SAMPLE_RATE = 16000                       # 与麦克风采样率一致
TTS_FORMAT      = AudioFormat.WAV_16000HZ_MONO_16BIT

# ── 全局状态 ──────────────────────────────────────────────
audio_q             = queue.Queue()
tts_audio_q         = queue.Queue()  # TTS 待播音频队列，(audio_np, spoken_text)
running             = threading.Event()
running.set()
waiting_for_command = False

# ── 模型 / 客户端初始化 ──────────────────────────────────
print("正在加载 SenseVoiceSmall 语音识别模型，请稍候...")
asr_model = AutoModel(
    model="iic/SenseVoiceSmall",
    vad_model="fsmn-vad",
    device="cpu",
    use_itn=True,
    disable_pbar=True,
)
print("模型加载完成！\n")

llm_client        = OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)
dashscope.api_key = LLM_API_KEY


# ─────────────────────────────────────────────────────────
# 音频采集回调
# ─────────────────────────────────────────────────────────
def audio_callback(indata, frames, time_info, status):
    if status:
        print(f"[音频状态] {status}", file=sys.stderr)
    audio_q.put(indata[:, 0].copy())


# ─────────────────────────────────────────────────────────
# ASR
# ─────────────────────────────────────────────────────────
def recognize(audio_np):
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


# ─────────────────────────────────────────────────────────
# 唤醒词检测（支持近同音字容错）
# ─────────────────────────────────────────────────────────
def find_wake_word(text):
    if WAKE_WORD in text:
        return text.index(WAKE_WORD)
    for i in range(len(text) - _WW_LEN + 1):
        if "".join(lazy_pinyin(text[i:i + _WW_LEN])) == _WW_PINYIN:
            return i
    return -1


# ─────────────────────────────────────────────────────────
# TTS 合成
# ─────────────────────────────────────────────────────────
def synthesize_speech(text):
    try:
        syn = SpeechSynthesizer(
            model="cosyvoice-v2",
            voice=TTS_VOICE,
            format=TTS_FORMAT,
        )
        audio_bytes = syn.call(text)
        if not audio_bytes:
            print("[TTS] 合成返回空数据", file=sys.stderr)
            return None
        audio_np, _ = sf.read(io.BytesIO(audio_bytes), dtype="float32")
        return audio_np
    except Exception as e:
        print(f"[TTS 错误] {e}", file=sys.stderr)
        return None


# ─────────────────────────────────────────────────────────
# TTS 播放线程（独立线程，不阻塞主音频处理）
# ─────────────────────────────────────────────────────────
def tts_playback_thread():
    while running.is_set():
        try:
            audio_np = tts_audio_q.get(timeout=0.5)
        except queue.Empty:
            continue

        try:
            sd.play(audio_np, samplerate=TTS_SAMPLE_RATE, device=OUTPUT_DEVICE_INDEX)
            sd.wait()
        except Exception as e:
            print(f"[播放错误] {e}", file=sys.stderr)


# ─────────────────────────────────────────────────────────
# LLM 响应生成与解析
# ─────────────────────────────────────────────────────────
def parse_llm_response(raw):
    """从 LLM 双段输出中提取口语回复和执行指令。"""
    spoken = ""
    instruction_lines = []
    in_instructions = False
    for line in raw.splitlines():
        if line.startswith("[口语回复]："):
            spoken = line[len("[口语回复]："):].strip()
        elif line.startswith("[执行指令]："):
            in_instructions = True
        elif in_instructions and line.strip():
            instruction_lines.append(line)
    return spoken, "\n".join(instruction_lines)


def generate_response(text):
    resp = llm_client.chat.completions.create(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": LLM_SYSTEM},
            {"role": "user",   "content": text},
        ],
    )
    raw = resp.choices[0].message.content.strip()
    spoken, instructions = parse_llm_response(raw)

    if instructions:
        print(f"\n✅ 标准化指令:\n{instructions}\n", flush=True)
    else:
        print(f"[LLM 原始输出]\n{raw}\n", flush=True)

    if spoken:
        print(f"🔊 语音回复：{spoken}", flush=True)
        audio_np = synthesize_speech(spoken)
        if audio_np is not None:
            tts_audio_q.put(audio_np)
    else:
        print("[警告] LLM 未生成口语回复，检查提示词格式", file=sys.stderr)


# ─────────────────────────────────────────────────────────
# ASR 结果处理
# ─────────────────────────────────────────────────────────
def handle_asr_result(text):
    global waiting_for_command

    pos = find_wake_word(text)
    if pos >= 0:
        cmd = text[pos + _WW_LEN:].strip("，。,.： ")
        if cmd:
            print(f"📋 指令原文: {cmd}", flush=True)
            print("⏳ 解析中...", flush=True)
            generate_response(cmd)
        else:
            print("👂 已唤醒，请说出指令...", flush=True)
            waiting_for_command = True
    elif waiting_for_command:
        waiting_for_command = False
        print(f"📋 指令原文: {text}", flush=True)
        print("⏳ 解析中...", flush=True)
        generate_response(text)


# ─────────────────────────────────────────────────────────
# 主音频处理循环
# ─────────────────────────────────────────────────────────
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


# ─────────────────────────────────────────────────────────
# 入口
# ─────────────────────────────────────────────────────────
def main():
    print(f"麦克风: Index={DEVICE_INDEX} | 扬声器: Index={OUTPUT_DEVICE_INDEX}（启英泰伦 USB）")
    print(f"采样率: {SAMPLE_RATE} Hz | 静音阈值 RMS: {SILENCE_THRESHOLD}")
    print(f"唤醒词: 【{WAKE_WORD}】 | TTS 音色: {TTS_VOICE}")
    print("─" * 50)
    print("说出唤醒词后下达指令，按 Ctrl+C 停止...\n")

    proc_thread = threading.Thread(target=process_loop,      daemon=True)
    tts_thread  = threading.Thread(target=tts_playback_thread, daemon=True)
    proc_thread.start()
    tts_thread.start()

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
        tts_thread.join(timeout=3)


if __name__ == "__main__":
    main()
