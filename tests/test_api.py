# SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
# SPDX-License-Identifier: AGPL-3.0-or-later

"""API 端点测试。"""
import json
import os
import pytest
from fastapi.testclient import TestClient

from tests.helpers import make_characters


@pytest.fixture(autouse=True)
def isolate_db(tmp_path, monkeypatch):
    """隔离数据库到临时路径。"""
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("SQLITE_PATH", db_path)
    monkeypatch.setenv("LLM_API_KEY", "sk-test-placeholder")

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
        import asyncio
        asyncio.run(sc._conn.close())
        sc._conn = None


@pytest.fixture
def client(isolate_db):
    from server.main import app
    return TestClient(app)


def _login(client, nick):
    client.post("/api/auth/login", json={"nickname": nick})
    return nick


class TestAuth:
    def test_login_success(self, client):
        res = client.post("/api/auth/login", json={"nickname": "测试用户"})
        assert res.status_code == 200
        data = res.json()
        assert data["user_id"] == "测试用户"

    def test_login_forbidden(self, client):
        res = client.post("/api/auth/login", json={"nickname": "system"})
        assert res.status_code == 400

    def test_login_empty_nickname(self, client):
        res = client.post("/api/auth/login", json={"nickname": ""})
        assert res.status_code == 422


class TestWorlds:
    def test_create_and_list(self, client):
        uid = _login(client, "world_test")
        res = client.post("/api/worlds/create", json={
            "user_id": uid, "name": "测试世界", "description": "描述",
            "world_history": "", "rules": [],
            "initial_event": {"content": "开始", "time": "黎明"},
            "characters": make_characters(3),
        })
        assert res.status_code == 201
        wid = res.json()["world_id"]
        assert wid.startswith("world_")

        res2 = client.get(f"/api/worlds/list?user_id={uid}")
        assert res2.status_code == 200
        assert len(res2.json()["worlds"]) == 1

    def test_delete_own_world(self, client):
        uid = _login(client, "owner")
        res = client.post("/api/worlds/create", json={
            "user_id": uid, "name": "我的世界", "description": "",
            "world_history": "", "rules": [],
            "initial_event": {"content": "", "time": ""},
            "characters": make_characters(3),
        })
        wid = res.json()["world_id"]
        res2 = client.post(f"/api/worlds/delete?world_id={wid}&user_id={uid}")
        assert res2.status_code == 200
        assert res2.json()["status"] == "deleted"

    def test_cannot_delete_others_world(self, client):
        _login(client, "alice")
        _login(client, "bob")
        res = client.post("/api/worlds/create", json={
            "user_id": "alice", "name": "A的世界", "description": "",
            "world_history": "", "rules": [],
            "initial_event": {"content": "", "time": ""},
            "characters": make_characters(3),
        })
        wid = res.json()["world_id"]
        res2 = client.post(f"/api/worlds/delete?world_id={wid}&user_id=bob")
        assert res2.status_code == 404

    def test_create_world_min_characters_rejected(self, client):
        uid = _login(client, "min_char_user")
        res = client.post("/api/worlds/create", json={
            "user_id": uid, "name": "两人世界", "description": "",
            "world_history": "", "rules": [],
            "initial_event": {"content": "", "time": ""},
            "characters": make_characters(2),
        })
        assert res.status_code == 422

    def test_create_world_max_characters(self, client):
        uid = _login(client, "max_char_user")
        res = client.post("/api/worlds/create", json={
            "user_id": uid, "name": "十人世界", "description": "",
            "world_history": "", "rules": [],
            "initial_event": {"content": "", "time": ""},
            "characters": make_characters(10),
        })
        assert res.status_code == 201

        res2 = client.post("/api/worlds/create", json={
            "user_id": uid, "name": "十一人世界", "description": "",
            "world_history": "", "rules": [],
            "initial_event": {"content": "", "time": ""},
            "characters": make_characters(11),
        })
        assert res2.status_code == 422

    def test_update_world_character_bounds(self, client):
        uid = _login(client, "bounds_user")
        res = client.post("/api/worlds/create", json={
            "user_id": uid, "name": "边界世界", "description": "",
            "world_history": "", "rules": [],
            "initial_event": {"content": "", "time": ""},
            "characters": make_characters(3),
        })
        wid = res.json()["world_id"]
        base = {
            "user_id": uid, "world_id": wid, "name": "边界世界", "description": "",
            "world_history": "", "rules": [],
            "initial_event": {"content": "", "time": ""},
        }
        res2 = client.post("/api/worlds/update", json={**base, "characters": make_characters(2)})
        assert res2.status_code == 422
        res3 = client.post("/api/worlds/update", json={**base, "characters": make_characters(10)})
        assert res3.status_code == 200

    def test_update_world_remove_imported_character_400(self, client):
        import asyncio
        from uuid import uuid4
        from server.storage.sqlite_client import get_db, now_ms

        uid = _login(client, "guard_api")
        res = client.post("/api/worlds/create", json={
            "user_id": uid, "name": "守卫接口", "description": "",
            "world_history": "", "rules": [],
            "initial_event": {"content": "", "time": ""},
            "characters": make_characters(3),
        })
        wid = res.json()["world_id"]
        chars = client.get(f"/api/worlds/detail?world_id={wid}").json()["characters"]

        async def _import():
            db = await get_db()
            eid = f"sess_{uuid4().hex[:8]}"
            nid = f"novel_{uuid4().hex[:8]}"
            now = now_ms()
            await db.execute(
                "INSERT INTO world_evolutions (evolution_id, user_id, world_id, status, "
                "current_round, created_at) VALUES (?, ?, ?, 'idle', 0, ?)",
                (eid, uid, wid, now))
            await db.execute(
                "INSERT INTO novels (novel_id, user_id, world_id, evolution_id, title, "
                "content, world_snapshot, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (nid, uid, wid, eid, "t", "", "{}", now))
            await db.execute(
                "INSERT INTO novel_characters (character_id, novel_id, user_id, "
                "source_character_id, character_snapshot, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (f"nc_{uuid4().hex[:8]}", nid, uid, chars[0]["character_id"], "{}", now))
            await db.commit()
        asyncio.run(_import())

        new_chars = [c for c in make_characters(3) if c["name"] != "角色1"]
        new_chars.append({"name": "替补", "identity": ""})
        res2 = client.post("/api/worlds/update", json={
            "user_id": uid, "world_id": wid, "name": "守卫接口", "description": "",
            "world_history": "", "rules": [],
            "initial_event": {"content": "", "time": ""},
            "characters": new_chars,
        })
        assert res2.status_code == 400
        assert "角色1" in res2.json()["detail"]
