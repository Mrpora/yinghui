# SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
# SPDX-License-Identifier: AGPL-3.0-or-later

"""记忆路由——记忆 CRUD。"""
import logging
from fastapi import APIRouter, Query, Body
from server.models.schemas import (
    MemoryListResponse, MemoryItemResponse, DeleteMemoryResponse,
    SetExpiryRequest, SetExpiryResponse, ClearMemoriesResponse,
)
from server.services.memory_service import (
    get_memories, delete_memory, clear_all_memories, update_expiry,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/memories", tags=["memories"])


@router.get("/list", response_model=MemoryListResponse)
async def list_memories(
    user_id: str = Query(...),
    novel_id: str = Query(...),
    character_id: str | None = Query(None),
):
    memories = await get_memories(user_id, novel_id, character_id)
    return MemoryListResponse(
        memories=[
            MemoryItemResponse(
                id=m["memory_id"], character_name=m["character_name"],
                memory_type=m["memory_type"], content=m["content"],
                created_at=m["created_at"], expires_at=m["expires_at"],
                recall_count=m["recall_count"],
            )
            for m in memories
        ]
    )


@router.post("/delete", response_model=DeleteMemoryResponse)
async def remove_memory(memory_id: str = Query(...)):
    result = await delete_memory(memory_id)
    return DeleteMemoryResponse(status=result["status"], memory_id=result["memory_id"])


@router.post("/update-expiry", response_model=SetExpiryResponse)
async def set_memory_expiry(
    memory_id: str = Query(...),
    body: SetExpiryRequest = Body(...),
):
    result = await update_expiry(memory_id, body.expires_at)
    return SetExpiryResponse(
        status=result["status"], memory_id=result["memory_id"],
        expires_at=result["expires_at"],
    )


@router.post("/clear", response_model=ClearMemoriesResponse)
async def clear_memories(
    user_id: str = Query(...),
    novel_id: str = Query(...),
    character_id: str = Query(...),
):
    result = await clear_all_memories(user_id, novel_id, character_id)
    return ClearMemoriesResponse(status=result["status"], deleted_count=result["deleted_count"])
