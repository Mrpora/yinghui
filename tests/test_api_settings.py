# SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
# SPDX-License-Identifier: AGPL-3.0-or-later

"""设置 API 端点测试——关怀等级获取与更新。"""
import pytest

from tests.helpers import make_characters


@pytest.fixture(autouse=True)
def isolate_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("SQLITE_PATH", db_path)
    monkeypatch.setenv("LLM_API_KEY", "sk-test-settings")

    import server.config as cfg
    monkeypatch.setattr(cfg.config, "SQLITE_PATH", db_path)

    import server.storage.sqlite_client as sc
    sc._conn = None
    import asyncio
    asyncio.run(sc.init_db())

    import server.prompt_loader as pl
    pl.PROMPTS = {}

    yield

    if sc._conn:
        asyncio.run(sc._conn.close())
        sc._conn = None


@pytest.fixture
def client(isolate_db):
    from server.main import app
    from fastapi.testclient import TestClient
    return TestClient(app)


class TestCareLevel:
    def test_get_default_care_level(self, client):
        """未设置关怀等级时返回默认值 80。"""
        res = client.get(
            "/api/settings/care-level"
            "?user_id=test_user&novel_id=novel_1&character_id=char_1"
        )
        assert res.status_code == 200
        assert res.json()["level"] == 80

    def test_update_and_get_care_level(self, client):
        """设置后再次获取应返回更新后的值。"""
        import asyncio
        from uuid import uuid4
        from server.storage.sqlite_client import get_db, now_ms

        uid = "test_user"
        # 通过 API 创建世界（自动创建 user + world）
        client.post("/api/auth/login", json={"nickname": uid})
        wid_res = client.post("/api/worlds/create", json={
            "user_id": uid, "name": "t", "description": "",
            "world_history": "", "rules": [],
            "initial_event": {"content": "", "time": ""},
            "characters": make_characters(3),
        })
        wid = wid_res.json()["world_id"]

        async def _setup():
            db = await get_db()
            # 查询 API 创建世界时生成的真实角色 ID
            cursor = await db.execute(
                "SELECT character_id FROM world_characters WHERE world_id = ?", (wid,))
            row = await cursor.fetchone()
            source_cid = row["character_id"]

            now = now_ms()
            eid = f"sess_{uuid4().hex[:8]}"
            nid = f"novel_{uuid4().hex[:8]}"
            await db.execute(
                "INSERT INTO world_evolutions (evolution_id, user_id, world_id, status, current_round, created_at) "
                "VALUES (?, ?, ?, 'idle', 0, ?)", (eid, uid, wid, now))
            await db.execute(
                "INSERT INTO novels (novel_id, user_id, world_id, evolution_id, title, content, world_snapshot, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (nid, uid, wid, eid, "t", "", "{}", now))
            await db.execute(
                "INSERT INTO novel_characters (character_id, novel_id, user_id, source_character_id, character_snapshot, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                ("char_1", nid, uid, source_cid, "{}", now))
            await db.commit()
            return nid

        novel_id = asyncio.run(_setup())

        res_update = client.post("/api/settings/update-care-level", json={
            "user_id": uid,
            "novel_id": novel_id,
            "character_id": "char_1",
            "level": 50,
        })
        assert res_update.status_code == 200
        assert res_update.json()["level"] == 50

        res_get = client.get(
            f"/api/settings/care-level?user_id={uid}&novel_id={novel_id}&character_id=char_1"
        )
        assert res_get.status_code == 200
        assert res_get.json()["level"] == 50

    def test_update_multiple_users_independent(self, client):
        """不同用户的设置相互独立。"""
        import asyncio
        from uuid import uuid4
        from server.storage.sqlite_client import get_db, now_ms

        # 通过 API 创建世界（归属 alice）
        client.post("/api/auth/login", json={"nickname": "alice"})
        client.post("/api/auth/login", json={"nickname": "bob"})
        wid_res = client.post("/api/worlds/create", json={
            "user_id": "alice", "name": "t", "description": "",
            "world_history": "", "rules": [],
            "initial_event": {"content": "", "time": ""},
            "characters": make_characters(3),
        })
        wid = wid_res.json()["world_id"]

        async def _setup():
            db = await get_db()
            # 查询 API 创建世界时生成的真实角色 ID
            cursor = await db.execute(
                "SELECT character_id FROM world_characters WHERE world_id = ?", (wid,))
            row = await cursor.fetchone()
            source_cid = row["character_id"]

            now = now_ms()
            eid = f"sess_{uuid4().hex[:8]}"
            nid = f"novel_{uuid4().hex[:8]}"
            await db.execute(
                "INSERT INTO world_evolutions (evolution_id, user_id, world_id, status, current_round, created_at) "
                "VALUES (?, ?, ?, 'idle', 0, ?)", (eid, "alice", wid, now))
            await db.execute(
                "INSERT INTO novels (novel_id, user_id, world_id, evolution_id, title, content, world_snapshot, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (nid, "alice", wid, eid, "t", "", "{}", now))
            await db.execute(
                "INSERT INTO novel_characters (character_id, novel_id, user_id, source_character_id, character_snapshot, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                ("c1", nid, "alice", source_cid, "{}", now))
            await db.commit()
            return nid

        novel_id = asyncio.run(_setup())
        client.post("/api/settings/update-care-level", json={
            "user_id": "alice", "novel_id": novel_id, "character_id": "c1", "level": 30,
        })
        client.post("/api/settings/update-care-level", json={
            "user_id": "bob", "novel_id": novel_id, "character_id": "c1", "level": 70,
        })

        alice = client.get(
            f"/api/settings/care-level?user_id=alice&novel_id={novel_id}&character_id=c1"
        )
        bob = client.get(
            f"/api/settings/care-level?user_id=bob&novel_id={novel_id}&character_id=c1"
        )
        assert alice.json()["level"] == 30
        assert bob.json()["level"] == 70
