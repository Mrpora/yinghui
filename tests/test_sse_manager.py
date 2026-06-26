# SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
# SPDX-License-Identifier: AGPL-3.0-or-later

"""SSE 发布-订阅管理器测试。"""
import asyncio
import pytest
from server.sse.sse_manager import SSEManager


class TestSubscribe:
    def test_subscribe_adds_queue(self):
        mgr = SSEManager()
        queue: asyncio.Queue = asyncio.Queue()
        mgr.subscribe("test", queue)
        assert mgr.subscriber_count("test") == 1

    def test_subscribe_multiple_queues(self):
        mgr = SSEManager()
        q1: asyncio.Queue = asyncio.Queue()
        q2: asyncio.Queue = asyncio.Queue()
        mgr.subscribe("ch", q1)
        mgr.subscribe("ch", q2)
        assert mgr.subscriber_count("ch") == 2


class TestUnsubscribe:
    def test_unsubscribe_removes_queue(self):
        mgr = SSEManager()
        q: asyncio.Queue = asyncio.Queue()
        mgr.subscribe("ch", q)
        mgr.unsubscribe("ch", q)
        assert mgr.subscriber_count("ch") == 0

    def test_unsubscribe_nonexistent_channel_is_safe(self):
        mgr = SSEManager()
        q: asyncio.Queue = asyncio.Queue()
        mgr.unsubscribe("no-such-channel", q)  # 不抛异常

    def test_unsubscribe_nonexistent_queue_is_safe(self):
        mgr = SSEManager()
        q1: asyncio.Queue = asyncio.Queue()
        q2: asyncio.Queue = asyncio.Queue()
        mgr.subscribe("ch", q1)
        mgr.unsubscribe("ch", q2)  # q2 不在列表中
        assert mgr.subscriber_count("ch") == 1

    def test_channel_cleaned_up_when_empty(self):
        mgr = SSEManager()
        q: asyncio.Queue = asyncio.Queue()
        mgr.subscribe("ch", q)
        mgr.unsubscribe("ch", q)
        assert "ch" not in mgr._subscribers


class TestBroadcast:
    @pytest.mark.asyncio
    async def test_broadcast_delivers_to_subscribers(self):
        mgr = SSEManager()
        q1: asyncio.Queue = asyncio.Queue(maxsize=10)
        q2: asyncio.Queue = asyncio.Queue(maxsize=10)
        mgr.subscribe("ch", q1)
        mgr.subscribe("ch", q2)

        event = {"type": "test", "data": {"msg": "hello"}}
        await mgr.broadcast("ch", event)

        assert await q1.get() == event
        assert await q2.get() == event

    @pytest.mark.asyncio
    async def test_broadcast_skips_empty_channel(self):
        mgr = SSEManager()
        await mgr.broadcast("no-subscribers", {"type": "nobody"})  # 不抛异常

    @pytest.mark.asyncio
    async def test_broadcast_drops_full_queue(self):
        mgr = SSEManager()
        q: asyncio.Queue = asyncio.Queue(maxsize=1)
        mgr.subscribe("ch", q)
        q.put_nowait("prefill")  # 填满队列

        await mgr.broadcast("ch", {"type": "overflow"})
        # 满队列被移除
        assert mgr.subscriber_count("ch") == 0

    @pytest.mark.asyncio
    async def test_broadcast_keeps_other_queues_on_one_full(self):
        mgr = SSEManager()
        q_full: asyncio.Queue = asyncio.Queue(maxsize=1)
        q_ok: asyncio.Queue = asyncio.Queue(maxsize=10)
        mgr.subscribe("ch", q_full)
        mgr.subscribe("ch", q_ok)
        q_full.put_nowait("prefill")

        event = {"type": "test"}
        await mgr.broadcast("ch", event)

        # q_full 被移除，q_ok 仍收到事件
        assert await q_ok.get() == event
        assert mgr.subscriber_count("ch") == 1


class TestSubscriberCount:
    def test_returns_zero_for_unknown_channel(self):
        mgr = SSEManager()
        assert mgr.subscriber_count("unknown") == 0

    def test_returns_correct_count(self):
        mgr = SSEManager()
        mgr.subscribe("ch", asyncio.Queue())
        mgr.subscribe("ch", asyncio.Queue())
        assert mgr.subscriber_count("ch") == 2
