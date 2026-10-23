# SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
# SPDX-License-Identifier: AGPL-3.0-or-later

"""agent_ops 测试共享辅助——DB 隔离 fixture + SSE 事件收集器。"""
import asyncio

import pytest


@pytest.fixture
def isolate_db(tmp_path, monkeypatch):
    """数据库隔离——tmp SQLite + 重置连接单例。

    与 tests/test_api_evolutions.py 的 isolate_db 同款风格。
    """
    db_path = str(tmp_path / "test_agent_ops.db")
    monkeypatch.setenv("SQLITE_PATH", db_path)

    import server.config as cfg
    monkeypatch.setattr(cfg.config, "SQLITE_PATH", db_path)

    import server.storage.sqlite_client as sc
    sc._conn = None
    asyncio.run(sc.init_db())

    yield

    if sc._conn:
        asyncio.run(sc._conn.close())
        sc._conn = None


@pytest.fixture
def client(isolate_db):
    from server.main import app
    from fastapi.testclient import TestClient
    return TestClient(app)


def get_sse():
    """获取 SSEManager 单例（与路由层 Depends(get_sse_manager) 同一实例）。"""
    from server.dependencies import get_sse_manager
    return get_sse_manager()


class SSECollector:
    """订阅 SSEManager 指定通道收集事件。

    SSEManager.broadcast 使用 put_nowait 同步入队，TestClient 请求返回即
    意味着该请求触发的全部事件已入队，故测试线程直接 get_nowait 泵取即可，
    无需跨事件循环 await。
    """

    def __init__(self, sse_manager, channel: str, maxsize: int = 1000):
        self.manager = sse_manager
        self.channel = channel
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=maxsize)
        self._subscribed = False

    def __enter__(self) -> "SSECollector":
        self.manager.subscribe(self.channel, self.queue)
        self._subscribed = True
        return self

    def __exit__(self, *exc) -> bool:
        if self._subscribed:
            self.manager.unsubscribe(self.channel, self.queue)
            self._subscribed = False
        return False

    def drain(self) -> list[dict]:
        """取空队列，返回已收集的事件列表（按广播顺序）。"""
        events = []
        while True:
            try:
                events.append(self.queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        return events

    def event_types(self) -> list[str]:
        """取空队列，仅返回事件类型序列（演化用 type 键，聊天用 event 键）。"""
        return [e.get("type", e.get("event")) for e in self.drain()]


def assert_events(collector: SSECollector, expected_types: list[str]):
    """断言收集器当前积压的事件类型序列恰为 expected_types（并取空队列）。"""
    actual = collector.event_types()
    assert actual == expected_types, f"SSE 事件序列不符: {actual} != {expected_types}"
