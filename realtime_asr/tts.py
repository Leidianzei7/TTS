#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import io
import queue
import sounddevice as sd
import soundfile as sf
import dashscope
from dashscope.audio.tts_v2 import SpeechSynthesizer
from .config import TTS_VOICE, TTS_FORMAT, TTS_SAMPLE_RATE, OUTPUT_DEVICE_INDEX, LLM_API_KEY
from . import state as _state

dashscope.api_key = LLM_API_KEY


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


def tts_playback_thread():
    while _state.running.is_set():
        try:
            audio_np = _state.tts_audio_q.get(timeout=0.5)
        except queue.Empty:
            continue

        try:
            sd.play(audio_np, samplerate=TTS_SAMPLE_RATE, device=OUTPUT_DEVICE_INDEX)
            sd.wait()
        except Exception as e:
            print(f"[播放错误] {e}", file=sys.stderr)
