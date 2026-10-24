# SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
# SPDX-License-Identifier: AGPL-3.0-or-later

"""agent_ops 领域服务层——/api/agent/* 的全部业务实现。

供 MCP server 与桥接进程回写领域数据使用（纯增量，不 import server/ai/
下任何模块；precheck 正则自 novel_agent/tools.py 原样复制，删除在 Task 2）。

约定：
- 纯函数式服务层，依赖显式入参（db / sse 由路由层注入），禁止模块级单例；
- 资源存在性校验一律 meta 级查询（直接 SELECT 行，不经 SessionManager.get()
  的世界重载路径——演化中软删世界不得引发 TypeError）；
- 失配一律抛 HTTPException(404, 中文 detail)；
- SSE 词汇冻结：演化 round_start/timeline_event/branches/session_paused/
  round_end/session_ended/relationships；聊天 thinking/retrieving/memorizing/
  token/done。
"""
import asyncio
import json
import logging
import random
import re
import statistics
from pathlib import Path

from fastapi import HTTPException

from server.config import config
from server.storage.sqlite_client import now_ms
from server.services.session_manager import SessionManager, SessionStatus
# JSON 列读-改-写进程内锁（Final Review Fix Important 3；Round 2 提升注册表至
# server/services/_resource_locks.py 供路由层共用——路由侧用户消息落库与
# select-branch/custom-event/intervene 写时间线与本模块竞争同一 JSON 列）。
from server.services._resource_locks import lock_for as _lock_for

logger = logging.getLogger(__name__)


# SSE 通道前缀（与前端既有订阅契约一致）
def evolution_channel(evolution_id: str) -> str:
    return f"evolution:{evolution_id}"


def chat_channel(chat_id: str) -> str:
    return f"chat:{chat_id}"


def novel_channel(task_id: str) -> str:
    return f"novel:{task_id}"


# ── 通用小工具 ──

def _loads(text, default):
    """JSON 容错解析——空/损坏时返回 default。"""
    if not text:
        return default
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return default


async def _require_row(db, sql: str, params: tuple, detail: str) -> dict:
    """meta 级存在性校验——直接 SELECT 行，失配 404（中文 detail）。"""
    cursor = await db.execute(sql, params)
    row = await cursor.fetchone()
    if row is None:
        raise HTTPException(404, detail)
    return dict(row)


async def _require_evolution(db, evolution_id: str) -> dict:
    return await _require_row(
        db,
        "SELECT * FROM world_evolutions WHERE evolution_id = ? AND is_deleted = 0",
        (evolution_id,), "演化会话不存在")


async def _require_chat(db, chat_id: str) -> dict:
    return await _require_row(
        db,
        "SELECT * FROM character_chats WHERE chat_id = ? AND is_deleted = 0",
        (chat_id,), "对话不存在")


async def _require_novel(db, novel_id: str) -> dict:
    return await _require_row(
        db,
        "SELECT * FROM novels WHERE novel_id = ? AND is_deleted = 0",
        (novel_id,), "小说不存在")


async def _require_task(db, task_id: str) -> dict:
    return await _require_row(
        db, "SELECT * FROM novel_tasks WHERE task_id = ?",
        (task_id,), "任务不存在")


async def _require_memory(db, memory_id: str) -> dict:
    return await _require_row(
        db, "SELECT * FROM memories WHERE memory_id = ?",
        (memory_id,), "记忆不存在")


async def _require_world(db, world_id: str, detail: str = "世界不存在") -> dict:
    # 注意：不过滤 is_deleted——软删世界的演化仍可读取（meta 级查询的核心诉求）
    return await _require_row(
        db, "SELECT * FROM worlds WHERE world_id = ?", (world_id,), detail)


async def _world_characters(db, world_id: str) -> list[dict]:
    cursor = await db.execute(
        "SELECT * FROM world_characters WHERE world_id = ? ORDER BY sort_order ASC",
        (world_id,),
    )
    return [dict(r) for r in await cursor.fetchall()]


async def _require_world_character(db, evolution: dict, name: str) -> dict:
    """校验角色名属于演化的世界，返回 world_characters 行。"""
    cursor = await db.execute(
        "SELECT * FROM world_characters WHERE world_id = ? AND name = ?",
        (evolution["world_id"], name),
    )
    row = await cursor.fetchone()
    if row is None:
        raise HTTPException(404, "角色不存在")
    return dict(row)


def _world_snapshot(world_row: dict, characters: list[dict]) -> dict:
    """构建 world 快照（与 seed_presets 的落库形状一致）。"""
    return {
        "name": world_row["name"],
        "description": world_row["description"],
        "world_history": world_row.get("world_history", ""),
        "rules": _loads(world_row.get("rules"), []),
        "characters": characters,
    }


def _character_view(row: dict) -> dict:
    """world_characters 行 → API 视图（attitudes 解析为对象）。"""
    view = dict(row)
    view["attitudes"] = _loads(row.get("attitudes"), {})
    return view


async def _append_timeline(db, evolution_id: str, event: dict) -> None:
    """追加时间线事件并持久化（锁内完成读-改-写，防并发丢更新）。"""
    async with _lock_for(f"evolution:{evolution_id}"):
        cursor = await db.execute(
            "SELECT timeline FROM world_evolutions WHERE evolution_id = ? AND is_deleted = 0",
            (evolution_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            raise HTTPException(404, "演化会话不存在")
        timeline = _loads(row["timeline"], [])
        timeline.append(event)
        await db.execute(
            "UPDATE world_evolutions SET timeline = ? WHERE evolution_id = ?",
            (json.dumps(timeline, ensure_ascii=False), evolution_id),
        )
        await db.commit()


async def _update_evolution_status(db, evolution_id: str, status: str) -> None:
    await db.execute(
        "UPDATE world_evolutions SET status = ? WHERE evolution_id = ?",
        (status, evolution_id),
    )
    await db.commit()


def _memory_view(row: dict) -> dict:
    """memories 行 → API 视图（memory_type 重命名为 type）。"""
    view = {k: row[k] for k in (
        "memory_id", "user_id", "novel_id", "character_id", "memory_type",
        "content", "created_at", "updated_at", "expires_at") if k in row}
    view["type"] = view.pop("memory_type")
    return view


# ═══════════════════════════════════════════════════════════
# 演化组
# ═══════════════════════════════════════════════════════════

async def get_world_config(db, evolution_id: str) -> dict:
    """读世界配置 + 角色列表（软删世界不拦截——meta 级查询）。"""
    evolution = await _require_evolution(db, evolution_id)
    world = await _require_world(db, evolution["world_id"])
    chars = await _world_characters(db, evolution["world_id"])
    return {
        "world_config": {
            "name": world["name"],
            "description": world["description"],
            "world_history": world.get("world_history", ""),
            "rules": _loads(world.get("rules"), []),
            "initial_event": _loads(world.get("initial_event"), {}),
        },
        "characters": [_character_view(c) for c in chars],
    }


async def get_timeline(db, evolution_id: str, since_round: int = 0) -> dict:
    """读时间线（since_round 过滤）/关系图/轮次进度。"""
    evolution = await _require_evolution(db, evolution_id)
    events = [
        e for e in _loads(evolution["timeline"], [])
        if int(e.get("round", 0)) >= since_round
    ]
    return {
        "events": events,
        "relationships": _loads(evolution["relationships"], {}),
        "current_round": int(evolution["current_round"]),
        "max_rounds": int(evolution["max_rounds"]),
        "status": evolution["status"],
    }


async def write_timeline_event(
    db, sse, evolution_id: str, *, event_type: str, content: str,
    character: str | None = None, motive: str | None = None,
    inner_thoughts: str | None = None, source: str | None = None,
    round_number: int | None = None,
) -> dict:
    """写时间线事件（类型校验复用 SessionManager 现有词汇集）+ SSE timeline_event。"""
    evolution = await _require_evolution(db, evolution_id)
    if event_type not in SessionManager.VALID_EVENT_TYPES:
        raise HTTPException(422, f"无效的事件类型: {event_type}")

    event: dict = {
        "type": event_type,
        "round": round_number if round_number is not None else int(evolution["current_round"]),
        "content": content,
    }
    if character is not None:
        event["character"] = character
        # 角色强调色（无则省略，与原 evolution_agent 行为一致）
        cursor = await db.execute(
            "SELECT accent_color FROM world_characters WHERE world_id = ? AND name = ?",
            (evolution["world_id"], character),
        )
        row = await cursor.fetchone()
        if row is not None and row["accent_color"]:
            event["character_color"] = row["accent_color"]
    if source is not None:
        event["source"] = source
    if motive is not None:
        event["motive"] = motive
    if inner_thoughts is not None:
        event["inner_thoughts"] = inner_thoughts

    await _append_timeline(db, evolution_id, event)
    await sse.broadcast(evolution_channel(evolution_id), {
        "type": "timeline_event",
        "data": {"event": event},
    })
    return event


async def write_round_summary(db, sse, evolution_id: str, round_number: int,
                              summary: str) -> dict:
    """写轮总结——内部写 round_summary 时间线事件（走同一 SSE）。"""
    return await write_timeline_event(
        db, sse, evolution_id,
        event_type="round_summary", content=summary, round_number=round_number,
    )


async def update_relationships(db, sse, evolution_id: str, edges: list[dict]) -> dict:
    """合并关系边进 relationships JSON + SSE relationships（全量边广播）。

    relationships 读-改-写在 `evolution:{eid}` 锁内完成（防并发丢更新）；
    SSE 广播在锁外（锁内不 await 其他资源操作）。
    """
    await _require_evolution(db, evolution_id)
    async with _lock_for(f"evolution:{evolution_id}"):
        cursor = await db.execute(
            "SELECT relationships FROM world_evolutions WHERE evolution_id = ?",
            (evolution_id,),
        )
        row = await cursor.fetchone()
        relationships = _loads(row["relationships"] if row is not None else None, {})
        for edge in edges:
            relationships.setdefault(edge["from_character"], {})[edge["to_character"]] = \
                edge["description"]

        await db.execute(
            "UPDATE world_evolutions SET relationships = ? WHERE evolution_id = ?",
            (json.dumps(relationships, ensure_ascii=False), evolution_id),
        )
        await db.commit()

    all_edges = [
        {"from": from_char, "to": to_char, "relationship": rel}
        for from_char, targets in relationships.items()
        for to_char, rel in targets.items()
    ]
    await sse.broadcast(evolution_channel(evolution_id), {
        "type": "relationships",
        "data": {"edges": all_edges},
    })
    return {"relationships": relationships}


async def push_branches(db, sse, evolution_id: str, branches: list[dict]) -> dict:
    """推分支：写 branch_options 事件 + SSE branches + SSE session_paused + 置 PAUSED。

    回合内迁移：仅 RUNNING 会话允许（非 RUNNING → 409）。
    """
    evolution = await _require_evolution(db, evolution_id)
    if evolution["status"] != SessionStatus.RUNNING.value:
        raise HTTPException(409, "当前状态不允许推送分支（仅运行中的会话可在回合内暂停）")

    indexed = [
        {"index": i, "title": b["title"], "description": b["description"]}
        for i, b in enumerate(branches)
    ]
    event = {
        "type": "branch_options",
        "round": int(evolution["current_round"]),
        "content": json.dumps(indexed, ensure_ascii=False),
    }
    await _append_timeline(db, evolution_id, event)
    await sse.broadcast(evolution_channel(evolution_id), {
        "type": "branches",
        "data": {"branches": indexed},
    })
    await _update_evolution_status(db, evolution_id, SessionStatus.PAUSED.value)
    await sse.broadcast(evolution_channel(evolution_id), {
        "type": "session_paused",
        "data": {"reason": "conflict",
                 "message": "检测到冲突，请选择剧情分支或输入自定义事件"},
    })
    return {"branches": indexed}


async def get_pending_branches(db, evolution_id: str) -> list[dict] | None:
    """解析 timeline 最后一条 branch_options 事件为待决分支。

    容错同前端 evolution.ts：content 非法 JSON → null；数组元素缺字段跳过。
    """
    evolution = await _require_evolution(db, evolution_id)
    events = _loads(evolution["timeline"], [])
    last = next(
        (e for e in reversed(events) if e.get("type") == "branch_options"), None)
    if last is None:
        return None

    parsed = _loads(last.get("content"), None)
    if not isinstance(parsed, list):
        return None

    branches: list[dict] = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        title = item.get("title")
        description = item.get("description")
        if not isinstance(title, str) or not title:
            continue
        if not isinstance(description, str):
            continue
        branches.append({
            "index": item.get("index", len(branches)),
            "title": title,
            "description": description,
        })
    return branches


async def complete_round(db, sse, evolution_id: str) -> dict:
    """收束回合（领域判定）：额度用尽 → ENDED + session_ended；否则
    WAITING_NEXT_ROUND + round_end。"""
    evolution = await _require_evolution(db, evolution_id)
    current = int(evolution["current_round"])
    max_rounds = int(evolution["max_rounds"])

    if current >= max_rounds:
        await _update_evolution_status(db, evolution_id, SessionStatus.ENDED.value)
        await sse.broadcast(evolution_channel(evolution_id), {
            "type": "session_ended",
            "data": {"reason": "rounds_exhausted",
                     "message": f"演化额度已用完（{current}/{max_rounds}）"},
        })
        return {"status": SessionStatus.ENDED.value, "round": current}

    await _update_evolution_status(
        db, evolution_id, SessionStatus.WAITING_NEXT_ROUND.value)
    await sse.broadcast(evolution_channel(evolution_id), {
        "type": "round_end",
        "data": {"round": current, "remaining_rounds": max_rounds - current},
    })
    return {"status": SessionStatus.WAITING_NEXT_ROUND.value, "round": current}


async def recover_session(db, sse, evolution_id: str, reason: str) -> dict:
    """回收函数（bridge 启动扫场与运行期失败共用）：RUNNING → WAITING_NEXT_ROUND
    + SSE error + SSE round_end；非 RUNNING 幂等返回现状。"""
    evolution = await _require_evolution(db, evolution_id)
    current = int(evolution["current_round"])
    status = evolution["status"]

    if status != SessionStatus.RUNNING.value:
        return {"status": status, "round": current}

    await _update_evolution_status(
        db, evolution_id, SessionStatus.WAITING_NEXT_ROUND.value)
    await sse.broadcast(evolution_channel(evolution_id), {
        "type": "error",
        "data": {"message": reason},
    })
    await sse.broadcast(evolution_channel(evolution_id), {
        "type": "round_end",
        "data": {"round": current,
                 "remaining_rounds": max(int(evolution["max_rounds"]) - current, 0)},
    })
    logger.warning("♻️ 演化会话回收 evolution=%s round=%d reason=%s",
                   evolution_id, current, reason)
    return {"status": SessionStatus.WAITING_NEXT_ROUND.value, "round": current}


async def get_character_context(db, evolution_id: str, name: str) -> list[dict]:
    """读角色持久化上下文镜像。"""
    evolution = await _require_evolution(db, evolution_id)
    await _require_world_character(db, evolution, name)
    contexts = _loads(evolution["character_contexts"], {})
    return contexts.get(name, [])


async def append_character_context(db, evolution_id: str, name: str,
                                   message: str) -> list[dict]:
    """追加角色上下文（system 消息）并持久化——MCP 写入的落点。

    character_contexts 读-改-写在 `evolution:{eid}` 锁内完成（防并发丢更新）。
    """
    evolution = await _require_evolution(db, evolution_id)
    await _require_world_character(db, evolution, name)
    async with _lock_for(f"evolution:{evolution_id}"):
        cursor = await db.execute(
            "SELECT character_contexts FROM world_evolutions WHERE evolution_id = ?",
            (evolution_id,),
        )
        row = await cursor.fetchone()
        contexts = _loads(row["character_contexts"] if row is not None else None, {})
        messages = contexts.get(name, [])
        messages.append({"role": "system", "content": message})
        contexts[name] = messages
        await db.execute(
            "UPDATE world_evolutions SET character_contexts = ? WHERE evolution_id = ?",
            (json.dumps(contexts, ensure_ascii=False), evolution_id),
        )
        await db.commit()
    return messages


async def get_character_profile(db, evolution_id: str, name: str) -> dict:
    """读角色人设（world_characters 行全字段）。"""
    evolution = await _require_evolution(db, evolution_id)
    row = await _require_world_character(db, evolution, name)
    return _character_view(row)


# ═══════════════════════════════════════════════════════════
# 聊天组
# ═══════════════════════════════════════════════════════════

async def retrieve_memories(db, user_id: str, novel_id: str, character_id: str,
                            query: str, top_k: int | None = None) -> list[dict]:
    """记忆混合检索——retrieval_service.retrieve 直通。"""
    from server.services import retrieval_service
    await _require_novel(db, novel_id)
    if top_k is None:
        return await retrieval_service.retrieve(
            query=query, user_id=user_id, novel_id=novel_id,
            character_id=character_id)
    return await retrieval_service.retrieve(
        query=query, user_id=user_id, novel_id=novel_id,
        character_id=character_id, top_k=top_k)


async def list_user_facts(db, user_id: str, novel_id: str) -> list[dict]:
    """全量 user_fact 记忆读取（供 chat_flow 组装 prompt 直注入）。"""
    await _require_novel(db, novel_id)
    now = now_ms()
    cursor = await db.execute(
        """SELECT * FROM memories
           WHERE user_id = ? AND novel_id = ?
             AND memory_type = 'user_fact'
             AND (expires_at IS NULL OR expires_at >= ?)
           ORDER BY updated_at DESC""",
        (user_id, novel_id, now),
    )
    return [_memory_view(dict(r)) for r in await cursor.fetchall()]


async def write_memory(db, user_id: str, novel_id: str, character_id: str,
                       content: str, memory_type: str,
                       expires_at: int | None = None) -> dict:
    """写永久记忆；容量满 → 409。importance 参数无落库列，仅为契约兼容接收。"""
    from server.services import memory_service

    await _require_row(db, "SELECT user_id FROM users WHERE user_id = ?",
                       (user_id,), "用户不存在")
    await _require_novel(db, novel_id)
    await _require_row(
        db, "SELECT character_id FROM novel_characters WHERE character_id = ?",
        (character_id,), "角色不存在")
    if memory_type not in ("user_fact", "event"):
        raise HTTPException(422, f"无效的记忆类型: {memory_type}（须为 user_fact 或 event）")

    result = await memory_service.create_memory(
        user_id, novel_id, character_id, memory_type, content, expires_at)
    if result.get("status") != "success":
        raise HTTPException(409, result.get("message", "记忆写入失败"))

    row = await _require_memory(db, result["memory_id"])
    return {"memory": _memory_view(row)}


async def update_memory(db, memory_id: str, content: str | None = None,
                        memory_type: str | None = None,
                        expires_at: int | None = None) -> dict:
    """更新记忆（内容/类型/过期时间）。importance 无落库列，仅为契约兼容接收。"""
    from server.services import memory_service

    row = await _require_memory(db, memory_id)
    if memory_type is not None and memory_type not in ("user_fact", "event"):
        raise HTTPException(422, f"无效的记忆类型: {memory_type}（须为 user_fact 或 event）")

    if content is not None or memory_type is not None:
        await memory_service.update_memory(
            memory_id, content if content is not None else row["content"],
            memory_type)
    if expires_at is not None:
        await memory_service.update_expiry(memory_id, expires_at)

    updated = await _require_memory(db, memory_id)
    return {"memory": _memory_view(updated)}


async def delete_memory(db, memory_id: str) -> dict:
    """删除记忆（清理三张表）。"""
    from server.services import memory_service

    await _require_memory(db, memory_id)
    await memory_service.delete_memory(memory_id)
    return {"ok": True}


async def report_extreme_emotion(db, user_id: str, novel_id: str,
                                 character_id: str, summary: str,
                                 level: float) -> dict:
    """极端情绪安全上报——safety_service.send_alert 直通（写入 logs/safety.log）。"""
    from server.services.safety_service import send_alert

    cursor = await db.execute(
        "SELECT nickname FROM users WHERE user_id = ?", (user_id,))
    row = await cursor.fetchone()
    if row is None:
        raise HTTPException(404, "用户不存在")
    send_alert(row["nickname"], summary, str(level))
    return {"ok": True}


async def get_chat_history(db, chat_id: str, last_n: int = 20) -> list[dict]:
    """读对话历史最近 last_n 条。"""
    chat = await _require_chat(db, chat_id)
    messages = _loads(chat["messages"], [])
    return messages[-last_n:] if last_n > 0 else messages


async def get_character_snapshot(db, character_id: str) -> dict:
    """读角色快照（novel_characters.character_snapshot）。"""
    row = await _require_row(
        db,
        "SELECT * FROM novel_characters WHERE character_id = ?",
        (character_id,), "角色不存在")
    return _loads(row["character_snapshot"], {})


async def append_chat_message(db, chat_id: str, message: dict) -> dict:
    """追加对话消息并持久化（bridge 写用户/角色消息用）。"""
    chat = await _require_chat(db, chat_id)
    content = message.get("content")
    if not isinstance(content, str) or not content:
        raise HTTPException(422, "message.content 必须为非空字符串")
    role = message.get("role", "character")
    if role not in ("user", "character", "system"):
        raise HTTPException(422, f"无效的消息角色: {role}")

    entry = {**message, "role": role, "content": content}
    entry.setdefault("timestamp", now_ms())

    async with _lock_for(f"chat:{chat_id}"):
        # 锁内重读 messages（entry 校验用的 chat 行可能已过期）——读-改-写原子
        fresh = await _require_chat(db, chat_id)
        messages = _loads(fresh["messages"], [])
        messages.append(entry)
        await db.execute(
            "UPDATE character_chats SET messages = ?, modified_at = ? WHERE chat_id = ?",
            (json.dumps(messages, ensure_ascii=False), now_ms(), chat_id),
        )
        await db.commit()
    return {"ok": True}


async def emit_chat_stage(db, sse, chat_id: str, stage: str) -> None:
    """发聊天阶段事件（SSE thinking/retrieving/memorizing；stage 由路由层 Literal 校验）。"""
    await _require_chat(db, chat_id)
    await sse.broadcast(chat_channel(chat_id), {"event": stage, "data": {}})


async def emit_chat_error(db, sse, chat_id: str, message: str) -> None:
    """发聊天错误事件（SSE error，终结 chats/start 持流代理；bridge 治理路径用）。"""
    await _require_chat(db, chat_id)
    await sse.broadcast(chat_channel(chat_id), {"event": "error", "data": {"message": message}})


async def chat_done(db, sse, chat_id: str, character_message: dict) -> dict:
    """持久化角色消息 + 2-4 字符随机分块（sleep 0.02-0.06s）广播 SSE token* + done。

    复刻原 chat_agent/agent.py 假流式行为（分块 2-4 字符一致，
    sleep 区间按 brief 为 0.02-0.06s）。
    """
    chat = await _require_chat(db, chat_id)
    content = character_message.get("content")
    if not isinstance(content, str):
        raise HTTPException(422, "character_message.content 必须为字符串")

    async with _lock_for(f"chat:{chat_id}"):
        # 消息读-改-写在 `chat:{cid}` 锁内完成（防并发丢更新）；
        # 锁内不做 SSE 广播/其他资源 await
        fresh = await _require_chat(db, chat_id)
        messages = _loads(fresh["messages"], [])
        round_num = sum(1 for m in messages if m.get("role") == "character") + 1
        character_msg = {
            "role": "character",
            "content": content,
            "timestamp": now_ms(),
            "round": round_num,
        }
        messages.append(character_msg)
        await db.execute(
            "UPDATE character_chats SET messages = ?, modified_at = ? WHERE chat_id = ?",
            (json.dumps(messages, ensure_ascii=False), now_ms(), chat_id),
        )
        await db.commit()

    channel = chat_channel(chat_id)
    i = 0
    while i < len(content):
        step = random.randint(2, 4)
        chunk = content[i:i + step]
        await sse.broadcast(channel, {"event": "token", "data": {"content": chunk}})
        i += step
        await asyncio.sleep(random.uniform(0.02, 0.06))

    await sse.broadcast(channel, {
        "event": "done",
        "data": {
            "chat_id": chat_id,
            "user_id": chat["user_id"],
            "novel_id": chat["novel_id"],
            "character_id": chat["character_id"],
            "message": character_msg,
        },
    })
    return {"chat_id": chat_id, "message": character_msg}


# ═══════════════════════════════════════════════════════════
# 小说组
# ═══════════════════════════════════════════════════════════

def _task_work_dir(task_id: str) -> Path:
    """解析任务工作目录（相对路径基于项目根，承袭 novel_agent 行为）。"""
    base = Path(config.NOVEL_WORK_DIR_BASE)
    if not base.is_absolute():
        base = Path(__file__).resolve().parent.parent.parent / config.NOVEL_WORK_DIR_BASE
    return base / task_id


async def save_chapter(db, task_id: str, index: int, title: str, content: str) -> dict:
    """写章节文件 chapters/ch_{index}.md；title 在正文无标题时补 `# {title}`。"""
    await _require_task(db, task_id)
    chapters_dir = _task_work_dir(task_id) / "chapters"
    chapters_dir.mkdir(parents=True, exist_ok=True)
    text = content
    if title and not text.lstrip().startswith("#"):
        text = f"# {title}\n\n{text}"
    path = chapters_dir / f"ch_{index}.md"
    path.write_text(text, encoding="utf-8")
    return {"path": path.as_posix()}


async def read_chapter(db, task_id: str, index: int) -> str:
    """读章节文件内容。"""
    await _require_task(db, task_id)
    path = _task_work_dir(task_id) / "chapters" / f"ch_{index}.md"
    if not path.is_file():
        raise HTTPException(404, "章节不存在")
    return path.read_text(encoding="utf-8")


# ── precheck 硬门（自 server/ai/novel_agent/tools.py 原样迁移的纯函数）──

def _count_chinese_chars(text: str) -> int:
    """统计中文字符数（含中文标点）。"""
    count = 0
    for ch in text:
        if '一' <= ch <= '鿿' or ch in '，。！？；：、""''【】《》（）……——':
            count += 1
    return count


def _compute_sentence_stats(text: str) -> dict:
    sentences = re.split(r'[。！？；\n]', text)
    lengths = [_count_chinese_chars(s) for s in sentences if s.strip()]
    if not lengths:
        return {"count": 0, "mean": 0, "std": 0, "p10": 0, "p50": 0, "p90": 0,
                "buckets": {"<=5": 0, "6-10": 0, "11-20": 0, "21-35": 0, ">35": 0}}
    lengths.sort()
    n = len(lengths)
    return {
        "count": n,
        "mean": round(sum(lengths) / n, 1),
        "std": round(statistics.stdev(lengths), 1) if n >= 2 else 0,
        "p10": lengths[int(n * 0.1)] if n >= 10 else lengths[0],
        "p50": lengths[n // 2],
        "p90": lengths[int(n * 0.9)] if n >= 10 else lengths[-1],
        "buckets": {
            "<=5": sum(1 for l in lengths if l <= 5),
            "6-10": sum(1 for l in lengths if 6 <= l <= 10),
            "11-20": sum(1 for l in lengths if 11 <= l <= 20),
            "21-35": sum(1 for l in lengths if 21 <= l <= 35),
            ">35": sum(1 for l in lengths if l > 35),
        },
    }


def _count_same_length_groups(text: str) -> int:
    sentences = re.split(r'[。！？；\n]', text)
    lengths = [_count_chinese_chars(s) for s in sentences if s.strip()]
    if len(lengths) < 3:
        return 0
    groups = 0
    for i in range(len(lengths) - 2):
        a, b, c = lengths[i], lengths[i + 1], lengths[i + 2]
        if abs(a - b) < 5 and abs(b - c) < 5 and abs(a - c) < 5:
            groups += 1
    return groups


def _precheck_stats(text: str) -> dict:
    """AI 腔正则统计（原 _precheck_chapter 迁移，正则原样保留）。"""
    return {
        "star_count": len(re.findall(r'\n\*{3}\n', text)),
        "dash_count": len(re.findall(r'\n---\n', text)),
        "simile_estimate": len(re.findall(r'像是|仿佛|似乎|如同|宛如', text)),
        "fangfo_count": len(re.findall(r'仿佛', text)),
        "wanru_count": len(re.findall(r'宛如', text)),
        "ai_adverbs": {
            "渐渐": len(re.findall(r'渐渐', text)),
            "缓缓": len(re.findall(r'缓缓', text)),
            "突然": len(re.findall(r'突然', text)),
            "猛地": len(re.findall(r'猛地', text)),
            "轻轻": len(re.findall(r'轻轻', text)),
            "深深": len(re.findall(r'深深', text)),
            "默默": len(re.findall(r'默默', text)),
            "静静": len(re.findall(r'静静', text)),
        },
        "emotion_cliches": {
            "胃里翻涌/攥": len(re.findall(r'胃里.*翻涌|胃里.*攥', text)),
            "倒吸凉气": len(re.findall(r'倒吸.*凉气', text)),
            "心里一紧/心头一颤": len(re.findall(r'心里一紧|心头一颤|心头一震', text)),
        },
        "emotion_tags": {
            "胃里翻涌": len(re.findall(r'胃里翻涌', text)),
            "指尖攥紧": len(re.findall(r'指尖攥紧', text)),
            "心跳漏了一拍": len(re.findall(r'心跳漏了一拍', text)),
            "瞳孔一缩": len(re.findall(r'瞳孔一缩', text)),
        },
        "consecutive_same_length_groups": _count_same_length_groups(text),
        "subtle_ai_templates": {
            "呼吸停顿": len(re.findall(r'呼吸(?:停|停滞|屏住|凝滞)了(?:一瞬|半拍|片刻|一下)', text)),
            "沉默填充": len(re.findall(r'沉默(?:了|着)(?:半晌|许久|片刻|了很久|了一会儿)', text)),
            "静止填充": len(re.findall(r'一动不动地(?:站|蹲|坐|待)了很久', text)),
        },
        "de_count": len(re.findall(r'的', text)),
        "sentence_stats": _compute_sentence_stats(text),
    }


def precheck_chapter(text: str, *, min_chars: int, max_chars: int) -> dict:
    """确定性硬门检查：字数 ∈ [min_chars, max_chars] 且无 `---` 残留。

    AI 腔正则统计与句长统计随原函数一并迁移（供审查/重写 prompt 使用）。
    """
    stats = _precheck_stats(text)
    word_count = _count_chinese_chars(text)
    issues: list[str] = []
    if word_count < min_chars:
        issues.append(
            f"字数不足：当前 {word_count} 字，最低 {min_chars} 字，需扩写 {min_chars - word_count} 字")
    elif word_count > max_chars:
        issues.append(
            f"字数超出：当前 {word_count} 字，上限 {max_chars} 字，需压缩 {word_count - max_chars} 字")
    if stats["dash_count"] > 0:
        issues.append(
            f"检测到 {stats['dash_count']} 处 `---` 残留。`---` 是违禁分场符，请替换为 `***`")
    return {"passed": not issues, "issues": issues, "word_count": word_count,
            "stats": stats}


async def precheck_task_chapter(db, task_id: str, index: int) -> dict:
    """对任务章节执行硬门检查（阈值读 config）。"""
    text = await read_chapter(db, task_id, index)
    return precheck_chapter(
        text,
        min_chars=config.NOVEL_CHAPTER_MIN_CHARS,
        max_chars=config.NOVEL_CHAPTER_MAX_CHARS,
    )


async def assemble_novel(db, sse, task_id: str) -> dict:
    """按序拼接章节 → 写 novels 行（含 world_snapshot）→ 任务 completed + SSE completed。"""
    task = await _require_task(db, task_id)
    novel = await _require_novel(db, task["novel_id"])

    chapters_dir = _task_work_dir(task_id) / "chapters"
    files = list(chapters_dir.glob("ch_*.md")) if chapters_dir.is_dir() else []
    if not files:
        raise HTTPException(400, "无章节文件，无法拼卷")

    def _extract_num(p: Path) -> int:
        m = re.search(r'ch_(\d+)\.md$', p.name)
        return int(m.group(1)) if m else 10 ** 9

    files.sort(key=_extract_num)

    parts = ["***本小说由 AI 基于世界演化记录自动转化而成***\n\n"]
    total_chars = 0
    for idx, f in enumerate(files, start=1):
        text = f.read_text(encoding="utf-8")
        # 先剥离已有"第x章"前缀（LLM 可能不稳定输出），再统一编号（承旧 assemble 行为）
        text = re.sub(r'^#\s*第[一二三四五六七八九十百千0-9]+章\s*', '# ', text)
        text = re.sub(r'^# ', f'# 第{idx}章 ', text, count=1)
        parts.append(text)
        total_chars += _count_chinese_chars(text)

    full_text = "\n\n---\n\n".join(parts) + "\n\n（全篇完）\n"

    # world 快照（世界行不过滤软删——meta 级读取）
    world_row = await db.execute(
        "SELECT * FROM worlds WHERE world_id = ?", (novel["world_id"],))
    world = await world_row.fetchone()
    snapshot = (
        _world_snapshot(dict(world), await _world_characters(db, novel["world_id"]))
        if world is not None else _loads(novel["world_snapshot"], {})
    )

    await db.execute(
        "UPDATE novels SET content = ?, world_snapshot = ? WHERE novel_id = ?",
        (full_text, json.dumps(snapshot, ensure_ascii=False), novel["novel_id"]),
    )
    await db.execute(
        "UPDATE novel_tasks SET status = 'completed', result = ?, "
        "completed_at = ? WHERE task_id = ?",
        (json.dumps({"chapter_count": len(files), "total_chars": total_chars,
                     "novel_id": novel["novel_id"]}, ensure_ascii=False),
         now_ms(), task_id),
    )
    await db.commit()

    await sse.broadcast(novel_channel(task_id), {
        "type": "completed",
        "data": {"task_id": task_id, "novel_id": novel["novel_id"],
                 "chapter_count": len(files), "total_chars": total_chars},
    })
    logger.info("📖 小说拼卷完成 task=%s novel=%s chapters=%d chars=%d",
                task_id, novel["novel_id"], len(files), total_chars)
    return {"novel_id": novel["novel_id"], "status": "completed"}


async def get_task(db, task_id: str) -> dict:
    """读任务全字段。"""
    return {"task": await _require_task(db, task_id)}


async def fail_task(db, sse, task_id: str, reason: str) -> dict:
    """任务置 failed + SSE error。"""
    await _require_task(db, task_id)
    await db.execute(
        "UPDATE novel_tasks SET status = 'failed', error = ?, completed_at = ? "
        "WHERE task_id = ?",
        (reason, now_ms(), task_id),
    )
    await db.commit()
    await sse.broadcast(novel_channel(task_id), {
        "type": "error",
        "data": {"message": reason},
    })
    logger.warning("任务失败 task=%s reason=%s", task_id, reason)
    return {"ok": True}


async def get_novel_source(db, novel_id: str) -> dict:
    """读演化记录 + world 快照 + 角色（写作/提取种子）。"""
    novel = await _require_novel(db, novel_id)

    cursor = await db.execute(
        "SELECT timeline FROM world_evolutions WHERE evolution_id = ? AND is_deleted = 0",
        (novel["evolution_id"],),
    )
    evo = await cursor.fetchone()
    timeline = _loads(evo["timeline"], []) if evo is not None else []

    world_cursor = await db.execute(
        "SELECT * FROM worlds WHERE world_id = ?", (novel["world_id"],))
    world = await world_cursor.fetchone()
    if world is not None:
        chars = await _world_characters(db, novel["world_id"])
        snapshot = _world_snapshot(dict(world), [_character_view(c) for c in chars])
        characters = [_character_view(c) for c in chars]
    else:
        snapshot = _loads(novel["world_snapshot"], {})
        characters = snapshot.get("characters", [])

    return {"timeline": timeline, "world_snapshot": snapshot,
            "characters": characters}


async def get_novel_text(db, novel_id: str) -> dict:
    """读已生成全文（提取器输入）。"""
    novel = await _require_novel(db, novel_id)
    return {"content": novel["content"] or ""}


# ═══════════════════════════════════════════════════════════
# 通用
# ═══════════════════════════════════════════════════════════

async def care_echo(db, user_id: str, novel_id: str, character_id: str,
                    is_active: bool = True) -> dict:
    """关怀回响判定——care_service.judge_and_prepare_care 直通。"""
    from server.services.care_service import judge_and_prepare_care

    await _require_row(db, "SELECT user_id FROM users WHERE user_id = ?",
                       (user_id,), "用户不存在")
    await _require_novel(db, novel_id)
    await _require_row(
        db, "SELECT character_id FROM novel_characters WHERE character_id = ?",
        (character_id,), "角色不存在")

    cursor = await db.execute(
        """SELECT level FROM care_settings
           WHERE user_id = ? AND novel_id = ? AND character_id = ?""",
        (user_id, novel_id, character_id),
    )
    row = await cursor.fetchone()
    care_level = row["level"] if row is not None else 80

    event = await judge_and_prepare_care(
        user_id, novel_id, character_id, care_level, is_active)
    return {"message": event["content"] if event is not None else None}
