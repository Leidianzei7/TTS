#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
from openai import OpenAI
from .config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, LLM_SYSTEM

llm_client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)

_SPOKEN_PREFIX = "[口语回复]："
_INSTR_PREFIX  = "[执行指令]："


def generate_response(text: str) -> tuple[str, list[str]]:
    """调用 LLM，返回 (口语回复, 指令行列表)。调用方负责 TTS 播放和指令处理。"""
    stream = llm_client.chat.completions.create(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": LLM_SYSTEM},
            {"role": "user",   "content": text},
        ],
        stream=True,
    )

    raw = ""
    spoken = ""
    spoken_found = False

    for chunk in stream:
        delta = chunk.choices[0].delta.content or ""
        raw += delta

        if not spoken_found and _SPOKEN_PREFIX in raw:
            start = raw.index(_SPOKEN_PREFIX) + len(_SPOKEN_PREFIX)
            after = raw[start:]
            if "\n" in after:
                spoken = after[: after.index("\n")].strip()
                spoken_found = True

    instruction_lines = []
    in_instructions = False
    for line in raw.splitlines():
        if line.startswith(_INSTR_PREFIX):
            in_instructions = True
        elif in_instructions and line.strip():
            instruction_lines.append(line)

    if not spoken_found:
        print(f"[LLM 原始输出]\n{raw}\n", flush=True)
        print("[警告] LLM 未生成口语回复，检查提示词格式", file=sys.stderr)

    return spoken, instruction_lines
