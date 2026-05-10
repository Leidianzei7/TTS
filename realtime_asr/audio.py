#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
音频管道：开麦 → 重采样到 16k → VAD → ASR → 通过回调吐出文本。

run_audio_pipeline(on_asr_text, log, running)
    on_asr_text: Callable[[str], None] — 每段识别结果（VAD 切完后）的回调
    log:         Callable[[str], None] — 日志函数（print 或 ros logger）
    running:     threading.Event — 为 None 时使用 state.running

handle_asr_result / _dispatch_command 是 main.py 用的"唤醒词 + LLM 派发"逻辑，
ros_voice/voice_node.py 不应使用，它有自己的 ROS topic 派发逻辑。
"""
import sys
import json
import queue
import numpy as np
import sounddevice as sd
from scipy import signal as scipy_signal
from .config import (
    DEVICE_INDEX, SAMPLE_RATE, HW_SAMPLE_RATE, CHANNELS, CHUNK,
    NOISE_INIT_SEC, SPEECH_DELTA, VAD_MODE,
)
from . import state as _state
from .asr import recognize
from .vad import run_vad


def _drain(q):
    while not q.empty():
        try:
            q.get_nowait()
        except queue.Empty:
            break


def _calibrate_noise(audio_q, log):
    from .tts import stream_play
    log("🔇 即将校准底噪，请保持安静...")
    stream_play("请保持安静，正在校准底噪")
    _drain(audio_q)  # 丢掉 TTS 期间采集到的回声

    log(f"🔇 校准中（{NOISE_INIT_SEC:.1f}秒）...")
    init_chunks = int(NOISE_INIT_SEC * SAMPLE_RATE / CHUNK)
    samples = []
    for _ in range(init_chunks):
        try:
            chunk = audio_q.get(timeout=1.0)
            rms   = np.sqrt(np.mean(chunk.astype(np.float32) ** 2) * (32768 ** 2))
            samples.append(rms)
        except queue.Empty:
            pass

    noise_floor = float(np.median(samples)) if samples else 500.0
    threshold   = noise_floor + SPEECH_DELTA
    db          = lambda r: 20 * np.log10(max(r, 1))
    log(f"📊 底噪 {db(noise_floor):.1f} dB，检测阈值 {db(threshold):.1f} dB")

    stream_play("校准完成，可以开始说话了")
    _drain(audio_q)
    return noise_floor


def run_audio_pipeline(on_asr_text, log=print, running=None):
    if running is None:
        running = _state.running

    audio_q = queue.Queue()

    def _callback(indata, frames, time_info, status):
        if status:
            log(f"[音频状态] {status}")
        chunk = scipy_signal.resample_poly(indata[:, 0], up=1, down=3).astype(np.float32)
        audio_q.put(chunk.copy())

    with sd.InputStream(
        device=DEVICE_INDEX,
        samplerate=HW_SAMPLE_RATE,
        channels=CHANNELS,
        dtype="float32",
        blocksize=CHUNK * 3,
        callback=_callback,
    ):
        noise_floor = 0.0
        if VAD_MODE != "webrtc":
            noise_floor = _calibrate_noise(audio_q, log)

        def _on_speech(audio):
            log("⏳ 识别中...")
            text = recognize(audio)
            if text.strip():
                log(f"🗣  {text}")
                on_asr_text(text)
            else:
                log("（未识别到有效内容）")

        run_vad(audio_q, running, _on_speech, log, noise_floor)


# ── 仅 main.py 使用：唤醒词 + LLM 派发 ───────────────────────
from .wake_word import find_wake_word
from .llm import generate_response


def _dispatch_command(cmd):
    print(f"📋 指令原文: {cmd}", flush=True)
    print("⏳ 解析中...", flush=True)
    spoken, commands = generate_response(cmd)
    if spoken:
        print(f"🔊 语音回复：{spoken}", flush=True)
        _state.tts_text_q.put(spoken)
    if commands:
        print(f"\n✅ 标准化指令:\n{json.dumps(commands, ensure_ascii=False, indent=2)}\n", flush=True)
    elif not spoken:
        print("[警告] LLM 回复解析失败", flush=True)


def handle_asr_result(text):
    pos, ww_len = find_wake_word(text)
    if pos >= 0:
        cmd = text[pos + ww_len:].strip("，。,.： ")
        if cmd:
            _dispatch_command(cmd)
        else:
            print("👂 已唤醒，请说出指令...", flush=True)
            _state.waiting_for_command = True
    elif _state.waiting_for_command:
        _state.waiting_for_command = False
        _dispatch_command(text)
