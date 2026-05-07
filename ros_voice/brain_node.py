#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
brain_node: LLM 推理 + TTS 播放 + 指令发布
订阅 /voice/command    (std_msgs/String) — 来自 voice_node 的用户指令
发布 /robot/instructions (std_msgs/String) — JSON 数组，每项为一条机器人指令
"""
import sys
import json
import threading

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))

from realtime_asr.llm import generate_response
from realtime_asr.tts import stream_play


class BrainNode(Node):
    def __init__(self):
        super().__init__("brain_node")

        self._instr_pub = self.create_publisher(String, "/robot/instructions", 10)
        self.create_subscription(String, "/voice/command", self._on_command, 10)

        # 串行执行队列，避免 LLM 并发调用
        self._work_q  = __import__("queue").Queue()
        self._worker  = threading.Thread(target=self._work_loop, daemon=True)
        self._worker.start()

        self.get_logger().info("brain_node 就绪，等待 /voice/command")

    def _on_command(self, msg: String):
        self._work_q.put(msg.data)

    def _work_loop(self):
        while True:
            cmd = self._work_q.get()
            self.get_logger().info(f"收到指令: {cmd}")
            try:
                spoken, instructions = generate_response(cmd)

                if spoken:
                    self.get_logger().info(f"语音回复: {spoken}")
                    # TTS 阻塞播放，在工作线程中执行不影响 ROS spin
                    stream_play(spoken)

                if instructions:
                    self.get_logger().info(
                        "标准化指令:\n" + "\n".join(instructions)
                    )
                    instr_msg = String()
                    instr_msg.data = json.dumps(instructions, ensure_ascii=False)
                    self._instr_pub.publish(instr_msg)

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
