# SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
# SPDX-License-Identifier: AGPL-3.0-or-later

"""全局依赖注入——7 个单例，惰性初始化，供 API 路由和 Agent 使用。"""
import logging

logger = logging.getLogger(__name__)

# ── 惰性单例 ──

_llm_client = None
_sse_manager = None
_session_manager = None
_evolution_agent = None
_novel_agent = None


async def get_db():
    """SQLite 连接单例——委托给 storage 层。"""
    from server.storage.sqlite_client import get_db as _get_db
    return await _get_db()


def get_llm_client():
    """统一 LLM 客户端单例。"""
    global _llm_client
    if _llm_client is None:
        from server.config import config
        from server.ai.common.llm_client import LLMClient
        _llm_client = LLMClient(config)
        logger.info("✅ LLMClient 单例已初始化")
    return _llm_client


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


def get_evolution_agent():
    """演化管线编排器单例——依赖 LLMClient、SessionManager、SSEManager。"""
    global _evolution_agent
    if _evolution_agent is None:
        from server.ai.evolution_agent.agent import PipelineOrchestrator
        _evolution_agent = PipelineOrchestrator(
            llm_client=get_llm_client(),
            session_manager=get_session_manager(),
            sse_manager=get_sse_manager(),
        )
        logger.info("✅ PipelineOrchestrator 单例已初始化")
    return _evolution_agent


def get_novel_agent():
    """小说生成 Agent 单例。"""
    global _novel_agent
    if _novel_agent is None:
        from server.ai.novel_agent.agent import NovelAgent
        _novel_agent = NovelAgent()
        logger.info("✅ NovelAgent 单例已初始化")
    return _novel_agent


def get_chat_run():
    """对话 Agent 的 run() 异步生成器——模块级函数，直接引用。"""
    from server.ai.chat_agent.agent import run
    return run
