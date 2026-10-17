# SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
# SPDX-License-Identifier: AGPL-3.0-or-later

"""测试共享辅助——构造最小合法角色列表。"""


def make_characters(n: int = 3, prefix: str = "角色") -> list[dict]:
    """生成 n 个最小合法角色 dict（name 自增保证唯一，其余字段给默认值）。"""
    return [{"name": f"{prefix}{i}", "identity": "测试身份"} for i in range(1, n + 1)]
