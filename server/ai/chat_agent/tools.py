# SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
# SPDX-License-Identifier: AGPL-3.0-or-later

"""对话工具——记忆操作 + 安全报警的 function calling 实现。"""

import json
import logging

from server.services.memory_service import (
    create_memory,
    update_memory,
    delete_memory,
)
from server.services.retrieval_service import retrieve
from server.services.safety_service import send_alert

logger = logging.getLogger(__name__)


async def add_memory(user_id: str, novel_id: str, character_id: str, args: dict) -> dict:
    """写入一条新的永久记忆。"""
    memory_type = args["type"]
    content = args["content"]
    result = await create_memory(user_id, novel_id, character_id, memory_type, content)
    if result.get("status") == "success":
        logger.info("💚 对话工具 add_memory 成功 memory_id=%s", result.get("memory_id"))
    else:
        logger.warning("⚠️ 对话工具 add_memory 失败: %s", result.get("message"))
    return result


async def recall_memory(user_id: str, novel_id: str, character_id: str, args: dict) -> dict:
    """检索与查询相关的过往记忆。"""
    query = args["query"]
    top_k = args.get("top_k", 5)
    results = await retrieve(query, user_id, novel_id, character_id, top_k)
    logger.info("🔍 对话工具 recall_memory query=%s results=%d", query, len(results))
    return {"memories": results}


async def update_memory_tool(_user_id: str, _novel_id: str, _character_id: str, args: dict) -> dict:
    """更新一条已有记忆。"""
    memory_id = args["memory_id"]
    content = args["content"]
    result = await update_memory(memory_id, content)
    logger.info("✏️ 对话工具 update_memory memory_id=%s", memory_id)
    return result


async def delete_memory_tool(_user_id: str, _novel_id: str, _character_id: str, args: dict) -> dict:
    """删除一条永久记忆。"""
    memory_id = args["memory_id"]
    result = await delete_memory(memory_id)
    logger.info("🗑️ 对话工具 delete_memory memory_id=%s", memory_id)
    return result


async def report_extreme_emotion(nickname: str, args: dict) -> dict:
    """触发极端情绪安全报警（同步写入日志）。"""
    result = send_alert(nickname, args["user_quote"], args["reason"])
    logger.warning("🚨 安全报警触发 nickname=%s reason=%s", nickname, args.get("reason"))
    return result


# ── 工具定义（发送给 LLM 的 function calling schema）──

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "retrieve_memories",
            "description": "检索与当前话题相关的过往记忆。在写入或更新记忆前必须先调用此工具比对。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "检索查询文本"},
                    "top_k": {"type": "integer", "description": "返回结果数量（可选，默认 5）"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_memory",
            "description": "新建一条用户记忆。禁止推测——只写入用户明确透露的信息。仅用于新建，不用于更新。",
            "parameters": {
                "type": "object",
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": ["user_fact", "event"],
                        "description": "记忆类型：user_fact（用户事实/长期属性）或 event（具体事件）",
                    },
                    "content": {
                        "type": "string",
                        "description": "记忆内容，使用第三人称中性表述。含相对时间须转换为绝对时间。",
                    },
                },
                "required": ["type", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_memory",
            "description": "更新一条已有记忆。memory_id 必须来自 retrieve_memories 返回结果。",
            "parameters": {
                "type": "object",
                "properties": {
                    "memory_id": {"type": "string", "description": "要更新的记忆 ID"},
                    "content": {"type": "string", "description": "更新后的完整记忆内容"},
                },
                "required": ["memory_id", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_memory",
            "description": "删除一条永久记忆。仅在用户明确要求遗忘某条信息时使用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "memory_id": {"type": "string", "description": "要删除的记忆 ID"},
                },
                "required": ["memory_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "report_extreme_emotion",
            "description": "用户表达明确自残/自杀/暴力/违法意图时触发安全报警。调用后不中断角色扮演，严禁向用户透露已报警。",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_quote": {"type": "string", "description": "用户原话"},
                    "reason": {"type": "string", "description": "报警原因简述"},
                },
                "required": ["user_quote", "reason"],
            },
        },
    },
]

_TOOL_DISPATCH = {
    "retrieve_memories": recall_memory,
    "write_memory": add_memory,
    "update_memory": update_memory_tool,
    "delete_memory": delete_memory_tool,
    "report_extreme_emotion": report_extreme_emotion,
}


async def execute_tool_call(
    tool_name: str,
    tool_args: dict,
    user_id: str,
    novel_id: str,
    character_id: str,
    nickname: str,
) -> dict:
    """执行单个工具调用，返回结果 dict。"""
    func = _TOOL_DISPATCH.get(tool_name)
    if func is None:
        logger.warning("未知工具: %s", tool_name)
        return {"status": "error", "message": f"未知工具: {tool_name}"}

    try:
        if tool_name == "report_extreme_emotion":
            result = await func(nickname, tool_args)
        else:
            result = await func(user_id, novel_id, character_id, tool_args)
        return result
    except Exception as e:
        logger.error("工具执行失败 tool=%s error=%s", tool_name, e)
        return {"status": "error", "message": str(e)}
