# SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
# SPDX-License-Identifier: AGPL-3.0-or-later

"""retrieval_service 直接单测——BM25 降级、RRF 融合、时间衰减、top_k 截断。

终审盲区补债：原先仅经 agent_ops 间接覆盖，本文件对
server/services/retrieval_service.py 做直连测试。

embeddings 说明：编码模型是本地 BGE（models/ 不存在、sentence_transformers
未安装），向量通道一律 mock encode_single——降级用例让它抛错，RRF 用例用
确定性伪向量直插 memory_embeddings（sqlite-vec 本地可用），不触碰真实模型。
"""
import asyncio
import json
import math
import struct

import pytest

from tests.helpers_agent import isolate_db  # noqa: F401  供 fixture 链解析

USER_ID = "u_ret"
NOVEL_ID = "n_ret"
CHARACTER_ID = "c_ret"
CHARACTER_NAME = "林知夏"

DAY_MS = 86_400_000


def _boom_encode(text: str):
    """模拟嵌入模型不可用（sentence_transformers 缺失/models/ 不存在）。"""
    raise RuntimeError("嵌入模型不可用")


def _unit(dim: int, *hot: int) -> list[float]:
    """构造归一化单位向量：第 hot 各维 = 1/sqrt(len(hot))，其余为 0。"""
    v = [0.0] * dim
    w = 1.0 / math.sqrt(len(hot))
    for i in hot:
        v[i] = w
    return v


async def _seed_scene(db):
    """插入 users/worlds/world_characters/evolutions/novels/novel_characters 父行（FK 全链）。"""
    from server.storage.sqlite_client import now_ms
    now = now_ms()
    await db.execute(
        "INSERT INTO users (user_id, nickname, created_at) VALUES (?, ?, ?)",
        (USER_ID, "ret_user", now),
    )
    await db.execute(
        "INSERT INTO worlds (world_id, user_id, name, created_at) VALUES (?, ?, ?, ?)",
        ("w_ret", USER_ID, "检索测试世界", now),
    )
    await db.execute(
        "INSERT INTO world_characters (character_id, world_id, name) VALUES (?, ?, ?)",
        ("src_ret", "w_ret", CHARACTER_NAME),
    )
    await db.execute(
        "INSERT INTO world_evolutions (evolution_id, user_id, world_id, created_at) "
        "VALUES (?, ?, ?, ?)",
        ("evo_ret", USER_ID, "w_ret", now),
    )
    await db.execute(
        "INSERT INTO novels (novel_id, user_id, world_id, evolution_id, title, "
        "content, world_snapshot, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (NOVEL_ID, USER_ID, "w_ret", "evo_ret", "检索测试小说", "正文", "{}", now),
    )
    await db.execute(
        "INSERT INTO novel_characters (character_id, novel_id, user_id, "
        "source_character_id, character_snapshot, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (
            CHARACTER_ID, NOVEL_ID, USER_ID, "src_ret",
            json.dumps({"name": CHARACTER_NAME}, ensure_ascii=False), now,
        ),
    )
    await db.commit()


async def _add_memory(db, memory_id, tokens_freq, *, updated_at=None,
                      with_embedding=None):
    """直插 memories + memory_bm25（可控 updated_at / 词频），可选直插向量 blob。"""
    from server.storage.sqlite_client import now_ms
    ts = updated_at if updated_at is not None else now_ms()
    content = " ".join(tokens_freq.keys())
    await db.execute(
        """INSERT INTO memories
           (memory_id, user_id, novel_id, character_id, memory_type, content,
            created_at, updated_at)
           VALUES (?, ?, ?, ?, 'user_fact', ?, ?, ?)""",
        (memory_id, USER_ID, NOVEL_ID, CHARACTER_ID, content, ts, ts),
    )
    await db.executemany(
        "INSERT INTO memory_bm25 (memory_id, token, term_frequency) VALUES (?, ?, ?)",
        [(memory_id, tok, freq) for tok, freq in tokens_freq.items()],
    )
    if with_embedding is not None:
        blob = struct.pack(f"{len(with_embedding)}f", *with_embedding)
        await db.execute(
            "INSERT INTO memory_embeddings (memory_id, vector) VALUES (?, ?)",
            (memory_id, blob),
        )
    await db.commit()


class TestBm25Fallback:
    def test_bm25_only_when_vector_unavailable(self, isolate_db, monkeypatch):
        """向量通道异常（encode_single 抛错）→ 静默降级为纯 BM25，结果字段完整。"""
        import server.services.retrieval_service as rs
        monkeypatch.setattr(rs, "encode_single", _boom_encode)

        async def _scene():
            db = await rs.get_db()
            await _seed_scene(db)
            await _add_memory(db, "mem_a", {"苹果": 5})
            await _add_memory(db, "mem_b", {"苹果": 2})
            await _add_memory(db, "mem_c", {"香蕉": 4})

        asyncio.run(_scene())

        results = asyncio.run(
            rs.retrieve("苹果", USER_ID, NOVEL_ID, CHARACTER_ID))
        assert [r["memory_id"] for r in results] == ["mem_a", "mem_b"]
        first = results[0]
        assert set(first.keys()) == {
            "memory_id", "type", "content", "character_name",
            "created_at", "updated_at",
        }
        assert first["type"] == "user_fact"
        assert first["character_name"] == CHARACTER_NAME

    def test_no_match_returns_empty(self, isolate_db, monkeypatch):
        """查询 token 与所有记忆无交集 → RRF 候选为空 → 返回 []。"""
        import server.services.retrieval_service as rs
        monkeypatch.setattr(rs, "encode_single", _boom_encode)

        async def _scene():
            db = await rs.get_db()
            await _seed_scene(db)
            await _add_memory(db, "mem_a", {"苹果": 5})

        asyncio.run(_scene())

        results = asyncio.run(
            rs.retrieve("完全无关的词汇", USER_ID, NOVEL_ID, CHARACTER_ID))
        assert results == []


class TestRRFFusion:
    def test_dual_channel_second_beats_single_channel_first(
            self, isolate_db, monkeypatch):
        """RRF 融合序：两通道均排第二的记忆，胜过两个"单通道第一"。

        向量通道序：mem_x > mem_z；BM25 通道序：mem_y > mem_z。
        RRF：z = 1/62 + 1/62 ≈ 0.0323 > x = y = 1/61 ≈ 0.0164 → z 居首。
        （记忆均为新写，时间衰减对三者近似一致，不影响断言。）
        """
        import server.services.retrieval_service as rs

        dim = 1024
        query_vec = _unit(dim, 0, 1)   # cos 与 e1 ≈ 0.707、与 (e2+e3)/√2 = 0.5
        vec_x = _unit(dim, 0)          # mem_x：向量通道 rank 0
        vec_z = _unit(dim, 1, 2)       # mem_z：向量通道 rank 1
        monkeypatch.setattr(rs, "encode_single", lambda text: query_vec)

        async def _scene():
            db = await rs.get_db()
            await _seed_scene(db)
            # x：向量第一，token 不在查询里 → BM25 缺席
            await _add_memory(db, "mem_x", {"橙子": 5}, with_embedding=vec_x)
            # y：BM25 第一（词频 9），无向量行 → 向量通道缺席
            await _add_memory(db, "mem_y", {"苹果": 9})
            # z：BM25 第二（词频 1）+ 向量第二
            await _add_memory(db, "mem_z", {"开会": 1}, with_embedding=vec_z)

        asyncio.run(_scene())

        results = asyncio.run(
            rs.retrieve("苹果 开会", USER_ID, NOVEL_ID, CHARACTER_ID))
        ids = [r["memory_id"] for r in results]
        assert len(ids) == 3
        assert ids[0] == "mem_z"
        assert set(ids[1:]) == {"mem_x", "mem_y"}


class TestTimeDecay:
    def test_decay_sends_stale_rank0_memory_to_last(self, isolate_db, monkeypatch):
        """时间衰减翻转融合序：BM25 rank 0 但 30 天未更新的记忆跌至末位。

        mem_old = 1/61 × exp(-ln2/15 × 30) = 1/61 × 0.25 ≈ 0.0041
        mem_new = 1/62 × ≈1.0 ≈ 0.0161 → 新者靠前。
        """
        import server.config as cfg
        import server.services.retrieval_service as rs
        from server.storage.sqlite_client import now_ms
        monkeypatch.setattr(cfg.config, "DECAY_HALF_LIFE_DAYS", 15.0)
        monkeypatch.setattr(rs, "encode_single", _boom_encode)

        now = now_ms()

        async def _scene():
            db = await rs.get_db()
            await _seed_scene(db)
            await _add_memory(db, "mem_old", {"苹果": 9},
                              updated_at=now - 30 * DAY_MS)
            await _add_memory(db, "mem_new", {"苹果": 5}, updated_at=now)

        asyncio.run(_scene())

        results = asyncio.run(
            rs.retrieve("苹果", USER_ID, NOVEL_ID, CHARACTER_ID))
        assert [r["memory_id"] for r in results] == ["mem_new", "mem_old"]


class TestTopK:
    def test_top_k_truncation(self, isolate_db, monkeypatch):
        """top_k 截断：3 条命中只返回前 top_k 条，且按融合序取前缀。"""
        import server.services.retrieval_service as rs
        monkeypatch.setattr(rs, "encode_single", _boom_encode)

        async def _scene():
            db = await rs.get_db()
            await _seed_scene(db)
            await _add_memory(db, "mem_1", {"苹果": 5})
            await _add_memory(db, "mem_2", {"苹果": 3})
            await _add_memory(db, "mem_3", {"苹果": 1})

        asyncio.run(_scene())

        r2 = asyncio.run(
            rs.retrieve("苹果", USER_ID, NOVEL_ID, CHARACTER_ID, top_k=2))
        assert [r["memory_id"] for r in r2] == ["mem_1", "mem_2"]

        r1 = asyncio.run(
            rs.retrieve("苹果", USER_ID, NOVEL_ID, CHARACTER_ID, top_k=1))
        assert [r["memory_id"] for r in r1] == ["mem_1"]
