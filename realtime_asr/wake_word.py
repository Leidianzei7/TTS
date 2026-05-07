#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from pypinyin import lazy_pinyin
from .config import WAKE_WORD, _WW_LEN, _WW_PINYIN


def find_wake_word(text):
    """返回唤醒词在 text 中的起始位置，找不到返回 -1。支持近同音字容错。"""
    if WAKE_WORD in text:
        return text.index(WAKE_WORD)
    for i in range(len(text) - _WW_LEN + 1):
        if "".join(lazy_pinyin(text[i : i + _WW_LEN])) == _WW_PINYIN:
            return i
    return -1
