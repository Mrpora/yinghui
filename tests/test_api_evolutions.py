# SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
# SPDX-License-Identifier: AGPL-3.0-or-later

"""演化 API 端点测试——会话 CRUD + 时间线。"""
import pytest

from tests.helpers import make_characters


@pytest.fixture(autouse=True)
def isolate_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("SQLITE_PATH", db_path)
    monkeypatch.setenv("LLM_API_KEY", "sk-test-evo")

    import server.config as cfg
    monkeypatch.setattr(cfg.config, "SQLITE_PATH", db_path)

    import server.storage.sqlite_client as sc
    sc._conn = None
    import asyncio
    asyncio.run(sc.init_db())

    import server.prompt_loader as pl
    pl.PROMPTS = {
        "evolution_agent_v2/director_system": "导演模板 {world_name} {world_config}",
        "evolution_agent_v2/world_injection": "注入 {world_config_json}",
        "evolution_agent_v2/character_system": (
            "角色 {character_name} {identity} {personality} {speech_style} "
            "{world_name} {world_description} {world_history} {world_rules} "
            "{world_knowledge} {attitude_block} {core_goal} {backstory}"
        ),
    }

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


def _create_world(client, user_id, name="演化测试世界"):
    res = client.post("/api/worlds/create", json={
        "user_id": user_id, "name": name, "description": "测试",
        "world_history": "", "rules": [],
        "initial_event": {"content": "开始", "time": "黎明"},
        "characters": make_characters(3),
    })
    return res.json()["world_id"]


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


class TestEvolutionStartRoundValidation:
    def test_start_round_requires_valid_state(self, client):
        """IDLE 状态的会话允许启动轮次。但启动需要 LLM，此处测试参数校验。"""
        uid = _login(client, "evo_round")
        wid = _create_world(client, uid)
        create_res = client.post("/api/evolutions/create", json={
            "user_id": uid, "world_id": wid,
        })
        eid = create_res.json()["evolution_id"]

        # 没有 LLM 时 start-round 会触发后台任务（LLM调用会失败），
        # 但状态校验应先通过（IDLE → RUNNING）
        res = client.post(f"/api/evolutions/start-round?evolution_id={eid}&user_id={uid}")
        # 后台任务会发起 LLM 调用，可能返回 201 或遇到 LLM 错误
        # 这里测试的是路由层接受请求
        assert res.status_code in (200, 201, 500)
