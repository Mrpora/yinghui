# SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
# SPDX-License-Identifier: AGPL-3.0-or-later

"""对话 Agent 循环编排器——构建上下文 → 调用 LLM → 工具调用循环 → SSE 流式输出。

与 demoA 原版的核心差异：
- LLM 客户端统一为 LLMClient（替代 AsyncOpenAI）
- 对话持久化：SQLite character_chats 表（替代 Redis）
- 记忆维度：user + novel（替代 user + character）
- SSE 输出：SSEManager.broadcast() + AsyncGenerator yield
- reasoning_content 写入上下文
"""

import asyncio
import json
import logging
import random
from datetime import datetime, timedelta, timezone
from typing import AsyncGenerator

from server.config import config
from server.storage.sqlite_client import get_db, now_ms
from server.ai.common.llm_client import LLMClient
from server.services.care_service import judge_and_prepare_care
from server.prompt_loader import get_prompt
from server.ai.chat_agent.tools import TOOL_DEFINITIONS, execute_tool_call

logger = logging.getLogger(__name__)

client = LLMClient(config)


# ── 上下文构建 ──

async def _load_character_info(character_id: str) -> dict | None:
    """从 novel_characters 表加载角色信息。"""
    db = await get_db()
    cursor = await db.execute(
        """SELECT character_snapshot, story_context
           FROM novel_characters
           WHERE character_id = ? AND is_deleted = 0""",
        (character_id,),
    )
    row = await cursor.fetchone()
    if row is None:
        return None

    snapshot = json.loads(row["character_snapshot"])
    return {
        "name": snapshot.get("name", ""),
        "identity": snapshot.get("identity", ""),
        "personality": ",".join(snapshot.get("personality_traits", []))
                       or snapshot.get("personality", ""),
        "speech_style": snapshot.get("speech_style", ""),
        "goal": snapshot.get("goal", ""),
        "backstory": snapshot.get("backstory", ""),
        "story_context": row["story_context"] or "",
    }


async def _build_system_messages(
    character_id: str,
    user_id: str,
    novel_id: str,
    current_time: str,
) -> list[dict]:
    """构建系统消息数组（不含回响记忆和对话历史——由 run() 注入）。"""
    char_info = await _load_character_info(character_id)
    if char_info is None:
        raise ValueError(f"角色不存在: {character_id}")

    messages: list[dict] = []

    template = get_prompt("chat_agent/system_prompt")
    if not template:
        raise RuntimeError("系统提示词模板未加载: chat_agent/system_prompt")

    system_prompt = template
    system_prompt = system_prompt.replace("{character_name}", char_info["name"])
    system_prompt = system_prompt.replace("{identity}", char_info["identity"])
    system_prompt = system_prompt.replace("{personality}", char_info["personality"])
    system_prompt = system_prompt.replace("{speech_style}", char_info["speech_style"])
    system_prompt = system_prompt.replace("{goal}", char_info["goal"])
    system_prompt = system_prompt.replace("{backstory}", char_info["backstory"])
    system_prompt = system_prompt.replace("{story_context}", char_info["story_context"])
    messages.append({"role": "system", "content": system_prompt})
    logger.info("📋 系统提示词注入 %d 字符", len(system_prompt))

    # 用户事实记忆
    db = await get_db()
    now = now_ms()
    cursor = await db.execute(
        """SELECT content, memory_id FROM memories
           WHERE user_id = ? AND novel_id = ?
             AND memory_type = 'user_fact'
             AND (expires_at IS NULL OR expires_at >= ?)
           ORDER BY updated_at DESC""",
        (user_id, novel_id, now),
    )
    facts = await cursor.fetchall()
    if facts:
        fact_lines = [f"- {row['content']} ({row['memory_id']})" for row in facts]
        messages.append({
            "role": "system",
            "content": "## 永久记忆——用户事实\n" + "\n".join(fact_lines),
        })
        logger.info("📌 用户事实注入 %d 条", len(facts))

    messages.append({"role": "system", "content": f"## 当前时间\n{current_time}"})
    return messages


# ── 对话持久化 ──

async def _load_chat_messages(chat_id: str) -> list[dict]:
    db = await get_db()
    cursor = await db.execute(
        "SELECT messages FROM character_chats WHERE chat_id = ? AND is_deleted = 0",
        (chat_id,),
    )
    row = await cursor.fetchone()
    if row is None:
        return []
    return json.loads(row["messages"] or "[]")


async def _save_chat_messages(chat_id: str, messages: list[dict]):
    db = await get_db()
    now = now_ms()
    await db.execute(
        "UPDATE character_chats SET messages = ?, modified_at = ? WHERE chat_id = ?",
        (json.dumps(messages, ensure_ascii=False), now, chat_id),
    )
    await db.commit()


async def _ensure_chat_exists(chat_id: str, user_id: str, novel_id: str, character_id: str):
    db = await get_db()
    cursor = await db.execute(
        "SELECT chat_id FROM character_chats WHERE chat_id = ?",
        (chat_id,),
    )
    row = await cursor.fetchone()
    if row is None:
        now = now_ms()
        await db.execute(
            """INSERT INTO character_chats
               (chat_id, user_id, novel_id, character_id, messages, is_deleted, created_at)
               VALUES (?, ?, ?, ?, '[]', 0, ?)""",
            (chat_id, user_id, novel_id, character_id, now),
        )
        await db.commit()
        logger.info("📦 新建聊天记录 chat_id=%s", chat_id)


async def _is_new_chat(chat_id: str) -> bool:
    messages = await _load_chat_messages(chat_id)
    dialogue_msgs = [m for m in messages if m["role"] in ("user", "character")]
    return len(dialogue_msgs) == 0


async def _execute_tool_calls_batch(
    tool_calls_by_index: dict,
    messages: list[dict],
    user_id: str,
    novel_id: str,
    character_id: str,
    nickname: str,
) -> bool:
    """并行执行一批工具调用，返回是否触发 memory_full。"""

    async def _exec_one(idx: int, tc: dict) -> tuple[int, dict]:
        name = tc["function"]["name"]
        raw_args = tc["function"]["arguments"]
        try:
            args = json.loads(raw_args) if raw_args else {}
        except json.JSONDecodeError:
            logger.warning("工具参数 JSON 解析失败: %s", raw_args)
            args = {}
        result = await execute_tool_call(
            name, args, user_id, novel_id, character_id, nickname)
        return idx, result

    results = await asyncio.gather(*[
        _exec_one(idx, tool_calls_by_index[idx])
        for idx in sorted(tool_calls_by_index.keys())
    ])

    memory_full_triggered = False
    for idx, result in results:
        tc = tool_calls_by_index[idx]
        if tc["function"]["name"] == "write_memory" and result.get("status") == "error":
            memory_full_triggered = True
        messages.append({
            "role": "tool",
            "tool_call_id": tc["id"],
            "content": json.dumps(result, ensure_ascii=False),
        })

    return memory_full_triggered


# ── 主入口 ──

async def run(
    chat_id: str,
    user_id: str,
    novel_id: str,
    character_id: str,
    content: str | None,
    sse_manager=None,
) -> AsyncGenerator[dict, None]:
    """Agent 循环主入口，产出 SSE 事件 dict。

    content 为 None 表示首次进入对话（触发开场问候）。
    """
    beijing_tz = timezone(timedelta(hours=8))
    now = datetime.now(beijing_tz)
    weekday_names = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    current_time = f"{now.year}年{now.month}月{now.day}日 {weekday_names[now.weekday()]} "
    current_time += f"{now.hour:02d}:{now.minute:02d}:{now.second:02d}（北京时间）"
    ms_now = now_ms()
    sse_channel = f"chat:{chat_id}"

    async def _emit(event: dict):
        yield event
        if sse_manager:
            await sse_manager.broadcast(sse_channel, event)

    # 0. 确保聊天记录存在
    await _ensure_chat_exists(chat_id, user_id, novel_id, character_id)

    # 1. 记忆回响判断
    db = await get_db()
    cursor = await db.execute(
        """SELECT level FROM care_settings
           WHERE user_id = ? AND novel_id = ? AND character_id = ?""",
        (user_id, novel_id, character_id),
    )
    care_row = await cursor.fetchone()
    care_level = care_row["level"] if care_row else 80

    is_new = await _is_new_chat(chat_id)
    care_event = await judge_and_prepare_care(
        user_id, novel_id, character_id, care_level, is_new)
    if care_event is not None:
        logger.info("回响触发 chat=%s care_level=%d", chat_id, care_level)

    # 2. 构建消息列表
    logger.info("Agent 开始 chat=%s user=%s novel=%s char=%s",
                chat_id, user_id, novel_id, character_id)
    messages = await _build_system_messages(character_id, user_id, novel_id, current_time)

    if care_event is not None:
        messages.append({"role": "system", "content": care_event["content"]})
        logger.info("💚 回响记忆注入")

    # 对话历史（仅加载最近 N 条，完整历史保留在 DB）
    chat_messages = await _load_chat_messages(chat_id)
    instant_msgs = [m for m in chat_messages if m["role"] in ("user", "character")]
    instant_msgs = instant_msgs[-config.INSTANT_MEMORY_SIZE:]
    for msg in instant_msgs:
        role = "assistant" if msg["role"] == "character" else msg["role"]
        messages.append({"role": role, "content": msg["content"]})
    if instant_msgs:
        user_msgs = sum(1 for m in instant_msgs if m["role"] == "user")
        char_msgs = sum(1 for m in instant_msgs if m["role"] == "character")
        logger.info("💬 对话历史注入 user=%d char=%d", user_msgs, char_msgs)

    # 用户本轮消息
    if content:
        messages.append({"role": "user", "content": content})
        logger.info("👤 用户输入 (%d 字符)", len(content))
    else:
        messages.append({
            "role": "system",
            "content": "（用户刚刚进入对话，还没有说话。请用符合你性格的普通问候语主动开场。）",
        })
        logger.info("🚪 开场指令注入")

    # 昵称
    cursor = await db.execute(
        "SELECT nickname FROM users WHERE user_id = ?", (user_id,)
    )
    user_row = await cursor.fetchone()
    nickname = user_row["nickname"] if user_row else "unknown"

    # 上下文汇总日志
    role_counts = {}
    for m in messages:
        role_counts[m["role"]] = role_counts.get(m["role"], 0) + 1
    total_chars = sum(len(m.get("content") or "") for m in messages)
    logger.info("📦 上下文构建完成 messages=%d chars=%d roles=%s",
                len(messages), total_chars, role_counts)

    # 3. Agent 循环
    loop_count = 0
    dialogue_text: str | None = None

    yield {"event": "thinking", "data": {}}
    if sse_manager:
        await sse_manager.broadcast(sse_channel, {"event": "thinking", "data": {}})

    while loop_count < config.CHAT_MAX_AGENT_LOOP:
        loop_count += 1
        logger.info("=== Agent 循环 #%d chat=%s ===", loop_count, chat_id)

        response = await client.generate(
            messages=messages,
            reasoning_effort=config.CHAT_REASONING_EFFORT,
            model=config.CHAT_MODEL,
            tools=TOOL_DEFINITIONS,
            temperature=config.CHAT_TEMPERATURE,
            top_p=config.CHAT_TOP_P,
            frequency_penalty=config.CHAT_FREQUENCY_PENALTY,
            presence_penalty=config.CHAT_PRESENCE_PENALTY,
            max_tokens=config.CHAT_MAX_TOKENS,
            stop=config.CHAT_STOP,
            seed=config.CHAT_SEED,
            caller="ChatAgent",
        )

        reasoning = response.reasoning_content or ""
        if reasoning:
            logger.info("🧠 思考 (%d 字符)", len(reasoning))

        if response.tool_calls:
            tool_names = [tc["function"]["name"] for tc in response.tool_calls]
            logger.info("🔧 工具调用: %s", tool_names)

            if "retrieve_memories" in tool_names:
                yield {"event": "retrieving", "data": {}}
                if sse_manager:
                    await sse_manager.broadcast(sse_channel, {"event": "retrieving", "data": {}})
            if any(n in tool_names for n in ("write_memory", "update_memory", "delete_memory")):
                yield {"event": "memorizing", "data": {}}
                if sse_manager:
                    await sse_manager.broadcast(sse_channel, {"event": "memorizing", "data": {}})

            assistant_msg: dict = {
                "role": "assistant",
                "content": None,
                "tool_calls": response.tool_calls,
            }
            if reasoning:
                assistant_msg["reasoning_content"] = reasoning
            messages.append(assistant_msg)

            tool_calls_by_index = {i: tc for i, tc in enumerate(response.tool_calls)}
            memory_full = await _execute_tool_calls_batch(
                tool_calls_by_index, messages, user_id, novel_id,
                character_id, nickname)

            if memory_full:
                yield {"event": "memory_full", "data": {"limit": config.MEMORY_LIMIT}}
                if sse_manager:
                    await sse_manager.broadcast(sse_channel, {
                        "event": "memory_full", "data": {"limit": config.MEMORY_LIMIT},
                    })
                logger.warning("⚠️ 记忆容量已满 chat=%s limit=%d", chat_id, config.MEMORY_LIMIT)
            continue

        # 对话输出路径——逐 token 流式推送
        dialogue_text = (response.content or "").strip()
        logger.info("💬 模型输出 (%d 字符)", len(dialogue_text))

        i = 0
        while i < len(dialogue_text):
            step = random.randint(2, 4)
            chunk = dialogue_text[i:i + step]
            yield {"event": "token", "data": {"content": chunk}}
            if sse_manager:
                await sse_manager.broadcast(sse_channel, {"event": "token", "data": {"content": chunk}})
            i += step
            await asyncio.sleep(random.uniform(0.015, 0.06))
        break

    if dialogue_text is None:
        logger.warning("MAX_AGENT_LOOP 耗尽 chat=%s", chat_id)
        dialogue_text = ""

    # 4. 持久化
    existing_msgs = await _load_chat_messages(chat_id)
    round_num = sum(1 for m in existing_msgs if m["role"] == "character") + 1
    new_messages = list(existing_msgs)

    if content:
        new_messages.append({
            "role": "user", "content": content,
            "timestamp": ms_now, "round": round_num,
        })
    new_messages.append({
        "role": "character", "content": dialogue_text or "",
        "timestamp": ms_now, "round": round_num,
    })

    await _save_chat_messages(chat_id, new_messages)

    character_msg = {
        "role": "character", "content": dialogue_text or "",
        "timestamp": ms_now, "round": round_num,
    }
    logger.info("Agent 完成 chat=%s loops=%d round=%d", chat_id, loop_count, round_num)

    done_event = {
        "event": "done",
        "data": {
            "chat_id": chat_id, "user_id": user_id,
            "novel_id": novel_id, "character_id": character_id,
            "message": character_msg,
        },
    }
    yield done_event
    if sse_manager:
        await sse_manager.broadcast(sse_channel, done_event)
