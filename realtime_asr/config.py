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
SPEECH_HOLD_SEC = 1.2   # 停顿多久后触发识别（秒）
MIN_SPEECH_SEC  = 0.3   # 有效语音最短时长（秒），低于此值丢弃

# ── VAD 模式选择 ───────────────────────────────────────────
# "energy" : 启动时校准底噪，阈值 = 底噪 + SPEECH_DELTA，动态跟随环境变化
# "webrtc"  : Google WebRTC VAD，无需校准，基于频谱特征，稳态噪声下可能误判
VAD_MODE = "energy"

# 能量阈值 VAD（VAD_MODE = "energy"）
NOISE_INIT_SEC  = 1.5   # 启动校准时长（秒），期间请保持安静
NOISE_ALPHA     = 0.01  # 底噪 EMA 更新速率（越小越平滑）
SPEECH_DELTA    = 3000  # 阈值 = 底噪 + 此值，根据说话音量调整

# WebRTC VAD（VAD_MODE = "webrtc"，无需校准）
VAD_AGGRESSIVENESS = 3    # 0-3，越高对噪声越激进
VAD_FRAME_MS       = 20   # 每帧时长，只能是 10/20/30
VAD_FRAME_SAMPLES  = SAMPLE_RATE * VAD_FRAME_MS // 1000
VAD_SPEECH_TRIGGER = 3    # 连续 N 帧判定为语音才开始录制

# ── 唤醒词 ────────────────────────────────────────────────
WAKE_WORD       = "小智小智"
WAKE_WORD_SHORT = "小智"
_WW_LEN         = len(WAKE_WORD)
_WWS_LEN        = len(WAKE_WORD_SHORT)
_WW_PINYIN      = "".join(lazy_pinyin(WAKE_WORD))       # "xiaozhixiaozhi"
_WWS_PINYIN     = "".join(lazy_pinyin(WAKE_WORD_SHORT)) # "xiaozhi"

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
