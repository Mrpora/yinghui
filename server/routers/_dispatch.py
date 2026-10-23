# SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
# SPDX-License-Identifier: AGPL-3.0-or-later

"""路由层桥接分发辅助——统一把 BridgeUnavailable 转 503（中文 detail 语义冻结）。"""
import logging

from fastapi import HTTPException

from server.services import bridge_dispatcher
from server.services.bridge_dispatcher import BridgeUnavailable

logger = logging.getLogger(__name__)

# 契约冻结的错误 detail（前端据文案提示启动桥接）
BRIDGE_UNAVAILABLE_DETAIL = "桥接服务未启动：请先运行 yinghui-dsh-plug bridge（默认 127.0.0.1:8100）"


async def dispatch_or_503(
    agent: str,
    payload: dict,
    *,
    wait: bool = False,
    timeout: float | None = None,
) -> dict:
    """调 bridge_dispatcher.dispatch，不可达 → HTTPException(503, 中文 detail)。"""
    try:
        return await bridge_dispatcher.dispatch(agent, payload, wait=wait, timeout=timeout)
    except BridgeUnavailable:
        raise HTTPException(503, BRIDGE_UNAVAILABLE_DETAIL)
