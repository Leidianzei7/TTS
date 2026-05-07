#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
voice_node: 音频采集 + VAD + ASR + 唤醒词检测
发布 /voice/command (std_msgs/String) — 唤醒后识别到的指令文本
发布 /voice/text    (std_msgs/String) — 所有 ASR 原始输出（调试用）
"""
import sys
import queue
import collections
import threading

import numpy as np
import sounddevice as sd
import rclpy
from rclpy.node import Node
from std_msgs.msg import String

# 将项目根目录加入路径（RDK X5 上按实际路径调整）
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))

from realtime_asr.config import (
    DEVICE_INDEX, SAMPLE_RATE, CHANNELS, CHUNK,
    SPEECH_HOLD_SEC, MIN_SPEECH_SEC, VAD_MODE,
    NOISE_INIT_SEC, NOISE_ALPHA, SPEECH_DELTA,
    VAD_AGGRESSIVENESS, VAD_FRAME_SAMPLES, VAD_FRAME_MS, VAD_SPEECH_TRIGGER,
)
from realtime_asr.asr import recognize
from realtime_asr.wake_word import find_wake_word


class VoiceNode(Node):
    def __init__(self):
        super().__init__("voice_node")

        self._cmd_pub  = self.create_publisher(String, "/voice/command", 10)
        self._text_pub = self.create_publisher(String, "/voice/text",    10)

        self._audio_q  = queue.Queue()
        self._running  = threading.Event()
        self._running.set()
        self._waiting_for_command = False

        self.get_logger().info(
            f"VAD 模式: {VAD_MODE} | 麦克风 Index={DEVICE_INDEX} | "
            f"唤醒词: 小智"
        )

    # ── 音频回调（sounddevice 调用，在独立线程）──────────────────
    def _audio_callback(self, indata, frames, time_info, status):
        if status:
            self.get_logger().warn(str(status))
        self._audio_q.put(indata[:, 0].copy())

    # ── 唤醒词 + 发布 ────────────────────────────────────────────
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

    # ── 能量 VAD 主循环 ──────────────────────────────────────────
    def _process_energy(self):
        # 简单底噪校准（无 TTS 提示，RDK X5 上 TTS 由 brain_node 处理）
        self.get_logger().info(f"校准底噪 {NOISE_INIT_SEC:.1f}s，请保持安静...")
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
        self.get_logger().info(
            f"底噪 {20*np.log10(max(noise_floor,1)):.1f} dB，"
            f"阈值 {20*np.log10(max(threshold,1)):.1f} dB，开始监听"
        )

        speech_buf    = np.array([], dtype=np.float32)
        in_speech     = False
        silence_cnt   = 0
        silence_limit = int(SPEECH_HOLD_SEC * SAMPLE_RATE / CHUNK)

        while self._running.is_set():
            try:
                chunk = self._audio_q.get(timeout=0.5)
            except queue.Empty:
                continue

            chunk = chunk.astype(np.float32)
            rms   = np.sqrt(np.mean(chunk ** 2) * (32768 ** 2))

            if rms > threshold:
                if not in_speech:
                    in_speech  = True
                    speech_buf = chunk.copy()
                    self.get_logger().info("正在聆听...")
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
                            self.get_logger().info("识别中...")
                            text = recognize(speech_buf)
                            if text.strip():
                                self.get_logger().info(f"ASR: {text}")
                                self._handle_asr(text)
                        speech_buf = np.array([], dtype=np.float32)

    # ── WebRTC VAD 主循环 ────────────────────────────────────────
    def _process_webrtc(self):
        import webrtcvad
        vad      = webrtcvad.Vad(VAD_AGGRESSIVENESS)
        pre_roll = int(200 / VAD_FRAME_MS)
        pre_buf  = collections.deque(maxlen=pre_roll)

        speech_frames = []
        in_speech     = False
        silence_cnt   = 0
        speech_cnt    = 0
        silence_limit = int(SPEECH_HOLD_SEC * 1000 / VAD_FRAME_MS)
        sample_buf    = np.array([], dtype=np.float32)

        self.get_logger().info("WebRTC VAD 就绪，开始监听")

        while self._running.is_set():
            try:
                chunk = self._audio_q.get(timeout=0.5)
            except queue.Empty:
                continue

            sample_buf = np.concatenate([sample_buf, chunk.astype(np.float32)])

            while len(sample_buf) >= VAD_FRAME_SAMPLES:
                frame      = sample_buf[:VAD_FRAME_SAMPLES]
                sample_buf = sample_buf[VAD_FRAME_SAMPLES:]
                pcm        = (frame * 32768).clip(-32768, 32767).astype(np.int16).tobytes()
                is_speech  = vad.is_speech(pcm, SAMPLE_RATE)

                if is_speech:
                    speech_cnt  += 1
                    silence_cnt  = 0
                    if not in_speech:
                        if speech_cnt >= VAD_SPEECH_TRIGGER:
                            in_speech     = True
                            speech_frames = list(pre_buf) + [frame]
                            self.get_logger().info("正在聆听...")
                    else:
                        speech_frames.append(frame)
                else:
                    speech_cnt = 0
                    if in_speech:
                        speech_frames.append(frame)
                        silence_cnt += 1
                        if silence_cnt >= silence_limit:
                            in_speech     = False
                            silence_cnt   = 0
                            audio         = np.concatenate(speech_frames)
                            speech_frames = []
                            if len(audio) / SAMPLE_RATE >= MIN_SPEECH_SEC:
                                self.get_logger().info("识别中...")
                                text = recognize(audio)
                                if text.strip():
                                    self.get_logger().info(f"ASR: {text}")
                                    self._handle_asr(text)
                    else:
                        pre_buf.append(frame)

    def start_audio(self):
        target = self._process_webrtc if VAD_MODE == "webrtc" else self._process_energy
        threading.Thread(target=target, daemon=True).start()
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
