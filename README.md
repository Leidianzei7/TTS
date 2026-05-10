# 实时语音对话系统

> 麦克风 → VAD → ASR → 唤醒词 → LLM → TTS → 扬声器，CPU 推理，可选 ROS2 发布。

## 各环节流式状态

下表标注每个环节是**流式**（边到边处理）还是**离线**（凑齐整段再算）。

| # | 环节 | 流式? | 实现 | 说明 |
|---|------|:-----:|------|------|
| 1 | 音频采集 | ✅ | sounddevice 回调 | 硬件 48 kHz，每次回调推送 `CHUNK*3` 个采样到队列 |
| 2 | 重采样 48k→16k | ✅ | scipy `resample_poly` | 在采集回调里逐块处理，喂给 ASR 端 |
| 3 | VAD (energy / webrtc) | ✅ | `realtime_asr.vad.run_vad` | 从队列逐块取，逐帧判定语音/静音；积满静音阈值后切段 |
| 4 | **ASR 推理** | ❌ **离线** | FunASR `SenseVoiceSmall.generate(audio_np)` | **VAD 切出完整段才一次性送推理**。CPU 上换 `paraformer-zh-streaming` 反而更慢，故保留 SenseVoice 整段推理 |
| 5 | 唤醒词匹配 | ❌ 批 | `wake_word.find_wake_word` | 对 ASR 输出的整句字符串做匹配，输入本就是离散文本 |
| 6 | LLM (Qwen-turbo) | ✅ 部分流式 | OpenAI SDK `stream=True` | token 流式接收。**口语回复**等 `\n`（行边界）即可截取并送 TTS，不必等流结束；**机械指令 JSON** 必须等整段流结束才能 `json.loads`（语法约束） |
| 7 | TTS 合成 (CosyVoice v2) | ✅ | DashScope `ResultCallback.on_data` | 服务端边合成边回 PCM 片段，回调入队 |
| 8 | TTS 重采样 16k→48k + 播放 | ✅ | `resample_poly` + `OutputStream.write` | **收到一片立即重采样并写声卡**，首字延迟 ~150 ms |

### 整体延迟瓶颈

不在 ASR 推理本身，而在 **#3 VAD 的静音等待** —— `SPEECH_HOLD_SEC=1.2 s` 决定了用户停顿后多久才进入 ASR。要降低感知延迟优先调这个参数。

## 模块布局

```
realtime_asr/
├── audio.py        采音 + 重采样 + VAD 调度（含校准）
├── vad.py          能量 / WebRTC 双模式 VAD 核心循环
├── asr.py          SenseVoiceSmall 离线推理封装
├── wake_word.py    "小智 / 小智小智" 字面 + 拼音容错匹配
├── llm.py          Qwen-turbo 流式调用，解析口语回复 + JSON 指令
├── tts.py          CosyVoice v2 流式合成 + 边播
├── commands.py     机械指令集与 system prompt
├── pipeline.py     高层 API：run_command_pipeline / process_command
├── config.py       全部可调参数
└── main.py         单进程入口（main.py 在仓库根目录转发）

ros_voice/          纯 ROS2 层，不含任何 ASR/LLM/TTS 实现
├── voice_node.py   调 run_command_pipeline → publish /voice/command
├── brain_node.py   subscribe /voice/command → 调 process_command → publish /robot/instructions
└── launch/voice.launch.py
```

## 运行

```bash
# 单进程版（无 ROS）
python3 main.py

# ROS2 版
ros2 launch ros_voice voice.launch.py
```

详见 [CLAUDE.md](CLAUDE.md) 的硬件、参数、分支工作流说明。
