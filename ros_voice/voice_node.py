#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
voice_node: 音频采集 + VAD + ASR + 唤醒词检测
发布 /voice/command (std_msgs/String) — 唤醒后识别到的指令文本
发布 /voice/text    (std_msgs/String) — 所有 ASR 原始输出（调试用）
"""
import sys
import queue
import threading
from pathlib import Path

import numpy as np
import sounddevice as sd
import rclpy
from rclpy.node import Node
from std_msgs.msg import String

sys.path.insert(0, str(Path(__file__).parent.parent))

from realtime_asr.config import (
    DEVICE_INDEX, SAMPLE_RATE, CHANNELS, CHUNK,
    NOISE_INIT_SEC, SPEECH_DELTA, VAD_MODE,
)
from realtime_asr.asr import recognize
from realtime_asr.wake_word import find_wake_word
from realtime_asr.vad import run_vad
from realtime_asr.tts import stream_play


class VoiceNode(Node):
    def __init__(self):
        super().__init__("voice_node")

        self._cmd_pub  = self.create_publisher(String, "/voice/command", 10)
        self._text_pub = self.create_publisher(String, "/voice/text",    10)

        self._audio_q = queue.Queue()
        self._running = threading.Event()
        self._running.set()
        self._waiting_for_command = False

        self.get_logger().info(
            f"VAD 模式: {VAD_MODE} | 麦克风 Index={DEVICE_INDEX} | 唤醒词: 小智"
        )

    def _audio_callback(self, indata, frames, time_info, status):
        if status:
            self.get_logger().warn(str(status))
        self._audio_q.put(indata[:, 0].copy())

    def _handle_asr(self, text):
        msg = String()
        msg.data = text
        self._text_pub.publish(msg)

        pos, ww_len = find_wake_word(text)
        if pos >= 0:
            cmd = text[pos + ww_len:].strip("，。,.： ")
            if cmd:
                self.get_logger().info(f"指令: {cmd}")
                cmd_msg = String()
                cmd_msg.data = cmd
                self._cmd_pub.publish(cmd_msg)
            else:
                self.get_logger().info("已唤醒，等待指令...")
                self._waiting_for_command = True
        elif self._waiting_for_command:
            self._waiting_for_command = False
            self.get_logger().info(f"指令: {text}")
            cmd_msg = String()
            cmd_msg.data = text
            self._cmd_pub.publish(cmd_msg)

    def _calibrate_noise(self) -> float:
        stream_play("请保持安静，正在校准底噪")

        # 清空 TTS 播放期间采集到的音频（含回声）
        while not self._audio_q.empty():
            try:
                self._audio_q.get_nowait()
            except queue.Empty:
                break

        self.get_logger().info(f"校准中（{NOISE_INIT_SEC:.1f}s）...")
        init_chunks = int(NOISE_INIT_SEC * SAMPLE_RATE / CHUNK)
        samples = []
        for _ in range(init_chunks):
            try:
                chunk = self._audio_q.get(timeout=1.0)
                rms = np.sqrt(np.mean(chunk.astype(np.float32) ** 2) * (32768 ** 2))
                samples.append(rms)
            except queue.Empty:
                pass
        noise_floor = float(np.median(samples)) if samples else 500.0
        threshold   = noise_floor + SPEECH_DELTA
        db = lambda r: 20 * np.log10(max(r, 1))
        self.get_logger().info(
            f"底噪 {db(noise_floor):.1f} dB，阈值 {db(threshold):.1f} dB"
        )
        stream_play("校准完成，可以开始说话了")
        return noise_floor

    def _vad_thread(self):
        noise_floor = self._calibrate_noise() if VAD_MODE != "webrtc" else 500.0

        def _on_speech(audio):
            self.get_logger().info("识别中...")
            text = recognize(audio)
            if text.strip():
                self.get_logger().info(f"ASR: {text}")
                self._handle_asr(text)

        run_vad(self._audio_q, self._running, _on_speech, self.get_logger().info, noise_floor)

    def start_audio(self):
        threading.Thread(target=self._vad_thread, daemon=True).start()
        return sd.InputStream(
            device=DEVICE_INDEX,
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype="float32",
            blocksize=CHUNK,
            callback=self._audio_callback,
        )

    def stop(self):
        self._running.clear()


def main():
    rclpy.init()
    node = VoiceNode()
    with node.start_audio():
        try:
            rclpy.spin(node)
        except KeyboardInterrupt:
            pass
        finally:
            node.stop()
            node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
