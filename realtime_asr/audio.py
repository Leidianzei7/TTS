#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import queue
import numpy as np
from .config import SAMPLE_RATE, CHUNK, SILENCE_THRESHOLD, SPEECH_HOLD_SEC, MIN_SPEECH_SEC, _WW_LEN
from . import state as _state
from .asr import recognize
from .wake_word import find_wake_word
from .llm import generate_response


def audio_callback(indata, frames, time_info, status):
    if status:
        print(f"[音频状态] {status}", file=sys.stderr)
    _state.audio_q.put(indata[:, 0].copy())


def handle_asr_result(text):
    pos = find_wake_word(text)
    if pos >= 0:
        cmd = text[pos + _WW_LEN :].strip("，。,.： ")
        if cmd:
            print(f"📋 指令原文: {cmd}", flush=True)
            print("⏳ 解析中...", flush=True)
            generate_response(cmd)
        else:
            print("👂 已唤醒，请说出指令...", flush=True)
            _state.waiting_for_command = True
    elif _state.waiting_for_command:
        _state.waiting_for_command = False
        print(f"📋 指令原文: {text}", flush=True)
        print("⏳ 解析中...", flush=True)
        generate_response(text)


def process_loop():
    speech_buf    = np.array([], dtype=np.float32)
    in_speech     = False
    silence_cnt   = 0
    silence_limit = int(SPEECH_HOLD_SEC * SAMPLE_RATE / CHUNK)

    while _state.running.is_set():
        try:
            chunk = _state.audio_q.get(timeout=0.5)
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
