# SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
# SPDX-License-Identifier: AGPL-3.0-or-later

"""字形混淆工具——加载映射表，对中文内容进行混淆/还原。

混淆后的文本在 DOM/源码中为乱码，但用混淆字体渲染后会显示为正确的文字。
"""
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# 映射表路径
_KEY_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "obfuscation_key.json"

_obfuscation_map: dict[str, str] | None = None


def _load_map() -> dict[str, str]:
    global _obfuscation_map
    if _obfuscation_map is not None:
        return _obfuscation_map
    try:
        with open(_KEY_PATH, "r", encoding="utf-8") as f:
            _obfuscation_map = json.load(f)
        logger.info("字形混淆映射已加载，%d 个字符", len(_obfuscation_map))
    except FileNotFoundError:
        logger.warning("混淆映射文件不存在: %s，混淆功能禁用", _KEY_PATH)
        _obfuscation_map = {}
    except Exception as e:
        logger.error("加载混淆映射失败: %s", e)
        _obfuscation_map = {}
    return _obfuscation_map


def obfuscate(text: str) -> str:
    """将文本中的中文字符替换为混淆后的字符。"""
    mapping = _load_map()
    if not mapping:
        return text

    result: list[str] = []
    for ch in text:
        result.append(mapping.get(ch, ch))
    return "".join(result)


def deobfuscate(text: str) -> str:
    """将混淆后的文本还原（用于调试/测试）。"""
    mapping = _load_map()
    if not mapping:
        return text

    # 构建反向映射
    reverse = {v: k for k, v in mapping.items()}
    result: list[str] = []
    for ch in text:
        result.append(reverse.get(ch, ch))
    return "".join(result)
