#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
from openai import OpenAI
from .config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, LLM_SYSTEM
from . import state as _state
from .tts import synthesize_speech

llm_client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)


def parse_llm_response(raw):
    """从 LLM 双段输出中提取口语回复和执行指令。"""
    spoken = ""
    instruction_lines = []
    in_instructions = False
    for line in raw.splitlines():
        if line.startswith("[口语回复]："):
            spoken = line[len("[口语回复]：") :].strip()
        elif line.startswith("[执行指令]："):
            in_instructions = True
        elif in_instructions and line.strip():
            instruction_lines.append(line)
    return spoken, "\n".join(instruction_lines)


def generate_response(text):
    resp = llm_client.chat.completions.create(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": LLM_SYSTEM},
            {"role": "user",   "content": text},
        ],
    )
    raw = resp.choices[0].message.content.strip()
    spoken, instructions = parse_llm_response(raw)

    if instructions:
        print(f"\n✅ 标准化指令:\n{instructions}\n", flush=True)
    else:
        print(f"[LLM 原始输出]\n{raw}\n", flush=True)

    if spoken:
        print(f"🔊 语音回复：{spoken}", flush=True)
        audio_np = synthesize_speech(spoken)
        if audio_np is not None:
            _state.tts_audio_q.put(audio_np)
    else:
        print("[警告] LLM 未生成口语回复，检查提示词格式", file=sys.stderr)
