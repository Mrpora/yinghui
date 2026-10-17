# SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
# SPDX-License-Identifier: AGPL-3.0-or-later

"""SQLite 存储层测试。"""
import asyncio
import pytest

from tests.helpers import make_characters


@pytest.fixture(autouse=True)
def isolate_db(tmp_path, monkeypatch):
    """使用临时数据库，通过环境变量隔离。"""
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("SQLITE_PATH", db_path)
    monkeypatch.setenv("LLM_API_KEY", "sk-test")

    import server.config as cfg
    monkeypatch.setattr(cfg.config, "SQLITE_PATH", db_path)

    import server.storage.sqlite_client as sc
    sc._conn = None
    asyncio.run(sc.init_db())

    import server.prompt_loader as pl
    pl.PROMPTS = {"test": "mock prompt"}

    yield str(db_path)

    if sc._conn:
        asyncio.run(sc._conn.close())
        sc._conn = None


class TestUsers:
    def test_upsert_new_user(self):
        from server.storage.sqlite_client import upsert_user
        user = asyncio.run(upsert_user("测试用户"))
        assert user["user_id"] == "测试用户"
        assert user["nickname"] == "测试用户"

    def test_upsert_existing_user(self):
        from server.storage.sqlite_client import upsert_user
        u1 = asyncio.run(upsert_user("老用户"))
        u2 = asyncio.run(upsert_user("老用户"))
        assert u1["user_id"] == u2["user_id"]

    def test_forbidden_nickname(self):
        from server.storage.sqlite_client import upsert_user
        with pytest.raises(ValueError):
            asyncio.run(upsert_user("system"))


class TestWorlds:
    def test_create_and_list(self):
        from server.storage.sqlite_client import upsert_user, create_world, list_worlds
        asyncio.run(upsert_user("admin"))
        wid = asyncio.run(create_world(
            "admin", "测试世界", "描述", "历史", ["规则1"],
            {"content": "开始", "time": "黎明"},
            make_characters(3),
        ))
        assert wid.startswith("world_")
        worlds = asyncio.run(list_worlds("admin"))
        assert len(worlds) == 1
        assert worlds[0]["name"] == "测试世界"
        assert worlds[0]["character_count"] == 3

    def test_get_world_and_characters(self):
        from server.storage.sqlite_client import upsert_user, create_world, get_world, get_world_characters
        asyncio.run(upsert_user("admin"))
        wid = asyncio.run(create_world(
            "admin", "世界", "描述", "", [],
            {"content": "开始", "time": "noon"},
            make_characters(3),
        ))
        w = asyncio.run(get_world(wid))
        assert w is not None
        assert w["name"] == "世界"
        chars = asyncio.run(get_world_characters(wid))
        assert len(chars) == 3
        assert chars[0]["name"] == "角色1"

    def test_soft_delete(self):
        from server.storage.sqlite_client import (
            upsert_user, create_world, get_world, soft_delete_world,
        )
        asyncio.run(upsert_user("admin"))
        wid = asyncio.run(create_world(
            "admin", "待删除", "", "", [],
            {"content": "", "time": ""},
            make_characters(3),
        ))
        assert asyncio.run(soft_delete_world(wid, "admin")) is True
        assert asyncio.run(get_world(wid)) is None
        assert asyncio.run(soft_delete_world(wid, "admin")) is False

    def test_permission_check(self):
        from server.storage.sqlite_client import (
            upsert_user, create_world, get_world, soft_delete_world,
        )
        asyncio.run(upsert_user("alice"))
        asyncio.run(upsert_user("bob"))
        wid = asyncio.run(create_world(
            "alice", "A的世界", "", "", [],
            {"content": "", "time": ""},
            make_characters(3),
        ))
        assert asyncio.run(soft_delete_world(wid, "bob")) is False
        assert asyncio.run(get_world(wid)) is not None

    def test_create_world_character_bounds(self):
        from server.storage.sqlite_client import upsert_user, create_world
        asyncio.run(upsert_user("bounds"))
        with pytest.raises(ValueError, match="3-10"):
            asyncio.run(create_world(
                "bounds", "两人", "", "", [],
                {"content": "", "time": ""},
                [{"name": "角色1", "identity": ""}, {"name": "角色2", "identity": ""}],
            ))
        with pytest.raises(ValueError, match="3-10"):
            asyncio.run(create_world(
                "bounds", "十一人", "", "", [],
                {"content": "", "time": ""},
                [{"name": f"角色{i}", "identity": ""} for i in range(1, 12)],
            ))

    def test_create_world_ten_characters_unique_colors(self):
        from server.storage.sqlite_client import (
            upsert_user, create_world, get_world_characters,
        )
        asyncio.run(upsert_user("palette"))
        chars = [{"name": f"角色{i}", "identity": "测试"} for i in range(1, 11)]
        wid = asyncio.run(create_world(
            "palette", "十色世界", "描述", "", [],
            {"content": "", "time": ""},
            chars,
        ))
        rows = asyncio.run(get_world_characters(wid))
        colors = [r["accent_color"] for r in rows]
        assert len(colors) == 10
        assert len(set(colors)) == 10
