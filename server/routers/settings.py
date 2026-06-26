# SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
# SPDX-License-Identifier: AGPL-3.0-or-later

"""设置路由——关怀等级配置。"""
from fastapi import APIRouter, Query
from server.storage.sqlite_client import get_db
from server.models.schemas import (
    CareLevelResponse, CareLevelUpdateRequest, CareLevelUpdateResponse,
)

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("/care-level", response_model=CareLevelResponse)
async def get_care_level(
    user_id: str = Query(...),
    novel_id: str = Query(...),
    character_id: str = Query(...),
):
    db = await get_db()
    cursor = await db.execute(
        "SELECT level FROM care_settings WHERE user_id = ? AND novel_id = ? "
        "AND character_id = ?",
        (user_id, novel_id, character_id),
    )
    row = await cursor.fetchone()
    return CareLevelResponse(level=row["level"] if row else 80)


@router.post("/update-care-level", response_model=CareLevelUpdateResponse)
async def set_care_level(body: CareLevelUpdateRequest):
    db = await get_db()
    await db.execute(
        "INSERT OR REPLACE INTO care_settings (user_id, novel_id, character_id, level) "
        "VALUES (?, ?, ?, ?)",
        (body.user_id, body.novel_id, body.character_id, body.level),
    )
    await db.commit()
    return CareLevelUpdateResponse(status="updated", level=body.level)
