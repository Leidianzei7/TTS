#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import tempfile
import os
import soundfile as sf
from funasr import AutoModel
from funasr.utils.postprocess_utils import rich_transcription_postprocess
from .config import SAMPLE_RATE

print("正在加载 SenseVoiceSmall 语音识别模型，请稍候...")
asr_model = AutoModel(
    model="iic/SenseVoiceSmall",
    vad_model="fsmn-vad",
    device="cpu",
    use_itn=True,
    disable_pbar=True,
)
print("模型加载完成！\n")


def recognize(audio_np):
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        tmp_path = f.name
    try:
        sf.write(tmp_path, audio_np, SAMPLE_RATE)
        res = asr_model.generate(
            input=tmp_path,
            cache={},
            language="auto",
            use_itn=True,
            batch_size_s=60,
            merge_vad=True,
            merge_length_s=15,
        )
        if res and res[0].get("text"):
            return rich_transcription_postprocess(res[0]["text"])
        return ""
    finally:
        os.remove(tmp_path)
