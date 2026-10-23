# SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
# SPDX-License-Identifier: AGPL-3.0-or-later

"""演化 API 端点测试——会话 CRUD + 时间线 + 桥接触发（dispatch 一律 stub）。"""
import asyncio

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
    asyncio.run(sc.init_db())

    yield

    if sc._conn:
        asyncio.run(sc._conn.close())
        sc._conn = None


@pytest.fixture(autouse=True)
def stub_dispatcher(monkeypatch):
    """所有用例 stub 掉桥接分发——测试不得发真 HTTP。"""
    import server.services.bridge_dispatcher as bd
    calls = []

    async def fake_dispatch(agent, payload, *, wait=False, timeout=None):
        calls.append({"agent": agent, "payload": payload})
        return {}

    monkeypatch.setattr(bd, "dispatch", fake_dispatch)
    return calls


@pytest.fixture
def client(isolate_db):
    from server.main import app
    from fastapi.testclient import TestClient
    return TestClient(app)


def _login(client, nick):
    client.post("/api/auth/login", json={"nickname": nick})
    return nick


def _create_world(client, user_id, name="演化测试世界"):
    res = client.post("/api/worlds/create", json={
        "user_id": user_id, "name": name, "description": "测试",
        "world_history": "", "rules": [],
        "initial_event": {"content": "开始", "time": "黎明"},
        "characters": make_characters(3),
    })
    return res.json()["world_id"]


def _pause_with_branches(client, uid, eid):
    """直接落库把演化置为 PAUSED 并写入 branch_options 事件。"""
    import json as _json
    from server.storage.sqlite_client import get_db

    async def _setup():
        db = await get_db()
        branch_event = {
            "type": "branch_options", "round": 1,
            "content": _json.dumps([
                {"index": 0, "title": "分支甲", "description": "甲描述"},
                {"index": 1, "title": "分支乙", "description": "乙描述"},
            ], ensure_ascii=False),
        }
        await db.execute(
            "UPDATE world_evolutions SET status = 'paused', current_round = 1, "
            "timeline = ? WHERE evolution_id = ?",
            (_json.dumps([branch_event], ensure_ascii=False), eid),
        )
        await db.commit()
    asyncio.run(_setup())


class TestEvolutionSessionLifecycle:
    def test_create_session(self, client):
        uid = _login(client, "evo_user")
        wid = _create_world(client, uid)

        res = client.post("/api/evolutions/create", json={
            "user_id": uid, "world_id": wid,
        })
        assert res.status_code == 201
        data = res.json()
        assert data["evolution_id"].startswith("sess_")
        assert data["status"] == "idle"
        assert data["max_rounds"] == 20

    def test_list_sessions(self, client):
        uid = _login(client, "evo_user2")
        wid = _create_world(client, uid)

        client.post("/api/evolutions/create", json={"user_id": uid, "world_id": wid})
        client.post("/api/evolutions/create", json={"user_id": uid, "world_id": wid})

        res = client.get(f"/api/evolutions/list?user_id={uid}")
        assert res.status_code == 200
        assert len(res.json()["sessions"]) == 2

    def test_get_session_detail(self, client):
        uid = _login(client, "evo_user3")
        wid = _create_world(client, uid)

        create_res = client.post("/api/evolutions/create", json={
            "user_id": uid, "world_id": wid,
        })
        eid = create_res.json()["evolution_id"]

        res = client.get(f"/api/evolutions/detail?evolution_id={eid}&user_id={uid}")
        assert res.status_code == 200
        data = res.json()
        assert data["evolution_id"] == eid
        assert data["character_names"] == ["角色1", "角色2", "角色3"]

    def test_detail_requires_owner(self, client):
        uid = _login(client, "evo_owner")
        wid = _create_world(client, uid)
        create_res = client.post("/api/evolutions/create", json={
            "user_id": uid, "world_id": wid,
        })
        eid = create_res.json()["evolution_id"]

        other = _login(client, "evo_other")
        res = client.get(f"/api/evolutions/detail?evolution_id={eid}&user_id={other}")
        assert res.status_code == 403

    def test_delete_session(self, client):
        uid = _login(client, "evo_user4")
        wid = _create_world(client, uid)
        create_res = client.post("/api/evolutions/create", json={
            "user_id": uid, "world_id": wid,
        })
        eid = create_res.json()["evolution_id"]

        res = client.post(f"/api/evolutions/delete?evolution_id={eid}&user_id={uid}")
        assert res.status_code == 200
        assert res.json()["status"] == "deleted"

        # 再次获取应 404
        detail_res = client.get(f"/api/evolutions/detail?evolution_id={eid}&user_id={uid}")
        assert detail_res.status_code == 404


class TestEvolutionTimeline:
    def test_empty_timeline(self, client):
        uid = _login(client, "evo_timeline")
        wid = _create_world(client, uid)
        create_res = client.post("/api/evolutions/create", json={
            "user_id": uid, "world_id": wid,
        })
        eid = create_res.json()["evolution_id"]

        res = client.get(f"/api/evolutions/timeline?evolution_id={eid}&user_id={uid}")
        assert res.status_code == 200
        data = res.json()
        assert data["events"] == []
        assert data["current_round"] == 0


class TestEvolutionSSE:
    @pytest.mark.skip(
        reason="SSE 端点产生无限响应流（永不关闭连接），同步 TestClient 的 "
        "iter_lines() 会永久阻塞。SSE 核心机制已有 test_sse_manager.py ×11 "
        "覆盖。HTTP 层 SSE 连接测试需 E2E 或异步测试基础设施。"
    )
    def test_sse_events_connection(self, client):
        uid = _login(client, "evo_sse")
        wid = _create_world(client, uid)
        create_res = client.post("/api/evolutions/create", json={
            "user_id": uid, "world_id": wid,
        })
        eid = create_res.json()["evolution_id"]

        with client.stream("GET", f"/api/evolutions/events?evolution_id={eid}&user_id={uid}") as response:
            assert response.status_code == 200
            assert response.headers["content-type"] == "text/event-stream; charset=utf-8"
            import itertools
            lines = list(itertools.islice(response.iter_lines(), 3))
            assert any("connected" in line for line in lines)


class TestEvolutionStartRound:
    def test_start_round_dispatches_and_migrates(self, client, stub_dispatcher):
        """start-round：stub dispatcher 被调用 + 原子迁移（自增/RUNNING）+ round_start SSE。"""
        uid = _login(client, "evo_round")
        wid = _create_world(client, uid)
        create_res = client.post("/api/evolutions/create", json={
            "user_id": uid, "world_id": wid,
        })
        eid = create_res.json()["evolution_id"]

        # 预订阅 SSE 通道捕获 round_start
        from server.dependencies import get_sse_manager
        sse = get_sse_manager()
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        sse.subscribe(f"evolution:{eid}", queue)

        try:
            res = client.post(f"/api/evolutions/start-round?evolution_id={eid}&user_id={uid}")
        finally:
            sse.unsubscribe(f"evolution:{eid}", queue)

        assert res.status_code == 200
        data = res.json()
        assert data["round"] == 1
        assert data["status"] == "running"

        # dispatcher 被 stub 调用，载荷含自增后的轮次
        assert len(stub_dispatcher) == 1
        call = stub_dispatcher[0]
        assert call["agent"] == "evolutions/start-round"
        assert call["payload"] == {"evolution_id": eid, "user_id": uid, "round": 1}

        # SSE round_start {round, max_rounds}
        event = queue.get_nowait()
        assert event["type"] == "round_start"
        assert event["data"] == {"round": 1, "max_rounds": 20}

        # 状态迁移落库：RUNNING + current_round=1
        detail = client.get(f"/api/evolutions/detail?evolution_id={eid}&user_id={uid}").json()
        assert detail["status"] == "running"
        assert detail["current_round"] == 1

    def test_start_round_bridge_unavailable_503_no_migration(self, client, monkeypatch):
        """桥接不可达 → 503，且不做任何状态迁移（保持原状态可重试）。"""
        import server.services.bridge_dispatcher as bd

        async def unavailable(agent, payload, *, wait=False, timeout=None):
            raise bd.BridgeUnavailable("桥接服务未启动")

        monkeypatch.setattr(bd, "dispatch", unavailable)

        uid = _login(client, "evo_round_503")
        wid = _create_world(client, uid)
        create_res = client.post("/api/evolutions/create", json={
            "user_id": uid, "world_id": wid,
        })
        eid = create_res.json()["evolution_id"]

        res = client.post(f"/api/evolutions/start-round?evolution_id={eid}&user_id={uid}")
        assert res.status_code == 503
        assert "yinghui-dsh-plug bridge" in res.json()["detail"]

        detail = client.get(f"/api/evolutions/detail?evolution_id={eid}&user_id={uid}").json()
        assert detail["status"] == "idle"
        assert detail["current_round"] == 0


class TestEvolutionSelectBranch:
    def test_select_branch_writes_decision_and_resumes(self, client, stub_dispatcher):
        """select-branch：dispatch 成功后写 user_decision + 置 RUNNING，响应体不变。"""
        uid = _login(client, "evo_branch")
        wid = _create_world(client, uid)
        create_res = client.post("/api/evolutions/create", json={
            "user_id": uid, "world_id": wid,
        })
        eid = create_res.json()["evolution_id"]
        _pause_with_branches(client, uid, eid)

        res = client.post(
            f"/api/evolutions/select-branch?evolution_id={eid}&user_id={uid}&branch_index=1")
        assert res.status_code == 200
        data = res.json()
        assert data == {"accepted": True, "selected_branch": {"index": 1, "title": "分支乙"}}

        assert stub_dispatcher[0]["agent"] == "evolutions/select-branch"
        assert stub_dispatcher[0]["payload"]["branch_index"] == 1

        detail = client.get(f"/api/evolutions/detail?evolution_id={eid}&user_id={uid}").json()
        assert detail["status"] == "running"

        timeline = client.get(f"/api/evolutions/timeline?evolution_id={eid}&user_id={uid}").json()
        decisions = [e for e in timeline["events"] if e["type"] == "user_decision"]
        assert len(decisions) == 1
        assert "分支乙" in decisions[0]["content"]

    def test_select_branch_bridge_unavailable_keeps_paused(self, client, monkeypatch):
        """dispatch 失败：不写决策、不置 RUNNING，保持 PAUSED 可重试。"""
        import server.services.bridge_dispatcher as bd

        async def unavailable(agent, payload, *, wait=False, timeout=None):
            raise bd.BridgeUnavailable("桥接服务未启动")

        monkeypatch.setattr(bd, "dispatch", unavailable)

        uid = _login(client, "evo_branch_503")
        wid = _create_world(client, uid)
        create_res = client.post("/api/evolutions/create", json={
            "user_id": uid, "world_id": wid,
        })
        eid = create_res.json()["evolution_id"]
        _pause_with_branches(client, uid, eid)

        res = client.post(
            f"/api/evolutions/select-branch?evolution_id={eid}&user_id={uid}&branch_index=0")
        assert res.status_code == 503

        detail = client.get(f"/api/evolutions/detail?evolution_id={eid}&user_id={uid}").json()
        assert detail["status"] == "paused"

        timeline = client.get(f"/api/evolutions/timeline?evolution_id={eid}&user_id={uid}").json()
        assert not [e for e in timeline["events"] if e["type"] == "user_decision"]

    def test_select_branch_twice_conflict_409(self, client, stub_dispatcher):
        """二次调用：RUNNING 非 PAUSED → 409。"""
        uid = _login(client, "evo_branch_twice")
        wid = _create_world(client, uid)
        create_res = client.post("/api/evolutions/create", json={
            "user_id": uid, "world_id": wid,
        })
        eid = create_res.json()["evolution_id"]
        _pause_with_branches(client, uid, eid)

        first = client.post(
            f"/api/evolutions/select-branch?evolution_id={eid}&user_id={uid}&branch_index=0")
        assert first.status_code == 200
        second = client.post(
            f"/api/evolutions/select-branch?evolution_id={eid}&user_id={uid}&branch_index=1")
        assert second.status_code == 409


class TestEvolutionCustomEvent:
    def test_custom_event_writes_decision_and_resumes(self, client, stub_dispatcher):
        """custom-event：dispatch 成功后写 user_decision（文本原样）+ 置 RUNNING。"""
        uid = _login(client, "evo_custom")
        wid = _create_world(client, uid)
        create_res = client.post("/api/evolutions/create", json={
            "user_id": uid, "world_id": wid,
        })
        eid = create_res.json()["evolution_id"]
        _pause_with_branches(client, uid, eid)

        res = client.post(
            f"/api/evolutions/custom-event?evolution_id={eid}&user_id={uid}"
            f"&event_text=陨石坠落在城北")
        assert res.status_code == 200
        assert res.json() == {"accepted": True}

        assert stub_dispatcher[0]["agent"] == "evolutions/custom-event"
        assert stub_dispatcher[0]["payload"]["event_text"] == "陨石坠落在城北"

        detail = client.get(f"/api/evolutions/detail?evolution_id={eid}&user_id={uid}").json()
        assert detail["status"] == "running"

        timeline = client.get(f"/api/evolutions/timeline?evolution_id={eid}&user_id={uid}").json()
        decisions = [e for e in timeline["events"] if e["type"] == "user_decision"]
        assert len(decisions) == 1
        assert decisions[0]["content"] == "陨石坠落在城北"
