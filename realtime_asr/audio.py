#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import queue
import collections
import numpy as np
from .config import (SAMPLE_RATE, CHUNK, SPEECH_HOLD_SEC, MIN_SPEECH_SEC, VAD_MODE,
                     NOISE_INIT_SEC, NOISE_ALPHA, SPEECH_DELTA,
                     VAD_AGGRESSIVENESS, VAD_FRAME_SAMPLES, VAD_FRAME_MS, VAD_SPEECH_TRIGGER)
from . import state as _state
from .asr import recognize
from .wake_word import find_wake_word
from .llm import generate_response


def audio_callback(indata, frames, time_info, status):
    if status:
        print(f"[音频状态] {status}", file=sys.stderr)
    _state.audio_q.put(indata[:, 0].copy())


def _dispatch_command(cmd):
    import json as _json
    print(f"📋 指令原文: {cmd}", flush=True)
    print("⏳ 解析中...", flush=True)
    spoken, commands = generate_response(cmd)
    if spoken:
        print(f"🔊 语音回复：{spoken}", flush=True)
        _state.tts_text_q.put(spoken)
    if commands:
        print(f"\n✅ 标准化指令:\n{_json.dumps(commands, ensure_ascii=False, indent=2)}\n", flush=True)
    elif not spoken:
        print("[警告] LLM 回复解析失败", flush=True)


def handle_asr_result(text):
    pos, ww_len = find_wake_word(text)
    if pos >= 0:
        cmd = text[pos + ww_len :].strip("，。,.： ")
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

    # 语音提示用户保持安静
    print("🔇 即将校准底噪，请保持安静...", flush=True)
    stream_play("请保持安静，正在校准底噪")

    # 清空 TTS 播放期间采集到的音频（含回声）
    while not _state.audio_q.empty():
        try:
            _state.audio_q.get_nowait()
        except queue.Empty:
            break

    # 采样，用中位数对偶发噪声免疫
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


def _process_energy():
    from .tts import stream_play
    noise_floor = _sample_noise_floor()
    threshold   = noise_floor + SPEECH_DELTA
    db = lambda r: 20 * np.log10(max(r, 1))
    print(f"📊 底噪 {db(noise_floor):.1f} dB，检测阈值 {db(threshold):.1f} dB\n", flush=True)
    stream_play("校准完成，可以开始说话了")

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

        if rms > threshold:
            if not in_speech:
                in_speech  = True
                speech_buf = chunk.copy()
                print("🎤 正在聆听...", flush=True)
            else:
                speech_buf = np.concatenate([speech_buf, chunk])
            silence_cnt = 0
        else:
            if not in_speech:
                noise_floor = NOISE_ALPHA * rms + (1 - NOISE_ALPHA) * noise_floor
                threshold   = noise_floor + SPEECH_DELTA
            if in_speech:
                speech_buf  = np.concatenate([speech_buf, chunk])
                silence_cnt += 1
                if silence_cnt >= silence_limit:
                    in_speech   = False
                    silence_cnt = 0
                    if len(speech_buf) / SAMPLE_RATE >= MIN_SPEECH_SEC:
                        print("⏳ 识别中...", flush=True)
                        text = recognize(speech_buf)
                        if text.strip():
                            print(f"🗣  {text}", flush=True)
                            handle_asr_result(text)
                        else:
                            print("（未识别到有效内容）\n", flush=True)
                    speech_buf = np.array([], dtype=np.float32)


def _process_webrtc():
    import webrtcvad
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


def process_loop():
    if VAD_MODE == "webrtc":
        _process_webrtc()
    else:
        _process_energy()
