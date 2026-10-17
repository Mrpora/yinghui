# SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
# SPDX-License-Identifier: AGPL-3.0-or-later

"""记忆 API 端点测试——列表/删除/更新过期/清空。"""
import pytest

from tests.helpers import make_characters


@pytest.fixture(autouse=True)
def isolate_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("SQLITE_PATH", db_path)
    monkeypatch.setenv("LLM_API_KEY", "sk-test-mem")

    import server.config as cfg
    monkeypatch.setattr(cfg.config, "SQLITE_PATH", db_path)
    # 配置较小的记忆上限以便测试容量限制
    monkeypatch.setattr(cfg.config, "MEMORY_LIMIT", 3)

    import server.storage.sqlite_client as sc
    sc._conn = None
    import asyncio
    asyncio.run(sc.init_db())

    import server.prompt_loader as pl
    pl.PROMPTS = {}

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


def _login(client, nick):
    client.post("/api/auth/login", json={"nickname": nick})
    return nick


def _setup_world_and_novel(client, user_id):
    """创建世界 → 演化 → 小说 → 导入角色，返回 (user_id, novel_id, character_id)。"""
    wid_res = client.post("/api/worlds/create", json={
        "user_id": user_id, "name": "记忆测试世界", "description": "desc",
        "world_history": "", "rules": [],
        "initial_event": {"content": "开始", "time": "黎明"},
        "characters": make_characters(3),
    })
    wid = wid_res.json()["world_id"]

    # 手动在 DB 中创建演化、小说、角色（跳过 LLM）
    import asyncio
    from server.storage.sqlite_client import get_db, now_ms
    async def _setup():
        from uuid import uuid4
        db = await get_db()
        # 查询 API 创建世界时生成的真实角色 ID
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
        import json
        await db.execute(
            "INSERT INTO novels (novel_id, user_id, world_id, evolution_id, title, "
            "content, world_snapshot, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (nid, user_id, wid, eid, "测试小说", "小说内容",
             json.dumps({"name": "测试世界", "characters": []}), now),
        )
        cid = f"nc_{uuid4().hex[:8]}"
        await db.execute(
            "INSERT INTO novel_characters (character_id, novel_id, user_id, "
            "source_character_id, character_snapshot, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (cid, nid, user_id, source_cid,
             json.dumps({"name": "角色1", "identity": "测试身份"}), now),
        )
        await db.commit()
        return nid, cid
    return asyncio.run(_setup())


class TestMemoryList:
    def test_empty_memory_list(self, client):
        uid = _login(client, "mem_user")
        novel_id, char_id = _setup_world_and_novel(client, uid)

        res = client.get(
            f"/api/memories/list?user_id={uid}&novel_id={novel_id}&character_id={char_id}"
        )
        assert res.status_code == 200
        assert res.json()["memories"] == []

    def test_memory_list_requires_params(self, client):
        """缺少必需参数时返回 422。"""
        _login(client, "mem_user2")
        res = client.get("/api/memories/list")
        assert res.status_code == 422


class TestMemoryDelete:
    def test_delete_nonexistent_memory(self, client):
        """删除不存在的记忆应正常返回 deleted 状态。"""
        _login(client, "mem_user3")
        res = client.post("/api/memories/delete?memory_id=nonexistent_id")
        # delete_memory 总是返回 deleted，即使不存在
        assert res.status_code == 200
        assert res.json()["status"] == "deleted"


class TestMemoryExpiry:
    def test_update_expiry_nonexistent(self, client):
        """更新不存在记忆的过期时间——底层 UPDATE 不报错但也不会创建。"""
        _login(client, "mem_user4")
        res = client.post(
            "/api/memories/update-expiry?memory_id=nonexistent",
            json={"expires_at": 9999999999999},
        )
        assert res.status_code == 200
        assert res.json()["status"] == "updated"


class TestMemoryClear:
    def test_clear_empty_memories(self, client):
        uid = _login(client, "mem_user5")
        novel_id, char_id = _setup_world_and_novel(client, uid)

        res = client.post(
            f"/api/memories/clear?user_id={uid}&novel_id={novel_id}&character_id={char_id}"
        )
        assert res.status_code == 200
        assert res.json()["deleted_count"] == 0
