# SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
# SPDX-License-Identifier: AGPL-3.0-or-later

"""小说路由——异步生成 + 任务轮询 + SSE 进展 + 列表/详情 + 角色导入。"""
import asyncio
import json
import logging
import uuid
from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import StreamingResponse

from server.dependencies import get_novel_agent, get_sse_manager
from server.storage.sqlite_client import (
    now_ms,
    get_db, create_novel, create_novel_task, update_novel_task, get_novel_task,
    list_novels, get_novel, get_latest_novel_task_status, soft_delete_novel,
    create_novel_character, list_novel_characters,
    get_processing_task_by_evolution,
)
from server.utils.font_obfuscate import obfuscate

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/novels", tags=["novels"])


async def _run_generation(
    task_id: str, novel_id: str, agent, world_config: dict,
    characters: list[dict], initial_event: dict, timeline_events: list[dict],
    sse_manager, user_id: str, world_id: str, evolution_id: str,
):
    """后台异步执行小说生成。"""
    try:
        result = await agent.generate(
            task_id=task_id,
            world_config=world_config,
            characters=characters,
            initial_event=initial_event,
            timeline_events=timeline_events,
            sse_manager=sse_manager,
        )
        content = result.get("content", "")
        if not content:
            out_path = result.get("output_path")
            if out_path:
                try:
                    content = __import__("pathlib").Path(out_path).read_text(encoding="utf-8")
                except Exception as e:
                    logger.warning("读取小说输出文件失败 path=%s: %s", out_path, e)
        title = result.get("title", world_config.get("name", "未命名"))
        title = f"{title}（小说）"

        db = await get_db()
        await db.execute(
            "UPDATE novels SET title = ?, content = ? WHERE novel_id = ?",
            (title, content, novel_id),
        )
        await db.commit()
        await update_novel_task(task_id, "completed", json.dumps(result, ensure_ascii=False))
        logger.info("小说生成完成 task_id=%s novel_id=%s", task_id, novel_id)
    except Exception as e:
        logger.error("小说生成失败 task_id=%s: %s", task_id, e)
        await update_novel_task(task_id, "failed", error=str(e))


# ── 启动生成 ──

@router.post("/generate")
async def start_novel_generation(
    user_id: str = Query(...),
    world_id: str = Query(...),
    evolution_id: str = Query(...),
    agent=Depends(get_novel_agent),
    sse=Depends(get_sse_manager),
):
    """启动小说生成任务（异步），立即返回 task_id。"""
    from server.storage.sqlite_client import get_world, get_world_characters

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

    task_id = f"task_{uuid.uuid4().hex[:8]}"
    now = now_ms()

    world_config = {
        "name": world["name"],
        "description": world["description"],
        "world_history": world.get("world_history", ""),
        "rules": world.get("rules", "[]"),
    }

    timeline_events = json.loads(evo["timeline"]) if evo else []
    initial_event = json.loads(world["initial_event"]) if isinstance(world["initial_event"], str) else world["initial_event"]

    # 预创建 novel 记录
    novel_id = await create_novel(user_id, world_id, evolution_id, world["name"], "", world_config)
    await create_novel_task(task_id, novel_id, evolution_id)

    task = asyncio.create_task(
        _run_generation(
            task_id=task_id, novel_id=novel_id, agent=agent,
            world_config=world_config,
            characters=[dict(c) for c in chars],
            initial_event=initial_event,
            timeline_events=timeline_events,
            sse_manager=sse,
            user_id=user_id, world_id=world_id, evolution_id=evolution_id,
        )
    )
    task.add_done_callback(
        lambda t: logger.error("小说后台任务崩溃 task_id=%s: %s", task_id, t.exception())
        if t.exception() else None
    )

    logger.info("小说生成任务已启动 task_id=%s world_id=%s", task_id, world_id)
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
    """从生成的小说中提取角色剧情并导入 novel_characters 表，供对话系统使用。"""
    from server.ai.extract_llm.extract import extract_character_plots

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

    # 提取剧情
    char_dicts = [dict(c) for c in world_chars] if world_chars else source_chars
    plots = await extract_character_plots(novel["content"], char_dicts)

    async def _import_one(wc):
        char_name = wc["name"]
        story_ctx = plots.get(char_name, "")
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
