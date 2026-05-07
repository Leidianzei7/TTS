#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
brain_node: LLM 推理 + TTS 播放 + 指令发布
订阅 /voice/command      (std_msgs/String) — 来自 voice_node 的用户指令
发布 /robot/instructions (std_msgs/String) — JSON 数组，每项格式：
    {"cmd": "move_forward", "params": {"speed": 0.2, "distance": 1.0}}
"""
import sys
import json
import queue
import threading

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))

from realtime_asr.llm import generate_response, _SYSTEM_PROMPT
from realtime_asr.tts import stream_play


class BrainNode(Node):
    def __init__(self):
        super().__init__("brain_node")

        self._instr_pub = self.create_publisher(String, "/robot/instructions", 10)
        self.create_subscription(String, "/voice/command", self._on_command, 10)

        # 串行工作队列：避免 LLM 并发调用
        self._work_q = queue.Queue()
        threading.Thread(target=self._work_loop, daemon=True).start()

        self.get_logger().info("brain_node 就绪，等待 /voice/command")
        self.get_logger().debug(f"系统提示词前100字：{_SYSTEM_PROMPT[:100]}")

    def _on_command(self, msg: String):
        self._work_q.put(msg.data)

    def _work_loop(self):
        while True:
            cmd = self._work_q.get()
            self.get_logger().info(f"收到指令: {cmd}")
            try:
                spoken, commands = generate_response(cmd, system_prompt=_SYSTEM_PROMPT)

                if spoken:
                    self.get_logger().info(f"语音回复: {spoken}")
                    stream_play(spoken)

                if commands:
                    payload = json.dumps(commands, ensure_ascii=False)
                    self.get_logger().info(f"发布指令: {payload}")
                    msg = String()
                    msg.data = payload
                    self._instr_pub.publish(msg)
                else:
                    self.get_logger().info("无机械指令")

            except Exception as e:
                self.get_logger().error(f"处理指令失败: {e}")


def main():
    rclpy.init()
    node = BrainNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
