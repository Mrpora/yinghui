# SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
# SPDX-License-Identifier: AGPL-3.0-or-later

"""FastAPI 入口——萦回 Demo 统一后端。"""
import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from server.logging_config import setup_logging
from server.storage.sqlite_client import init_db
from server.prompt_loader import preload_all
from server.routers import auth, worlds, evolutions, novels, chats, memories, settings

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
    logger.info("萦回 Demo 服务关闭")


app = FastAPI(title="萦回 Demo API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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


if __name__ == "__main__":
    uvicorn.run("server.main:app", host="127.0.0.1", port=8000, reload=True)
