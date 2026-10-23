# SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
# SPDX-License-Identifier: AGPL-3.0-or-later

"""世界路由——CRUD + LLM 智能补全（补全经桥接分发至外部编排）。"""
import asyncio
import json
import logging
from fastapi import APIRouter, Query, HTTPException
from server.models.schemas import (
    CreateWorldRequest, CreateWorldResponse, UpdateWorldRequest,
    WorldListResponse, WorldItem,
    CompleteConfigRequest, CompleteConfigResponse,
)
from server.routers._dispatch import dispatch_or_503
from server.storage.sqlite_client import (
    list_worlds, create_world, get_world, get_world_characters, soft_delete_world,
    update_world,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/worlds", tags=["worlds"])


@router.get("/list", response_model=WorldListResponse)
async def get_worlds(user_id: str = Query(...)):
    rows = await list_worlds(user_id)
    worlds = []
    for r in rows:
        worlds.append(WorldItem(
            world_id=r["world_id"],
            name=r["name"],
            description=r["description"],
            rules=json.loads(r["rules"]),
            is_preset=bool(r["is_preset"]),
            character_count=r["character_count"],
            created_at=r["created_at"],
        ))
    return WorldListResponse(worlds=worlds)


@router.post("/create", response_model=CreateWorldResponse, status_code=201)
async def post_world(req: CreateWorldRequest):
    logger.info("创建世界 user=%s name=%s chars=%d", req.user_id, req.name, len(req.characters))
    try:
        wid = await create_world(
            user_id=req.user_id, name=req.name, description=req.description,
            world_history=req.world_history,
            rules=req.rules, initial_event=req.initial_event,
            characters=[c.model_dump() for c in req.characters],
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return CreateWorldResponse(world_id=wid)


@router.post("/update")
async def put_world(req: UpdateWorldRequest):
    logger.info("更新世界 world_id=%s user=%s name=%s", req.world_id, req.user_id, req.name)
    try:
        success = await update_world(
            world_id=req.world_id, user_id=req.user_id, name=req.name,
            description=req.description, world_history=req.world_history,
            rules=req.rules, initial_event=req.initial_event,
            characters=[c.model_dump() for c in req.characters],
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not success:
        raise HTTPException(404, "世界不存在或无权修改")
    return {"status": "updated", "world_id": req.world_id}


@router.post("/complete-config", response_model=CompleteConfigResponse)
async def complete_config(req: CompleteConfigRequest):
    """同步代理：等 bridge oneshot 补全结果，按原响应模型返回。"""
    logger.info("智能补全世界 name=%s", req.world_name)
    result = await dispatch_or_503(
        "worlds/complete-config",
        {
            "world_name": req.world_name,
            "world_description": req.world_description,
            "world_history": req.world_history,
            "rules": req.rules,
            "initial_event": req.initial_event,
            "characters": [c.model_dump() for c in req.characters],
            "character_count": min(10, max(3, len(req.characters))),
        },
        wait=True,
        timeout=300.0,
    )
    return CompleteConfigResponse(**result)


@router.get("/detail")
async def get_world_detail(world_id: str = Query(...)):
    world, chars = await asyncio.gather(
        get_world(world_id),
        get_world_characters(world_id),
    )
    if world is None:
        raise HTTPException(404, "世界不存在")
    return {
        "world_id": world["world_id"],
        "name": world["name"],
        "description": world["description"],
        "world_history": world.get("world_history", ""),
        "rules": json.loads(world["rules"]),
        "initial_event": json.loads(world["initial_event"]),
        "is_preset": bool(world["is_preset"]),
        "created_at": world["created_at"],
        "characters": chars,
    }


@router.post("/delete")
async def delete_world(world_id: str = Query(...), user_id: str = Query(...)):
    success = await soft_delete_world(world_id, user_id)
    if not success:
        raise HTTPException(404, "世界不存在或无权删除")
    return {"status": "deleted", "world_id": world_id}
