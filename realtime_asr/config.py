#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from pypinyin import lazy_pinyin
from dashscope.audio.tts_v2 import AudioFormat

# ── 设备配置 ──────────────────────────────────────────────
# 运行 `python3 -c "import sounddevice as sd; print(sd.query_devices())"` 查看设备列表
DEVICE_INDEX        = 2      # 麦克风输入设备编号（USB PnP 输入端）
OUTPUT_DEVICE_INDEX = 1      # 扬声器输出设备编号（USB PnP 输出端，同一物理模块）
SAMPLE_RATE         = 16000  # SenseVoiceSmall 要求 16kHz
CHANNELS            = 1
CHUNK               = 1024   # 每次读取帧数，越小延迟越低

# ── VAD 参数 ──────────────────────────────────────────────
SILENCE_THRESHOLD = 4000  # RMS 能量阈值，环境噪大时调高（1500-2000）
SPEECH_HOLD_SEC   = 1.0   # 停顿多久后触发识别（秒）
MIN_SPEECH_SEC    = 0.3   # 有效语音最短时长（秒），低于此值丢弃

# ── 唤醒词 ────────────────────────────────────────────────
WAKE_WORD  = "小智小智"
_WW_LEN    = len(WAKE_WORD)
_WW_PINYIN = "".join(lazy_pinyin(WAKE_WORD))  # 拼音版本，用于近同音字容错匹配

# ── LLM 配置 ──────────────────────────────────────────────
LLM_API_KEY  = "sk-1c3077000f6347858d88c0936169d5af"
LLM_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
LLM_MODEL    = "qwen-turbo"   # 可换 qwen-plus（更准）或 qwen-max（最强，更慢）
LLM_SYSTEM   = (
    "你是小智，一个智能语音助手。用户用语音下达指令，你必须严格按以下格式回复，"
    "第一行必须是口语回复，第二行才是指令：\n"
    "[口语回复]：<用自然口语化的1句话回应用户>\n"
    "[执行指令]：\n"
    "1. 动作一\n"
    "2. 动作二\n\n"
    "规则：[口语回复]必须在第一行且只占一行；只输出这两个部分，不要任何额外说明。"
)

# ── TTS 配置 ──────────────────────────────────────────────
# 可用中文音色（CosyVoice v2）：
#   longxiaochun_v2（男，成熟）longxiaoxia_v2（女，温柔）
#   longxiaobai_v2（男，活泼）longxiaomiao_v2（女，知性）
TTS_VOICE       = "longxiaochun_v2"
TTS_SAMPLE_RATE = 16000
TTS_FORMAT      = AudioFormat.WAV_16000HZ_MONO_16BIT
