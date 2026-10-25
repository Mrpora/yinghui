# SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
# SPDX-License-Identifier: AGPL-3.0-or-later

"""小说路由——异步生成 + 任务轮询 + SSE 进展 + 列表/详情 + 角色导入。

生成与角色提取的 LLM 编排已外移至 yinghui-dsh-plug bridge：
/generate 预建 novel/task 行后 fire-and-forget 触发（失败任务可断点续写——
复用原 task_id/novel_id，W4b）；
/import-characters 同步代理 bridge oneshot 提取，落库仍在本路由。
"""
import asyncio
import json
import logging
import uuid
from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import StreamingResponse

from server.dependencies import get_sse_manager
from server.routers._dispatch import dispatch_or_503
from server.storage.sqlite_client import (
    now_ms,
    get_db, create_novel, create_novel_task, get_novel_task,
    list_novels, get_novel, get_latest_novel_task_status, soft_delete_novel,
    create_novel_character, list_novel_characters,
    get_processing_task_by_evolution,
)
from server.utils.font_obfuscate import obfuscate

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/novels", tags=["novels"])


# ── 启动生成 ──

@router.post("/generate")
async def start_novel_generation(
    user_id: str = Query(...),
    world_id: str = Query(...),
    evolution_id: str = Query(...),
):
    """预建 novel/task 行后触发桥接生成（fire-and-forget），立即返回 task_id。

    断点续写（W4b）：同演化最新 failed 任务且章节目录留存（ch_*.md 非空）→
    复用原 task_id/novel_id 并重置任务行续写（响应模型不变，前端零感知）；
    未命中 → 预建新行（现行为不变）。
    """
    from server.services.agent_ops_service import task_has_chapters
    from server.storage.sqlite_client import (
        get_world, get_world_characters,
        get_latest_failed_task_by_evolution,
        reset_novel_task_for_retry, restore_novel_task,
    )

    world, chars = await asyncio.gather(
        get_world(world_id),
        get_world_characters(world_id),
    )
    if world is None:
        raise HTTPException(404, "世界不存在")
    db = await get_db()
    cursor = await db.execute(
        "SELECT timeline FROM world_evolutions WHERE evolution_id = ? AND is_deleted = 0",
        (evolution_id,),
    )
    evo = await cursor.fetchone()

    world_config = {
        "name": world["name"],
        "description": world["description"],
        "world_history": world.get("world_history", ""),
        "rules": world.get("rules", "[]"),
    }

    # 断点续写判定：同演化最新 failed 任务 + 章节目录留存 → 复用；否则新建
    prev = await get_latest_failed_task_by_evolution(evolution_id)
    reused = prev is not None and task_has_chapters(prev["task_id"])
    if reused:
        task_id = prev["task_id"]
        novel_id = prev["novel_id"]
        logger.info("断点续写：命中可复用失败任务 task_id=%s novel_id=%s "
                    "evolution_id=%s（章节目录留存），重置任务行续写",
                    task_id, novel_id, evolution_id)
        await reset_novel_task_for_retry(task_id)
    else:
        if prev is not None:
            logger.info("断点续写未命中：失败任务 task_id=%s 章节目录不存在或为空，"
                        "预建新行从头生成", prev["task_id"])
        task_id = f"task_{uuid.uuid4().hex[:8]}"

        # 预创建 novel 记录与任务行（bridge 按 task_id 经 /api/agent/* 回写）
        novel_id = await create_novel(user_id, world_id, evolution_id, world["name"], "",
                                      world_config)
        await create_novel_task(task_id, novel_id, evolution_id)

    try:
        await dispatch_or_503("novels/generate", {
            "task_id": task_id,
            "novel_id": novel_id,
            "user_id": user_id,
            "world_id": world_id,
            "evolution_id": evolution_id,
        })
    except Exception:
        # 触发失败（含 bridge 非 2xx / 非法 JSON 被包装为 BridgeUnavailable → 503）：
        # 新建路径回收预建的行；复用路径恢复失败任务行原值（不删行，
        # 章节 文件仍留存可再次重试续写），均保持「不可达 = 什么都没发生」
        if reused:
            await restore_novel_task(
                task_id, prev["status"], prev["result"], prev["error"],
                prev["completed_at"])
        else:
            await db.execute("DELETE FROM novel_tasks WHERE task_id = ?", (task_id,))
            await db.execute("DELETE FROM novels WHERE novel_id = ?", (novel_id,))
            await db.commit()
        raise

    logger.info("小说生成任务已触发 task_id=%s world_id=%s reuse=%s",
                task_id, world_id, reused)
    return {"task_id": task_id, "novel_id": novel_id, "status": "processing"}


# ── 任务状态轮询 ──

@router.get("/task-status")
async def get_task_status(task_id: str = Query(...)):
    row = await get_novel_task(task_id)
    if row is None:
        raise HTTPException(404, "任务不存在")
    return {
        "task_id": task_id,
        "status": row["status"],
        "result": json.loads(row["result"]) if row["result"] else None,
        "error": row.get("error"),
        "created_at": row["created_at"],
        "completed_at": row.get("completed_at"),
    }


# ── 检查演化记录是否有进行中的任务 ──

@router.get("/check-task")
async def check_novel_task(evolution_id: str = Query(...)):
    """检查某个演化记录是否有正在处理中的小说生成任务。"""
    task = await get_processing_task_by_evolution(evolution_id)
    return {"has_task": task is not None, "task": task}


# ── SSE 生成进展 ──

@router.get("/events")
async def stream_novel_events(
    task_id: str = Query(...),
    sse=Depends(get_sse_manager),
):
    channel = f"novel:{task_id}"
    queue: asyncio.Queue = asyncio.Queue(maxsize=100)
    sse.subscribe(channel, queue)

    logger.info("SSE 小说事件连接建立 task=%s", task_id)

    async def generator():
        try:
            while True:
                event = await queue.get()
                payload = {"type": event["type"], **event.get("data", {})}
                data = json.dumps(payload, ensure_ascii=False)
                yield f"data: {data}\n\n"
        except asyncio.CancelledError:
            logger.info("SSE 小说事件断开 task=%s", task_id)
        finally:
            sse.unsubscribe(channel, queue)

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── 列表 ──

@router.get("/list")
async def get_novels(user_id: str = Query(...)):
    rows = await list_novels(user_id)
    return {"novels": rows}


# ── 详情 ──

@router.get("/detail")
async def get_novel_detail(novel_id: str = Query(...)):
    novel = await get_novel(novel_id)
    if novel is None:
        raise HTTPException(404, "小说不存在")
    chars, task_status = await asyncio.gather(
        list_novel_characters(novel_id),
        get_latest_novel_task_status(novel_id),
    )
    return {
        "novel_id": novel["novel_id"],
        "title": novel["title"],
        "content": obfuscate(novel["content"] or ""),
        "world_snapshot": json.loads(novel["world_snapshot"]) if novel["world_snapshot"] else {},
        "created_at": novel["created_at"],
        "characters": chars,
        "task_status": task_status,
    }


# ── 删除 ──

@router.post("/delete")
async def delete_novel(
    novel_id: str = Query(...),
    user_id: str = Query(...),
):
    success = await soft_delete_novel(novel_id, user_id)
    if not success:
        raise HTTPException(404, "小说不存在或无权删除")
    return {"status": "deleted", "novel_id": novel_id}


# ── 导入角色到对话系统 ──

@router.post("/import-characters")
async def import_characters(
    novel_id: str = Query(...),
    user_id: str = Query(...),
):
    """从生成的小说中提取角色剧情并导入 novel_characters 表，供对话系统使用。

    同步代理：等 bridge oneshot 提取角色剧情（600s），落库仍在本路由完成。
    """
    novel = await get_novel(novel_id)
    if novel is None:
        raise HTTPException(404, "小说不存在")
    if not novel.get("content"):
        raise HTTPException(400, "小说内容为空，无法导入角色")

    # 检查是否已导入
    db = await get_db()
    cursor = await db.execute(
        "SELECT COUNT(*) as cnt FROM novel_characters WHERE novel_id = ? AND is_deleted = 0",
        (novel_id,),
    )
    row = await cursor.fetchone()
    if row and row["cnt"] > 0:
        raise HTTPException(400, "该小说的角色已导入，不可重复导入")

    world_snapshot = json.loads(novel["world_snapshot"]) if novel["world_snapshot"] else {}
    source_chars = world_snapshot.get("characters", [])

    cursor = await db.execute(
        "SELECT * FROM world_characters WHERE world_id = ?", (novel["world_id"],),
    )
    world_chars = await cursor.fetchall()

    char_dicts = [dict(c) for c in world_chars] if world_chars else source_chars

    # 同步代理：bridge oneshot 提取各角色剧情（角色名 → 剧情段落）
    plots = await dispatch_or_503(
        "novels/import-characters",
        {
            "novel_id": novel_id,
            "user_id": user_id,
            "characters": char_dicts,
        },
        wait=True,
        timeout=600.0,
    )

    async def _import_one(wc):
        char_name = wc["name"]
        story_ctx = (plots or {}).get(char_name, "")
        char_id = await create_novel_character(
            novel_id=novel_id,
            user_id=user_id,
            source_character_id=wc["character_id"],
            character_snapshot=dict(wc),
            story_context=story_ctx,
            accent_color=wc["accent_color"] or "",
        )
        return {"character_id": char_id, "name": char_name}

    imported = await asyncio.gather(*[_import_one(wc) for wc in world_chars])

    logger.info("导入角色完成 novel=%s count=%d", novel_id, len(imported))
    return {"status": "imported", "novel_id": novel_id, "characters": imported}
