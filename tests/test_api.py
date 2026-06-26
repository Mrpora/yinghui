# SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
# SPDX-License-Identifier: AGPL-3.0-or-later

"""API 端点测试。"""
import json
import os
import pytest
from fastapi.testclient import TestClient


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
            "characters": [{"name": "A", "identity": "战士"}],
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
            "characters": [{"name": "C", "identity": ""}],
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
            "characters": [{"name": "C", "identity": ""}],
        })
        wid = res.json()["world_id"]
        res2 = client.post(f"/api/worlds/delete?world_id={wid}&user_id=bob")
        assert res2.status_code == 404
