# TTS / 实时语音识别项目

> 每次功能变更后更新此文件，保持简洁，重点记录进度和思路变化。
> 对话变长时提醒用户执行 `/compact` 压缩上下文以节省 token。

## 硬件
- 启英泰伦 USB 声音模块，Index=1（USB PnP Audio Device，硬件 48kHz），代码内 scipy 重采样 48k↔16k

## 技术栈
- 运行平台：Linux（wheeltec 机器人），Python 3.10，无 conda 环境
- 音频采集：sounddevice，48kHz 硬件采集，scipy `resample_poly` 软件重采样到 16k 喂 ASR；TTS 16k PCM 反向上采样到 48k 播放
- VAD：能量阈值 / WebRTC 双模式可切换（见下方关键参数）
- 语音识别：FunASR SenseVoiceSmall + fsmn-vad，CPU 推理。**流程是"流式 VAD + 离线 ASR"——VAD 切完整段后整段送入推理**
- LLM：阿里云 DashScope Qwen（qwen-turbo），OpenAI 兼容格式，流式输出
- TTS：DashScope CosyVoice v2，**单片 PCM 到达即重采样并播放**（首字 ~150ms）

## 当前进度
- [x] 设备检测与录音验证
- [x] 实时采集 → VAD → SenseVoiceSmall → 屏幕打印
- [x] 唤醒词触发（支持单个"小智"及近同音容错）→ ASR → Qwen LLM → 指令输出
- [x] TTS 语音回复（流式播放，单片重采样到 48k 即写入声卡）
- [x] 代码拆分为 `realtime_asr/` 包（config / audio / asr / llm / tts / wake_word / state）

## 经验与坑
- **流式 ASR 不能只换模型**：试过把 `asr.py` 的 SenseVoice 换成 `paraformer-zh-streaming`，CPU 上反而慢得多（chunk 切片后每片都重算 encoder 上下文）。要拿到流式收益，必须把 `audio.py` / `vad.py` 改成"边采边喂 ASR"。否则维持 SenseVoice 一段一次推理是最优解
- **延迟瓶颈不在 ASR**：当前感知延迟主要来自 `SPEECH_HOLD_SEC=1.2s` 静音等待。要提速优先调它，而不是换模型
- **TTS 必须按片播放**：48k 重采样改造一度引入"全部攒齐再播"的回归，导致首字延迟 ~1.2s。修复后 `stream_play` 收到一片就 `resample_poly` + `stream.write`
- **funasr-onnx 切不掉 PyTorch**：试过把 ASR 切到 `funasr-onnx` + `onnxruntime` 以省内存/提速。发现两个问题：① `funasr_onnx/sensevoice_bin.py` 推理代码硬 `import torch`（CTC 解码用 `torch.from_numpy` / `torch.unique_consecutive`），torch 卸不掉；② 首次加载需要 `funasr` + `onnxscript` 在本机把 `.pt` 导出为 `.onnx`，在 6.9 GB 无 swap 的机器上导出峰值内存 ~3.7 GB 直接被 OOM-killer 杀死。已回退，保持原 PyTorch 路径。若要重试，需先 `fallocate -l 8G /swapfile` 加 swap，或在其它机器导出好 `model_quant.onnx` 再拷过来

## 分支工作流（严格遵守，勿误改）

| 改动范围 | 工作分支 | 同步方式 |
|---|---|---|
| `realtime_asr/`、根目录文件 | `asrdev` | 改完 merge 到 `main` |
| `ros_voice/` | `rosdev` | 改完 merge 到 `main` |

**规则：在任何分支上动手之前，必须先从 `main` pull（`git merge main`），防止覆盖他人改动。**

```
# asrdev 上开发
git checkout asrdev && git merge main
# ...改动...
git checkout main && git merge asrdev

# rosdev 上开发
git checkout rosdev && git merge main
# ...改动...
git checkout main && git merge rosdev
```

历史备注：`mac_complete` 为 ROS 改造前的 Mac 完整版快照，已删除。

## 研发思路
参考代码（ref codes/）覆盖：录音、VAD、ASR、LLM对话、TTS合成、多模态视觉。
演进路径：录音验证 → 实时ASR → 接入LLM对话 → TTS语音回复 → 视觉多模态扩展

## 运行
```bash
python3 main.py   # Ctrl+C 退出
```

## 关键参数（realtime_asr/config.py）
| 参数 | 默认值 | 说明 |
|------|--------|------|
| DEVICE_INDEX | 1 | 麦克风设备（USB PnP，硬件 48kHz，代码内重采样至 16k） |
| OUTPUT_DEVICE_INDEX | 1 | 扬声器设备（同一 USB PnP，代码内重采样至 48k） |
| HW_SAMPLE_RATE | 48000 | 硬件原生采样率 |
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

### VAD_MODE = "webrtc"（无需校准）
| 参数 | 默认值 | 说明 |
|------|--------|------|
| VAD_AGGRESSIVENESS | 3 | 0-3，越高越激进，3 适合空调环境 |
| VAD_SPEECH_TRIGGER | 3 | 连续 N 帧（×20ms）确认语音才录制 |
