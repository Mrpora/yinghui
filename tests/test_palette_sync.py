# SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
# SPDX-License-Identifier: AGPL-3.0-or-later

"""调色板同源锁定测试（debt-wave4a F4）。

server/seed_presets.py 的 ``_PALETTE``/``_accent_color`` 与
server/storage/sqlite_client.py 的 ``_CHARACTER_PALETTE``/``_pick_accent_color``
是刻意重复——seed_presets 为 stdlib-only 独立脚本（依赖隔离），不得 import
服务端模块，只能复制实现。本测试同时加载两侧实现，锁定：

1. 调色板颜色列表完全一致；
2. 对同一角色名输入序列（含哈希碰撞对），选择函数返回完全一致的颜色序列；
3. 前 N（≤调色板容量）个角色取色不重复（线性探测避撞语义一致）。

任一侧单独改动（扩色、换哈希、改探测策略）都会在此失败，提醒同步另一侧。
seed_presets 以 importlib 从文件路径加载（不依赖其在 sys.path 上的包形态，
也不引入其 stdlib 之外的任何东西——其自身即 stdlib-only）。
"""
import importlib.util
from pathlib import Path

import pytest

_SERVER_DIR = Path(__file__).resolve().parent.parent / "server"


def _load_seed_presets():
    """以文件路径加载 seed_presets 模块（绕开常规包导入路径）。"""
    spec = importlib.util.spec_from_file_location(
        "seed_presets_sync_check", _SERVER_DIR / "seed_presets.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def seed_mod():
    return _load_seed_presets()


def _assign_sequence(pick, names: list[str]) -> list[str]:
    """模拟真实建库流程：按序取色并把已用色累计进 assigned 集合。"""
    assigned: set[str] = set()
    out: list[str] = []
    for name in names:
        color = pick(name, assigned)
        out.append(color)
        assigned.add(color)
    return out


# "ab"/"ba" 序数和相同 → 哈希同槽，构造线性探测碰撞路径
_NAMES = ["林清雪", "苏小焰", "宋桓", "ab", "ba", "墨渊",
          "石破天", "阿朱", "段誉", "王语嫣", "虚竹", "梦姑"]


def test_palettes_identical(seed_mod):
    """两侧调色板颜色列表（含顺序）完全一致。"""
    from server.storage import sqlite_client

    assert list(seed_mod._PALETTE) == list(sqlite_client._CHARACTER_PALETTE)


def test_same_names_same_color_sequence(seed_mod):
    """同一输入序列（含碰撞对）下，两侧选择函数返回一致的颜色序列。"""
    from server.storage import sqlite_client

    assert _assign_sequence(seed_mod._accent_color, _NAMES) == \
        _assign_sequence(sqlite_client._pick_accent_color, _NAMES)


def test_same_name_same_color_on_empty_pool(seed_mod):
    """空池单次取色：同一名字两侧命中同一颜色。"""
    from server.storage import sqlite_client

    for name in _NAMES:
        assert seed_mod._accent_color(name, set()) == \
            sqlite_client._pick_accent_color(name, set())


def test_first_n_colors_distinct(seed_mod):
    """前 N（=调色板容量）个角色取色互不重复（探测避撞语义一致）。"""
    names = [f"角色{k}" for k in range(len(seed_mod._PALETTE))]
    seq = _assign_sequence(seed_mod._accent_color, names)
    assert len(seq) == len(set(seq)) == len(seed_mod._PALETTE)
