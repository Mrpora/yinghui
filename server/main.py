# SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
# SPDX-License-Identifier: AGPL-3.0-or-later

"""FastAPI 入口——萦回 Demo 统一后端。"""
import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from server.config import config
from server.logging_config import setup_logging
from server.storage.sqlite_client import init_db
from server.prompt_loader import preload_all
from server.routers import auth, worlds, evolutions, novels, chats, memories, settings
from server.routers import agent_ops

setup_logging(logging.DEBUG)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("萦回 Demo 服务启动")
    await init_db()
    preload_all()
    from server.services.memory_service import init_jieba
    init_jieba()
    logger.info("数据库初始化 + 预加载完成")
    yield
    from server.services.bridge_dispatcher import aclose as close_bridge_client
    await close_bridge_client()
    logger.info("萦回 Demo 服务关闭")


app = FastAPI(title="萦回 Demo API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    # CORS_ORIGINS 未配置（默认空）时回落 "*"：维持本地开发与 docker nginx
    # 同源代理的现状兼容；公网/跨域部署应显式设置以收窄来源（debt-wave4a F2）
    allow_origins=config.CORS_ORIGINS or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(worlds.router)
app.include_router(evolutions.router)
app.include_router(novels.router)
app.include_router(chats.router)
app.include_router(memories.router)
app.include_router(settings.router)
app.include_router(agent_ops.router)


if __name__ == "__main__":
    uvicorn.run("server.main:app", host="127.0.0.1", port=8000, reload=True)
