#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
voice_node: 音频采集 + VAD + ASR + 唤醒词检测
发布 /voice/command (std_msgs/String) — 唤醒后识别到的指令文本
发布 /voice/text    (std_msgs/String) — 所有 ASR 原始输出（调试用）

音频管道（开麦 / 重采样 / 校准 / VAD / ASR）全部委托给
realtime_asr.audio.run_audio_pipeline，本节点只负责 ROS topic 派发。
"""
import sys
import threading
from pathlib import Path

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

sys.path.insert(0, str(Path(__file__).parent.parent))

from realtime_asr.config import DEVICE_INDEX, VAD_MODE
from realtime_asr.audio import run_audio_pipeline
from realtime_asr.wake_word import find_wake_word


class VoiceNode(Node):
    def __init__(self):
        super().__init__("voice_node")
        self._cmd_pub  = self.create_publisher(String, "/voice/command", 10)
        self._text_pub = self.create_publisher(String, "/voice/text",    10)

        self._running             = threading.Event()
        self._running.set()
        self._waiting_for_command = False

        self.get_logger().info(
            f"VAD 模式: {VAD_MODE} | 麦克风 Index={DEVICE_INDEX} | 唤醒词: 小智"
        )

    def _on_asr_text(self, text: str):
        self._text_pub.publish(String(data=text))

        pos, ww_len = find_wake_word(text)
        if pos >= 0:
            cmd = text[pos + ww_len:].strip("，。,.： ")
            if cmd:
                self.get_logger().info(f"指令: {cmd}")
                self._cmd_pub.publish(String(data=cmd))
            else:
                self.get_logger().info("已唤醒，等待指令...")
                self._waiting_for_command = True
        elif self._waiting_for_command:
            self._waiting_for_command = False
            self.get_logger().info(f"指令: {text}")
            self._cmd_pub.publish(String(data=text))

    def start(self):
        threading.Thread(
            target=run_audio_pipeline,
            kwargs={
                "on_asr_text": self._on_asr_text,
                "log":         self.get_logger().info,
                "running":     self._running,
            },
            daemon=True,
        ).start()

    def stop(self):
        self._running.clear()


def main():
    rclpy.init()
    node = VoiceNode()
    node.start()
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
