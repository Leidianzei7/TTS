#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import time
import threading
import sounddevice as sd
from .config import (
    DEVICE_INDEX, OUTPUT_DEVICE_INDEX, SAMPLE_RATE, HW_SAMPLE_RATE, CHANNELS, CHUNK,
    WAKE_WORD, TTS_VOICE,
)
from . import state as _state
from .audio import audio_callback, process_loop
from .tts import tts_playback_thread


def main():
    print(f"麦克风: Index={DEVICE_INDEX} | 扬声器: Index={OUTPUT_DEVICE_INDEX}（启英泰伦 USB）")
    print(f"采样率: {SAMPLE_RATE} Hz | 阈值: 动态自适应")
    print(f"唤醒词: 【{WAKE_WORD}】 | TTS 音色: {TTS_VOICE}")
    print("─" * 50)
    print("说出唤醒词后下达指令，按 Ctrl+C 停止...\n")

    proc_thread = threading.Thread(target=process_loop,        daemon=True)
    tts_thread  = threading.Thread(target=tts_playback_thread, daemon=True)
    proc_thread.start()
    tts_thread.start()

    try:
        with sd.InputStream(
            device=DEVICE_INDEX,
            samplerate=HW_SAMPLE_RATE,
            channels=CHANNELS,
            dtype="float32",
            blocksize=CHUNK * 3,
            callback=audio_callback,
        ):
            while _state.running.is_set():
                time.sleep(0.1)
    except KeyboardInterrupt:
        print("\n\n停止识别。")
    except Exception as e:
        print(f"\n音频设备错误: {e}")
    finally:
        _state.running.clear()
        proc_thread.join(timeout=3)
        tts_thread.join(timeout=3)


if __name__ == "__main__":
    main()
