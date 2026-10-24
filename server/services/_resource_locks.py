# SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
# SPDX-License-Identifier: AGPL-3.0-or-later

"""JSON 列读-改-写资源锁注册表——agent_ops_service 与路由层共用。

Round 2（终审复审 I3 补漏）：锁注册表自 agent_ops_service 提升为独立小模块，
消除「路由层包锁须 import 服务层私有函数」的耦合与循环 import 风险。

背景：timeline / relationships / character_contexts / chat messages 四类 JSON
列的读-改-写若无锁交错会丢更新。所有写者（路由 / bridge / MCP）都经 yinghui
API 收敛到同一进程，进程内按资源键加锁即完备（同 plug T4 flows._lock_for 先例）：
- `evolution:{eid}`——world_evolutions 的 timeline / relationships /
  character_contexts 列（agent_ops `_append_timeline` 等 + 路由
  select-branch / custom-event / intervene 经 session_manager 写入）；
- `chat:{cid}`——character_chats.messages 列（agent_ops append_chat_message /
  chat_done + 路由 chats/start 用户消息落库）。

约定：锁内只做同一 JSON 列的读-改-写（SELECT→append→UPDATE→commit），
不做 SSE 广播等其他资源 await。
"""
import asyncio

_locks: dict[str, asyncio.Lock] = {}


def lock_for(key: str) -> asyncio.Lock:
    """按资源键取进程内互斥锁（setdefault 注册，同键必得同一把锁）。"""
    return _locks.setdefault(key, asyncio.Lock())
