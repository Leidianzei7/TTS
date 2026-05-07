#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import contextlib
import io
import logging
from funasr import AutoModel
from funasr.utils.postprocess_utils import rich_transcription_postprocess


@contextlib.contextmanager
def _silent():
    logging.disable(logging.WARNING)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        try:
            yield
        finally:
            logging.disable(logging.NOTSET)


print("正在加载语音识别模型...")
with _silent():
    asr_model = AutoModel(
        model="iic/SenseVoiceSmall",
        vad_model="fsmn-vad",
        device="cpu",
        use_itn=True,
        disable_pbar=True,
        disable_update=True,
    )
print("模型加载完成！\n")


def recognize(audio_np):
    res = asr_model.generate(
        input=audio_np,
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
