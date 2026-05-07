#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import json
import queue
import numpy as np
from .config import (SAMPLE_RATE, CHUNK, NOISE_INIT_SEC, NOISE_ALPHA,
                     SPEECH_DELTA, VAD_MODE)
from . import state as _state
from .asr import recognize
from .wake_word import find_wake_word
from .llm import generate_response
from .vad import run_vad


def audio_callback(indata, frames, time_info, status):
    if status:
        print(f"[音频状态] {status}", file=sys.stderr)
    _state.audio_q.put(indata[:, 0].copy())


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


def _sample_noise_floor():
    from .tts import stream_play
    print("🔇 即将校准底噪，请保持安静...", flush=True)
    stream_play("请保持安静，正在校准底噪")

    # 清空 TTS 播放期间采集到的音频（含回声）
    while not _state.audio_q.empty():
        try:
            _state.audio_q.get_nowait()
        except queue.Empty:
            break

    init_chunks = int(NOISE_INIT_SEC * SAMPLE_RATE / CHUNK)
    samples = []
    print(f"🔇 校准中（{NOISE_INIT_SEC:.1f}秒）...", flush=True)
    for _ in range(init_chunks):
        try:
            chunk = _state.audio_q.get(timeout=1.0)
            rms = np.sqrt(np.mean(chunk.astype(np.float32) ** 2) * (32768 ** 2))
            samples.append(rms)
        except queue.Empty:
            pass
    return float(np.median(samples)) if samples else 0.0


def _on_speech(audio):
    print("⏳ 识别中...", flush=True)
    text = recognize(audio)
    if text.strip():
        print(f"🗣  {text}", flush=True)
        handle_asr_result(text)
    else:
        print("（未识别到有效内容）\n", flush=True)


def process_loop():
    noise_floor = 0.0
    if VAD_MODE != "webrtc":
        from .tts import stream_play
        noise_floor = _sample_noise_floor()
        threshold   = noise_floor + SPEECH_DELTA
        db = lambda r: 20 * np.log10(max(r, 1))
        print(f"📊 底噪 {db(noise_floor):.1f} dB，检测阈值 {db(threshold):.1f} dB\n", flush=True)
        stream_play("校准完成，可以开始说话了")
        # 清空 TTS 播放期间麦克风采集到的回声/环境音，防止 VAD 误判
        while not _state.audio_q.empty():
            try:
                _state.audio_q.get_nowait()
            except queue.Empty:
                break

    run_vad(_state.audio_q, _state.running, _on_speech, print, noise_floor)
