# SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
# SPDX-License-Identifier: AGPL-3.0-or-later

"""会话管理器测试——Session CRUD、上下文操作、时间线、关系图。"""
import json
import pytest
from server.services.session_manager import (
    SessionManager, Session, SessionStatus, WorldConfig, WorldInfo,
    CharacterConfig, InitialEvent,
)


@pytest.fixture(autouse=True)
def isolate_db(tmp_path, monkeypatch):
    """隔离数据库到临时路径。"""
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("SQLITE_PATH", db_path)
    monkeypatch.setenv("LLM_API_KEY", "sk-test-sm")

    import server.config as cfg
    monkeypatch.setattr(cfg.config, "SQLITE_PATH", db_path)

    import server.storage.sqlite_client as sc
    sc._conn = None
    import asyncio
    asyncio.run(sc.init_db())

    import server.prompt_loader as pl
    pl.PROMPTS = {
        "evolution_agent_v2/director_system": "导演提示词模板 {world_name} {world_config}",
        "evolution_agent_v2/world_injection": "世界配置注入 {world_config_json}",
        "evolution_agent_v2/character_system": (
            "角色提示词 {character_name} {identity} {personality} {speech_style} "
            "{world_name} {world_description} {world_history} {world_rules} "
            "{world_knowledge} {attitude_block} {core_goal} {backstory}"
        ),
    }

    yield

    if sc._conn:
        import asyncio
        asyncio.run(sc._conn.close())
        sc._conn = None


async def _create_test_world(user_id="test_user"):
    """创建测试世界及其角色，返回 world_id 和角色列表。"""
    from server.storage.sqlite_client import upsert_user, create_world, get_world_characters
    await upsert_user(user_id)
    wid = await create_world(
        user_id, "测试世界", "世界描述", "世界历史", ["规则1"],
        {"content": "初始事件", "time": "黎明"},
        [
            {"name": "张三", "identity": "战士", "personality": "勇敢", "speech_style": "豪放",
             "goal": "守护家园", "attitudes": {"李四": "信任"}, "backstory": "曾是民兵",
             "initial_location": "城门口", "initial_state": "警觉"},
            {"name": "李四", "identity": "法师", "personality": "冷静", "speech_style": "优雅",
             "goal": "探寻真相", "attitudes": {"张三": "怀疑"}, "backstory": "来自远方",
             "initial_location": "塔顶", "initial_state": "沉思"},
            {"name": "王五", "identity": "游侠", "personality": "洒脱", "speech_style": "诙谐",
             "goal": "寻找故人", "attitudes": {"张三": "观望"}, "backstory": "浪迹天涯",
             "initial_location": "渡口", "initial_state": "小酌"},
        ],
    )
    chars = await get_world_characters(wid)
    return wid, chars


class TestWorldConfigBuilding:
    """测试 WorldConfig 从 DB 行构建。"""

    @pytest.mark.asyncio
    async def test_build_world_config_from_db(self):
        wid, chars = await _create_test_world()
        from server.storage.sqlite_client import get_world
        world_row = await get_world(wid)

        mgr = SessionManager()
        wc = mgr._build_world_config(world_row, chars)

        assert wc.world.name == "测试世界"
        assert wc.world.description == "世界描述"
        assert wc.world.world_history == "世界历史"
        assert wc.world.rules == ["规则1"]
        assert wc.initial_event.content == "初始事件"
        assert wc.initial_event.time == "黎明"
        assert len(wc.characters) == 3
        assert wc.character_names == ["张三", "李四", "王五"]

    @pytest.mark.asyncio
    async def test_get_character_by_name(self):
        wid, chars = await _create_test_world()
        from server.storage.sqlite_client import get_world
        world_row = await get_world(wid)

        mgr = SessionManager()
        wc = mgr._build_world_config(world_row, chars)

        zhangsan = wc.get_character("张三")
        assert zhangsan is not None
        assert zhangsan.identity == "战士"
        assert zhangsan.goal == "守护家园"
        assert zhangsan.attitudes == {"李四": "信任"}

        assert wc.get_character("不存在") is None


class TestDirectorContextBuilding:
    """测试导演上下文构建。"""

    @pytest.mark.asyncio
    async def test_build_director_context(self):
        wid, chars = await _create_test_world()
        from server.storage.sqlite_client import get_world
        world_row = await get_world(wid)

        mgr = SessionManager()
        wc = mgr._build_world_config(world_row, chars)
        ctx = mgr._build_director_context(wc)

        assert len(ctx) == 1
        assert ctx[0]["role"] == "system"
        assert "测试世界" in ctx[0]["content"]
        assert "张三" in ctx[0]["content"]
        assert "李四" in ctx[0]["content"]

    @pytest.mark.asyncio
    async def test_build_character_context(self):
        wid, chars = await _create_test_world()
        from server.storage.sqlite_client import get_world
        world_row = await get_world(wid)

        mgr = SessionManager()
        wc = mgr._build_world_config(world_row, chars)
        zhangsan = wc.get_character("张三")
        ctx = mgr._build_character_context(zhangsan, wc)

        assert len(ctx) == 1
        assert ctx[0]["role"] == "system"
        assert "张三" in ctx[0]["content"]
        assert "战士" in ctx[0]["content"]
        assert "李四" in ctx[0]["content"]


class TestSessionLifecycle:
    """测试会话 CRUD 生命周期。"""

    @pytest.mark.asyncio
    async def test_create_session(self):
        wid, chars = await _create_test_world()
        mgr = SessionManager()
        session = await mgr.create("test_user", wid)

        assert session.id.startswith("sess_")
        assert session.user_id == "test_user"
        assert session.world_id == wid
        assert session.status == SessionStatus.IDLE
        assert session.current_round == 0
        assert session.character_names == ["张三", "李四", "王五"]
        assert len(session.director_context) == 1
        assert len(session.character_contexts) == 3

    @pytest.mark.asyncio
    async def test_get_session(self):
        wid, _ = await _create_test_world()
        mgr = SessionManager()
        created = await mgr.create("test_user", wid)
        loaded = await mgr.get(created.id, "test_user")

        assert loaded.id == created.id
        assert loaded.user_id == "test_user"
        assert loaded.world_id == wid
        assert loaded.status == SessionStatus.IDLE

    @pytest.mark.asyncio
    async def test_get_session_permission_denied(self):
        from server.storage.sqlite_client import upsert_user
        wid, _ = await _create_test_world()
        await upsert_user("alice")
        mgr = SessionManager()
        session = await mgr.create("alice", wid)

        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            await mgr.get(session.id, "bob")
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_delete_session(self):
        wid, _ = await _create_test_world()
        mgr = SessionManager()
        session = await mgr.create("test_user", wid)

        await mgr.delete(session.id, "test_user")
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            await mgr.get(session.id, "test_user")
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_session_permission_denied(self):
        from server.storage.sqlite_client import upsert_user
        wid, _ = await _create_test_world()
        await upsert_user("alice")
        mgr = SessionManager()
        session = await mgr.create("alice", wid)

        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            await mgr.delete(session.id, "bob")
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_list_user_sessions(self):
        wid, _ = await _create_test_world()
        mgr = SessionManager()
        await mgr.create("test_user", wid)
        await mgr.create("test_user", wid)

        sessions = await mgr.list_user_sessions("test_user")
        assert len(sessions) == 2
        assert all(s["world_name"] for s in sessions)


class TestContextOperations:
    """测试上下文读写操作。"""

    @pytest.mark.asyncio
    async def test_get_set_director_context(self):
        wid, _ = await _create_test_world()
        mgr = SessionManager()
        session = await mgr.create("test_user", wid)

        ctx = await mgr.get_context(session.id, "director")
        new_msg = {"role": "user", "content": "测试消息"}
        ctx.append(new_msg)
        await mgr.set_context(session.id, "director", ctx)

        reloaded = await mgr.get_context(session.id, "director")
        assert len(reloaded) == len(ctx)
        assert reloaded[-1]["content"] == "测试消息"

    @pytest.mark.asyncio
    async def test_get_set_character_context(self):
        wid, _ = await _create_test_world()
        mgr = SessionManager()
        session = await mgr.create("test_user", wid)

        ctx = await mgr.get_context(session.id, "张三")
        assert len(ctx) == 1
        new_msg = {"role": "assistant", "content": "角色回复"}
        ctx.append(new_msg)
        await mgr.set_context(session.id, "张三", ctx)

        reloaded = await mgr.get_context(session.id, "张三")
        assert len(reloaded) == 2
        assert reloaded[-1]["content"] == "角色回复"


class TestTimelineOperations:
    """测试时间线操作。"""

    @pytest.mark.asyncio
    async def test_empty_timeline(self):
        wid, _ = await _create_test_world()
        mgr = SessionManager()
        session = await mgr.create("test_user", wid)

        events = await mgr.get_timeline(session.id)
        assert events == []

    @pytest.mark.asyncio
    async def test_append_and_get_timeline(self):
        wid, _ = await _create_test_world()
        mgr = SessionManager()
        session = await mgr.create("test_user", wid)

        await mgr.append_timeline_event(session.id, {
            "type": "action", "content": "角色行动", "round": 1,
        })
        await mgr.append_timeline_event(session.id, {
            "type": "conflict", "content": "冲突事件", "round": 1,
        })

        events = await mgr.get_timeline(session.id)
        assert len(events) == 2
        assert events[0]["type"] == "action"
        assert events[1]["type"] == "conflict"

    @pytest.mark.asyncio
    async def test_invalid_event_type_fallback(self):
        wid, _ = await _create_test_world()
        mgr = SessionManager()
        session = await mgr.create("test_user", wid)

        await mgr.append_timeline_event(session.id, {
            "type": "invalid_type", "content": "测试",
        })
        events = await mgr.get_timeline(session.id)
        assert len(events) == 1
        assert events[0]["type"] == "action"  # fallback


class TestRelationshipOperations:
    """测试关系图操作。"""

    @pytest.mark.asyncio
    async def test_get_set_relationships(self):
        wid, _ = await _create_test_world()
        mgr = SessionManager()
        session = await mgr.create("test_user", wid)

        rels = await mgr.get_relationships(session.id)
        # 初始关系来自角色 attitudes
        assert "张三" in rels
        assert rels["张三"].get("李四") == "信任"

        new_rels = {"张三": {"李四": "敌对"}, "李四": {"张三": "恐惧"}}
        await mgr.set_relationships(session.id, new_rels)
        updated = await mgr.get_relationships(session.id)
        assert updated == new_rels


class TestUpdateMeta:
    """测试 update_meta 操作。"""

    @pytest.mark.asyncio
    async def test_update_status_and_round(self):
        wid, _ = await _create_test_world()
        mgr = SessionManager()
        session = await mgr.create("test_user", wid)

        await mgr.update_meta(session.id, status="running", current_round=3)
        loaded = await mgr.get(session.id, "test_user")

        assert loaded.status == SessionStatus.RUNNING
        assert loaded.current_round == 3
