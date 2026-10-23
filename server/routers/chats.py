# SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
# SPDX-License-Identifier: AGPL-3.0-or-later

"""对话路由——角色列表 + SSE 流式对话（桥接持流代理）+ 历史消息 + 删除。"""
import asyncio
import json
import logging

from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import StreamingResponse

from server.dependencies import get_sse_manager
from server.routers._dispatch import dispatch_or_503
from server.storage.sqlite_client import (
    now_ms,
    get_db, create_chat, get_chat, list_chats as db_list_chats, get_chat_messages,
    soft_delete_chat, list_novel_characters as db_list_novel_characters,
    get_latest_chat_novel,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/chats", tags=["chats"])


# ── 角色列表 ──

@router.get("/characters")
async def get_characters(
    user_id: str = Query(...),
    novel_id: str = Query(...),
):
    """获取可对话的角色列表（已导入到 novel_characters 的角色）。"""
    chars = await db_list_novel_characters(novel_id)
    return {
        "characters": [
            {
                "id": c["character_id"],
                "name": json.loads(c["character_snapshot"]).get("name", "") if c.get("character_snapshot") else "",
                "identity": json.loads(c["character_snapshot"]).get("identity", "") if c.get("character_snapshot") else "",
                "personality_traits": json.loads(c["character_snapshot"]).get("personality", "").split("，") if c.get("character_snapshot") else [],
                "speaking_style": json.loads(c["character_snapshot"]).get("speech_style", "") if c.get("character_snapshot") else "",
                "accent_color": c.get("accent_color", ""),
                "relationships": json.loads(c["character_snapshot"]).get("attitudes", {}) if c.get("character_snapshot") else {},
                "story_context": c.get("story_context", ""),
            }
            for c in chars
        ]
    }


# ── 开始/继续对话 (SSE) ──

@router.post("/start")
async def start_chat(
    user_id: str = Query(...),
    novel_id: str = Query(...),
    character_id: str = Query(...),
    chat_id: str | None = Query(None),
    content: str | None = Query(None),
    sse=Depends(get_sse_manager),
    db=Depends(get_db),
):
    """SSE 流式对话——持流代理：建/取 chat 行后触发桥接，从 chat:{cid} 通道
    逐事件转发直至 done|error（词汇 session_created|thinking|retrieving|
    memorizing|token|done|error 契约不变）。"""
    # 1. 建/取 chat 行
    is_new = chat_id is None
    if is_new:
        chat_id = await create_chat(user_id, novel_id, character_id)
        logger.info("新建对话 chat=%s user=%s char=%s", chat_id, user_id, character_id)
    else:
        existing = await get_chat(chat_id)
        if existing is None:
            raise HTTPException(404, "对话不存在")

    # 2. 用户消息先落库（行为改进：flow 失败重载后消息保留可重发）
    if content:
        cursor = await db.execute(
            "SELECT messages FROM character_chats WHERE chat_id = ?", (chat_id,))
        row = await cursor.fetchone()
        messages = json.loads(row["messages"] or "[]") if row else []
        round_num = sum(1 for m in messages if m.get("role") == "character") + 1
        messages.append({
            "role": "user", "content": content,
            "timestamp": now_ms(), "round": round_num,
        })
        await db.execute(
            "UPDATE character_chats SET messages = ?, modified_at = ? WHERE chat_id = ?",
            (json.dumps(messages, ensure_ascii=False), now_ms(), chat_id),
        )
        await db.commit()

    # 3. 订阅先于触发（bridge 早期阶段事件不丢）；bridge 不可达在开流前 503
    queue: asyncio.Queue = asyncio.Queue(maxsize=100)
    channel = f"chat:{chat_id}"
    sse.subscribe(channel, queue)
    try:
        await dispatch_or_503("chats/start", {
            "chat_id": chat_id,
            "user_id": user_id,
            "novel_id": novel_id,
            "character_id": character_id,
            "content": content,
        })
    except Exception:
        sse.unsubscribe(channel, queue)
        raise

    async def event_stream():
        try:
            if is_new:
                yield f"event: session_created\ndata: {{\"chat_id\": \"{chat_id}\"}}\n\n"
            while True:
                event = await queue.get()
                event_type = event.get("event", "message")
                data = json.dumps(event.get("data", event), ensure_ascii=False)
                yield f"event: {event_type}\ndata: {data}\n\n"
                if event_type in ("done", "error"):
                    break
        except asyncio.CancelledError:
            # 前端 abort 断开 SSE 后 flow 继续跑完并落库（bridge 侧治理）
            logger.info("对话 SSE 断开（flow 继续至落库）chat=%s", chat_id)
        finally:
            sse.unsubscribe(channel, queue)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ── 历史对话列表 ──

@router.get("/list")
async def list_chats(
    user_id: str = Query(...),
    novel_id: str | None = Query(None),
    character_id: str | None = Query(None),
):
    """列出用户的历史对话（仅元数据，不含消息内容）。按修改时间倒序。"""
    rows = await db_list_chats(user_id, novel_id, character_id)
    return {
        "chats": [
            {
                "chat_id": c["chat_id"],
                "character_id": c["character_id"],
                "character_name": c.get("character_name", ""),
                "accent_color": c.get("accent_color", ""),
                "created_at": c["created_at"],
                "modified_at": c["modified_at"],
            }
            for c in rows
        ]
    }


# ── 历史消息 ──

@router.get("/messages")
async def get_messages(chat_id: str = Query(...)):
    chat = await get_chat(chat_id)
    if chat is None:
        raise HTTPException(404, "对话不存在")
    messages = await get_chat_messages(chat_id)
    return {"chat_id": chat_id, "messages": messages}


# ── 删除对话 ──

@router.post("/delete")
async def delete_chat(
    chat_id: str = Query(...),
    user_id: str = Query(...),
):
    success = await soft_delete_chat(chat_id, user_id)
    if not success:
        raise HTTPException(404, "对话不存在或无权删除")
    return {"status": "deleted", "chat_id": chat_id}


# ── 移除角色 ──

@router.post("/remove-characters")
async def remove_characters(
    novel_id: str = Query(...),
    user_id: str = Query(...),
    character_id: str = Query(...),
):
    """从对话系统中移除已导入的角色。"""
    from server.storage.sqlite_client import soft_delete_novel_character
    success = await soft_delete_novel_character(character_id)
    if not success:
        raise HTTPException(404, "角色不存在")
    return {"status": "removed", "character_id": character_id}


@router.get("/latest-novel")
async def latest_novel(user_id: str = Query(...)):
    """获取用户最近互动的对话对应的 novel_id。"""
    novel_id = await get_latest_chat_novel(user_id)
    return {"novel_id": novel_id}
