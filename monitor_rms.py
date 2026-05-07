#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
实时监测麦克风 RMS 能量值
用于校准 config.py 中的 SILENCE_THRESHOLD 参数

运行：python3 monitor_rms.py
退出：Ctrl+C
"""

import numpy as np
import sounddevice as sd

DEVICE_INDEX    = 2
SAMPLE_RATE     = 16000
CHUNK           = 1024
THRESHOLD       = 4000   # 当前 config.py 中的值，仅用于对比显示
BAR_WIDTH       = 40     # 能量条最大宽度（字符数）
RMS_DISPLAY_MAX = 8000   # 能量条对应的满格 RMS 值


def rms(data: np.ndarray) -> float:
    return float(np.sqrt(np.mean(data.astype(np.float64) ** 2)))


def draw_bar(value: float, max_value: float, width: int, threshold: float) -> str:
    filled = int(min(value / max_value, 1.0) * width)
    bar = "#" * filled + "-" * (width - filled)
    threshold_pos = int(min(threshold / max_value, 1.0) * width)
    # 在阈值位置插入 | 标记
    bar = bar[:threshold_pos] + "|" + bar[threshold_pos + 1:]
    return bar


def main():
    print(f"设备 Index={DEVICE_INDEX}，采样率={SAMPLE_RATE}Hz")
    print(f"当前 SILENCE_THRESHOLD={THRESHOLD}（config.py 中的值，| 标记位置）")
    print("按 Ctrl+C 退出\n")

    with sd.InputStream(
        device=DEVICE_INDEX,
        channels=1,
        samplerate=SAMPLE_RATE,
        dtype="int16",
        blocksize=CHUNK,
    ) as stream:
        while True:
            data, _ = stream.read(CHUNK)
            r = rms(data)
            bar = draw_bar(r, RMS_DISPLAY_MAX, BAR_WIDTH, THRESHOLD)
            status = "语音" if r >= THRESHOLD else "静音"
            print(f"\r[{bar}] RMS={r:6.0f}  {status}   ", end="", flush=True)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n已退出。")
