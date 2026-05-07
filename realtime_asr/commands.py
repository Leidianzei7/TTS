#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
陪护机器人指令集
每条指令格式：
  "cmd_name": {
      "desc": "中文描述",
      "params": {
          "param_name": {
              "type":    str/float/int,
              "options": [...],        # 枚举型参数
              "range":   [min, max],   # 数值型参数
              "default": ...,
              "unit":    "m/s" 等,     # 可选
              "desc":    "参数说明",
          }
      }
  }
增删指令只需修改此文件，LLM 提示词和话题内容会自动跟随更新。
"""

COMMANDS: dict = {

    # ══════════════════════════════════════════
    # 底盘控制
    # ══════════════════════════════════════════

    "move_forward": {
        "desc": "向前直行",
        "params": {
            "speed":    {"type": float, "range": [0.05, 0.5],  "default": 0.2, "unit": "m/s", "desc": "行进速度"},
            "distance": {"type": float, "range": [0.1, 10.0],  "default": 1.0, "unit": "m",   "desc": "行进距离，0=持续"},
        },
    },

    "move_backward": {
        "desc": "向后直行",
        "params": {
            "speed":    {"type": float, "range": [0.05, 0.3],  "default": 0.15, "unit": "m/s"},
            "distance": {"type": float, "range": [0.1, 5.0],   "default": 0.5,  "unit": "m"},
        },
    },

    "turn_left": {
        "desc": "原地左转",
        "params": {
            "angle": {"type": float, "range": [5.0, 360.0], "default": 90.0, "unit": "deg", "desc": "转动角度"},
            "speed": {"type": float, "range": [0.1, 1.0],   "default": 0.5,  "unit": "rad/s"},
        },
    },

    "turn_right": {
        "desc": "原地右转",
        "params": {
            "angle": {"type": float, "range": [5.0, 360.0], "default": 90.0, "unit": "deg"},
            "speed": {"type": float, "range": [0.1, 1.0],   "default": 0.5,  "unit": "rad/s"},
        },
    },

    "stop": {
        "desc": "立即停止所有运动",
        "params": {},
    },

    "navigate_to": {
        "desc": "自主导航到指定地点",
        "params": {
            "location": {
                "type": str,
                "options": ["bedroom", "living_room", "kitchen", "bathroom", "entrance", "charging_dock"],
                "desc": "目标地点（卧室/客厅/厨房/卫生间/门口/充电桩）",
            },
        },
    },

    "follow_person": {
        "desc": "跟随前方人员行走",
        "params": {
            "distance": {"type": float, "range": [0.5, 2.0], "default": 1.0, "unit": "m", "desc": "跟随保持距离"},
        },
    },

    "return_home": {
        "desc": "返回充电桩并充电",
        "params": {},
    },

    "set_speed_level": {
        "desc": "设置行进速度档位",
        "params": {
            "level": {"type": str, "options": ["slow", "normal", "fast"], "default": "normal", "desc": "慢/正常/快"},
        },
    },

    # ══════════════════════════════════════════
    # 机械臂控制
    # ══════════════════════════════════════════

    "arm_home": {
        "desc": "机械臂回归待机收纳位",
        "params": {},
    },

    "arm_wave": {
        "desc": "挥手打招呼",
        "params": {
            "times": {"type": int, "range": [1, 5], "default": 2, "desc": "挥手次数"},
        },
    },

    "arm_handshake": {
        "desc": "伸出右手握手姿势",
        "params": {},
    },

    "arm_point": {
        "desc": "手臂指向某方向或地点",
        "params": {
            "direction": {
                "type": str,
                "options": ["forward", "left", "right", "up", "backward"],
                "default": "forward",
            },
        },
    },

    "arm_reach": {
        "desc": "手臂伸出以递送或接取物品",
        "params": {
            "direction": {
                "type": str,
                "options": ["forward", "left", "right", "up", "down"],
                "default": "forward",
            },
            "distance": {"type": float, "range": [0.1, 0.6], "default": 0.35, "unit": "m"},
        },
    },

    "arm_grab": {
        "desc": "夹爪闭合抓取",
        "params": {
            "force": {"type": float, "range": [0.1, 1.0], "default": 0.5, "desc": "抓取力度比例"},
        },
    },

    "arm_release": {
        "desc": "夹爪张开释放物品",
        "params": {},
    },

    "arm_pat": {
        "desc": "轻拍安抚动作（轻触老人肩部/手背）",
        "params": {
            "times": {"type": int, "range": [1, 5], "default": 3},
        },
    },

    # ══════════════════════════════════════════
    # 交互与陪护
    # ══════════════════════════════════════════

    "express_emotion": {
        "desc": "通过屏幕表情和灯光表达情绪",
        "params": {
            "emotion": {
                "type": str,
                "options": ["happy", "caring", "concerned", "excited", "calm", "encouraging"],
                "default": "caring",
            },
        },
    },

    "call_caregiver": {
        "desc": "通知照护人员（推送消息/电话）",
        "params": {
            "urgency": {"type": str, "options": ["normal", "urgent"], "default": "normal"},
        },
    },

    "call_emergency": {
        "desc": "拨打紧急求助（120/家属）",
        "params": {},
    },

    "set_volume": {
        "desc": "调整机器人音量",
        "params": {
            "level": {"type": int, "range": [0, 10], "default": 5},
        },
    },

    "play_music": {
        "desc": "播放背景音乐",
        "params": {
            "genre": {
                "type": str,
                "options": ["relaxing", "classical", "folk", "nature", "silence"],
                "default": "relaxing",
            },
            "volume": {"type": int, "range": [1, 10], "default": 4},
        },
    },

    "set_reminder": {
        "desc": "设置定时提醒（吃药/喝水/运动/用餐）",
        "params": {
            "type": {
                "type": str,
                "options": ["medication", "drink_water", "exercise", "meal", "rest"],
                "desc": "提醒类型",
            },
            "delay_min": {"type": int, "range": [1, 1440], "default": 30, "unit": "min", "desc": "多少分钟后提醒"},
        },
    },

    "take_photo": {
        "desc": "拍照并保存（安全记录或家属查看）",
        "params": {},
    },

    "report_status": {
        "desc": "口头汇报当前状态（位置/电量/传感器）",
        "params": {},
    },
}


# ── 自动生成 LLM 提示词 ────────────────────────────────────────────

def _compact_param(name: str, p: dict) -> str:
    if p.get("options"):
        opts = "|".join(p["options"])
        return f'{name}="{opts}"'
    if p.get("range"):
        lo, hi = p["range"]
        unit = p.get("unit", "")
        return f"{name}={lo}~{hi}{unit}"
    return name


def _compact_cmd(name: str, info: dict) -> str:
    params = info.get("params", {})
    if not params:
        return f"{name}() — {info['desc']}"
    param_str = ", ".join(_compact_param(k, v) for k, v in params.items())
    return f"{name}({param_str}) — {info['desc']}"


def build_command_reference() -> str:
    """生成紧凑的指令参考字符串，嵌入 LLM 系统提示词。"""
    sections = {
        "底盘控制": ["move_forward", "move_backward", "turn_left", "turn_right", "stop",
                     "navigate_to", "follow_person", "return_home", "set_speed_level"],
        "机械臂":   ["arm_home", "arm_wave", "arm_handshake", "arm_point",
                     "arm_reach", "arm_grab", "arm_release", "arm_pat"],
        "交互陪护": ["express_emotion", "call_caregiver", "call_emergency",
                     "set_volume", "play_music", "set_reminder", "take_photo", "report_status"],
    }
    lines = []
    for section, names in sections.items():
        lines.append(f"【{section}】")
        for n in names:
            if n in COMMANDS:
                lines.append("  " + _compact_cmd(n, COMMANDS[n]))
    return "\n".join(lines)


def build_system_prompt() -> str:
    ref = build_command_reference()
    return (
        "你是小智，一个智能陪护机器人助手。用户用语音下达指令，你必须严格按以下格式回复：\n"
        "[口语回复]：<用自然口语化的1句话回应用户，不超过20字>\n"
        "[执行指令]：<JSON数组，从下方指令集中选取，必须是合法JSON，无多余文字>\n\n"
        "输出规则：\n"
        "- [口语回复]必须在第一行且只占一行\n"
        "- [执行指令]后紧跟JSON数组，例如：[{\"cmd\":\"move_forward\",\"params\":{\"speed\":0.2,\"distance\":1.0}}]\n"
        "- 若用户意图不涉及任何机械动作，[执行指令]输出空数组 []\n"
        "- 参数必须在指令集规定的范围/选项内，缺省时使用默认值\n"
        "- 只输出这两个部分，不要任何额外说明\n\n"
        f"可用指令集：\n{ref}"
    )
