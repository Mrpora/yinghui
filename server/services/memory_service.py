# SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
# SPDX-License-Identifier: AGPL-3.0-or-later

"""永久记忆服务——创建、更新、删除、查询记忆，含 BM25 索引和向量索引。

维度模型：一条记忆归属于 (user_id, novel_id, character_id)。
character_id 引用 novel_characters.character_id（非旧 characters 表）。
"""
import asyncio
import json
import re
import struct
import logging
from collections import Counter

from uuid import uuid4

import jieba

from server.config import config
from server.storage.sqlite_client import get_db, now_ms
from server.services.embedding_service import encode_single

logger = logging.getLogger(__name__)

_vec0_initialized = False


def init_jieba():
    """预加载 jieba 词典，修正常见错误分词。在服务启动时调用。"""
    jieba.initialize()
    jieba.del_word("点有")
    jieba.add_word("找工作")
    logger.info("✅ jieba 词典预加载完成")


async def _ensure_vec0(db):
    """确保 vec0 虚拟表 memory_embeddings 存在（幂等）。"""
    global _vec0_initialized
    if _vec0_initialized:
        return
    try:
        import sqlite_vec
        db._conn.enable_load_extension(True)
        sqlite_vec.load(db._conn)
        db._conn.enable_load_extension(False)
        await db.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS memory_embeddings USING vec0(
                memory_id TEXT,
                vector FLOAT[1024]
            )
        """)
        await db.commit()
        _vec0_initialized = True
        logger.info("✅ vec0 虚拟表 memory_embeddings 就绪")
    except Exception as e:
        logger.warning("⚠️ sqlite-vec 加载失败，向量检索/存储不可用: %s", e)
        _vec0_initialized = True  # 不再重试


def _tokenize(text: str) -> list[str]:
    """分词并过滤纯标点/空白 token，仅保留含中文或字母数字的 token（本地 jieba 分词）。"""
    tokens = jieba.cut(text)
    return [t for t in tokens if re.search(r"[一-鿿\w]", t)]


async def _write_bm25_index(db, memory_id, keywords):
    """将分词结果写入 BM25 索引表，使用 Counter 统计词频。"""
    token_counts = Counter(keywords)
    await db.executemany(
        "INSERT INTO memory_bm25 (memory_id, token, term_frequency) VALUES (?, ?, ?)",
        [(memory_id, token, freq) for token, freq in token_counts.items()],
    )


async def _write_embedding(db, memory_id, embedding):
    """将 embedding 列表转为二进制 blob 写入 vec0 虚拟表。"""
    if embedding is None:
        return
    await _ensure_vec0(db)
    blob = struct.pack(f"{len(embedding)}f", *embedding)
    await db.execute(
        "INSERT INTO memory_embeddings (memory_id, vector) VALUES (?, ?)",
        (memory_id, blob),
    )


async def create_memory(user_id, novel_id, character_id, memory_type, content, expires_at=None):
    """创建一条永久记忆，含 BM25 索引和向量索引。

    Args:
        user_id: 用户 ID
        novel_id: 小说 ID
        character_id: 角色 ID（引用 novel_characters.character_id）
        memory_type: "user_fact" 或 "event"
        content: 记忆文本内容
        expires_at: 过期时间（Unix 毫秒时间戳，INTEGER），默认 30 天后

    Returns:
        dict: {"status": "success", "memory_id": ...} 或
              {"status": "error", "message": ...}
    """
    db = await get_db()

    # 检查记忆容量（排除已过期记忆，按 novel 维度限制）
    now = now_ms()
    cursor = await db.execute(
        """SELECT COUNT(*) FROM memories
           WHERE user_id = ? AND novel_id = ?
             AND (expires_at IS NULL OR expires_at > ?)""",
        (user_id, novel_id, now),
    )
    row = await cursor.fetchone()
    if row[0] >= config.MEMORY_LIMIT:
        return {
            "status": "error",
            "message": (
                f"记忆容量已满（上限 {config.MEMORY_LIMIT} 条），"
                "请删除旧记忆或使用已有的 memory_id 调用 update_memory 覆盖"
            ),
        }

    memory_id = uuid4().hex

    # 默认过期时间：30 天后
    if expires_at is None:
        expires_at = now + 30 * 24 * 3600 * 1000

    # 分词
    keywords = _tokenize(content)

    # 编码
    embedding = None
    try:
        embedding = encode_single(content)
    except Exception as e:
        logger.warning("编码记忆失败，将不存储向量: %s", e)

    # 写入 memories 表
    await db.execute(
        """INSERT INTO memories
           (memory_id, user_id, novel_id, character_id, memory_type, content,
            keywords, created_at, updated_at, expires_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            memory_id,
            user_id,
            novel_id,
            character_id,
            memory_type,
            content,
            json.dumps(keywords, ensure_ascii=False),
            now,
            now,
            expires_at,
        ),
    )

    # 写入 BM25 索引
    await _write_bm25_index(db, memory_id, keywords)

    # 写入向量索引（仅在编码成功时）
    if embedding is not None:
        await _write_embedding(db, memory_id, embedding)

    await db.commit()
    logger.info(
        "💚 创建记忆成功 memory_id=%s user_id=%s novel_id=%s character_id=%s",
        memory_id, user_id, novel_id, character_id,
    )
    return {"status": "success", "memory_id": memory_id}


async def update_memory(memory_id, content, memory_type=None):
    """更新一条永久记忆的内容、分词和向量。

    Args:
        memory_id: 记忆 ID
        content: 新的记忆文本内容
        memory_type: 可选，新的记忆类型；为 None 则不修改

    Returns:
        dict: {"status": "success", "memory_id": ...}
    """
    db = await get_db()
    now = now_ms()

    # 重新分词
    keywords = _tokenize(content)

    # 重新编码
    new_embedding = None
    try:
        new_embedding = encode_single(content)
    except Exception as e:
        logger.warning("更新记忆时编码失败，跳过向量更新: %s", e)

    # 更新 memories 表的行
    if memory_type is not None:
        await db.execute(
            """UPDATE memories
               SET content = ?, keywords = ?, updated_at = ?, memory_type = ?
               WHERE memory_id = ?""",
            (
                content,
                json.dumps(keywords, ensure_ascii=False),
                now,
                memory_type,
                memory_id,
            ),
        )
    else:
        await db.execute(
            """UPDATE memories
               SET content = ?, keywords = ?, updated_at = ?
               WHERE memory_id = ?""",
            (
                content,
                json.dumps(keywords, ensure_ascii=False),
                now,
                memory_id,
            ),
        )

    # 重新写入 BM25 索引（先删后插）
    await db.execute("DELETE FROM memory_bm25 WHERE memory_id = ?", (memory_id,))
    await _write_bm25_index(db, memory_id, keywords)

    # 重新写入向量（仅在编码成功时）
    if new_embedding is not None:
        await db.execute("DELETE FROM memory_embeddings WHERE memory_id = ?", (memory_id,))
        await _write_embedding(db, memory_id, new_embedding)
    else:
        await db.execute("DELETE FROM memory_embeddings WHERE memory_id = ?", (memory_id,))

    await db.commit()
    logger.info("💚 更新记忆成功 memory_id=%s", memory_id)
    return {"status": "success", "memory_id": memory_id}


async def delete_memory(memory_id):
    """删除一条永久记忆（清理三张表）。

    Args:
        memory_id: 记忆 ID

    Returns:
        dict: {"status": "deleted", "memory_id": ...}
    """
    db = await get_db()
    await asyncio.gather(
        db.execute("DELETE FROM memories WHERE memory_id = ?", (memory_id,)),
        db.execute("DELETE FROM memory_bm25 WHERE memory_id = ?", (memory_id,)),
        db.execute("DELETE FROM memory_embeddings WHERE memory_id = ?", (memory_id,)),
    )
    await db.commit()
    logger.info("🗑️ 删除记忆成功 memory_id=%s", memory_id)
    return {"status": "deleted", "memory_id": memory_id}


async def clear_all_memories(user_id, novel_id, character_id):
    """清除某个用户在某个小说下某个角色的所有记忆。

    Args:
        user_id: 用户 ID
        novel_id: 小说 ID
        character_id: 角色 ID（引用 novel_characters.character_id）

    Returns:
        dict: {"status": "cleared", "deleted_count": ...}
    """
    db = await get_db()

    # 找到该用户+小说+角色下的所有记忆 ID
    cursor = await db.execute(
        """SELECT memory_id FROM memories
           WHERE user_id = ? AND novel_id = ? AND character_id = ?""",
        (user_id, novel_id, character_id),
    )
    rows = await cursor.fetchall()

    memory_ids = [r["memory_id"] for r in rows]
    count = len(memory_ids)

    if count == 0:
        await db.commit()
        return {"status": "cleared", "deleted_count": 0}

    placeholders = ",".join("?" * count)
    await asyncio.gather(
        db.execute(
            f"DELETE FROM memories WHERE memory_id IN ({placeholders})", memory_ids
        ),
        db.execute(
            f"DELETE FROM memory_bm25 WHERE memory_id IN ({placeholders})", memory_ids
        ),
        db.execute(
            f"DELETE FROM memory_embeddings WHERE memory_id IN ({placeholders})", memory_ids
        ),
    )
    await db.commit()
    logger.info(
        "🗑️ 清除记忆成功 user_id=%s novel_id=%s character_id=%s deleted_count=%d",
        user_id, novel_id, character_id, count,
    )
    return {"status": "cleared", "deleted_count": count}


async def get_memories(user_id, novel_id=None, character_id=None):
    """获取用户的记忆列表，按更新时间倒序。

    Args:
        user_id: 用户 ID
        novel_id: 可选，按小说过滤；为 None 则返回所有小说的记忆
        character_id: 可选，按角色过滤；为 None 则返回所有角色的记忆
                      （引用 novel_characters.character_id）

    Returns:
        list[dict]: 每条记忆包含 memory_id, character_name, memory_type,
                    content, created_at, expires_at, recall_count
    """
    db = await get_db()

    now = now_ms()

    # 构建 WHERE 条件
    conditions = [
        "m.user_id = ?",
        "(m.expires_at IS NULL OR m.expires_at > ?)",
    ]
    params: list = [user_id, now]

    if novel_id is not None:
        conditions.append("m.novel_id = ?")
        params.append(novel_id)
    if character_id is not None:
        conditions.append("m.character_id = ?")
        params.append(character_id)

    where = " AND ".join(conditions)

    cursor = await db.execute(
        f"""SELECT m.memory_id, json_extract(nc.character_snapshot, '$.name') AS character_name, m.memory_type, m.content,
                   m.created_at, m.expires_at, m.recall_count
            FROM memories m
            JOIN novel_characters nc ON m.character_id = nc.character_id
            WHERE {where}
            ORDER BY m.created_at DESC""",
        params,
    )
    rows = await cursor.fetchall()

    return [dict(r) for r in rows]


async def get_memory_count(user_id, novel_id=None):
    """获取用户的记忆总数（按小说维度可选过滤）。

    Args:
        user_id: 用户 ID
        novel_id: 可选，按小说过滤

    Returns:
        int: 记忆数量
    """
    db = await get_db()
    now = now_ms()
    if novel_id is not None:
        cursor = await db.execute(
            """SELECT COUNT(*) FROM memories
               WHERE user_id = ? AND novel_id = ?
                 AND (expires_at IS NULL OR expires_at > ?)""",
            (user_id, novel_id, now),
        )
    else:
        cursor = await db.execute(
            """SELECT COUNT(*) FROM memories
               WHERE user_id = ?
                 AND (expires_at IS NULL OR expires_at > ?)""",
            (user_id, now),
        )
    row = await cursor.fetchone()
    return row[0]


async def update_expiry(memory_id, expires_at):
    """更新记忆的过期时间。

    Args:
        memory_id: 记忆 ID
        expires_at: 新的过期时间（Unix 毫秒时间戳，INTEGER）

    Returns:
        dict: {"status": "updated", "memory_id": ..., "expires_at": ...}
    """
    db = await get_db()
    await db.execute(
        "UPDATE memories SET expires_at = ? WHERE memory_id = ?",
        (expires_at, memory_id),
    )
    await db.commit()
    return {"status": "updated", "memory_id": memory_id, "expires_at": expires_at}


async def update_last_recalled(memory_id, increment_count=True):
    """记录记忆最近一次被调取的时间，可选递增调取次数。

    Args:
        memory_id: 记忆 ID
        increment_count: 是否递增 recall_count；False 时仅更新时间戳（如回响触发）
    """
    db = await get_db()
    now = now_ms()
    if increment_count:
        await db.execute(
            """UPDATE memories
               SET last_recalled_at = ?, recall_count = recall_count + 1
               WHERE memory_id = ?""",
            (now, memory_id),
        )
    else:
        await db.execute(
            "UPDATE memories SET last_recalled_at = ? WHERE memory_id = ?",
            (now, memory_id),
        )
    await db.commit()
