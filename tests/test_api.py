# SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
# SPDX-License-Identifier: AGPL-3.0-or-later

"""API 端点测试。"""
import json
import os
import uuid

import pytest
from fastapi.testclient import TestClient

from tests.helpers import make_characters


@pytest.fixture(autouse=True)
def isolate_db(tmp_path, monkeypatch):
    """隔离数据库到临时路径。"""
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

    def test_complete_config_clamps_character_count(self, client, monkeypatch):
        import server.services.bridge_dispatcher as bd
        captured = {}

        async def fake_dispatch(agent, payload, *, wait=False, timeout=None):
            captured["agent"] = agent
            captured["payload"] = payload
            captured["wait"] = wait
            captured["timeout"] = timeout
            return {"world_history": "", "rules": [], "initial_event": None,
                    "characters": []}

        monkeypatch.setattr(bd, "dispatch", fake_dispatch)
        res = client.post("/api/worlds/complete-config", json={
            "world_name": "测试", "world_description": "描述",
            "characters": [{"name": f"a{i}", "identity": ""} for i in range(20)],
        })
        assert res.status_code == 200
        assert captured["agent"] == "worlds/complete-config"
        assert captured["wait"] is True
        assert captured["timeout"] == 600.0    # 覆盖 bridge oneshot 最坏 3×180s≈540s + 余量
        assert captured["payload"]["character_count"] == 10    # min(10, max(3, 20))

    def test_complete_config_bridge_unavailable_503(self, client, monkeypatch):
        import server.services.bridge_dispatcher as bd

        async def unavailable(agent, payload, *, wait=False, timeout=None):
            raise bd.BridgeUnavailable("桥接服务未启动")

        monkeypatch.setattr(bd, "dispatch", unavailable)
        res = client.post("/api/worlds/complete-config", json={
            "world_name": "测试", "world_description": "描述",
            "characters": [{"name": "a", "identity": ""}],
        })
        assert res.status_code == 503
        assert "yinghui-dsh-plug bridge" in res.json()["detail"]


def _world_with_evolution(client, nick: str) -> tuple[str, str, str]:
    """建用户+世界+演化，返回 (uid, world_id, evolution_id)。"""
    uid = _login(client, nick)
    res = client.post("/api/worlds/create", json={
        "user_id": uid, "name": "断点世界", "description": "",
        "world_history": "", "rules": [],
        "initial_event": {"content": "", "time": ""},
        "characters": make_characters(3),
    })
    wid = res.json()["world_id"]
    eid = client.post("/api/evolutions/create",
                      json={"user_id": uid, "world_id": wid}).json()["evolution_id"]
    return uid, wid, eid


def _insert_failed_task(uid: str, wid: str, eid: str,
                        task_id: str = "task_deadbeef") -> str:
    """直插 failed 任务行 + novel 行（模拟上次运行失败后的留存），返回 novel_id。"""
    import asyncio

    from server.storage.sqlite_client import get_db, now_ms

    async def _run() -> str:
        db = await get_db()
        now = now_ms()
        novel_id = f"novel_{uuid.uuid4().hex[:8]}"
        await db.execute(
            "INSERT INTO novels (novel_id, user_id, world_id, evolution_id, title, "
            "content, world_snapshot, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (novel_id, uid, wid, eid, "旧标题", "", "{}", now))
        await db.execute(
            "INSERT INTO novel_tasks (task_id, novel_id, evolution_id, status, "
            "result, error, created_at, completed_at) "
            "VALUES (?, ?, ?, 'failed', NULL, '章节回合超时', ?, ?)",
            (task_id, novel_id, eid, now, now))
        await db.commit()
        return novel_id

    return asyncio.run(_run())


def _make_chapters(work_base, task_id: str, indices=(1, 2)) -> None:
    """在工作目录为任务留存章节文件（断点续写判定输入）。"""
    from pathlib import Path

    chapters = Path(work_base) / task_id / "chapters"
    chapters.mkdir(parents=True, exist_ok=True)
    for i in indices:
        (chapters / f"ch_{i}.md").write_text(f"# 第{i}章\n\n上次运行留存的正文。",
                                             encoding="utf-8")


def _stub_dispatch(monkeypatch, *, fail: bool = False) -> dict:
    """stub bridge dispatcher，记录 payload；fail=True 时抛 BridgeUnavailable。"""
    import server.services.bridge_dispatcher as bd
    captured: dict = {}

    async def stub(agent, payload, *, wait=False, timeout=None):
        captured["agent"] = agent
        captured["payload"] = payload
        if fail:
            raise bd.BridgeUnavailable("桥接服务未启动")
        return {}

    monkeypatch.setattr(bd, "dispatch", stub)
    return captured


def _query_db(sql: str, params: tuple = ()) -> list[dict]:
    import asyncio

    from server.storage.sqlite_client import get_db

    async def _run():
        db = await get_db()
        rows = await (await db.execute(sql, params)).fetchall()
        return [dict(r) for r in rows]

    return asyncio.run(_run())


class TestNovelsGenerate:
    def test_generate_bridge_unavailable_503_no_orphan_rows(self, client, monkeypatch):
        """stub dispatcher 抛 BridgeUnavailable → 503，且预建 novel/task 行被回收（无孤儿）。"""
        import asyncio
        import server.services.bridge_dispatcher as bd

        async def unavailable(agent, payload, *, wait=False, timeout=None):
            raise bd.BridgeUnavailable("桥接服务未启动")

        monkeypatch.setattr(bd, "dispatch", unavailable)

        uid = _login(client, "novel_orphan")
        res = client.post("/api/worlds/create", json={
            "user_id": uid, "name": "孤儿回收世界", "description": "",
            "world_history": "", "rules": [],
            "initial_event": {"content": "", "time": ""},
            "characters": make_characters(3),
        })
        wid = res.json()["world_id"]
        evo = client.post("/api/evolutions/create", json={"user_id": uid, "world_id": wid})
        eid = evo.json()["evolution_id"]

        res = client.post(
            f"/api/novels/generate?user_id={uid}&world_id={wid}&evolution_id={eid}")
        assert res.status_code == 503
        assert "yinghui-dsh-plug bridge" in res.json()["detail"]

        from server.storage.sqlite_client import get_db

        async def _count_rows():
            db = await get_db()
            novels = await (await db.execute("SELECT COUNT(*) AS c FROM novels")).fetchone()
            tasks = await (await db.execute("SELECT COUNT(*) AS c FROM novel_tasks")).fetchone()
            return novels["c"], tasks["c"]

        novel_count, task_count = asyncio.run(_count_rows())
        assert novel_count == 0
        assert task_count == 0

    def test_generate_reuses_failed_task_with_chapters(self, client, monkeypatch, tmp_path):
        """断点续写：同演化 failed 任务 + 章节目录留存 → 复用原 task_id/novel_id、
        任务行重置 processing（error/result/completed_at 清空）、不新增行。"""
        import server.config as cfg
        monkeypatch.setattr(cfg.config, "NOVEL_WORK_DIR_BASE", str(tmp_path / "work"))
        captured = _stub_dispatch(monkeypatch)

        uid, wid, eid = _world_with_evolution(client, "novel_reuse")
        old_novel = _insert_failed_task(uid, wid, eid)
        _make_chapters(tmp_path / "work", "task_deadbeef")

        res = client.post(
            f"/api/novels/generate?user_id={uid}&world_id={wid}&evolution_id={eid}")
        assert res.status_code == 200
        # 响应模型逐字不变，task_id/novel_id 为复用值
        assert res.json() == {"task_id": "task_deadbeef", "novel_id": old_novel,
                              "status": "processing"}

        # 不新增行（novels/novel_tasks 各恰 1 行），任务行已重置
        tasks = _query_db("SELECT task_id, novel_id, status, result, error, completed_at "
                          "FROM novel_tasks")
        assert len(tasks) == 1
        row = tasks[0]
        assert row["task_id"] == "task_deadbeef" and row["novel_id"] == old_novel
        assert row["status"] == "processing"
        assert row["result"] is None and row["error"] is None
        assert row["completed_at"] is None
        novels = _query_db("SELECT novel_id FROM novels")
        assert [n["novel_id"] for n in novels] == [old_novel]
        # bridge 触发 payload 为复用 id
        assert captured["agent"] == "novels/generate"
        assert captured["payload"]["task_id"] == "task_deadbeef"
        assert captured["payload"]["novel_id"] == old_novel

    def test_generate_no_reuse_when_chapters_missing(self, client, monkeypatch, tmp_path):
        """failed 任务存在但章节目录不存在 → 不复用：预建新行，旧行原样保留。"""
        import server.config as cfg
        monkeypatch.setattr(cfg.config, "NOVEL_WORK_DIR_BASE", str(tmp_path / "work"))
        _stub_dispatch(monkeypatch)

        uid, wid, eid = _world_with_evolution(client, "novel_nodir")
        old_novel = _insert_failed_task(uid, wid, eid)

        res = client.post(
            f"/api/novels/generate?user_id={uid}&world_id={wid}&evolution_id={eid}")
        assert res.status_code == 200
        body = res.json()
        assert body["task_id"] != "task_deadbeef"
        assert body["novel_id"] != old_novel

        tasks = _query_db("SELECT task_id, status, error FROM novel_tasks "
                          "ORDER BY created_at")
        assert len(tasks) == 2
        assert tasks[0]["task_id"] == "task_deadbeef"
        assert tasks[0]["status"] == "failed" and tasks[0]["error"] == "章节回合超时"
        assert tasks[1]["status"] == "processing"
        assert len(_query_db("SELECT novel_id FROM novels")) == 2

    def test_generate_no_reuse_when_chapters_dir_empty(self, client, monkeypatch, tmp_path):
        """failed 任务章节目录存在但为空 → 不复用：预建新行。"""
        import server.config as cfg
        monkeypatch.setattr(cfg.config, "NOVEL_WORK_DIR_BASE", str(tmp_path / "work"))
        _stub_dispatch(monkeypatch)

        uid, wid, eid = _world_with_evolution(client, "novel_emptydir")
        old_novel = _insert_failed_task(uid, wid, eid)
        (tmp_path / "work" / "task_deadbeef" / "chapters").mkdir(parents=True)

        res = client.post(
            f"/api/novels/generate?user_id={uid}&world_id={wid}&evolution_id={eid}")
        assert res.status_code == 200
        assert res.json()["task_id"] != "task_deadbeef"
        assert res.json()["novel_id"] != old_novel
        assert len(_query_db("SELECT task_id FROM novel_tasks")) == 2

    def test_generate_no_failed_task_keeps_current_behavior(self, client, monkeypatch, tmp_path):
        """无 failed 任务 → 现行为不变：预建新 novel/task 行。"""
        import server.config as cfg
        monkeypatch.setattr(cfg.config, "NOVEL_WORK_DIR_BASE", str(tmp_path / "work"))
        captured = _stub_dispatch(monkeypatch)

        uid, wid, eid = _world_with_evolution(client, "novel_fresh")

        res = client.post(
            f"/api/novels/generate?user_id={uid}&world_id={wid}&evolution_id={eid}")
        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "processing"
        assert body["task_id"] and body["novel_id"]
        tasks = _query_db("SELECT task_id, novel_id, status FROM novel_tasks")
        assert len(tasks) == 1
        assert tasks[0]["task_id"] == body["task_id"]
        assert tasks[0]["novel_id"] == body["novel_id"]
        assert tasks[0]["status"] == "processing"
        assert captured["payload"]["task_id"] == body["task_id"]

    def test_generate_reuse_rollback_restores_failed_row(self, client, monkeypatch, tmp_path):
        """复用路径触发失败（bridge 不可达 503）→ 任务行恢复 failed 原值，
        行不删除（章节文件仍留存可再次重试续写）。"""
        import server.config as cfg
        monkeypatch.setattr(cfg.config, "NOVEL_WORK_DIR_BASE", str(tmp_path / "work"))
        _stub_dispatch(monkeypatch, fail=True)

        uid, wid, eid = _world_with_evolution(client, "novel_reuse_rb")
        old_novel = _insert_failed_task(uid, wid, eid)
        _make_chapters(tmp_path / "work", "task_deadbeef", indices=(1,))

        res = client.post(
            f"/api/novels/generate?user_id={uid}&world_id={wid}&evolution_id={eid}")
        assert res.status_code == 503

        tasks = _query_db("SELECT task_id, status, error, completed_at FROM novel_tasks")
        assert len(tasks) == 1
        row = tasks[0]
        assert row["task_id"] == "task_deadbeef"
        assert row["status"] == "failed" and row["error"] == "章节回合超时"
        assert row["completed_at"] is not None
        assert [n["novel_id"] for n in _query_db("SELECT novel_id FROM novels")] == [old_novel]
