# SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
# SPDX-License-Identifier: AGPL-3.0-or-later

"""统一 aiosqlite 连接 + 全部表结构（11 表），WAL 模式，外键开启。"""
import asyncio
import json
import logging
import os

import aiosqlite

logger = logging.getLogger(__name__)


def now_ms() -> int:
    """返回当前 UTC 时间的毫秒时间戳。"""
    from datetime import datetime, timezone
    return int(datetime.now(timezone.utc).timestamp() * 1000)


# 角色强调色调色板——上限 10 人需 ≥10 色，第 10-12 色为本次扩充
_CHARACTER_PALETTE = [
    "#7B9EFF", "#4ECDC4", "#FF6B5B", "#F5C842", "#B8835A", "#7B9A8E",
    "#E2805C", "#9B8E7E", "#C44B3A", "#8E7CC3", "#5F9EA0", "#D4A5A5",
]


def _pick_accent_color(name: str, assigned: set[str]) -> str:
    """按角色名哈希取色，撞色时向后探测第一个未用色。"""
    h = sum(ord(c) for c in name)
    idx = h % len(_CHARACTER_PALETTE)
    offset = 0
    while (_CHARACTER_PALETTE[(idx + offset) % len(_CHARACTER_PALETTE)] in assigned
           and offset < len(_CHARACTER_PALETTE)):
        offset += 1
    return _CHARACTER_PALETTE[(idx + offset) % len(_CHARACTER_PALETTE)]


_conn: aiosqlite.Connection | None = None
_lock = asyncio.Lock()


async def get_db() -> aiosqlite.Connection:
    global _conn
    if _conn is None:
        async with _lock:
            if _conn is None:
                from server.config import config
                os.makedirs(os.path.dirname(config.SQLITE_PATH), exist_ok=True)
                # check_same_thread=False：aiosqlite 通过 async 序列化所有操作，
                # 同一时刻仅一个操作在执行，不存在并发。但 sqlite-vec 等扩展需要
                # 从事件循环线程直接访问底层 _conn，默认的线程检查会误杀。
                _conn = await aiosqlite.connect(config.SQLITE_PATH, check_same_thread=False)
                _conn.row_factory = aiosqlite.Row
                await _conn.execute("PRAGMA journal_mode=WAL")
                await _conn.execute("PRAGMA foreign_keys=ON")
                await _conn.execute("PRAGMA busy_timeout=5000")
    return _conn


async def init_db():
    """创建全部 11 张表，幂等（IF NOT EXISTS）。无种子数据注入。"""
    conn = await get_db()
    await conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            user_id     TEXT PRIMARY KEY,
            nickname    TEXT NOT NULL UNIQUE,
            created_at  INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS worlds (
            world_id       TEXT PRIMARY KEY,
            user_id        TEXT NOT NULL REFERENCES users(user_id),
            name           TEXT NOT NULL,
            description    TEXT NOT NULL DEFAULT '',
            world_history  TEXT NOT NULL DEFAULT '',
            rules          TEXT NOT NULL DEFAULT '[]',
            initial_event  TEXT NOT NULL DEFAULT '{}',
            is_preset      INTEGER NOT NULL DEFAULT 0,
            is_deleted     INTEGER NOT NULL DEFAULT 0,
            created_at     INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_worlds_user ON worlds(user_id);
        CREATE INDEX IF NOT EXISTS idx_worlds_preset ON worlds(is_preset);
        CREATE INDEX IF NOT EXISTS idx_worlds_not_deleted ON worlds(is_deleted);

        CREATE TABLE IF NOT EXISTS world_characters (
            character_id     TEXT PRIMARY KEY,
            world_id         TEXT NOT NULL REFERENCES worlds(world_id),
            name             TEXT NOT NULL,
            identity         TEXT NOT NULL DEFAULT '',
            personality      TEXT NOT NULL DEFAULT '',
            speech_style     TEXT NOT NULL DEFAULT '',
            goal             TEXT NOT NULL DEFAULT '',
            attitudes        TEXT NOT NULL DEFAULT '{}',
            backstory        TEXT NOT NULL DEFAULT '',
            initial_location TEXT NOT NULL DEFAULT '',
            initial_state    TEXT NOT NULL DEFAULT '',
            accent_color     TEXT NOT NULL DEFAULT '',
            sort_order       INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_world_chars_world ON world_characters(world_id);

        CREATE TABLE IF NOT EXISTS world_evolutions (
            evolution_id       TEXT PRIMARY KEY,
            user_id            TEXT NOT NULL REFERENCES users(user_id),
            world_id           TEXT NOT NULL REFERENCES worlds(world_id),
            status             TEXT NOT NULL DEFAULT 'idle',
            current_round      INTEGER NOT NULL DEFAULT 0,
            max_rounds         INTEGER NOT NULL DEFAULT 20,
            global_notify_count INTEGER DEFAULT 0,
            director_context   TEXT NOT NULL DEFAULT '[]',
            character_contexts TEXT NOT NULL DEFAULT '{}',
            timeline           TEXT NOT NULL DEFAULT '[]',
            relationships      TEXT NOT NULL DEFAULT '{}',
            is_deleted         INTEGER NOT NULL DEFAULT 0,
            created_at         INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_evolutions_world ON world_evolutions(world_id);
        CREATE INDEX IF NOT EXISTS idx_evolutions_user ON world_evolutions(user_id);

        CREATE TABLE IF NOT EXISTS novels (
            novel_id        TEXT PRIMARY KEY,
            user_id         TEXT NOT NULL REFERENCES users(user_id),
            world_id        TEXT NOT NULL REFERENCES worlds(world_id),
            evolution_id    TEXT NOT NULL REFERENCES world_evolutions(evolution_id),
            title           TEXT NOT NULL,
            content         TEXT NOT NULL,
            world_snapshot  TEXT NOT NULL,
            is_deleted      INTEGER NOT NULL DEFAULT 0,
            created_at      INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_novels_user ON novels(user_id);

        CREATE TABLE IF NOT EXISTS novel_tasks (
            task_id       TEXT PRIMARY KEY,
            novel_id      TEXT NOT NULL REFERENCES novels(novel_id),
            evolution_id  TEXT NOT NULL REFERENCES world_evolutions(evolution_id),
            status        TEXT NOT NULL DEFAULT 'processing',
            result        TEXT,
            error         TEXT,
            created_at    INTEGER NOT NULL,
            completed_at  INTEGER
        );

        CREATE TABLE IF NOT EXISTS novel_characters (
            character_id        TEXT PRIMARY KEY,
            novel_id            TEXT NOT NULL REFERENCES novels(novel_id),
            user_id             TEXT NOT NULL REFERENCES users(user_id),
            source_character_id TEXT NOT NULL REFERENCES world_characters(character_id),
            character_snapshot  TEXT NOT NULL,
            story_context       TEXT NOT NULL DEFAULT '',
            accent_color        TEXT NOT NULL DEFAULT '',
            is_deleted          INTEGER NOT NULL DEFAULT 0,
            created_at          INTEGER NOT NULL,
            UNIQUE (novel_id, source_character_id)
        );
        CREATE INDEX IF NOT EXISTS idx_novel_chars_novel ON novel_characters(novel_id);

        CREATE TABLE IF NOT EXISTS character_chats (
            chat_id       TEXT PRIMARY KEY,
            user_id       TEXT NOT NULL REFERENCES users(user_id),
            novel_id      TEXT NOT NULL REFERENCES novels(novel_id),
            character_id  TEXT NOT NULL REFERENCES novel_characters(character_id),
            messages      TEXT NOT NULL DEFAULT '[]',
            is_deleted    INTEGER NOT NULL DEFAULT 0,
            created_at    INTEGER NOT NULL,
            modified_at   INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_chats_user_char ON character_chats(user_id, character_id);

        CREATE TABLE IF NOT EXISTS memories (
            memory_id        TEXT PRIMARY KEY,
            user_id          TEXT NOT NULL REFERENCES users(user_id),
            novel_id         TEXT NOT NULL REFERENCES novels(novel_id),
            character_id     TEXT NOT NULL REFERENCES novel_characters(character_id),
            memory_type      TEXT NOT NULL CHECK(memory_type IN ('user_fact', 'event')),
            content          TEXT NOT NULL,
            keywords         TEXT,
            created_at       INTEGER NOT NULL,
            updated_at       INTEGER NOT NULL,
            expires_at       INTEGER,
            last_recalled_at INTEGER,
            recall_count     INTEGER DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_memories_novel ON memories(novel_id);
        CREATE INDEX IF NOT EXISTS idx_memories_user_novel ON memories(user_id, novel_id);

        CREATE TABLE IF NOT EXISTS memory_bm25 (
            memory_id       TEXT NOT NULL REFERENCES memories(memory_id) ON DELETE CASCADE,
            token           TEXT NOT NULL,
            term_frequency  INTEGER NOT NULL,
            PRIMARY KEY (memory_id, token)
        );

        CREATE TABLE IF NOT EXISTS care_settings (
            user_id       TEXT NOT NULL REFERENCES users(user_id),
            novel_id      TEXT NOT NULL REFERENCES novels(novel_id),
            character_id  TEXT NOT NULL REFERENCES novel_characters(character_id),
            level         INTEGER DEFAULT 80,
            PRIMARY KEY (user_id, novel_id, character_id)
        );
    """)
    await conn.commit()

    # 迁移：为已有 world_evolutions 表补齐 global_notify_count 列
    cursor = await conn.execute("PRAGMA table_info('world_evolutions')")
    rows = await cursor.fetchall()
    column_names = {row[1] for row in rows}
    if "global_notify_count" in column_names:
        logger.debug("global_notify_count 列已存在，跳过迁移")
    else:
        await conn.execute(
            "ALTER TABLE world_evolutions ADD COLUMN global_notify_count INTEGER DEFAULT 0"
        )
        await conn.commit()
        logger.info("迁移：world_evolutions 表新增 global_notify_count 列")

    # 创建向量虚拟表（sqlite-vec）
    try:
        import sqlite_vec
        conn._conn.enable_load_extension(True)
        sqlite_vec.load(conn._conn)
        conn._conn.enable_load_extension(False)
        await conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS memory_embeddings USING vec0(
                memory_id TEXT,
                vector FLOAT[1024]
            )
        """)
        await conn.commit()
        logger.info("✅ vec0 虚拟表 memory_embeddings 就绪")
    except Exception as e:
        logger.warning("⚠️ sqlite-vec 加载失败，向量检索/存储不可用: %s", e)

    logger.info("✅ SQLite 表结构初始化完成（11 表 + 1 向量表）")


async def upsert_user(nickname: str) -> dict:
    """昵称即用户 ID。存在则返回已有用户，否则创建。"""
    _FORBIDDEN = {"system"}
    if nickname.lower() in _FORBIDDEN:
        raise ValueError("该昵称被保留，不可使用")
    conn = await get_db()
    cursor = await conn.execute(
        "SELECT user_id, nickname, created_at FROM users WHERE user_id = ?",
        (nickname,),
    )
    row = await cursor.fetchone()
    if row:
        return dict(row)
    created_at = now_ms()
    await conn.execute(
        "INSERT INTO users (user_id, nickname, created_at) VALUES (?, ?, ?)",
        (nickname, nickname, created_at),
    )
    await conn.commit()
    return {"user_id": nickname, "nickname": nickname, "created_at": created_at}


# ── Worlds ──

async def list_worlds(user_id: str) -> list[dict]:
    conn = await get_db()
    cursor = await conn.execute(
        "SELECT w.*, (SELECT COUNT(*) FROM world_characters c WHERE c.world_id = w.world_id) "
        "AS character_count FROM worlds w "
        "WHERE w.is_deleted = 0 AND (w.is_preset = 1 OR w.user_id = ?) "
        "ORDER BY w.created_at DESC",
        (user_id,),
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def get_world(world_id: str) -> dict | None:
    conn = await get_db()
    cursor = await conn.execute(
        "SELECT * FROM worlds WHERE world_id = ? AND is_deleted = 0", (world_id,),
    )
    row = await cursor.fetchone()
    return dict(row) if row else None


async def get_world_characters(world_id: str) -> list[dict]:
    conn = await get_db()
    cursor = await conn.execute(
        "SELECT * FROM world_characters WHERE world_id = ? ORDER BY sort_order ASC",
        (world_id,),
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def create_world(user_id: str, name: str, description: str, world_history: str,
                        rules: list[str], initial_event: dict, characters: list[dict]) -> str:
    if len(characters) < 3 or len(characters) > 10:
        raise ValueError("角色数量必须在 3-10 之间")
    from uuid import uuid4
    conn = await get_db()
    world_id = f"world_{uuid4().hex[:8]}"
    now = now_ms()
    await conn.execute(
        "INSERT INTO worlds (world_id, user_id, name, description, world_history, "
        "rules, initial_event, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (world_id, user_id, name, description, world_history,
         json.dumps(rules, ensure_ascii=False),
         json.dumps(initial_event, ensure_ascii=False), now),
    )
    assigned: set[str] = set()
    for i, char in enumerate(characters):
        char_id = f"char_{uuid4().hex[:8]}"
        accent = char.get("accent_color", "") or _pick_accent_color(char["name"], assigned)
        assigned.add(accent)
        await conn.execute(
            "INSERT INTO world_characters (character_id, world_id, name, identity, "
            "personality, speech_style, goal, attitudes, backstory, initial_location, "
            "initial_state, accent_color, sort_order) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (char_id, world_id,
             char["name"], char.get("identity", ""), char.get("personality", ""),
             char.get("speech_style", ""), char.get("goal", ""),
             json.dumps(char.get("attitudes", {}), ensure_ascii=False),
             char.get("backstory", ""),
             char.get("initial_location", ""), char.get("initial_state", ""),
             accent, i),
        )
    await conn.commit()
    return world_id


async def update_world(world_id: str, user_id: str, name: str, description: str,
                       world_history: str, rules: list[str], initial_event: dict,
                       characters: list[dict]) -> bool:
    """更新世界及角色数据。先删旧角色再写新角色，在一个事务内完成。"""
    if len(characters) < 3 or len(characters) > 10:
        raise ValueError("角色数量必须在 3-10 之间")
    from uuid import uuid4
    conn = await get_db()
    now = now_ms()
    cursor = await conn.execute(
        "UPDATE worlds SET name = ?, description = ?, world_history = ?, "
        "rules = ?, initial_event = ? WHERE world_id = ? AND user_id = ? "
        "AND is_deleted = 0",
        (name, description, world_history,
         json.dumps(rules, ensure_ascii=False),
         json.dumps(initial_event, ensure_ascii=False),
         world_id, user_id),
    )
    if cursor.rowcount == 0:
        await conn.rollback()
        return False
    await conn.execute("DELETE FROM world_characters WHERE world_id = ?", (world_id,))
    assigned: set[str] = set()
    for i, char in enumerate(characters):
        char_id = f"char_{uuid4().hex[:8]}"
        accent = char.get("accent_color", "") or _pick_accent_color(char["name"], assigned)
        assigned.add(accent)
        await conn.execute(
            "INSERT INTO world_characters (character_id, world_id, name, identity, "
            "personality, speech_style, goal, attitudes, backstory, initial_location, "
            "initial_state, accent_color, sort_order) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (char_id, world_id,
             char["name"], char.get("identity", ""), char.get("personality", ""),
             char.get("speech_style", ""), char.get("goal", ""),
             json.dumps(char.get("attitudes", {}), ensure_ascii=False),
             char.get("backstory", ""),
             char.get("initial_location", ""), char.get("initial_state", ""),
             accent, i),
        )
    await conn.commit()
    return True


async def soft_delete_world(world_id: str, user_id: str) -> bool:
    conn = await get_db()
    cursor = await conn.execute(
        "UPDATE worlds SET is_deleted = 1 WHERE world_id = ? AND user_id = ? "
        "AND is_deleted = 0", (world_id, user_id),
    )
    await conn.commit()
    return cursor.rowcount > 0


# ── Evolutions ──

async def list_evolutions(user_id: str) -> list[dict]:
    conn = await get_db()
    cursor = await conn.execute(
        "SELECT evolution_id, user_id, world_id, status, current_round, max_rounds, "
        "created_at FROM world_evolutions WHERE user_id = ? AND is_deleted = 0 "
        "ORDER BY created_at DESC", (user_id,),
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def get_evolution(evolution_id: str) -> dict | None:
    conn = await get_db()
    cursor = await conn.execute(
        "SELECT * FROM world_evolutions WHERE evolution_id = ? AND is_deleted = 0",
        (evolution_id,),
    )
    row = await cursor.fetchone()
    return dict(row) if row else None


async def soft_delete_evolution(evolution_id: str, user_id: str) -> bool:
    conn = await get_db()
    cursor = await conn.execute(
        "UPDATE world_evolutions SET is_deleted = 1 WHERE evolution_id = ? "
        "AND user_id = ? AND is_deleted = 0", (evolution_id, user_id),
    )
    await conn.commit()
    return cursor.rowcount > 0


async def update_evolution_state(evolution_id: str, director_context: str,
                                  character_contexts: str, timeline: str,
                                  relationships: str, status: str, current_round: int):
    conn = await get_db()
    await conn.execute(
        "UPDATE world_evolutions SET director_context = ?, character_contexts = ?, "
        "timeline = ?, relationships = ?, status = ?, current_round = ? "
        "WHERE evolution_id = ?",
        (director_context, character_contexts, timeline, relationships,
         status, current_round, evolution_id),
    )
    await conn.commit()


# ── Novels ──

async def create_novel(user_id: str, world_id: str, evolution_id: str, title: str,
                        content: str, world_snapshot: dict) -> str:
    from uuid import uuid4
    conn = await get_db()
    novel_id = f"novel_{uuid4().hex[:8]}"
    now = now_ms()
    await conn.execute(
        "INSERT INTO novels (novel_id, user_id, world_id, evolution_id, title, "
        "content, world_snapshot, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (novel_id, user_id, world_id, evolution_id, title, content,
         json.dumps(world_snapshot, ensure_ascii=False), now),
    )
    await conn.commit()
    return novel_id


async def create_novel_task(task_id: str, novel_id: str, evolution_id: str):
    conn = await get_db()
    now = now_ms()
    await conn.execute(
        "INSERT INTO novel_tasks (task_id, novel_id, evolution_id, status, created_at) "
        "VALUES (?, ?, ?, 'processing', ?)",
        (task_id, novel_id, evolution_id, now),
    )
    await conn.commit()


async def update_novel_task(task_id: str, status: str, result: str | None = None,
                             error: str | None = None):
    conn = await get_db()
    now = now_ms()
    await conn.execute(
        "UPDATE novel_tasks SET status = ?, result = ?, error = ?, completed_at = ? "
        "WHERE task_id = ?",
        (status, result, error, now, task_id),
    )
    await conn.commit()


async def get_novel_task(task_id: str) -> dict | None:
    conn = await get_db()
    cursor = await conn.execute(
        "SELECT * FROM novel_tasks WHERE task_id = ?", (task_id,),
    )
    row = await cursor.fetchone()
    return dict(row) if row else None


async def get_latest_novel_task_status(novel_id: str) -> str | None:
    """获取小说最新的任务状态（processing/completed/failed）。"""
    conn = await get_db()
    cursor = await conn.execute(
        "SELECT status FROM novel_tasks WHERE novel_id = ? "
        "ORDER BY created_at DESC LIMIT 1",
        (novel_id,),
    )
    row = await cursor.fetchone()
    return row["status"] if row else None


async def get_processing_task_by_evolution(evolution_id: str) -> dict | None:
    """获取某个演化记录正在处理中的小说任务（排除已软删除的小说）。"""
    conn = await get_db()
    cursor = await conn.execute(
        "SELECT nt.* FROM novel_tasks nt "
        "JOIN novels n ON n.novel_id = nt.novel_id AND n.is_deleted = 0 "
        "WHERE nt.evolution_id = ? AND nt.status = 'processing' "
        "ORDER BY nt.created_at DESC LIMIT 1",
        (evolution_id,),
    )
    row = await cursor.fetchone()
    return dict(row) if row else None


async def list_novels(user_id: str) -> list[dict]:
    conn = await get_db()
    cursor = await conn.execute(
        "SELECT n.novel_id, n.user_id, n.world_id, n.evolution_id, n.title, "
        "n.created_at, nt.status AS task_status, "
        "MAX(nc.created_at) AS last_char_imported_at "
        "FROM novels n "
        "LEFT JOIN novel_tasks nt ON n.novel_id = nt.novel_id "
        "AND nt.created_at = (SELECT MAX(created_at) FROM novel_tasks WHERE novel_id = n.novel_id) "
        "LEFT JOIN novel_characters nc ON n.novel_id = nc.novel_id AND nc.is_deleted = 0 "
        "WHERE n.user_id = ? AND n.is_deleted = 0 "
        "GROUP BY n.novel_id "
        "ORDER BY last_char_imported_at DESC NULLS LAST, n.created_at DESC",
        (user_id,),
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def get_novel(novel_id: str) -> dict | None:
    conn = await get_db()
    cursor = await conn.execute(
        "SELECT * FROM novels WHERE novel_id = ? AND is_deleted = 0", (novel_id,),
    )
    row = await cursor.fetchone()
    return dict(row) if row else None


async def soft_delete_novel(novel_id: str, user_id: str) -> bool:
    conn = await get_db()
    cursor = await conn.execute(
        "UPDATE novels SET is_deleted = 1 WHERE novel_id = ? AND user_id = ? "
        "AND is_deleted = 0", (novel_id, user_id),
    )
    if cursor.rowcount > 0:
        await asyncio.gather(
            conn.execute(
                "UPDATE novel_tasks SET status = 'cancelled' WHERE novel_id = ? AND status = 'processing'",
                (novel_id,),
            ),
            conn.execute(
                "UPDATE novel_characters SET is_deleted = 1 WHERE novel_id = ? AND is_deleted = 0",
                (novel_id,),
            ),
        )
    await conn.commit()
    return cursor.rowcount > 0


async def create_novel_character(novel_id: str, user_id: str,
                                  source_character_id: str, character_snapshot: dict,
                                  story_context: str, accent_color: str) -> str:
    from uuid import uuid4
    conn = await get_db()
    char_id = f"nc_{uuid4().hex[:8]}"
    now = now_ms()
    await conn.execute(
        "INSERT OR REPLACE INTO novel_characters (character_id, novel_id, user_id, "
        "source_character_id, character_snapshot, story_context, accent_color, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (char_id, novel_id, user_id, source_character_id,
         json.dumps(character_snapshot, ensure_ascii=False),
         story_context, accent_color, now),
    )
    await conn.commit()
    return char_id


async def list_novel_characters(novel_id: str) -> list[dict]:
    conn = await get_db()
    cursor = await conn.execute(
        "SELECT * FROM novel_characters WHERE novel_id = ? AND is_deleted = 0 ORDER BY created_at DESC",
        (novel_id,),
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def soft_delete_novel_character(character_id: str) -> bool:
    conn = await get_db()
    cursor = await conn.execute(
        "UPDATE novel_characters SET is_deleted = 1 WHERE character_id = ?",
        (character_id,),
    )
    await conn.commit()
    return cursor.rowcount > 0


# ── Chats ──

async def create_chat(user_id: str, novel_id: str, character_id: str) -> str:
    from uuid import uuid4
    conn = await get_db()
    chat_id = f"chat_{uuid4().hex[:8]}"
    now = now_ms()
    await conn.execute(
        "INSERT INTO character_chats (chat_id, user_id, novel_id, character_id, "
        "messages, created_at, modified_at) VALUES (?, ?, ?, ?, '[]', ?, ?)",
        (chat_id, user_id, novel_id, character_id, now, now),
    )
    await conn.commit()
    return chat_id


async def get_chat(chat_id: str) -> dict | None:
    conn = await get_db()
    cursor = await conn.execute(
        "SELECT * FROM character_chats WHERE chat_id = ? AND is_deleted = 0",
        (chat_id,),
    )
    row = await cursor.fetchone()
    return dict(row) if row else None


async def get_latest_chat_novel(user_id: str) -> str | None:
    """获取用户最近互动的对话对应的 novel_id。"""
    conn = await get_db()
    cursor = await conn.execute(
        "SELECT novel_id FROM character_chats "
        "WHERE user_id = ? AND is_deleted = 0 "
        "ORDER BY modified_at DESC LIMIT 1",
        (user_id,),
    )
    row = await cursor.fetchone()
    return row["novel_id"] if row else None


async def list_chats(user_id: str, novel_id: str | None = None, character_id: str | None = None) -> list[dict]:
    conn = await get_db()
    base = (
        "SELECT c.chat_id, c.user_id, c.novel_id, c.character_id, "
        "c.created_at, c.modified_at, "
        "json_extract(nc.character_snapshot, '$.name') AS character_name, "
        "nc.accent_color "
        "FROM character_chats c "
        "JOIN novel_characters nc ON c.character_id = nc.character_id "
        "WHERE c.user_id = ? AND c.is_deleted = 0"
    )
    params: list = [user_id]
    if novel_id:
        base += " AND c.novel_id = ?"
        params.append(novel_id)
    if character_id:
        base += " AND c.character_id = ?"
        params.append(character_id)
    base += " ORDER BY c.modified_at DESC"
    cursor = await conn.execute(base, tuple(params))
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def get_chat_messages(chat_id: str) -> list[dict]:
    conn = await get_db()
    cursor = await conn.execute(
        "SELECT messages FROM character_chats WHERE chat_id = ? AND is_deleted = 0",
        (chat_id,),
    )
    row = await cursor.fetchone()
    if not row or not row["messages"]:
        return []
    return json.loads(row["messages"])


async def append_chat_message(chat_id: str, role: str, content: str):
    conn = await get_db()
    cursor = await conn.execute(
        "SELECT messages FROM character_chats WHERE chat_id = ?", (chat_id,),
    )
    row = await cursor.fetchone()
    if not row:
        return
    messages = json.loads(row["messages"]) if row["messages"] else []
    messages.append({"role": role, "content": content})
    await conn.execute(
        "UPDATE character_chats SET messages = ?, modified_at = ? WHERE chat_id = ?",
        (json.dumps(messages, ensure_ascii=False), now_ms(), chat_id),
    )
    await conn.commit()


async def soft_delete_chat(chat_id: str, user_id: str) -> bool:
    conn = await get_db()
    cursor = await conn.execute(
        "UPDATE character_chats SET is_deleted = 1 WHERE chat_id = ? AND user_id = ? "
        "AND is_deleted = 0", (chat_id, user_id),
    )
    await conn.commit()
    return cursor.rowcount > 0
