#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import json
from openai import OpenAI
from .config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL
from .commands import build_system_prompt

llm_client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)

_SYSTEM_PROMPT = build_system_prompt()

_SPOKEN_PREFIX = "[口语回复]："
_INSTR_PREFIX  = "[执行指令]："


def generate_response(
    text: str,
    system_prompt: str = _SYSTEM_PROMPT,
) -> tuple[str, list[dict]]:
    """
    调用 LLM，返回 (口语回复, 指令列表)。
    指令列表格式：[{"cmd": "move_forward", "params": {"speed": 0.2, "distance": 1.0}}, ...]
    调用方负责 TTS 播放和指令处理。
    """
    stream = llm_client.chat.completions.create(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
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

    commands = _parse_commands(raw)

    if not spoken_found:
        print(f"[LLM 原始输出]\n{raw}\n", flush=True)
        print("[警告] LLM 未生成口语回复，检查提示词格式", file=sys.stderr)

    return spoken, commands


def _parse_commands(raw: str) -> list[dict]:
    """从 LLM 原始输出中提取 [执行指令] 后的 JSON 数组。"""
    idx = raw.find(_INSTR_PREFIX)
    if idx == -1:
        return []
    after = raw[idx + len(_INSTR_PREFIX):].strip()
    # 取第一行（LLM 有时会多输出换行后的解释文字）
    first_line = after.split("\n")[0].strip()
    try:
        result = json.loads(first_line)
        if isinstance(result, list):
            return result
    except json.JSONDecodeError:
        # 尝试找 [...] 块
        start = after.find("[")
        end   = after.rfind("]")
        if start != -1 and end != -1 and end > start:
            try:
                result = json.loads(after[start: end + 1])
                if isinstance(result, list):
                    return result
            except json.JSONDecodeError:
                pass
        print(f"[警告] 执行指令 JSON 解析失败: {after[:200]}", file=sys.stderr)
    return []
