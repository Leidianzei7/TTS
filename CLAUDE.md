# TTS / 实时语音识别项目

> 每次功能变更后更新此文件，保持简洁，重点记录进度和思路变化。
> 对话变长时提醒用户执行 `/compact` 压缩上下文以节省 token。

## 硬件
- 启英泰伦 USB 声音模块，sounddevice Index=2（麦克风）/ Index=1（扬声器）

## 技术栈
- 音频采集：sounddevice（macOS 无 portaudio，弃用 pyaudio）
- VAD：双模式可切换（见下方关键参数）
- 语音识别：FunASR SenseVoiceSmall + fsmn-vad，CPU 推理，直接传 numpy array
- LLM：阿里云 DashScope Qwen（qwen-turbo），OpenAI 兼容格式，流式输出
- TTS：DashScope CosyVoice v2，流式合成边合成边播，首字出声 ~100ms
- Python 3.11，venv 在项目根目录 `venv/`（系统 Python 3.14 缺依赖，勿用）

## 当前进度
- [x] 设备检测与录音验证
- [x] 实时采集 → VAD → SenseVoiceSmall → 屏幕打印
- [x] 唤醒词触发（支持单个"小智"及近同音容错）→ ASR → Qwen LLM → 指令输出
- [x] TTS 语音回复（流式，低延迟）
- [x] 代码拆分为 `realtime_asr/` 包（config / audio / vad / asr / llm / tts / wake_word / state / commands）
- [ ] 视觉多模态扩展

## 分支工作流

| 分支 | 用途 |
|---|---|
| `main` | 主开发分支，功能直接提交到此 |
| `mac_snapshot` | Mac 本机环境快照（Python 3.11 venv），不 merge 回 main |

历史备注：`asrdev` / `rosdev` 已删除（远程及本地均已移除）。`mac_complete` 为 ROS 改造前快照，已删除。

## 所需库（直接依赖）
| 库 | 用途 |
|---|---|
| sounddevice | 音频采集与播放 |
| numpy | 音频数据处理 |
| torch / torchaudio | FunASR 推理后端 |
| funasr | SenseVoiceSmall ASR + fsmn-vad |
| openai | DashScope LLM（OpenAI 兼容格式） |
| dashscope | CosyVoice v2 TTS |
| pypinyin | 唤醒词拼音容错匹配 |
| webrtcvad | WebRTC VAD 模式（可选） |

完整依赖见 `requirements.txt`，用 `pip install -r requirements.txt` 一键安装。

## 研发思路
参考代码（ref codes/）覆盖：录音、VAD、ASR、LLM对话、TTS合成、多模态视觉。
演进路径：录音验证 → 实时ASR → 接入LLM对话 → TTS语音回复 → 视觉多模态扩展

## 运行
```bash
source venv/bin/activate   # 激活虚拟环境（每个新终端窗口执行一次）
python3 main.py            # Ctrl+C 退出
```

## 关键参数（realtime_asr/config.py）
| 参数 | 默认值 | 说明 |
|------|--------|------|
| DEVICE_INDEX | 2 | 麦克风设备 |
| OUTPUT_DEVICE_INDEX | 1 | 扬声器设备 |
| VAD_MODE | "energy" | VAD 模式："energy" 或 "webrtc" |
| SPEECH_HOLD_SEC | 1.2 | 停顿多久触发识别（秒） |
| WAKE_WORD | 小智小智 | 主唤醒词 |
| WAKE_WORD_SHORT | 小智 | 单次唤醒词（含近同音容错） |
| LLM_MODEL | qwen-turbo | DashScope 模型 |
| TTS_VOICE | longxiaochun_v2 | CosyVoice v2 音色 |

### VAD_MODE = "energy"（默认）
| 参数 | 默认值 | 说明 |
|------|--------|------|
| NOISE_INIT_SEC | 1.5 | 启动校准时长（秒），TTS 提示后采样中位数 |
| NOISE_ALPHA | 0.01 | 底噪 EMA 更新速率 |
| SPEECH_DELTA | 5000 | 阈值 = 底噪 RMS + 此值 |
| MIN_SPEECH_SEC | 0.3 | 有效语音最短时长（秒），低于此值丢弃 |

### VAD_MODE = "webrtc"（无需校准）
| 参数 | 默认值 | 说明 |
|------|--------|------|
| VAD_AGGRESSIVENESS | 3 | 0-3，越高越激进，3 适合空调环境 |
| VAD_SPEECH_TRIGGER | 3 | 连续 N 帧（×20ms）确认语音才录制 |
