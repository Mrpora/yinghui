# SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
# SPDX-License-Identifier: AGPL-3.0-or-later

"""SSE 发布-订阅管理器——演化 + 小说 + 对话共用。"""
import asyncio
import logging

logger = logging.getLogger(__name__)


class SSEManager:
    """基于 asyncio.Queue 的发布-订阅，按 channel 隔离。"""

    def __init__(self):
        self._subscribers: dict[str, list[asyncio.Queue]] = {}

    def subscribe(self, channel: str, queue: asyncio.Queue):
        """订阅指定 channel。"""
        if channel not in self._subscribers:
            self._subscribers[channel] = []
        self._subscribers[channel].append(queue)
        count = len(self._subscribers[channel])
        logger.info("📡 SSE 订阅 channel=%s subscribers=%d", channel, count)

    def unsubscribe(self, channel: str, queue: asyncio.Queue):
        """取消订阅。"""
        if channel in self._subscribers:
            try:
                self._subscribers[channel].remove(queue)
            except ValueError:
                pass
            if self._subscribers[channel]:
                count = len(self._subscribers[channel])
                logger.debug("📡 SSE 退订 channel=%s remaining=%d", channel, count)
            else:
                del self._subscribers[channel]
                logger.info("📡 SSE 全部退订 channel=%s", channel)

    async def broadcast(self, channel: str, event: dict):
        """向 channel 所有订阅者推送事件。"""
        if channel not in self._subscribers:
            return
        dead = []
        for queue in self._subscribers[channel]:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                dead.append(queue)
                logger.warning("SSE 队列已满 channel=%s event_type=%s",
                             channel, event.get("type"))
        for q in dead:
            self.unsubscribe(channel, q)

    def subscriber_count(self, channel: str) -> int:
        """获取 channel 当前订阅数。"""
        return len(self._subscribers.get(channel, []))
