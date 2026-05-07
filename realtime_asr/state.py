#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
共享可变状态：所有模块通过 `import realtime_asr.state as _state` 读写此处的变量，
避免循环导入，也使状态边界清晰可见。
"""
import queue
import threading

# 音频采集队列：audio_callback → process_loop
audio_q = queue.Queue()

# TTS 待播音频队列：generate_response → tts_playback_thread
tts_audio_q = queue.Queue()

# 主循环运行标志
running = threading.Event()
running.set()

# 唤醒后等待指令的标志
waiting_for_command = False
