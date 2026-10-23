# SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
# SPDX-License-Identifier: AGPL-3.0-or-later

"""chats/start 持流代理测试——桥接触发 + chat:{cid} 通道逐事件转发（dispatch 一律 stub）。

对端语义：事件由 bridge/MCP 经 /api/agent/chats/{cid}/stage|done 写入
SSEManager 通道；本组测试用 stub dispatch 在触发时直接向通道广播同等
形状的事件，验证路由的转发/终止/session_created 契约。
"""
import asyncio
import json

import pytest

from tests.helpers import make_characters
from tests.test_api_chats import _setup_chat_prereqs


@pytest.fixture(autouse=True)
def isolate_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test_chat_start.db")
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


def _sse_lines(text: str) -> list[tuple[str, dict]]:
    """解析 SSE 响应体为 (event, data) 序列。"""
    events = []
    for block in text.split("\n\n"):
        if not block.strip():
            continue
        event_type, data = None, None
        for line in block.split("\n"):
            if line.startswith("event: "):
                event_type = line[len("event: "):]
            elif line.startswith("data: "):
                data = json.loads(line[len("data: "):])
        events.append((event_type, data))
    return events


def _stub_flow(monkeypatch, events):
    """stub dispatch：触发时向 chat:{cid} 通道广播给定事件序列（对端语义）。"""
    import server.services.bridge_dispatcher as bd
    from server.dependencies import get_sse_manager

    calls = []

    async def fake_dispatch(agent, payload, *, wait=False, timeout=None):
        calls.append({"agent": agent, "payload": payload})
        if agent == "chats/start":
            sse = get_sse_manager()
            for event in events:
                await sse.broadcast(f"chat:{payload['chat_id']}", event)
        return {}

    monkeypatch.setattr(bd, "dispatch", fake_dispatch)
    return calls


_DONE_EVENT = {
    "event": "done",
    "data": {"chat_id": "c", "user_id": "u", "novel_id": "n",
             "character_id": "ch", "message": {}},
}


class TestChatStartStreamingProxy:
    def test_new_chat_full_sequence(self, client, monkeypatch):
        """新建对话：session_created 前置 + 通道事件按序转发直至 done 终止。"""
        uid = "cs_user1"
        novel_id, char_id = _setup_chat_prereqs(client, uid)
        calls = _stub_flow(monkeypatch, [
            {"event": "thinking", "data": {}},
            {"event": "token", "data": {"content": "你好"}},
            {"event": "token", "data": {"content": "呀"}},
            _DONE_EVENT,
        ])

        res = client.post(
            f"/api/chats/start?user_id={uid}&novel_id={novel_id}&character_id={char_id}")
        assert res.status_code == 200
        assert res.headers["content-type"].startswith("text/event-stream")

        events = _sse_lines(res.text)
        assert [e for e, _ in events] == [
            "session_created", "thinking", "token", "token", "done"]

        # session_created 仅新建时发，data 为新 chat_id
        assert events[0][1]["chat_id"]
        # 触发载荷透传
        assert calls[0]["agent"] == "chats/start"
        assert calls[0]["payload"]["novel_id"] == novel_id
        assert calls[0]["payload"]["character_id"] == char_id
        assert calls[0]["payload"]["content"] is None

    def test_existing_chat_persists_user_message_no_session_created(self, client, monkeypatch):
        """续聊：无 session_created；用户消息在触发前先落库。"""
        uid = "cs_user2"
        novel_id, char_id = _setup_chat_prereqs(client, uid)

        from server.storage.sqlite_client import create_chat
        chat_id = asyncio.run(create_chat(uid, novel_id, char_id))

        calls = _stub_flow(monkeypatch, [
            {"event": "token", "data": {"content": "记得你"}},
            _DONE_EVENT,
        ])

        res = client.post(
            f"/api/chats/start?user_id={uid}&novel_id={novel_id}&character_id={char_id}"
            f"&chat_id={chat_id}&content=上次聊到哪了")
        assert res.status_code == 200

        events = _sse_lines(res.text)
        assert [e for e, _ in events] == ["token", "done"]

        assert calls[0]["payload"]["chat_id"] == chat_id
        assert calls[0]["payload"]["content"] == "上次聊到哪了"

        # 用户消息已落库（flow 失败重载后可重发）
        msgs = client.get(f"/api/chats/messages?chat_id={chat_id}").json()["messages"]
        users = [m for m in msgs if m["role"] == "user"]
        assert len(users) == 1
        assert users[0]["content"] == "上次聊到哪了"
        assert users[0]["round"] == 1

    def test_bridge_unavailable_503_before_stream(self, client, monkeypatch):
        """bridge 不可达 → 开流前 503（前端 onError 兼容 HTTP 状态）。"""
        import server.services.bridge_dispatcher as bd

        async def unavailable(agent, payload, *, wait=False, timeout=None):
            raise bd.BridgeUnavailable("桥接服务未启动")

        monkeypatch.setattr(bd, "dispatch", unavailable)

        uid = "cs_user3"
        novel_id, char_id = _setup_chat_prereqs(client, uid)

        res = client.post(
            f"/api/chats/start?user_id={uid}&novel_id={novel_id}&character_id={char_id}")
        assert res.status_code == 503
        assert "yinghui-dsh-plug bridge" in res.json()["detail"]

    def test_nonexistent_chat_404(self, client, monkeypatch):
        _setup_chat_prereqs(client, "cs_user4")
        res = client.post(
            f"/api/chats/start?user_id=cs_user4&novel_id=n&character_id=c"
            f"&chat_id=no_such_chat")
        assert res.status_code == 404
