#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import threading
from openai import OpenAI
from .config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, LLM_SYSTEM
from . import state as _state

llm_client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)

_SPOKEN_PREFIX = "[口语回复]："
_INSTR_PREFIX  = "[执行指令]："


def _tts_and_enqueue(spoken):
    _state.tts_text_q.put(spoken)


def generate_response(text):
    stream = llm_client.chat.completions.create(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": LLM_SYSTEM},
            {"role": "user",   "content": text},
        ],
        stream=True,
    )

    raw = ""
    spoken_fired = False

    for chunk in stream:
        delta = chunk.choices[0].delta.content or ""
        raw += delta

        # 一旦 [口语回复]：...那行输出完整（出现换行），立即异步触发 TTS
        if not spoken_fired and _SPOKEN_PREFIX in raw:
            start = raw.index(_SPOKEN_PREFIX) + len(_SPOKEN_PREFIX)
            after = raw[start:]
            if "\n" in after:
                spoken = after[: after.index("\n")].strip()
                spoken_fired = True
                if spoken:
                    print(f"🔊 语音回复：{spoken}", flush=True)
                    threading.Thread(target=_tts_and_enqueue, args=(spoken,), daemon=True).start()
                else:
                    print("[警告] 口语回复为空，检查提示词格式", file=sys.stderr)

    # 流式接收完毕，提取并打印执行指令
    instruction_lines = []
    in_instructions = False
    for line in raw.splitlines():
        if line.startswith(_INSTR_PREFIX):
            in_instructions = True
        elif in_instructions and line.strip():
            instruction_lines.append(line)

    if instruction_lines:
        print(f"\n✅ 标准化指令:\n" + "\n".join(instruction_lines) + "\n", flush=True)

    if not spoken_fired:
        print(f"[LLM 原始输出]\n{raw}\n", flush=True)
        print("[警告] LLM 未生成口语回复，检查提示词格式", file=sys.stderr)
