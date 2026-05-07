#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import queue
import collections
import numpy as np
import webrtcvad
from .config import (SAMPLE_RATE, SPEECH_HOLD_SEC, MIN_SPEECH_SEC,
                     VAD_AGGRESSIVENESS, VAD_FRAME_SAMPLES, VAD_FRAME_MS, VAD_SPEECH_TRIGGER)
from . import state as _state
from .asr import recognize
from .wake_word import find_wake_word
from .llm import generate_response


def audio_callback(indata, frames, time_info, status):
    if status:
        print(f"[音频状态] {status}", file=sys.stderr)
    _state.audio_q.put(indata[:, 0].copy())


def handle_asr_result(text):
    pos, ww_len = find_wake_word(text)
    if pos >= 0:
        cmd = text[pos + ww_len :].strip("，。,.： ")
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
    vad = webrtcvad.Vad(VAD_AGGRESSIVENESS)

    pre_roll = int(200 / VAD_FRAME_MS)
    pre_buf  = collections.deque(maxlen=pre_roll)

    speech_frames = []
    in_speech     = False
    silence_cnt   = 0
    speech_cnt    = 0
    silence_limit = int(SPEECH_HOLD_SEC * 1000 / VAD_FRAME_MS)
    sample_buf    = np.array([], dtype=np.float32)

    while _state.running.is_set():
        try:
            chunk = _state.audio_q.get(timeout=0.5)
        except queue.Empty:
            continue

        sample_buf = np.concatenate([sample_buf, chunk.astype(np.float32)])

        while len(sample_buf) >= VAD_FRAME_SAMPLES:
            frame      = sample_buf[:VAD_FRAME_SAMPLES]
            sample_buf = sample_buf[VAD_FRAME_SAMPLES:]

            pcm       = (frame * 32768).clip(-32768, 32767).astype(np.int16).tobytes()
            is_speech = vad.is_speech(pcm, SAMPLE_RATE)

            if is_speech:
                speech_cnt += 1
                silence_cnt  = 0
                if not in_speech:
                    if speech_cnt >= VAD_SPEECH_TRIGGER:
                        in_speech     = True
                        speech_frames = list(pre_buf) + [frame]
                        print("🎤 正在聆听...", flush=True)
                else:
                    speech_frames.append(frame)
            else:
                speech_cnt = 0
                if in_speech:
                    speech_frames.append(frame)
                    silence_cnt += 1
                    if silence_cnt >= silence_limit:
                        in_speech   = False
                        silence_cnt = 0
                        audio       = np.concatenate(speech_frames)
                        speech_frames = []
                        if len(audio) / SAMPLE_RATE >= MIN_SPEECH_SEC:
                            print("⏳ 识别中...", flush=True)
                            text = recognize(audio)
                            if text.strip():
                                print(f"🗣  {text}", flush=True)
                                handle_asr_result(text)
                            else:
                                print("（未识别到有效内容）\n", flush=True)
                else:
                    pre_buf.append(frame)
