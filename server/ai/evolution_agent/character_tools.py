# SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
# SPDX-License-Identifier: AGPL-3.0-or-later

"""角色 Agent 工具——角色在演化中可调用的 function calling 工具。"""

import logging

from server.services.session_manager import Session

logger = logging.getLogger(__name__)


async def write_my_memory(
    session: Session,
    character_name: str,
    type: str,
    content: str,
    importance: int = 5,
) -> dict:
    """将值得记住的事件或态度判断注入角色上下文，以系统消息形式写入。"""
    memory_message = {
        "role": "system",
        "content": f"[记忆·{type}] {content} (重要性: {importance}/10)",
    }
    if character_name not in session.character_contexts:
        return {"status": "error", "message": f"角色 {character_name} 不存在"}

    session.character_contexts[character_name].append(memory_message)
    logger.info("🧠 角色记忆写入 char=%s type=%s importance=%d round=%d",
                character_name, type, importance, session.current_round)
    return {"status": "success"}


CHARACTER_TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "write_my_memory",
            "description": "将值得记住的事件或态度判断写入记忆。写入后以系统消息形式注入上下文。",
            "parameters": {
                "type": "object",
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": ["world_event", "attitude"],
                        "description": "world_event：世界中发生的事件；attitude：态度判断",
                    },
                    "content": {
                        "type": "string",
                        "description": "记忆内容文本",
                    },
                    "importance": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 10,
                        "default": 5,
                        "description": "重要性评分（1-10）",
                    },
                },
                "required": ["type", "content"],
            },
        },
    }
]
