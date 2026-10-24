# SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
# SPDX-License-Identifier: AGPL-3.0-or-later

"""care_service 直接单测——概率门控、冷却去重、回响格式、无合格记忆返回 None。

终审盲区补债：原先仅经 agent_ops 间接覆盖（且只测了 care_level=0 不命中），
本文件对 server/services/care_service.py 做直连测试。随机性用 monkeypatch
random.random 消除。
"""
import asyncio
import json

import pytest

from tests.helpers_agent import isolate_db  # noqa: F401  供 fixture 链解析

USER_ID = "u_care"
NOVEL_ID = "n_care"
CHARACTER_ID = "c_care"
CHARACTER_NAME = "沈砚"

HOUR_MS = 3_600_000


async def _seed_scene(db):
    """插入 users/worlds/world_characters/evolutions/novels/novel_characters 父行（FK 全链）。"""
    from server.storage.sqlite_client import now_ms
    now = now_ms()
    await db.execute(
        "INSERT INTO users (user_id, nickname, created_at) VALUES (?, ?, ?)",
        (USER_ID, "care_user", now),
    )
    await db.execute(
        "INSERT INTO worlds (world_id, user_id, name, created_at) VALUES (?, ?, ?, ?)",
        ("w_care", USER_ID, "回响测试世界", now),
    )
    await db.execute(
        "INSERT INTO world_characters (character_id, world_id, name) VALUES (?, ?, ?)",
        ("src_care", "w_care", CHARACTER_NAME),
    )
    await db.execute(
        "INSERT INTO world_evolutions (evolution_id, user_id, world_id, created_at) "
        "VALUES (?, ?, ?, ?)",
        ("evo_care", USER_ID, "w_care", now),
    )
    await db.execute(
        "INSERT INTO novels (novel_id, user_id, world_id, evolution_id, title, "
        "content, world_snapshot, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (NOVEL_ID, USER_ID, "w_care", "evo_care", "回响测试小说", "正文", "{}", now),
    )
    await db.execute(
        "INSERT INTO novel_characters (character_id, novel_id, user_id, "
        "source_character_id, character_snapshot, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (
            CHARACTER_ID, NOVEL_ID, USER_ID, "src_care",
            json.dumps({"name": CHARACTER_NAME}, ensure_ascii=False), now,
        ),
    )
    await db.commit()


async def _add_memory(db, memory_id, content, *, updated_at=None,
                      memory_type="event", last_recalled_at=None):
    """直插 memories 行（可控 updated_at / last_recalled_at，默认不过期）。"""
    from server.storage.sqlite_client import now_ms
    ts = updated_at if updated_at is not None else now_ms()
    await db.execute(
        """INSERT INTO memories
           (memory_id, user_id, novel_id, character_id, memory_type, content,
            created_at, updated_at, last_recalled_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (memory_id, USER_ID, NOVEL_ID, CHARACTER_ID, memory_type, content,
         ts, ts, last_recalled_at),
    )
    await db.commit()


async def _get_last_recalled_at(memory_id):
    from server.storage.sqlite_client import get_db
    db = await get_db()
    cur = await db.execute(
        "SELECT last_recalled_at FROM memories WHERE memory_id = ?", (memory_id,))
    row = await cur.fetchone()
    return row["last_recalled_at"] if row is not None else None


class TestProbabilityGate:
    def test_care_level_zero_never_triggers(self, isolate_db, monkeypatch):
        """care_level=0 → p=0，有合格记忆也绝不触发，且不写 last_recalled_at。"""
        import server.services.care_service as cs
        monkeypatch.setattr(cs.random, "random", lambda: 0.5)

        async def _scene():
            db = await cs.get_db()
            await _seed_scene(db)
            await _add_memory(db, "mem_e1", "她在码头等了一夜")

        asyncio.run(_scene())

        result = asyncio.run(cs.judge_and_prepare_care(
            USER_ID, NOVEL_ID, CHARACTER_ID, care_level=0, is_active=True))
        assert result is None
        assert asyncio.run(_get_last_recalled_at("mem_e1")) is None

    def test_probability_miss_returns_none(self, isolate_db, monkeypatch):
        """care_level=80 → p=0.64，随机数 0.9 > p → 不触发，不写时间戳。"""
        import server.config as cfg
        import server.services.care_service as cs
        monkeypatch.setattr(cfg.config, "CARE_COOLDOWN_HOURS", 24)
        monkeypatch.setattr(cs.random, "random", lambda: 0.9)

        async def _scene():
            db = await cs.get_db()
            await _seed_scene(db)
            await _add_memory(db, "mem_e1", "她在码头等了一夜")

        asyncio.run(_scene())

        result = asyncio.run(cs.judge_and_prepare_care(
            USER_ID, NOVEL_ID, CHARACTER_ID, care_level=80, is_active=True))
        assert result is None
        assert asyncio.run(_get_last_recalled_at("mem_e1")) is None


class TestHitFormat:
    def test_active_hit_returns_pending_memory(self, isolate_db, monkeypatch):
        """命中（主动）→ 返回 [待回响记忆] 格式，选中最新 event 记忆并写时间戳。"""
        import server.config as cfg
        import server.services.care_service as cs
        from server.storage.sqlite_client import now_ms
        monkeypatch.setattr(cfg.config, "CARE_COOLDOWN_HOURS", 24)
        monkeypatch.setattr(cs.random, "random", lambda: 0.0)  # 必命中

        now = now_ms()

        async def _scene():
            db = await cs.get_db()
            await _seed_scene(db)
            await _add_memory(db, "mem_new", "最新事件", updated_at=now)
            await _add_memory(db, "mem_old", "更早事件", updated_at=now - HOUR_MS)
            # user_fact 不参与回响（查询限定 memory_type='event'）
            await _add_memory(db, "mem_fact", "用户偏好", updated_at=now,
                              memory_type="user_fact")

        asyncio.run(_scene())

        result = asyncio.run(cs.judge_and_prepare_care(
            USER_ID, NOVEL_ID, CHARACTER_ID, care_level=80, is_active=True))
        assert result is not None
        assert result["role"] == "care_event"
        assert result["round"] == 0
        assert isinstance(result["timestamp"], int)

        label, sep, payload = result["content"].partition("\n")
        assert sep != ""
        assert label == "[待回响记忆]"
        data = json.loads(payload)
        # ORDER BY updated_at DESC → 最新 event 记忆被选中，user_fact 被排除
        assert data["memory_id"] == "mem_new"
        assert data["type"] == "event"
        assert data["content"] == "最新事件"
        assert data["character_name"] == CHARACTER_NAME

        # 命中即在事务内写 last_recalled_at 并提交
        recalled = asyncio.run(_get_last_recalled_at("mem_new"))
        assert recalled is not None and recalled >= now
        assert asyncio.run(_get_last_recalled_at("mem_old")) is None

    def test_passive_hit_uses_passive_label(self, isolate_db, monkeypatch):
        """命中（被动）→ 标签为 [被动回响 - 事件记忆]。"""
        import server.config as cfg
        import server.services.care_service as cs
        monkeypatch.setattr(cfg.config, "CARE_COOLDOWN_HOURS", 24)
        monkeypatch.setattr(cs.random, "random", lambda: 0.0)

        async def _scene():
            db = await cs.get_db()
            await _seed_scene(db)
            await _add_memory(db, "mem_e1", "她在码头等了一夜")

        asyncio.run(_scene())

        result = asyncio.run(cs.judge_and_prepare_care(
            USER_ID, NOVEL_ID, CHARACTER_ID, care_level=80, is_active=False))
        assert result is not None
        assert result["content"].startswith("[被动回响 - 事件记忆]\n")


class TestCooldown:
    def test_cooldown_blocks_recently_recalled_memory(self, isolate_db, monkeypatch):
        """冷却内（last_recalled_at 距今 < 24h）的记忆不再被选中。

        mem_a 处于冷却 → 第一次选 mem_b；mem_b 刚被召回进入冷却 → 第二次无合格
        记忆返回 None（同时覆盖 BEGIN IMMEDIATE → ROLLBACK 后连接仍可用）。
        """
        import server.config as cfg
        import server.services.care_service as cs
        from server.storage.sqlite_client import now_ms
        monkeypatch.setattr(cfg.config, "CARE_COOLDOWN_HOURS", 24)
        monkeypatch.setattr(cs.random, "random", lambda: 0.0)

        now = now_ms()

        async def _scene():
            db = await cs.get_db()
            await _seed_scene(db)
            await _add_memory(db, "mem_a", "冷却中的事件",
                              updated_at=now, last_recalled_at=now - HOUR_MS)
            await _add_memory(db, "mem_b", "从未召回的事件",
                              updated_at=now - HOUR_MS)

        asyncio.run(_scene())

        r1 = asyncio.run(cs.judge_and_prepare_care(
            USER_ID, NOVEL_ID, CHARACTER_ID, care_level=80, is_active=True))
        assert r1 is not None
        assert "mem_b" in r1["content"]  # 冷却内的 mem_a 被排除

        r2 = asyncio.run(cs.judge_and_prepare_care(
            USER_ID, NOVEL_ID, CHARACTER_ID, care_level=80, is_active=True))
        assert r2 is None


class TestNoEligibleMemory:
    def test_returns_none_when_no_memory(self, isolate_db, monkeypatch):
        """概率命中但无任何记忆 → None（ROLLBACK 路径）。"""
        import server.config as cfg
        import server.services.care_service as cs
        monkeypatch.setattr(cfg.config, "CARE_COOLDOWN_HOURS", 24)
        monkeypatch.setattr(cs.random, "random", lambda: 0.0)

        async def _scene():
            db = await cs.get_db()
            await _seed_scene(db)

        asyncio.run(_scene())

        result = asyncio.run(cs.judge_and_prepare_care(
            USER_ID, NOVEL_ID, CHARACTER_ID, care_level=80, is_active=True))
        assert result is None
