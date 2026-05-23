# 实时语音识别 & 对话机器人

基于 FunASR SenseVoiceSmall + DashScope Qwen/CosyVoice 的本地实时语音对话系统，支持唤醒词触发、LLM 对话和流式 TTS 播报。

## 硬件要求

- 启英泰伦 USB 声音模块（或其他 USB 音频设备）
- 麦克风设备索引默认 `2`，扬声器默认 `1`，可在 `realtime_asr/config.py` 修改

## 环境要求

- **Python 3.11**（系统 Python 3.12+ 可能缺少兼容 wheel，推荐 3.11）
- macOS / Linux
- [DashScope API Key](https://dashscope.console.aliyun.com/)（用于 LLM 和 TTS）

## 部署步骤

### 1. 克隆仓库

```bash
git clone https://github.com/Leidianzei7/TTS.git
cd TTS
```

### 2. 安装 Python 3.11（macOS）

```bash
brew install python@3.11
```

### 3. 创建虚拟环境

```bash
python3.11 -m venv venv
source venv/bin/activate
```

### 4. 安装依赖

```bash
pip install -r requirements.txt
```

> 首次安装含 torch/torchaudio，体积较大（~1GB），请耐心等待。

### 5. 配置 API Key

```bash
export DASHSCOPE_API_KEY="your_api_key_here"
```

建议写入 `~/.zshrc` 或 `~/.bashrc` 永久生效：

```bash
echo 'export DASHSCOPE_API_KEY="your_api_key_here"' >> ~/.zshrc
source ~/.zshrc
```

### 6. 查看音频设备编号（可选）

```bash
python3 -c "import sounddevice as sd; print(sd.query_devices())"
```

对照输出修改 `realtime_asr/config.py` 中的 `DEVICE_INDEX` 和 `OUTPUT_DEVICE_INDEX`。

### 7. 运行

```bash
source venv/bin/activate   # 新终端窗口需重新激活
python3 main.py            # Ctrl+C 退出
```

## 使用说明

- 启动后自动校准环境底噪（约 1.5 秒），期间保持安静
- 说出唤醒词 **"小智小智"** 或 **"小智"** 触发对话
- 系统识别语音 → 调用 LLM → TTS 播报回复

## 项目结构

```
TTS/
├── main.py                  # 入口
├── requirements.txt         # 依赖列表
├── realtime_asr/            # 核心包
│   ├── config.py            # 所有可调参数
│   ├── audio.py             # 音频采集
│   ├── vad.py               # 语音活动检测
│   ├── asr.py               # 语音识别
│   ├── wake_word.py         # 唤醒词检测
│   ├── llm.py               # LLM 对话
│   ├── tts.py               # 语音合成
│   ├── state.py             # 状态管理
│   └── commands.py          # 指令处理
└── ros_voice/               # ROS2 集成层（可选）
```
