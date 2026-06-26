# SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
# SPDX-License-Identifier: AGPL-3.0-or-later

"""认证路由——POST /api/auth/login。"""
import logging
from fastapi import APIRouter, HTTPException
from server.models.schemas import LoginRequest, LoginResponse
from server.storage.sqlite_client import upsert_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])

_FORBIDDEN_NICKNAMES = {"system"}


@router.post("/login", response_model=LoginResponse)
async def login(req: LoginRequest):
    if req.nickname.strip().lower() in _FORBIDDEN_NICKNAMES:
        raise HTTPException(400, "该昵称不可使用")
    user = await upsert_user(req.nickname)
    logger.info("用户登录 user=%s nickname=%s", user["user_id"], user["nickname"])
    return LoginResponse(
        user_id=user["user_id"],
        nickname=user["nickname"],
        created_at=user["created_at"],
    )
