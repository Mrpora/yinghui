# SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
# SPDX-License-Identifier: AGPL-3.0-or-later

"""对话 API 端点测试——列表/消息/删除/角色移除。"""
import json
import pytest

from tests.helpers import make_characters


@pytest.fixture(autouse=True)
def isolate_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("SQLITE_PATH", db_path)

    import server.config as cfg
    monkeypatch.setattr(cfg.config, "SQLITE_PATH", db_path)

    import server.storage.sqlite_client as sc
    sc._conn = None
    import asyncio
    asyncio.run(sc.init_db())

    yield

    if sc._conn:
        import asyncio
        asyncio.run(sc._conn.close())
        sc._conn = None


@pytest.fixture
def client(isolate_db):
    from server.main import app
    from fastapi.testclient import TestClient
    return TestClient(app)


def _setup_chat_prereqs(client, user_id):
    """创建世界→演化→小说→导入角色，返回 (novel_id, character_id)。"""
    import asyncio
    from server.storage.sqlite_client import get_db, now_ms, upsert_user
    from uuid import uuid4

    res = client.post("/api/auth/login", json={"nickname": user_id})

    wid_res = client.post("/api/worlds/create", json={
        "user_id": user_id, "name": "对话测试世界", "description": "",
        "world_history": "", "rules": [],
        "initial_event": {"content": "", "time": ""},
        "characters": make_characters(3),
    })
    wid = wid_res.json()["world_id"]

    async def _setup():
        db = await get_db()
        # 查询 API 创建世界时生成的真实角色 ID，满足 novel_characters FK 约束
        cursor = await db.execute(
            "SELECT character_id FROM world_characters WHERE world_id = ?", (wid,))
        row = await cursor.fetchone()
        source_cid = row["character_id"]

        eid = f"sess_{uuid4().hex[:8]}"
        nid = f"novel_{uuid4().hex[:8]}"
        now = now_ms()
        await db.execute(
            "INSERT INTO world_evolutions (evolution_id, user_id, world_id, status, "
            "current_round, created_at) VALUES (?, ?, ?, 'idle', 0, ?)",
            (eid, user_id, wid, now),
        )
        await db.execute(
            "INSERT INTO novels (novel_id, user_id, world_id, evolution_id, title, "
            "content, world_snapshot, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (nid, user_id, wid, eid, "测试小说", "内容",
             json.dumps({}), now),
        )
        await db.execute(
            "INSERT INTO novel_characters (character_id, novel_id, user_id, "
            "source_character_id, character_snapshot, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("nc_test_char", nid, user_id, source_cid,
             json.dumps({"name": "角色1", "identity": "测试身份"}), now),
        )
        await db.commit()
        return nid, "nc_test_char"

    return asyncio.run(_setup())


class TestChatList:
    def test_empty_chat_list(self, client):
        uid = "chat_user"
        novel_id, char_id = _setup_chat_prereqs(client, uid)

        res = client.get(f"/api/chats/list?user_id={uid}")
        assert res.status_code == 200
        assert res.json()["chats"] == []

    def test_chat_list_filter_by_novel(self, client):
        uid = "chat_user2"
        novel_id, char_id = _setup_chat_prereqs(client, uid)

        res = client.get(f"/api/chats/list?user_id={uid}&novel_id={novel_id}")
        assert res.status_code == 200
        assert res.json()["chats"] == []


class TestChatMessages:
    def test_messages_nonexistent_chat(self, client):
        """不存在的对话应返回 404。"""
        uid = "chat_user3"
        _setup_chat_prereqs(client, uid)

        res = client.get("/api/chats/messages?chat_id=nonexistent_chat")
        assert res.status_code == 404


class TestChatDelete:
    def test_delete_nonexistent_chat(self, client):
        """删除不存在的对话返回 404。"""
        uid = "chat_user4"
        _setup_chat_prereqs(client, uid)

        res = client.post(f"/api/chats/delete?chat_id=nonexistent&user_id={uid}")
        assert res.status_code == 404


class TestChatCharacters:
    def test_get_characters(self, client):
        """获取可对话角色列表。"""
        uid = "chat_user5"
        novel_id, char_id = _setup_chat_prereqs(client, uid)

        res = client.get(f"/api/chats/characters?user_id={uid}&novel_id={novel_id}")
        assert res.status_code == 200
        chars = res.json()["characters"]
        assert len(chars) == 1
        assert chars[0]["name"] == "角色1"

    def test_remove_character(self, client):
        """移除角色。"""
        uid = "chat_user6"
        novel_id, char_id = _setup_chat_prereqs(client, uid)

        res = client.post(
            f"/api/chats/remove-characters?novel_id={novel_id}&user_id={uid}&character_id={char_id}"
        )
        assert res.status_code == 200
        assert res.json()["status"] == "removed"

    def test_remove_nonexistent_character(self, client):
        """移除不存在的角色返回 404。"""
        uid = "chat_user7"
        novel_id, char_id = _setup_chat_prereqs(client, uid)

        res = client.post(
            f"/api/chats/remove-characters?novel_id={novel_id}&user_id={uid}&character_id=no_such_char"
        )
        assert res.status_code == 404


class TestLatestNovel:
    def test_latest_novel_empty(self, client):
        """没有对话记录时返回 null。"""
        uid = "chat_user8"
        novel_id, char_id = _setup_chat_prereqs(client, uid)

        res = client.get(f"/api/chats/latest-novel?user_id={uid}")
        assert res.status_code == 200
        assert res.json()["novel_id"] is None
