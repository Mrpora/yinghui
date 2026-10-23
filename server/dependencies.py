# SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
# SPDX-License-Identifier: AGPL-3.0-or-later

"""全局依赖注入——惰性单例，供 API 路由使用。

原四个 agent/LLM 编排类单例随内置编排删除——编排已外移至
yinghui-dsh-plug 桥接进程，本模块仅保留领域服务单例。
"""
import logging

logger = logging.getLogger(__name__)

# ── 惰性单例 ──

_sse_manager = None
_session_manager = None


async def get_db():
    """SQLite 连接单例——委托给 storage 层。"""
    from server.storage.sqlite_client import get_db as _get_db
    return await _get_db()


def get_sse_manager():
    """SSE 发布-订阅管理器单例。"""
    global _sse_manager
    if _sse_manager is None:
        from server.sse.sse_manager import SSEManager
        _sse_manager = SSEManager()
        logger.info("✅ SSEManager 单例已初始化")
    return _sse_manager


def get_session_manager():
    """会话管理器单例。"""
    global _session_manager
    if _session_manager is None:
        from server.services.session_manager import SessionManager
        _session_manager = SessionManager()
        logger.info("✅ SessionManager 单例已初始化")
    return _session_manager
