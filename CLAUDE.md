# TTS / 实时语音识别项目

> 每次功能变更后更新此文件，保持简洁，重点记录进度和思路变化。
> 对话变长时提醒用户执行 `/compact` 压缩上下文以节省 token。

## 硬件
- 启英泰伦 USB 声音模块，sounddevice Index=2，2声道输入

## 技术栈
- 音频采集：sounddevice（macOS无portaudio，弃用pyaudio）
- VAD：RMS能量阈值（SILENCE_THRESHOLD=300）
- 语音识别：FunASR SenseVoiceSmall + fsmn-vad，CPU推理
- LLM：阿里云 DashScope Qwen（qwen-turbo），OpenAI 兼容格式
- Python 3.9，无conda环境

## 当前进度
- [x] 设备检测与录音验证
- [x] `realtime_asr.py`：实时采集 → VAD → SenseVoiceSmall → 屏幕打印
- [x] 唤醒词"小智小智"触发 → ASR → Qwen LLM → 标准化编号指令输出
- [ ] 下一步待定

## 研发思路
参考代码（ref codes/）覆盖：录音、VAD、ASR、LLM对话、TTS合成、多模态视觉。
演进路径：录音验证 → 实时ASR → 接入LLM对话 → TTS语音回复 → 视觉多模态扩展

## 运行
```bash
python3 realtime_asr.py   # Ctrl+C 退出
```

## 关键参数
| 参数 | 默认值 | 说明 |
|------|--------|------|
| DEVICE_INDEX | 2 | 启英泰伦设备 |
| SILENCE_THRESHOLD | 300 | RMS噪音阈值，环境噪大时调高 |
| SPEECH_HOLD_SEC | 1.5 | 停顿多久触发识别 |
| WAKE_WORD | 小智小智 | 唤醒词，说出后下达指令 |
| LLM_MODEL | qwen-turbo | DashScope 模型，base_url 华北2 |
